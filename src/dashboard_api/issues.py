"""GitHub drift-issue states for the dashboard (Task 13.3).

The data comes only from the snapshot that `scripts/fetch_dashboard_data.py` writes
(`github_issues.json` in the data directory): the drift issues of Tasks 8.1/8.3 with
their state, close reason, timestamps and first-line marker. A drift is matched to its
issues by the marker fingerprint fp(environment, address), the same formula as
`scripts/github_automation.fingerprint` (kept equal by a test).

Lifecycle (Task 8.3): one open issue per fingerprint at a time; it is created by the drifted
run's issues job (after the run's observation) or updated if already open, and closed with
state_reason `completed` by a later run that sees the resource in sync; a recurrence gets a
new issue. So the issue of a drift observed by run R is the earliest-created issue with that
fingerprint that was still open when R finished (closed_at is null or later than R's
`finished_at`). Without a snapshot the status is `no_snapshot`; with one but no such issue it
is `none_found`. Nothing is guessed.

Remediation pull requests: automated remediation PRs do not exist in this project (Task 8.2
is blocked, superseded by Phase 11, which is on hold), so every drift reports
`remediation_pr: not_enabled` rather than an invented PR state.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from typing import Any

from drift_engine import investigation_public as pub

ISSUES_FILE = "github_issues.json"
MAX_BYTES = 5 * 1024 * 1024
MARKER_VERSION = 1
_URL = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}/issues/[1-9][0-9]{0,9}$")
_TIME = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_FP = re.compile(r"^[0-9a-f]{64}$")
_RUN = re.compile(r"^github-[0-9]{1,20}-[0-9]{1,6}$")
_KEYS = {"number", "url", "state", "state_reason", "created_at", "closed_at", "fingerprint", "marker_run",
         "marker_plan"}
REMEDIATION_PR = {"status": "not_enabled",
                  "reason": "Automated remediation pull requests are not enabled (Task 8.2 superseded by Phase 11, "
                            "which is on hold); remediation stays a manual, approved action."}


def fingerprint(environment: str, address: str) -> str:
    return hashlib.sha256(f"drift-issue-fingerprint:v{MARKER_VERSION}\n{environment}\n{address}".encode()).hexdigest()


@dataclass(frozen=True)
class Snapshot:
    repository: str
    fetched_at: str
    issues: tuple[dict, ...]


def _valid_issue(item: Any) -> bool:
    return (isinstance(item, dict) and set(item) == _KEYS and type(item["number"]) is int and item["number"] > 0
            and isinstance(item["url"], str) and bool(_URL.match(item["url"]))
            and item["url"].endswith(f"/issues/{item['number']}")
            and item["state"] in ("open", "closed")
            and item["state_reason"] in (None, "completed", "not_planned", "reopened")
            and isinstance(item["created_at"], str) and bool(_TIME.match(item["created_at"]))
            and (item["closed_at"] is None or (isinstance(item["closed_at"], str) and bool(_TIME.match(item["closed_at"]))))
            and (item["state"] == "closed") == (item["closed_at"] is not None)
            and isinstance(item["fingerprint"], str) and bool(_FP.match(item["fingerprint"]))
            and isinstance(item["marker_run"], str) and bool(_RUN.match(item["marker_run"]))
            and isinstance(item["marker_plan"], str) and bool(_TIME.match(item["marker_plan"])))


def load(root: str) -> tuple[Snapshot | None, str | None]:
    """(snapshot, None), (None, None) when there is none, or (None, problem code)."""
    path = os.path.join(root, ISSUES_FILE)
    if not os.path.lexists(path):
        return None, None
    if os.path.islink(path) or not os.path.isfile(path):
        return None, "issues_snapshot_invalid"
    try:
        with open(path, "rb") as fh:
            data = fh.read(MAX_BYTES + 1)
        doc = pub.strict_json(data) if len(data) <= MAX_BYTES else None
    except (OSError, ValueError, RecursionError, UnicodeDecodeError):
        doc = None
    issues = doc.get("issues") if isinstance(doc, dict) else None
    if not (isinstance(doc, dict) and doc.get("snapshot_version") == "1" and doc.get("label") == "drift-detected"
            and isinstance(doc.get("repository"), str) and isinstance(doc.get("fetched_at"), str)
            and _TIME.match(doc["fetched_at"]) and isinstance(issues, list) and all(map(_valid_issue, issues))):
        return None, "issues_snapshot_invalid"
    if any(not issue["url"].startswith(f"https://github.com/{doc['repository']}/issues/") for issue in issues):
        return None, "issues_snapshot_invalid"
    return Snapshot(doc["repository"], doc["fetched_at"], tuple(issues)), None


def _public(issue: dict) -> dict:
    return {k: issue[k] for k in ("number", "url", "state", "state_reason", "created_at", "closed_at")}


def _instant(timestamp: str) -> str:
    """`...Z` timestamps with or without fractional seconds, comparable as strings to the second."""
    return timestamp[:19]


def issue_status(snapshot: Snapshot | None, environment: str | None, address: str | None,
                 run_finished_at: str | None) -> dict:
    """The drift issue of (environment, address) for the run that finished at `run_finished_at`."""
    if snapshot is None:
        return {"status": "no_snapshot", "fetched_at": None}
    if not environment or not address or not isinstance(run_finished_at, str) or not _TIME.match(
            run_finished_at[:19] + "Z"):
        return {"status": "none_found", "fetched_at": snapshot.fetched_at}
    fp, finished = fingerprint(environment, address), _instant(run_finished_at)
    candidates = sorted((i for i in snapshot.issues if i["fingerprint"] == fp
                         and (i["closed_at"] is None or _instant(i["closed_at"]) > finished)),
                        key=lambda i: (i["created_at"], i["number"]))
    if not candidates:
        return {"status": "none_found", "fetched_at": snapshot.fetched_at}
    chosen = candidates[0]
    return dict(_public(chosen), status=chosen["state"], fetched_at=snapshot.fetched_at)


def summary(snapshot: Snapshot | None, addresses: set[tuple[str, str]]) -> dict:
    """Every drift issue of the snapshot, with its resource when a known report names it."""
    if snapshot is None:
        return {"snapshot": False, "fetched_at": None, "open": 0, "closed": 0, "items": []}
    known = {fingerprint(env, addr): (env, addr) for env, addr in addresses}
    items = []
    for issue in sorted(snapshot.issues, key=lambda i: i["number"], reverse=True):
        env, addr = known.get(issue["fingerprint"], (None, None))
        items.append(dict(_public(issue), environment=env, address=addr))
    return {"snapshot": True, "fetched_at": snapshot.fetched_at, "repository": snapshot.repository,
            "open": sum(1 for i in items if i["state"] == "open"),
            "closed": sum(1 for i in items if i["state"] == "closed"), "items": items}
