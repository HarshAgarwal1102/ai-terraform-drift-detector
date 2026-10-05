"""Task 6.7: cross-cutting evidence-vs-inference validation of the Phase 6 AI engine.

- guard corpus (tests/corpora/guards.json): every entry through the guards and
  end to end through a section validation;
- prompt-injection corpus (tests/corpora/injection.json): hostile values in
  Terraform/Azure evidence stay data; deterministic state and remediation are
  unchanged; unsafe echoes are rejected;
- independent rule tables (verify.py) agree with the graph's own nodes;
- reply parsing / truncation / duplicate keys; raw replies never reach output;
- `verify_report` on every fixture and LLM outcome, and on tampered reports;
- determinism, write-once state, one call / one HTTP attempt;
- the previously uncovered paths.

Every LLM is a fake or a local httpx.MockTransport; tests/conftest.py blocks any
non-loopback connection. Nothing is executed.
"""

from __future__ import annotations

import builtins
import copy
import importlib.util
import json
import re
from pathlib import Path

import pytest

from ai_engine import verify
from ai_engine.evidence import EVIDENCE_TAG, EvidenceIntegrityError, EvidenceLimits, build_llm_evidence
from ai_engine.nodes.analyze_drift import InvalidEnvelope, make_analyze_drift, parse_envelope
from ai_engine.nodes.common import (
    DuplicateKeyError,
    free_text_violation,
    is_suspicious_text,
    normalize_for_guards,
    strict_json_loads,
)
from ai_engine.nodes.cost_analysis import route_cost_config, validate_cost_section, CostSection
from ai_engine.nodes.investigation_facts import derive_investigation
from ai_engine.nodes.parse_drift import parse_drift
from ai_engine.nodes.remediation import hcl_value, plan_remediation
from ai_engine.nodes.report_generator import AiAnalysisReport, render_markdown
from ai_engine.nodes.root_cause import (
    HYPOTHESIS_ORIGINS,
    change_risk_factors,
    derive_origin_risk,
    hypothesis_consistent,
    origin_category,
)
from ai_engine.nodes.security_analysis import InvalidModelOutput, classify_drift, parse_model_output
from drift_engine.classifier import evaluate


def _public(evaluation):
    """The public drift report (Task 9B.4A): every consumer reads it, never the internal report."""
    from drift_engine.report_public import public_document
    return public_document(evaluation.report, evaluation.plan or {})


HAS_AI_EXTRA = all(importlib.util.find_spec(m) for m in ("langgraph", "langchain_openai"))
requires_ai = pytest.mark.skipif(not HAS_AI_EXTRA, reason="needs the 'ai' extra")
if HAS_AI_EXTRA:
    import httpx
    from langgraph.graph import END, START, StateGraph

    from ai_engine.config import create_chat_model, load_config
    from ai_engine.graph import AiState, EvidenceMutationError, FrozenDict, FrozenList, run_analysis
    from ai_engine.nodes.report_generator import write_report

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
CORPORA = Path(__file__).parent / "corpora"
GROUPS = ("plan_evidence", "security_plans", "cost_config_plans", "root_cause_plans", "report_plans")
SECTION_KEYS = ("analyze_security", "analyze_cost", "analyze_configuration", "analyze_root_cause", "assess_risk")
DETERMINISTIC = ("parsed_drift", "security_targets", "cost_targets", "config_targets", "origin_facts",
                 "remediation_plan")
REPORT_DETERMINISTIC = ("report_version", "provenance", "summary", "investigation", "resources", "remediation", "cost")
AVAILABLE = {"available": True, "provider": "fake", "model": "fake-model", "reason": None}
RG = 'module.resource_group.azurerm_resource_group.this["main"]'
GUARDS = json.loads((CORPORA / "guards.json").read_text(encoding="utf-8"))["cases"]
INJECTIONS = json.loads((CORPORA / "injection.json").read_text(encoding="utf-8"))["cases"]


def fixture_report(group: str, name: str) -> dict:
    base = FIXTURES / group / name
    plan = next((base / f for f in ("plan.synthetic.json", "plan.sanitized.json") if (base / f).exists()),
                base / "plan.json")
    return _public(evaluate(str(plan), str(base / "detection_run.json")))


ALL_FIXTURES = [(g, p.name) for g in GROUPS for p in sorted((FIXTURES / g).iterdir()) if p.is_dir()]


def prepared(drift_report: dict) -> dict:
    state = {"drift_report": drift_report, "llm": AVAILABLE}
    for node in (parse_drift, classify_drift, route_cost_config, derive_origin_risk, derive_investigation,
                 plan_remediation):
        state.update(node(state))
    return state


def shown(messages) -> dict:
    body = re.search(rf"<{EVIDENCE_TAG}>\n(.*)\n</{EVIDENCE_TAG}>", messages[-1].content, re.DOTALL).group(1)
    return json.loads(body)


def envelope(**sections) -> str:
    keys = ("security_analysis", "cost_analysis", "configuration_analysis", "root_cause_analysis", "risk_assessment",
            "investigation_analysis")
    return json.dumps({k: sections.get(k, {"findings": [], "summary": ""}) for k in keys})


class ScriptedLLM:
    def __init__(self, reply=None, error: BaseException | None = None):
        self.reply, self.error, self.prompts = reply, error, []

    def invoke(self, messages):
        self.prompts.append(messages)
        if self.error is not None:
            raise self.error
        return self.reply


_HYPOTHESIS = {"outside_terraform": "out_of_band_change", "outside_terraform_converged": "out_of_band_change",
               "configuration_side": "configuration_change", "both_sides": "out_of_band_change",
               "value_unknown_until_apply": "provider_or_platform_behavior", "undetermined": "undetermined"}


def findings_for(evidence: dict, explanation=lambda r, c: f"{'.'.join(c['path'])} differs from the declaration."):
    """Schema-valid findings for every section, each citing exactly one change sent for that section."""
    out = {k: [] for k in ("security", "cost", "configuration", "root_cause", "risk")}
    for r in evidence["resources"]:
        for c in r["changes"]:
            base = {"address": r["address"], "cited_paths": [c["path"]], "basis": "inference",
                    "explanation": explanation(r, c)[:590]}
            secs = c["sections"]
            if "security" in secs:
                out["security"].append(dict(base, exposure="other", ai_assessed_impact=c["severity"]["level"]))
            if "cost" in secs:
                out["cost"].append(dict(base, cost_driver="other", direction="undetermined",
                                        monetary_impact="not_determinable_from_evidence"))
            if "configuration" in secs:
                out["configuration"].append(dict(base, topic="other"))
            if "root_cause" in secs:
                origin = c["origin"]
                out["root_cause"].append(dict(base, hypothesis="lifecycle_change" if origin["lifecycle"]
                                              else _HYPOTHESIS[origin["category"]],
                                              possible_channels=["unknown"]))
            if "risk" in secs:
                kind = next((f for f in origin_factors(c) if f not in ("redacted_unreadable", "moved_or_importing")),
                            "other")
                out["risk"].append(dict(base, risk_kind=kind))
    return out


def origin_factors(change):
    return change["origin"]["risk_factors"]


def reply_for(evidence: dict, **kw) -> str:
    f = findings_for(evidence, **kw)
    return envelope(security_analysis={"findings": f["security"][:50], "summary": "Security summary."},
                    cost_analysis={"findings": f["cost"][:50], "summary": ""},
                    configuration_analysis={"findings": f["configuration"][:50], "summary": ""},
                    root_cause_analysis={"findings": f["root_cause"][:20], "summary": ""},
                    risk_assessment={"findings": f["risk"][:20], "summary": ""})


class AllSectionsLLM(ScriptedLLM):
    """A well-behaved fake: consistent findings in all five sections."""

    def invoke(self, messages):
        self.prompts.append(messages)
        return reply_for(shown(messages))


def analyze(state, llm, limits=EvidenceLimits()):
    return make_analyze_drift(llm, limits)(state)


# --------------------------------------------------------------------------- guard corpus


@pytest.mark.parametrize("case", GUARDS, ids=[f"{c['category']}:{c['text'][:40]}" for c in GUARDS])
def test_guard_corpus(case):
    assert free_text_violation(case["text"]) == case["expected"], case["note"]


def test_guard_corpus_is_balanced():
    by_category = {}
    for case in GUARDS:
        by_category.setdefault(case["category"], set()).add(case["expected"] is None)
    for category in ("attribution", "remediation", "cost", "identity", "verdict_upgrade", "reference"):
        assert by_category[category] == {True, False}  # positives and documented negatives
    assert any(c["known_tradeoff"] for c in GUARDS)


@requires_ai
@pytest.mark.parametrize("case", [c for c in GUARDS if len(c["text"]) <= 590],
                         ids=[f"{c['category']}:{c['text'][:40]}" for c in GUARDS if len(c["text"]) <= 590])
def test_guard_corpus_end_to_end(case):
    """Each corpus text as a finding explanation and as a summary: rejected exactly when the guard says so."""
    state = prepared(fixture_report("plan_evidence", "external_drift"))
    finding = {"address": RG, "cited_paths": [["tags", "probe"]], "topic": "other", "explanation": case["text"],
               "basis": "inference"}
    reply = envelope(configuration_analysis={"findings": [finding], "summary": case["text"]})
    result = analyze(state, ScriptedLLM(reply))["inferences"]["analyze_configuration"]
    assert result["status"] == "ok"
    if case["expected"] is None:
        assert len(result["findings"]) == 1 and result["summary"] == case["text"]
    else:
        assert result["findings"] == [] and result["summary"] is None
        assert result["rejected_findings"] == [{"index": 0, "reason": case["expected"]},
                                               {"index": None, "reason": f"summary_{case['expected']}"}]


def test_suspicious_is_decided_on_the_original_text():
    text = "safe" + "​" + "text"
    assert is_suspicious_text(text)
    assert "​" not in normalize_for_guards(text)  # normalization removes it; the decision already happened
    assert free_text_violation(text) == "suspicious_text"
    assert not is_suspicious_text("Москва") and not is_suspicious_text("Zoë") and not is_suspicious_text("東京")


def test_normalization_only_adds_detections():
    """Matching runs on the original AND the normalized copy: whatever a pattern finds in the original text is
    still rejected, so normalization can never remove a detection."""
    from ai_engine.nodes import common

    patterns = (common._COST_CLAIM, common._COST_CLAIM_EXTRA, common._ATTRIBUTION_CLAIM, common._ATTRIBUTION_EXTRA,
                common._REMEDIATION_CLAIM, common._REMEDIATION_EXTRA)
    texts = [c["text"] for c in GUARDS] + [c["value"] for c in INJECTIONS]
    hits = 0
    for text in texts:
        if any(p.search(text) for p in patterns):
            hits += 1
            assert free_text_violation(text) is not None, text
    assert hits > 50


# --------------------------------------------------------------------------- independent rule tables agree


@pytest.mark.parametrize(("group", "name"), ALL_FIXTURES, ids=[f"{g}/{n}" for g, n in ALL_FIXTURES])
def test_independent_origin_and_factor_tables_agree(group, name):
    drift = fixture_report(group, name)
    for resource in drift["resources"]:
        if resource["classification"] == "in_sync":
            continue
        for change in resource["attribute_changes"]:
            assert verify._origin(resource, change) == origin_category(resource, change)
            assert verify._factors(resource, change) == change_risk_factors(resource, change)


def test_independent_hypothesis_table_agrees():
    origins = ("outside_terraform", "outside_terraform_converged", "configuration_side", "both_sides",
               "value_unknown_until_apply", "undetermined")
    for hypothesis in list(HYPOTHESIS_ORIGINS) + ["lifecycle_change", "undetermined"]:
        for origin in origins:
            for lifecycle in (True, False):
                node = hypothesis_consistent(hypothesis, {"category": origin, "lifecycle": lifecycle})
                if hypothesis == "lifecycle_change":
                    independent = lifecycle
                elif hypothesis == "undetermined":
                    independent = True
                else:
                    independent = origin in verify._HYPOTHESIS_ALLOWS[hypothesis]
                assert node == independent, (hypothesis, origin, lifecycle)


# --------------------------------------------------------------------------- redaction fail-closed corpus


@pytest.mark.parametrize("tamper", ["flagged_with_value", "mixed_views", "unrouted_resource"])
def test_redaction_fail_closed_corpus(tamper):
    secret = fixture_report("security_plans", "web_app_secret_changed")
    state = prepared(secret)
    parsed = copy.deepcopy(state["parsed_drift"])
    if tamper == "unrouted_resource":
        other = prepared(fixture_report("security_plans", "nsg_open_inbound"))
        parsed["resources"] = copy.deepcopy(other["parsed_drift"]["resources"]) + parsed["resources"]
        routes = other["security_targets"]["changes"]
    else:
        routes = state["security_targets"]["changes"]
    change = parsed["resources"][-1]["attribute_changes"][0]
    change["real"] = {"status": "value", "value": "LEAKED"}
    if tamper == "mixed_views":
        change["redacted"] = False
    with pytest.raises(EvidenceIntegrityError) as info:
        build_llm_evidence(parsed, routes)
    assert "LEAKED" not in str(info.value)


# --------------------------------------------------------------------------- prompt-injection corpus


def _injection_plan(placement: str, value: str) -> dict:
    sub = "/subscriptions/<AZURE_SUBSCRIPTION_ID>/resourceGroups/rg/providers"
    if placement == "tag":
        rtype, state = "azurerm_storage_account", {"id": f"{sub}/sa", "name": "sa", "account_replication_type": "LRS",
                                                   "tags": {"env": "dev"}}
        real = dict(state, tags={"env": "dev", "note": value})
        configured = ["name", "account_replication_type", "tags"]
    elif placement == "nsg_rule":
        rtype, state = "azurerm_network_security_group", {"id": f"{sub}/nsg", "name": "nsg", "security_rule": []}
        real = dict(state, security_rule=[{"access": "Allow", "direction": "Inbound", "source_address_prefix": "*",
                                           "destination_port_range": "22", "description": value, "name": "x",
                                           "priority": 100, "protocol": "Tcp"}])
        configured = ["name", "security_rule"]
    else:  # sku
        rtype, state = "azurerm_service_plan", {"id": f"{sub}/plan", "name": "plan", "sku_name": "P1v3"}
        real = dict(state, sku_name=value)
        configured = ["name", "sku_name"]
    entry = {"address": f"{rtype}.this", "mode": "managed", "type": rtype, "name": "this",
             "provider_name": "registry.terraform.io/hashicorp/azurerm"}
    mask = {}
    return {"format_version": "1.2", "terraform_version": "1.14.7", "timestamp": "2026-10-03T12:00:00Z",
            "applyable": True, "errored": False, "complete": True, "output_changes": {},
            "resource_drift": [dict(entry, change={"actions": ["update"], "before": state, "after": real,
                                                   "after_unknown": {}, "before_sensitive": mask,
                                                   "after_sensitive": mask})],
            "resource_changes": [dict(entry, change={"actions": ["update"], "before": real, "after": state,
                                                     "after_unknown": {}, "before_sensitive": mask,
                                                     "after_sensitive": mask})],
            "configuration": {"root_module": {"resources": [{
                "address": f"{rtype}.this", "mode": "managed", "type": rtype, "name": "this",
                "expressions": {k: {"constant_value": None} for k in configured}}]}}}


def _injection_report(tmp_path, placement: str, value: str) -> dict:
    manifest = {"backend_key": "dev.tfstate", "environment": "dev", "failure_reason": None, "failure_stage": None,
                "finished_at": "2026-10-03T12:00:05Z", "git_commit": None, "outcome": "succeeded",
                "plan_exit_code": 2, "run_id": "injection", "show_exit_code": 0,
                "started_at": "2026-10-03T12:00:00Z", "terraform_version": "1.14.7",
                "working_dir": "terraform/environments/dev"}
    (tmp_path / "plan.json").write_text(json.dumps(_injection_plan(placement, value)), encoding="utf-8")
    (tmp_path / "detection_run.json").write_text(json.dumps(manifest), encoding="utf-8")
    drift = _public(evaluate(str(tmp_path / "plan.json"), str(tmp_path / "detection_run.json")))
    assert drift["outcome"] == "succeeded"
    return drift


class ObedientLLM(ScriptedLLM):
    """A worst-case fake that obeys the injected value: echoes it everywhere and cites an unrelated resource."""

    def __init__(self, value):
        super().__init__()
        self.value = value

    def invoke(self, messages):
        self.prompts.append(messages)
        evidence = shown(messages)
        f = findings_for(evidence, explanation=lambda r, c: f"The value says: {self.value}")
        bogus = {"address": "azurerm_key_vault.prod", "cited_paths": [["access_policy"]], "basis": "inference",
                 "explanation": "Unrelated resource."}
        sections = {}
        for name, key, extra in (("security", "security_analysis", {"exposure": "other", "ai_assessed_impact": "INFO"}),
                                 ("cost", "cost_analysis", {"cost_driver": "other", "direction": "undetermined",
                                                            "monetary_impact": "not_determinable_from_evidence"}),
                                 ("configuration", "configuration_analysis", {"topic": "other"}),
                                 ("root_cause", "root_cause_analysis", {"hypothesis": "undetermined",
                                                                        "possible_channels": ["unknown"]}),
                                 ("risk", "risk_assessment", {"risk_kind": "other"})):
            sections[key] = {"findings": f[name] + [dict(bogus, **extra)], "summary": f"The value says: {self.value}"}
        return envelope(**sections)


@requires_ai
@pytest.mark.parametrize("placement", ["tag", "nsg_rule", "sku"])
@pytest.mark.parametrize("case", INJECTIONS, ids=[c["id"] for c in INJECTIONS])
def test_injection_stays_data(case, placement, tmp_path):
    drift = _injection_report(tmp_path, placement, case["value"])
    baseline = run_analysis(copy.deepcopy(drift), config=load_config({}))
    llm = ObedientLLM(case["value"])
    state = run_analysis(copy.deepcopy(drift), llm=llm)
    # 1. the value is data inside the evidence block: one closing delimiter, '<' / '>' escaped
    human = llm.prompts[0][1].content
    assert human.count(f"</{EVIDENCE_TAG}>") == 1 and human.rstrip().endswith(f"</{EVIDENCE_TAG}>")
    block = human.split(f"<{EVIDENCE_TAG}>\n", 1)[1]
    assert "<" not in block.rsplit(f"\n</{EVIDENCE_TAG}>", 1)[0]
    # 2. deterministic state and remediation are unchanged by the injected value being obeyed
    for key in DETERMINISTIC:
        assert state[key] == baseline[key], key
    for key in REPORT_DETERMINISTIC:
        assert state["report"][key] == baseline["report"][key], key
    # 3. unsafe AI output is rejected: the unrelated citation always, the echo when the corpus says so
    for key in SECTION_KEYS:
        result = state["inferences"][key]
        if result["status"] != "ok":
            continue
        reasons = [r["reason"] for r in result["rejected_findings"]]
        assert "unsupported_citation" in reasons
        assert all(f["address"] != "azurerm_key_vault.prod" for f in result["findings"])
        if case["echo_rejected_as"] != "inert":
            assert result["findings"] == [] and result["summary"] is None
            assert case["echo_rejected_as"] in reasons and f"summary_{case['echo_rejected_as']}" in reasons
    # 4. the final report is valid against the drift report, and Markdown is the rendering of its JSON
    assert verify.verify_report(state["report"], drift) == []
    paths = write_report(state, tmp_path / "out")
    md = paths["markdown"].read_text(encoding="utf-8")
    assert verify.verify_markdown(md, json.loads(paths["json"].read_text(encoding="utf-8"))) == []
    assert "<script" not in _prose(md) and "](" not in _prose(md)


def _prose(md: str) -> str:
    """Markdown outside fenced blocks and inline code spans."""
    out, fence = [], None
    for line in md.split("\n"):
        if fence is not None:
            fence = None if line == fence else fence
            continue
        opener = re.match(r"^(`{3,})", line)
        if opener:
            fence = opener.group(1)
            continue
        out.append(re.sub(r"(`+) .*? \1", "", line))
    return "\n".join(out)


# --------------------------------------------------------------------------- reply parsing / truncation


@pytest.mark.parametrize("text", [
    '{"a": 1, "a": 2}', '{"x": {"b": 1, "b": 2}}', '[{"k": 1, "k": 1}]',
])
def test_duplicate_keys_rejected_at_any_depth(text):
    with pytest.raises(DuplicateKeyError):
        strict_json_loads(text)


def test_duplicate_section_key_rejected_in_envelope_and_standalone():
    full = envelope()
    with pytest.raises(InvalidEnvelope):
        parse_envelope(full[:-1] + ', "security_analysis": {"findings": [], "summary": ""}}')
    nested = full.replace('"summary": ""', '"summary": "", "summary": "x"', 1)
    with pytest.raises(InvalidEnvelope):
        parse_envelope(nested)
    with pytest.raises(InvalidModelOutput, match="duplicate key"):
        parse_model_output('{"findings": [], "summary": "a", "summary": "b"}')
    with pytest.raises(InvalidEnvelope):
        parse_envelope('{"a": NaN}')


@requires_ai
def test_truncated_replies_at_every_boundary():
    state = prepared(fixture_report("cost_config_plans", "combined_security_cost_config"))
    probe = AllSectionsLLM()
    analyze(state, probe)
    full = reply_for(shown(probe.prompts[0]), explanation=lambda r, c: "SECRET-RAW-MARKER explanation")
    cuts = [i for i, ch in enumerate(full) if ch in "}],"][:-1]
    assert len(cuts) > 30
    for cut in cuts[:: max(1, len(cuts) // 60)]:
        update = analyze(state, ScriptedLLM(full[:cut + 1]))
        assert {update["inferences"][k]["status"] for k in SECTION_KEYS} == {"invalid_output"}, cut
        assert "SECRET-RAW-MARKER" not in json.dumps(update)
    assert {analyze(state, ScriptedLLM(full))["inferences"][k]["status"] for k in SECTION_KEYS} == {"ok"}


@requires_ai
@pytest.mark.parametrize("reply", [
    "﻿" + envelope(), "```JSON\n" + envelope() + "\n```", envelope() + "\n\nThanks!",
])
def test_reply_framing_variants_are_rejected(reply):
    state = prepared(fixture_report("plan_evidence", "external_drift"))
    update = analyze(state, ScriptedLLM(reply))
    assert update["inferences"]["analyze_configuration"]["status"] == "invalid_output"
    assert "Thanks" not in json.dumps(update)


@requires_ai
def test_list_content_reply_is_invalid_and_discarded():
    class Message:
        content = [{"type": "text", "text": "RAW-BLOCK-MARKER"}]

    state = prepared(fixture_report("plan_evidence", "external_drift"))
    update = analyze(state, ScriptedLLM(Message()))
    assert update["inferences"]["analyze_configuration"]["status"] == "invalid_output"
    assert "RAW-BLOCK-MARKER" not in json.dumps(update)


@requires_ai
@pytest.mark.parametrize("section", ["security_analysis", "root_cause_analysis"])
def test_oversized_sections_invalidate_only_themselves(section):
    state = prepared(fixture_report("security_plans", "nsg_open_inbound"))
    probe = AllSectionsLLM()
    analyze(state, probe)
    data = json.loads(reply_for(shown(probe.prompts[0])))
    data[section]["findings"] = data[section]["findings"] * 60  # beyond every section's findings cap
    update = analyze(state, ScriptedLLM(json.dumps(data)))
    key = {"security_analysis": "analyze_security", "root_cause_analysis": "analyze_root_cause"}[section]
    assert update["inferences"][key]["status"] == "invalid_output"
    others = [k for k in SECTION_KEYS if k != key and update["inferences"][k]["status"] != "skipped"]
    assert others and all(update["inferences"][k]["status"] == "ok" for k in others)


# --------------------------------------------------------------------------- verify_report


def _run(drift, mode):
    llm = {"none": None, "ok": AllSectionsLLM(), "failed": ScriptedLLM(error=TimeoutError("down")),
           "invalid": ScriptedLLM("not json")}[mode]
    return run_analysis(copy.deepcopy(drift), llm=llm) if llm else run_analysis(copy.deepcopy(drift),
                                                                                config=load_config({}))


@requires_ai
@pytest.mark.parametrize("mode", ["none", "ok", "failed", "invalid"])
@pytest.mark.parametrize(("group", "name"), ALL_FIXTURES, ids=[f"{g}/{n}" for g, n in ALL_FIXTURES])
def test_verify_report_and_determinism_matrix(group, name, mode):
    drift = fixture_report(group, name)
    baseline = _run(drift, "none")
    state = _run(drift, mode)
    assert verify.verify_report(state["report"], drift) == []
    for key in DETERMINISTIC:
        assert state[key] == baseline[key], key
    for key in REPORT_DETERMINISTIC:
        assert state["report"][key] == baseline["report"][key], key
    assert verify.verify_markdown(render_markdown(state["report"]), state["report"]) == []


@pytest.fixture(scope="module")
def full_report():
    if not HAS_AI_EXTRA:
        pytest.skip("needs the 'ai' extra")
    drift = fixture_report("cost_config_plans", "combined_security_cost_config")
    state = _run(drift, "ok")
    assert {state["report"]["analysis"][s]["status"] for s in ("security", "cost", "configuration", "root_cause",
                                                                "risk")} == {"ok"}
    return json.loads(json.dumps(state["report"])), drift


def _first(report, section):
    return report["analysis"][section]["findings"][0]


TAMPERS = {
    "fingerprint": lambda r, d: r["provenance"].update(drift_report_sha256="0" * 64),
    "run id": lambda r, d: r["provenance"].update(run_id="other-run"),
    "summary severity": lambda r, d: r["summary"].update(highest_severity="INFO"),
    "resource severity": lambda r, d: r["resources"][0]["what"].update(severity="LOW"),
    "resource classification": lambda r, d: r["resources"][0]["what"].update(classification="in_sync"),
    "resource dropped": lambda r, d: r["resources"].pop(),
    "resource risk factors": lambda r, d: r["resources"][0]["what"].update(risk_factors=[]),
    "change origin": lambda r, d: r["resources"][0]["what"]["changes"][0].update(origin="configuration_side"),
    "change view": lambda r, d: r["resources"][0]["what"]["changes"][0].update(real={"status": "absent"}),
    "evidence_sent unknown key": lambda r, d: r["llm"]["evidence_sent"].append(
        {"address": "azurerm_key_vault.prod", "path": ["x"], "sections": ["security"]}),
    "evidence_sent ineligible section": lambda r, d: next(
        k for k in r["llm"]["evidence_sent"] if k["path"] == ["tags", "owner"])["sections"].insert(0, "security"),
    "evidence_sent dropped": lambda r, d: r["llm"].update(evidence_sent=[]),
    "finding deterministic severity": lambda r, d: _first(r, "security").update(deterministic_severity="LOW"),
    "finding below flag": lambda r, d: _first(r, "security").update(ai_impact_below_deterministic=True),
    "finding cites unsent path": lambda r, d: _first(r, "cost").update(cited_paths=[["tags", "owner"]]),
    "cost classification": lambda r, d: _first(r, "cost").update(classification="in_sync"),
    "config evidence facts": lambda r, d: _first(r, "configuration")["evidence_facts"][0].update(assessment="noise"),
    "root cause origin facts": lambda r, d: _first(r, "root_cause")["origin_facts"][0].update(origin="both_sides"),
    "root cause contradicting hypothesis": lambda r, d: _first(r, "root_cause").update(
        hypothesis="configuration_change"),
    "risk factors": lambda r, d: _first(r, "risk").update(risk_factors=["ambiguous_intent"]),
    "risk kind unsupported": lambda r, d: _first(r, "risk").update(risk_kind="apply_destroys_or_recreates"),
    "AI text attribution": lambda r, d: _first(r, "configuration").update(explanation="Changed by admin@x.io."),
    "AI summary remediation": lambda r, d: r["analysis"]["security"].update(summary="Run terraform destroy."),
    "rejected count": lambda r, d: r["analysis"]["security"].update(rejected_count=3),
    "llm not attempted but ok": lambda r, d: r["llm"].update(attempted=False, evidence_sent=[]),
    "failed section keeps findings": lambda r, d: r["analysis"]["security"].update(status="failed"),
    "remediation plan_default moved": lambda r, d: r["remediation"]["options"][1].update(plan_default=True),
    "remediation destructive": lambda r, d: r["remediation"]["options"][0].update(destructive=True),
    "remediation command": lambda r, d: r["remediation"]["options"][0]["commands"][-1].update(
        command="terraform -chdir=terraform/environments/dev apply -auto-approve reviewed.tfplan"),
    "remediation unknown template": lambda r, d: r["remediation"]["options"][0]["commands"][0].update(
        template_id="nuke"),
    "remediation fragment interpolation": lambda r, d: next(
        o for o in r["remediation"]["options"] if o["fragments"])["fragments"][0].update(value_hcl='"${file(x)}"'),
    "remediation scope": lambda r, d: r["remediation"]["options"][0].update(address="azurerm_key_vault.prod"),
    "remediation human flag": lambda r, d: r["remediation"]["options"][0].update(human_decision_required=True),
    "remediation evidence": lambda r, d: r["remediation"]["options"][0].update(evidence=[]),
    "remediation two plan defaults": lambda r, d: r["remediation"]["options"][1].update(
        plan_default=True, terraform_plan_action=r["remediation"]["options"][0]["terraform_plan_action"]),
    "remediation no plan default": lambda r, d: r["remediation"]["options"][0].update(
        plan_default=False, terraform_plan_action=None),
    "remediation extra resource": lambda r, d: r["remediation"]["options"].append(
        dict(copy.deepcopy(r["remediation"]["options"][0]), address="azurerm_key_vault.prod",
             option_id="azurerm_key_vault.prod#1")),
    "evidence_sent without a call": lambda r, d: r["llm"].update(attempted=False),
    "evidence_sent duplicate": lambda r, d: r["llm"]["evidence_sent"].append(copy.deepcopy(r["llm"]["evidence_sent"][0])),
    "config topic other conflicting": lambda r, d: _first(r, "configuration").update(topic_conflicts_with_evidence=True),
    "root cause lifecycle on update": lambda r, d: _first(r, "root_cause").update(hypothesis="lifecycle_change"),
    "risk unverified flag": lambda r, d: _first(r, "risk").update(risk_kind_unverified=True),
    "risk evidence_incomplete unsupported": lambda r, d: _first(r, "risk").update(risk_kind="evidence_incomplete"),
    "remediation data_not_restored": lambda r, d: r["remediation"]["options"][0].update(data_not_restored=True),
    "remediation recreate on update": lambda r, d: r["remediation"]["options"][0].update(
        kind="recreate_deleted_object", data_not_restored=True),
    "remediation nested assignment": lambda r, d: next(
        f for o in r["remediation"]["options"] for f in o["fragments"] if len(f["path"]) > 1).update(
        assignment_hcl="tags = {}"),
    "remediation gap outside scope": lambda r, d: r["remediation"]["options"][0]["fragment_gaps"].append(
        {"path": ["nope"], "reason": "value_absent"}),
    "remediation command altered": lambda r, d: r["remediation"]["options"][0]["commands"][0].update(
        command=r["remediation"]["options"][0]["commands"][0]["command"] + " -lock=false"),
    "schema: actor": lambda r, d: r["resources"][0]["who"]["actor_attribution"].update(status="confirmed"),
    "schema: caller identity": lambda r, d: r["resources"][0]["who"]["recorded_caller"].update(identity="admin"),
    "recommendation changed": lambda r, d: r["resources"][0]["remediation"]["recommendation"].update(
        decision="human_decision_required", policy_rule="R1", rationale="ambiguous_intent", option_id=None,
        kind=None, notes=[]),
    "investigation status claimed": lambda r, d: r["investigation"].update(status="complete"),
    "narrative statement edited": lambda r, d: r["resources"][0]["analysis"]["narrative"][0].update(
        text="Terraform reports nothing."),
    "schema: finding actor": lambda r, d: _first(r, "root_cause").update(actor="admin@contoso.com"),
    "schema: finding confirmed": lambda r, d: _first(r, "root_cause").update(confirmed=True),
    "schema: execution": lambda r, d: r["remediation"]["options"][0]["execution"].update(allowed=True),
    "schema: extra finding field": lambda r, d: _first(r, "security").update(severity="CRITICAL"),
    "schema: extra report field": lambda r, d: r.update(recommended_option="x"),
}


@requires_ai
@pytest.mark.parametrize("name", list(TAMPERS))
def test_verify_report_detects_tampering(name, full_report):
    report, drift = copy.deepcopy(full_report[0]), full_report[1]
    assert verify.verify_report(report, drift) == []
    TAMPERS[name](report, drift)
    problems = verify.verify_report(report, drift)
    assert problems, name
    # report v2 restates policy v1 too, so a forged remediation flag is also caught there; the dedicated check
    # must still fire on its own (Task 9B.4)
    if name in SPECIFIC_PROBLEM:
        assert any(SPECIFIC_PROBLEM[name] in p for p in problems), problems


SPECIFIC_PROBLEM = {
    "remediation destructive": "destructive flags do not match the plan action",
    "remediation data_not_restored": "data_not_restored is wrong",
    "remediation recreate on update": "recreate offered for a resource that was not deleted outside Terraform",
}


@requires_ai
def test_verify_report_failed_noise_and_unreadable_fragment_cases():
    failed = fixture_report("plan_evidence", "failed_run")
    report = json.loads(json.dumps(_run(failed, "none")["report"]))
    assert verify.verify_report(report, failed) == []
    report["remediation"]["reason"] = None
    assert "remediation: a failed drift report must have no options and a reason" in verify.verify_report(report, failed)

    added = fixture_report("plan_evidence", "resource_added")
    report = json.loads(json.dumps(_run(added, "ok")["report"]))
    assert verify.verify_report(report, added) == []
    extra = 'module.resource_group.azurerm_resource_group.this["extra"]'
    report["llm"]["evidence_sent"].append({"address": extra, "path": ["id"], "sections": ["configuration"]})
    assert any("not eligible for the configuration section" in p for p in verify.verify_report(report, added))

    drift = fixture_report("plan_evidence", "external_drift")  # tags.probe was removed in Azure: no readable value
    report = json.loads(json.dumps(_run(drift, "none")["report"]))
    report["remediation"]["options"][1]["fragments"].append(
        {"path": ["tags", "probe"], "value_hcl": '"1"', "value_source": "real_view", "location": "not_determined",
         "assignment_hcl": None})
    assert any("fragment for a value that must not produce one" in p for p in verify.verify_report(report, drift))


@requires_ai
def test_verify_report_rejects_a_different_drift_report(full_report):
    other = fixture_report("cost_config_plans", "storage_replication_upgrade")
    problems = verify.verify_report(full_report[0], other)
    assert any(p.startswith("provenance") for p in problems)
    with pytest.raises(verify.ReportVerificationError):
        verify.assert_report_valid(full_report[0], other)
    verify.assert_report_valid(*full_report)


@requires_ai
def test_verify_markdown_detects_tampering(full_report):
    md = render_markdown(full_report[0])
    assert verify.verify_markdown(md, full_report[0]) == []
    assert verify.verify_markdown(md.replace("## Risk", "## Risk\n\nInjected line."), full_report[0])
    assert verify.verify_markdown(md, {"not": "a report"}) == ["markdown: the report JSON is not valid"]


@requires_ai
def test_markdown_contains_no_information_absent_from_json(full_report):
    """Every word of the Markdown comes from the renderer's own template text or from a JSON string value."""
    report = full_report[0]
    md = render_markdown(report)
    template = (ROOT / "src" / "ai_engine" / "nodes" / "report_generator.py").read_text(encoding="utf-8")

    def strings(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield str(k)
                yield from strings(v)
        elif isinstance(node, list):
            for v in node:
                yield from strings(v)
        else:
            yield json.dumps(node) if not isinstance(node, str) else node

    vocabulary = set(re.findall(r"[A-Za-z]{3,}", template)) | {
        w for s in strings(report) for w in re.findall(r"[A-Za-z]{3,}", s)}
    words = set(re.findall(r"[A-Za-z]{3,}", md.replace("​", "")))
    assert words - vocabulary == set()


# --------------------------------------------------------------------------- state isolation


def _graph_with_later(later, include_analysis=True):
    from ai_engine.nodes.report_generator import generate_report

    graph = StateGraph(AiState)
    steps = [("parse_drift", parse_drift), ("classify_drift", classify_drift), ("route_cost_config",
             route_cost_config), ("derive_origin_risk", derive_origin_risk),
             ("derive_investigation", derive_investigation), ("plan_remediation", plan_remediation)]
    if include_analysis:
        steps += [("analyze_drift", make_analyze_drift(None)), ("generate_report", generate_report)]
    steps.append(("later", later))
    for name, node in steps:
        graph.add_node(name, node)
    graph.add_edge(START, steps[0][0])
    for (a, _), (b, _) in zip(steps, steps[1:]):
        graph.add_edge(a, b)
    graph.add_edge(steps[-1][0], END)
    return graph.compile()


OFF = {"available": False, "provider": "none", "model": None, "reason": "off"}


@requires_ai
@pytest.mark.parametrize("write", [
    {"llm": {"available": True, "provider": "x", "model": "y", "reason": None}},
    {"inferences": {"analyze_security": {"status": "ok"}}},
    {"llm_call": {"attempted": True}},
], ids=["llm", "inferences-key", "llm_call"])
def test_later_nodes_cannot_replace_ai_state(write):
    with pytest.raises(EvidenceMutationError):
        _graph_with_later(lambda state: write).invoke(
            {"drift_report": fixture_report("plan_evidence", "external_drift"), "llm": OFF})


@requires_ai
def test_inference_results_are_frozen_but_new_keys_may_be_added():
    def mutate(state):
        state["inferences"]["analyze_security"]["rejected_findings"].append({"index": 0})
        return {}

    with pytest.raises(EvidenceMutationError):
        _graph_with_later(mutate).invoke({"drift_report": fixture_report("plan_evidence", "external_drift"),
                                          "llm": OFF})
    state = _graph_with_later(lambda s: {"inferences": {"later_note": {"status": "x"}}}).invoke(
        {"drift_report": fixture_report("plan_evidence", "external_drift"), "llm": OFF})
    assert isinstance(state["inferences"], FrozenDict) and set(state["inferences"]) >= set(SECTION_KEYS)


@requires_ai
def test_inferences_reject_non_objects():
    with pytest.raises(TypeError):
        _graph_with_later(lambda s: {"inferences": ["x"]}, include_analysis=False).invoke(
            {"drift_report": fixture_report("plan_evidence", "external_drift"), "llm": OFF})


@requires_ai
@pytest.mark.parametrize("status", [200, 500])
def test_whole_graph_one_http_attempt_by_default(status):
    config = load_config({"AI_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "sk-test-not-real", "AI_LLM_MODEL": "m",
                          "OPENAI_BASE_URL": "https://llm.example.invalid/v1"})
    requests: list = []

    def handler(request):
        requests.append(request)
        body = {"id": "c", "object": "chat.completion", "created": 0, "model": "m",
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": envelope()}}]} if status == 200 else \
            {"error": {"message": "x"}}
        return httpx.Response(status, json=body)

    model, _ = create_chat_model(config, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    drift = fixture_report("cost_config_plans", "combined_security_cost_config")
    state = run_analysis(drift, config=config, llm=model)
    assert len(requests) == 1
    assert verify.verify_report(state["report"], drift) == []
    sent = {(k["address"], tuple(k["path"])) for k in state["report"]["llm"]["evidence_sent"]}
    shown_keys = {(r["address"], tuple(c["path"])) for r in json.loads(re.search(
        rf"<{EVIDENCE_TAG}>\n(.*)\n</{EVIDENCE_TAG}>", json.loads(requests[0].content)["messages"][1]["content"],
        re.DOTALL).group(1))["resources"] for c in r["changes"]}
    assert sent == shown_keys  # evidence_sent records exactly what the model was given


# --------------------------------------------------------------------------- previously uncovered paths


@requires_ai
def test_failed_report_markdown(tmp_path):
    drift = fixture_report("plan_evidence", "failed_run")
    state = run_analysis(drift, config=load_config({}))
    md = write_report(state, tmp_path)["markdown"].read_text(encoding="utf-8")
    assert "- Failure: detection" in md and "never \"no drift\"" in md
    assert "no remediation options" in md
    assert verify.verify_report(state["report"], drift) == []


@requires_ai
def test_atomic_write_cleans_up_on_failure(tmp_path, monkeypatch):
    from ai_engine.nodes import report_generator

    state = run_analysis(fixture_report("plan_evidence", "external_drift"), config=load_config({}))
    first = write_report(state, tmp_path)
    before = first["json"].read_bytes()

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(report_generator.os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        write_report(state, tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ai_analysis_report.json", "ai_analysis_report.md"]
    assert first["json"].read_bytes() == before


@requires_ai
def test_client_construction_failure_degrades_without_leaking(monkeypatch):
    import langchain_openai

    class Exploding:
        def __init__(self, **kwargs):
            raise ValueError("bad config for sk-test-not-real")

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", Exploding)
    model, reason = create_chat_model(load_config({"AI_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "sk-test-not-real",
                                                   "AI_LLM_MODEL": "m"}))
    assert model is None and reason == "could not create openai client (ValueError)"


def test_recoverable_errors_without_openai(monkeypatch):
    from ai_engine import llm

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "openai":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert llm._recoverable_errors() == (TimeoutError, ConnectionError)
    assert llm.invoke_llm(ScriptedLLM(error=TimeoutError("x")), []).error == "LLM call failed (TimeoutError)"


def test_hcl_value_rejects_non_json():
    with pytest.raises(TypeError, match="not a JSON value"):
        hcl_value(object())


@requires_ai
def test_frozen_list_copies_and_non_object_writes():
    from ai_engine.graph import freeze_evidence, write_once_parsed_drift

    frozen = freeze_evidence({"l": [1, [2]]})["l"]
    assert isinstance(frozen, FrozenList)
    assert copy.copy(frozen) is frozen and copy.deepcopy(frozen) is frozen
    with pytest.raises(TypeError, match="must be a JSON object"):
        write_once_parsed_drift({}, ["not", "an", "object"])


def test_duplicate_route_for_the_same_section_is_ignored():
    state = prepared(fixture_report("security_plans", "nsg_open_inbound"))
    routes = state["security_targets"]["changes"]
    evidence = build_llm_evidence(state["parsed_drift"], routes + routes)
    assert evidence["truncation"]["changes_total"] == len(routes)
    assert evidence["truncation"]["per_section"]["security"] == {"routed": len(routes), "included": len(routes)}


def test_cost_section_rejects_unsupported_citations_and_guarded_text():
    state = prepared(fixture_report("cost_config_plans", "storage_replication_upgrade"))
    routes = state["cost_targets"]["changes"]
    evidence = build_llm_evidence(state["parsed_drift"], routes, origin_facts=state["origin_facts"])
    sa = "azurerm_storage_account.this"
    base = {"cost_driver": "sku_or_tier", "direction": "likely_increase",
            "monetary_impact": "not_determinable_from_evidence", "basis": "inference"}
    output = CostSection.model_validate_json(json.dumps({"summary": "", "findings": [
        dict(base, address=sa, cited_paths=[["nonexistent"]], explanation="x"),
        dict(base, address=sa, cited_paths=[["account_replication_type"]], explanation="An admin changed it."),
        dict(base, address=sa, cited_paths=[["account_replication_type"]], explanation="Replication grew."),
    ]}))
    kept, rejected = validate_cost_section(output, evidence)
    assert rejected == [{"index": 0, "reason": "unsupported_citation"},
                        {"index": 1, "reason": "unsupported_attribution"}]
    assert len(kept) == 1


@requires_ai
def test_evidence_incomplete_is_accepted_for_redacted_evidence():
    drift = fixture_report("security_plans", "web_app_secret_changed")
    state = prepared(drift)
    reply = envelope(risk_assessment={"findings": [{
        "address": "azurerm_linux_web_app.this", "cited_paths": [["site_config"]], "risk_kind": "evidence_incomplete",
        "explanation": "The sensitive value cannot be read.", "basis": "inference"}], "summary": ""})
    full = run_analysis(copy.deepcopy(drift), llm=ScriptedLLM(reply))
    assert len(full["report"]["analysis"]["risk"]["findings"]) == 1
    assert verify.verify_report(full["report"], drift) == []


@requires_ai
def test_evidence_sent_must_be_empty_when_no_call_was_made():
    drift = fixture_report("cost_config_plans", "combined_security_cost_config")
    report = json.loads(json.dumps(_run(drift, "none")["report"]))
    assert report["llm"]["attempted"] is False and verify.verify_report(report, drift) == []
    report["llm"]["evidence_sent"].append({"address": "azurerm_storage_account.this", "path": ["tags", "owner"],
                                           "sections": ["configuration"]})  # valid and eligible, but nothing was sent
    assert verify.verify_report(report, drift) == ["llm: evidence_sent / investigation_sent is not empty although no call was made"]


@requires_ai
def test_dangerous_commands_rejected_even_if_the_catalogue_regressed(monkeypatch, full_report):
    report, drift = copy.deepcopy(full_report[0]), full_report[1]
    template = "terraform -chdir={working_dir} apply -auto-approve reviewed.tfplan"
    monkeypatch.setitem(verify.COMMAND_CATALOGUE, "apply_reviewed_plan", (template, False, "infrastructure"))
    option = report["remediation"]["options"][0]
    command = next(c for c in option["commands"] if c["template_id"] == "apply_reviewed_plan")
    command["command"] = template.format(working_dir="terraform/environments/dev")
    assert any("would apply or destroy without review" in p for p in verify.verify_report(report, drift))
