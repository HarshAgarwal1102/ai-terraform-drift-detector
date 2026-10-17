"""Tests for the dashboard UI (Task 13.2).

Run from the repository root:
    pytest tests/test_dashboard_ui.py

- The component tests (dashboard/render.test.js) run under `node --test`: they render a
  human name, a service principal and a managed identity identifier, every `Unknown`
  reason, filters, overview cards and the detail modal.
- Static checks: the browser code uses no browser storage or cookies, contacts no
  external host (Azure included), and has no inline script, style or event handler.
- The API serves exactly the UI files, with the strict Content-Security-Policy.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "dashboard"
REAL = ROOT / "tests" / "fixtures" / "dashboard" / "real_9b6"
BROWSER_FILES = ("index.html", "app.js", "render.js", "styles.css")


def browser_code() -> dict[str, str]:
    return {name: (UI / name).read_text(encoding="utf-8") for name in BROWSER_FILES}


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js for the component tests")
def test_component_tests_pass():
    result = subprocess.run(["node", "--test", str(UI / "render.test.js")], cwd=ROOT, capture_output=True,
                            text=True, timeout=120)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]
    assert re.search(r"^# pass ([1-9][0-9]*)$", result.stdout, re.M)
    assert re.search(r"^# fail 0$", result.stdout, re.M)


def test_no_browser_storage_cookies_or_external_hosts():
    for name, text in browser_code().items():
        for forbidden in ("localStorage", "sessionStorage", "indexedDB", "document.cookie", "caches.open",
                          "azure.com", "azure.net", "microsoftonline", "http://", "https://", "//cdn"):
            assert forbidden not in text, f"{name}: {forbidden}"


def test_no_inline_script_style_or_handlers():
    html = browser_code()["index.html"]
    assert re.findall(r"<script\b[^>]*>", html) == ['<script src="render.js" defer>', '<script src="app.js" defer>']
    assert not re.search(r"\sstyle\s*=", html)
    assert not re.search(r"\son[a-z]+\s*=", html)
    for name in ("app.js", "render.js"):
        text = browser_code()[name]
        assert "eval(" not in text and "new Function" not in text, name
        assert not re.search(r"style=\\?\"", text), name  # a CSP without 'unsafe-inline' would block it


def test_api_calls_go_through_the_backend_only():
    app_js = browser_code()["app.js"]
    assert re.findall(r'api\("([^"?]+)', app_js) == ["/api/drifts", "/api/drifts", "/api/summary",
                                                      "/api/remediations"]
    assert "encodeURIComponent(state.run)" in app_js
    assert app_js.count("fetch(") == 1
    assert 'credentials: "omit"' in app_js and 'cache: "no-store"' in app_js


@pytest.fixture
def client(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from dashboard_api.app import create_app

    users = tmp_path / "users.json"
    users.write_text(json.dumps({"users": [{"name": "m", "token_sha256": hashlib.sha256(b"t" * 32).hexdigest(),
                                            "roles": ["viewer"]}]}), encoding="utf-8")
    users.chmod(0o600)
    return TestClient(create_app(data_dir=str(REAL), users_file=str(users), environ={}))


def test_ui_is_served_with_a_strict_policy(client):
    page = client.get("/")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert "Caller recorded by Azure" in page.text
    policy = page.headers["content-security-policy"]
    for directive in ("default-src 'none'", "script-src 'self'", "style-src 'self'", "connect-src 'self'",
                      "frame-ancestors 'none'"):
        assert directive in policy
    assert "unsafe-inline" not in policy and "unsafe-eval" not in policy
    assert page.headers["cache-control"] == "no-store"
    for name, kind in (("app.js", "text/javascript"), ("render.js", "text/javascript"), ("styles.css", "text/css")):
        response = client.get(f"/{name}")
        assert response.status_code == 200 and response.headers["content-type"].startswith(kind), name
    for path in ("/render.test.js", "/pyproject.toml", "/..%2Fpyproject.toml", "/index.htm", "/docs"):
        assert client.get(path).status_code == 404, path


def test_ui_assets_need_no_token_but_data_does(client):
    assert client.get("/app.js").status_code == 200
    assert client.get("/api/summary").status_code == 401
    assert client.get("/api/summary", headers={"Authorization": "Bearer " + "t" * 32}).status_code == 200


def test_ui_can_be_disabled(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from dashboard_api.app import create_app

    client = TestClient(create_app(data_dir=str(REAL), users_file=str(tmp_path / "none"), ui_dir=None, environ={}))
    assert client.get("/").status_code == 404
