#!/usr/bin/env python3
"""Fetch the dashboard's live data from GitHub (Task 13.3).

Writes, into the dashboard data directory (`DASHBOARD_DATA_DIR`):

    <data-dir>/<artifact-name>/<file>   the real workflow artifacts, one directory each:
        drift-report-<id>/drift_report.json
        drift-investigation-<id>/drift_investigation.json
        ai-analysis-report-<id>/ai_analysis_report.json
        infracost-report-<id>/cost_run.json
        unmanaged-inventory-<id>/unmanaged_inventory.json
    <data-dir>/github_issues.json       a snapshot of the drift issues (label drift-detected)

Rules:
- artifacts: GET /repos/{repo}/actions/artifacts (up to MAX_PAGES pages of 100). Kept: an exact
  name above, not expired, from a run on `main`, created within --days (default 30, the
  artifact retention). Artifacts are immutable, so an existing directory is never fetched
  again. Only the expected JSON file is extracted (one regular file at the archive root,
  bounded size) and written atomically (0600 file in a 0700 directory).
- downloads reuse fetch_prior_drift_reports.GitHub: the token goes to the API only; the
  redirect to signed storage is followed without it.
- issues: GET /repos/{repo}/issues?state=all&labels=drift-detected; pull requests are
  skipped. Only the state, timestamps, number, URL and the first-line marker fields
  (fingerprint, run, plan timestamp) are stored: never a title, body, user or label list.
- --every SECONDS repeats the fetch (live refresh); the dashboard re-reads on every request.
- staging: an artifact is written into a hidden `.fetch-*` folder and renamed into place, the
  issue snapshot into a hidden `.issues-*` file replaced into place. Leftovers of an interrupted
  fetch (older than STALE_STAGING_SECONDS) are removed at the start of every fetch; the
  dashboard never reads hidden entries. On SIGTERM (the dashboard's timeout or shutdown) the
  script removes its own staging entry and exits with status 143.

--verify-only (Task 13.5) checks the token instead of fetching: three read-only requests (repository,
Actions artifacts, issues) and one line, `dashboard_verify=ok` or `dashboard_verify=failed reason=<category>
[http=NNN] [need=actions|issues]` (an `ok` line may add `warning=insufficient_permissions http=403 need=issues`
when only the issue listing is refused: reports can still be fetched). Categories: invalid_token (401), insufficient_permissions (403 without a
rate-limit signal), repository_not_accessible (404), sso_required (403 with `X-GitHub-SSO`), rate_limited
(429, a rate-limit header, or a secondary-rate-limit message), network_error, api_error. During a fetch
the script prints `dashboard_stage=listing|downloading|issues` lines before its result line.

Output: counts and fixed reasons only; never the token, a URL or artifact content. A failure
names its step (`artifacts` or `issues`) and, for an HTTP error of the issue listing, its status
(`detail=http_403` usually means the token lacks "Issues: read"). Artifacts written before an
issue-step failure are kept and reported (`dashboard_fetch=partial`).

    GH_TOKEN=... fetch_dashboard_data.py --repository OWNER/NAME --data-dir DIR [--days 30] [--every 300]
    fetch_dashboard_data.py --token-stdin --repository OWNER/NAME --data-dir DIR   (token on standard input)

--token-stdin reads the token from the first line of standard input instead of GH_TOKEN, so a
caller (the dashboard's "Check GitHub for new runs" job, Task 13.4) passes it through neither an
environment variable nor an argument. When standard input is a terminal (manual use), the token
is read without echo (getpass) instead of being shown as it is typed. The token needs read access to Actions artifacts and issues of the repository only (for
example a fine-grained token with "Actions: read" and "Issues: read"). Exit status: 0 done,
1 listing or write failure, 2 usage error. Standard library only.
"""

from __future__ import annotations

import argparse
import getpass
import io
import json
import os
import re
import shutil
import signal
import stat
import sys
import tempfile
import time
import urllib.error
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_prior_drift_reports as fpr  # noqa: E402  (sibling script: GitHub client, safe download)
import github_automation as gha  # noqa: E402  (drift issue label and marker format)

ARTIFACT_FILES = {
    "drift-report": "drift_report.json",
    "drift-investigation": "drift_investigation.json",
    "ai-analysis-report": "ai_analysis_report.json",
    "infracost-report": "cost_run.json",
    "unmanaged-inventory": "unmanaged_inventory.json",
}
ARTIFACT_NAME = re.compile(r"^(drift-report|drift-investigation|ai-analysis-report|infracost-report|unmanaged-inventory)"
                           r"-([1-9][0-9]{0,19})$")
ISSUES_FILE = "github_issues.json"
SNAPSHOT_VERSION = "1"
MAX_PAGES = 5
PER_PAGE = 100
MAX_FILE_BYTES = 10 * 1024 * 1024
BRANCH = "main"
STALE_STAGING_SECONDS = 3600  # longer than any fetch may run (the dashboard job's timeout is 10 minutes)
MAX_TOKEN_CHARS = 1024
SKIP_REASONS = ("artifact_expired", "artifact_too_large", "download_failed", "archive_invalid", "not_main",
                "too_old", "invalid_listing_entry")


def _stage(name: str) -> None:
    """A progress marker for the dashboard's status window (flushed: the output is a pipe)."""
    print(f"dashboard_stage={name}", flush=True)


def _timestamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def extract(archive: bytes, name: str) -> bytes:
    """The one regular file `name` at the archive root."""
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            entries = [i for i in zf.infolist() if i.filename == name]
            if len(entries) != 1:
                raise fpr.CandidateError("archive_invalid")
            info = entries[0]
            file_type = stat.S_IFMT(info.external_attr >> 16)
            if info.is_dir() or (file_type and file_type != stat.S_IFREG):
                raise fpr.CandidateError("archive_invalid")
            if info.file_size > MAX_FILE_BYTES:
                raise fpr.CandidateError("artifact_too_large")
            with zf.open(info) as fh:
                data = fh.read(MAX_FILE_BYTES + 1)
    except (zipfile.BadZipFile, OSError, RuntimeError, ValueError):
        raise fpr.CandidateError("archive_invalid") from None
    if len(data) > MAX_FILE_BYTES:
        raise fpr.CandidateError("artifact_too_large")
    return data


def _write_new_dir(data_dir: str, directory: str, name: str, data: bytes) -> None:
    """data_dir/directory/name, created atomically: a half-written artifact never appears."""
    staging = tempfile.mkdtemp(prefix=".fetch-", dir=data_dir)
    try:
        fd = os.open(os.path.join(staging, name), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.rename(staging, os.path.join(data_dir, directory))
    except BaseException:  # also SIGTERM (SystemExit): never leave a staging folder behind
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _forbidden_kind(exc: urllib.error.HTTPError) -> str:
    """Why GitHub answered 403 (or 429), as a fixed code: `sso_required` (the `X-GitHub-SSO` header: the token
    is not authorized for the organization's SAML single sign-on), `rate_limited` (a 429, a rate-limit header,
    or a secondary-rate-limit message), else `http_403`. At most 4 KB of the body is read, only to match the
    words "rate limit" in its `message`; the body is never printed, logged or returned."""
    headers = exc.headers
    if exc.code == 429:
        return "rate_limited"
    if headers is not None and headers.get("X-GitHub-SSO"):
        return "sso_required"
    if headers is not None and (headers.get("X-RateLimit-Remaining") == "0" or headers.get("Retry-After") is not None):
        return "rate_limited"
    try:
        message = json.loads(exc.read(4096) or b"{}").get("message", "")
    except (OSError, ValueError, AttributeError):
        message = ""
    return "rate_limited" if isinstance(message, str) and "rate limit" in message.lower() else "http_403"


def get_json(github: fpr.GitHub, url: str):
    """The decoded JSON of an authorized GET. Raises fpr.ListingError with a fixed detail:
    `http_NNN`, `rate_limited`, `network` or `invalid_json`; never the URL, the token or the body."""
    try:
        with github._open(url, authorized=True, follow=False) as response:
            return json.loads(response.read(5 * 1024 * 1024 + 1))
    except urllib.error.HTTPError as exc:
        raise fpr.ListingError(_forbidden_kind(exc) if exc.code in (403, 429) else f"http_{exc.code}") from None
    except ValueError:
        raise fpr.ListingError("invalid_json") from None
    except (OSError, TimeoutError):  # URLError, socket errors, timeouts
        raise fpr.ListingError("network") from None


def list_artifacts(github: fpr.GitHub, repository: str) -> list[dict]:
    found: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        payload = get_json(github, f"{github.api}/repos/{repository}/actions/artifacts?per_page={PER_PAGE}&page={page}")
        if not isinstance(payload, dict):
            raise fpr.ListingError("invalid_json")
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list):
            raise fpr.ListingError("invalid_json")
        found += artifacts
        if len(artifacts) < PER_PAGE:
            break
    return found


def fetch_artifacts(github: fpr.GitHub, repository: str, data_dir: str, now: datetime, days: int) -> Counter:
    counts: Counter = Counter()
    expected_url = f"{github.api}/repos/{repository}/actions/artifacts/"
    _stage("listing")
    listed = list_artifacts(github, repository)
    _stage("downloading")
    for artifact in listed:
        name = artifact.get("name") if isinstance(artifact, dict) else None
        match = ARTIFACT_NAME.match(name) if isinstance(name, str) else None
        if match is None:
            continue
        counts["listed"] += 1
        if os.path.lexists(os.path.join(data_dir, name)):
            counts["already_present"] += 1
            continue
        created = fpr._parse_time(artifact.get("created_at"))
        run = artifact.get("workflow_run") if isinstance(artifact.get("workflow_run"), dict) else {}
        size, url = artifact.get("size_in_bytes"), artifact.get("archive_download_url")
        try:
            if created is None or type(size) is not int or not isinstance(url, str) or not url.startswith(expected_url):
                raise fpr.CandidateError("invalid_listing_entry")
            if artifact.get("expired") is not False:
                raise fpr.CandidateError("artifact_expired")
            if run.get("head_branch") != BRANCH:
                raise fpr.CandidateError("not_main")
            if created < now - timedelta(days=days):
                raise fpr.CandidateError("too_old")
            if size > fpr.MAX_ZIP_BYTES:
                raise fpr.CandidateError("artifact_too_large")
            data = extract(github.download(url), ARTIFACT_FILES[match.group(1)])
        except fpr.CandidateError as exc:
            counts[f"skipped_{exc.reason}"] += 1
            continue
        _write_new_dir(data_dir, name, ARTIFACT_FILES[match.group(1)], data)
        counts["fetched"] += 1
    return counts


def issue_entry(item: dict, repository: str) -> dict | None:
    """The stored fields of one drift issue, or None when it is not one (or a pull request)."""
    # is_automation_issue checks the bot author, the label and the number; it also requires
    # `open`, so it is asked about an open copy: closed issues carry the resolution state.
    if not isinstance(item, dict) or "pull_request" in item or not gha.is_automation_issue(dict(item, state="open")):
        return None
    try:
        marker = gha.parse_marker(item.get("body") or "")
    except gha.AutomationError:
        return None
    number, url = item.get("number"), item.get("html_url")
    if type(number) is not int or url != f"https://github.com/{repository}/issues/{number}":
        return None
    state, reason = item.get("state"), item.get("state_reason")
    if state not in ("open", "closed"):
        return None
    return {"number": number, "url": url, "state": state,
            "state_reason": reason if reason in ("completed", "not_planned", "reopened") else None,
            "created_at": item.get("created_at"), "closed_at": item.get("closed_at"),
            "fingerprint": marker.fingerprint, "marker_run": marker.run_id, "marker_plan": marker.plan_timestamp}


def fetch_issues(github: fpr.GitHub, repository: str, data_dir: str, now: datetime) -> Counter:
    issues: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        url = f"{github.api}/repos/{repository}/issues?state=all&labels={gha.LABEL}&per_page={PER_PAGE}&page={page}"
        items = get_json(github, url)
        if not isinstance(items, list):
            raise fpr.ListingError("invalid_json")
        issues += [entry for entry in (issue_entry(i, repository) for i in items) if entry is not None]
        if len(items) < PER_PAGE:
            break
    issues.sort(key=lambda i: i["number"])
    snapshot = {"snapshot_version": SNAPSHOT_VERSION, "repository": repository, "label": gha.LABEL,
                "fetched_at": _timestamp(now), "issues": issues}
    fd, staging = tempfile.mkstemp(prefix=".issues-", dir=data_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, indent=2, sort_keys=True)
        os.chmod(staging, 0o600)
        os.replace(staging, os.path.join(data_dir, ISSUES_FILE))
    except BaseException:  # also SIGTERM (SystemExit): never leave a staging file behind
        try:
            os.remove(staging)
        except OSError:
            pass
        raise
    return Counter(issues=len(issues), issues_open=sum(1 for i in issues if i["state"] == "open"))


def _detail(exc: Exception) -> str:
    code = str(exc)
    return f" detail={code}" if re.fullmatch(r"http_[1-5][0-9]{2}|[A-Za-z_]{1,40}", code) else ""


def _counts(counts: Counter) -> str:
    return " ".join(f"{k}={v}" for k, v in sorted(counts.items()))


def remove_stale_staging(data_dir: str, now_seconds: float) -> int:
    """Remove `.fetch-*` folders and `.issues-*` files left by an interrupted fetch (older than
    STALE_STAGING_SECONDS, so a fetch still running elsewhere is left alone). Never follows links."""
    removed = 0
    for name in os.listdir(data_dir):
        if not (name.startswith(".fetch-") or name.startswith(".issues-")):
            continue
        path = os.path.join(data_dir, name)
        try:
            info = os.lstat(path)
            if now_seconds - info.st_mtime < STALE_STAGING_SECONDS:
                continue
            if stat.S_ISDIR(info.st_mode) and name.startswith(".fetch-"):
                shutil.rmtree(path)
            elif stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                os.remove(path)
            else:
                continue
            removed += 1
        except OSError:
            continue
    return removed


def run_once(github: fpr.GitHub, repository: str, data_dir: str, days: int) -> int:
    now = datetime.now(timezone.utc)
    stale = remove_stale_staging(data_dir, time.time())
    try:
        counts = fetch_artifacts(github, repository, data_dir, now, days)
        if stale:
            counts["stale_staging_removed"] = stale
    except fpr.ListingError as exc:
        print(f"dashboard_fetch=failed step=artifacts reason=listing_failed{_detail(exc)}")
        return 1
    except OSError:
        print("dashboard_fetch=failed step=artifacts reason=write_failed")
        return 1
    _stage("issues")
    try:
        counts.update(fetch_issues(github, repository, data_dir, now))
    except fpr.ListingError as exc:
        print(f"dashboard_fetch=partial step=issues reason=listing_failed{_detail(exc)} {_counts(counts)}")
        return 1
    except OSError:
        print(f"dashboard_fetch=partial step=issues reason=write_failed {_counts(counts)}")
        return 1
    print(f"dashboard_fetch=ok at={_timestamp(now)} {_counts(counts)}")
    return 0


def verify_token(github: fpr.GitHub, repository: str) -> int:
    """Read-only check that the token reaches the repository and may list Actions artifacts and issues."""
    base = f"{github.api}/repos/{repository}"
    checks = (("", None), ("/actions/artifacts?per_page=1", "actions"),
              (f"/issues?state=all&labels={gha.LABEL}&per_page=1", "issues"))
    warning = ""
    for suffix, need in checks:
        try:
            get_json(github, base + suffix)
        except fpr.ListingError as exc:
            detail = str(exc)
            if need == "issues" and detail == "http_403":
                # The token authenticates and may list the artifacts (the required access); without
                # "Issues: read" a fetch still downloads reports, only the drift issue states stay stale.
                warning = " warning=insufficient_permissions http=403 need=issues"
                continue
            if detail == "http_401":
                reason, extra = "invalid_token", " http=401"
            elif detail == "http_403":
                reason, extra = "insufficient_permissions", " http=403" + (f" need={need}" if need else "")
            elif detail == "http_404":
                reason, extra = "repository_not_accessible", " http=404"
            elif detail == "sso_required":
                reason, extra = "sso_required", " http=403"
            elif detail == "rate_limited":
                reason, extra = "rate_limited", ""
            elif detail == "network":
                reason, extra = "network_error", ""
            else:
                reason = "api_error"
                extra = f" http={detail[5:]}" if re.fullmatch(r"http_[1-5][0-9]{2}", detail) else ""
            print(f"dashboard_verify=failed reason={reason}{extra}")
            return 1
    print("dashboard_verify=ok" + warning)
    return 0


def _on_sigterm(signum, frame):  # noqa: ARG001 (signal handler signature)
    raise SystemExit(143)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch the dashboard's live data from GitHub (Task 13.3).")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--data-dir")
    parser.add_argument("--verify-only", action="store_true",
                        help="only check that the token can read the repository, its artifacts and its issues")
    parser.add_argument("--days", type=int, default=30, help="artifact age limit in days (1-90, default 30)")
    parser.add_argument("--every", type=int, default=0, help="repeat every N seconds (>= 60; default: once)")
    parser.add_argument("--token-stdin", action="store_true",
                        help="read the token from the first line of standard input instead of GH_TOKEN")
    args = parser.parse_args(argv)
    if args.token_stdin:
        if sys.stdin.isatty():  # typed by hand: never echo it
            token = getpass.getpass("GitHub token (hidden): ")[:MAX_TOKEN_CHARS + 1].strip()
        else:
            token = sys.stdin.readline(MAX_TOKEN_CHARS + 1).strip()
        if len(token) > MAX_TOKEN_CHARS or any(c.isspace() or not c.isprintable() for c in token):
            token = ""
    else:
        token = os.environ.get("GH_TOKEN", "")
    if (not token or not fpr._REPOSITORY.match(args.repository) or not 1 <= args.days <= 90
            or (args.every and args.every < 60) or (not args.verify_only and not args.data_dir)):
        print("dashboard_fetch=usage", file=sys.stderr)
        return 2
    if args.verify_only:
        # One attempt per request: a 429 or an outage is reported at once, never retried in a burst; the user
        # retries from the dashboard (which also enforces a minimum gap between verifications).
        fpr.RETRIES = 0
        return verify_token(fpr.GitHub(os.environ.get("GITHUB_API_URL", "https://api.github.com"), token,
                                       sleep=lambda _seconds: None), args.repository)
    try:
        if os.path.islink(args.data_dir):
            raise OSError("symbolic link")
        os.makedirs(args.data_dir, mode=0o700, exist_ok=True)
    except OSError:
        print("dashboard_fetch=usage", file=sys.stderr)
        return 2
    github = fpr.GitHub(os.environ.get("GITHUB_API_URL", "https://api.github.com"), token)
    # SIGTERM (the dashboard's timeout or shutdown): unwind like an interrupt, so every staging
    # entry is removed by the write functions above, then exit 143 without a result line.
    signal.signal(signal.SIGTERM, _on_sigterm)
    while True:
        status = run_once(github, args.repository, args.data_dir, args.days)
        if not args.every:
            return status
        time.sleep(args.every)


if __name__ == "__main__":
    sys.exit(main())
