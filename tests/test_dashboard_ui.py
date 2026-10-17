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
    assert re.findall(r'api\("([^"?]+)', app_js) == ["/api/summary", "/api/drifts", "/api/drifts", "/api/drifts",
                                                      "/api/summary", "/api/remediations", "/api/unmanaged"]
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


# --------------------------------------------------------------------------- "Could not load data (http_404)"
# Regression (2026-10-17): after sign-in the UI showed `Could not load data (http_404)` for any token.
# Every request the UI makes exists in dashboard-api; the 404 came from a server that does not serve
# the API (the dashboard files opened through a static server or file preview), whose HTML 404 page
# carries no {"error": ...} body. The UI now reports that case as `api_not_found`, before sign-in.

UI_CALLS = sorted(set(re.findall(r'api\("([^"]+)"', browser_code()["app.js"])))


@pytest.fixture
def signed_in(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from dashboard_api.app import create_app

    token = "v" * 40
    users = tmp_path / "users.json"
    users.write_text(json.dumps({"users": [{"name": "m", "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                                            "roles": ["viewer", "caller_reader"]}]}), encoding="utf-8")
    users.chmod(0o600)
    return TestClient(create_app(data_dir=str(REAL), users_file=str(users), terraform_json=None, environ={})), token


def test_every_ui_request_exists_in_the_api(signed_in):
    client, token = signed_in
    assert UI_CALLS == ["/api/drifts", "/api/drifts?include_caller=true", "/api/remediations", "/api/summary",
                        "/api/unmanaged"]
    for path in UI_CALLS:
        valid = client.get(path, headers={"Authorization": f"Bearer {token}"})
        assert valid.status_code == 200 and valid.headers["content-type"] == "application/json", path
        for headers in ({}, {"Authorization": "Bearer wrong-token"}):
            refused = client.get(path, headers=headers)
            assert (refused.status_code, refused.json()) == (401, {"error": "unauthenticated"}), path


def test_api_404s_always_carry_the_error_envelope(signed_in):
    client, token = signed_in
    headers = {"Authorization": f"Bearer {token}"}
    for path in ("/api/reports/github-1-1", "/api/drifts?report_id=nope", "/api/remediations?report_id=nope",
                 "/api/unknown", "/api/summary/extra"):
        response = client.get(path, headers=headers)
        assert response.status_code == 404 and set(response.json()) == {"error"}, path


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js to evaluate render.js")
def test_static_server_404_is_reported_as_api_not_found(tmp_path):
    """The exact failing request: GET /api/summary with a token, against a static server of dashboard/."""
    import functools
    import http.server
    import threading
    import urllib.error
    import urllib.request

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(UI))
    handler.log_message = lambda *args: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/api/summary",
                                         headers={"Authorization": "Bearer any-token", "Accept": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=10)
        status, body = caught.value.code, caught.value.read().decode("utf-8", "replace")
    finally:
        server.shutdown()
        server.server_close()
    assert status == 404 and body.lstrip().startswith("<!DOCTYPE")  # not the API: no JSON error envelope
    script = ("const R = require(process.argv[1]); let body = null; try { body = JSON.parse(process.argv[2]); } "
              "catch (e) {} const code = R.apiErrorCode(Number(process.argv[3]), body); "
              "console.log(JSON.stringify([code, R.errorMessage(code, 'http://static.test')]));")
    result = subprocess.run(["node", "-e", script, str(UI / "render.js"), body, str(status)], capture_output=True,
                            text=True, timeout=60, check=True)
    code, message = json.loads(result.stdout)
    assert code == "api_not_found"
    assert "dashboard-api server" in message and "http_404" not in message


def test_ui_checks_the_api_before_sign_in():
    app_js = browser_code()["app.js"]
    assert "checkApi();" in app_js and 'err.code === "unauthenticated"' in app_js
    assert "if (state.token) headers.Authorization" in app_js  # no "Bearer null" header before sign-in
