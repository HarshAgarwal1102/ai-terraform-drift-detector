"""Tests for the one-command dashboard launcher (scripts/run_dashboard.sh, Phase 13).

Run from the repository root:
    pytest tests/test_run_dashboard.py

The launcher runs with --setup-only against the test interpreter's own environment
(DASHBOARD_VENV) and a temporary DASHBOARD_LOCAL_DIR, so nothing is installed, no data is
fetched, no server starts and the real .artifacts/ is never touched.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "scripts" / "run_dashboard.sh"
FINDER = ROOT / "scripts" / "Start Dashboard.command"
TOKEN_LINE = re.compile(r"^   ([A-Za-z0-9_-]{43})$", re.M)

pytestmark = pytest.mark.integration


def launch(tmp_path: Path, *args: str, stdin: str | None = None, venv: str | None = None,
           extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(tmp_path),
           "DASHBOARD_VENV": venv or sys.prefix, "DASHBOARD_LOCAL_DIR": str(tmp_path / "local"),
           "DASHBOARD_DATA_DIR": str(ROOT / "tests" / "fixtures" / "dashboard" / "real_9b6"), **(extra_env or {})}
    return subprocess.run(["bash", str(LAUNCHER), *args], cwd=ROOT, env=env, capture_output=True, text=True,
                          timeout=120, input=stdin if stdin is not None else "")


@pytest.fixture(autouse=True)
def needs_dashboard_extra():
    pytest.importorskip("fastapi")
    pytest.importorskip("uvicorn")
    if not (Path(sys.prefix) / "bin" / "python").exists():
        pytest.skip("the test interpreter has no <prefix>/bin/python")


def test_launchers_are_executable_and_parse():
    for path in (LAUNCHER, FINDER):
        assert path.stat().st_mode & stat.S_IXUSR, path
        assert subprocess.run(["bash", "-n", str(path)], capture_output=True).returncode == 0, path
    assert 'exec scripts/run_dashboard.sh "$@"' in FINDER.read_text()


def test_first_run_creates_a_digest_only_users_file_and_shows_the_token_once(tmp_path):
    first = launch(tmp_path, "--setup-only")
    assert first.returncode == 0, first.stderr
    tokens = TOKEN_LINE.findall(first.stdout)
    assert len(tokens) == 1
    users_file = tmp_path / "local" / "users.json"
    assert stat.S_IMODE(users_file.stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "local").stat().st_mode) == 0o700
    text = users_file.read_text()
    assert tokens[0] not in text  # only the SHA-256 digest is stored
    user = json.loads(text)["users"][0]
    assert (user["name"], user["roles"], len(user["token_sha256"])) == ("local-admin", ["viewer", "caller_reader", "data_refresher"], 64)
    from dashboard_api import auth
    assert auth.authenticate(f"Bearer {tokens[0]}", auth.load_users(str(users_file))).name == "local-admin"
    assert "==> Ready:" in first.stdout and "127.0.0.1:8000" in first.stdout

    second = launch(tmp_path, "--setup-only")
    assert second.returncode == 0 and not TOKEN_LINE.search(second.stdout)  # never shown again
    assert users_file.read_text() == text

    rotated = launch(tmp_path, "--setup-only", "--new-token")
    new = TOKEN_LINE.findall(rotated.stdout)
    assert len(new) == 1 and new[0] != tokens[0]
    assert auth.authenticate(f"Bearer {tokens[0]}", auth.load_users(str(users_file))) is None  # old token revoked


def test_caller_lookup_follows_the_terraform_json_option(tmp_path):
    assert "Caller lookup off" in launch(tmp_path, "--setup-only").stdout
    state = tmp_path / "state.json"
    state.write_text("{}")
    assert "Caller lookup enabled" in launch(tmp_path, "--setup-only", "--terraform-json", str(state)).stdout
    missing = launch(tmp_path, "--setup-only", "--terraform-json", str(tmp_path / "absent.json"))
    assert missing.returncode == 1 and "terraform JSON not found" in missing.stderr


@pytest.mark.parametrize("args, message", [(["--bogus"], "unknown option"), (["--port", "x"], "--port needs a number")])
def test_bad_options(tmp_path, args, message):
    result = launch(tmp_path, *args)
    assert result.returncode == 1 and message in result.stderr


def test_help(tmp_path):
    result = launch(tmp_path, "--help")
    assert result.returncode == 0 and "start the drift dashboard with one command" in result.stdout


# --------------------------------------------------------------------------- Task 13.4: --enable-github-fetch

GITHUB_TOKEN = "test-launcher-sentinel-not-a-real-token"

FAKE_DASHBOARD_API = """#!/bin/bash
# Stand-in for dashboard-api: records how the GitHub token arrived, then exits.
exec "{python}" - "$@" <<'PY'
import hashlib, json, os, sys
token = os.read(3, 4096).decode().strip() if "--github-token-fd" in sys.argv else ""
record = {{"argv": sys.argv[1:], "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
          "env_has_token": any("{marker}" in v for v in os.environ.values()),
          "env_names": sorted(k for k in os.environ if "TOKEN" in k)}}
json.dump(record, open("{record}", "w"))
PY
"""


def fake_venv(tmp_path: Path) -> tuple[Path, Path]:
    """A venv whose python is the test interpreter and whose dashboard-api only records its inputs."""
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    python = venv / "bin" / "python"
    python.write_text(f'#!/bin/bash\nexec "{Path(sys.prefix) / "bin" / "python"}" "$@"\n')
    python.chmod(0o755)
    record = tmp_path / "record.json"
    api = venv / "bin" / "dashboard-api"
    api.write_text(FAKE_DASHBOARD_API.format(python=Path(sys.prefix) / "bin" / "python", marker=GITHUB_TOKEN[4:20],
                                             record=record))
    api.chmod(0o755)
    return venv, record


def test_enable_github_fetch_hands_the_token_over_a_pipe_only(tmp_path):
    venv, record = fake_venv(tmp_path)
    result = launch(tmp_path, "--enable-github-fetch", "--no-browser", "--port", "8799", stdin=GITHUB_TOKEN + "\n",
                    venv=str(venv), extra_env={"GH_TOKEN": "inherited-" + GITHUB_TOKEN, "GITHUB_TOKEN": "x"})
    assert result.returncode == 0, result.stderr
    assert "Check GitHub for new runs: enabled" in result.stdout
    assert "deprecated" in result.stderr  # the dashboard now connects GitHub itself (Task 13.5)
    seen = json.loads(record.read_text())
    assert seen["argv"] == ["--port", "8799", "--github-token-fd", "3"]  # no token in the arguments
    assert seen["token_sha256"] == hashlib.sha256(GITHUB_TOKEN.encode()).hexdigest()  # it arrived on fd 3
    assert seen["env_has_token"] is False and seen["env_names"] == []  # not in the server's environment
    assert GITHUB_TOKEN not in result.stdout + result.stderr
    for path in (tmp_path / "local").rglob("*"):
        assert GITHUB_TOKEN not in path.read_text(errors="ignore"), path


def test_without_the_flag_the_server_gets_no_token(tmp_path):
    venv, record = fake_venv(tmp_path)
    result = launch(tmp_path, "--no-browser", "--port", "8798", venv=str(venv))
    assert result.returncode == 0, result.stderr
    assert json.loads(record.read_text())["argv"] == ["--port", "8798"]
    assert "Check GitHub" not in result.stdout


def test_enable_github_fetch_gives_local_admin_the_role(tmp_path):
    first = launch(tmp_path, "--setup-only")
    token = TOKEN_LINE.findall(first.stdout)[0]
    users_file = tmp_path / "local" / "users.json"
    doc = json.loads(users_file.read_text())
    doc["users"][0]["roles"] = ["viewer", "caller_reader"]  # a users file from before Task 13.4
    users_file.write_text(json.dumps(doc))
    users_file.chmod(0o600)
    result = launch(tmp_path, "--setup-only", "--enable-github-fetch", stdin=GITHUB_TOKEN + "\n")
    assert result.returncode == 0, result.stderr
    assert "local-admin now has the data_refresher role" in result.stdout
    assert "--github-token-fd 3" in result.stdout and "Check GitHub enabled" in result.stdout
    user = json.loads(users_file.read_text())["users"][0]
    assert user["roles"] == ["viewer", "caller_reader", "data_refresher"]
    assert stat.S_IMODE(users_file.stat().st_mode) == 0o600
    from dashboard_api import auth
    assert auth.authenticate(f"Bearer {token}", auth.load_users(str(users_file))).name == "local-admin"  # same token
    assert GITHUB_TOKEN not in result.stdout + result.stderr + users_file.read_text()


def test_enable_github_fetch_needs_a_token(tmp_path):
    result = launch(tmp_path, "--setup-only", "--enable-github-fetch", stdin="\n")
    assert result.returncode == 1 and "no token entered" in result.stderr


# --------------------------------------------------------------------------- Task 13.5: no flag needed


def test_plain_startup_needs_no_flag_to_connect_github_in_the_dashboard(tmp_path):
    first = launch(tmp_path, "--setup-only")
    token = TOKEN_LINE.findall(first.stdout)[0]
    users_file = tmp_path / "local" / "users.json"
    doc = json.loads(users_file.read_text())
    doc["users"][0]["roles"] = ["viewer", "caller_reader"]  # a users file from before Task 13.4
    users_file.write_text(json.dumps(doc))
    users_file.chmod(0o600)
    result = launch(tmp_path, "--setup-only")  # no flag, no stdin: nothing is asked
    assert result.returncode == 0, result.stderr
    assert "local-admin now has the data_refresher role" in result.stdout
    assert "deprecated" not in result.stderr and "GitHub token" not in result.stdout
    assert json.loads(users_file.read_text())["users"][0]["roles"] == ["viewer", "caller_reader", "data_refresher"]
    from dashboard_api import auth
    assert auth.authenticate(f"Bearer {token}", auth.load_users(str(users_file))).name == "local-admin"


def test_plain_startup_starts_the_server_without_any_github_token(tmp_path):
    venv, record = fake_venv(tmp_path)
    result = launch(tmp_path, "--no-browser", "--port", "8797", venv=str(venv),
                    extra_env={"GH_TOKEN": "inherited-" + GITHUB_TOKEN, "GITHUB_TOKEN": "x"})
    assert result.returncode == 0, result.stderr
    seen = json.loads(record.read_text())
    assert seen["argv"] == ["--port", "8797"]  # the token is entered in the dashboard, never at startup
    assert seen["env_names"] == []  # GH_TOKEN / GITHUB_TOKEN of the caller are not inherited


# --------------------------------------------------------------------------- review finding 3: users.json migration


def broken_users_file(tmp_path: Path, content: bytes | None) -> Path:
    local = tmp_path / "local"
    local.mkdir(mode=0o700, exist_ok=True)
    users_file = local / "users.json"
    if content is None:
        users_file.mkdir()  # something that is not a regular file is in the way
    else:
        users_file.write_bytes(content)
        users_file.chmod(0o600)
    return users_file


@pytest.mark.parametrize("content, warning", [
    (b'{"users": [ {"name": "local-admin", ', "not valid JSON"),
    (b"\xff\xfe not utf-8", "not valid JSON"),
    (b'{"users": "local-admin"}', "does not have the expected shape"),
    (b'[1, 2, 3]', "does not have the expected shape"),
    (b'{"users": [{"name": "local-admin", "roles": "viewer"}]}', "does not have the expected shape"),
    (None, "is not a regular file"),
])
def test_an_unusable_users_file_is_left_untouched_and_never_stops_the_launcher(tmp_path, content, warning):
    users_file = broken_users_file(tmp_path, content)
    before = None if content is None else users_file.read_bytes()
    result = launch(tmp_path, "--setup-only")
    assert result.returncode == 0, result.stderr
    assert warning in result.stderr
    assert "Traceback" not in result.stdout + result.stderr
    assert "==> Ready:" in result.stdout
    assert not TOKEN_LINE.findall(result.stdout)  # no new sign-in token: the configuration is not regenerated
    if content is None:
        assert users_file.is_dir() and not any(users_file.iterdir())
    else:
        assert users_file.read_bytes() == before  # not rewritten, not "repaired"
    assert not (users_file.parent / "users.json.tmp").exists()


def test_an_unusable_users_file_still_refuses_every_sign_in(tmp_path):
    """The launcher warning does not weaken authentication: the server fails closed (503) on the same file."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from dashboard_api.app import create_app
    users_file = broken_users_file(tmp_path, b'{"users": [ {"name": "local-admin", ')
    client = TestClient(create_app(data_dir=str(ROOT / "tests" / "fixtures" / "dashboard" / "real_9b6"),
                                   users_file=str(users_file), environ={}, ui_dir=None))
    for path in ("/api/summary", "/api/fetch/status"):
        assert client.get(path, headers={"Authorization": "Bearer anything"}).status_code == 503
    assert client.post("/api/github/connect", json={"token": "x"},
                       headers={"Authorization": "Bearer anything"}).status_code == 503


def test_a_users_file_symlink_is_never_followed_or_replaced(tmp_path):
    local = tmp_path / "local"
    local.mkdir(mode=0o700)
    target = tmp_path / "elsewhere.json"
    target.write_text('{"users": []}')
    (local / "users.json").symlink_to(target)
    result = launch(tmp_path, "--setup-only")
    assert result.returncode == 0 and "is not a regular file" in result.stderr
    assert (local / "users.json").is_symlink() and target.read_text() == '{"users": []}'


@pytest.mark.parametrize("how", ["flag", "environment"])
def test_github_can_be_turned_off_without_touching_users_json(tmp_path, how):
    first = launch(tmp_path, "--setup-only")
    assert first.returncode == 0
    users_file = tmp_path / "local" / "users.json"
    doc = json.loads(users_file.read_text())
    doc["users"][0]["roles"] = ["viewer", "caller_reader"]  # the user removed data_refresher on purpose
    users_file.write_text(json.dumps(doc))
    users_file.chmod(0o600)
    before = users_file.read_bytes()
    args, env = (["--no-github"], None) if how == "flag" else ([], {"DASHBOARD_NO_GITHUB": "1"})
    result = launch(tmp_path, "--setup-only", *args, extra_env=env)
    assert result.returncode == 0, result.stderr
    assert users_file.read_bytes() == before  # the role is not granted again
    assert "data_refresher role" not in result.stdout
    assert "GitHub access: off" in result.stdout and "--no-github" in result.stdout.split("==> Ready:")[1]


def test_no_github_starts_the_server_with_github_off(tmp_path):
    venv, record = fake_venv(tmp_path)
    result = launch(tmp_path, "--no-browser", "--no-github", "--port", "8796", venv=str(venv))
    assert result.returncode == 0, result.stderr
    assert json.loads(record.read_text())["argv"] == ["--port", "8796", "--no-github"]


@pytest.mark.parametrize("other", ["--enable-github-fetch", "--fetch"])
def test_no_github_conflicts_with_github_options(tmp_path, other):
    result = launch(tmp_path, "--setup-only", "--no-github", other, stdin="x\n")
    assert result.returncode == 1 and "cannot be combined" in result.stderr


def test_deprecated_alias_still_works_alongside_the_migration(tmp_path):
    result = launch(tmp_path, "--setup-only", "--enable-github-fetch", stdin=GITHUB_TOKEN + "\n")
    assert result.returncode == 0 and "deprecated" in result.stderr and "--github-token-fd 3" in result.stdout


@pytest.mark.skipif(shutil.which("chflags") is None or os.geteuid() == 0,
                    reason="needs chflags (macOS/BSD) and a non-root user to make the file truly unreadable")
def test_an_unreadable_users_file_is_reported_and_left_untouched(tmp_path):
    """Mode 000 plus the user-immutable flag: the launcher can neither read nor re-mode it."""
    users_file = broken_users_file(tmp_path, b'{"users": []}')
    users_file.chmod(0o000)
    subprocess.run(["chflags", "uchg", str(users_file)], check=True)
    try:
        result = launch(tmp_path, "--setup-only")
        assert result.returncode == 0, result.stderr
        assert "could not set" in result.stderr and "is unreadable" in result.stderr
        assert "Traceback" not in result.stderr and "==> Ready:" in result.stdout
        assert stat.S_IMODE(users_file.stat().st_mode) == 0
    finally:
        subprocess.run(["chflags", "nouchg", str(users_file)], check=False)
        users_file.chmod(0o600)
    assert users_file.read_bytes() == b'{"users": []}'
