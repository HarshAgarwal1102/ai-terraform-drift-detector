#!/usr/bin/env python3
"""Fetch last-in-sync anchor candidates for the drift investigation (Task 9B.5).

Writes the anchor-candidate directory that `drift-engine investigate --anchors` reads
(PROJECT_PLAN.md Phase 9B, G9 "Candidate input" and "Anchor fetch"):

    <output-dir>/run-<id>-<attempt>/run.json          {id, run_attempt, repository,
                                                       workflow_path, head_branch, event}
    <output-dir>/run-<id>-<attempt>/drift_report.json the run's public drift report

Rules (locked):
- runs: GET /repos/{repo}/actions/workflows/drift-detection.yml/runs?branch=main&
  status=completed&per_page=100 (one page). Kept: event schedule or workflow_dispatch,
  head_branch main, not the current run id, created within the last 30 days (artifact
  retention); the newest 50 at most (G9's limit, so `candidate_limit` never comes from here).
- artifacts: only the non-expired artifact named exactly drift-report-<id>; zip <= 10 MB;
  only `drift_report.json` is extracted, as one regular file at the archive root (no paths,
  no symlinks), <= 10 MB uncompressed. 30 s per request; up to 3 retries on 5xx / 429.
- the artifact download redirect is followed WITHOUT the Authorization header (the token
  never reaches the storage host).
- a listing failure is fatal (exit 1, `anchor_fetch_failed` in the caller). A single
  candidate whose artifact is missing, expired, oversized, corrupt or fails to download
  still gets its run.json, without a report: `investigate` then records it as
  `report_invalid`.

Output: counts and fixed skip reasons only; never the token, a URL or report content.

    GH_TOKEN=... fetch_prior_drift_reports.py --repository OWNER/NAME --current-run-id ID \\
        --output-dir DIR [--now 2026-10-05T00:00:00Z]

Exit status: 0 candidates written (possibly none), 1 listing failure, 2 usage error.
Standard library only.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone

WORKFLOW_FILE = "drift-detection.yml"
WORKFLOW_PATH = ".github/workflows/drift-detection.yml"
EVENTS = ("schedule", "workflow_dispatch")
BRANCH = "main"
MAX_CANDIDATES = 50
RETENTION = timedelta(days=30)
PER_PAGE = 100
MAX_ZIP_BYTES = 10 * 1024 * 1024
MAX_REPORT_BYTES = 10 * 1024 * 1024
REPORT_FILE = "drift_report.json"
TIMEOUT_SECONDS = 30
RETRIES = 3
SKIP_REASONS = ("artifact_missing", "artifact_expired", "artifact_too_large", "download_failed", "archive_invalid")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")


class ListingError(Exception):
    """The run or artifact listing could not be read: the fetch fails (fixed code only)."""


class CandidateError(Exception):
    """One candidate's report could not be fetched; `reason` is one of SKIP_REASONS."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102 - stdlib signature
        return None


class GitHub:
    def __init__(self, api: str, token: str, sleep=time.sleep) -> None:
        self.api, self.token, self.sleep = api.rstrip("/"), token, sleep
        self._no_redirect = urllib.request.build_opener(_NoRedirect)
        self._plain = urllib.request.build_opener()

    def _open(self, url: str, authorized: bool, follow: bool):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "drift-detector-anchor-fetch"}
        if authorized:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, headers=headers)
        opener = self._plain if follow else self._no_redirect
        for attempt in range(RETRIES + 1):
            try:
                return opener.open(request, timeout=TIMEOUT_SECONDS)
            except urllib.error.HTTPError as exc:
                if exc.code in (301, 302, 303, 307, 308) and not follow:
                    return exc  # the caller reads Location
                if exc.code in (429,) or 500 <= exc.code < 600:
                    if attempt < RETRIES:
                        self.sleep(min(2 ** attempt, 8))
                        continue
                raise
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt < RETRIES:
                    self.sleep(min(2 ** attempt, 8))
                    continue
                raise
        raise OSError("unreachable")  # pragma: no cover

    def json(self, path: str, query: dict) -> dict:
        url = f"{self.api}{path}?{urllib.parse.urlencode(query)}"
        try:
            with self._open(url, authorized=True, follow=False) as response:
                data = json.loads(response.read(5 * 1024 * 1024 + 1))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise ListingError(type(exc).__name__) from None
        if not isinstance(data, dict):
            raise ListingError("invalid_json")
        return data

    def download(self, url: str) -> bytes:
        """The artifact zip: the API answers with a redirect to signed storage, fetched without the token."""
        try:
            first = self._open(url, authorized=True, follow=False)
            location = first.headers.get("Location") if getattr(first, "code", 200) in (301, 302, 303, 307, 308) \
                else None
            if location is None:
                body = first.read(MAX_ZIP_BYTES + 1)
            else:
                first.close()
                with self._open(location, authorized=False, follow=True) as response:
                    body = response.read(MAX_ZIP_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, OSError):
            raise CandidateError("download_failed") from None
        if len(body) > MAX_ZIP_BYTES:
            raise CandidateError("artifact_too_large")
        return body


def _parse_time(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def select_runs(payload: dict, current_run_id: int, now: datetime) -> list[dict]:
    """The candidate runs of one listing page, newest first, at most MAX_CANDIDATES."""
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise ListingError("invalid_json")
    kept = []
    for run in runs:
        if not isinstance(run, dict):
            raise ListingError("invalid_json")
        created = _parse_time(run.get("created_at"))
        run_id, attempt = run.get("id"), run.get("run_attempt")
        if (type(run_id) is not int or type(attempt) is not int or created is None
                or run_id == current_run_id or run.get("event") not in EVENTS or run.get("head_branch") != BRANCH
                or run.get("path") != WORKFLOW_PATH or created < now - RETENTION or created > now):
            continue
        kept.append(run)
    kept.sort(key=lambda r: (_parse_time(r["created_at"]), r["id"]), reverse=True)
    return kept[:MAX_CANDIDATES]


def extract_report(archive: bytes) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            entries = [i for i in zf.infolist() if i.filename == REPORT_FILE]
            if len(entries) != 1:
                raise CandidateError("archive_invalid")
            info = entries[0]
            file_type = stat.S_IFMT(info.external_attr >> 16)  # 0 when the archiver records no type
            if info.is_dir() or (file_type and file_type != stat.S_IFREG) or info.file_size > MAX_REPORT_BYTES:
                raise CandidateError("archive_invalid" if info.file_size <= MAX_REPORT_BYTES else "artifact_too_large")
            with zf.open(info) as fh:
                data = fh.read(MAX_REPORT_BYTES + 1)
    except (zipfile.BadZipFile, OSError, RuntimeError, ValueError):
        raise CandidateError("archive_invalid") from None
    if len(data) > MAX_REPORT_BYTES:
        raise CandidateError("artifact_too_large")
    return data


def fetch_report(github: GitHub, repository: str, run_id: int) -> bytes:
    name = f"drift-report-{run_id}"
    payload = github.json(f"/repos/{repository}/actions/runs/{run_id}/artifacts", {"name": name, "per_page": 100})
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise ListingError("invalid_json")
    matches = [a for a in artifacts if isinstance(a, dict) and a.get("name") == name]
    if len(matches) != 1:
        raise CandidateError("artifact_missing")
    artifact = matches[0]
    if artifact.get("expired") is not False:
        raise CandidateError("artifact_expired")
    size = artifact.get("size_in_bytes")
    if type(size) is not int or size > MAX_ZIP_BYTES:
        raise CandidateError("artifact_too_large")
    url = artifact.get("archive_download_url")
    expected = f"{github.api}/repos/{repository}/actions/artifacts/"
    if not isinstance(url, str) or not url.startswith(expected):
        raise CandidateError("artifact_missing")
    return extract_report(github.download(url))


def _write(path: str, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def fetch(github: GitHub, repository: str, current_run_id: int, output_dir: str, now: datetime) -> Counter:
    payload = github.json(f"/repos/{repository}/actions/workflows/{WORKFLOW_FILE}/runs",
                          {"branch": BRANCH, "status": "completed", "per_page": PER_PAGE})
    runs = select_runs(payload, current_run_id, now)
    counts: Counter = Counter(listed=len(payload.get("workflow_runs") or []), candidates=len(runs))
    for run in runs:
        directory = os.path.join(output_dir, f"run-{run['id']}-{run['run_attempt']}")
        os.mkdir(directory, 0o700)
        metadata = {"id": run["id"], "run_attempt": run["run_attempt"], "repository": repository,
                    "workflow_path": run["path"], "head_branch": run["head_branch"], "event": run["event"]}
        _write(os.path.join(directory, "run.json"), json.dumps(metadata, sort_keys=True).encode())
        try:
            report = fetch_report(github, repository, run["id"])
        except CandidateError as exc:
            counts[f"skipped_{exc.reason}"] += 1
            continue
        _write(os.path.join(directory, REPORT_FILE), report)
        counts["reports"] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch drift-report anchor candidates (Task 9B.5).")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--current-run-id", required=True, type=int)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--now", help="current UTC time (ISO 8601; default: now)")
    args = parser.parse_args(argv)
    token = os.environ.get("GH_TOKEN", "")
    now = _parse_time(args.now) if args.now else datetime.now(timezone.utc)
    if not token or not _REPOSITORY.match(args.repository) or now is None or args.current_run_id < 1:
        print("anchor_fetch=usage", file=sys.stderr)
        return 2
    try:
        if os.path.lexists(args.output_dir) and (os.path.islink(args.output_dir) or os.listdir(args.output_dir)):
            raise OSError("output directory not new or empty")
        os.makedirs(args.output_dir, mode=0o700, exist_ok=True)
    except OSError:
        print("anchor_fetch=usage", file=sys.stderr)
        return 2
    github = GitHub(os.environ.get("GITHUB_API_URL", "https://api.github.com"), token)
    try:
        counts = fetch(github, args.repository, args.current_run_id, args.output_dir, now)
    except ListingError:
        print("anchor_fetch=failed reason=listing_failed")
        return 1
    except OSError:
        print("anchor_fetch=failed reason=write_failed")
        return 1
    print("anchor_fetch=ok " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
