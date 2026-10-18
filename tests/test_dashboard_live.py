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
import time
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

    def download(self, url: str) -> bytes:
        self.downloads.append(url)
        return self.archives[url]

    def _open(self, url: str, authorized: bool, follow: bool):
        if url.startswith(f"{API}/repos/{REPO}/actions/artifacts?"):
            return contextlib.closing(io.BytesIO(json.dumps({"artifacts": self.artifacts}).encode()))
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
    import urllib.error

    class Failing(FakeGitHub):
        def _open(self, url, authorized, follow):
            raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)
    assert fdd.run_once(Failing([], {}, []), REPO, str(tmp_path), 30) == 1
    out = capsys.readouterr().out.strip().splitlines()
    assert out[-1] == "dashboard_fetch=failed step=artifacts reason=listing_failed detail=http_401"
    assert out[:-1] == ["dashboard_stage=listing"]


def test_issue_step_failure_keeps_artifacts_and_names_the_status(tmp_path, capsys, fake):
    """A token without "Issues: read": the artifacts are written, the issue step reports HTTP 403."""
    import urllib.error

    class NoIssues(type(fake)):
        def _open(self, url, authorized, follow):
            if "/issues?" in url:
                raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
            return super()._open(url, authorized, follow)

    github = NoIssues(fake.artifacts, fake.archives, [])
    assert fdd.run_once(github, REPO, str(tmp_path), 30) == 1
    out = capsys.readouterr().out.strip().splitlines()[-1]
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


# --------------------------------------------------------------------------- Task 13.4: token on stdin, staging


def test_token_stdin_wins_over_the_environment_and_is_validated(tmp_path, monkeypatch, capsys):
    seen = []

    class Recorder:
        def __init__(self, api, token, sleep=None):
            seen.append(token)

    monkeypatch.setattr(fdd.fpr, "GitHub", Recorder)
    monkeypatch.setattr(fdd, "run_once", lambda github, repo, data_dir, days: 0)
    monkeypatch.setenv("GH_TOKEN", "environment-token")
    monkeypatch.setattr(sys, "stdin", io.StringIO(TOKEN + "\n"))
    assert fdd.main(["--token-stdin", "--repository", REPO, "--data-dir", str(tmp_path / "d")]) == 0
    assert seen == [TOKEN]
    for bad in ("", "two words\n", "x" * 2000 + "\n", "tok\x01en\n"):
        monkeypatch.setattr(sys, "stdin", io.StringIO(bad))
        assert fdd.main(["--token-stdin", "--repository", REPO, "--data-dir", str(tmp_path / "d")]) == 2, repr(bad)
    out = capsys.readouterr()
    assert TOKEN not in out.out + out.err


def test_stale_staging_is_removed_and_fresh_staging_kept(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.json").write_text("{}")
    old = time.time() - fdd.STALE_STAGING_SECONDS - 60
    (data / ".fetch-old").mkdir()
    (data / ".fetch-old" / "drift_report.json").write_text("{")
    (data / ".fetch-new").mkdir()
    (data / ".issues-old").write_text("{")
    (data / ".fetch-link").symlink_to(outside)
    (data / "drift-report-1").mkdir()
    for path in (data / ".fetch-old", data / ".fetch-old" / "drift_report.json", data / ".issues-old",
                 data / "drift-report-1"):
        os.utime(path, (old, old))
    os.utime(data / ".fetch-link", (old, old), follow_symlinks=False)
    assert fdd.remove_stale_staging(str(data), time.time()) == 3
    assert sorted(p.name for p in data.iterdir()) == [".fetch-new", "drift-report-1"]
    assert (outside / "keep.json").exists()  # a link is removed, never followed


def test_a_fetch_reports_removed_staging(tmp_path, fake, capsys):
    old = time.time() - fdd.STALE_STAGING_SECONDS - 60
    (tmp_path / ".fetch-old").mkdir()
    os.utime(tmp_path / ".fetch-old", (old, old))
    assert fdd.run_once(fake, REPO, str(tmp_path), 30) == 0
    assert "stale_staging_removed=1" in capsys.readouterr().out


# --------------------------------------------------------------------------- SIGTERM cleanup, hidden manual input


def test_an_interrupted_artifact_write_leaves_no_staging(tmp_path, monkeypatch):
    def interrupted(src, dst):
        raise SystemExit(143)  # what the SIGTERM handler raises
    monkeypatch.setattr(fdd.os, "rename", interrupted)
    with pytest.raises(SystemExit):
        fdd._write_new_dir(str(tmp_path), "drift-report-1", "drift_report.json", b"{}")
    assert list(tmp_path.iterdir()) == []


def test_an_interrupted_issue_snapshot_leaves_no_staging(tmp_path, fake, monkeypatch):
    def interrupted(src, dst):
        raise SystemExit(143)
    monkeypatch.setattr(fdd.os, "replace", interrupted)
    with pytest.raises(SystemExit):
        fdd.fetch_issues(fake, REPO, str(tmp_path), NOW)
    assert list(tmp_path.iterdir()) == []


def test_main_installs_the_sigterm_handler(tmp_path, monkeypatch):
    import signal
    previous = signal.getsignal(signal.SIGTERM)
    try:
        monkeypatch.setattr(fdd, "run_once", lambda github, repo, data_dir, days: 0)
        monkeypatch.setattr(sys, "stdin", io.StringIO(TOKEN + "\n"))
        assert fdd.main(["--token-stdin", "--repository", REPO, "--data-dir", str(tmp_path / "d")]) == 0
        assert signal.getsignal(signal.SIGTERM) is fdd._on_sigterm
        with pytest.raises(SystemExit) as stopped:
            fdd._on_sigterm(signal.SIGTERM, None)
        assert stopped.value.code == 143
    finally:
        signal.signal(signal.SIGTERM, previous)


def test_token_stdin_from_a_terminal_is_read_without_echo(tmp_path, monkeypatch):
    seen, prompts = [], []

    class Recorder:
        def __init__(self, api, token, sleep=None):
            seen.append(token)

    class Terminal(io.StringIO):
        def isatty(self):
            return True

        def readline(self, *args):
            raise AssertionError("a terminal token must not be read with echo")

    monkeypatch.setattr(fdd.fpr, "GitHub", Recorder)
    monkeypatch.setattr(fdd, "run_once", lambda github, repo, data_dir, days: 0)
    monkeypatch.setattr(fdd.getpass, "getpass", lambda prompt: prompts.append(prompt) or TOKEN)
    monkeypatch.setattr(sys, "stdin", Terminal())
    assert fdd.main(["--token-stdin", "--repository", REPO, "--data-dir", str(tmp_path / "d")]) == 0
    assert seen == [TOKEN] and prompts == ["GitHub token (hidden): "]


# ----------------------------------------------------------------------------- Task 13.5: verification and categories

import urllib.error  # noqa: E402


class Scripted(FakeGitHub):
    """Answers each URL with a body, or raises the error (an exception, or an HTTPError with headers)."""

    def __init__(self, plan: dict) -> None:
        super().__init__([], {}, [])
        self.plan, self.seen = plan, []

    def _open(self, url, authorized, follow):
        self.seen.append(url)
        for fragment, outcome in self.plan.items():
            if fragment in url:
                if isinstance(outcome, BaseException):
                    raise outcome
                return contextlib.closing(io.BytesIO(json.dumps(outcome).encode()))
        raise AssertionError(url)


def http_error(url: str, code: int, **headers) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "x", headers, io.BytesIO(b"sentinel-body"))


OKS = {f"/repos/{REPO}/actions/artifacts?": {"artifacts": []}, "/issues?": []}


def verify(plan: dict, capsys) -> tuple[int, str, Scripted]:
    github = Scripted(plan)
    code = fdd.verify_token(github, REPO)
    return code, capsys.readouterr().out.strip(), github


def test_verify_reaches_the_repository_actions_and_issues_with_three_reads(capsys):
    code, out, github = verify({f"/repos/{REPO}?": None, **OKS} if False else {**OKS, f"{API}/repos/{REPO}": {}}, capsys)
    assert (code, out) == (0, "dashboard_verify=ok")
    assert [u.split(f"{REPO}")[1].split("?")[0] for u in github.seen] == ["", "/actions/artifacts", "/issues"]
    assert all(u.startswith(API) for u in github.seen)  # fixed host: the token goes nowhere else


@pytest.mark.parametrize("fails, error, expected", [
    (f"{API}/repos/{REPO}", lambda u: http_error(u, 401), "dashboard_verify=failed reason=invalid_token http=401"),
    (f"{API}/repos/{REPO}", lambda u: http_error(u, 404), "dashboard_verify=failed reason=repository_not_accessible http=404"),
    ("/actions/artifacts?", lambda u: http_error(u, 403),
     "dashboard_verify=failed reason=insufficient_permissions http=403 need=actions"),
    ("/actions/artifacts?", lambda u: http_error(u, 403, **{"X-RateLimit-Remaining": "0"}),
     "dashboard_verify=failed reason=rate_limited"),
    ("/actions/artifacts?", lambda u: http_error(u, 403, **{"Retry-After": "60"}),
     "dashboard_verify=failed reason=rate_limited"),
    ("/issues?", lambda u: http_error(u, 429), "dashboard_verify=failed reason=rate_limited"),
    ("/actions/artifacts?", lambda u: urllib.error.URLError("dns failure for sentinel-host"),
     "dashboard_verify=failed reason=network_error"),
    ("/issues?", lambda u: TimeoutError("timed out"), "dashboard_verify=failed reason=network_error"),
    ("/actions/artifacts?", lambda u: http_error(u, 502), "dashboard_verify=failed reason=api_error http=502"),
])
def test_verify_failures_have_fixed_categories_and_no_details(capsys, fails, error, expected):
    plan = {f"{API}/repos/{REPO}": {}, **OKS}
    plan = {fails: error(f"{API}/repos/{REPO}/x"), **{k: v for k, v in plan.items() if k != fails}}
    code, out, _ = verify(plan, capsys)
    assert (code, out) == (1, expected)
    assert "sentinel" not in out and TOKEN not in out and "http" + "s://" not in out


def test_a_non_json_answer_is_not_a_verified_token(capsys):
    class Garbage(Scripted):
        def _open(self, url, authorized, follow):
            return contextlib.closing(io.BytesIO(b"<html>not json</html>"))
    github = Garbage({})
    assert fdd.verify_token(github, REPO) == 1
    assert capsys.readouterr().out.strip() == "dashboard_verify=failed reason=api_error"


def test_the_fetch_reports_rate_limits_and_network_failures_with_fixed_details(tmp_path, capsys):
    for error, detail in ((http_error(f"{API}/x", 403, **{"X-RateLimit-Remaining": "0"}), "rate_limited"),
                          (http_error(f"{API}/x", 404), "http_404"),
                          (urllib.error.URLError("sentinel"), "network")):
        class Failing(FakeGitHub):
            def _open(self, url, authorized, follow, _e=error):
                raise _e
        assert fdd.run_once(Failing([], {}, []), REPO, str(tmp_path), 30) == 1
        out = capsys.readouterr().out.strip().splitlines()[-1]
        assert out == f"dashboard_fetch=failed step=artifacts reason=listing_failed detail={detail}"


def test_the_fetch_prints_its_stages_before_the_result(tmp_path, capsys, fake):
    assert fdd.run_once(fake, REPO, str(tmp_path), 30) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[:3] == ["dashboard_stage=listing", "dashboard_stage=downloading", "dashboard_stage=issues"]
    assert lines[3].startswith("dashboard_fetch=ok ")


def test_verify_only_needs_no_data_dir_and_reads_the_token_from_stdin(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(fdd, "verify_token", lambda github, repo: calls.append((github.token, repo)) or 0)
    monkeypatch.setattr(sys, "stdin", io.StringIO(TOKEN + "\n"))
    assert fdd.main(["--verify-only", "--token-stdin", "--repository", REPO]) == 0
    assert calls == [(TOKEN, REPO)]
    monkeypatch.setattr(sys, "stdin", io.StringIO(TOKEN + "\n"))
    assert fdd.main(["--token-stdin", "--repository", REPO]) == 2  # a fetch still needs --data-dir
    assert TOKEN not in capsys.readouterr().out


def test_verify_accepts_a_token_without_issues_read_with_a_warning(capsys):
    """Review finding 2: the required access (the repository and its Actions artifacts) works; only the issue
    listing is refused, so reports can still be fetched. Accepted, with a fixed warning."""
    plan = {"/issues?": http_error(f"{API}/repos/{REPO}/issues", 403),  # matched in order: specific URLs first
            f"/repos/{REPO}/actions/artifacts?": {"artifacts": []}, f"{API}/repos/{REPO}": {}}
    code, out, _ = verify(plan, capsys)
    assert (code, out) == (0, "dashboard_verify=ok warning=insufficient_permissions http=403 need=issues")
    plan["/issues?"] = http_error(f"{API}/repos/{REPO}/issues", 401)  # a refused token is still a failure
    code, out, _ = verify(plan, capsys)
    assert (code, out) == (1, "dashboard_verify=failed reason=invalid_token http=401")


# ----------------------------------------------------------------------------- review, low findings 4 and 5


def http_error_body(url: str, code: int, body: bytes, **headers) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "x", headers, io.BytesIO(body))


@pytest.mark.parametrize("error, expected", [
    (lambda u: http_error_body(u, 403, b'{"message": "Resource protected by organization SAML enforcement."}',
                               **{"X-GitHub-SSO": "required; url=https://example.invalid/sso"}),
     "dashboard_verify=failed reason=sso_required http=403"),
    (lambda u: http_error_body(u, 403, b'{"message": "You have exceeded a secondary rate limit. sentinel"}'),
     "dashboard_verify=failed reason=rate_limited"),
    (lambda u: http_error_body(u, 403, b'{"message": "Resource not accessible by personal access token"}'),
     "dashboard_verify=failed reason=insufficient_permissions http=403 need=actions"),
    (lambda u: http_error_body(u, 403, b"<html>not json sentinel</html>"),
     "dashboard_verify=failed reason=insufficient_permissions http=403 need=actions"),
])
def test_forbidden_answers_are_told_apart_without_showing_the_body(capsys, error, expected):
    plan = {"/actions/artifacts?": error(f"{API}/repos/{REPO}/actions/artifacts"), "/issues?": [],
            f"{API}/repos/{REPO}": {}}
    code, out, _ = verify(plan, capsys)
    assert (code, out) == (1, expected)
    assert "sentinel" not in out and "SAML" not in out and "example.invalid" not in out


def test_the_fetch_reports_sso_and_secondary_rate_limits_with_fixed_details(tmp_path, capsys):
    for error, detail in ((http_error_body(f"{API}/x", 403, b"{}", **{"X-GitHub-SSO": "required"}), "sso_required"),
                          (http_error_body(f"{API}/x", 403, b'{"message": "secondary rate limit"}'), "rate_limited")):
        class Failing(FakeGitHub):
            def _open(self, url, authorized, follow, _e=error):
                raise _e
        assert fdd.run_once(Failing([], {}, []), REPO, str(tmp_path), 30) == 1
        assert capsys.readouterr().out.strip().splitlines()[-1] == (
            f"dashboard_fetch=failed step=artifacts reason=listing_failed detail={detail}")


def test_verify_only_turns_off_request_retries(monkeypatch):
    monkeypatch.setattr(fdd.fpr, "RETRIES", 3)  # restored after the test
    seen = {}
    monkeypatch.setattr(fdd, "verify_token", lambda github, repo: seen.update(retries=fdd.fpr.RETRIES) or 0)
    monkeypatch.setattr(sys, "stdin", io.StringIO(TOKEN + "\n"))
    assert fdd.main(["--verify-only", "--token-stdin", "--repository", REPO]) == 0
    assert seen["retries"] == 0
