"""Task 10.3: deterministic cost impact in the AI report (report v3).

Inputs are always produced the real way: the public drift report of the Task 10.1 synthetic SKU fixture,
and the real scripts/sanitize_infracost.py run on the real Infracost v0.10.46 samples. Amounts come only
from drift_engine.cost (Task 10.2). The LLM is a scripted fake (no network, conftest.py guard).
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
from pathlib import Path

import pytest

HAS_AI_EXTRA = all(importlib.util.find_spec(m) for m in ("langgraph", "langchain_openai"))
pytestmark = pytest.mark.skipif(not HAS_AI_EXTRA, reason="needs the 'ai' extra")

if HAS_AI_EXTRA:
    from ai_engine import verify
    from ai_engine.evidence import EVIDENCE_TAG
    from ai_engine.graph import run_analysis
    from ai_engine.nodes import cost_analysis as ca
    from ai_engine.nodes.report_generator import (
        NO_PRICING_LIMITATION,
        AiAnalysisReport,
        CostImpact,
        cost_limitations,
        render_markdown,
    )
    from drift_engine import cost as cost_engine
    from drift_engine.classifier import evaluate
    from drift_engine.investigation_public import canonical_sha256
    from drift_engine.report_public import public_document

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "infracost"
RUN_ID = "synthetic-infracost-fixture"
PLAN = "azurerm_service_plan.this"
AMOUNTS = ("106.58", "119.72", "13.14")


def _sanitizer():
    spec = importlib.util.spec_from_file_location("sanitize_infracost_for_cost_impact", ROOT / "scripts" /
                                                  "sanitize_infracost.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def drift() -> dict:
    evaluation = evaluate(str(FIXTURE / "service_plan_sku_drift" / "plan.synthetic.json"),
                          str(FIXTURE / "service_plan_sku_drift" / "detection_run.json"))
    return public_document(evaluation.report, evaluation.plan or {})


def _cost_dir(tmp_path_factory, drift: dict, raw: str) -> Path:
    tmp = tmp_path_factory.mktemp("cost")
    (tmp / "drift_report.json").write_text(json.dumps(drift), encoding="utf-8")
    out = tmp / f"infracost-report-{raw}"
    out.mkdir()
    assert _sanitizer().main(["--raw", str(FIXTURE / "raw" / f"{raw}.raw.json"), "--drift-report",
                              str(tmp / "drift_report.json"), "--run-id", RUN_ID, "--environment", "dev",
                              "--infracost-version", "v0.10.46", "--output-dir", str(out)]) == 0
    return out


@pytest.fixture(scope="module")
def priced(tmp_path_factory, drift) -> Path:
    return _cost_dir(tmp_path_factory, drift, "service_plan_sku_drift")


@pytest.fixture(scope="module")
def unpriced(tmp_path_factory, drift) -> Path:
    return _cost_dir(tmp_path_factory, drift, "in_sync")


def cost_args(directory: Path | None, drift: dict) -> tuple[dict | None, dict | None]:
    """(cost input for run_analysis, cost check for verify_report), exactly as the CLI builds them."""
    if directory is None:
        return None, None
    documents = ca.read_cost_documents(directory)
    if isinstance(documents, str):
        return ca.rejected_cost(documents), {"rejected": documents}
    return ca.cost_input(drift, documents["infracost"], documents["cost_run"]), documents


def analyse(drift: dict, directory: Path | None = None, llm=None) -> tuple[dict, list[str]]:
    cost, check = cost_args(directory, drift)
    state = run_analysis(drift, llm=llm, cost=cost) if llm is not None else run_analysis(drift, cost=cost)
    report = json.loads(json.dumps(state["report"]))
    return report, verify.verify_report(report, drift, None, check)


class CostLLM:
    """A scripted model: cites every cost-routed change with `direction`; records what it was shown."""

    def __init__(self, direction: str = "likely_increase", summary: str = "", explanation: str | None = None):
        self.direction, self.summary, self.explanation, self.prompts = direction, summary, explanation, []

    def invoke(self, messages):
        self.prompts.append(messages)
        body = re.search(rf"<{EVIDENCE_TAG}>\n(.*)\n</{EVIDENCE_TAG}>", messages[-1].content, re.DOTALL).group(1)
        evidence = json.loads(body)
        cost = [{"address": r["address"], "cited_paths": [c["path"]], "cost_driver": "sku_or_tier",
                 "direction": self.direction, "monetary_impact": "not_determinable_from_evidence",
                 "explanation": self.explanation or "A larger plan tier is typically billed at a higher rate.",
                 "basis": "inference"}
                for r in evidence["resources"] for c in r["changes"] if "cost" in c["sections"]]
        empty = {"findings": [], "summary": ""}
        return json.dumps({"security_analysis": empty, "cost_analysis": {"findings": cost, "summary": self.summary},
                           "configuration_analysis": empty, "root_cause_analysis": empty, "risk_assessment": empty,
                           "investigation_analysis": empty})


def shown(llm: CostLLM) -> str:
    return llm.prompts[0][-1].content


# --------------------------------------------------------------------------- complete: exact amounts


def test_complete_report_carries_exactly_the_cost_delta(drift, priced):
    report, problems = analyse(drift, priced)
    assert problems == []
    documents = ca.read_cost_documents(priced)
    expected = cost_engine.cost_delta(drift, documents["infracost"], documents["cost_run"])
    cost = report["cost"]
    assert (report["report_version"], cost["status"], cost["reason"]) == ("3", "complete", None)
    assert cost["cost_delta"] == expected  # embedded unchanged: cost.py is the only source of amounts
    assert (cost["monetary_impact"], cost["pricing_source"]) == ("estimated_list_price",
                                                                 "infracost_list_prices_usd_no_usage_file")
    assert report["provenance"]["cost_input_sha256"] == {"infracost": canonical_sha256(documents["infracost"]),
                                                         "cost_run": canonical_sha256(documents["cost_run"])}
    assert report["provenance"]["versions"]["cost_delta"] == "1"
    [resource] = report["resources"]
    entry = next(e for e in expected["resources"] if e["address"] == PLAN)
    assert {k: v for k, v in resource["cost"].items() if k != "statements"} == entry
    assert resource["cost"]["statements"] == [{"id": "cost.resource.v1", "text": (
        "Estimated monthly cost impact on azurerm_service_plan.this: +$106.58/month (106.58 USD per month; current "
        "configuration 119.72 USD per month, declared configuration 13.14 USD per month); attribution drift; "
        "Infracost list-price estimate, not actual Azure billing.")}]
    texts = [s["text"] for s in cost["statements"]]
    assert [s["id"] for s in cost["statements"]] == ["cost.status_complete.v1", "cost.group.v1", "cost.plan_delta.v1"]
    assert "not actual Azure billing" in texts[0] and "Terraform-managed resources only" in texts[0]
    assert texts[1] == ("Confirmed drift (the only drift cost): +$106.58/month (106.58 USD per month) from 1 priced "
                        "line(s).")
    assert texts[2].endswith("drift and pending configuration changes combined; not a drift cost.")
    assert NO_PRICING_LIMITATION not in report["limitations"]
    assert [line for line in report["limitations"] if "Infracost" in line or "drift cost" in line] == \
        cost_limitations("complete", None)


def test_unpriced_resource_is_null_never_zero(drift, unpriced):
    report, problems = analyse(drift, unpriced)
    assert problems == []
    entry = report["resources"][0]["cost"]
    assert (entry["monthly_cost_delta"], entry["display"], entry["cost_status"]) == (None, None, "not_in_cost_output")
    assert entry["statements"][0]["text"] == ("Monthly cost impact on azurerm_service_plan.this: not determinable from "
                                              "available evidence (not_in_cost_output); attribution drift.")
    group = report["cost"]["statements"][1]["text"]
    assert group == ("Confirmed drift (the only drift cost): not determinable from available evidence from 0 priced "
                     "line(s); incomplete: 1 without a price.")
    assert "$0.00" not in json.dumps(report["resources"]) and "0.00 USD" not in json.dumps(report["resources"])


# --------------------------------------------------------------------------- not_available / rejected: no amounts


def _assert_no_cost_claims(report: dict, status: str, reason: str) -> None:
    cost = report["cost"]
    assert (cost["status"], cost["reason"], cost["cost_delta"]) == (status, reason, None)
    assert (cost["monetary_impact"], cost["pricing_source"]) == ("not_determinable_from_evidence", None)
    assert len(cost["statements"]) == 1 and not re.search(r"[$€£¥₹]|\bUSD\b|\d", cost["statements"][0]["text"])
    assert all(r["cost"] is None for r in report["resources"])
    assert report["provenance"]["versions"]["cost_delta"] is None
    assert NO_PRICING_LIMITATION in report["limitations"]
    for amount in AMOUNTS:
        assert amount not in json.dumps(report) and amount not in render_markdown(report)


def test_not_available_publishes_no_amount(drift):
    report, problems = analyse(drift)
    assert problems == []
    _assert_no_cost_claims(report, "not_available", "cost_input_not_provided")
    assert report["provenance"]["cost_input_sha256"] is None
    assert report["cost"]["statements"][0]["id"] == "cost.status_not_available.v1"


def _tamper(directory: Path, tmp_path: Path, file: str, change) -> Path:
    out = tmp_path / "cost"
    out.mkdir()
    for name in ("infracost.json", "cost_run.json"):
        text = (directory / name).read_text(encoding="utf-8")
        (out / name).write_text(change(text) if name == file else text, encoding="utf-8")
    return out


REJECTIONS = {
    "binding_mismatch": ("cost_run.json", lambda t: t.replace(RUN_ID, "github-1-1")),
    "unsupported_source": ("cost_run.json", lambda t: t.replace("v0.10.46", "v0.10.47")),
    "currency_not_usd": ("infracost.json", lambda t: t.replace('"USD"', '"EUR"')),
    "invalid_decimal": ("infracost.json", lambda t: t.replace('"-106.58"', "-106.58", 1)),
    "cost_input_unreadable": ("infracost.json", lambda t: t[:-5]),
}


@pytest.mark.parametrize("code", sorted(REJECTIONS))
def test_rejected_input_publishes_a_fixed_code_and_no_amount(drift, priced, tmp_path, code):
    file, change = REJECTIONS[code]
    report, problems = analyse(drift, _tamper(priced, tmp_path, file, change))
    assert problems == []
    _assert_no_cost_claims(report, "rejected", code)
    assert report["cost"]["statements"][0]["text"] == (
        f"The cost estimate was rejected ({code}): monetary impact is not determinable from available evidence.")
    parsed = code != "cost_input_unreadable"  # hashes exist only once both documents parsed
    assert (report["provenance"]["cost_input_sha256"] is not None) is parsed


def test_duplicate_key_and_incomplete_directory_are_rejected(drift, priced, tmp_path):
    report, problems = analyse(drift, _tamper(priced, tmp_path, "cost_run.json",
                                              lambda t: t.replace('{\n', '{\n  "mode": "x",\n', 1)))
    assert problems == [] and report["cost"]["reason"] == "cost_input_unreadable"
    partial = tmp_path / "partial"
    partial.mkdir()
    (partial / "cost_run.json").write_text((priced / "cost_run.json").read_text(), encoding="utf-8")
    report, problems = analyse(drift, partial)
    assert problems == [] and report["cost"]["reason"] == "cost_input_incomplete"
    report, problems = analyse(drift, tmp_path / "missing")
    assert problems == [] and report["cost"]["reason"] == "cost_input_unreadable"


def test_cost_never_changes_drift_investigation_or_recommendation(drift, priced, tmp_path):
    before = copy.deepcopy(drift)
    reports = [analyse(drift, d)[0] for d in (None, priced, _tamper(priced, tmp_path, "infracost.json",
                                                                     lambda t: t.replace('"USD"', '"EUR"')))]
    assert drift == before

    def without_cost(report: dict) -> dict:
        return {"summary": report["summary"], "investigation": report["investigation"],
                "remediation": report["remediation"],
                "resources": [{k: v for k, v in r.items() if k != "cost"} for r in report["resources"]],
                "analysis": {k: v for k, v in report["analysis"].items() if k != "cost"}}

    assert without_cost(reports[0]) == without_cost(reports[1]) == without_cost(reports[2])


# --------------------------------------------------------------------------- LLM: direction only, conflicts rejected


def test_llm_receives_only_the_direction_never_an_amount(drift, priced):
    llm = CostLLM("likely_increase", summary="Cost goes up for this plan.")
    report, problems = analyse(drift, priced, llm)
    assert problems == []
    prompt = shown(llm)
    assert '"cost_estimate_direction": "increase"' in prompt
    for amount in AMOUNTS:
        assert amount not in prompt
    assert "USD" not in prompt and "$" not in prompt
    cost_keys = [k for k in report["llm"]["evidence_sent"] if "cost" in k["sections"]]
    assert cost_keys and all(k["estimate_direction"] == "increase" for k in cost_keys)
    assert all(k["estimate_direction"] is None for k in report["llm"]["evidence_sent"] if "cost" not in k["sections"])


def test_consistent_finding_is_published_with_the_deterministic_estimate(drift, priced):
    report, problems = analyse(drift, priced, CostLLM("likely_increase", summary="Cost goes up for this plan."))
    assert problems == []
    section = report["analysis"]["cost"]
    [finding] = section["findings"]
    assert (finding["direction"], finding["estimate_direction"]) == ("likely_increase", "increase")
    assert finding["estimate"] == {"attribution": "drift", "cost_status": "cost_line", "monthly_cost_delta": "106.58",
                                   "display": "+$106.58/month"}
    assert finding["monetary_impact"] == "estimated_list_price"
    # the free-text cost summary is withheld: the deterministic statements stand instead of it
    assert section["summary"] is None and section["reason"] == ca.SUMMARY_WITHHELD


@pytest.mark.parametrize("direction", ["likely_decrease", "likely_neutral"])
def test_conflicting_finding_is_rejected_and_never_published(drift, priced, direction):
    explanation = "The plan became cheaper after this change."
    report, problems = analyse(drift, priced, CostLLM(direction, explanation=explanation))
    assert problems == []
    section = report["analysis"]["cost"]
    assert section["findings"] == [] and section["rejection_reasons"] == {"direction_conflicts_with_estimate": 1}
    assert explanation not in json.dumps(report) and explanation not in render_markdown(report)
    assert report["resources"][0]["cost"]["monthly_cost_delta"] == "106.58"  # the deterministic estimate stands


def test_without_cost_the_llm_direction_stays_inference_and_the_summary_is_kept(drift):
    report, problems = analyse(drift, None, CostLLM("likely_decrease", summary="Cost may go down."))
    assert problems == []
    section = report["analysis"]["cost"]
    [finding] = section["findings"]
    assert (finding["estimate_direction"], finding["estimate"], finding["monetary_impact"]) == (
        "not_determinable", None, "not_determinable_from_evidence")
    assert section["summary"] == "Cost may go down." and section["reason"] is None


def test_amount_in_llm_text_is_still_rejected(drift, priced):
    report, problems = analyse(drift, priced, CostLLM(explanation="This costs about $106.58 more per month."))
    assert problems == [] and report["analysis"]["cost"]["rejection_reasons"] == {"unsupported_cost_claim": 1}


# --------------------------------------------------------------------------- verifier: tampering is caught


def _tampered_problems(drift, directory, mutate, llm=None) -> list[str]:
    cost, check = cost_args(directory, drift)
    state = run_analysis(drift, llm=llm, cost=cost) if llm else run_analysis(drift, cost=cost)
    report = json.loads(json.dumps(state["report"]))
    mutate(report)
    return verify.verify_report(report, drift, None, check)


TAMPERING = {
    "resource_amount": lambda r: r["resources"][0]["cost"].update(monthly_cost_delta="1.00"),
    "embedded_total": lambda r: r["cost"]["cost_delta"]["totals"]["confirmed_drift"].update(monthly_cost_delta="1"),
    "statement_text": lambda r: r["cost"]["statements"][1].update(text="Confirmed drift: +$1.00/month."),
    "resource_statement": lambda r: r["resources"][0]["cost"]["statements"][0].update(text="Free."),
    "attribution": lambda r: r["resources"][0]["cost"].update(attribution="configuration"),
    "limitation_removed": lambda r: r["limitations"].remove(next(
        line for line in r["limitations"] if line.startswith("Cost figures are"))),
    "no_pricing_added": lambda r: r["limitations"].append(NO_PRICING_LIMITATION),
    "input_hash": lambda r: r["provenance"]["cost_input_sha256"].update(infracost="0" * 64),
    "version": lambda r: r["provenance"]["versions"].update(cost_delta=None),
}


@pytest.mark.parametrize("name", sorted(TAMPERING))
def test_verifier_catches_tampered_cost(drift, priced, name):
    assert _tampered_problems(drift, priced, TAMPERING[name])


def test_verifier_catches_tampered_direction_and_estimate(drift, priced):
    llm = CostLLM("likely_increase")

    def direction(r):
        r["llm"]["evidence_sent"][0]["estimate_direction"] = "decrease"
    assert _tampered_problems(drift, priced, direction, llm)

    def estimate(r):
        r["analysis"]["cost"]["findings"][0]["estimate"]["monthly_cost_delta"] = "1.00"
    assert _tampered_problems(drift, priced, estimate, CostLLM("likely_increase"))

    def summary(r):
        r["analysis"]["cost"].update(summary="Costs go up.", reason=None)
    assert _tampered_problems(drift, priced, summary, CostLLM("likely_increase"))


def test_verifier_rejects_a_report_whose_cost_does_not_match_its_input(drift, priced, tmp_path):
    report, _ = analyse(drift, priced)
    assert verify.verify_report(report, drift, None, None)  # claims complete, but no cost input was given
    rejected, _ = analyse(drift, tmp_path / "missing")
    assert verify.verify_report(rejected, drift, None, None)  # rejected, but not provided
    # an amount slipped into a not_available report is caught by the schema or the verifier
    plain, _ = analyse(drift)
    plain["cost"]["statements"][0]["text"] = "No cost estimate was provided: about $10 per month."
    assert verify.verify_report(plain, drift, None, None)


# --------------------------------------------------------------------------- contract, determinism, Markdown


def test_contract_validators_enforce_the_status_rules(drift, priced):
    report, _ = analyse(drift, priced)
    cost = report["cost"]
    for broken in ({**cost, "cost_delta": None}, {**cost, "pricing_source": None},
                   {**cost, "status": "not_available", "reason": "cost_input_not_provided"},
                   {**cost, "status": "rejected", "reason": "made_up", "cost_delta": None, "pricing_source": None,
                    "monetary_impact": "not_determinable_from_evidence", "statements": cost["statements"][:1]}):
        with pytest.raises(ValueError):
            CostImpact.model_validate(broken)
    plain, _ = analyse(drift)
    plain["resources"][0]["cost"] = report["resources"][0]["cost"]  # an amount without a complete cost
    with pytest.raises(ValueError):
        AiAnalysisReport.model_validate(plain)


def test_report_is_deterministic_and_markdown_has_the_cost_section(drift, priced):
    first, _ = analyse(drift, priced)
    second, _ = analyse(drift, priced)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    markdown = render_markdown(first)
    assert markdown == render_markdown(second)
    section = markdown.split("## Cost impact (estimate)")[1].split("## Recommendation & options")[0]
    assert "Not actual Azure billing" in section and "106\\.58 USD per month" in section
    assert "- Cost estimate: **complete**" in markdown
    plain = render_markdown(analyse(drift)[0])
    section = plain.split("## Cost impact (estimate)")[1].split("## Recommendation & options")[0]
    assert "$" not in section.replace("`cost_delta`", "") and "not determinable" in section


def test_a_cost_document_bound_to_another_report_is_an_internal_error(drift, priced):
    other = copy.deepcopy(drift)
    other["resources"][0]["notes"] = ["changed"]  # same run, different canonical hash
    cost, _ = cost_args(priced, drift)
    with pytest.raises(ValueError, match="another drift report"):
        run_analysis(other, cost=cost)


# --------------------------------------------------------------------------- CLI


def test_cli_cost_option(drift, priced, tmp_path, monkeypatch, capsys):
    from ai_engine import cli

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("AI_LLM_PROVIDER", "none")
    report_path = tmp_path / "drift_report.json"
    report_path.write_text(json.dumps(drift), encoding="utf-8")
    assert cli.main(["--report", str(report_path), "--cost", str(priced), "--output-dir", str(tmp_path / "a")]) == 0
    out, err = capsys.readouterr()
    assert "cost complete" in out and err == ""
    data = json.loads((tmp_path / "a" / "ai_analysis_report.json").read_text(encoding="utf-8"))
    assert data["cost"]["status"] == "complete"
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "cost_run.json").write_text("{}", encoding="utf-8")
    assert cli.main(["--report", str(report_path), "--cost", str(bad), "--output-dir", str(tmp_path / "b")]) == 0
    out, err = capsys.readouterr()
    assert "cost rejected (cost_input_incomplete)" in err and str(bad) not in err and "{}" not in err
    assert "cost rejected" in out  # the stdout summary line carries the status only
    assert json.loads((tmp_path / "b" / "ai_analysis_report.json").read_text())["cost"]["reason"] == \
        "cost_input_incomplete"


# --------------------------------------------------------------------------- remaining statement and input paths


def _write_documents(directory: Path, infracost: dict, cost_run: dict) -> Path:
    directory.mkdir()
    (directory / "infracost.json").write_text(json.dumps(infracost), encoding="utf-8")
    (directory / "cost_run.json").write_text(json.dumps(cost_run), encoding="utf-8")
    return directory


def test_only_non_drift_cost_gives_the_no_drift_cost_statement(drift, priced, tmp_path):
    configured = copy.deepcopy(drift)
    item = configured["resources"][1]
    assert item["address"] == PLAN
    item.update(classification="config_change", drift_action=None, drift_actions=None)
    documents = ca.read_cost_documents(priced)
    cost_run = {**documents["cost_run"], "drift_report_sha256": canonical_sha256(configured)}
    report, problems = analyse(configured, _write_documents(tmp_path / "c", documents["infracost"], cost_run))
    assert problems == []
    ids = [s["id"] for s in report["cost"]["statements"]]
    assert ids == ["cost.status_complete.v1", "cost.no_drift_cost.v1", "cost.group.v1", "cost.plan_delta.v1"]
    assert report["cost"]["statements"][2]["text"].startswith("Pending configuration changes (not drift cost): "
                                                              "+$106.58/month")
    assert report["cost"]["cost_delta"]["totals"]["confirmed_drift"]["monthly_cost_delta"] is None


def test_reconciliation_residual_gets_its_own_statement(drift, priced, tmp_path):
    documents = ca.read_cost_documents(priced)
    infracost = copy.deepcopy(documents["infracost"])
    infracost["projects"][0]["diff"]["totalMonthlyCost"] = "-100"
    report, problems = analyse(drift, _write_documents(tmp_path / "r", infracost, documents["cost_run"]))
    assert problems == []
    assert report["cost"]["statements"][-1] == {"id": "cost.reconciliation.v1", "text": (
        "Infracost's totals do not reconcile with its resource lines (2 check(s) differ, 0 line(s) without an "
        "amount); $0.00/month (0.00 USD per month) of the plan total is unattributed and reported as unreconciled.")}
    assert report["cost"]["cost_delta"]["reconciliation"]["status"] == "residual"


def test_oversize_input_is_unreadable_and_load_cost_input_matches_the_cli_path(drift, priced, monkeypatch):
    assert ca.load_cost_input(priced, drift) == cost_args(priced, drift)[0]
    monkeypatch.setattr(ca, "MAX_COST_FILE_BYTES", 10)
    assert ca.read_cost_documents(priced) == "cost_input_unreadable"
    assert ca.load_cost_input(priced, drift) == ca.rejected_cost("cost_input_unreadable")


@pytest.mark.parametrize("cost", [
    {"status": "unknown", "reason": None, "cost_delta": None, "input_sha256": None},
    {"status": "complete", "reason": None, "cost_delta": {"cost_delta_version": "1"}, "input_sha256": None},
    {"status": "rejected", "reason": "made_up_code", "cost_delta": None, "input_sha256": None},
    {"status": "not_available", "reason": "binding_mismatch", "cost_delta": None, "input_sha256": None},
], ids=["status", "invalid_document", "unknown_code", "reason_mismatch"])
def test_an_inconsistent_cost_input_is_an_internal_error_not_a_result(drift, cost):
    with pytest.raises(ValueError):
        run_analysis(drift, cost=cost)


# --------------------------------------------------------------------------- contract guards, one by one


def test_cost_finding_contract_guards(drift, priced):
    from ai_engine.nodes.report_generator import CostReportFinding

    report, _ = analyse(drift, priced, CostLLM("likely_increase"))
    finding = report["analysis"]["cost"]["findings"][0]
    CostReportFinding.model_validate(finding)
    for broken in ({**finding, "estimate_direction": "decrease"},  # not the sign of the estimate
                   {**finding, "monetary_impact": "not_determinable_from_evidence"},  # an amount exists
                   {**finding, "direction": "likely_decrease"}):  # contradicts the authoritative direction
        with pytest.raises(ValueError):
            CostReportFinding.model_validate(broken)
    without = copy.deepcopy(report)
    without["analysis"]["cost"]["findings"][0].update(estimate=None, estimate_direction="not_determinable",
                                                      monetary_impact="not_determinable_from_evidence")
    with pytest.raises(ValueError):  # a complete cost, but the finding carries no estimate
        AiAnalysisReport.model_validate(without)


def test_cost_block_contract_guards(drift, priced, tmp_path):
    complete = analyse(drift, priced)[0]["cost"]
    rejected = analyse(drift, tmp_path / "missing")[0]["cost"]
    for broken in ({**complete, "monetary_impact": "not_determinable_from_evidence"},
                   {**rejected, "status": "not_available"},  # reason cost_input_unreadable does not fit
                   {**rejected, "statements": rejected["statements"] * 2}):
        with pytest.raises(ValueError):
            CostImpact.model_validate(broken)
    with pytest.raises(ValueError, match="cost must be"):
        run_analysis(drift, cost={})


def test_verifier_checks_the_cost_binding_against_provenance(drift, priced):
    problems = _tampered_problems(drift, priced, lambda r: r["provenance"].update(run_id="github-1-1"))
    assert "cost: the cost_delta binding differs from the report provenance" in problems
