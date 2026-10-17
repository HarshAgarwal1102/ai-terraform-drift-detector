"""Tests for the dashboard's live data path (Task 13.3).

Run from the repository root:
    pytest tests/test_dashboard_live.py

- scripts/fetch_dashboard_data.py against a fake GitHub API (no network): which artifacts
  are fetched, how they are extracted and written, and what the issue snapshot stores;
- src/dashboard_api/issues.py: the fingerprint equals github_automation's, the snapshot is
  validated strictly, and each drift shows its open issue, else its latest closed one;
- the API: drift rows carry the issue state and `remediation_pr: not_enabled`.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_dashboard_data as fdd  # noqa: E402
import github_automation as gha  # noqa: E402

from dashboard_api import issues  # noqa: E402

REPO = "owner/repo"
API = "https://api.github.com"
NOW = datetime(2026, 10, 17, 6, 0, tzinfo=timezone.utc)
REAL = ROOT / "tests" / "fixtures" / "dashboard" / "real_9b6"
RG = 'module.resource_group.azurerm_resource_group.this["main"]'
TOKEN = "sentinel-token-value"


def zipped(name: str, data: bytes, extra: dict | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(name, data)
        for other, content in (extra or {}).items():
            zf.writestr(other, content)
    return buffer.getvalue()


def artifact(name: str, number: int, **overrides) -> dict:
    entry = {"name": name, "expired": False, "size_in_bytes": 1000, "created_at": "2026-10-16T00:00:00Z",
             "archive_download_url": f"{API}/repos/{REPO}/actions/artifacts/{number}/zip",
             "workflow_run": {"id": number, "head_branch": "main"}}
    entry.update(overrides)
    return entry


def issue(number: int, fp: str, state: str = "open", **overrides) -> dict:
    item = {"number": number, "state": state, "state_reason": "completed" if state == "closed" else None,
            "html_url": f"https://github.com/{REPO}/issues/{number}", "created_at": "2026-10-16T01:00:00Z",
            "closed_at": "2026-10-16T02:00:00Z" if state == "closed" else None,
            "user": {"login": gha.BOT_LOGIN, "type": gha.BOT_TYPE}, "labels": [{"name": gha.LABEL}],
            "title": "sentinel-title", "body": gha.marker_line(fp, "0" * 64, "github-1-1", "2026-10-16T00:00:00Z")
            + "\nsentinel-body"}
    item.update(overrides)
    return item


class FakeGitHub:
    """The parts of fetch_prior_drift_reports.GitHub the fetcher uses."""

    def __init__(self, artifacts: list[dict], archives: dict[str, bytes], issue_items: list[dict]) -> None:
        self.api, self.artifacts, self.archives, self.issue_items = API, artifacts, archives, issue_items
        self.downloads: list[str] = []

    def json(self, path: str, query: dict) -> dict:
        assert path == f"/repos/{REPO}/actions/artifacts"
        return {"artifacts": self.artifacts}

    def download(self, url: str) -> bytes:
        self.downloads.append(url)
        return self.archives[url]

    def _open(self, url: str, authorized: bool, follow: bool):
        assert url.startswith(f"{API}/repos/{REPO}/issues?state=all&labels=drift-detected")
        return contextlib.closing(io.BytesIO(json.dumps(self.issue_items).encode()))


def real(name: str) -> bytes:
    return next(REAL.glob(f"*/{name}")).read_bytes()


@pytest.fixture
def fake():
    report = (REAL / "drift-report-38105671846" / "drift_report.json").read_bytes()
    fp = gha.fingerprint("dev", RG)
    artifacts = [
        artifact("drift-report-101", 1),
        artifact("drift-investigation-101", 2),
        artifact("ai-analysis-report-101", 3),
        artifact("infracost-report-101", 4),
        artifact("drift-report-102", 5, expired=True),
        artifact("drift-report-103", 6, workflow_run={"id": 6, "head_branch": "feature"}),
        artifact("drift-report-104", 7, created_at="2026-08-01T00:00:00Z"),
        artifact("drift-report-105", 8, size_in_bytes=20 * 1024 * 1024),
        artifact("drift-report-106", 9, archive_download_url="https://evil.example/zip"),
        artifact("drift-report-107", 10),
        artifact("unrelated-artifact-1", 11),
    ]
    archives = {
        f"{API}/repos/{REPO}/actions/artifacts/1/zip": zipped("drift_report.json", report,
                                                              {"detection_run.json": b"{}"}),
        f"{API}/repos/{REPO}/actions/artifacts/2/zip": zipped("drift_investigation.json", b"{}"),
        f"{API}/repos/{REPO}/actions/artifacts/3/zip": zipped("ai_analysis_report.json", b"{}"),
        f"{API}/repos/{REPO}/actions/artifacts/4/zip": zipped("cost_run.json", b"{}"),
        f"{API}/repos/{REPO}/actions/artifacts/10/zip": zipped("nested/drift_report.json", report),
    }
    items = [
        issue(7, fp, "closed"),
        issue(9, fp),
        issue(10, fp, pull_request={"url": "x"}),                    # a pull request
        issue(11, fp, user={"login": "someone", "type": "User"}),    # not the automation bot
        issue(12, fp, labels=[]),                                    # no drift label
        issue(13, fp, body="no marker"),                             # invalid marker
        issue(14, "f" * 64, html_url="https://evil.example/14"),      # wrong URL
    ]
    return FakeGitHub(artifacts, archives, items)


def test_fetch_keeps_only_valid_main_artifacts_and_expected_files(tmp_path, fake):
    counts = fdd.fetch_artifacts(fake, REPO, str(tmp_path), NOW, 30)
    assert counts["fetched"] == 4
    assert {k: v for k, v in counts.items() if k.startswith("skipped_")} == {
        "skipped_artifact_expired": 1, "skipped_not_main": 1, "skipped_too_old": 1, "skipped_artifact_too_large": 1,
        "skipped_invalid_listing_entry": 1, "skipped_archive_invalid": 1}
    files = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file())
    assert files == ["ai-analysis-report-101/ai_analysis_report.json", "drift-investigation-101/drift_investigation.json",
                     "drift-report-101/drift_report.json", "infracost-report-101/cost_run.json"]
    assert (tmp_path / "drift-report-101" / "drift_report.json").stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".fetch-*"))  # no staging leftovers
    again = fdd.fetch_artifacts(fake, REPO, str(tmp_path), NOW, 30)
    assert again["already_present"] == 4 and again["fetched"] == 0  # artifacts are immutable: never refetched


def test_issue_snapshot_stores_only_state_and_marker_fields(tmp_path, fake):
    counts = fdd.fetch_issues(fake, REPO, str(tmp_path), NOW)
    assert (counts["issues"], counts["issues_open"]) == (2, 1)
    text = (tmp_path / "github_issues.json").read_text()
    snapshot = json.loads(text)
    assert [i["number"] for i in snapshot["issues"]] == [7, 9]
    assert set(snapshot["issues"][0]) == {"number", "url", "state", "state_reason", "created_at", "closed_at",
                                          "fingerprint", "marker_run", "marker_plan"}
    assert "sentinel" not in text and "user" not in text and "title" not in text
    assert (tmp_path / "github_issues.json").stat().st_mode & 0o777 == 0o600
    loaded, problem = issues.load(str(tmp_path))
    assert problem is None and loaded.fetched_at == "2026-10-17T06:00:00Z"


def test_main_needs_a_token_and_never_prints_it(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert fdd.main(["--repository", REPO, "--data-dir", str(tmp_path)]) == 2
    monkeypatch.setenv("GH_TOKEN", TOKEN)
    for bad in (["--repository", "not a repo", "--data-dir", str(tmp_path)],
                ["--repository", REPO, "--data-dir", str(tmp_path), "--every", "5"],
                ["--repository", REPO, "--data-dir", str(tmp_path), "--days", "0"]):
        assert fdd.main(bad) == 2
    monkeypatch.setattr(fdd, "run_once", lambda github, repo, data_dir, days: 0)
    assert fdd.main(["--repository", REPO, "--data-dir", str(tmp_path)]) == 0
    out = capsys.readouterr()
    assert TOKEN not in out.out + out.err


def test_listing_failure_is_reported_without_details(tmp_path, capsys):
    class Failing(FakeGitHub):
        def json(self, path, query):
            raise fdd.fpr.ListingError("HTTPError")
    assert fdd.run_once(Failing([], {}, []), REPO, str(tmp_path), 30) == 1
    assert capsys.readouterr().out.strip() == "dashboard_fetch=failed step=artifacts reason=listing_failed detail=HTTPError"


def test_issue_step_failure_keeps_artifacts_and_names_the_status(tmp_path, capsys, fake):
    """A token without "Issues: read": the artifacts are written, the issue step reports HTTP 403."""
    import urllib.error

    class NoIssues(type(fake)):
        def _open(self, url, authorized, follow):
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)

    github = NoIssues(fake.artifacts, fake.archives, [])
    assert fdd.run_once(github, REPO, str(tmp_path), 30) == 1
    out = capsys.readouterr().out.strip()
    assert out.startswith("dashboard_fetch=partial step=issues reason=listing_failed detail=http_403 ")
    assert "fetched=4" in out and TOKEN not in out and "http" + "s://" not in out
    assert (tmp_path / "drift-report-101" / "drift_report.json").is_file()
    assert not (tmp_path / "github_issues.json").exists()


def test_fingerprint_matches_the_issue_automation():
    for env, address in (("dev", RG), ("prod", 'module.x.y["z"]')):
        assert issues.fingerprint(env, address) == gha.fingerprint(env, address)


def snapshot_file(directory: Path, items: list[dict], **overrides) -> None:
    doc = {"snapshot_version": "1", "repository": REPO, "label": "drift-detected",
           "fetched_at": "2026-10-17T06:00:00Z", "issues": items}
    doc.update(overrides)
    (directory / "github_issues.json").write_text(json.dumps(doc))


def stored(number: int, fp: str, state: str) -> dict:
    return {"number": number, "url": f"https://github.com/{REPO}/issues/{number}", "state": state,
            "state_reason": "completed" if state == "closed" else None, "created_at": "2026-10-16T01:00:00Z",
            "closed_at": "2026-10-16T02:00:00Z" if state == "closed" else None, "fingerprint": fp,
            "marker_run": "github-1-1", "marker_plan": "2026-10-16T00:00:00Z"}


def test_issue_status_is_the_issue_open_when_the_run_finished(tmp_path):
    """Lifecycle: #3 closed before the run (an earlier episode), #4 open at the run (or created by it), #5 later."""
    fp = issues.fingerprint("dev", RG)

    def item(number, created, closed):
        return dict(stored(number, fp, "closed" if closed else "open"), created_at=created, closed_at=closed)

    snapshot_file(tmp_path, [item(3, "2026-10-14T01:00:00Z", "2026-10-15T01:00:00Z"),
                             item(4, "2026-10-16T01:10:00Z", "2026-10-16T03:00:00Z"),
                             item(5, "2026-10-17T01:10:00Z", None)])
    loaded, _ = issues.load(str(tmp_path))
    status = lambda finished: issues.issue_status(loaded, "dev", RG, finished)  # noqa: E731
    assert status("2026-10-16T01:00:00Z")["number"] == 4  # created by this run's issues job, after the run
    assert (status("2026-10-16T02:00:00Z")["number"], status("2026-10-16T02:00:00Z")["status"]) == (4, "closed")
    assert status("2026-10-14T00:30:00Z")["number"] == 3
    assert (status("2026-10-17T01:00:00Z")["number"], status("2026-10-17T01:00:00Z")["status"]) == (5, "open")
    assert status("2026-10-16T01:00:00.000000Z")["number"] == 4  # fractional seconds
    assert issues.issue_status(loaded, "prod", RG, "2026-10-16T01:00:00Z")["status"] == "none_found"
    assert issues.issue_status(loaded, "dev", RG, None)["status"] == "none_found"
    assert issues.issue_status(None, "dev", RG, "2026-10-16T01:00:00Z") == {"status": "no_snapshot", "fetched_at": None}


@pytest.mark.parametrize("damage", [
    lambda items: items[0].update(url="https://evil.example/issues/3"),
    lambda items: items[0].update(state="merged"),
    lambda items: items[0].update(closed_at=None),
    lambda items: items[0].update(title="x"),
    lambda items: items[0].update(fingerprint="nope"),
    lambda items: items[0].update(url=f"https://github.com/other/repo/issues/3"),
])
def test_invalid_snapshots_are_ignored(tmp_path, damage):
    items = [stored(3, "a" * 64, "closed")]
    damage(items)
    snapshot_file(tmp_path, items)
    assert issues.load(str(tmp_path)) == (None, "issues_snapshot_invalid")


def test_symlinked_snapshot_is_ignored(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    snapshot_file(other, [])
    data = tmp_path / "data"
    data.mkdir()
    (data / "github_issues.json").symlink_to(other / "github_issues.json")
    assert issues.load(str(data)) == (None, "issues_snapshot_invalid")


def test_api_rows_carry_issue_and_pr_state(tmp_path):
    pytest.importorskip("fastapi")
    import hashlib

    from fastapi.testclient import TestClient

    from dashboard_api.app import create_app

    data = tmp_path / "data"
    shutil.copytree(REAL, data)
    fp = issues.fingerprint("dev", RG)
    snapshot_file(data, [stored(7, fp, "closed")])
    users = tmp_path / "users.json"
    users.write_text(json.dumps({"users": [{"name": "m", "token_sha256": hashlib.sha256(b"t" * 32).hexdigest(),
                                            "roles": ["viewer"]}]}))
    users.chmod(0o600)
    client = TestClient(create_app(data_dir=str(data), users_file=str(users), environ={}, ui_dir=None))
    headers = {"Authorization": "Bearer " + "t" * 32}
    row = client.get("/api/drifts?report_id=github-38105671846-1", headers=headers).json()["drifts"][0]
    assert (row["issue"]["status"], row["issue"]["number"], row["issue"]["state_reason"]) == ("closed", 7, "completed")
    assert row["remediation_pr"]["status"] == "not_enabled"
    summary = client.get("/api/summary", headers=headers).json()
    assert (summary["issues"]["closed"], summary["issues"]["items"][0]["address"]) == (1, RG)
    (data / "github_issues.json").unlink()
    row = client.get("/api/drifts?report_id=github-38105671846-1", headers=headers).json()["drifts"][0]
    assert row["issue"]["status"] == "no_snapshot"
