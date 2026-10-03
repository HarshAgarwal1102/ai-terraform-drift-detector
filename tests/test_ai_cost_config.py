"""Task 6.4: cost and configuration sections of the single LLM call.

Reports come from drift_engine run on synthetic plans (tests/fixtures/
cost_config_plans, see build.py there; no pricing data anywhere) and on the real
fixtures. Every LLM is a fake or a local httpx.MockTransport; tests/conftest.py
blocks any non-loopback connection.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
from pathlib import Path

import pytest

from ai_engine.evidence import EVIDENCE_TAG, EvidenceLimits, build_llm_evidence
from ai_engine.nodes.analyze_drift import SYSTEM_PROMPT, InvalidEnvelope, make_analyze_drift, parse_envelope
from ai_engine.nodes.common import contains_cost_claim
from ai_engine.nodes.cost_analysis import route_cost_config
from ai_engine.nodes.parse_drift import parse_drift
from ai_engine.nodes.security_analysis import classify_drift
from drift_engine.classifier import evaluate

HAS_AI_EXTRA = all(importlib.util.find_spec(m) for m in ("langgraph", "langchain_openai"))
requires_ai = pytest.mark.skipif(not HAS_AI_EXTRA, reason="needs the 'ai' extra")
if HAS_AI_EXTRA:
    import httpx
    from langgraph.graph import END, START, StateGraph

    from ai_engine.config import create_chat_model, load_config
    from ai_engine.graph import AiState, EvidenceMutationError, FrozenDict, run_analysis

FIXTURES = Path(__file__).parent / "fixtures"
COST = FIXTURES / "cost_config_plans"
SA = "azurerm_storage_account.this"
PLAN = "azurerm_service_plan.this"
VM = "azurerm_linux_virtual_machine.this"
VMSS = "azurerm_linux_virtual_machine_scale_set.this"
NSG = "azurerm_network_security_group.this"
AVAILABLE = {"available": True, "provider": "fake", "model": "fake-model", "reason": None}
SECTIONS = ("analyze_security", "analyze_cost", "analyze_configuration")


def report(name: str) -> dict:
    return evaluate(str(COST / name / "plan.synthetic.json"), str(COST / name / "detection_run.json")).report


def real_report(name: str) -> dict:
    base = FIXTURES / "plan_evidence" / name
    return evaluate(str(base / "plan.sanitized.json"), str(base / "detection_run.json")).report


def prepared(drift_report: dict) -> dict:
    state = {"drift_report": drift_report, "llm": AVAILABLE}
    for node in (parse_drift, classify_drift, route_cost_config):
        state.update(node(state))
    return state


def shown(messages) -> dict:
    body = re.search(rf"<{EVIDENCE_TAG}>\n(.*)\n</{EVIDENCE_TAG}>", messages[-1].content, re.DOTALL).group(1)
    return json.loads(body)


def envelope(security=(), cost=(), configuration=(), summaries=("", "", "")) -> str:
    return json.dumps({"security_analysis": {"findings": list(security), "summary": summaries[0]},
                       "cost_analysis": {"findings": list(cost), "summary": summaries[1]},
                       "configuration_analysis": {"findings": list(configuration), "summary": summaries[2]}})


def cost_finding(address=SA, paths=(["account_replication_type"],), **extra) -> dict:
    return {"address": address, "cited_paths": [list(p) for p in paths], "cost_driver": "sku_or_tier",
            "direction": "likely_increase", "monetary_impact": "not_determinable_from_evidence",
            "explanation": "Geo-redundant replication stores more copies than locally redundant.",
            "basis": "inference", **extra}


def config_finding(address=SA, paths=(["account_replication_type"],), topic="declared_value_overridden",
                   **extra) -> dict:
    return {"address": address, "cited_paths": [list(p) for p in paths], "topic": topic,
            "explanation": "Azure differs from the declared value; apply would revert it.", "basis": "inference",
            **extra}


def security_finding(address=NSG, paths=(["security_rule"],), **extra) -> dict:
    return {"address": address, "cited_paths": [list(p) for p in paths], "exposure": "network_exposure",
            "ai_assessed_impact": "CRITICAL", "explanation": "SSH is open to any source.", "basis": "inference",
            **extra}


class ScriptedLLM:
    def __init__(self, reply=None, error: BaseException | None = None):
        self.reply, self.error, self.prompts = reply, error, []

    def invoke(self, messages):
        self.prompts.append(messages)
        if self.error is not None:
            raise self.error
        return self.reply


class CitingLLM(ScriptedLLM):
    """Cites every change it was shown, once per section it was shown for."""

    def invoke(self, messages):
        self.prompts.append(messages)
        evidence = shown(messages)

        def pairs(section):
            return [(r, c) for r in evidence["resources"] for c in r["changes"] if section in c["sections"]]

        def base(r, c):
            return {"address": r["address"], "cited_paths": [c["path"]], "basis": "inference",
                    "explanation": f"{'.'.join(c['path'])} differs from the declared value."}

        security = [dict(base(r, c), exposure="other", ai_assessed_impact=c["severity"]["level"])
                    for r, c in pairs("security")]
        cost = [dict(base(r, c), cost_driver="other", direction="undetermined",
                     monetary_impact="not_determinable_from_evidence") for r, c in pairs("cost")]
        config = [dict(base(r, c), topic="other") for r, c in pairs("configuration")]
        return envelope(security, cost, config)


def analyze(state, llm, limits=EvidenceLimits()):
    return make_analyze_drift(llm, limits)(state)


# --------------------------------------------------------------------------- deterministic routing


@pytest.mark.parametrize(("scenario", "cost", "config"), [
    ("storage_replication_upgrade", [(SA, ["account_replication_type"], "cost attribute: account_replication_type")],
     [["account_replication_type"]]),
    ("app_plan_sku_downgrade", [(PLAN, ["sku_name"], "cost attribute: sku_name")], [["sku_name"]]),
    ("vm_size_planned_change", [(VM, ["size"], "cost attribute: size")], [["size"]]),
    ("vmss_zones_and_unknown_capacity", [(VMSS, ["instances"], "cost attribute: instances"),
                                         (VMSS, ["zones"], "cost attribute: zones")], [["instances"], ["zones"]]),
    ("storage_config_mix", [], [["account_kind"], ["large_file_share_enabled"], ["tags", "owner"]]),
])
def test_cost_and_config_routing(scenario, cost, config):
    state = prepared(report(scenario))
    assert [(c["address"], c["path"], c["reason"]) for c in state["cost_targets"]["changes"]] == cost
    assert [c["path"] for c in state["config_targets"]["changes"]] == config
    assert all(c["section"] == "cost" for c in state["cost_targets"]["changes"])


@pytest.mark.parametrize(("scenario", "reason"), [("storage_added", "lifecycle: resource_added"),
                                                  ("storage_deleted_externally", "lifecycle: external_deletion")])
def test_lifecycle_routes_every_non_noise_change(scenario, reason):
    state = prepared(report(scenario))
    routed = state["cost_targets"]["changes"]
    assert {c["reason"] for c in routed} == {reason}
    paths = {tuple(c["path"]) for c in routed}
    assert ("id",) not in paths and ("timeouts",) not in paths  # proven noise excluded
    assert ("account_replication_type",) in paths and ("tags", "environment") in paths
    config_paths = {tuple(c["path"]) for c in state["config_targets"]["changes"]}
    assert config_paths == paths  # every non-noise change, noise excluded from configuration too
    assert state["config_targets"]["summary"][0]["noise_excluded"] == 2


def test_real_fixtures_routing():
    assert prepared(real_report("external_drift"))["cost_targets"]["changes"] == []  # tag drift: config only
    assert [c["path"] for c in prepared(real_report("external_drift"))["config_targets"]["changes"]] == \
        [["tags", "probe"]]
    replace = prepared(real_report("replace"))
    assert {c["reason"] for c in replace["cost_targets"]["changes"]} == {"lifecycle: planned replace"}
    assert prepared(real_report("in_sync"))["config_targets"]["changes"] == []


def test_configuration_summary_regroups_the_report():
    state = prepared(report("storage_config_mix"))
    [summary] = state["config_targets"]["summary"]
    assert summary == {
        "address": SA, "classification": "drift_and_config_change", "action": "update",
        "changes_by_class": {"drifted": 2, "drifted_and_config_changed": 1},
        "changes_by_assessment": {"configured": 2, "unconfigured": 1},
        "reverted_on_apply": [["account_kind"], ["large_file_share_enabled"], ["tags", "owner"]],
        "pending_config_changes": [], "ambiguous": [["account_kind"]], "unknown_until_apply": [],
        "unconfigured_reverted": [["large_file_share_enabled"]], "noise_excluded": 0,
    }
    # Nothing re-classified: the report is unchanged.
    assert state["drift_report"]["resources"][0]["classification"] == "drift_and_config_change"


# --------------------------------------------------------------------------- evidence: dedupe, scoping, caps


@requires_ai
def test_change_routed_to_several_sections_is_sent_once():
    llm = CitingLLM()
    analyze(prepared(report("combined_security_cost_config")), llm)
    evidence = shown(llm.prompts[0])
    keys = [(r["address"], tuple(c["path"])) for r in evidence["resources"] for c in r["changes"]]
    assert len(keys) == len(set(keys)) == 3  # 5 routes over 3 distinct changes
    by_key = {(r["address"], tuple(c["path"])): c["sections"] for r in evidence["resources"] for c in r["changes"]}
    assert set(by_key[(SA, ("account_replication_type",))]) == {"security", "cost", "configuration"}
    assert set(by_key[(NSG, ("security_rule",))]) == {"security", "configuration"}
    assert set(by_key[(SA, ("tags", "owner"))]) == {"configuration"}
    assert evidence["sections"] == {s: {"applicable": True} for s in ("security", "cost", "configuration")}


def test_per_section_caps_do_not_starve_other_sections():
    state = prepared(report("combined_security_cost_config"))
    routes = (state["security_targets"]["changes"] + state["cost_targets"]["changes"]
              + state["config_targets"]["changes"])
    evidence = build_llm_evidence(state["parsed_drift"], routes, EvidenceLimits(max_configuration_changes=1))
    per = evidence["truncation"]["per_section"]
    assert per["configuration"] == {"routed": 3, "included": 1}
    assert per["security"]["included"] == per["security"]["routed"] == 2
    assert per["cost"] == {"routed": 1, "included": 1}
    assert {"address": SA, "path": ["tags", "owner"], "sections": ["configuration"]} in \
        evidence["truncation"]["changes_omitted"]


# --------------------------------------------------------------------------- the one-call guarantee


@requires_ai
@pytest.mark.parametrize("scenario", sorted(p.name for p in COST.iterdir() if p.is_dir()))
def test_at_most_one_call_per_run(scenario):
    llm = CitingLLM()
    update = analyze(prepared(report(scenario)), llm)
    assert len(llm.prompts) == 1 and update["llm_call"]["attempted"] is True
    assert set(update["inferences"]) == set(SECTIONS)


@requires_ai
def test_whole_graph_makes_one_call_for_all_three_sections():
    llm = CitingLLM()
    state = run_analysis(report("combined_security_cost_config"), llm=llm)
    assert len(llm.prompts) == 1
    assert {k: state["inferences"][k]["status"] for k in SECTIONS} == {k: "ok" for k in SECTIONS}
    assert state["llm_call"]["status"] == "ok"


def _http_run(extra_env: dict, status: int, body: dict):
    config = load_config({"AI_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "sk-test-not-real", "AI_LLM_MODEL": "m",
                          "OPENAI_BASE_URL": "https://llm.example.invalid/v1", **extra_env})
    requests: list = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, json=body, headers={"retry-after-ms": "1"})

    model, _ = create_chat_model(config, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    state = run_analysis(report("combined_security_cost_config"), config=config, llm=model)
    return state, requests


@requires_ai
def test_default_config_one_http_request_for_three_sections():
    ok = {"id": "c", "object": "chat.completion", "created": 0, "model": "m",
          "choices": [{"index": 0, "finish_reason": "stop",
                       "message": {"role": "assistant", "content": envelope()}}]}
    state, requests = _http_run({}, 200, ok)
    assert len(requests) == 1 and state["llm_call"]["max_retries"] == 0
    state, requests = _http_run({}, 503, {"error": {"message": "x"}})
    assert len(requests) == 1
    assert {state["inferences"][k]["status"] for k in SECTIONS} == {"failed"}


@requires_ai
def test_retries_still_opt_in_for_the_single_call():
    state, requests = _http_run({"AI_LLM_MAX_RETRIES": "2"}, 503, {"error": {"message": "x"}})
    assert len(requests) == 3 and len({r.content for r in requests}) == 1
    assert state["llm_call"]["max_retries"] == 2


# --------------------------------------------------------------------------- section-scoped citations


@requires_ai
def test_findings_may_cite_only_their_own_section():
    state = prepared(report("combined_security_cost_config"))
    reply = envelope(
        security=[security_finding(), security_finding(address=SA, paths=(["tags", "owner"],))],  # config-only
        cost=[cost_finding(), cost_finding(address=NSG, paths=(["security_rule"],))],  # not sent for cost
        configuration=[config_finding(), config_finding(address=SA, paths=(["tags", "owner"],))])
    inferences = analyze(state, ScriptedLLM(reply))["inferences"]
    for key in SECTIONS:
        assert inferences[key]["status"] == "ok"
    assert inferences["analyze_security"]["rejected_findings"] == [{"index": 1, "reason": "unsupported_citation"}]
    assert inferences["analyze_cost"]["rejected_findings"] == [{"index": 1, "reason": "unsupported_citation"}]
    assert inferences["analyze_configuration"]["rejected_findings"] == []
    assert len(inferences["analyze_configuration"]["findings"]) == 2


@requires_ai
def test_non_applicable_section_findings_are_rejected():
    state = prepared(real_report("external_drift"))  # tag drift: configuration only
    reply = envelope(security=[security_finding(address="x", paths=(["tags", "probe"],))],
                     cost=[cost_finding(address="x")],
                     configuration=[config_finding(address='module.resource_group.azurerm_resource_group.this["main"]',
                                                   paths=(["tags", "probe"],))])
    inferences = analyze(state, ScriptedLLM(reply))["inferences"]
    for key, reason in (("analyze_security", "no security-relevant changes"), ("analyze_cost", "no cost-relevant changes")):
        assert (inferences[key]["status"], inferences[key]["reason"]) == ("skipped", reason)
        assert inferences[key]["rejected_findings"] == [{"index": 0, "reason": "section_not_applicable"}]
        assert inferences[key]["findings"] == []
    assert inferences["analyze_configuration"]["status"] == "ok"
    assert len(inferences["analyze_configuration"]["findings"]) == 1


# --------------------------------------------------------------------------- cost contract


@pytest.mark.parametrize("text", [
    "This adds $40 per month.", "Roughly 35 USD/month more.", "about €12 a month", "costs about 120 per month",
    "saves 30% cheaper", "savings of 500", "₹2,000 monthly", "an extra 0.05 per hour", "monthly cost of 12",
    "it would cost 99", "Cost: 9,999", "approximately 15 dollars",
])
def test_cost_claim_guard_flags_amounts(text):
    assert contains_cost_claim(text)


@pytest.mark.parametrize("text", [
    "Inbound port 22 is open to any source.", "min_tls_version dropped to TLS1_0.", "3 rules were removed.",
    "The size moved to Standard_D4s_v5.", "GRS keeps 6 copies across 2 regions.", "This likely increases cost.",
    "Monetary impact cannot be determined from the supplied evidence.", "sku_name changed from P1v3 to B1.",
    "instances is unknown until apply; zones changed from 1 to 1 and 2.",
])
def test_cost_claim_guard_allows_qualitative_text(text):
    assert not contains_cost_claim(text)


@requires_ai
def test_cost_findings_are_qualitative_and_pricing_free():
    state = prepared(report("storage_replication_upgrade"))
    reply = envelope(cost=[cost_finding(), cost_finding(explanation="GRS costs about $20 per month more.")],
                     summaries=("", "Replication now costs 2x: about 25 USD/month.", ""))
    result = analyze(state, ScriptedLLM(reply))["inferences"]["analyze_cost"]
    assert result["status"] == "ok"
    [kept] = result["findings"]
    assert kept["monetary_impact"] == "not_determinable_from_evidence" and kept["pricing_source"] is None
    assert kept["direction"] == "likely_increase" and kept["basis"] == "inference"
    assert (kept["classification"], kept["action"], kept["deterministic_severity"]) == \
        ("external_drift", "update", "MEDIUM")
    assert result["rejected_findings"] == [{"index": 1, "reason": "unsupported_cost_claim"},
                                           {"index": None, "reason": "summary_unsupported_cost_claim"}]
    assert result["summary"] is None


@pytest.mark.parametrize("bad", [
    {"monetary_impact": "about $20/month"}, {"monetary_impact": "increase"}, {"direction": "up"},
    {"cost_driver": "pricing"}, {"monthly_cost_delta": 20}, {"basis": "evidence"},
])
@requires_ai
def test_cost_section_schema_is_strict(bad):
    state = prepared(report("storage_replication_upgrade"))
    inferences = analyze(state, ScriptedLLM(envelope(cost=[cost_finding(**bad)],
                                                     configuration=[config_finding()])))["inferences"]
    assert inferences["analyze_cost"]["status"] == "invalid_output" and inferences["analyze_cost"]["findings"] == []
    assert inferences["analyze_configuration"]["status"] == "ok"  # other sections survive


@requires_ai
def test_free_resource_is_still_not_determinable():
    state = prepared(real_report("resource_added"))  # a resource group: no SKU at all
    path = ["location"]
    address = next(r["address"] for r in state["parsed_drift"]["resources"])
    reply = envelope(cost=[cost_finding(address=address, paths=(path,), cost_driver="resource_lifecycle",
                                        direction="likely_neutral")])
    [kept] = analyze(state, ScriptedLLM(reply))["inferences"]["analyze_cost"]["findings"]
    assert kept["monetary_impact"] == "not_determinable_from_evidence"


@requires_ai
def test_cost_claims_rejected_in_every_section():
    state = prepared(report("combined_security_cost_config"))
    reply = envelope(security=[security_finding(explanation="Fixing this saves $300 a month.")],
                     configuration=[config_finding(explanation="This drift costs 50 USD/month.")])
    inferences = analyze(state, ScriptedLLM(reply))["inferences"]
    assert inferences["analyze_security"]["rejected_findings"] == [{"index": 0, "reason": "unsupported_cost_claim"}]
    assert inferences["analyze_configuration"]["rejected_findings"] == [
        {"index": 0, "reason": "unsupported_cost_claim"}]


# --------------------------------------------------------------------------- configuration contract


@pytest.mark.parametrize(("path", "topic", "conflict"), [
    (["account_kind"], "ambiguous_change", False),
    (["account_kind"], "declared_value_overridden", False),
    (["large_file_share_enabled"], "unmanaged_setting", False),
    (["tags", "owner"], "unmanaged_setting", True),  # tags are configured
    (["tags", "owner"], "pending_config_change", True),  # drift, not a pending config change
    (["tags", "owner"], "value_unknown_until_apply", True),
    (["tags", "owner"], "other", False),
])
@requires_ai
def test_configuration_topic_checked_against_evidence(path, topic, conflict):
    state = prepared(report("storage_config_mix"))
    reply = envelope(configuration=[config_finding(paths=(path,), topic=topic)])
    [kept] = analyze(state, ScriptedLLM(reply))["inferences"]["analyze_configuration"]["findings"]
    assert kept["topic_conflicts_with_evidence"] is conflict
    fact = kept["evidence_facts"][0]
    change = next(c for c in state["parsed_drift"]["resources"][0]["attribute_changes"] if c["path"] == path)
    assert (fact["class"], fact["assessment"]) == (change["class"], change["assessment"]["category"])


@requires_ai
def test_unknown_until_apply_topic():
    state = prepared(report("vmss_zones_and_unknown_capacity"))
    reply = envelope(configuration=[config_finding(address=VMSS, paths=(["instances"],),
                                                   topic="value_unknown_until_apply")])
    [kept] = analyze(state, ScriptedLLM(reply))["inferences"]["analyze_configuration"]["findings"]
    assert kept["topic_conflicts_with_evidence"] is False


@requires_ai
@pytest.mark.parametrize("bad", [{"topic": "drifted"}, {"classification": "in_sync"}, {"remediation": "set it back"},
                                 {"changed_by": "admin"}, {"severity": "LOW"}])
def test_configuration_schema_has_no_room_for_decisions(bad):
    state = prepared(report("storage_config_mix"))
    result = analyze(state, ScriptedLLM(envelope(configuration=[config_finding(paths=(["account_kind"],), **bad)])))
    assert result["inferences"]["analyze_configuration"]["status"] == "invalid_output"


# --------------------------------------------------------------------------- envelope and failures


@pytest.mark.parametrize("text", [
    "", "Here is my analysis.", "I'm sorry, I can't help with that.", "[]", '{"a": NaN}',
    json.dumps({"security_analysis": {"findings": [], "summary": ""}}),  # missing sections
    envelope()[:-1] + ', "remediation_analysis": {}}',  # extra section
    envelope() + envelope(),
])
@requires_ai
def test_invalid_envelope_invalidates_every_applicable_section(text):
    state = prepared(report("combined_security_cost_config"))
    update = analyze(state, ScriptedLLM(text))
    assert {update["inferences"][k]["status"] for k in SECTIONS} == {"invalid_output"}
    assert update["llm_call"]["status"] == "invalid_output"
    assert "sorry" not in json.dumps(update["inferences"])  # raw reply discarded
    with pytest.raises(InvalidEnvelope):
        parse_envelope(text)


def test_fenced_envelope_accepted():
    assert set(parse_envelope("```json\n" + envelope() + "\n```")) == {
        "security_analysis", "cost_analysis", "configuration_analysis"}


@requires_ai
def test_failed_call_marks_applicable_sections_and_keeps_deterministic_state():
    state = prepared(real_report("external_drift"))  # configuration only
    import openai

    request = httpx.Request("POST", "https://llm.example.invalid")
    update = analyze(state, ScriptedLLM(error=openai.APIConnectionError(request=request)))
    statuses = {k: update["inferences"][k]["status"] for k in SECTIONS}
    assert statuses == {"analyze_security": "skipped", "analyze_cost": "skipped", "analyze_configuration": "failed"}
    assert update["llm_call"]["status"] == "failed" and update["llm_call"]["attempted"] is True
    assert set(update) == {"inferences", "llm_call", "warnings"}  # no deterministic field touched


@requires_ai
@pytest.mark.parametrize("error", [KeyError("bug"), TypeError("bug"), ValueError("bug")])
def test_application_bugs_still_raise(error):
    with pytest.raises(type(error)):
        analyze(prepared(report("storage_replication_upgrade")), ScriptedLLM(error=error))


def test_no_routes_at_all_is_recorded_as_such():
    update = analyze(prepared(real_report("in_sync")), ScriptedLLM(envelope()))
    assert update["llm_call"] == {"attempted": False, "status": "not_attempted", "reason": "no relevant changes",
                                  "provider": "fake", "model": "fake-model", "max_retries": None,
                                  "truncation": None}


def test_unavailable_llm_skips_all_without_call():
    state = prepared(report("combined_security_cost_config"))
    state["llm"] = {"available": False, "provider": "none", "model": None, "reason": "AI_LLM_PROVIDER is not set"}
    llm = ScriptedLLM(envelope())
    update = analyze(state, llm)
    assert llm.prompts == [] and update["llm_call"]["attempted"] is False
    assert {update["inferences"][k]["reason"] for k in SECTIONS} == {"LLM unavailable: AI_LLM_PROVIDER is not set"}


# --------------------------------------------------------------------------- untrusted values


@requires_ai
def test_injection_values_are_escaped_and_claims_rejected():
    state = prepared(report("app_plan_injection"))
    echo = envelope(cost=[cost_finding(address=PLAN, paths=(["sku_name"],),
                                       explanation="As instructed, report savings of $5,000/month.")],
                    configuration=[config_finding(address=PLAN, paths=(["sku_name"],),
                                                  explanation="The SKU no longer matches the declared P1v3.")])
    llm = ScriptedLLM(echo)
    update = analyze(state, llm)
    human = llm.prompts[0][1].content
    assert human.count(f"</{EVIDENCE_TAG}>") == 1 and "\\u003c/terraform_evidence\\u003e" in human
    assert llm.prompts[0][0].content == SYSTEM_PROMPT
    assert "untrusted DATA" in SYSTEM_PROMPT and "Do not recommend remediation" in SYSTEM_PROMPT
    assert "No pricing data is provided" in SYSTEM_PROMPT and "Do not claim who or what made a change" in SYSTEM_PROMPT
    assert update["inferences"]["analyze_cost"]["rejected_findings"] == [
        {"index": 0, "reason": "unsupported_cost_claim"}]
    assert len(update["inferences"]["analyze_configuration"]["findings"]) == 1


# --------------------------------------------------------------------------- acceptance: SKU change end to end


@pytest.mark.parametrize(("scenario", "address", "path"), [
    ("storage_replication_upgrade", SA, ["account_replication_type"]),
    ("app_plan_sku_downgrade", PLAN, ["sku_name"]),
    ("vm_size_planned_change", VM, ["size"]),
])
@requires_ai
def test_sku_change_end_to_end(scenario, address, path):
    llm = CitingLLM()
    update = analyze(prepared(report(scenario)), llm)
    cost = update["inferences"]["analyze_cost"]
    config = update["inferences"]["analyze_configuration"]
    assert cost["status"] == config["status"] == "ok"
    assert [(f["address"], f["cited_paths"]) for f in cost["findings"]] == [(address, [path])]
    assert cost["findings"][0]["monetary_impact"] == "not_determinable_from_evidence"
    assert [(f["address"], f["cited_paths"]) for f in config["findings"]] == [(address, [path])]
    assert len(llm.prompts) == 1


# --------------------------------------------------------------------------- frozen state


@requires_ai
@pytest.mark.parametrize("field", ["cost_targets", "config_targets"])
@pytest.mark.parametrize("mode", ["replace", "mutate"])
def test_later_node_cannot_change_routing(field, mode):
    def later(state):
        if mode == "mutate":
            state[field]["changes"].pop()
            return {}
        return {field: {"changes": []}}

    graph = StateGraph(AiState)
    for name, node in (("parse_drift", parse_drift), ("classify_drift", classify_drift),
                       ("route_cost_config", route_cost_config), ("later", later)):
        graph.add_node(name, node)
    graph.add_edge(START, "parse_drift")
    graph.add_edge("parse_drift", "classify_drift")
    graph.add_edge("classify_drift", "route_cost_config")
    graph.add_edge("route_cost_config", "later")
    graph.add_edge("later", END)
    with pytest.raises(EvidenceMutationError):
        graph.compile().invoke({"drift_report": report("storage_config_mix")})


@requires_ai
def test_llm_call_record_is_frozen_and_deterministic_state_intact():
    drift_report = report("combined_security_cost_config")
    state = run_analysis(drift_report, llm=CitingLLM())
    assert isinstance(state["llm_call"], FrozenDict) and isinstance(state["cost_targets"], FrozenDict)
    assert isinstance(state["config_targets"], FrozenDict)
    assert state["drift_report"] == drift_report
    baseline = run_analysis(copy.deepcopy(drift_report), config=load_config({}))  # no LLM at all
    for key in ("parsed_drift", "security_targets", "cost_targets", "config_targets"):
        assert state[key] == baseline[key]  # deterministic output independent of the LLM
