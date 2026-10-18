"""Tests for "Check GitHub for new runs" (Phase 13 design amendment, Task 13.4).

Run from the repository root:
    pytest tests/test_dashboard_fetch.py

The dashboard API runs a fake fetch script in place of scripts/fetch_dashboard_data.py: it records
its arguments, its environment and the SHA-256 of the token it received on standard input, then
behaves as `behavior.json` next to it says (output line, exit code, sleep, stderr). No network,
no GitHub, no real token: the token is a sentinel that must never appear in a response, a log, a
command line, an environment or a file.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from dashboard_api import cli, github_fetch  # noqa: E402
from dashboard_api.app import create_app  # noqa: E402

pytestmark = pytest.mark.integration  # runs subprocesses

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "tests" / "fixtures" / "dashboard" / "real_9b6"
SENTINEL = "test-fetch-sentinel-not-a-real-token"
TOKENS = {"refresher": "r" * 40, "viewer": "v" * 40}
OK_LINE = "dashboard_fetch=ok at=2026-10-18T06:30:00Z already_present=77 fetched=4 issues=6 issues_open=0 listed=81"

FAKE_SCRIPT = r'''
import hashlib, json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
behavior = json.load(open(os.path.join(here, "behavior.json")))
token = sys.stdin.readline().strip()
record = {"argv": sys.argv[1:], "env": dict(os.environ), "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
          "cwd": os.getcwd(), "pid": os.getpid()}
with open(os.path.join(here, "record-%d.json" % os.getpid()), "w") as fh:
    json.dump(record, fh)
if behavior.get("stderr"):
    sys.stderr.write(behavior["stderr"] + "\n")
import signal
def _term(signum, frame):
    open(os.path.join(here, "terminated-%d" % os.getpid()), "w").close()  # stands for the staging cleanup
    if not behavior.get("ignore_term"):
        sys.exit(143)
signal.signal(signal.SIGTERM, _term)
if "--verify-only" in sys.argv:
    time.sleep(behavior.get("verify_sleep", 0))
    print(behavior.get("verify_stdout", "dashboard_verify=ok"))
    sys.exit(behavior.get("verify_exit", 0))
for stage in behavior.get("stages", []):
    print("dashboard_stage=" + stage, flush=True)
    time.sleep(behavior.get("stage_sleep", 0))
time.sleep(behavior.get("sleep", 0))
print(behavior.get("stdout", ""))
sys.exit(behavior.get("exit", 0))
'''


class Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.text: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.text.append(f"{record.getMessage()} {getattr(record, 'event', '')} "
                         f"{json.dumps(getattr(record, 'fields', {}), default=str)}")


@pytest.fixture
def logs():
    capture = Capture()
    root = logging.getLogger()
    old = root.level
    root.addHandler(capture)
    root.setLevel(logging.DEBUG)
    yield capture
    root.removeHandler(capture)
    root.setLevel(old)


class Env:
    """A data directory, a users file, a fake fetch script and the app around them."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.data = tmp / "data"
        shutil.copytree(REAL, self.data)
        self.fake = tmp / "fake"
        self.fake.mkdir()
        (self.fake / "fetch.py").write_text(FAKE_SCRIPT)
        self.behave(stdout=OK_LINE)
        self.users = tmp / "users.json"
        self.users.write_text(json.dumps({"users": [
            {"name": "refresher", "token_sha256": hashlib.sha256(TOKENS["refresher"].encode()).hexdigest(),
             "roles": ["viewer", "data_refresher"]},
            {"name": "viewer", "token_sha256": hashlib.sha256(TOKENS["viewer"].encode()).hexdigest(),
             "roles": ["viewer"]}]}))
        self.users.chmod(0o600)

    def behave(self, **behavior) -> None:
        (self.fake / "behavior.json").write_text(json.dumps(behavior))

    def records(self) -> list[dict]:
        return [json.loads(p.read_text()) for p in sorted(self.fake.glob("record-*.json"))]

    def fetcher(self, token=SENTINEL, cooldown=0, timeout=30, environ=None, verify_gap=0) -> github_fetch.GitHubFetcher:
        return github_fetch.GitHubFetcher(token=token, data_dir=str(self.data), script=str(self.fake / "fetch.py"),
                                          cooldown_seconds=cooldown, timeout_seconds=timeout,
                                          verify_gap_seconds=verify_gap,
                                          environ=environ if environ is not None else {})

    def client(self, fetcher=None, environ=None) -> TestClient:
        fetcher = fetcher or self.fetcher()
        self._fetcher = fetcher
        return TestClient(create_app(data_dir=str(self.data), users_file=str(self.users), environ=environ or {},
                                     ui_dir=None, fetcher=fetcher))

    def wait(self) -> None:
        self._fetcher.wait(30)


def headers(who: str) -> dict:
    return {"Authorization": f"Bearer {TOKENS[who]}"}


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def test_only_data_refresher_may_start_a_fetch(env):
    client = env.client()
    assert client.post("/api/fetch").status_code == 401
    refused = client.post("/api/fetch", headers=headers("viewer"))
    assert (refused.status_code, refused.json()) == (403, {"error": "fetch_access_denied"})
    status = client.get("/api/fetch/status", headers=headers("viewer")).json()
    assert (status["allowed"], status["available"], status["status"]) == (False, True, "idle")
    assert client.get("/api/fetch/status").status_code == 401
    assert env.records() == []  # nothing refused ever ran the fetch
    assert client.get("/api/fetch/status", headers=headers("refresher")).json()["allowed"] is True


def test_start_runs_the_existing_script_with_the_token_on_stdin_only(env, logs):
    client = env.client(environ={"GITHUB_API_URL": "https://attacker.example", "GH_TOKEN": "server-env-token"})
    started = client.post("/api/fetch?repository=evil/repo&data_dir=/tmp", headers=headers("refresher"),
                          json={"script": "/bin/sh", "token": "x"})
    assert started.status_code == 202, started.text
    assert started.json()["status"] == "running"
    assert started.headers["cache-control"] == "no-store"
    env.wait()
    status = client.get("/api/fetch/status", headers=headers("refresher")).json()
    assert (status["status"], status["code"], status["counts"]["fetched"]) == ("new_artifacts", None, 4)
    assert status["started_at"] and status["finished_at"]
    [record] = env.records()
    assert record["argv"] == ["--token-stdin", "--repository", github_fetch.REPOSITORY,
                              "--data-dir", str(env.data.resolve())]  # nothing from the request reached it
    assert record["token_sha256"] == hashlib.sha256(SENTINEL.encode()).hexdigest()
    assert set(record["env"]) <= {"PATH", "LANG", "PYTHONDONTWRITEBYTECODE", "__CF_USER_TEXT_ENCODING"}
    assert "GITHUB_API_URL" not in record["env"] and "GH_TOKEN" not in record["env"]
    assert SENTINEL not in json.dumps(record["env"]) and SENTINEL not in " ".join(record["argv"])
    texts = [started.text, json.dumps(status), "\n".join(logs.text), repr(env._fetcher)]
    assert not any(SENTINEL in text for text in texts)
    for path in env.data.rglob("*"):
        if path.is_file():
            assert SENTINEL not in path.read_text(errors="ignore"), path
    assert any("dashboard_fetch_started" in line for line in logs.text)
    assert any("dashboard_fetch_finished" in line and "new_artifacts" in line for line in logs.text)


def test_one_fetch_at_a_time_then_cooldown(env):
    env.behave(stdout=OK_LINE.replace("fetched=4", "fetched=0"), sleep=1.5)
    client = env.client(env.fetcher(cooldown=120))
    assert client.post("/api/fetch", headers=headers("refresher")).status_code == 202
    busy = client.post("/api/fetch", headers=headers("refresher"))
    assert (busy.status_code, busy.json()) == (409, {"error": "fetch_in_progress"})
    env.wait()
    assert client.get("/api/fetch/status", headers=headers("refresher")).json()["status"] == "no_new_artifacts"
    cooling = client.post("/api/fetch", headers=headers("refresher"))
    assert (cooling.status_code, cooling.json()) == (429, {"error": "fetch_cooldown"})
    assert 1 <= int(cooling.headers["retry-after"]) <= 120
    assert client.get("/api/fetch/status", headers=headers("viewer")).json()["retry_after_seconds"] >= 1
    assert len(env.records()) == 1


def test_overall_timeout_kills_the_fetch(env):
    env.behave(stdout=OK_LINE, sleep=60)
    client = env.client(env.fetcher(timeout=1))
    started = time.monotonic()
    assert client.post("/api/fetch", headers=headers("refresher")).status_code == 202
    env.wait()
    assert time.monotonic() - started < 15
    status = client.get("/api/fetch/status", headers=headers("refresher")).json()
    assert (status["status"], status["code"]) == ("failed", "timeout")
    [record] = env.records()
    with pytest.raises(ProcessLookupError):
        os.kill(record["pid"], 0)  # the process is gone, not left running


def test_stderr_is_never_returned_or_logged(env, logs):
    env.behave(stdout="", stderr=f"Traceback ... https://api.github.com/repos/x Authorization: Bearer {SENTINEL}", exit=1)
    client = env.client()
    client.post("/api/fetch", headers=headers("refresher"))
    env.wait()
    status = client.get("/api/fetch/status", headers=headers("refresher"))
    assert (status.json()["status"], status.json()["code"]) == ("failed", "unexpected_output")
    assert "Traceback" not in status.text and SENTINEL not in status.text
    assert not any("Traceback" in line or SENTINEL in line for line in logs.text)


def test_unavailable_without_a_token_and_refused_in_github_actions(env):
    client = env.client(env.fetcher(token=None))
    assert client.get("/api/fetch/status", headers=headers("refresher")).json()["available"] is False
    refused = client.post("/api/fetch", headers=headers("refresher"))
    assert (refused.status_code, refused.json()) == (503, {"error": "fetch_unavailable"})
    ci = env.client(env.fetcher(environ={"GITHUB_ACTIONS": "true"}))
    refused = ci.post("/api/fetch", headers=headers("refresher"))
    assert (refused.status_code, refused.json()) == (503, {"error": "local_only"})
    assert env.records() == []


def test_get_endpoints_never_start_a_fetch_or_write(env):
    client = env.client()
    before = {p: p.stat().st_mtime_ns for p in env.data.rglob("*")}
    for path in ("/api/summary", "/api/drifts", "/api/remediations", "/api/unmanaged", "/api/fetch/status",
                 "/api/reports/github-38105671846-1"):
        assert client.get(path, headers=headers("refresher")).status_code == 200, path
    assert client.get("/api/fetch", headers=headers("refresher")).status_code == 405  # POST only
    assert env.records() == []
    assert {p: p.stat().st_mtime_ns for p in env.data.rglob("*")} == before


def test_a_failed_fetch_keeps_the_local_reports_available(env):
    env.behave(stdout="dashboard_fetch=failed step=artifacts reason=listing_failed detail=URLError", exit=1)
    client = env.client()
    client.post("/api/fetch", headers=headers("refresher"))
    env.wait()
    status = client.get("/api/fetch/status", headers=headers("refresher")).json()
    assert (status["status"], status["code"]) == ("failed", "artifacts_listing_failed_urlerror")
    summary = client.get("/api/summary", headers=headers("refresher")).json()
    assert summary["reports_total"] == 3  # GitHub unavailable: the saved reports are still served


@pytest.mark.parametrize("code, stdout, expected", [
    (0, OK_LINE, ("new_artifacts", None, 4)),
    (0, OK_LINE.replace("fetched=4", "fetched=0"), ("no_new_artifacts", None, 0)),
    (0, "dashboard_fetch=ok at=2026-10-18T06:30:00Z already_present=77 listed=77 issues=6 issues_open=0",
     ("no_new_artifacts", None, 0)),
    (1, "dashboard_fetch=partial step=issues reason=listing_failed detail=http_403 already_present=77 fetched=2",
     ("partial", "issues_listing_failed_http_403", 2)),
    (1, "dashboard_fetch=partial step=issues reason=write_failed fetched=1", ("partial", "issues_write_failed", 1)),
    (1, "dashboard_fetch=failed step=artifacts reason=listing_failed detail=HTTPError",
     ("failed", "artifacts_listing_failed_httperror", 0)),
    (1, "dashboard_fetch=failed step=artifacts reason=write_failed", ("failed", "artifacts_write_failed", 0)),
    (2, "", ("failed", "usage", 0)),
    (3, OK_LINE, ("failed", "unexpected_exit", 4)),
    (0, OK_LINE + " ; rm -rf /", ("failed", "unexpected_output", 0)),
    (0, "dashboard_fetch=ok at=2026-10-18T06:30:00Z fetched=4 token=ghp_x", ("failed", "unexpected_output", 0)),
    (0, "dashboard_fetch=ok\nsomething else", ("failed", "unexpected_output", 0)),
])
def test_only_the_fixed_result_line_is_trusted(code, stdout, expected):
    result = github_fetch.parse_result(code, stdout)
    assert (result["status"], result["code"], result["counts"].get("fetched", 0)) == expected


def test_token_descriptor_is_read_once_and_validated():
    def through_pipe(data: bytes):
        read_fd, write_fd = os.pipe()
        os.write(write_fd, data)
        os.close(write_fd)
        token = cli.read_token_fd(read_fd)
        with pytest.raises(OSError):
            os.fstat(read_fd)  # closed after reading
        return token

    assert through_pipe(SENTINEL.encode() + b"\n") == SENTINEL
    for bad in (b"", b"\n", b"two words\n", b"x" * 2000, b"tok\x00en", "tökén".encode()):
        assert through_pipe(bad) is None, bad


def test_cli_refuses_low_descriptors_and_unusable_tokens(capsys):
    assert cli.main(["--github-token-fd", "0"]) == 2
    read_fd, write_fd = os.pipe()
    os.close(write_fd)  # empty
    assert cli.main(["--github-token-fd", str(read_fd)]) == 2
    out = capsys.readouterr()
    assert "no usable GitHub token" in out.err and SENTINEL not in out.err + out.out


def test_the_default_job_runs_the_repository_fetch_script():
    assert Path(github_fetch.DEFAULT_SCRIPT) == ROOT / "scripts" / "fetch_dashboard_data.py"
    assert (github_fetch.COOLDOWN_SECONDS, github_fetch.TIMEOUT_SECONDS) == (120, 600)
    fetcher = github_fetch.GitHubFetcher(token=SENTINEL, data_dir="relative/dir", environ={})
    assert fetcher._command()[:2] == [sys.executable, github_fetch.DEFAULT_SCRIPT]
    assert fetcher._command()[-1] == str(Path("relative/dir").resolve())  # absolute: the job runs elsewhere
    assert SENTINEL not in repr(fetcher) and SENTINEL not in json.dumps(fetcher.status())


# --------------------------------------------------------------------------- robustness (final review, 2026-10-18)


def test_an_unexpected_worker_error_never_leaves_the_job_running(env, logs, monkeypatch):
    fetcher = env.fetcher()
    def boom():
        raise RuntimeError("unexpected")
    monkeypatch.setattr(fetcher, "_run_process", boom)
    client = env.client(fetcher)
    assert client.post("/api/fetch", headers=headers("refresher")).status_code == 202
    env.wait()
    status = client.get("/api/fetch/status", headers=headers("refresher")).json()
    assert (status["status"], status["code"]) == ("failed", "internal_error")
    assert status["finished_at"]
    assert not any("unexpected" in line for line in logs.text)  # the exception text is never logged


def test_dashboard_shutdown_stops_a_running_fetch_with_sigterm(env):
    env.behave(stdout=OK_LINE, sleep=60)
    fetcher = env.fetcher()
    started = time.monotonic()
    with env.client(fetcher) as client:  # leaving the block runs the app's shutdown (lifespan)
        assert client.post("/api/fetch", headers=headers("refresher")).status_code == 202
        for _ in range(100):  # wait until the child process exists
            if env.records():
                break
            time.sleep(0.05)
    assert time.monotonic() - started < 15
    status = fetcher.status()
    assert (status["status"], status["code"]) == ("failed", "shutdown")
    assert (status["available"], status["unavailable_reason"]) == (False, "shutting_down")
    [record] = env.records()
    assert (env.fake / f"terminated-{record['pid']}").exists()  # SIGTERM reached it: it could clean up
    with pytest.raises(ProcessLookupError):
        os.kill(record["pid"], 0)
    with pytest.raises(github_fetch.FetchRefused) as refused:
        fetcher.start()
    assert refused.value.code == "fetch_unavailable"


def test_a_fetch_ignoring_sigterm_is_killed_after_the_grace_period(env):
    env.behave(stdout=OK_LINE, sleep=60, ignore_term=True)
    fetcher = env.fetcher()
    fetcher.start()
    for _ in range(100):
        if env.records():
            break
        time.sleep(0.05)
    started = time.monotonic()
    fetcher.shutdown(grace_seconds=0.5)
    assert time.monotonic() - started < 10
    [record] = env.records()
    with pytest.raises(ProcessLookupError):
        os.kill(record["pid"], 0)
    assert (fetcher.status()["status"], fetcher.status()["code"]) == ("failed", "shutdown")


def test_the_timeout_also_stops_gracefully(env):
    env.behave(stdout=OK_LINE, sleep=60)
    client = env.client(env.fetcher(timeout=1))
    client.post("/api/fetch", headers=headers("refresher"))
    env.wait()
    status = client.get("/api/fetch/status", headers=headers("refresher")).json()
    assert (status["status"], status["code"]) == ("failed", "timeout")
    [record] = env.records()
    assert (env.fake / f"terminated-{record['pid']}").exists()  # SIGTERM first, so the script cleaned up


def test_only_proxy_and_certificate_settings_pass_through(env):
    environ = {"HTTPS_PROXY": "http://proxy.example:3128", "no_proxy": "localhost", "SSL_CERT_FILE": "/etc/ca.pem",
               "HTTP_PROXY": "http://plain.example:80", "ALL_PROXY": "socks5://x", "GITHUB_API_URL": "https://evil",
               "GH_TOKEN": "server-token", "SSL_CERT_DIR": "bad\nvalue", "HOME": "/Users/someone"}
    client = env.client(env.fetcher(environ=environ))
    client.post("/api/fetch", headers=headers("refresher"))
    env.wait()
    [record] = env.records()
    passed = {k: v for k, v in record["env"].items() if k not in ("PATH", "LANG", "PYTHONDONTWRITEBYTECODE",
                                                                    "__CF_USER_TEXT_ENCODING")}
    assert passed == {"HTTPS_PROXY": "http://proxy.example:3128", "no_proxy": "localhost",
                      "SSL_CERT_FILE": "/etc/ca.pem"}


def test_unavailable_reasons_are_fixed_codes(env, tmp_path):
    cases = {
        "not_connected": env.fetcher(token=None),
        "local_only": env.fetcher(environ={"GITHUB_ACTIONS": "true"}),
        "fetch_script_missing": github_fetch.GitHubFetcher(token=SENTINEL, data_dir=str(env.data),
                                                           script=str(tmp_path / "absent.py"), environ={}),
        "no_data_dir": github_fetch.GitHubFetcher(token=SENTINEL, data_dir="", script=str(env.fake / "fetch.py"),
                                                  environ={}),
    }
    for reason, fetcher in cases.items():
        client = env.client(fetcher)
        status = client.get("/api/fetch/status", headers=headers("refresher")).json()
        assert (status["available"], status["unavailable_reason"]) == (False, reason), reason
        assert str(tmp_path) not in json.dumps(status)  # never a path
        refused = client.post("/api/fetch", headers=headers("refresher")).json()["error"]
        assert refused == ("local_only" if reason == "local_only" else "fetch_unavailable"), reason
    ready = env.client().get("/api/fetch/status", headers=headers("refresher")).json()
    assert (ready["available"], ready["unavailable_reason"]) == (True, None)


# --------------------------------------------------------------------------- Task 13.5: connect GitHub in the dashboard

GOOD = "gh-good-sentinel-not-a-real-token"
BAD = "gh-bad-sentinel-not-a-real-token"
JSON = {"Content-Type": "application/json"}


def connect(client, token, who="refresher", **extra):
    return client.post("/api/github/connect", json={"token": token}, headers={**headers(who), **extra})


def token_hashes(env) -> list[str]:
    return [r["token_sha256"] for r in env.records()]


def sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def test_connect_verifies_with_the_script_then_the_fetch_uses_that_token(env, logs):
    client = env.client(env.fetcher(token=None))
    before = client.get("/api/fetch/status", headers=headers("refresher")).json()
    assert (before["available"], before["unavailable_reason"], before["connection"]["connected"]) == (
        False, "not_connected", False)
    assert client.post("/api/fetch", headers=headers("refresher")).status_code == 503  # nothing to fetch with yet
    response = connect(client, GOOD)
    body = response.json()
    assert response.status_code == 200
    assert body["verification"] == {"ok": True, "category": None, "http_status": None, "need": None, "warning": None}
    assert body["connection"]["connected"] and body["connection"]["verified"]
    assert body["connection"]["source"] == "dashboard" and body["available"] is True
    verify = env.records()[0]
    assert verify["argv"][:3] == ["--verify-only", "--token-stdin", "--repository"]
    assert "--data-dir" not in verify["argv"]
    assert verify["token_sha256"] == sha(GOOD)
    assert client.post("/api/fetch", headers=headers("refresher")).status_code == 202
    env.wait()
    assert token_hashes(env)[-1] == sha(GOOD)  # the verified token is the one the fetch received (on stdin)
    # never in a response, a log line, an argument or an environment
    surfaces = [response.text, client.get("/api/fetch/status", headers=headers("refresher")).text, " ".join(logs.text),
                repr(client.app)]
    surfaces += [json.dumps(r["argv"]) + json.dumps(r["env"]) for r in env.records()]
    assert all(GOOD not in surface for surface in surfaces)
    assert GOOD not in repr(env._fetcher)


@pytest.mark.parametrize("code, stdout, expected", [
    (0, "dashboard_verify=ok", (True, None, None, None)),
    (1, "dashboard_verify=failed reason=invalid_token http=401", (False, "invalid_token", 401, None)),
    (1, "dashboard_verify=failed reason=insufficient_permissions http=403 need=issues",
     (False, "insufficient_permissions", 403, "issues")),
    (1, "dashboard_verify=failed reason=insufficient_permissions http=403 need=actions",
     (False, "insufficient_permissions", 403, "actions")),
    (1, "dashboard_verify=failed reason=repository_not_accessible http=404",
     (False, "repository_not_accessible", 404, None)),
    (1, "dashboard_verify=failed reason=rate_limited", (False, "rate_limited", None, None)),
    (1, "dashboard_verify=failed reason=network_error", (False, "network_error", None, None)),
    (1, "dashboard_verify=failed reason=api_error http=502", (False, "api_error", 502, None)),
    (0, "dashboard_verify=ok ; rm -rf /", (False, "unexpected_output", None, None)),
    (1, "dashboard_verify=failed reason=made_up_reason", (False, "unexpected_output", None, None)),
    (1, "dashboard_verify=ok", (False, "unexpected_output", None, None)),  # an ok line with a failing exit is not ok
    (2, "", (False, "unexpected_output", None, None)),
])
def test_every_verification_outcome_maps_to_a_fixed_category(env, code, stdout, expected):
    env.behave(verify_stdout=stdout, verify_exit=code)
    client = env.client(env.fetcher(token=None))
    body = connect(client, BAD).json()
    v = body["verification"]
    assert (v["ok"], v["category"], v["http_status"], v["need"]) == expected
    assert body["connection"]["connected"] is expected[0]  # only an accepted token is kept
    assert BAD not in json.dumps(body)


def test_a_rejected_token_is_discarded_and_the_earlier_one_stays_until_replaced(env):
    client = env.client(env.fetcher(token=None))
    assert connect(client, GOOD).json()["verification"]["ok"]
    env.behave(verify_stdout="dashboard_verify=failed reason=invalid_token http=401", verify_exit=1)
    failed = connect(client, BAD).json()
    assert failed["verification"]["category"] == "invalid_token"
    assert failed["connection"]["connected"] and failed["connection"]["last_attempt"]["category"] == "invalid_token"
    env.behave(stdout=OK_LINE)
    assert client.post("/api/fetch", headers=headers("refresher")).status_code == 202
    env.wait()
    assert token_hashes(env)[-1] == sha(GOOD)  # the rejected token never replaced it
    assert sha(BAD) not in token_hashes(env)[-1:]


def test_a_corrected_token_works_without_restarting(env):
    client = env.client(env.fetcher(token=None))
    env.behave(verify_stdout="dashboard_verify=failed reason=invalid_token http=401", verify_exit=1)
    assert connect(client, BAD).json()["connection"]["connected"] is False
    assert client.post("/api/fetch", headers=headers("refresher")).status_code == 503
    env.behave(stdout=OK_LINE)  # verify defaults to ok again
    assert connect(client, GOOD).json()["verification"]["ok"]
    assert client.post("/api/fetch", headers=headers("refresher")).status_code == 202
    env.wait()
    status = client.get("/api/fetch/status", headers=headers("refresher")).json()
    assert status["status"] == "new_artifacts" and status["connection"]["last_attempt"]["ok"] is True


def test_connect_input_checks_and_authorization(env):
    client = env.client(env.fetcher(token=None))
    assert client.post("/api/github/connect", json={"token": GOOD}).status_code == 401
    assert connect(client, GOOD, who="viewer").status_code == 403
    for bad in ("", " ", "has space", "x" * 1025, "tab\there", "é" * 5):
        r = connect(client, bad)
        assert r.status_code == 422 and r.json() == {"error": "invalid_token_format"}, bad
    for body in ({}, {"token": GOOD, "extra": 1}, {"token": 5}, []):
        r = client.post("/api/github/connect", json=body, headers=headers("refresher"))
        assert r.status_code == 422 and r.json() == {"error": "invalid_request"}
        assert GOOD not in r.text
    r = client.post("/api/github/connect", content=json.dumps({"token": GOOD}),
                    headers={**headers("refresher"), "Content-Type": "text/plain"})
    assert r.status_code == 415
    assert not env.records()  # nothing reached the verifier


def test_state_changing_requests_refuse_a_cross_origin_browser(env):
    client = env.client(env.fetcher(token=None))
    for origin in ("http://evil.example", "null", "http://testserver.evil.example"):
        for path, kwargs in (("/api/github/connect", {"json": {"token": GOOD}}), ("/api/github/disconnect", {}),
                             ("/api/fetch", {})):
            r = client.post(path, headers={**headers("refresher"), "Origin": origin}, **kwargs)
            assert (r.status_code, r.json()) == (403, {"error": "origin_not_allowed"}), (origin, path)
    assert not env.records()
    ok = connect(client, GOOD, Origin="http://testserver")  # same origin as the Host header
    assert ok.status_code == 200 and ok.json()["verification"]["ok"]


def test_verification_is_single_flight_and_rate_limited(env):
    env.behave(verify_sleep=1.5)
    client = env.client(env.fetcher(token=None, verify_gap=30))
    import threading
    first = {}
    thread = threading.Thread(target=lambda: first.update(r=connect(client, GOOD)))
    thread.start()
    time.sleep(0.5)
    second = connect(client, BAD)
    assert (second.status_code, second.json()) == (409, {"error": "verification_in_progress"})
    thread.join(10)
    assert first["r"].json()["verification"]["ok"]
    third = connect(client, BAD)  # inside the minimum gap
    assert third.status_code == 429 and third.json() == {"error": "verify_too_soon"}
    assert int(third.headers["Retry-After"]) >= 1


def test_connect_and_disconnect_are_refused_while_a_fetch_runs(env):
    env.behave(stdout=OK_LINE, sleep=2)
    client = env.client(env.fetcher())
    assert client.post("/api/fetch", headers=headers("refresher")).status_code == 202
    assert connect(client, GOOD).json() == {"error": "fetch_in_progress"}
    assert client.post("/api/github/disconnect", headers=headers("refresher")).json() == {"error": "fetch_in_progress"}
    env.wait()
    assert client.post("/api/github/disconnect", headers=headers("refresher")).status_code == 200


def test_disconnect_forgets_the_token(env):
    client = env.client(env.fetcher())
    body = client.post("/api/github/disconnect", headers=headers("refresher")).json()
    assert body["connection"]["connected"] is False and body["unavailable_reason"] == "not_connected"
    assert client.post("/api/fetch", headers=headers("refresher")).status_code == 503
    assert client.post("/api/github/disconnect", headers=headers("viewer")).status_code == 403


def test_an_unexpected_verification_error_never_leaks_the_token(env, logs, monkeypatch):
    fetcher = env.fetcher(token=None)

    def boom(self, token):
        raise RuntimeError(f"cannot reach GitHub with {token}")

    monkeypatch.setattr(github_fetch.GitHubFetcher, "_run_verify", boom)
    client = env.client(fetcher)
    r = connect(client, GOOD)
    assert r.json()["verification"]["category"] == "internal_error"
    assert GOOD not in r.text + " ".join(logs.text)


def test_stages_are_reported_while_the_fetch_runs(env):
    env.behave(stdout=OK_LINE, stages=["listing", "downloading", "issues"], stage_sleep=0.8)
    client = env.client()
    started = client.post("/api/fetch", headers=headers("refresher")).json()
    assert started["stage"] == "connecting" and started["status"] == "running"
    seen = set()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        status = client.get("/api/fetch/status", headers=headers("refresher")).json()
        seen.add(status["stage"])
        if status["status"] != "running":
            break
        assert isinstance(status["elapsed_seconds"], int)
        time.sleep(0.2)
    assert {"listing", "downloading", "issues"} <= seen
    assert status["status"] == "new_artifacts" and status["counts"]["fetched"] == 4
    assert status["elapsed_seconds"] >= 2 and status["finished_at"]


@pytest.mark.parametrize("line, category, http, need", [
    ("dashboard_fetch=failed step=artifacts reason=listing_failed detail=http_401", "invalid_token", 401, "actions"),
    ("dashboard_fetch=failed step=artifacts reason=listing_failed detail=http_403", "insufficient_permissions", 403,
     "actions"),
    ("dashboard_fetch=failed step=artifacts reason=listing_failed detail=http_404", "repository_not_accessible", 404,
     "actions"),
    ("dashboard_fetch=failed step=artifacts reason=listing_failed detail=rate_limited", "rate_limited", None, "actions"),
    ("dashboard_fetch=failed step=artifacts reason=listing_failed detail=network", "network_error", None, "actions"),
    ("dashboard_fetch=failed step=artifacts reason=listing_failed detail=http_502", "artifacts_listing_failed", 502,
     "actions"),
    ("dashboard_fetch=failed step=artifacts reason=write_failed", "write_failed", None, "actions"),
])
def test_a_failed_fetch_keeps_its_category_and_http_status(env, line, category, http, need):
    env.behave(stdout=line, exit=1)
    client = env.client()
    client.post("/api/fetch", headers=headers("refresher"))
    env.wait()
    status = client.get("/api/fetch/status", headers=headers("refresher")).json()
    assert (status["status"], status["category"], status["http_status"], status["need"]) == ("failed", category, http, need)
    assert client.get("/api/summary", headers=headers("refresher")).json()["reports_total"] == 3  # reports untouched


def test_a_token_github_refuses_is_flagged_and_a_replacement_clears_it(env):
    env.behave(stdout="dashboard_fetch=failed step=artifacts reason=listing_failed detail=http_401", exit=1)
    client = env.client()
    client.post("/api/fetch", headers=headers("refresher"))
    env.wait()
    c = client.get("/api/fetch/status", headers=headers("refresher")).json()["connection"]
    assert c["connected"] and not c["verified"] and c["last_error"]["category"] == "invalid_token"
    env.behave(stdout=OK_LINE)
    assert connect(client, GOOD).json()["connection"]["last_error"] is None
    client.post("/api/fetch", headers=headers("refresher"))
    env.wait()
    status = client.get("/api/fetch/status", headers=headers("refresher")).json()
    assert status["status"] == "new_artifacts" and status["category"] is None
    assert status["connection"]["verified"] is True


def test_an_issue_step_permission_failure_is_a_partial_result_naming_the_permission(env):
    env.behave(stdout="dashboard_fetch=partial step=issues reason=listing_failed detail=http_403 fetched=2", exit=1)
    client = env.client()
    client.post("/api/fetch", headers=headers("refresher"))
    env.wait()
    status = client.get("/api/fetch/status", headers=headers("refresher")).json()
    assert (status["status"], status["category"], status["http_status"], status["need"]) == (
        "partial", "insufficient_permissions", 403, "issues")
    assert status["counts"]["fetched"] == 2


def test_the_token_preloaded_at_startup_is_marked_unverified(env):
    client = env.client(env.fetcher(token=SENTINEL))
    c = client.get("/api/fetch/status", headers=headers("refresher")).json()["connection"]
    assert (c["connected"], c["source"], c["verified"]) == (True, "startup", False)
    assert SENTINEL not in json.dumps(c)


def test_a_slow_verification_that_times_out_is_a_network_error(env):
    env.behave(verify_sleep=30)
    fetcher = github_fetch.GitHubFetcher(token=None, data_dir=str(env.data), script=str(env.fake / "fetch.py"),
                                         verify_timeout_seconds=1, verify_gap_seconds=0, environ={})
    client = env.client(fetcher)
    started = time.monotonic()
    v = connect(client, GOOD).json()["verification"]
    assert v["category"] == "network_error" and time.monotonic() - started < 15


# --------------------------------------------------------------------------- real script, loopback fake GitHub


class FakeGitHubServer:
    """A loopback HTTP server standing in for api.github.com (the script is pointed at it with
    GITHUB_API_URL, as in its own tests): answers by path with a scripted status and headers and records
    the Authorization header of every request. No real network, no real token."""

    def __init__(self, routes: dict[str, tuple[int, dict, object]]) -> None:
        import http.server
        import threading
        self.routes, self.auth = routes, []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                outer.auth.append(self.headers.get("Authorization"))
                key = max((k for k in outer.routes if self.path.startswith(k)), key=len, default=None)
                status, hdrs, body = outer.routes.get(key, (404, {}, {"message": "Not Found"}))
                payload = json.dumps(body).encode()
                self.send_response(status)
                for name, value in hdrs.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):  # silent
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def real_fetcher(env, server, **kwargs) -> github_fetch.GitHubFetcher:
    """The real script, with the server's API URL passed the way the script reads it (its environment)."""
    fetcher = github_fetch.GitHubFetcher(token=None, data_dir=str(env.data), verify_gap_seconds=0, environ={},
                                         cooldown_seconds=0, **kwargs)
    fetcher._environment = lambda: {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1",
                                    "GITHUB_API_URL": server.url}
    return fetcher


REPO_PATH = f"/repos/{github_fetch.REPOSITORY}"


@pytest.mark.parametrize("routes, expected", [
    ({REPO_PATH: (200, {}, {}), REPO_PATH + "/actions/artifacts": (200, {}, {"artifacts": []}),
      REPO_PATH + "/issues": (200, {}, [])}, (True, None, None, None)),
    ({REPO_PATH: (401, {}, {"message": "Bad credentials"})}, (False, "invalid_token", 401, None)),
    ({REPO_PATH: (404, {}, {"message": "Not Found"})}, (False, "repository_not_accessible", 404, None)),
    ({REPO_PATH: (200, {}, {}), REPO_PATH + "/actions/artifacts": (403, {}, {"message": "Resource not accessible"})},
     (False, "insufficient_permissions", 403, "actions")),
    ({REPO_PATH: (200, {}, {}), REPO_PATH + "/actions/artifacts": (200, {}, {"artifacts": []}),
      REPO_PATH + "/issues": (403, {}, {"message": "Resource not accessible"})},
     (True, None, None, None)),  # accepted with a warning (review finding 2), see the test below
    ({REPO_PATH: (403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1"}, {"message": "API rate limit exceeded"})},
     (False, "rate_limited", None, None)),
    ({REPO_PATH: (200, {}, {}), REPO_PATH + "/actions/artifacts": (429, {"Retry-After": "60"}, {})},
     (False, "rate_limited", None, None)),
])
def test_real_verification_against_a_loopback_fake_github(env, routes, expected):
    server = FakeGitHubServer(routes)
    try:
        client = env.client(real_fetcher(env, server))
        r = connect(client, GOOD)
        v = r.json()["verification"]
        assert (v["ok"], v["category"], v["http_status"], v["need"]) == expected
        assert set(server.auth) == {f"Bearer {GOOD}"}  # sent to the (fake) API host only, as a bearer token
        assert GOOD not in r.text and "Bad credentials" not in r.text and "Resource not accessible" not in r.text
        assert r.json()["connection"]["connected"] is expected[0]
        issues_only = routes.get(REPO_PATH + "/issues", (200,))[0] == 403
        assert v["warning"] == (ISSUES_WARNING if issues_only else None)
    finally:
        server.close()


def test_real_verification_with_the_api_unreachable_is_a_network_error(env):
    server = FakeGitHubServer({})
    url = server.url
    server.close()  # nothing listens any more
    fetcher = real_fetcher(env, type("S", (), {"url": url})())
    v = connect(env.client(fetcher), GOOD).json()["verification"]
    assert (v["ok"], v["category"]) == (False, "network_error")


def test_real_fetch_with_a_revoked_token_fails_with_a_clear_category_and_keeps_the_reports(env):
    server = FakeGitHubServer({REPO_PATH: (401, {}, {"message": "Bad credentials"})})
    try:
        fetcher = real_fetcher(env, server)
        fetcher._token = GOOD
        client = env.client(fetcher)
        before = sorted(p.name for p in env.data.iterdir())
        assert client.post("/api/fetch", headers=headers("refresher")).status_code == 202
        env.wait()
        status = client.get("/api/fetch/status", headers=headers("refresher")).json()
        assert (status["status"], status["category"], status["http_status"]) == ("failed", "invalid_token", 401)
        assert status["code"] == "artifacts_listing_failed_http_401"
        assert sorted(p.name for p in env.data.iterdir()) == before  # no download, no staging left, nothing removed
        assert client.get("/api/summary", headers=headers("refresher")).json()["reports_total"] == 3
    finally:
        server.close()


# --------------------------------------------------------------------------- review finding 2: Issues-only refusals

ISSUES_WARNING = {"category": "insufficient_permissions", "http_status": 403, "need": "issues"}


def test_a_token_without_issues_read_connects_verified_with_a_warning(env):
    env.behave(verify_stdout="dashboard_verify=ok warning=insufficient_permissions http=403 need=issues")
    client = env.client(env.fetcher(token=None))
    body = connect(client, GOOD).json()
    assert body["verification"]["ok"] is True and body["verification"]["warning"] == ISSUES_WARNING
    c = body["connection"]
    assert (c["connected"], c["verified"], c["last_error"], c["warning"]) == (True, True, None, ISSUES_WARNING)
    assert body["available"] is True


def test_actions_ok_but_issues_403_keeps_the_token_verified_with_a_warning(env):
    env.behave(stdout="dashboard_fetch=partial step=issues reason=listing_failed detail=http_403 fetched=2", exit=1)
    client = env.client(env.fetcher(token=None))
    assert connect(client, GOOD).json()["connection"]["verified"] is True
    client.post("/api/fetch", headers=headers("refresher"))
    env.wait()
    status = client.get("/api/fetch/status", headers=headers("refresher")).json()
    assert status["status"] == "partial" and status["counts"]["fetched"] == 2
    c = status["connection"]
    assert (c["verified"], c["last_error"], c["warning"]) == (True, None, ISSUES_WARNING)
    env.behave(stdout=OK_LINE)  # a later full success clears the warning
    client.post("/api/fetch", headers=headers("refresher"))
    env.wait()
    c = client.get("/api/fetch/status", headers=headers("refresher")).json()["connection"]
    assert (c["verified"], c["last_error"], c["warning"]) == (True, None, None)


@pytest.mark.parametrize("line, category, need", [
    ("dashboard_fetch=failed step=artifacts reason=listing_failed detail=http_401", "invalid_token", "actions"),
    ("dashboard_fetch=failed step=artifacts reason=listing_failed detail=http_403", "insufficient_permissions", "actions"),
    ("dashboard_fetch=failed step=artifacts reason=listing_failed detail=http_404", "repository_not_accessible", "actions"),
    ("dashboard_fetch=failed step=artifacts reason=listing_failed detail=sso_required", "sso_required", "actions"),
    ("dashboard_fetch=partial step=issues reason=listing_failed detail=http_401 fetched=1", "invalid_token", "issues"),
])
def test_a_refused_token_or_required_access_marks_it_unverified_with_its_own_category(env, line, category, need):
    env.behave(stdout=line, exit=1)
    client = env.client(env.fetcher(token=None))
    connect(client, GOOD)
    client.post("/api/fetch", headers=headers("refresher"))
    env.wait()
    c = client.get("/api/fetch/status", headers=headers("refresher")).json()["connection"]
    assert c["connected"] is True and c["verified"] is False
    assert (c["last_error"]["category"], c["last_error"]["need"]) == (category, need)


@pytest.mark.parametrize("line", [
    "dashboard_fetch=partial step=issues reason=listing_failed detail=rate_limited fetched=1",
    "dashboard_fetch=partial step=issues reason=listing_failed detail=network fetched=1",
    "dashboard_fetch=failed step=artifacts reason=listing_failed detail=network",
    "dashboard_fetch=failed step=artifacts reason=write_failed",
])
def test_problems_that_say_nothing_about_the_token_leave_its_state_alone(env, line):
    env.behave(stdout=line, exit=1)
    client = env.client(env.fetcher(token=None))
    connect(client, GOOD)
    client.post("/api/fetch", headers=headers("refresher"))
    env.wait()
    c = client.get("/api/fetch/status", headers=headers("refresher")).json()["connection"]
    assert (c["verified"], c["last_error"], c["warning"]) == (True, None, None)


# --------------------------------------------------------------------------- review finding 3: GitHub turned off


def test_github_turned_off_refuses_connect_and_fetch_and_ignores_a_startup_token(env):
    fetcher = github_fetch.GitHubFetcher(token=SENTINEL, data_dir=str(env.data), script=str(env.fake / "fetch.py"),
                                         environ={}, disabled=True)
    client = env.client(fetcher)
    status = client.get("/api/fetch/status", headers=headers("refresher")).json()
    assert (status["available"], status["unavailable_reason"], status["connection"]["connected"]) == (
        False, "disabled", False)
    assert connect(client, GOOD).json() == {"error": "disabled"}
    assert client.post("/api/fetch", headers=headers("refresher")).json() == {"error": "disabled"}
    assert not env.records()  # nothing ran
    assert client.get("/api/summary", headers=headers("refresher")).status_code == 200  # local data unaffected


def test_cli_no_github_flag(monkeypatch, capsys):
    import os as _os
    r, w = _os.pipe()
    _os.write(w, b"x\n")
    _os.close(w)
    assert cli.main(["--no-github", "--github-token-fd", str(r)]) == 2
    assert "cannot be combined" in capsys.readouterr().err
    seen = {}
    import types
    fake_uvicorn = types.SimpleNamespace(run=lambda app, **kw: seen.update(app=app))
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.setattr("dashboard_api.app.create_app_from_env",
                        lambda github_token=None, github_enabled=True: seen.update(enabled=github_enabled) or "app")
    assert cli.main(["--no-github"]) == 0 and seen["enabled"] is False
    assert cli.main([]) == 0 and seen["enabled"] is True


# --------------------------------------------------------------------------- review, low findings 4-6 (real script)


def test_real_verification_sends_one_request_on_a_429_and_recognises_sso(env):
    server = FakeGitHubServer({REPO_PATH: (200, {}, {}),
                               REPO_PATH + "/actions/artifacts": (429, {"Retry-After": "60"}, {})})
    try:
        client = env.client(real_fetcher(env, server))
        v = connect(client, GOOD).json()["verification"]
        assert v["category"] == "rate_limited"
        assert len(server.auth) == 2  # the repository, then the artifact listing once: no burst of retries
    finally:
        server.close()
    server = FakeGitHubServer({REPO_PATH: (403, {"X-GitHub-SSO": "required; url=https://example.invalid/sso"},
                                           {"message": "Resource protected by organization SAML enforcement."})})
    try:
        r = connect(env.client(real_fetcher(env, server)), GOOD)
        assert (r.json()["verification"]["category"], r.json()["verification"]["http_status"]) == ("sso_required", 403)
        assert "SAML" not in r.text and "example.invalid" not in r.text
    finally:
        server.close()


def test_the_connect_body_is_bounded_before_it_is_read(env):
    client = env.client(env.fetcher(token=None))
    big = client.post("/api/github/connect", content=json.dumps({"token": "x" * 5000}),
                      headers={**headers("refresher"), **JSON})
    assert (big.status_code, big.json()) == (413, {"error": "request_too_large"})
    unauthenticated = client.post("/api/github/connect", content=b"{" + b" " * 10_000 + b"}", headers=JSON)
    assert unauthenticated.status_code == 413  # refused before authentication, before parsing
    chunked = client.post("/api/github/connect", content=iter([b'{"token": "', GOOD.encode(), b'"}']),
                          headers={**headers("refresher"), **JSON})
    assert (chunked.status_code, chunked.json()) == (411, {"error": "length_required"})
    assert not env.records()
    assert connect(client, GOOD).status_code == 200  # a normal request still works
