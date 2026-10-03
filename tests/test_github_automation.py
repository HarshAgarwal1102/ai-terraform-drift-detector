"""Tests for scripts/github_automation.py (Task 8.1, deterministic drift issue creator).

No network: the GitHub API is an in-memory fake behind the client's `opener` hook,
and the test-wide guard (tests/conftest.py) blocks any real connection. Reports are
produced by the real classifier from the repository fixtures, with the run bound to
`github-123-1` the way CI binds it.
"""

from __future__ import annotations

import ast
import copy
import email.message
import glob
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import types
import unicodedata
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from urllib.parse import parse_qs, urlsplit

import yaml

from drift_engine.classifier import evaluate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "github_automation.py")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "drift-detection.yml")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")

_spec = importlib.util.spec_from_file_location("github_automation", SCRIPT)
ga = importlib.util.module_from_spec(_spec)
sys.modules["github_automation"] = ga
_spec.loader.exec_module(ga)

REPO = "octo-org/drift-repo"
TOKEN = "ghs_TESTTOKEN_never_printed_0123456789"
RUN = "github-123-1"
API = "https://api.github.com"
BOT = {"login": "github-actions[bot]", "type": "Bot"}
ENV = {
    "GITHUB_ACTIONS": "true", "GITHUB_API_URL": API, "GITHUB_SERVER_URL": "https://github.com",
    "GITHUB_REPOSITORY": REPO, "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_TOKEN": TOKEN,
}
GUID = "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"
ARM_ID = f"/subscriptions/{GUID}/resourceGroups/rg-dev/providers/Microsoft.Network/networkSecurityGroups/nsg"


# --------------------------------------------------------------------------- report helpers

def fixture_dirs() -> list[str]:
    dirs = []
    for d in sorted(glob.glob(os.path.join(FIXTURES, "*", "*", ""))):
        if any(os.path.exists(os.path.join(d, f)) for f in ("plan.sanitized.json", "plan.synthetic.json")):
            dirs.append(d)
    return dirs


def fixture_report(name: str, run_id: str = RUN) -> dict:
    matches = [d for d in fixture_dirs() if os.path.basename(os.path.normpath(d)) == name]
    assert len(matches) == 1, name
    d = matches[0]
    plan = next(os.path.join(d, f) for f in ("plan.sanitized.json", "plan.synthetic.json")
                if os.path.exists(os.path.join(d, f)))
    report = evaluate(plan, os.path.join(d, "detection_run.json")).report
    if report["run"] is not None:
        report["run"]["run_id"] = run_id
    return report


def lowest_report(**changes) -> dict:
    """external_drift: one LOW resource-group tag drift (full body)."""
    report = fixture_report("external_drift")
    report["plan"]["timestamp"] = changes.pop("plan_ts", "2026-10-03T10:00:00Z")
    return report


RG_ADDR = 'module.resource_group.azurerm_resource_group.this["main"]'


def resolved_report(count: int = 1, plan_ts: str = "2026-10-03T10:00:00Z") -> dict:
    """A valid no-drift run (Task 8.3): the in_sync fixture, optionally with extra in-sync resources."""
    report = fixture_report("in_sync")
    report["plan"]["timestamp"] = plan_ts
    base = report["resources"][0]
    for i in range(1, count):
        item = copy.deepcopy(base)
        item["address"] = f'module.resource_group.azurerm_resource_group.this["s{i:02d}"]'
        report["resources"].append(item)
    report["summary"]["resources_total"] = count
    return report


def many_resources(report: dict, count: int) -> dict:
    base = report["resources"][0]
    report["resources"] = []
    for i in range(count):
        item = copy.deepcopy(base)
        item["address"] = f'module.resource_group.azurerm_resource_group.this["r{i:02d}"]'
        report["resources"].append(item)
    report["summary"]["drifted_resources"] = count
    report["summary"]["resources_total"] = count
    return report


def evidence(report: dict, environment: str = "dev"):
    return ga.evidence_from_report(ga.load_report(json.dumps(report).encode()), environment)


def hostile_report() -> dict:
    report = lowest_report()
    resource = report["resources"][0]
    resource["address"] = ('module.x.azurerm_resource_group.this["a``b <!-- drift-issue v=1 --> @octocat #1 '
                           f'https://evil.example/x www.evil.example \u202eevil\u200b {GUID} {ARM_ID}\nline2"]')
    resource["type"] = "azurerm_resource_group"
    change = resource["attribute_changes"][0]
    variants = [["tags", "owner:alice@example.com"], ["tags", "<script>"], ["tags", "ok_key"], ["tags", GUID],
                ["tags", "@octocat"], ["tags", "#1"], ["tags", "a" * 65], ["tags", "x\u202ey"]]
    resource["attribute_changes"] = []
    for path in variants:
        item = copy.deepcopy(change)
        item["path"] = path
        resource["attribute_changes"].append(item)
    return report


# --------------------------------------------------------------------------- fake GitHub

def _headers(values: dict | None) -> email.message.Message:
    message = email.message.Message()
    for key, value in (values or {}).items():
        message[key] = value
    return message


def http_error(code: int, headers: dict | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(f"{API}/x", code, "error", _headers(headers), io.BytesIO(b"{}"))


class FakeResponse:
    def __init__(self, status: int, data, headers: dict | None = None, raw: bytes | None = None):
        self.status = status
        self.headers = _headers(headers)
        self._raw = raw if raw is not None else (b"" if data is None else json.dumps(data).encode())

    def read(self, n: int = -1) -> bytes:
        return self._raw if n < 0 else self._raw[:n]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeGitHub:
    """Minimal in-memory GitHub REST API behind GitHubClient's opener hook."""

    def __init__(self, labels=(ga.LABEL,), page_size: int = 100, next_base: str = f"{API}/repositories/1/issues",
                 descending: bool = False):
        self.labels = set(labels)
        self.descending = descending
        self.page_size = page_size
        self.next_base = next_base
        self.issues: dict[int, dict] = {}
        self.next_number = 1
        self.requests: list[tuple[str, str, object]] = []
        self.headers: list[dict] = []
        self.failures: dict[str, list] = {}
        self.list_override = None
        self.before_patch = None  # hook to simulate a concurrent human edit

    def add_issue(self, body: str, *, title: str = "t", user=None, labels=(ga.LABEL,), state: str = "open",
                  pr: bool = False, number: int | None = None) -> int:
        n = number if number is not None else self.next_number
        self.next_number = max(self.next_number, n + 1)
        item = {"number": n, "title": title, "body": body, "state": state, "user": dict(user or BOT),
                "labels": [{"name": name} for name in labels]}
        if pr:
            item["pull_request"] = {"url": "x"}
        self.issues[n] = item
        return n

    def fail(self, kind: str, *outcomes) -> None:
        self.failures.setdefault(kind, []).extend(outcomes)

    def count(self, method: str) -> int:
        return sum(1 for m, _, _ in self.requests if m == method)

    def open(self, req: urllib.request.Request, timeout: float):
        assert timeout == ga.TIMEOUT
        method = req.get_method()
        payload = json.loads(req.data) if req.data else None
        self.requests.append((method, req.full_url, payload))
        self.headers.append(dict(req.header_items()))
        parts = urlsplit(req.full_url)
        if method == "GET" and parts.path.startswith(f"/repos/{REPO}/labels/"):
            kind = "label"
        elif method == "GET":
            kind = "list"
        elif method == "POST":
            kind = "create"
        else:
            kind = "update"
        queue = self.failures.get(kind)
        if queue:
            outcome = queue.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            if isinstance(outcome, int):
                raise http_error(outcome)
            if isinstance(outcome, tuple):
                raise http_error(*outcome)
            return outcome
        if kind == "label":
            name = parts.path.rsplit("/", 1)[1].replace("%5B", "[").replace("%5D", "]")
            if name not in self.labels:
                raise http_error(404)
            return FakeResponse(200, {"name": name})
        if kind == "list":
            if self.list_override is not None:
                return self.list_override
            page = int(parse_qs(parts.query).get("page", ["1"])[0])
            items = [self.issues[n] for n in sorted(self.issues, reverse=self.descending)]
            chunk = items[(page - 1) * self.page_size: page * self.page_size]
            headers = {}
            if page * self.page_size < len(items):
                headers["Link"] = f'<{self.next_base}?state=open&page={page + 1}>; rel="next"'
            return FakeResponse(200, copy.deepcopy(chunk), headers)
        if kind == "create":
            n = self.add_issue(payload["body"], title=payload["title"], labels=tuple(payload["labels"]))
            return FakeResponse(201, {"number": n})
        n = int(parts.path.rsplit("/", 1)[1])
        if self.before_patch:
            self.before_patch(self, n)
        self.issues[n].update(payload)
        return FakeResponse(200, {"number": n})


def args_for(report_path: str, *, publish: bool = True, drift: str = "true", environment: str = "dev",
             out_dir: str | None = None, repository: str | None = None):
    argv = ["--report", report_path, "--environment", environment, "--drift-detected", drift]
    argv += ["--publish"] if publish else ["--out-dir", out_dir]
    if repository:
        argv += ["--repository", repository]
    return ga._parser().parse_args(argv)


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gh-issues-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.sleeps: list[float] = []

    def write_report(self, report: dict, name: str = "drift_report.json") -> str:
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh)
        return path

    def client_factory(self, fake: FakeGitHub, module=ga):
        return lambda token, repo: module.GitHubClient(token, repo, opener=fake, sleep=self.sleeps.append)

    def publish(self, report: dict, fake: FakeGitHub, env: dict | None = None, module=ga):
        path = self.write_report(report)
        return module.run(args_for(path), dict(ENV if env is None else env), self.client_factory(fake, module))


# --------------------------------------------------------------------------- gating and input

class GatingTests(_Base):
    def test_not_drift_detected_is_skipped_without_reading_the_report(self):
        for value in ("unknown", "", "True", "1", "FALSE"):  # 'false' runs the Task 8.3 lifecycle
            with self.subTest(value=value):
                fake = FakeGitHub()
                result = ga.run(args_for(os.path.join(self.tmp, "missing.json"), drift=value), ENV,
                                self.client_factory(fake))
                self.assertEqual(result.outcome, "skipped")
                self.assertEqual(result.codes, ["not_drift_detected"])
                self.assertEqual(fake.requests, [])

    def test_report_failures(self):
        failed = evaluate(os.path.join(self.tmp, "absent-plan.json"),
                          os.path.join(FIXTURES, "plan_evidence", "failed_run", "detection_run.json")).report
        self.assertEqual(failed["outcome"], "failed")
        in_sync = fixture_report("in_sync")
        cases = {
            "report_failed": failed,
            "report_inconsistent": in_sync,
            "report_invalid": {"not": "a report"},
        }
        for code_, report in cases.items():
            with self.subTest(code_):
                fake = FakeGitHub()
                result = self.publish(report, fake)
                self.assertEqual(result.codes, [code_])
                self.assertEqual(result.outcome, "failed")
                self.assertEqual(fake.requests, [])

    def test_unreadable_and_oversized_reports(self):
        fake = FakeGitHub()
        result = ga.run(args_for(os.path.join(self.tmp, "nope.json")), ENV, self.client_factory(fake))
        self.assertEqual(result.codes, ["report_missing"])
        big = os.path.join(self.tmp, "big.json")
        with open(big, "wb") as fh:
            fh.write(b" " * (ga.MAX_REPORT_BYTES + 1))
        self.assertEqual(ga.run(args_for(big), ENV, self.client_factory(fake)).codes, ["report_invalid"])
        with open(big, "wb") as fh:
            fh.write(b"{not json")
        self.assertEqual(ga.run(args_for(big), ENV, self.client_factory(fake)).codes, ["report_invalid"])
        self.assertEqual(fake.requests, [])

    def test_report_consistency_checks(self):
        cases = {}
        r = lowest_report(); r["summary"]["drifted_resources"] = 2; cases["count"] = (r, "report_inconsistent")
        r = lowest_report(); r["plan"]["timestamp"] = None; cases["no-ts"] = (r, "report_inconsistent")
        r = lowest_report(); r["plan"]["timestamp"] = "2026-10-03 10:00:00"; cases["bad-ts"] = (r, "report_inconsistent")
        r = lowest_report(); r["plan"]["timestamp"] = "2026-10-03T10:00:00+00:00"; cases["offset-ts"] = (r, "report_inconsistent")
        r = lowest_report(); r["resources"].append(copy.deepcopy(r["resources"][0])); r["summary"]["drifted_resources"] = 2
        cases["duplicate-address"] = (r, "report_inconsistent")
        r = lowest_report(); r["resources"].append(copy.deepcopy(r["resources"][0]))
        r["resources"][1]["address"] = "azurerm_resource_group.extra"; r["resources"][1]["drift_action"] = None
        r["resources"][1]["drift_actions"] = None; r["resources"][1]["classification"] = "config_change"
        cases["mixed-ok"] = (r, None)
        r = lowest_report(); r["run"]["environment"] = "prod"; cases["env"] = (r, "environment_mismatch")
        r = lowest_report(); r["run"]["run_id"] = "local-20261001T171607Z-1"; cases["local-run"] = (r, "run_mismatch")
        r = lowest_report(); r["run"]["run_id"] = None; cases["no-run-id"] = (r, "run_mismatch")
        r = lowest_report(); r["run"]["run_id"] = "github-123-1 -->"; cases["run-id-injection"] = (r, "run_mismatch")
        for name, (report, code_) in cases.items():
            with self.subTest(name):
                fake = FakeGitHub()
                result = self.publish(report, fake)
                self.assertEqual(result.codes, [code_] if code_ else [])
                if code_:
                    self.assertEqual(fake.requests, [])

    def test_environment_argument_is_validated(self):
        for value in ("Dev", "../dev", "dev env", "", "a" * 33, "dev\n"):
            with self.subTest(value=value):
                fake = FakeGitHub()
                result = ga.run(args_for(self.write_report(lowest_report()), environment=value), ENV,
                                self.client_factory(fake))
                self.assertEqual(result.codes, ["environment_invalid"])
                self.assertEqual(fake.requests, [])


class PublishBindingTests(_Base):
    def test_binding_failures_make_no_request(self):
        cases = {
            "publish_outside_actions": {"GITHUB_ACTIONS": None},
            "api_url_invalid": {"GITHUB_API_URL": "https://ghe.example.com/api/v3"},
            "repository_invalid": {"GITHUB_REPOSITORY": "octo-org/../x"},
            "run_mismatch": {"GITHUB_RUN_ID": "124"},
            "attempt_mismatch": {"GITHUB_RUN_ATTEMPT": "2"},
            "token_missing": {"GITHUB_TOKEN": ""},
        }
        extra = {"server": ("api_url_invalid", {"GITHUB_SERVER_URL": "https://evil.example"}),
                 "run-not-digits": ("run_mismatch", {"GITHUB_RUN_ID": "12a"}),
                 "attempt-not-digits": ("run_mismatch", {"GITHUB_RUN_ATTEMPT": ""}),
                 "no-repo": ("repository_invalid", {"GITHUB_REPOSITORY": None})}
        items = [(c, c, e) for c, e in cases.items()] + [(n, c, e) for n, (c, e) in extra.items()]
        for name, code_, changes in items:
            with self.subTest(name):
                env = dict(ENV)
                for key, value in changes.items():
                    if value is None:
                        env.pop(key)
                    else:
                        env[key] = value
                fake = FakeGitHub()
                built = []
                factory = lambda token, repo: built.append(1)  # noqa: E731 - must never be called
                result = ga.run(args_for(self.write_report(lowest_report())), env, factory)
                self.assertEqual(result.codes, [code_])
                self.assertEqual(built, [])
                self.assertEqual(fake.requests, [])

    def test_rerun_of_failed_jobs_never_publishes(self):
        # attempt 2 re-runs only the issues job: the artifact still says attempt 1
        fake = FakeGitHub()
        result = self.publish(lowest_report(), fake, dict(ENV, GITHUB_RUN_ATTEMPT="2"))
        self.assertEqual(result.codes, ["attempt_mismatch"])
        # re-run of all jobs produces fresh evidence bound to the new attempt
        report = lowest_report()
        report["run"]["run_id"] = "github-123-2"
        result = self.publish(report, fake, dict(ENV, GITHUB_RUN_ATTEMPT="2"))
        self.assertEqual((result.codes, len(result.created)), ([], 1))


# --------------------------------------------------------------------------- issue set

class IssueSetTests(_Base):
    def test_issue_set_is_the_has_drift_set_on_every_fixture(self):
        checked = 0
        for d in fixture_dirs():
            name = os.path.basename(os.path.normpath(d))
            report = fixture_report(name)
            if report["outcome"] != "succeeded":
                continue
            with self.subTest(name):
                expected = sorted(r["address"] for r in report["resources"] if r["drift_action"] is not None)
                self.assertEqual(len(expected), report["summary"]["drifted_resources"])
                if not report["has_drift"]:
                    with self.assertRaises(ga.AutomationError) as ctx:
                        evidence(report)
                    self.assertEqual(ctx.exception.code, "report_inconsistent")
                    continue
                ev = evidence(report)
                self.assertEqual(sorted(r.address for r in ev.resources), expected)
                for r in ev.resources:
                    self.assertNotIn(r.classification, ("config_change", "resource_added", "resource_removed", "in_sync"))
                checked += 1
        self.assertGreaterEqual(checked, 25)

    def test_processing_order_is_severity_then_address(self):
        report = many_resources(lowest_report(), 4)
        levels = ["LOW", "CRITICAL", "LOW", "HIGH"]
        for item, level in zip(report["resources"], levels):
            item["severity"]["level"] = level
        order = [(r.severity.level, r.address[-6:]) for r in evidence(report).resources]
        self.assertEqual(order, [("CRITICAL", '"r01"]'), ("HIGH", '"r03"]'), ("LOW", '"r00"]'), ("LOW", '"r02"]')])


# --------------------------------------------------------------------------- rendering

def strip_code_spans(line: str) -> str:
    out, i = [], 0
    while i < len(line):
        if line[i] != "`":
            out.append(line[i])
            i += 1
            continue
        j = i
        while j < len(line) and line[j] == "`":
            j += 1
        n, k, found = j - i, j, -1
        while True:
            m = line.find("`" * n, k)
            if m < 0:
                break
            e = m
            while e < len(line) and line[e] == "`":
                e += 1
            if e - m == n:
                found = m
                break
            k = e
        if found < 0:
            out.append(line[i:j])
            i = j
        else:
            out.append("\u00a7CODE\u00a7")
            i = found + n
    return "".join(out)


class RenderingTests(_Base):
    def render(self, report: dict, repository: str | None = REPO):
        ev = evidence(report)
        return [ga.render_issue(ev, r, repository) for r in ev.resources]

    def assert_inert(self, rendered):
        lines = rendered.body.split("\n")
        self.assertTrue(lines[0].startswith("<!-- drift-issue v=1 fp="))
        self.assertTrue(ga._MARKER_RE.match(lines[0]))
        run_lines = [ln for ln in lines if ln.startswith("Content last changed by detection run ")]
        self.assertEqual(len(run_lines), 1)
        for line in lines[1:]:
            self.assertFalse(line.startswith("<!--"))
            if line in run_lines:
                continue
            outside = strip_code_spans(line)
            for token in ("@", "<", ">", "http", "www", "](", "&"):
                self.assertNotIn(token, outside, line)
            self.assertIsNone(re.search(r"#\d", outside), line)
            self.assertFalse(outside.startswith("#") and not outside.startswith(("## ", "### ")), line)
        for text in (rendered.title, rendered.body):
            self.assertIsNone(ga._GUID_RE.search(text))
            self.assertNotIn("/subscriptions/", text.lower())
            self.assertFalse(any(unicodedata.category(ch) in ga._STRIP_CATEGORIES and ch != "\n" for ch in text))
            self.assertNotIn("alice", text)

    def test_full_body_for_low_tag_drift(self):
        (rendered,) = self.render(lowest_report())
        self.assertIn("### Changed paths (1)", rendered.body)
        self.assertIn("- `tags.probe`: class `drifted`; state `value`, real `absent`, desired `value`", rendered.body)
        self.assertEqual(rendered.title, 'Drift detected: module.resource_group.azurerm_resource_group.this["main"] (dev)')
        self.assert_inert(rendered)

    def test_reduced_body_rules(self):
        cases = {
            "nsg_tags_only": "reduced",           # LOW, but a security-sensitive type
            "nsg_open_inbound": "reduced",        # CRITICAL
            "storage_tls_https_downgrade": "reduced",
            "web_app_secret_changed": "reduced",  # redacted, HIGH
            "unconfigured_attribute_drift": "reduced",  # MEDIUM
            "noise_only_drift": "reduced",        # INFO, but a storage account (security-sensitive type)
            "policy_like_tag": "reduced",         # LOW storage account
            "converged_drift": "full",            # LOW resource group
        }
        for name, expected in cases.items():
            with self.subTest(name):
                for rendered in self.render(fixture_report(name)):
                    full = "### Changed paths" in rendered.body
                    self.assertEqual("full" if full else "reduced", expected)
                    if not full:
                        self.assertIn("### Details withheld", rendered.body)
                        self.assertNotIn("- `", rendered.body.split("### Details withheld", 1)[1])
                    self.assert_inert(rendered)

    def test_level_rule_on_non_sensitive_type(self):
        for level, expected in (("INFO", True), ("LOW", True), ("MEDIUM", False), ("HIGH", False), ("CRITICAL", False)):
            with self.subTest(level=level):
                report = lowest_report()
                report["resources"][0]["severity"]["level"] = level
                (rendered,) = self.render(report)
                self.assertEqual("### Changed paths" in rendered.body, expected)

    def test_redacted_change_on_low_resource_is_reduced(self):
        for flag, view in ((True, False), (False, True)):
            with self.subTest(flag=flag, view=view):
                report = lowest_report()
                change = report["resources"][0]["attribute_changes"][0]
                change["redacted"] = flag
                if view:
                    change["real"] = {"status": "redacted"}
                (rendered,) = self.render(report)
                self.assertIn("### Details withheld", rendered.body)

    def test_values_and_reasons_are_never_rendered(self):
        report = many_resources(lowest_report(), 2)
        for item in report["resources"]:
            item["severity"]["reasons"] = ["SENTINEL-REASON tags.probe: tags"]
            change = item["attribute_changes"][0]
            change["state"] = {"status": "value", "value": "SENTINEL-STATE"}
            change["real"] = {"status": "value", "value": {"nested": "SENTINEL-REAL"}}
            change["desired"] = {"status": "value", "value": ["SENTINEL-DESIRED"]}
        report["resources"][1]["severity"]["level"] = "HIGH"
        for rendered in self.render(report):
            for text in (rendered.title, rendered.body):
                self.assertNotIn("SENTINEL", text)

    def test_fixture_values_never_appear(self):
        for d in fixture_dirs():
            name = os.path.basename(os.path.normpath(d))
            report = fixture_report(name)
            if report["outcome"] != "succeeded" or not report["has_drift"]:
                continue
            with self.subTest(name):
                for rendered in self.render(report):
                    self.assert_inert(rendered)
                    resource = next(r for r in report["resources"] if r["address"] == rendered.address)
                    for change in resource["attribute_changes"]:
                        for view in (change["state"], change["real"], change["desired"]):
                            value = view.get("value")
                            if isinstance(value, str) and len(value) >= 6 and value not in rendered.address:
                                self.assertNotIn(value, rendered.body)

    def test_hostile_text_is_inert_and_masked(self):
        (rendered,) = self.render(hostile_report())
        self.assert_inert(rendered)
        body = rendered.body
        self.assertIn("- `tags.ok_key`", body)
        self.assertEqual(body.count(f"`tags.{ga.PATH_PLACEHOLDER}`"), 6)
        self.assertIn("- `tags.xy`", body)  # bidi override stripped, the rest is an allowed key
        self.assertNotIn("\u202e", body)
        self.assertIn(" line2", body)  # a line break becomes a space, never joins words
        self.assertIn("<guid>", body)
        self.assertIn("<arm-id>", body)
        self.assertEqual(body.count("<!-- drift-issue"), 2)  # the marker and the inert copy inside a code span
        self.assertTrue(set(rendered.title) <= set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-[]" ():~'))
        self.assertLessEqual(len(rendered.title), ga.MAX_TITLE)

    def test_code_span_fence_and_padding(self):
        self.assertEqual(ga.code("a"), "`a`")
        self.assertEqual(ga.code("a`b"), "``a`b``")
        self.assertEqual(ga.code("`x``"), "``` `x`` ```")
        self.assertEqual(ga.code(""), "`   `")  # all-space content is not stripped by GFM
        for text in ("a`b", "`x``", "```", "`` a"):
            span = ga.code(text)
            self.assertEqual(strip_code_spans(span), "\u00a7CODE\u00a7")

    def test_long_title_is_truncated_deterministically(self):
        report = lowest_report()
        report["resources"][0]["address"] = "module.m." + "x" * 400
        (rendered,) = self.render(report)
        self.assertEqual(len(rendered.title), ga.MAX_TITLE)
        self.assertTrue(rendered.title.endswith("~" + rendered.fingerprint[:12]))
        self.assertEqual(rendered, self.render(report)[0])

    def test_path_cap(self):
        report = lowest_report()
        change = report["resources"][0]["attribute_changes"][0]
        report["resources"][0]["attribute_changes"] = []
        for i in range(ga.MAX_PATHS + 10):
            item = copy.deepcopy(change)
            item["path"] = ["tags", f"k{i:03d}"]
            report["resources"][0]["attribute_changes"].append(item)
        (rendered,) = self.render(report)
        self.assertEqual(rendered.body.count("\n- `tags.k"), ga.MAX_PATHS)
        self.assertIn("- …and 10 more", rendered.body)
        self.assertIn(f"### Changed paths ({ga.MAX_PATHS + 10})", rendered.body)

    def test_determinism_and_content_hash(self):
        report = many_resources(lowest_report(), 3)
        first = self.render(report)
        shuffled = copy.deepcopy(report)
        shuffled["resources"].reverse()
        for change_list in (r["attribute_changes"] for r in shuffled["resources"]):
            change_list.reverse()
        self.assertEqual(sorted(first, key=lambda r: r.address), sorted(self.render(shuffled), key=lambda r: r.address))
        # run-specific data changes the body but not the content hash
        other = copy.deepcopy(report)
        other["run"]["run_id"] = "github-999-3"
        other["plan"]["timestamp"] = "2026-10-04T10:00:00Z"
        for a, b in zip(first, self.render(other)):
            self.assertEqual((a.content_hash, a.title, a.fingerprint), (b.content_hash, b.title, b.fingerprint))
            self.assertNotEqual(a.body, b.body)
        # content changes change the hash
        changed = copy.deepcopy(report)
        changed["resources"][0]["severity"]["level"] = "INFO"
        self.assertNotEqual(first[0].content_hash, self.render(changed)[0].content_hash)
        # no repository: no link
        (unlinked,) = self.render(lowest_report(), repository=None)
        self.assertNotIn("https://", unlinked.body)

    def test_fingerprint_and_marker(self):
        fp = ga.fingerprint("dev", "a.b")
        self.assertEqual(fp, ga.fingerprint("dev", "a.b"))
        self.assertNotEqual(fp, ga.fingerprint("prod", "a.b"))
        self.assertNotEqual(fp, ga.fingerprint("dev", "a.c"))
        self.assertRegex(fp, r"^[0-9a-f]{64}$")
        line = ga.marker_line(fp, "c" * 64, RUN, "2026-10-03T10:00:00Z")
        marker = ga.parse_marker(line + "\nrest")
        self.assertEqual(marker, ga.Marker(1, fp, "c" * 64, RUN, "2026-10-03T10:00:00Z"))
        self.assertIsNone(ga.run_url("bad repo", RUN))
        self.assertIsNone(ga.run_url(REPO, "local-1"))


# --------------------------------------------------------------------------- marker semantics

class MarkerSemanticsTests(_Base):
    def setUp(self):
        super().setUp()
        self.ev = evidence(lowest_report(plan_ts="2026-10-03T10:00:00Z"))
        self.rendered = ga.render_issue(self.ev, self.ev.resources[0], REPO)

    def issue(self, *, plan: str, same: bool, number: int = 7, version: int = 1) -> dict:
        content = self.rendered.content_hash if same else "d" * 64
        body = (f"<!-- drift-issue v={version} fp={self.rendered.fingerprint} content={content} "
                f"run=github-100-1 plan={plan} -->\nbody")
        return {"number": number, "body": body}

    def test_matrix(self):
        cases = {
            ("older", True): ("unchanged", None),
            ("older", False): ("refused", "stale_evidence"),
            ("equal", True): ("unchanged", None),
            ("equal", False): ("refused", "conflicting_evidence"),
            ("newer", True): ("unchanged", None),
            ("newer", False): ("update", None),
        }
        marker_ts = {"older": "2026-10-03T10:00:01Z", "equal": "2026-10-03T10:00:00Z", "newer": "2026-10-03T09:59:59Z"}
        for (when, same), (action, code_) in cases.items():
            with self.subTest(evidence=when, same_content=same):
                decision = ga.decide(self.rendered, self.ev, [self.issue(plan=marker_ts[when], same=same)])
                self.assertEqual((decision.action, decision.code, decision.number), (action, code_, 7))

    def test_no_match_creates(self):
        self.assertEqual(ga.decide(self.rendered, self.ev, []), ga.Decision("create", None, None))

    def test_invalid_and_unsupported_markers_fail_closed(self):
        fp = self.rendered.fingerprint
        bodies = {
            f"<!-- drift-issue v=1 fp={fp} content=xyz run=github-1-1 plan=2026-10-03T10:00:00Z -->": "marker_invalid",
            f"<!-- drift-issue v=1 fp={fp} -->": "marker_invalid",
            f"<!-- drift-issue v=1 fp={fp} content={'a' * 64} run=local-1 plan=2026-10-03T10:00:00Z -->": "marker_invalid",
            f"<!-- drift-issue v=2 fp={fp} content={'a' * 64} run=github-1-1 plan=2026-10-03T10:00:00Z -->":
                "marker_version_unsupported",
            f"<!-- drift-issue fp={fp} content={'a' * 64} -->": "marker_invalid",
        }
        for body, code_ in bodies.items():
            with self.subTest(body=body[:40]):
                decision = ga.decide(self.rendered, self.ev, [{"number": 3, "body": body}])
                self.assertEqual((decision.action, decision.code), ("refused", code_))
        # one bad marker among duplicates still refuses
        good = self.issue(plan="2026-10-03T09:00:00Z", same=False, number=2)
        decision = ga.decide(self.rendered, self.ev, [good, {"number": 3, "body": list(bodies)[0]}])
        self.assertEqual((decision.action, decision.code), ("refused", "marker_invalid"))

    def test_marker_must_be_the_first_line(self):
        fp = self.rendered.fingerprint
        line = ga.marker_line(fp, "a" * 64, RUN, "2026-10-03T10:00:00Z")
        self.assertEqual(ga.marker_fingerprint(line + "\nx"), ("1", fp))
        self.assertEqual(ga.marker_fingerprint(line + "\r\nx"), ("1", fp))
        for body in ("x\n" + line, " " + line, f"`{line}`", None, 42, ""):
            with self.subTest(body=repr(body)[:30]):
                self.assertEqual(ga.marker_fingerprint(body), (None, None))
        self.assertEqual(ga.marker_fingerprint("<!-- drift-issue nothing -->"), (None, None))

    def test_duplicates_update_lowest_number(self):
        issues = [self.issue(plan="2026-10-02T00:00:00Z", same=False, number=n) for n in (9, 4, 6)]
        for item in issues:
            item.update(state="open", user=dict(BOT), labels=[{"name": ga.LABEL}])
        matches = ga.matching_issues(issues, self.rendered.fingerprint)
        self.assertEqual([m["number"] for m in matches], [4, 6, 9])
        decision = ga.decide(self.rendered, self.ev, matches)
        self.assertEqual((decision.action, decision.number, decision.duplicates), ("update", 4, True))


class SpoofingTests(_Base):
    def base(self) -> dict:
        return {"number": 1, "state": "open", "user": dict(BOT), "labels": [{"name": ga.LABEL}], "body": "x"}

    def test_only_bot_created_labelled_open_issues_match(self):
        self.assertTrue(ga.is_automation_issue(self.base()))
        mutations = {
            "pull-request": lambda i: i.update(pull_request={"url": "x"}),
            "closed": lambda i: i.update(state="closed"),
            "human-author": lambda i: i.update(user={"login": "octocat", "type": "User"}),
            "user-named-like-bot": lambda i: i.update(user={"login": "github-actions[bot]", "type": "User"}),
            "other-bot": lambda i: i.update(user={"login": "dependabot[bot]", "type": "Bot"}),
            "no-user": lambda i: i.update(user=None),
            "no-label": lambda i: i.update(labels=[]),
            "other-label": lambda i: i.update(labels=[{"name": "drift-detected-x"}]),
            "labels-not-list": lambda i: i.update(labels="drift-detected"),
            "label-not-dict": lambda i: i.update(labels=["drift-detected"]),
            "number-bool": lambda i: i.update(number=True),
            "number-str": lambda i: i.update(number="1"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name):
                item = self.base()
                mutate(item)
                self.assertFalse(ga.is_automation_issue(item))
        self.assertFalse(ga.is_automation_issue("not a dict"))


# --------------------------------------------------------------------------- end to end with the fake API

class PublishTests(_Base):
    def test_create_then_idempotent_then_update(self):
        fake = FakeGitHub()
        result = self.publish(lowest_report(plan_ts="2026-10-03T10:00:00Z"), fake)
        self.assertEqual((result.outcome, result.created, result.codes), ("ok", [1], []))
        methods = [m for m, _, _ in fake.requests]
        self.assertEqual(methods, ["GET", "GET", "POST"])
        post = fake.requests[-1][2]
        self.assertEqual(sorted(post), ["body", "labels", "title"])
        self.assertEqual(post["labels"], [ga.LABEL])
        list_query = parse_qs(urlsplit(fake.requests[1][1]).query)
        self.assertEqual((list_query["state"], list_query["labels"], list_query["creator"]),
                         (["open"], [ga.LABEL], ["github-actions[bot]"]))
        # same evidence again (duplicate delivery) -> unchanged, no write
        result = self.publish(lowest_report(plan_ts="2026-10-03T10:00:00Z"), fake)
        self.assertEqual((result.unchanged, fake.count("POST"), fake.count("PATCH")), ([1], 1, 0))
        # newer evidence, identical content -> unchanged, marker not advanced
        newer = lowest_report(plan_ts="2026-10-04T10:00:00Z")
        newer["run"]["run_id"] = "github-123-1"
        result = self.publish(newer, fake)
        self.assertEqual((result.unchanged, fake.count("PATCH")), ([1], 0))
        self.assertIn("plan=2026-10-03T10:00:00Z", fake.issues[1]["body"].split("\n")[0])
        # newer evidence, different content -> PATCH title and body only
        changed = lowest_report(plan_ts="2026-10-05T10:00:00Z")
        changed["resources"][0]["severity"]["level"] = "INFO"
        result = self.publish(changed, fake)
        self.assertEqual((result.updated, fake.count("PATCH")), ([1], 1))
        patch = [p for m, _, p in fake.requests if m == "PATCH"][0]
        self.assertEqual(sorted(patch), ["body", "title"])
        self.assertIn("plan=2026-10-05T10:00:00Z", fake.issues[1]["body"].split("\n")[0])
        # older evidence with different content -> stale, no write
        stale = lowest_report(plan_ts="2026-10-04T12:00:00Z")
        result = self.publish(stale, fake)
        self.assertEqual((result.codes, result.outcome, fake.count("PATCH")), (["stale_evidence"], "failed", 1))
        self.assertEqual(len(fake.issues), 1)

    def test_headers_and_token(self):
        fake = FakeGitHub()
        self.publish(lowest_report(), fake)
        for headers in fake.headers:
            self.assertEqual(headers["Authorization"], f"Bearer {TOKEN}")
            self.assertEqual(headers["Accept"], "application/vnd.github+json")
            self.assertEqual(headers["X-github-api-version"], ga.API_VERSION)
        for _, url, _ in fake.requests:
            self.assertTrue(url.startswith(f"{API}/repos/{REPO}/"))
        client = ga.GitHubClient(TOKEN, REPO, opener=fake)
        self.assertNotIn(TOKEN, repr(client))
        with self.assertRaises(ga.AutomationError) as ctx:
            ga.GitHubClient(TOKEN, "not a repo")
        self.assertEqual(ctx.exception.code, "repository_invalid")

    def test_spoofed_and_unrelated_issues_are_ignored_and_never_touched(self):
        fake = FakeGitHub()
        ev = evidence(lowest_report())
        fp = ga.render_issue(ev, ev.resources[0], REPO).fingerprint
        marker = ga.marker_line(fp, "a" * 64, "github-1-1", "2026-10-01T00:00:00Z")
        fake.add_issue(marker, user={"login": "mallory", "type": "User"})
        fake.add_issue(marker, labels=())
        fake.add_issue(marker, pr=True)
        fake.add_issue(marker, state="closed")
        fake.add_issue("x\n" + marker)
        fake.add_issue(ga.marker_line("b" * 64, "a" * 64, "github-1-1", "2026-10-01T00:00:00Z"))
        before = copy.deepcopy(fake.issues)
        result = self.publish(lowest_report(), fake)
        # the bot-owned issue for another fingerprint is a Task 8.3 warning, never written
        self.assertEqual((result.created, result.codes, result.outcome), ([7], ["resource_not_in_report"], "ok"))
        for n, item in before.items():
            self.assertEqual(fake.issues[n], item)
        self.assertEqual(fake.count("PATCH"), 0)

    def test_duplicates_warn_and_update_lowest(self):
        fake = FakeGitHub()
        ev = evidence(lowest_report())
        fp = ga.render_issue(ev, ev.resources[0], REPO).fingerprint
        for n in (5, 3):
            fake.add_issue(ga.marker_line(fp, "a" * 64, "github-1-1", "2026-10-01T00:00:00Z"), number=n)
        result = self.publish(lowest_report(), fake)
        self.assertEqual((result.updated, result.codes, result.outcome), ([3], ["duplicate_issues"], "ok"))
        self.assertIn("github-1-1", fake.issues[5]["body"])

    def test_invalid_marker_blocks_create_and_patch(self):
        fake = FakeGitHub()
        ev = evidence(lowest_report())
        fp = ga.render_issue(ev, ev.resources[0], REPO).fingerprint
        fake.add_issue(f"<!-- drift-issue v=1 fp={fp} broken -->")
        result = self.publish(lowest_report(), fake)
        self.assertEqual((result.codes, result.outcome), (["marker_invalid"], "failed"))
        self.assertEqual((fake.count("POST"), fake.count("PATCH")), (0, 0))

    def test_label_must_exist(self):
        fake = FakeGitHub(labels=())
        result = self.publish(lowest_report(), fake)
        self.assertEqual(result.codes, ["label_missing"])
        self.assertEqual([m for m, _, _ in fake.requests], ["GET"])
        fake = FakeGitHub()
        fake.fail("label", FakeResponse(200, {"name": "other"}))
        self.assertEqual(self.publish(lowest_report(), fake).codes, ["label_missing"])

    def test_pagination(self):
        fake = FakeGitHub(page_size=2)
        ev = evidence(lowest_report())
        fp = ga.render_issue(ev, ev.resources[0], REPO).fingerprint
        for _ in range(5):
            fake.add_issue("unrelated")
        n = fake.add_issue(ga.marker_line(fp, "a" * 64, "github-1-1", "2026-10-01T00:00:00Z"))
        result = self.publish(lowest_report(), fake)
        self.assertEqual((result.updated, result.created), ([n], []))
        self.assertEqual(sum(1 for m, u, _ in fake.requests if m == "GET" and "/issues" in u), 3)

    def test_next_link_validation(self):
        for base, ok in ((f"{API}/repos/{REPO}/issues", True), (f"{API}/repositories/99/issues", True),
                         ("https://evil.example/repositories/1/issues", False), (f"http://api.github.com/repos/{REPO}/issues", False),
                         (f"{API}/repos/other/repo/issues", False), (f"{API}/repositories/1/pulls", False),
                         ("https://user@api.github.com/repositories/1/issues", False)):
            with self.subTest(base=base):
                fake = FakeGitHub(page_size=1, next_base=base)
                fake.add_issue("a")
                fake.add_issue("b")
                result = self.publish(lowest_report(), fake)
                self.assertEqual(result.codes, [] if ok else ["blocked_request"])
                if not ok:
                    self.assertEqual(fake.count("POST"), 0)
        client = ga.GitHubClient(TOKEN, REPO, opener=FakeGitHub())
        with self.assertRaises(ga.AutomationError):
            client.request("GET", "", url=f"{API}/repos/{REPO}/issues#frag")
        with self.assertRaises(ga.AutomationError) as ctx:
            client.request("GET", "evil.example/x")
        self.assertEqual(ctx.exception.code, "blocked_request")
        self.assertEqual(ga._next_link('<a>; rel="prev", <b>; rel="next"'), "b")
        self.assertIsNone(ga._next_link(""))

    def test_pagination_limit(self):
        fake = FakeGitHub(page_size=1)
        for _ in range(ga.MAX_PAGES + 1):
            fake.add_issue("x")
        result = self.publish(lowest_report(), fake)
        self.assertEqual(result.codes, ["pagination_limit"])
        self.assertEqual(fake.count("POST"), 0)
        fake = FakeGitHub(page_size=1)
        for _ in range(ga.MAX_PAGES):
            fake.add_issue("x")
        self.assertEqual(self.publish(lowest_report(), fake).codes, [])

    def test_per_run_cap(self):
        fake = FakeGitHub()
        result = self.publish(many_resources(lowest_report(), ga.MAX_WRITES_PER_RUN + 2), fake)
        self.assertEqual((len(result.created), result.not_processed, result.codes, result.outcome),
                         (ga.MAX_WRITES_PER_RUN, 2, ["cap_exceeded"], "failed"))
        created_titles = sorted(item["title"] for item in fake.issues.values())
        self.assertTrue(created_titles[-1].endswith('this["r09"] (dev)'))
        # a later run creates the rest; unchanged issues do not count against the cap
        later = many_resources(lowest_report(), ga.MAX_WRITES_PER_RUN + 2)
        result = self.publish(later, fake)
        self.assertEqual((len(result.created), len(result.unchanged), result.codes), (2, 10, []))

    def test_no_caller_or_phase7_input_can_reach_output(self):
        report = lowest_report()
        path = self.write_report(report)
        caller = "alice.caller@example.com"
        with open(os.path.join(self.tmp, "drift_attribution.json"), "w") as fh:
            json.dump({"resources": [{"address": report["resources"][0]["address"], "attribution": {
                "status": "confirmed", "caller": caller}}]}, fh)
        with open(os.path.join(self.tmp, "activity_log_evidence.json"), "w") as fh:
            json.dump({"events": [{"caller": caller}]}, fh)
        fake_with, fake_without = FakeGitHub(), FakeGitHub()
        ga.run(args_for(path), ENV, self.client_factory(fake_with))
        other = tempfile.mkdtemp(prefix="gh-issues-clean-")
        self.addCleanup(lambda: __import__("shutil").rmtree(other, ignore_errors=True))
        clean_path = os.path.join(other, "drift_report.json")
        with open(clean_path, "w") as fh:
            json.dump(report, fh)
        ga.run(args_for(clean_path), ENV, self.client_factory(fake_without))
        self.assertEqual(fake_with.requests, fake_without.requests)
        self.assertNotIn(caller, json.dumps(fake_with.requests))
        self.assertNotIn("alice", json.dumps(fake_with.requests))


class ClientErrorTests(_Base):
    def client(self, fake):
        return ga.GitHubClient(TOKEN, REPO, opener=fake, sleep=self.sleeps.append)

    def code_of(self, fn):
        with self.assertRaises(ga.AutomationError) as ctx:
            fn()
        return ctx.exception.code

    def test_status_codes(self):
        cases = {401: "auth_failed", 403: "forbidden", 404: "not_found", 410: "gone", 422: "validation_failed",
                 418: "http_error", 301: "blocked_request"}
        for status, code_ in cases.items():
            with self.subTest(status=status):
                fake = FakeGitHub()
                fake.fail("create", status)
                self.assertEqual(self.code_of(lambda: self.client(fake).create_issue("t", "b")), code_)
                self.assertEqual(fake.count("POST"), 1)

    def test_rate_limits(self):
        for headers in ({"X-RateLimit-Remaining": "0"}, {"Retry-After": "30"}):
            with self.subTest(headers=headers):
                fake = FakeGitHub()
                fake.fail("list", (403, headers))
                self.assertEqual(self.code_of(lambda: self.client(fake).open_automation_issues()), "rate_limited")
                self.assertEqual(fake.count("GET"), 1)  # no retry on a 403 rate limit
        fake = FakeGitHub()
        fake.fail("list", (429, {"Retry-After": "120"}), (429, {"Retry-After": "5"}))
        self.assertEqual(self.client(fake).open_automation_issues(), [])
        self.assertEqual(self.sleeps, [ga.RETRY_AFTER_CAP, 5.0])
        fake = FakeGitHub()
        fake.fail("list", 429, 429, 429)
        self.assertEqual(self.code_of(lambda: self.client(fake).open_automation_issues()), "rate_limited")
        self.assertEqual(fake.count("GET"), ga.MAX_ATTEMPTS)

    def test_get_and_patch_retry_post_never(self):
        fake = FakeGitHub()
        fake.fail("label", 502, 503)
        self.assertTrue(self.client(fake).label_exists(ga.LABEL))
        self.assertEqual(fake.count("GET"), 3)
        self.assertEqual(self.sleeps, [1.0, 2.0])
        fake = FakeGitHub()
        fake.fail("label", 500, 500, 500)
        self.assertEqual(self.code_of(lambda: self.client(fake).label_exists(ga.LABEL)), "server_error")
        fake = FakeGitHub()
        fake.add_issue("x")
        fake.fail("update", 502)
        self.assertEqual(self.client(fake).update_issue(1, "t", "b"), 1)
        self.assertEqual(fake.count("PATCH"), 2)
        for failure, code_ in ((502, "server_error"), (TimeoutError(), "timeout"),
                               (urllib.error.URLError(TimeoutError()), "timeout"),
                               (urllib.error.URLError("refused"), "connection_failed"), (429, "rate_limited")):
            with self.subTest(failure=repr(failure)):
                fake = FakeGitHub()
                fake.fail("create", failure)
                self.assertEqual(self.code_of(lambda: self.client(fake).create_issue("t", "b")), code_)
                self.assertEqual(fake.count("POST"), 1)

    def test_transport_errors_on_get(self):
        for failure, code_ in ((TimeoutError(), "timeout"), (urllib.error.URLError("x"), "connection_failed"),
                               (ConnectionResetError(), "connection_failed")):
            with self.subTest(failure=repr(failure)):
                fake = FakeGitHub()
                fake.fail("label", failure, failure, failure)
                self.assertEqual(self.code_of(lambda: self.client(fake).label_exists(ga.LABEL)), code_)
                self.assertEqual(fake.count("GET"), ga.MAX_ATTEMPTS)

    def test_invalid_responses(self):
        cases = {
            "not-json": ("label", FakeResponse(200, None, raw=b"{oops")),
            "too-big": ("label", FakeResponse(200, None, raw=b"x" * (ga.MAX_RESPONSE_BYTES + 1))),
            "empty-list-body": ("list", FakeResponse(204, None)),
            "non-2xx": ("label", FakeResponse(302, {"name": ga.LABEL})),
            "list-not-array": ("list", FakeResponse(200, {"items": []})),
            "create-no-number": ("create", FakeResponse(201, {"id": 1})),
            "create-bool-number": ("create", FakeResponse(201, {"number": True})),
        }
        for name, (kind, response) in cases.items():
            with self.subTest(name):
                fake = FakeGitHub()
                fake.fail(kind, response)
                client = self.client(fake)
                call = {"label": lambda: client.label_exists(ga.LABEL), "list": client.open_automation_issues,
                        "create": lambda: client.create_issue("t", "b")}[kind]
                self.assertEqual(self.code_of(call), "invalid_response")

    def test_label_404_means_missing_other_errors_raise(self):
        fake = FakeGitHub(labels=())
        self.assertFalse(self.client(fake).label_exists(ga.LABEL))
        fake = FakeGitHub()
        fake.fail("label", 401)
        self.assertEqual(self.code_of(lambda: self.client(fake).label_exists(ga.LABEL)), "auth_failed")

    def test_api_failure_reports_code_and_stops(self):
        fake = FakeGitHub()
        fake.fail("create", 422)
        result = self.publish(many_resources(lowest_report(), 3), fake)
        self.assertEqual((result.codes, result.outcome, fake.count("POST")), (["validation_failed"], "failed", 1))

    def test_no_redirect_handler(self):
        handler = ga.GitHubClient._NoRedirect()
        req = urllib.request.Request(f"{API}/x")
        self.assertIsNone(handler.redirect_request(req, None, 302, "Found", {}, "https://evil.example/"))
        client = ga.GitHubClient(TOKEN, REPO)
        self.assertTrue(any(isinstance(h, ga.GitHubClient._NoRedirect) for h in client._opener.handlers))

    def test_delay(self):
        self.assertEqual(ga.GitHubClient._delay({"retry-after": "7"}, 1), 7.0)
        self.assertEqual(ga.GitHubClient._delay({"retry-after": "999"}, 1), ga.RETRY_AFTER_CAP)
        self.assertEqual(ga.GitHubClient._delay({"retry-after": "soon"}, 3), 4.0)


# --------------------------------------------------------------------------- CLI, dry-run, summary

class CliTests(_Base):
    def main(self, argv, env=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = ga.main(argv, env if env is not None else {})
        return rc, out.getvalue(), err.getvalue()

    def test_dry_run_writes_reviewable_requests_without_network(self):
        report = self.write_report(many_resources(lowest_report(), 2))
        out_dir = os.path.join(self.tmp, "preview")
        rc, out, _ = self.main(["--report", report, "--environment", "dev", "--drift-detected", "true",
                                "--out-dir", out_dir, "--repository", REPO])
        self.assertEqual(rc, 0)
        summary = json.loads(out)
        self.assertEqual((summary["mode"], summary["planned"], summary["outcome"]), ("dry_run", 2, "ok"))
        self.assertEqual(sorted(os.listdir(out_dir)), ["issue-001.md", "issue-002.md", "requests.json"])
        with open(os.path.join(out_dir, "requests.json")) as fh:
            requests = json.load(fh)
        self.assertEqual([r["method"] for r in requests], ["POST", "POST"])
        self.assertIn(f"https://github.com/{REPO}/actions/runs/123/attempts/1", requests[0]["payload"]["body"])
        first = open(os.path.join(out_dir, "requests.json")).read()
        out2 = os.path.join(self.tmp, "preview2")
        self.main(["--report", report, "--environment", "dev", "--drift-detected", "true", "--out-dir", out2,
                   "--repository", REPO])
        self.assertEqual(first, open(os.path.join(out2, "requests.json")).read())
        # repository from the environment; no repository -> no link
        out3 = os.path.join(self.tmp, "preview3")
        self.main(["--report", report, "--environment", "dev", "--drift-detected", "true", "--out-dir", out3])
        self.assertNotIn("https://", open(os.path.join(out3, "requests.json")).read())

    def test_dry_run_output_dir_rules(self):
        report = self.write_report(lowest_report())
        busy = os.path.join(self.tmp, "busy")
        os.makedirs(busy)
        open(os.path.join(busy, "old.md"), "w").close()
        rc, out, _ = self.main(["--report", report, "--environment", "dev", "--drift-detected", "true", "--out-dir", busy])
        self.assertEqual((rc, json.loads(out)["codes"]), (1, ["out_dir_not_empty"]))
        blocker = os.path.join(self.tmp, "file")
        open(blocker, "w").close()
        rc, out, _ = self.main(["--report", report, "--environment", "dev", "--drift-detected", "true",
                                "--out-dir", os.path.join(blocker, "sub")])
        self.assertEqual((rc, json.loads(out)["codes"]), (1, ["out_dir_unwritable"]))
        rc, out, _ = self.main(["--report", report, "--environment", "dev", "--drift-detected", "true",
                                "--out-dir", os.path.join(self.tmp, "x"), "--repository", "bad/repo/x"])
        self.assertEqual((rc, json.loads(out)["codes"]), (1, ["repository_invalid"]))

    def test_publish_outside_actions_is_refused(self):
        report = self.write_report(lowest_report())
        rc, out, _ = self.main(["--report", report, "--environment", "dev", "--drift-detected", "true", "--publish"],
                               env={k: v for k, v in ENV.items() if k != "GITHUB_ACTIONS"})
        self.assertEqual((rc, json.loads(out)["codes"]), (1, ["publish_outside_actions"]))

    def test_usage_errors(self):
        for argv in ([], ["--report", "x", "--environment", "dev", "--drift-detected", "true"],
                     ["--report", "x", "--environment", "dev", "--drift-detected", "true", "--publish", "--out-dir", "d"]):
            with self.subTest(argv=argv):
                rc, _, _ = self.main(argv)
                self.assertEqual(rc, 2)
        rc, out, _ = self.main(["--help"])
        self.assertEqual(rc, 0)
        self.assertIn("--publish", out)

    def test_skip_exit_zero_and_internal_error(self):
        rc, out, _ = self.main(["--report", "x", "--environment", "dev", "--drift-detected", "unknown", "--publish"], env=ENV)
        self.assertEqual((rc, json.loads(out)["outcome"]), (0, "skipped"))
        original = ga.run
        ga.run = lambda *a, **k: (_ for _ in ()).throw(RuntimeError(TOKEN))
        try:
            rc, out, err = self.main(["--report", "x", "--environment", "dev", "--drift-detected", "true", "--publish"], env=ENV)
        finally:
            ga.run = original
        self.assertEqual(rc, 70)
        self.assertNotIn(TOKEN, out + err)
        self.assertIn("internal error (RuntimeError)", err)

    def test_publish_through_main_writes_step_summary_and_never_prints_token(self):
        report = self.write_report(lowest_report())
        summary_path = os.path.join(self.tmp, "summary.md")
        fake = FakeGitHub()
        fake.fail("create", 502)
        original = ga.GitHubClient
        ga.GitHubClient = lambda token, repo: original(token, repo, opener=fake, sleep=self.sleeps.append)
        try:
            rc, out, err = self.main(["--report", report, "--environment", "dev", "--drift-detected", "true", "--publish"],
                                     env=dict(ENV, GITHUB_STEP_SUMMARY=summary_path))
        finally:
            ga.GitHubClient = original
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out)["codes"], ["server_error"])
        text = open(summary_path).read()
        self.assertIn("`server_error`", text)
        self.assertNotIn(TOKEN, out + err + text)
        self.assertNotIn("Drift detected:", text)  # counts and codes only
        # dry-run never writes the step summary
        rc, _, _ = self.main(["--report", report, "--environment", "dev", "--drift-detected", "true",
                              "--out-dir", os.path.join(self.tmp, "p")], env={"GITHUB_STEP_SUMMARY": summary_path})
        self.assertEqual(open(summary_path).read(), text)
        # a successful publish lists "none" for codes
        fake2 = FakeGitHub()
        ga.GitHubClient = lambda token, repo: original(token, repo, opener=fake2)
        try:
            rc, _, _ = self.main(["--report", report, "--environment", "dev", "--drift-detected", "true", "--publish"],
                                 env=dict(ENV, GITHUB_STEP_SUMMARY=summary_path))
        finally:
            ga.GitHubClient = original
        self.assertEqual(rc, 0)
        self.assertIn("Codes: none", open(summary_path).read())

    def test_write_atomic_cleans_up_on_failure(self):
        target = os.path.join(self.tmp, "out.txt")
        with self.assertRaises(TypeError):
            ga._write_atomic(target, None)
        self.assertEqual(os.listdir(self.tmp), [])

    def test_result_codes_are_unique_and_ordered(self):
        result = ga.Result("publish")
        for code_ in ("duplicate_issues", "stale_evidence", "duplicate_issues"):
            result.add(code_)
        self.assertEqual(result.codes, ["duplicate_issues", "stale_evidence"])
        self.assertEqual(result.outcome, "failed")

    def test_source_tree_import_fallback(self):
        import builtins
        real_import = builtins.__import__
        calls = []

        def flaky(name, *args, **kwargs):
            if name == "drift_engine.models" and not calls:
                calls.append(name)
                raise ImportError("simulated: package not installed")
            return real_import(name, *args, **kwargs)

        spec = importlib.util.spec_from_file_location("_github_automation_fallback", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        saved_path = list(sys.path)
        sys.modules[spec.name] = module
        builtins.__import__ = flaky
        try:
            spec.loader.exec_module(module)
        finally:
            builtins.__import__ = real_import
            sys.path[:] = saved_path
            sys.modules.pop(spec.name, None)
        self.assertEqual(calls, ["drift_engine.models"])
        self.assertIs(module.DriftReport, ga.DriftReport)

    def test_automation_error_rejects_unknown_codes(self):
        with self.assertRaises(AssertionError):
            ga.AutomationError("made_up")


# --------------------------------------------------------------------------- boundaries

class BoundaryTests(unittest.TestCase):
    FORBIDDEN = ("ai_engine", "drift_engine.activity_logs", "drift_engine.attribution", "azure", "openai",
                 "langchain", "langgraph", "github", "requests")

    def test_import_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = fixture_report("external_drift")
            path = os.path.join(tmp, "r.json")
            with open(path, "w") as fh:
                json.dump(report, fh)
            code_ = (
                "import runpy, sys, json\n"
                f"sys.argv = ['github_automation.py', '--report', {path!r}, '--environment', 'dev', "
                f"'--drift-detected', 'true', '--out-dir', {os.path.join(tmp, 'out')!r}]\n"
                "try:\n"
                f"    runpy.run_path({SCRIPT!r}, run_name='__main__')\n"
                "except SystemExit as exc:\n"
                "    assert exc.code == 0, exc.code\n"
                "print(json.dumps(sorted(sys.modules)), file=sys.stderr)\n"
            )
            proc = subprocess.run([sys.executable, "-c", code_], capture_output=True, text=True, timeout=120)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            loaded = json.loads(proc.stderr.strip().splitlines()[-1])
        for prefix in self.FORBIDDEN:
            self.assertFalse([m for m in loaded if m == prefix or m.startswith(prefix + ".")], prefix)

    def test_network_code_only_in_client_class(self):
        with open(SCRIPT, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        client = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GitHubClient")
        inside = {id(n) for n in ast.walk(client)}
        network_modules = ("urllib", "http", "socket", "ssl", "requests", "subprocess", "github")
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                if name.split(".")[0] in network_modules:
                    self.assertIn(id(node), inside, name)
                    self.assertNotIn(name.split(".")[0], ("socket", "ssl", "requests", "subprocess", "github", "http"))
        imported = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        imported += [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertEqual(sorted(m for m in imported if m.startswith("drift_engine")),
                         ["drift_engine.models", "drift_engine.models", "drift_engine.severity", "drift_engine.severity"])
        for name in ("ai_engine", "activity_logs", "attribution"):
            self.assertFalse([m for m in imported if name in m], name)


class WorkflowStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW, encoding="utf-8") as fh:
            cls.text = fh.read()
        cls.wf = yaml.safe_load(cls.text)
        cls.jobs = cls.wf["jobs"]
        cls.job = cls.jobs["issues"]

    def test_triggers_permissions_and_concurrency_unchanged(self):
        triggers = self.wf.get("on", self.wf.get(True))
        self.assertEqual(sorted(triggers), ["schedule", "workflow_dispatch"])
        self.assertEqual(self.wf["permissions"], {"id-token": "write", "contents": "read"})
        self.assertEqual(self.wf["concurrency"], {
            "group": "drift-detection-${{ github.event.inputs.environment || 'dev' }}", "cancel-in-progress": False})
        self.assertEqual(sorted(self.jobs), ["issues", "plan-and-analyze", "preflight", "report"])
        for name in ("preflight", "plan-and-analyze", "report"):
            self.assertNotIn("permissions", self.jobs[name])
        self.assertEqual(self.jobs["report"]["needs"], ["preflight", "plan-and-analyze"])

    def test_issues_job(self):
        job = self.job
        self.assertEqual(job["permissions"], {"contents": "read", "issues": "write"})
        self.assertEqual(job["needs"], ["preflight", "plan-and-analyze"])
        self.assertEqual(job["if"], "${{ needs.plan-and-analyze.outputs.drift_detected == 'true' || "
                                    "needs.plan-and-analyze.outputs.drift_detected == 'false' }}")  # Task 8.3
        self.assertNotIn("environment", job)
        self.assertNotIn("continue-on-error", job)
        self.assertNotIn("concurrency", job)
        steps = job["steps"]
        uses = [s.get("uses") for s in steps]
        self.assertEqual(uses, ["actions/checkout@v4", "actions/setup-python@v5", None, "actions/download-artifact@v4", None])
        self.assertEqual(steps[0]["with"], {"persist-credentials": False})
        self.assertEqual(steps[3]["with"]["name"], "drift-report-${{ github.run_id }}")
        for step in steps:
            self.assertNotIn("continue-on-error", step)
            self.assertNotIn("if", step)
            text = json.dumps(step)
            for forbidden in ("azure/login", "ARM_", "id-token", "terraform", "AZURE_", "-auto-approve"):
                self.assertNotIn(forbidden, text)
            if step is not steps[-1]:
                self.assertNotIn("GITHUB_TOKEN", text)
        self.assertEqual(steps[2]["run"].split()[-1], ".")  # core install, no extras
        last = steps[-1]
        self.assertEqual(last["env"]["GITHUB_TOKEN"], "${{ secrets.GITHUB_TOKEN }}")
        self.assertIn("scripts/github_automation.py", last["run"])
        self.assertIn("--publish", last["run"])
        self.assertIn('--drift-detected "${DRIFT_DETECTED}"', last["run"])
        self.assertNotIn("GITHUB_TOKEN", json.dumps(job.get("env", {})))  # token only in the script step
        self.assertEqual(self.text.count("secrets.GITHUB_TOKEN"), 1)
        code_lines = [ln for ln in self.text.splitlines() if not ln.lstrip().startswith("#")]
        self.assertEqual(sum("issues: write" in ln for ln in code_lines), 1)
        self.assertEqual(sum("permissions:" in ln for ln in code_lines), 2)  # workflow default + issues job
        self.assertNotIn("pull_request_target", self.text)
        self.assertNotIn("issue_comment", self.text)


# --------------------------------------------------------------------------- safeguard mutants

MUTANTS = {
    "gate-drift-detected": ('        if args.drift_detected not in ("true", "false"):', '        if False:'),
    "false-run-create-update": ("    if report.has_drift is not drift_detected:\n", "    if False:\n"),
    "gate-environment": ("    if report.run.environment != environment:\n", "    if False:\n"),
    "issue-set": ("    drifted = [r for r in report.resources if r.drift_action is not None]\n",
                  "    drifted = list(report.resources)\n"),
    "binding-exact": ('    if evidence.run_id != f"github-{run_id}-{attempt}":\n',
                      '    if not evidence.run_id.startswith(f"github-{run_id}-"):\n'),
    "publish-in-actions": ('    if env.get("GITHUB_ACTIONS") != "true":\n', "    if False:\n"),
    "author-login": ('user.get("login") != BOT_LOGIN or ', ""),
    "author-type": (' or user.get("type") != BOT_TYPE', ""),
    "label-on-issue": ('    if not isinstance(labels, list) or not any(', '    if False and not any('),
    "open-state": (' or item.get("state") != "open"', ""),
    "pr-filter": (' or "pull_request" in item', ""),
    "marker-first-line": ("    version, fp = _MARKER_VERSION_RE.search(first), _MARKER_FP_RE.search(first)\n",
                          "    version, fp = _MARKER_VERSION_RE.search(body), _MARKER_FP_RE.search(body)\n"),
    "marker-prefix": ("    if not first.startswith(_MARKER_PREFIX):\n        return None, None\n",
                      "    if _MARKER_PREFIX not in body:\n        return None, None\n"),
    "stale-strict": ("    if evidence.plan_timestamp > marker.plan_timestamp:", "    if evidence.plan_timestamp >= marker.plan_timestamp:"),
    "stale-ignored": ("    if evidence.plan_timestamp > marker.plan_timestamp:", "    if True:"),
    "no-edit-when-unchanged": ('        if same:\n            return Decision("unchanged", target["number"], None, duplicates)\n'
                               '        return Decision("update"', '        return Decision("update"'),
    "invalid-marker": ('        return Decision("refused", matches[0]["number"], exc.code)',
                       '        return Decision("create", None, None)'),
    "lowest-number": ('    return sorted(found, key=lambda item: item["number"])', "    return found"),
    "mask-guid": ('    return _GUID_RE.sub("<guid>", _ARM_ID_RE.sub("<arm-id>", text))',
                  '    return _ARM_ID_RE.sub("<arm-id>", text)'),
    "mask-arm": ('    return _GUID_RE.sub("<guid>", _ARM_ID_RE.sub("<arm-id>", text))', '    return _GUID_RE.sub("<guid>", text)'),
    "key-allowlist": ("    return cleaned if _SEGMENT_RE.match(cleaned) else PATH_PLACEHOLDER", "    return cleaned"),
    "strip-unsafe": ("if unicodedata.category(ch) not in _STRIP_CATEGORIES", "if True"),
    "fence-length": ('    fence = "`" * (longest + 1)', '    fence = "`"'),
    "title-allowlist": ('    safe_address = _TITLE_CHAR_RE.sub("_", clean(address))', "    safe_address = clean(address)"),
    "reduced-level": ("    return (resource.severity.level in FULL_LEVELS", "    return (True"),
    "reduced-type": ("            and resource.type not in SECURITY_SENSITIVE_TYPES\n", ""),
    "reduced-redacted": ("any(change.redacted or ", "any(False and "),
    "post-no-retry": ('        attempts = 1 if method == "POST" else MAX_ATTEMPTS', "        attempts = MAX_ATTEMPTS"),
    "label-exists": ('    if not client.label_exists(LABEL):\n        raise AutomationError("label_missing")\n',
                     "    client.label_exists(LABEL)\n"),
    "per-run-cap": ("        if writes >= MAX_WRITES_PER_RUN:", "        if False:"),
    "next-link-check": ("        if url is not None and not self._url_allowed(url):", "        if False:"),
    # Task 8.3 lifecycle safeguards ("closed issue reopened" is covered by open-state: closed issues never match)
    "close-no-timestamp": ("        if marker.plan_timestamp < evidence.plan_timestamp:", "        if True:"),
    "close-ge": ("marker.plan_timestamp < evidence.plan_timestamp", "marker.plan_timestamp <= evidence.plan_timestamp"),
    "resolvable-includes-unknown": ("        if fp not in resolvable:", "        if False:"),
    "drifted-exclusion-removed": ("        if fp is None or fp in drifted:", "        if fp is None:"),
    "lowest-duplicate-only": (
        '    candidates = sorted((i for i in items if is_automation_issue(i)), key=lambda i: i["number"])',
        '    candidates = sorted({marker_fingerprint(i.get("body"))[1]: i for i in sorted((i for i in items if '
        'is_automation_issue(i)), key=lambda i: -i["number"])}.values(), key=lambda i: i["number"])'),
    "close-state-reason-dropped": ('CLOSE_PAYLOAD = {"state": "closed", "state_reason": "completed"}',
                                   'CLOSE_PAYLOAD = {"state": "closed"}'),
    "close-comment-post": ('        response = self.request("PATCH", f"/repos/{self.repository}/issues/{int(number)}", dict(CLOSE_PAYLOAD))',
                           '        self.request("POST", f"/repos/{self.repository}/issues/{int(number)}/comments", {"body": "closed"})\n'
                           '        response = self.request("PATCH", f"/repos/{self.repository}/issues/{int(number)}", dict(CLOSE_PAYLOAD))'),
    "close-payload-body": ("dict(CLOSE_PAYLOAD))", 'dict(CLOSE_PAYLOAD, body=""))'),
    "close-marker-unchecked": ('            decisions.append(Decision("refused", number, exc.code, duplicates))',
                               '            decisions.append(Decision("close", number, None, duplicates))'),
    "close-cap": ("        if MAX_WRITES_PER_RUN <= writes:", "        if False:"),
    "per-issue-aborts": ('        if decision_.action != "close":\n            continue\n',
                         '        if decision_.action != "close":\n            return\n'),
    "per-issue-exit-0": ("        if decision_.code:\n            result.add(decision_.code)",
                         "        if decision_.code in WARNING_CODES:\n            result.add(decision_.code)"),
    "not-in-report-closes": ('            decisions.append(Decision("skip", number, "resource_not_in_report"))',
                             '            decisions.append(Decision("close", number, "resource_not_in_report"))'),
    "no-redirect": ("            return None  # a 3xx then surfaces as HTTPError -> blocked_request",
                    "            return super().redirect_request(req, fp, code, msg, headers, newurl)"),
}
NO_OP = ("# --------------------------------------------------------------------------- run", "# run")


class SafeguardMutationTests(_Base):
    """Each mutant removes one safeguard from an in-process copy of the script (the
    repository file is never changed) and must change at least one scenario's result."""

    def scenarios(self) -> dict:
        tmp = self.tmp

        def write(report, name):
            path = os.path.join(tmp, name)
            with open(path, "w") as fh:
                json.dump(report, fh)
            return path

        def publish(report, name, env=ENV, seed=None, page_size=100, next_base=f"{API}/repositories/1/issues",
                    drift="true", fake_kwargs=None):
            def scenario(m):
                fake = FakeGitHub(page_size=page_size, next_base=next_base, **(fake_kwargs or {}))
                if seed:
                    seed(m, fake)
                sleeps = []
                result = m.run(args_for(write(report, name), drift=drift), dict(env),
                               lambda token, repo: m.GitHubClient(token, repo, opener=fake, sleep=sleeps.append))
                return json.dumps([result.summary(), fake.requests, sorted(fake.issues.items())], sort_keys=True)
            return scenario

        def render(report):
            def scenario(m):
                ev = m.evidence_from_report(m.load_report(json.dumps(report).encode()), "dev")
                return json.dumps([dataclasses_tuple(m.render_issue(ev, r, REPO)) for r in ev.resources])
            return scenario

        def dataclasses_tuple(rendered):
            return [rendered.title, rendered.body, rendered.content_hash]

        def seed_marker(plan, same, **issue_kwargs):
            def seed(m, fake):
                ev = m.evidence_from_report(m.load_report(json.dumps(lowest_report()).encode()), "dev")
                rendered = m.render_issue(ev, ev.resources[0], REPO)
                content = rendered.content_hash if same else "d" * 64
                fake.add_issue(m.marker_line(rendered.fingerprint, content, "github-100-1", plan), **issue_kwargs)
            return seed

        def seed_bad_marker(m, fake):
            ev = m.evidence_from_report(m.load_report(json.dumps(lowest_report()).encode()), "dev")
            fake.add_issue(f"<!-- drift-issue v=1 fp={m.render_issue(ev, ev.resources[0], REPO).fingerprint} bad -->")

        def seed_two(m, fake):
            ev = m.evidence_from_report(m.load_report(json.dumps(lowest_report()).encode()), "dev")
            fp = m.render_issue(ev, ev.resources[0], REPO).fingerprint
            for n in (8, 2):
                fake.add_issue(m.marker_line(fp, "d" * 64, "github-100-1", "2026-10-01T00:00:00Z"), number=n)

        def seed_fp_on_second_line(m, fake):
            ev = m.evidence_from_report(m.load_report(json.dumps(lowest_report()).encode()), "dev")
            fp = m.render_issue(ev, ev.resources[0], REPO).fingerprint
            fake.add_issue(f"<!-- drift-issue v=1 -->\nfp={fp}")

        def seed_prefix_on_second_line(m, fake):
            ev = m.evidence_from_report(m.load_report(json.dumps(lowest_report()).encode()), "dev")
            fp = m.render_issue(ev, ev.resources[0], REPO).fingerprint
            fake.add_issue(f"note v=1 fp={fp}\n<!-- drift-issue -->")

        def seed_shifted(m, fake):
            ev = m.evidence_from_report(m.load_report(json.dumps(lowest_report()).encode()), "dev")
            fp = m.render_issue(ev, ev.resources[0], REPO).fingerprint
            fake.add_issue("quoted:\n" + m.marker_line(fp, "d" * 64, "github-100-1", "2026-10-01T00:00:00Z"))

        def redirect(m):
            handler = m.GitHubClient._NoRedirect()
            req = urllib.request.Request(f"{API}/x")
            return repr(type(handler.redirect_request(req, None, 302, "Found", {}, f"{API}/y")).__name__)

        def retry_post(m):
            fake = FakeGitHub()
            fake.fail("create", 502)
            client = m.GitHubClient(TOKEN, REPO, opener=fake, sleep=lambda s: None)
            try:
                client.create_issue("t", "b")
            except m.AutomationError as exc:
                return f"{exc.code}:{fake.count('POST')}"
            return f"ok:{fake.count('POST')}"

        failed_attempt = dict(ENV, GITHUB_RUN_ATTEMPT="2")
        report_attempt = lowest_report()
        report_attempt["run"]["run_id"] = "github-123-1"
        mixed = lowest_report()
        extra = copy.deepcopy(mixed["resources"][0])
        extra.update(address="azurerm_resource_group.cfg", drift_action=None, drift_actions=None, classification="config_change")
        mixed["resources"].append(extra)
        env_mismatch = lowest_report()
        env_mismatch["run"]["environment"] = "prod"
        redacted = lowest_report()
        redacted["resources"][0]["attribute_changes"][0]["redacted"] = True
        nsg_low = fixture_report("nsg_tags_only")

        def seed_life(address, plan, *, environment="dev", body=None, number=None, state="open"):
            def seed(m, fake):
                fp = m.fingerprint(environment, address)
                fake.add_issue(body.format(fp=fp) if body else m.marker_line(fp, "a" * 64, "github-100-1", plan),
                               number=number, state=state)
            return seed

        def seeds(*fns):
            return lambda m, fake: [fn(m, fake) for fn in fns]

        s01 = 'module.resource_group.azurerm_resource_group.this["s01"]'
        old = "2026-10-02T00:00:00Z"
        medium_rg = lowest_report()
        medium_rg["resources"][0]["severity"]["level"] = "MEDIUM"
        has_drift_false = lowest_report()
        has_drift_false["has_drift"] = False
        return {
            "skip": publish(lowest_report(), "a.json", drift="unknown"),
            "in-sync": publish(fixture_report("in_sync"), "b.json"),
            "env-mismatch": publish(env_mismatch, "c.json"),
            "mixed": publish(mixed, "d.json"),
            "failed-attempt": publish(report_attempt, "e.json", env=failed_attempt),
            "outside-actions": publish(lowest_report(), "f.json", env={k: v for k, v in ENV.items() if k != "GITHUB_ACTIONS"}),
            "create": publish(lowest_report(), "g.json"),
            "spoof-user": publish(lowest_report(), "h.json", seed=seed_marker(
                "2026-10-01T00:00:00Z", False, user={"login": "mallory", "type": "User"})),
            "spoof-type": publish(lowest_report(), "h2.json", seed=seed_marker(
                "2026-10-01T00:00:00Z", False, user={"login": "github-actions[bot]", "type": "User"})),
            "spoof-label": publish(lowest_report(), "i.json", seed=seed_marker("2026-10-01T00:00:00Z", False, labels=())),
            "closed": publish(lowest_report(), "j.json", seed=seed_marker("2026-10-01T00:00:00Z", False, state="closed")),
            "pr": publish(lowest_report(), "k.json", seed=seed_marker("2026-10-01T00:00:00Z", False, pr=True)),
            "shifted-marker": publish(lowest_report(), "l.json", seed=seed_shifted),
            "older-same": publish(lowest_report(), "m.json", seed=seed_marker("2026-10-01T00:00:00Z", True)),
            "older-diff": publish(lowest_report(), "n.json", seed=seed_marker("2026-10-01T00:00:00Z", False)),
            "equal-diff": publish(lowest_report(), "o.json", seed=seed_marker("2026-10-03T10:00:00Z", False)),
            "newer-diff": publish(lowest_report(), "p.json", seed=seed_marker("2026-10-09T00:00:00Z", False)),
            "bad-marker": publish(lowest_report(), "q.json", seed=seed_bad_marker),
            "two": publish(lowest_report(), "r.json", seed=seed_two),
            "label-missing": publish(lowest_report(), "s.json", fake_kwargs={"labels": ()}),
            "cap": publish(many_resources(lowest_report(), ga.MAX_WRITES_PER_RUN + 1), "t.json"),
            "has-drift-false": publish(has_drift_false, "v.json"),
            "spoof-bot-login": publish(lowest_report(), "w.json", seed=seed_marker(
                "2026-10-01T00:00:00Z", False, user={"login": "evil[bot]", "type": "Bot"})),
            "fp-second-line": publish(lowest_report(), "x.json", seed=seed_fp_on_second_line),
            "prefix-second-line": publish(lowest_report(), "y.json", seed=seed_prefix_on_second_line),
            "two-desc": publish(lowest_report(), "z.json", seed=seed_two, fake_kwargs={"descending": True}),
            "medium-rg": render(medium_rg),
            "other-repo-next": publish(lowest_report(), "u2.json", page_size=1, next_base=f"{API}/repos/other/repo/issues",
                                       seed=lambda m, f: (f.add_issue("x"), f.add_issue("y"))),
            "foreign-next": publish(lowest_report(), "u.json", page_size=1, next_base="https://evil.example/repositories/1/issues",
                                    seed=lambda m, f: (f.add_issue("x"), f.add_issue("y"))),
            "life-close": publish(resolved_report(), "l1.json", drift="false", seed=seed_life(RG_ADDR, old)),
            "life-equal": publish(resolved_report(), "l2.json", drift="false", seed=seed_life(RG_ADDR, "2026-10-03T10:00:00Z")),
            "life-stale": publish(resolved_report(), "l3.json", drift="false", seed=seed_life(RG_ADDR, "2026-10-04T00:00:00Z")),
            "life-not-in-report": publish(resolved_report(), "l4.json", drift="false",
                                          seed=seed_life(RG_ADDR, old, environment="prod")),
            "life-unknown": publish(resolved_report(), "l5.json", drift="unknown", seed=seed_life(RG_ADDR, old)),
            "life-false-drifted": publish(lowest_report(), "l6.json", drift="false"),
            "life-dupes": publish(resolved_report(), "l7.json", drift="false",
                                  seed=seeds(seed_life(RG_ADDR, old, number=3), seed_life(RG_ADDR, old, number=5))),
            "life-bad-then-valid": publish(resolved_report(2), "l8.json", drift="false", seed=seeds(
                seed_life(RG_ADDR, old, number=2, body="<!-- drift-issue v=1 fp={fp} broken -->"),
                seed_life(s01, old, number=4))),
            "life-cap": publish(resolved_report(ga.MAX_WRITES_PER_RUN + 1), "l9.json", drift="false", seed=seeds(
                seed_life(RG_ADDR, old), *[seed_life(f'module.resource_group.azurerm_resource_group.this["s{i:02d}"]', old)
                                           for i in range(1, ga.MAX_WRITES_PER_RUN + 1)])),
            "life-true-not-in-report": publish(lowest_report(), "l10.json", seed=seed_life(s01, old)),
            "hostile": render(hostile_report()),
            "redacted": render(redacted),
            "medium": render(fixture_report("unconfigured_attribute_drift")),
            "nsg-low": render(nsg_low),
            "redirect": redirect,
            "retry-post": retry_post,
        }

    @staticmethod
    def load(name: str, source: str):
        module_name = f"_github_automation_mutant_{name.replace('-', '_')}"
        module = types.ModuleType(module_name)
        module.__file__ = f"<mutant {name}>"
        sys.modules[module_name] = module
        try:
            exec(compile(source, module.__file__, "exec"), module.__dict__)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
        return module

    @staticmethod
    def outcome(module, scenario) -> str:
        try:
            return scenario(module)
        except Exception as exc:  # a crash also shows the safeguard was exercised
            return f"raised {type(exc).__name__}"

    def test_every_mutant_is_caught(self):
        with open(SCRIPT, encoding="utf-8") as fh:
            source = fh.read()
        scenarios = self.scenarios()
        expected = {name: self.outcome(ga, s) for name, s in scenarios.items()}
        self.assertFalse(any(v.startswith("raised") for v in expected.values()), expected)
        survivors = []
        for name, (old, new) in MUTANTS.items():
            with self.subTest(name):
                self.assertEqual(source.count(old), 1, f"mutant {name} does not apply exactly once")
                module = self.load(name, source.replace(old, new))
                try:
                    if all(self.outcome(module, s) == expected[n] for n, s in scenarios.items()):
                        survivors.append(name)
                finally:
                    sys.modules.pop(module.__name__, None)
        self.assertEqual(survivors, [])

    def test_no_op_control_is_not_caught(self):
        with open(SCRIPT, encoding="utf-8") as fh:
            source = fh.read()
        self.assertEqual(source.count(NO_OP[0]), 1)
        module = self.load("no-op", source.replace(*NO_OP))
        try:
            for name, scenario in self.scenarios().items():
                self.assertEqual(self.outcome(module, scenario), self.outcome(ga, scenario), name)
        finally:
            sys.modules.pop(module.__name__, None)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
