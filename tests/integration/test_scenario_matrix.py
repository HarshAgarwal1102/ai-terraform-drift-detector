"""Task 12.2: end-to-end drift scenario test matrix with graceful-degradation checks.

Every scenario runs the real pipeline stages in-process, the way the drift-detection and ai-analysis
workflows chain them: `drift-engine analyze` (internal + public report) -> `drift-engine investigate`
(Azure Activity Log) -> `ai-analysis` (deterministic report, optional LLM) -> GitHub issue publication,
plus the cost path (scripts/sanitize_infracost.py -> `ai-analysis --cost`) and the unmanaged path
(`drift-engine inventory` -> `drift-engine unmanaged-cost` -> `ai-analysis --unmanaged`).

Rows (PROJECT_PLAN.md, Task 12.2): No Drift, Single Resource Drift, Multi-Resource Drift, Security
Drift, Cost Drift, AI Unavailable, Azure API Failure (plus Infracost unavailable). The degradation
contract checked everywhere: a dependency failure is reported explicitly with a fixed code, it never
changes the drift report (byte for byte), and every stage that does not need the failed dependency
still produces its normal, verified output.

No network: Azure, GitHub and the Retail Prices API are scripted fakes from the existing tests, and
tests/conftest.py blocks every non-loopback connection. "LLM API down" uses the real OpenAI client
against a loopback server (or a closed loopback port), so the failure goes through the same code path
as a real outage.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import http.server
import importlib.util
import io
import json
import os
import re
import socket
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"
sys.path.insert(0, str(TESTS))

HAS_AI_EXTRA = all(importlib.util.find_spec(m) for m in ("langgraph", "langchain_openai"))
pytestmark = [pytest.mark.integration, pytest.mark.skipif(not HAS_AI_EXTRA, reason="needs the 'ai' extra")]

from test_activity_logs import FakeSource, bundle  # noqa: E402  (shared helpers; no test classes imported)
from test_github_automation import ENV as GITHUB_ENV  # noqa: E402
from test_github_automation import FakeGitHub, args_for, ga  # noqa: E402
import unmanaged_fixtures as uf  # noqa: E402

from drift_engine import activity_logs as al  # noqa: E402
from drift_engine import cli  # noqa: E402
from drift_engine import inventory as inventory_mod  # noqa: E402
from drift_engine import unmanaged_cost  # noqa: E402

if HAS_AI_EXTRA:
    from ai_engine import cli as ai_cli

RUN_ID = "github-123-1"  # the run binding GitHub issue publication requires (GITHUB_RUN_ID 123, attempt 1)
API_KEY = "sk-test-not-real-matrix"
PROVIDER_ECHO = "provider-echo-marker-7f3a"  # in every fake LLM error body; only the exception type may be reported
CLEAN_ENV = ("GITHUB_ACTIONS", "AI_LLM_PROVIDER", "AI_LLM_MODEL", "AI_LLM_TIMEOUT_SECONDS", "AI_LLM_MAX_RETRIES",
             "AI_LLM_TEMPERATURE", "OPENAI_API_KEY", "OPENAI_BASE_URL", "AZURE_OPENAI_API_KEY",
             "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_VERSION")
# AI report sections that never depend on the LLM (the same set tests/test_ai_report.py compares, plus the
# Task 10.4 unmanaged section): identical with and without a working LLM. `analysis` is the LLM's own part.
DETERMINISTIC = ("report_version", "provenance", "summary", "investigation", "resources", "remediation", "cost",
                 "unmanaged")
SEVERITY_ORDER = ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL")


@dataclass(frozen=True)
class Scenario:
    group: str
    name: str
    drifted: int
    max_severity: str
    infracost_raw: str | None = None


SCENARIOS = {
    "no_drift": Scenario("plan_evidence", "in_sync", 0, "INFO"),
    "single_resource_drift": Scenario("plan_evidence", "external_drift", 1, "LOW"),
    "multi_resource_drift": Scenario("cost_config_plans", "combined_security_cost_config", 2, "CRITICAL"),
    "security_drift": Scenario("security_plans", "nsg_open_inbound", 1, "CRITICAL"),
    "cost_drift": Scenario("infracost", "service_plan_sku_drift", 1, "MEDIUM", "service_plan_sku_drift"),
}
DRIFTED = [name for name, s in SCENARIOS.items() if s.drifted]
# The seven rows named in PROJECT_PLAN.md Task 12.2; the last two are failure modes applied to the rows above.
MATRIX_ROWS = ("No Drift", "Single Resource Drift", "Multi-Resource Drift", "Security Drift", "Cost Drift",
               "AI Unavailable", "Azure API Failure")


# --------------------------------------------------------------------------- pipeline helpers


def call(main, argv, env=None, **patches) -> tuple[int, str, str]:
    """Run a CLI entry point in-process with a hermetic environment (no CI or LLM variables leak in)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.dict(os.environ))
        for name in CLEAN_ENV:
            os.environ.pop(name, None)
        os.environ.update(env or {})
        for name, value in patches.items():
            stack.enter_context(mock.patch.object(cli, name, value))
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FailingActivityLog:
    """Every Activity Log query fails with `error` (all resource groups), the way the SDK source raises."""

    def __init__(self, error: Exception) -> None:
        self.error, self.calls = error, 0

    def pages(self, subscription_id: str, query_filter: str):
        self.calls += 1

        def generate():
            raise self.error
            yield  # pragma: no cover  (makes this a generator)
        return generate()


class Pipeline:
    """One scenario's run directory: the drift reports are produced once, consumers read them."""

    def __init__(self, scenario: Scenario, directory: Path) -> None:
        self.scenario, self.dir = scenario, directory
        directory.mkdir(parents=True, exist_ok=True)
        self.plan, self.manifest = bundle(str(directory), scenario.group, scenario.name)
        manifest = json.loads(Path(self.manifest).read_text(encoding="utf-8"))
        manifest["run_id"] = RUN_ID  # as written by Generate Plan Evidence in CI
        Path(self.manifest).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self.internal, self.public = directory / "drift_report.internal.json", directory / "drift_report.json"
        self.analyze_code, _, self.analyze_err = call(cli.main, [
            "analyze", "--plan", self.plan, "--manifest", self.manifest,
            "--output", str(self.internal), "--public-output", str(self.public)])
        self.report = json.loads(self.public.read_text(encoding="utf-8"))

    def digests(self) -> tuple[str, str]:
        return sha256(self.internal), sha256(self.public)

    def investigate(self, source, label: str) -> tuple[int, str, dict | None]:
        public = self.dir / f"drift_investigation.{label}.json"
        code, _, err = call(cli.main, [
            "investigate", "--plan", self.plan, "--manifest", self.manifest, "--report", str(self.internal),
            "--output", str(self.dir / f"investigation.{label}.json"),
            "--evidence-output", str(self.dir / f"evidence.{label}.json"), "--public-output", str(public)],
            _activity_log_source=lambda: source)
        return code, err, json.loads(public.read_text(encoding="utf-8")) if public.exists() else None

    def ai(self, label: str, env: dict | None = None, *extra: str) -> tuple[int, str, str, dict | None, str]:
        out = self.dir / f"ai.{label}"
        code, stdout, err = call(ai_cli.main, ["--report", str(self.public), "--output-dir", str(out), *extra],
                                 env if env is not None else {"AI_LLM_PROVIDER": "none"})
        if code != 0:
            return code, stdout, err, None, ""
        return (code, stdout, err, json.loads((out / "ai_analysis_report.json").read_text(encoding="utf-8")),
                (out / "ai_analysis_report.md").read_text(encoding="utf-8"))

    def issues(self) -> tuple[object, FakeGitHub]:
        fake = FakeGitHub()
        drift = "true" if self.report["has_drift"] else "false"
        result = ga.run(args_for(str(self.public), drift=drift), dict(GITHUB_ENV),
                        lambda token, repo: ga.GitHubClient(token, repo, opener=fake, sleep=lambda seconds: None))
        return result, fake

    def cost_dir(self, raw: str | None) -> Path:
        """The Infracost artifact the real sanitizer writes; `raw=None` leaves it empty (Infracost unavailable)."""
        out = self.dir / f"infracost-{raw or 'missing'}"
        out.mkdir()
        if raw is not None:
            spec = importlib.util.spec_from_file_location("sanitize_infracost_matrix", ROOT / "scripts" /
                                                          "sanitize_infracost.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            assert module.main(["--raw", str(TESTS / "fixtures" / "infracost" / "raw" / f"{raw}.raw.json"),
                                "--drift-report", str(self.public), "--run-id", RUN_ID, "--environment", "dev",
                                "--infracost-version", "v0.10.46", "--output-dir", str(out)]) == 0
        return out

    def unmanaged(self, arm, prices, label: str) -> tuple[int, int, Path]:
        out = self.dir / f"unmanaged.{label}"
        out.mkdir()
        inv_code, _, _ = call(cli.main, ["inventory", "--plan", self.plan, "--report", str(self.public),
                                         "--output", str(out / "unmanaged_inventory.json")],
                              _inventory_source=lambda: arm)
        cost_code, _, _ = call(cli.main, ["unmanaged-cost", "--inventory", str(out / "unmanaged_inventory.json"),
                                          "--report", str(self.public), "--output", str(out / "unmanaged_cost.json")],
                               _price_source=lambda: prices)
        return inv_code, cost_code, out


@pytest.fixture(scope="module")
def baseline(tmp_path_factory) -> dict[str, dict]:
    """Every scenario with healthy dependencies (and the CI LLM setting, provider `none`)."""
    runs = {}
    for name, scenario in SCENARIOS.items():
        pipeline = Pipeline(scenario, tmp_path_factory.mktemp(name))
        source = FakeSource()
        inv_code, inv_err, investigation = pipeline.investigate(source, "healthy")
        cost = ("--cost", str(pipeline.cost_dir(scenario.infracost_raw))) if scenario.infracost_raw else ()
        ai_code, ai_out, ai_err, ai_report, ai_md = pipeline.ai("healthy", None, *cost)
        result, fake = pipeline.issues()
        runs[name] = dict(pipeline=pipeline, digests=pipeline.digests(), source=source, inv_code=inv_code,
                          inv_err=inv_err, investigation=investigation, ai_code=ai_code, ai_err=ai_err,
                          ai=ai_report, md=ai_md, issues=result, github=fake, cost=cost)
    return runs


def drift_view(report: dict) -> list[tuple]:
    """The per-resource drift facts the AI report copies from the drift report (never from the LLM)."""
    return [(r["address"], r["type"], json.dumps(r["what"], sort_keys=True)) for r in report["resources"]]


# --------------------------------------------------------------------------- matrix completeness


def test_matrix_covers_every_planned_row():
    covered = {"No Drift": "no_drift", "Single Resource Drift": "single_resource_drift",
               "Multi-Resource Drift": "multi_resource_drift", "Security Drift": "security_drift",
               "Cost Drift": "cost_drift", "AI Unavailable": test_ai_unavailable.__name__,
               "Azure API Failure": test_activity_log_api_failure.__name__}
    assert tuple(covered) == MATRIX_ROWS
    assert set(SCENARIOS) == {v for v in covered.values() if v in SCENARIOS}
    assert SCENARIOS["multi_resource_drift"].drifted > 1


# --------------------------------------------------------------------------- healthy rows


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenario_with_healthy_dependencies(baseline, name):
    run, scenario = baseline[name], SCENARIOS[name]
    pipeline, report = run["pipeline"], run["pipeline"].report
    # detection
    assert (pipeline.analyze_code, pipeline.analyze_err) == (0, "")
    assert (report["outcome"], report["has_drift"]) == ("succeeded", scenario.drifted > 0)
    assert report["summary"]["drifted_resources"] == scenario.drifted
    levels = [r["severity"]["level"] for r in report["resources"]]
    assert max(levels, key=SEVERITY_ORDER.index) == report["summary"]["highest_severity"] == scenario.max_severity
    # investigation: Azure is queried only when there is drift
    assert (run["inv_code"], run["investigation"]["outcome"]) == (0, "complete")
    assert (len(run["source"].calls) > 0) == (scenario.drifted > 0)
    # AI analysis (verified by the CLI before it writes anything)
    assert (run["ai_code"], run["ai_err"]) == (0, "")
    ai = run["ai"]
    assert (ai["llm"]["provider"], ai["llm"]["status"], ai["llm"]["attempted"]) == ("none", "not_attempted", False)
    assert ai["summary"]["drifted_resources"] == scenario.drifted
    assert ai["summary"]["highest_severity"] == scenario.max_severity
    # the AI report covers exactly the drifted resources, in drift-report order
    assert [r["address"] for r in ai["resources"]] == [r["address"] for r in report["resources"]
                                                      if r["drift_actions"] is not None]
    assert run["md"].startswith("#")
    # issues: exactly one per drifted resource, none without drift
    assert (run["issues"].outcome, run["issues"].codes) == ("ok", [])
    assert run["github"].count("POST") == scenario.drifted


def test_cost_drift_is_priced_from_the_infracost_result(baseline):
    ai = baseline["cost_drift"]["ai"]
    assert ai["cost"]["status"] == "complete"
    text = json.dumps(ai["cost"])
    for amount in ("106.58", "119.72", "13.14"):  # baseline, with drift, delta (USD/month, Task 10.2)
        assert amount in text


def test_security_drift_is_rated_critical_and_published(baseline):
    run = baseline["security_drift"]
    assert run["ai"]["summary"]["highest_severity"] == "CRITICAL"
    (body,) = [payload["body"] for method, _, payload in run["github"].requests if method == "POST"]
    assert "CRITICAL" in body


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_pipeline_is_deterministic(baseline, tmp_path, name):
    run = baseline[name]
    again = Pipeline(SCENARIOS[name], tmp_path / name)
    assert again.digests() == run["digests"]
    _, _, _, report, md = again.ai("again", None, *run["cost"])
    assert (report, md) == (run["ai"], run["md"])


# --------------------------------------------------------------------------- AI unavailable


class _LLMServer(http.server.BaseHTTPRequestHandler):
    mode = "http_500"

    def do_POST(self):  # noqa: N802 (http.server API)
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.mode == "timeout":
            time.sleep(3)
            return
        if self.mode == "invalid_reply":
            body = json.dumps({"id": "c", "object": "chat.completion", "created": 0, "model": "m",
                               "choices": [{"index": 0, "finish_reason": "stop",
                                            "message": {"role": "assistant",
                                                        "content": f"not the JSON envelope {PROVIDER_ECHO}"}}]})
            status = 200
        else:
            body, status = json.dumps({"error": {"message": f"unavailable {PROVIDER_ECHO}", "type": "server_error"}}), \
                {"http_500": 500, "http_429": 429, "http_503": 503}[self.mode]
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # silence the default stderr access log
        pass


@pytest.fixture(scope="module")
def llm_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _LLMServer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


LLM_OUTAGES = ("connection_refused", "http_500", "http_503", "http_429", "timeout", "invalid_reply")


@pytest.mark.parametrize("outage", LLM_OUTAGES)
@pytest.mark.parametrize("name", list(SCENARIOS))
def test_ai_unavailable(baseline, llm_server, name, outage):
    """LLM API down: the deterministic AI report is still written, verified and identical to the no-LLM one."""
    run = baseline[name]
    pipeline = run["pipeline"]
    port = _closed_port() if outage == "connection_refused" else llm_server.server_address[1]
    _LLMServer.mode = outage
    env = {"AI_LLM_PROVIDER": "openai", "OPENAI_API_KEY": API_KEY, "AI_LLM_MODEL": "matrix-model",
           "OPENAI_BASE_URL": f"http://127.0.0.1:{port}/v1", "AI_LLM_TIMEOUT_SECONDS": "1", "AI_LLM_MAX_RETRIES": "0"}
    code, stdout, err, report, md = pipeline.ai(f"llm-{outage}", env, *run["cost"])
    assert (code, err) == (0, "")
    expected = ("invalid_output" if outage == "invalid_reply" else "failed") if SCENARIOS[name].drifted \
        else "not_attempted"
    assert (report["llm"]["provider"], report["llm"]["status"]) == ("openai", expected)
    assert report["llm"]["attempted"] is bool(SCENARIOS[name].drifted)
    for key in DETERMINISTIC:
        assert report[key] == run["ai"][key], key
    # The LLM's own sections: those it would have filled carry a fixed failure reason and no findings (nothing is
    # invented); the deterministic ones ("no security-relevant changes", ...) are unchanged.
    reason = "reply is not strict JSON" if outage == "invalid_reply" else "LLM call failed ("
    routed = 0
    for key, section in report["analysis"].items():
        base = run["ai"]["analysis"][key]
        assert section["findings"] == [] == base["findings"], key
        if base["reason"].startswith("LLM unavailable") and SCENARIOS[name].drifted:
            routed += 1
            assert section["reason"].startswith(reason), (key, section["reason"])
            if outage != "invalid_reply":  # exactly the exception type, never the provider's message
                assert re.fullmatch(r"LLM call failed \(\w+\)", section["reason"]), section["reason"]
        else:
            assert section == base, key
    assert (routed > 0) == bool(SCENARIOS[name].drifted)
    assert pipeline.digests() == run["digests"]  # the drift report is never touched
    for secret in (API_KEY, PROVIDER_ECHO):
        assert secret not in json.dumps(report) + md + stdout + err


# --------------------------------------------------------------------------- Azure API failure


@pytest.mark.parametrize("code", al.QUERY_FAILURE_CODES)
@pytest.mark.parametrize("name", list(SCENARIOS))
def test_activity_log_api_failure(baseline, name, code):
    """Activity Log down: the investigation fails explicitly; drift report, AI report and issues are unaffected."""
    run, drifted = baseline[name], SCENARIOS[name].drifted > 0
    pipeline = run["pipeline"]
    source = FailingActivityLog(al.SourceError(code, 401 if code == "authentication_failed" else None))
    exit_code, err, investigation = pipeline.investigate(source, f"azure-{code}")
    assert pipeline.digests() == run["digests"]
    if not drifted:  # nothing to investigate: Azure is never queried, so its outage cannot matter
        assert (exit_code, source.calls, investigation["outcome"]) == (0, 0, "complete")
        return
    assert exit_code == 1 and source.calls > 0
    assert "INVESTIGATION FAILED [evidence_failed]" in err and "Drift detection results are unaffected" in err
    assert (investigation["outcome"], investigation["failure"]["reason"]) == ("failed", "evidence_failed")
    public = pipeline.dir / f"drift_investigation.azure-{code}.json"
    ai_code, _, ai_err, report, _ = pipeline.ai(f"azure-{code}", None, "--investigation", str(public), *run["cost"])
    assert (ai_code, ai_err) == (0, "")
    assert report["investigation"]["status"] == "failed"
    for key in ("summary", "remediation", "cost", "analysis"):
        assert report[key] == run["ai"][key], key
    assert drift_view(report) == drift_view(run["ai"])
    result, fake = pipeline.issues()
    assert (result.outcome, fake.requests) == ("ok", run["github"].requests)


@pytest.mark.parametrize("code", inventory_mod.SCOPE_FAILURE_CODES)
def test_arm_inventory_api_failure(baseline, code):
    run = baseline["single_resource_drift"]
    pipeline = run["pipeline"]
    arm = uf.FakeArm([inventory_mod.InventorySourceError(code, 403)])
    inv_code, cost_code, directory = pipeline.unmanaged(arm, uf.FakePrices(), f"arm-{code}")
    inventory = json.loads((directory / "unmanaged_inventory.json").read_text(encoding="utf-8"))
    cost = json.loads((directory / "unmanaged_cost.json").read_text(encoding="utf-8"))
    assert (inv_code, inventory["outcome"], inventory["failure"]) == (1, "failed", "listing_failed")
    assert (cost_code, cost["failure"]) == (1, "inventory_not_complete")
    ai_code, _, ai_err, report, _ = pipeline.ai(f"arm-{code}", None, "--unmanaged", str(directory))
    assert (ai_code, ai_err) == (0, "")
    assert report["unmanaged"]["inventory"]["failure"] == "listing_failed"
    for key in ("summary", "resources", "remediation", "cost", "analysis", "investigation"):
        assert report[key] == run["ai"][key], key
    assert pipeline.digests() == run["digests"]


@pytest.mark.parametrize("code", unmanaged_cost.API_FAILURES)
def test_retail_prices_api_failure(baseline, code):
    run = baseline["single_resource_drift"]
    pipeline = run["pipeline"]
    inv_code, cost_code, directory = pipeline.unmanaged(uf.portal_vm_source(), uf.FakePrices(fail=code),
                                                        f"prices-{code}")
    cost = json.loads((directory / "unmanaged_cost.json").read_text(encoding="utf-8"))
    assert (inv_code, cost_code, cost["failure"]) == (0, 1, code)
    ai_code, _, ai_err, report, _ = pipeline.ai(f"prices-{code}", None, "--unmanaged", str(directory))
    assert (ai_code, ai_err) == (0, "")
    assert report["unmanaged"]["cost"]["failure"] == code
    for key in ("summary", "resources", "remediation", "cost", "analysis", "investigation"):
        assert report[key] == run["ai"][key], key
    assert pipeline.digests() == run["digests"]


# --------------------------------------------------------------------------- Infracost unavailable


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_infracost_unavailable(baseline, name):
    """No Infracost result: the report records the rejected cost input; everything else is unchanged."""
    run = baseline[name]
    pipeline = run["pipeline"]
    missing = pipeline.cost_dir(None)
    code, _, err, report, _ = pipeline.ai("infracost-missing", None, "--cost", str(missing))
    assert code == 0 and "cost rejected" in err and "drift result is unaffected" in err
    assert (report["cost"]["status"], report["cost"]["reason"]) == ("rejected", "cost_input_incomplete")
    for key in ("summary", "remediation", "investigation"):
        assert report[key] == run["ai"][key], key
    assert drift_view(report) == drift_view(run["ai"])
    assert pipeline.digests() == run["digests"]
