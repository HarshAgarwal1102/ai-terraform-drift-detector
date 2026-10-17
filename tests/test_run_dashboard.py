"""Tests for the one-command dashboard launcher (scripts/run_dashboard.sh, Phase 13).

Run from the repository root:
    pytest tests/test_run_dashboard.py

The launcher runs with --setup-only against the test interpreter's own environment
(DASHBOARD_VENV) and a temporary DASHBOARD_LOCAL_DIR, so nothing is installed, no data is
fetched, no server starts and the real .artifacts/ is never touched.
"""

from __future__ import annotations

import json
import re
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


def launch(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(tmp_path),
           "DASHBOARD_VENV": sys.prefix, "DASHBOARD_LOCAL_DIR": str(tmp_path / "local"),
           "DASHBOARD_DATA_DIR": str(ROOT / "tests" / "fixtures" / "dashboard" / "real_9b6")}
    return subprocess.run(["bash", str(LAUNCHER), *args], cwd=ROOT, env=env, capture_output=True, text=True,
                          timeout=120)


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
    assert (user["name"], user["roles"], len(user["token_sha256"])) == ("local-admin", ["viewer", "caller_reader"], 64)
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
