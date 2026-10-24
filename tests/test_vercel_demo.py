"""Tests for the Vercel dashboard demo (`index.py`, `vercel.json`, `.vercelignore`, `deploy/vercel/`).

Run from the repository root:
    pytest tests/test_vercel_demo.py

The entry point is loaded from its file, as Vercel's runtime loads it. Sign-in tests use a users file of
their own with the deployed configuration otherwise unchanged; the deployed users file is only inspected
(its token is not in the repository). No Azure, GitHub, network or credentials.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
sys.path.insert(0, TESTS)

from tiers import integration  # noqa: E402

try:
    from fastapi.testclient import TestClient

    from dashboard_api import app as app_module
    from dashboard_api import auth
    from drift_engine import activity_logs as al
except ImportError:  # the dashboard extra (or httpx) is not installed
    TestClient = None

REAL_RUNS = {"github-38105671846-1", "github-38109121618-1", "github-38111406531-1"}
GET_ENDPOINTS = ("/api/summary", "/api/drifts", "/api/remediations", "/api/unmanaged", "/api/fetch/status",
                 "/api/reports/github-38109121618-1")
USERS_FILE = os.path.join(ROOT, "deploy", "vercel", "users.json")


def load_entry_point(name: str = "vercel_demo_index"):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "index.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(TestClient is None, "dashboard extra not installed (pip install -e '.[dashboard]')")
class VercelEntryPointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = load_entry_point()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.tokens = {}
        users = []
        for name, roles in (("viewer", ["viewer"]), ("everything", ["viewer", "caller_reader", "data_refresher"])):
            cls.tokens[name] = secrets.token_urlsafe(32)
            users.append({"name": name, "token_sha256": auth.token_digest(cls.tokens[name]), "roles": roles})
        cls.users_file = os.path.join(cls.tmp.name, "users.json")
        with open(cls.users_file, "w", encoding="utf-8") as fh:
            json.dump({"users": users}, fh)
        os.chmod(cls.users_file, 0o600)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def client(self, **kwargs) -> TestClient:
        return TestClient(self.index.create_demo_app(users_file=self.users_file, **kwargs))

    def get(self, client: TestClient, path: str, user: str | None = "viewer"):
        headers = {"Authorization": f"Bearer {self.tokens[user]}"} if user else {}
        return client.get(path, headers=headers)

    def post(self, client: TestClient, path: str, user: str, body: dict | None = None):
        headers = {"Authorization": f"Bearer {self.tokens[user]}", "Origin": "http://testserver"}
        return client.post(path, headers=headers, json=body if body is not None else {})

    def test_entry_point_exposes_the_fastapi_app_with_the_demo_configuration(self) -> None:
        from fastapi import FastAPI

        self.assertIsInstance(self.index.app, FastAPI)
        self.assertEqual(self.index.DATA_DIR, os.path.join(ROOT, "tests", "fixtures", "dashboard", "real_9b6"))
        self.assertEqual(self.index.USERS_FILE, USERS_FILE)
        self.assertEqual(self.index.UI_DIR, os.path.join(ROOT, "dashboard"))

    def test_deployed_app_rejects_unauthenticated_and_unknown_tokens(self) -> None:
        client = TestClient(self.index.app)  # the deployed users file
        for path in GET_ENDPOINTS:
            for headers in ({}, {"Authorization": f"Bearer {secrets.token_urlsafe(32)}"}, {"Authorization": "Basic x"}):
                response = client.get(path, headers=headers)
                self.assertEqual(response.status_code, 401, path)
                self.assertEqual(response.json(), {"error": "unauthenticated"})
                self.assertEqual(response.headers["www-authenticate"], "Bearer")
        for path in ("/api/fetch", "/api/github/disconnect"):
            self.assertEqual(client.post(path).status_code, 401, path)

    def test_cookies_grant_no_access_and_none_are_set(self) -> None:
        """The UI sends same-origin cookies (Vercel Authentication's own sign-in cookie must pass the protected
        deployment); the API ignores every cookie: only the bearer header signs in, and it never sets one."""
        client = self.client()
        cookie = {"Cookie": f"_vercel_jwt={secrets.token_urlsafe(32)}; session=viewer; token={self.tokens['viewer']}"}
        for path in GET_ENDPOINTS:
            response = client.get(path, headers=cookie)
            self.assertEqual((response.status_code, response.json()), (401, {"error": "unauthenticated"}), path)
            self.assertNotIn("set-cookie", response.headers, path)
        response = client.post("/api/fetch", headers=dict(cookie, Origin="http://testserver"))
        self.assertEqual(response.status_code, 401)
        signed_in = client.get("/api/summary", headers=dict(cookie, Authorization=f"Bearer {self.tokens['viewer']}"))
        self.assertEqual(signed_in.status_code, 200)
        for response in (signed_in, client.get("/"), client.get("/app.js")):
            self.assertNotIn("set-cookie", response.headers)

    def test_viewer_reads_the_three_fixture_runs(self) -> None:
        client = self.client()
        summary = self.get(client, "/api/summary")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual({run["report_id"] for run in summary.json()["history"]}, REAL_RUNS)
        self.assertEqual(summary.json()["data_problems"], {})
        drifts = self.get(client, "/api/drifts").json()
        self.assertEqual(drifts["reports"], ["github-38111406531-1"])  # the latest run of `dev`
        for run_id in sorted(REAL_RUNS):
            report = self.get(client, f"/api/reports/{run_id}")
            self.assertEqual(report.status_code, 200, run_id)
            self.assertEqual(report.json()["report_id"], run_id)
            artifacts = report.json()["artifacts"]
            self.assertEqual(artifacts["drift_report"]["public_version"], "1")
            self.assertIsNotNone(artifacts["ai_analysis_report"], run_id)
            self.assertIsNotNone(artifacts["investigation"], run_id)
            self.assertIsNotNone(artifacts["cost_run"], run_id)
            self.assertNotIn("caller_recorded_by_azure", json.dumps(report.json()))
        drifted = self.get(client, "/api/drifts?report_id=github-38109121618-1").json()["drifts"]
        self.assertEqual([row["address"] for row in drifted], ['module.resource_group.azurerm_resource_group.this["main"]'])
        for path in ("/api/remediations", "/api/unmanaged"):
            self.assertEqual(self.get(client, path).status_code, 200, path)

    def test_viewer_gets_no_caller_identity_and_no_github_access(self) -> None:
        client = self.client()
        for path in ("/api/drifts?include_caller=true", "/api/reports/github-38109121618-1?include_caller=true"):
            response = self.get(client, path)
            self.assertEqual((response.status_code, response.json()), (403, {"error": "caller_access_denied"}))
        for path, body in (("/api/fetch", None), ("/api/github/connect", {"token": "x" * 40}),
                           ("/api/github/disconnect", None)):
            response = self.post(client, path, "viewer", body)
            self.assertEqual((response.status_code, response.json()), (403, {"error": "fetch_access_denied"}), path)
        status = self.get(client, "/api/fetch/status").json()
        self.assertEqual((status["allowed"], status["available"], status["unavailable_reason"]), (False, False, "disabled"))
        self.assertFalse(status["connection"]["connected"])

    def test_github_and_azure_stay_off_even_for_a_user_holding_every_role(self) -> None:
        """Defence in depth: a misconfigured users file still cannot start a fetch, accept a GitHub token or
        reach Azure."""
        with mock.patch.object(al, "AzureMonitorSource", side_effect=AssertionError("Azure must not be used")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("no subprocess may start")):
            client = self.client()
            for path, body in (("/api/fetch", None), ("/api/github/connect", {"token": "x" * 40})):
                response = self.post(client, path, "everything", body)
                self.assertEqual((response.status_code, response.json()), (503, {"error": "disabled"}), path)
            status = self.get(client, "/api/fetch/status", "everything").json()
            self.assertEqual((status["available"], status["unavailable_reason"]), (False, "disabled"))
            rows = self.get(client, "/api/drifts?include_caller=true&report_id=github-38109121618-1",
                            "everything").json()["drifts"]
            self.assertTrue(rows)
            for row in rows:
                caller = row["caller_recorded_by_azure"]
                self.assertNotEqual(caller["status"], "matched")
                self.assertIsNone(caller.get("caller"))

    def test_activity_log_source_refuses_every_query(self) -> None:
        with self.assertRaises(al.SourceError) as caught:
            self.index.NoActivityLog().pages("00000000-0000-0000-0000-000000000000", "")
        self.assertEqual(caught.exception.code, "credential_unavailable")

    def test_process_environment_has_no_effect(self) -> None:
        with tempfile.TemporaryDirectory() as empty, mock.patch.dict(os.environ, {
                "DASHBOARD_DATA_DIR": empty, "DASHBOARD_USERS_FILE": os.path.join(empty, "users.json"),
                "DASHBOARD_TERRAFORM_JSON": os.path.join(empty, "state.json"), "GH_TOKEN": "not-used",
                "GITHUB_API_URL": "http://127.0.0.1:9"}):
            index = load_entry_point("vercel_demo_index_env")
            client = self.client()
            self.assertEqual(index.DATA_DIR, self.index.DATA_DIR)
            self.assertEqual(len(self.get(client, "/api/summary").json()["history"]), 3)
            self.assertEqual(TestClient(index.app).get("/api/summary").status_code, 401)  # still the deployed file

    def test_ui_and_api_share_one_origin_with_the_existing_security_headers(self) -> None:
        client = self.client()
        responses = {"/": client.get("/"), "/app.js": client.get("/app.js"), "/styles.css": client.get("/styles.css"),
                     "/api/summary": self.get(client, "/api/summary"), "/api/drifts (401)": client.get("/api/drifts"),
                     "/missing (404)": client.get("/app.test.js")}
        for label, response in responses.items():
            for name, value in app_module.SECURITY_HEADERS.items():
                self.assertEqual(response.headers.get(name), value, f"{label}: {name}")
        self.assertEqual(responses["/"].status_code, 200)
        self.assertIn("text/html", responses["/"].headers["content-type"])
        self.assertEqual(responses["/missing (404)"].status_code, 404)  # only the UI files are served
        html = responses["/"].text
        self.assertNotRegex(html, r"""(src|href)=["'](https?:)?//""")  # nothing loaded from another origin
        self.assertIn("connect-src 'self'", app_module.SECURITY_HEADERS["Content-Security-Policy"])


class DeployedUsersFileTest(unittest.TestCase):
    def test_one_viewer_only_account_with_a_digest_only(self) -> None:
        with open(USERS_FILE, encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertEqual(len(doc["users"]), 1)
        user = doc["users"][0]
        self.assertEqual(set(user), {"name", "token_sha256", "roles"})
        self.assertEqual(user["roles"], ["viewer"])
        self.assertRegex(user["token_sha256"], r"^[0-9a-f]{64}$")
        mode = os.lstat(USERS_FILE).st_mode
        self.assertTrue(stat.S_ISREG(mode))
        self.assertFalse(mode & (stat.S_IWGRP | stat.S_IWOTH), "auth.load_users refuses a group/other-writable file")

    @integration
    def test_users_file_is_tracked_without_write_bits_for_group_or_others(self) -> None:
        out = subprocess.run(["git", "ls-files", "-s", "deploy/vercel/users.json"], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout.split()
        if not out:
            self.skipTest("deploy/vercel/users.json is not committed yet")
        self.assertEqual(out[0], "100644")  # a checkout gives 0644 under the usual umask 022


class NewTokenScriptTest(unittest.TestCase):
    def test_writes_a_viewer_only_digest_and_a_private_token_and_never_prints_it(self) -> None:
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import new_vercel_demo_token as script

        with tempfile.TemporaryDirectory() as tmp:
            users, token_file = os.path.join(tmp, "users.json"), os.path.join(tmp, "local", "token.txt")
            with mock.patch("sys.stdout") as out:
                self.assertEqual(script.main(["--users-file", users, "--token-file", token_file]), 0)
            with open(token_file, encoding="ascii") as fh:
                token = fh.read().strip()
            self.assertGreaterEqual(len(token), 43)  # 32 random bytes, URL-safe base64
            printed = "".join(str(call) for call in out.mock_calls)
            self.assertNotIn(token, printed)
            self.assertEqual(stat.S_IMODE(os.lstat(token_file).st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(os.lstat(users).st_mode), 0o644)
            with open(users, encoding="utf-8") as fh:
                text = fh.read()
            self.assertNotIn(token, text)
            doc = json.loads(text)
            self.assertEqual(doc["users"][0]["roles"], ["viewer"])
            self.assertEqual(doc["users"][0]["token_sha256"], hashlib.sha256(token.encode()).hexdigest())
            if TestClient is not None:  # the dashboard accepts the file and the token
                found = auth.authenticate(f"Bearer {token}", auth.load_users(users))
                self.assertEqual(found.roles, frozenset({"viewer"}))
            self.assertEqual(script.main(["--users-file", users, "--token-file", token_file]), 0)  # rotation
            with open(token_file, encoding="ascii") as fh:
                self.assertNotEqual(fh.read().strip(), token)
            self.assertEqual(sorted(os.listdir(tmp)), ["local", "users.json"])  # no staging file left behind
            self.assertEqual(os.listdir(os.path.dirname(token_file)), ["token.txt"])

    def test_refuses_a_link(self) -> None:
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import new_vercel_demo_token as script

        with tempfile.TemporaryDirectory() as tmp:
            link = os.path.join(tmp, "users.json")
            os.symlink(os.path.join(tmp, "elsewhere.json"), link)
            with mock.patch("sys.stderr"):
                self.assertEqual(script.main(["--users-file", link, "--token-file", os.path.join(tmp, "t")]), 64)
            self.assertFalse(os.path.exists(os.path.join(tmp, "t")))


class DeployedRequirementsTest(unittest.TestCase):
    def test_every_requirement_is_hash_pinned_and_matches_the_ci_constraints(self) -> None:
        with open(os.path.join(ROOT, "deploy", "vercel", "requirements.txt"), encoding="utf-8") as fh:
            text = fh.read()
        entries = re.findall(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+) \\\n((?:\s+--hash=sha256:[0-9a-f]{64}(?: \\)?\n)+)",
                             text, re.M)
        pins = {name.lower().replace("_", "-"): version for name, version, _ in entries}
        self.assertEqual(len(entries), len(re.findall(r"^[A-Za-z0-9].*==", text, re.M)), "a pin without hashes")
        self.assertIn("fastapi", pins)
        self.assertNotIn("uvicorn", pins)  # Vercel serves the ASGI app itself
        constraints = {}
        for name in os.listdir(os.path.join(ROOT, "ci")):
            if name.endswith("-constraints.txt"):
                with open(os.path.join(ROOT, "ci", name), encoding="utf-8") as fh:
                    for line in fh:
                        if m := re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)", line):
                            constraints[m.group(1).lower().replace("_", "-")] = m.group(2)
        for name, version in pins.items():
            self.assertEqual(constraints.get(name), version, f"{name} differs from ci/*-constraints.txt")

    def test_vercel_json_installs_that_file_for_the_python_version(self) -> None:
        with open(os.path.join(ROOT, "vercel.json"), encoding="utf-8") as fh:
            config = json.load(fh)
        command = config["installCommand"]
        for flag in ("--require-hashes", "--no-deps", "--only-binary=:all:", "-r deploy/vercel/requirements.txt"):
            self.assertIn(flag, command)
        self.assertEqual(config["framework"], "fastapi")
        self.assertEqual(list(config["functions"]), ["index.py"])
        with open(os.path.join(ROOT, ".python-version"), encoding="utf-8") as fh:
            self.assertEqual(fh.read().strip(), "3.13")  # the pydantic-core wheels hashed in requirements.txt

    def test_vercel_json_fits_the_schema_limits(self) -> None:
        """https://openapi.vercel.sh/vercel.json: `excludeFiles` is one string of at most 256 characters (Vercel
        refuses the whole file otherwise) and a `functions` key is at most 256 characters."""
        with open(os.path.join(ROOT, "vercel.json"), encoding="utf-8") as fh:
            functions = json.load(fh)["functions"]
        for key, spec in functions.items():
            self.assertLessEqual(len(key), 256)
            self.assertIsInstance(spec["excludeFiles"], str)
            self.assertLessEqual(len(spec["excludeFiles"]), 256)


def _expand_braces(pattern: str) -> list[str]:
    """Brace expansion as minimatch applies it: comma lists, nested groups (`{a,b/{c,d}}`)."""
    depth = start = 0
    for i, char in enumerate(pattern):
        if char == "{":
            depth, start = depth + 1, i if depth == 0 else start
        elif char == "}" and depth:
            depth -= 1
            if depth == 0:
                parts, level, last = [], 0, start + 1
                for j in range(start + 1, i):
                    level += {"{": 1, "}": -1}.get(pattern[j], 0)
                    if pattern[j] == "," and level == 0:
                        parts.append(pattern[last:j])
                        last = j + 1
                parts.append(pattern[last:i])
                return [x for part in parts for x in _expand_braces(pattern[:start] + part + pattern[i + 1:])]
    return [pattern]


def _glob_regex(pattern: str) -> re.Pattern:
    """One brace-free glob of the `excludeFiles` form used here (`**/`, `**`, `*`, `[!x]`) as a regex, with
    minimatch's `dot: true` (glob applies ignore patterns that way): `*` also matches a leading dot."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "[":
            end = pattern.index("]", i)
            body = pattern[i + 1:end]
            out, i = out + "[" + ("^" + body[1:] if body.startswith("!") else body) + "]", end + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def excluded_by_vercel_json(path: str) -> bool:
    with open(os.path.join(ROOT, "vercel.json"), encoding="utf-8") as fh:
        spec = json.load(fh)["functions"]["index.py"]["excludeFiles"]
    return any(_glob_regex(p).match(path) for p in _expand_braces(spec))


RUNTIME_FILES = ("index.py", "deploy/vercel/users.json", "dashboard/index.html", "dashboard/app.js",
                 "dashboard/render.js", "dashboard/loader.js", "dashboard/styles.css", "src/dashboard_api/app.py",
                 "src/drift_engine/report_public.py",
                 "tests/fixtures/dashboard/real_9b6/drift-report-38109121618/drift_report.json")
SENSITIVE = re.compile(r"(^|/)(\.artifacts|\.venv|\.terraform|terraform|\.git)/|\.tfstate|\.tfplan$|(^|/)tfplan$|"
                       r"(^|/)plan\.json$|\.tfvars|(^|/)\.env|\.pem$|\.key$|\.pfx$|\.dmg$|token[^/]*\.txt$|\.coverage|"
                       r"dashboard-local|users\.json$")


@integration
class DeploymentContentsTest(unittest.TestCase):
    """What a deployment can contain: `vercel deploy` uploads the checkout minus `.vercelignore` (emulated with
    git's own gitignore matcher, which follows the same rules); a Git deployment builds the tracked files.
    Both then lose `vercel.json` `excludeFiles` when the function is bundled."""

    def cli_upload(self) -> list[str]:
        with tempfile.TemporaryDirectory() as gitdir:
            subprocess.run(["git", "init", "-q", "--bare", gitdir], check=True)
            out = subprocess.run(["git", "--work-tree", ROOT, "ls-files", "-o", "--exclude-from",
                                  os.path.join(ROOT, ".vercelignore")], env=dict(os.environ, GIT_DIR=gitdir),
                                 capture_output=True, text=True, check=True).stdout
        return out.splitlines()

    def test_cli_upload_holds_only_the_demo_and_nothing_sensitive(self) -> None:
        files = self.cli_upload()
        for path in RUNTIME_FILES + ("vercel.json", ".python-version", "deploy/vercel/requirements.txt"):
            self.assertIn(path, files)
        allowed = re.compile(r"^(index\.py|vercel\.json|\.python-version|pyproject\.toml|LICENSE|src/(dashboard_api|"
                             r"drift_engine)/[^/]+|dashboard/[^/]+|deploy/vercel/[^/]+|"
                             r"tests/fixtures/dashboard/real_9b6/.+)$")
        for path in files:
            self.assertRegex(path, allowed)
            if path != "deploy/vercel/users.json":
                self.assertNotRegex(path, SENSITIVE)
        self.assertFalse([p for p in files if p.endswith(".test.js") or p.endswith(".pyc")])

    def test_tracked_files_hold_no_state_plans_or_secrets(self) -> None:
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                                 check=True).stdout.splitlines()
        risky = re.compile(r"\.tfstate|\.tfplan$|(^|/)tfplan$|(^|/)plan\.json$|(^|/)\.env|\.pem$|\.key$|\.pfx$|"
                           r"\.dmg$|token[^/]*\.txt$|^\.artifacts/")
        self.assertEqual([p for p in tracked if risky.search(p)], [])

    def test_function_bundle_keeps_the_runtime_files_and_drops_the_rest(self) -> None:
        for path in RUNTIME_FILES + ("src/drift_engine/investigation_public.py", "src/dashboard_api/store.py"):
            self.assertFalse(excluded_by_vercel_json(path), path)
        for path in (".artifacts/dashboard-local/users.json", "terraform/environments/dev/backend.tf",
                     "x/terraform.tfstate", "a/b/dev.tfstate.backup", "tfplan", "a/plan.json", "a/.env",
                     "a/.env.local", "scripts/fetch_dashboard_data.py", "src/ai_engine/llm.py", "tests/test_cli.py",
                     "tests/fixtures/plan_evidence/in_sync/plan.sanitized.json", "dashboard/app.test.js",
                     "PROJECT_PLAN.md", "aitdd-l1-backup-2026-10-19.dmg", ".github/workflows/tests.yml",
                     ".artifacts/dashboard-local/vercel-demo-viewer-token.txt", "terraform.tfstate", "a/x.tfplan",
                     "x/.terraform/terraform.tfstate", "a/secret.auto.tfvars.json", "src/dashboard_api/.env.production",
                     "a/client.key", "a/id.pem", "cert.pfx", ".coverage.host.1", "tests/corpora/guards.json",
                     "tests/fixtures/security_plans/nsg_open_inbound/plan.synthetic.json", "requirements.txt"):
            self.assertTrue(excluded_by_vercel_json(path), path)


if __name__ == "__main__":
    unittest.main()
