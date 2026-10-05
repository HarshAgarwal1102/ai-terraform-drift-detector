"""Task 6.5: deterministic origin facts / risk factors and the root-cause and risk sections.

Reports come from drift_engine run on synthetic plans (tests/fixtures/
root_cause_plans, see build.py there) and on the real and earlier synthetic
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

from ai_engine.evidence import EVIDENCE_TAG, EvidenceIntegrityError, EvidenceLimits
from ai_engine.nodes.analyze_drift import SYSTEM_PROMPT, InvalidEnvelope, make_analyze_drift, parse_envelope
from ai_engine.nodes.common import contains_attribution_claim, contains_remediation_claim, free_text_violation
from ai_engine.nodes.cost_analysis import route_cost_config
from ai_engine.nodes.parse_drift import parse_drift
from ai_engine.nodes.root_cause import derive_origin_risk
from ai_engine.nodes.security_analysis import classify_drift
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
    from ai_engine.graph import AiState, EvidenceMutationError, FrozenDict, run_analysis

FIXTURES = Path(__file__).parent / "fixtures"
SA = "azurerm_storage_account.this"
RG = 'module.resource_group.azurerm_resource_group.this["main"]'
RG_EXTRA = 'module.resource_group.azurerm_resource_group.this["extra"]'  # the added resource in resource_added
SECTIONS = ("analyze_security", "analyze_cost", "analyze_configuration", "analyze_root_cause", "assess_risk")
AVAILABLE = {"available": True, "provider": "fake", "model": "fake-model", "reason": None}


def report(group: str, name: str) -> dict:
    base = FIXTURES / group / name
    plan = next(base / f for f in ("plan.synthetic.json", "plan.sanitized.json", "plan.json") if (base / f).exists()
                or f == "plan.json")
    return _public(evaluate(str(plan), str(base / "detection_run.json")))


def rc(name):
    return report("root_cause_plans", name)


def real(name):
    return report("plan_evidence", name)


def prepared(drift_report: dict) -> dict:
    state = {"drift_report": drift_report, "llm": AVAILABLE}
    for node in (parse_drift, classify_drift, route_cost_config, derive_origin_risk):
        state.update(node(state))
    return state


def shown(messages) -> dict:
    body = re.search(rf"<{EVIDENCE_TAG}>\n(.*)\n</{EVIDENCE_TAG}>", messages[-1].content, re.DOTALL).group(1)
    return json.loads(body)


def envelope(root_cause=(), risk=(), security=(), cost=(), configuration=(), summaries=None) -> str:
    summaries = summaries or {}

    def section(findings, key):
        return {"findings": list(findings), "summary": summaries.get(key, "")}

    return json.dumps({"security_analysis": section(security, "security"), "cost_analysis": section(cost, "cost"),
                       "configuration_analysis": section(configuration, "configuration"),
                       "root_cause_analysis": section(root_cause, "root_cause"),
                       "risk_assessment": section(risk, "risk"),
                       "investigation_analysis": section((), "investigation")})


def cause(address=RG, paths=(["tags", "probe"],), hypothesis="out_of_band_change", **extra) -> dict:
    return {"address": address, "cited_paths": [list(p) for p in paths], "hypothesis": hypothesis,
            "possible_channels": ["portal", "cli_or_sdk", "azure_policy"],
            "explanation": "Azure differs from the recorded state while the declaration did not change.",
            "basis": "inference", **extra}


def risk(address=RG, paths=(["tags", "probe"],), kind="apply_reverts_external_change", **extra) -> dict:
    return {"address": address, "cited_paths": [list(p) for p in paths], "risk_kind": kind,
            "explanation": "Applying the plan would revert the value set outside Terraform.", "basis": "inference",
            **extra}


class ScriptedLLM:
    def __init__(self, reply=None, error: BaseException | None = None):
        self.reply, self.error, self.prompts = reply, error, []

    def invoke(self, messages):
        self.prompts.append(messages)
        if self.error is not None:
            raise self.error
        return self.reply


HYPOTHESIS_FOR = {"outside_terraform": "out_of_band_change", "outside_terraform_converged": "out_of_band_change",
                  "configuration_side": "configuration_change", "both_sides": "out_of_band_change",
                  "value_unknown_until_apply": "provider_or_platform_behavior", "undetermined": "undetermined"}


class ConsistentLLM(ScriptedLLM):
    """A well-behaved fake: one hypothesis and one risk finding per change, consistent with its facts."""

    def invoke(self, messages):
        self.prompts.append(messages)
        evidence = shown(messages)
        causes, risks = [], []
        for r in evidence["resources"]:
            for c in r["changes"]:
                if "root_cause" in c["sections"]:
                    hypothesis = "lifecycle_change" if c["origin"]["lifecycle"] else \
                        HYPOTHESIS_FOR[c["origin"]["category"]]
                    causes.append(cause(r["address"], [c["path"]], hypothesis))
                if "risk" in c["sections"]:
                    kind = next((f for f in c["origin"]["risk_factors"] if f not in ("redacted_unreadable",
                                                                                     "moved_or_importing")), "other")
                    risks.append(risk(r["address"], [c["path"]], kind))
        return envelope(causes, risks)


def analyze(state, llm, limits=EvidenceLimits()):
    return make_analyze_drift(llm, limits)(state)


# --------------------------------------------------------------------------- deterministic origin facts

ORIGINS = [
    ("plan_evidence", "external_drift", {("outside_terraform", False)}),
    ("plan_evidence", "config_change", {("configuration_side", False)}),
    ("plan_evidence", "converged_drift", {("outside_terraform_converged", False)}),
    ("plan_evidence", "drift_and_config_change", {("both_sides", False)}),
    ("plan_evidence", "external_deletion", {("outside_terraform", True)}),
    ("plan_evidence", "resource_added", {("configuration_side", True)}),
    ("plan_evidence", "replace", {("configuration_side", False)}),
    ("root_cause_plans", "unconfigured_attribute_drift", {("outside_terraform", False)}),
    ("root_cause_plans", "undetermined_change", {("undetermined", False)}),
    ("root_cause_plans", "moved_resource", {("configuration_side", False)}),
    ("root_cause_plans", "policy_like_tag", {("outside_terraform", False)}),
    ("cost_config_plans", "vmss_zones_and_unknown_capacity",
     {("value_unknown_until_apply", False), ("outside_terraform", False)}),
]


@pytest.mark.parametrize(("group", "name", "expected"), ORIGINS, ids=[n for _, n, _ in ORIGINS])
def test_origin_categories(group, name, expected):
    facts = prepared(report(group, name))["origin_facts"]
    assert {(c["origin"], c["lifecycle"]) for c in facts["changes"]} == expected
    assert not {"actor", "confirmed"} & set(facts)  # attribution comes only from the investigation (Task 9B.4)


RISKS = [
    ("plan_evidence", "external_drift", ["apply_reverts_external_change"]),
    ("plan_evidence", "config_change", []),
    ("plan_evidence", "drift_and_config_change", ["apply_reverts_external_change", "ambiguous_intent"]),
    ("plan_evidence", "external_deletion", ["apply_destroys_or_recreates", "unmanaged_setting"]),
    ("plan_evidence", "replace", ["apply_destroys_or_recreates"]),
    ("root_cause_plans", "unconfigured_attribute_drift", ["apply_reverts_external_change", "unmanaged_setting"]),
    ("root_cause_plans", "undetermined_change", ["ambiguous_intent"]),
    ("root_cause_plans", "moved_resource", ["moved_or_importing"]),
    ("root_cause_plans", "importing_resource", ["moved_or_importing"]),
    ("root_cause_plans", "replace_cannot_update", ["apply_destroys_or_recreates"]),
    ("security_plans", "web_app_secret_changed", ["apply_reverts_external_change", "redacted_unreadable"]),
]


@pytest.mark.parametrize(("group", "name", "expected"), RISKS, ids=[n for _, n, _ in RISKS])
def test_resource_risk_factors(group, name, expected):
    resources = [r for r in prepared(report(group, name))["origin_facts"]["resources"]
                 if r["classification"] != "in_sync"]
    assert resources[0]["risk_factors"] == expected


def test_resource_facts_copy_engine_fields_without_previous_address():
    moved = prepared(rc("moved_resource"))["origin_facts"]["resources"][0]
    assert (moved["moved"], moved["importing"]) == (True, False)
    assert "azurerm_storage_account.legacy" not in json.dumps(moved)
    replace = prepared(rc("replace_cannot_update"))["origin_facts"]["resources"][0]
    assert replace["action_reason"] == "replace_because_cannot_update"


def test_noise_only_drift_has_nothing_to_analyze_and_makes_no_call():
    state = prepared(rc("noise_only_drift"))
    assert state["origin_facts"]["changes"] == [] and state["origin_facts"]["routes"] == []
    llm = ScriptedLLM(envelope())
    update = analyze(state, llm)
    assert llm.prompts == [] and update["llm_call"]["attempted"] is False


def test_routing_root_cause_all_non_noise_risk_only_with_factors():
    facts = prepared(real("config_change"))["origin_facts"]
    assert [(r["section"], r["path"]) for r in facts["routes"]] == [("root_cause", ["tags", "probe"])]
    facts = prepared(real("external_drift"))["origin_facts"]
    assert [r["section"] for r in facts["routes"]] == ["root_cause", "risk"]


def test_origin_facts_do_not_rewrite_the_report():
    drift_report = real("drift_and_config_change")
    state = prepared(drift_report)
    assert state["drift_report"] == drift_report
    facts = state["origin_facts"]["changes"][0]
    change = drift_report["resources"][0]["attribute_changes"][0]
    assert (facts["attribute_class"], facts["assessment"]) == (change["class"], change["assessment"]["category"])


# --------------------------------------------------------------------------- one call, five sections


def test_six_section_envelope_required():
    full = json.loads(envelope())
    assert set(full) == {"security_analysis", "cost_analysis", "configuration_analysis", "root_cause_analysis",
                         "risk_assessment", "investigation_analysis"}
    for missing in ("root_cause_analysis", "risk_assessment", "investigation_analysis"):
        partial = {k: v for k, v in full.items() if k != missing}
        with pytest.raises(InvalidEnvelope):
            parse_envelope(json.dumps(partial))
    with pytest.raises(InvalidEnvelope):
        parse_envelope(json.dumps({**full, "remediation": {"findings": [], "summary": ""}}))


@requires_ai
def test_one_call_one_http_request_with_all_five_sections():
    drift_report = report("cost_config_plans", "combined_security_cost_config")
    config = load_config({"AI_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "sk-test-not-real", "AI_LLM_MODEL": "m",
                          "OPENAI_BASE_URL": "https://llm.example.invalid/v1"})
    requests: list = []

    def handler(request):
        requests.append(request)
        body = {"id": "c", "object": "chat.completion", "created": 0, "model": "m",
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": envelope()}}]}
        return httpx.Response(200, json=body)

    model, _ = create_chat_model(config, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    state = run_analysis(drift_report, config=config, llm=model)
    assert len(requests) == 1 and state["llm_call"]["max_retries"] == 0
    assert {state["inferences"][k]["status"] for k in SECTIONS} == {"ok"}  # all five applicable, one request
    sent = json.loads(requests[0].content)["messages"][1]["content"]
    assert '"root_cause": {"applicable": true}' in sent and '"risk": {"applicable": true}' in sent


@requires_ai
@pytest.mark.parametrize("llm_kind", ["none", "ok", "failed", "invalid"])
def test_origin_facts_independent_of_llm_outcome(llm_kind):
    drift_report = rc("unconfigured_attribute_drift")
    baseline = run_analysis(copy.deepcopy(drift_report), config=load_config({}))
    llm = {"none": None, "ok": ConsistentLLM(), "invalid": ScriptedLLM("not json"),
           "failed": ScriptedLLM(error=TimeoutError("down"))}[llm_kind]
    state = run_analysis(copy.deepcopy(drift_report), llm=llm) if llm else baseline
    for key in ("parsed_drift", "security_targets", "cost_targets", "config_targets", "origin_facts"):
        assert state[key] == baseline[key]
    assert isinstance(state["origin_facts"], FrozenDict)


@requires_ai
@pytest.mark.parametrize("mode", ["replace", "mutate", "confirm"])
def test_origin_facts_cannot_be_changed(mode):
    def later(state):
        if mode == "mutate":
            state["origin_facts"]["changes"].pop()
        elif mode == "confirm":
            state["origin_facts"]["confirmed"] = True  # FrozenDict rejects the write
        return {"origin_facts": {"actor": "admin"}} if mode == "replace" else {}

    graph = StateGraph(AiState)
    for name, node in (("parse_drift", parse_drift), ("derive_origin_risk", derive_origin_risk), ("later", later)):
        graph.add_node(name, node)
    graph.add_edge(START, "parse_drift")
    graph.add_edge("parse_drift", "derive_origin_risk")
    graph.add_edge("derive_origin_risk", "later")
    graph.add_edge("later", END)
    with pytest.raises(EvidenceMutationError):
        graph.compile().invoke({"drift_report": real("external_drift")})


# --------------------------------------------------------------------------- evidence: allowlist, redaction


@requires_ai
def test_prompt_evidence_carries_origin_facts_only_through_the_allowlist():
    llm = ScriptedLLM(envelope())
    analyze(prepared(rc("moved_resource")), llm)
    evidence = shown(llm.prompts[0])
    [resource] = evidence["resources"]
    assert set(resource) == {"address", "type", "classification", "action", "drift_action", "ambiguous", "notes",
                             "severity", "changes", "risk_factors", "moved", "importing", "action_reason"}
    assert resource["moved"] is True
    for change in resource["changes"]:
        assert set(change["origin"]) == {"category", "lifecycle", "risk_factors"}
    # No previous-address field anywhere; the address appears only inside the engine's own `notes`
    # text ("moved from ..."), which is allowlisted as documented since Task 6.3.
    assert "previous_address" not in json.dumps(evidence)
    assert "legacy" not in json.dumps({k: v for k, v in resource.items() if k != "notes"})
    assert "synthetic-root-cause-fixture" not in llm.prompts[0][1].content  # no run metadata


@requires_ai
def test_redacted_values_stay_status_only_for_root_cause_and_risk():
    llm = ScriptedLLM(envelope())
    analyze(prepared(report("security_plans", "web_app_secret_changed")), llm)
    text = llm.prompts[0][1].content
    assert "SYNTHETIC-SECRET" not in text
    [change] = shown(llm.prompts[0])["resources"][0]["changes"]
    assert {"root_cause", "risk"} <= set(change["sections"])
    assert "redacted_unreadable" in change["origin"]["risk_factors"]


def test_redaction_fail_closed_still_applies():
    state = prepared(report("security_plans", "web_app_secret_changed"))
    state = dict(state, parsed_drift=copy.deepcopy(state["parsed_drift"]))
    state["parsed_drift"]["resources"][0]["attribute_changes"][0]["real"] = {"status": "value", "value": "leak"}
    llm = ScriptedLLM(envelope())
    with pytest.raises(EvidenceIntegrityError):
        analyze(state, llm)
    assert llm.prompts == []


# --------------------------------------------------------------------------- hypothesis / evidence consistency

CONSISTENCY = [
    ("plan_evidence", "external_drift", RG, ["tags", "probe"], "out_of_band_change", True),
    ("plan_evidence", "external_drift", RG, ["tags", "probe"], "azure_policy_or_automation", True),
    ("plan_evidence", "external_drift", RG, ["tags", "probe"], "configuration_change", False),
    ("plan_evidence", "external_drift", RG, ["tags", "probe"], "lifecycle_change", False),
    ("plan_evidence", "config_change", RG, ["tags", "probe"], "configuration_change", True),
    ("plan_evidence", "config_change", RG, ["tags", "probe"], "out_of_band_change", False),
    ("plan_evidence", "config_change", RG, ["tags", "probe"], "azure_policy_or_automation", False),
    ("plan_evidence", "config_change", RG, ["tags", "probe"], "provider_or_platform_behavior", True),
    ("plan_evidence", "drift_and_config_change", RG, ["tags", "probe"], "configuration_change", True),
    ("plan_evidence", "drift_and_config_change", RG, ["tags", "probe"], "out_of_band_change", True),
    ("plan_evidence", "converged_drift", RG, ["tags", "probe"], "configuration_change", False),
    ("plan_evidence", "resource_added", RG_EXTRA, ["location"], "lifecycle_change", True),
    ("plan_evidence", "resource_added", RG_EXTRA, ["location"], "out_of_band_change", False),
    ("root_cause_plans", "undetermined_change", SA, ["access_tier"], "undetermined", True),
    ("root_cause_plans", "undetermined_change", SA, ["access_tier"], "out_of_band_change", False),
]


@pytest.mark.parametrize(("group", "name", "address", "path", "hypothesis", "accepted"), CONSISTENCY)
@requires_ai
def test_hypothesis_must_agree_with_origin(group, name, address, path, hypothesis, accepted):
    state = prepared(report(group, name))
    result = analyze(state, ScriptedLLM(envelope([cause(address, (path,), hypothesis)])))["inferences"]
    root = result["analyze_root_cause"]
    assert root["status"] == "ok"
    if accepted:
        [kept] = root["findings"]
        assert not {"actor", "confirmed", "confirmation_requires"} & set(kept)  # no AI attribution (Task 9B.4)
        assert kept["origin_facts"][0]["path"] == path
    else:
        assert root["findings"] == []
        assert root["rejected_findings"] == [{"index": 0, "reason": "hypothesis_contradicts_evidence"}]


@requires_ai
def test_mixed_citations_must_all_agree():
    state = prepared(rc("unconfigured_attribute_drift"))
    reply = envelope([cause(SA, (["large_file_share_enabled"], ["nonexistent"]))])
    root = analyze(state, ScriptedLLM(reply))["inferences"]["analyze_root_cause"]
    assert root["rejected_findings"] == [{"index": 0, "reason": "unsupported_citation"}]


@requires_ai
@pytest.mark.parametrize("bad", [{"actor": "admin@contoso.com"}, {"actor": None}, {"confirmed": True},
                                 {"confirmed": "false"}, {"possible_channels": []},
                                 {"possible_channels": ["the_ops_team"]}, {"hypothesis": "manual_portal_edit"},
                                 {"caller_identity": "x"}, {"explanation": "x" * 601}])
def test_root_cause_schema_constants_and_limits(bad):
    state = prepared(real("external_drift"))
    inferences = analyze(state, ScriptedLLM(envelope([cause(**bad)])))["inferences"]
    assert inferences["analyze_root_cause"]["status"] == "invalid_output"
    assert inferences["analyze_root_cause"]["findings"] == []


@requires_ai
def test_root_cause_findings_cap():
    state = prepared(real("external_drift"))
    inferences = analyze(state, ScriptedLLM(envelope([cause()] * 21)))["inferences"]
    assert inferences["analyze_root_cause"]["status"] == "invalid_output"


# --------------------------------------------------------------------------- risk assessment


@requires_ai
@pytest.mark.parametrize(("kind", "accepted", "flagged"), [
    ("apply_reverts_external_change", True, False),
    ("apply_destroys_or_recreates", False, False),
    ("ambiguous_intent", False, False),
    ("evidence_incomplete", False, False),
    ("other", True, True),
])
def test_risk_kind_must_match_deterministic_factors(kind, accepted, flagged):
    state = prepared(real("external_drift"))
    result = analyze(state, ScriptedLLM(envelope(risk=[risk(kind=kind)])))["inferences"]["assess_risk"]
    if accepted:
        [kept] = result["findings"]
        assert kept["risk_kind_unverified"] is flagged
        assert kept["risk_factors"] == ["apply_reverts_external_change"]
        assert kept["deterministic_severity"] == "LOW"
    else:
        assert result["rejected_findings"] == [{"index": 0, "reason": "risk_not_supported_by_evidence"}]


@requires_ai
def test_evidence_incomplete_supported_by_redaction_or_truncation():
    secret = prepared(report("security_plans", "web_app_secret_changed"))
    reply = envelope(risk=[risk("azurerm_linux_web_app.this", (["site_config"],), "evidence_incomplete")])
    assert len(analyze(secret, ScriptedLLM(reply))["inferences"]["assess_risk"]["findings"]) == 1
    combined = prepared(report("cost_config_plans", "combined_security_cost_config"))
    reply = envelope(risk=[risk("azurerm_network_security_group.this", (["security_rule"],), "evidence_incomplete")])
    truncated = analyze(combined, ScriptedLLM(reply), EvidenceLimits(max_value_chars=20))["inferences"]["assess_risk"]
    assert len(truncated["findings"]) == 1


@requires_ai
@pytest.mark.parametrize("bad", [{"risk_level": "HIGH"}, {"severity": "LOW"}, {"likelihood": "high"},
                                 {"risk_kind": "data_loss"}])
def test_risk_schema_has_no_rating(bad):
    state = prepared(real("external_drift"))
    assert analyze(state, ScriptedLLM(envelope(risk=[risk(**bad)])))["inferences"]["assess_risk"]["status"] \
        == "invalid_output"


@requires_ai
def test_risk_citations_scoped_to_risk_section():
    state = prepared(real("config_change"))  # tags.probe: root cause yes, no risk factor -> not sent for risk
    reply = envelope([cause(paths=(["tags", "probe"],), hypothesis="configuration_change")],
                     [risk(paths=(["tags", "probe"],), kind="other")])
    inferences = analyze(state, ScriptedLLM(reply))["inferences"]
    assert len(inferences["analyze_root_cause"]["findings"]) == 1
    assert inferences["assess_risk"]["status"] == "skipped"
    assert inferences["assess_risk"]["rejected_findings"] == [{"index": 0, "reason": "section_not_applicable"}]


# --------------------------------------------------------------------------- attribution and remediation guards


@pytest.mark.parametrize("text", [
    "The tag was changed by admin@contoso.com.", "Changed by John in the portal.", "An administrator changed it.",
    "someone probably modified the SKU", "Object 1b4e28ba-2fa1-11d2-883f-0016d3cca427 deleted it",
    "a user has disabled HTTPS", "The engineer likely removed the rule", "updated manually by the ops team",
    "jane.doe@example.org set this value",
])
def test_attribution_guard_flags_actor_claims(text):
    assert contains_attribution_claim(text) and free_text_violation(text) == "unsupported_attribution"


@pytest.mark.parametrize("text", [
    "The change happened outside Terraform; the actor is unknown.", "Azure differs from the recorded state.",
    "Terraform would revert this on the next apply.", "The value was changed outside this Terraform run.",
    "The declared value was changed by the configuration.", "Activity Log evidence is needed to identify who.",
    "The rule allows SSH from any source.", "A Policy-like tag key appeared outside Terraform.",
])
def test_attribution_guard_allows_neutral_text(text):
    assert not contains_attribution_claim(text)


@pytest.mark.parametrize("text", [
    "Run terraform apply to revert it.", "You should restore the tag.", "We recommend setting GRS back to LRS.",
    "To fix this, re-apply the plan.", "Use terraform import for the new account.", "Please revert the change.",
    "Consider updating the configuration.", "terraform state rm the resource", "Teams must review this.",
])
def test_remediation_guard_flags_fix_instructions(text):
    assert contains_remediation_claim(text)


@pytest.mark.parametrize("text", [
    "Terraform would revert this value on the next apply.", "Applying the plan would recreate the account.",
    "The plan proposes an update.", "Reverting would re-replicate data.", "The configuration declares LRS.",
])
def test_remediation_guard_allows_descriptions(text):
    assert not contains_remediation_claim(text)


@requires_ai
@pytest.mark.parametrize(("text", "reason"), [
    ("Changed by admin@contoso.com via the portal.", "unsupported_attribution"),
    ("You should run terraform apply now.", "remediation_not_allowed"),
])
def test_guards_apply_to_every_section(text, reason):
    state = prepared(report("cost_config_plans", "combined_security_cost_config"))
    nsg, sa = "azurerm_network_security_group.this", SA
    reply = envelope(
        security=[{"address": nsg, "cited_paths": [["security_rule"]], "exposure": "network_exposure",
                   "ai_assessed_impact": "CRITICAL", "explanation": text, "basis": "inference"}],
        cost=[{"address": sa, "cited_paths": [["account_replication_type"]], "cost_driver": "sku_or_tier",
               "direction": "likely_increase", "monetary_impact": "not_determinable_from_evidence",
               "explanation": text, "basis": "inference"}],
        configuration=[{"address": sa, "cited_paths": [["tags", "owner"]], "topic": "other",
                        "explanation": text, "basis": "inference"}],
        root_cause=[cause(sa, (["tags", "owner"],), explanation=text)],
        risk=[risk(sa, (["tags", "owner"],), explanation=text)],
        summaries={"security": text, "risk": text})
    inferences = analyze(state, ScriptedLLM(reply))["inferences"]
    for key in SECTIONS:
        assert inferences[key]["findings"] == []
        assert {"index": 0, "reason": reason} in inferences[key]["rejected_findings"]
    assert inferences["analyze_security"]["summary"] is None
    assert {"index": None, "reason": f"summary_{reason}"} in inferences["assess_risk"]["rejected_findings"]


@requires_ai
def test_injected_actor_and_fix_are_escaped_and_echoes_rejected():
    state = prepared(rc("injection_attribution"))
    echo = envelope([cause(SA, (["tags", "note"],), explanation="The note says it was changed by admin@contoso.com.")],
                    [risk(SA, (["tags", "note"],), explanation="You should run terraform apply now to fix this.")])
    llm = ScriptedLLM(echo)
    inferences = analyze(state, llm)["inferences"]
    assert "admin@contoso.com" not in llm.prompts[0][1].content  # an identity: withheld from the public report
    assert llm.prompts[0][1].content.count(f"</{EVIDENCE_TAG}>") == 1
    assert inferences["analyze_root_cause"]["rejected_findings"] == [{"index": 0, "reason": "unsupported_attribution"}]
    assert inferences["assess_risk"]["rejected_findings"] == [{"index": 0, "reason": "remediation_not_allowed"}]


def test_system_prompt_states_the_boundaries():
    for phrase in ("Caller identities are withheld", "Do not claim who or what made a change",
                   "Do not recommend remediation", "No risk level", "unconfirmed hypotheses", "possible_channels",
                   "upgrade or contradict them", "operations, not property values"):
        assert phrase in SYSTEM_PROMPT


# --------------------------------------------------------------------------- acceptance end to end


@requires_ai
@pytest.mark.parametrize(("group", "name"), [
    ("plan_evidence", "external_drift"), ("plan_evidence", "config_change"), ("plan_evidence", "external_deletion"),
    ("plan_evidence", "drift_and_config_change"), ("root_cause_plans", "unconfigured_attribute_drift"),
    ("root_cause_plans", "moved_resource"), ("root_cause_plans", "replace_cannot_update"),
    ("root_cause_plans", "policy_like_tag"), ("root_cause_plans", "undetermined_change"),
])
def test_consistent_model_output_is_accepted_end_to_end(group, name):
    llm = ConsistentLLM()
    inferences = analyze(prepared(report(group, name)), llm)["inferences"]
    root, risk_result = inferences["analyze_root_cause"], inferences["assess_risk"]
    assert root["status"] == "ok" and root["rejected_findings"] == [] and root["findings"]
    assert all(f["basis"] == "inference" and "actor" not in f for f in root["findings"])
    assert risk_result["rejected_findings"] == []
    assert len(llm.prompts) == 1


# --------------------------------------------------------------------------- scope and all-citations checks


@requires_ai
def test_every_cited_change_must_agree_not_just_one():
    # zones: outside_terraform; instances: value_unknown_until_apply. Both are valid citations.
    vmss = "azurerm_linux_virtual_machine_scale_set.this"
    state = prepared(report("cost_config_plans", "vmss_zones_and_unknown_capacity"))
    both = (["zones"], ["instances"])
    result = analyze(state, ScriptedLLM(envelope([cause(vmss, both, "out_of_band_change"),
                                                  cause(vmss, both, "provider_or_platform_behavior")])))
    root = result["inferences"]["analyze_root_cause"]
    assert root["rejected_findings"] == [{"index": 0, "reason": "hypothesis_contradicts_evidence"}]
    assert [f["hypothesis"] for f in root["findings"]] == ["provider_or_platform_behavior"]


@requires_ai
def test_root_cause_citation_limited_to_changes_sent_for_root_cause():
    # With one root-cause slot, the second change is still sent (configuration) but not for root cause.
    state = prepared(rc("unconfigured_attribute_drift"))
    combined = prepared(report("cost_config_plans", "storage_config_mix"))
    llm = ScriptedLLM(envelope([cause(SA, (["tags", "owner"],), "out_of_band_change")]))
    root = analyze(combined, llm, EvidenceLimits(max_root_cause_changes=1))["inferences"]["analyze_root_cause"]
    sent = {tuple(c["path"]): c["sections"] for c in shown(llm.prompts[0])["resources"][0]["changes"]}
    assert "configuration" in sent[("tags", "owner")] and "root_cause" not in sent[("tags", "owner")]
    assert root["rejected_findings"] == [{"index": 0, "reason": "unsupported_citation"}]
    assert state["origin_facts"]["routes"]  # sanity: the fixture routes root cause normally


@requires_ai
def test_risk_citation_limited_to_changes_sent_for_risk():
    # resource_added: managed_by is unconfigured (risk factor); location has no factor (root cause only).
    state = prepared(real("resource_added"))
    reply = envelope(risk=[risk(RG_EXTRA, (["location"],), "other"), risk(RG_EXTRA, (["managed_by"],), "other")])
    result = analyze(state, ScriptedLLM(reply))["inferences"]["assess_risk"]
    assert result["rejected_findings"] == [{"index": 0, "reason": "unsupported_citation"}]
    assert [f["cited_paths"] for f in result["findings"]] == [[["managed_by"]]]
