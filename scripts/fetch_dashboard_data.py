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

Output: counts and fixed reasons only; never the token, a URL or artifact content. A failure
names its step (`artifacts` or `issues`) and, for an HTTP error of the issue listing, its status
(`detail=http_403` usually means the token lacks "Issues: read"). Artifacts written before an
issue-step failure are kept and reported (`dashboard_fetch=partial`).

    GH_TOKEN=... fetch_dashboard_data.py --repository OWNER/NAME --data-dir DIR [--days 30] [--every 300]

GH_TOKEN needs read access to Actions artifacts and issues of the repository only (for
example a fine-grained token with "Actions: read" and "Issues: read"). Exit status: 0 done,
1 listing or write failure, 2 usage error. Standard library only.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
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
SKIP_REASONS = ("artifact_expired", "artifact_too_large", "download_failed", "archive_invalid", "not_main",
                "too_old", "invalid_listing_entry")


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
    except OSError:
        for leftover in os.listdir(staging):
            os.remove(os.path.join(staging, leftover))
        os.rmdir(staging)
        raise


def list_artifacts(github: fpr.GitHub, repository: str) -> list[dict]:
    found: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        payload = github.json(f"/repos/{repository}/actions/artifacts", {"per_page": PER_PAGE, "page": page})
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
    for artifact in list_artifacts(github, repository):
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
        try:
            with github._open(url, authorized=True, follow=False) as response:
                items = json.loads(response.read(5 * 1024 * 1024 + 1))
        except urllib.error.HTTPError as exc:
            raise fpr.ListingError(f"http_{exc.code}") from None
        except (OSError, ValueError) as exc:
            raise fpr.ListingError(type(exc).__name__) from None
        if not isinstance(items, list):
            raise fpr.ListingError("invalid_json")
        issues += [entry for entry in (issue_entry(i, repository) for i in items) if entry is not None]
        if len(items) < PER_PAGE:
            break
    issues.sort(key=lambda i: i["number"])
    snapshot = {"snapshot_version": SNAPSHOT_VERSION, "repository": repository, "label": gha.LABEL,
                "fetched_at": _timestamp(now), "issues": issues}
    fd, staging = tempfile.mkstemp(prefix=".issues-", dir=data_dir)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2, sort_keys=True)
    os.chmod(staging, 0o600)
    os.replace(staging, os.path.join(data_dir, ISSUES_FILE))
    return Counter(issues=len(issues), issues_open=sum(1 for i in issues if i["state"] == "open"))


def _detail(exc: Exception) -> str:
    code = str(exc)
    return f" detail={code}" if re.fullmatch(r"http_[1-5][0-9]{2}|[A-Za-z]{1,40}", code) else ""


def _counts(counts: Counter) -> str:
    return " ".join(f"{k}={v}" for k, v in sorted(counts.items()))


def run_once(github: fpr.GitHub, repository: str, data_dir: str, days: int) -> int:
    now = datetime.now(timezone.utc)
    try:
        counts = fetch_artifacts(github, repository, data_dir, now, days)
    except fpr.ListingError as exc:
        print(f"dashboard_fetch=failed step=artifacts reason=listing_failed{_detail(exc)}")
        return 1
    except OSError:
        print("dashboard_fetch=failed step=artifacts reason=write_failed")
        return 1
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch the dashboard's live data from GitHub (Task 13.3).")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--days", type=int, default=30, help="artifact age limit in days (1-90, default 30)")
    parser.add_argument("--every", type=int, default=0, help="repeat every N seconds (>= 60; default: once)")
    args = parser.parse_args(argv)
    token = os.environ.get("GH_TOKEN", "")
    if (not token or not fpr._REPOSITORY.match(args.repository) or not 1 <= args.days <= 90
            or (args.every and args.every < 60)):
        print("dashboard_fetch=usage", file=sys.stderr)
        return 2
    try:
        if os.path.islink(args.data_dir):
            raise OSError("symbolic link")
        os.makedirs(args.data_dir, mode=0o700, exist_ok=True)
    except OSError:
        print("dashboard_fetch=usage", file=sys.stderr)
        return 2
    github = fpr.GitHub(os.environ.get("GITHUB_API_URL", "https://api.github.com"), token)
    while True:
        status = run_once(github, args.repository, args.data_dir, args.days)
        if not args.every:
            return status
        time.sleep(args.every)


if __name__ == "__main__":
    sys.exit(main())
