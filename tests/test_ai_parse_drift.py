"""Task 6.2: the deterministic `parse_drift` node.

Sample `drift_report.json` files are produced by drift_engine itself from the
sanitized plan fixtures (tests/fixtures/plan_evidence), so they always follow
the current report contract instead of a hand-written copy of it.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import logging
from pathlib import Path

import pytest

from ai_engine.nodes.parse_drift import (
    DriftReportError,
    load_drift_report,
    parse_drift,
    validate_drift_report,
)
from drift_engine.classifier import evaluate

HAS_AI_EXTRA = all(importlib.util.find_spec(m) for m in ("langgraph", "langchain_openai"))
requires_ai = pytest.mark.skipif(not HAS_AI_EXTRA, reason="needs the 'ai' extra")
if HAS_AI_EXTRA:
    from langgraph.graph import END, START, StateGraph

    from ai_engine.config import load_config
    from ai_engine.graph import AiState, EvidenceMutationError, FrozenDict, build_graph, run_analysis

EVIDENCE = Path(__file__).parent / "fixtures" / "plan_evidence"
SCENARIOS = sorted(p.name for p in EVIDENCE.iterdir() if p.is_dir())
RG = 'module.resource_group.azurerm_resource_group.this["main"]'


def report_for(scenario: str) -> dict:
    # failed_run has no plan: evaluate() then reports the manifest's failure.
    return evaluate(str(EVIDENCE / scenario / "plan.sanitized.json"),
                    str(EVIDENCE / scenario / "detection_run.json")).report


@pytest.fixture
def report_file(tmp_path):
    def write(scenario: str) -> Path:
        path = tmp_path / "drift_report.json"
        path.write_text(json.dumps(report_for(scenario)), encoding="utf-8")
        return path
    return write


# --------------------------------------------------------------------------- node on every sample report


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_parse_every_sample_report(scenario, report_file):
    report = load_drift_report(report_file(scenario))
    original = copy.deepcopy(report)
    parsed = parse_drift({"drift_report": report})["parsed_drift"]

    targets = [r for r in report["resources"] if r["classification"] != "in_sync"]
    assert parsed["outcome"] == report["outcome"]
    assert parsed["has_drift"] is report["has_drift"]
    # Resource diffs are the contract's own DriftItem JSON, unchanged.
    assert parsed["resources"] == targets
    assert parsed["resource_types"] == sorted({r["type"] for r in targets})
    summaries = parsed["resource_summaries"]
    assert [s["address"] for s in summaries] == [r["address"] for r in targets]
    for summary, resource in zip(summaries, targets):
        assert {k: summary[k] for k in ("type", "classification", "action", "drift_action", "ambiguous")} == \
               {k: resource[k] for k in ("type", "classification", "action", "drift_action", "ambiguous")}
        assert summary["severity"] == resource["severity"]["level"]  # copied from the report, not computed
        assert summary["changed_attributes"] == sorted({c["attribute"] for c in resource["attribute_changes"]})
        assert summary["attribute_change_count"] == len(resource["attribute_changes"])
        assert summary["redacted_change_count"] == sum(c["redacted"] for c in resource["attribute_changes"])
    if report["summary"]:
        # is_drift reproduces the classifier's own count.
        assert sum(s["is_drift"] for s in summaries) == report["summary"]["drifted_resources"]
    assert report == original
    json.dumps(parsed)  # plain JSON data


def test_external_drift_sample():
    update = parse_drift({"drift_report": report_for("external_drift")})
    assert "warnings" not in update
    assert update["parsed_drift"]["resource_types"] == ["azurerm_resource_group"]
    assert update["parsed_drift"]["resource_summaries"] == [{
        "address": RG,
        "type": "azurerm_resource_group",
        "classification": "external_drift",
        "action": "update",
        "drift_action": "update",
        "is_drift": True,
        "severity": "LOW",
        "changed_attributes": ["tags"],
        "attribute_change_count": 1,
        "redacted_change_count": 0,
        "ambiguous": False,
    }]
    resource = update["parsed_drift"]["resources"][0]
    assert resource["severity"] == {"level": "LOW", "reasons": ["tags.probe: tags"]}
    change = resource["attribute_changes"][0]
    assert change["path"] == ["tags", "probe"] and change["class"] == "drifted"
    assert change["real"] == {"status": "absent"}
    assert change["severity"] == {"level": "LOW", "rules": ["tags"]}
    assert change["assessment"] == {"category": "configured", "noise_rule": None}


def test_severity_is_consumed_not_computed():
    """The node copies the report's severity verbatim, even a value the rules would not give."""
    report = report_for("external_drift")
    report["resources"][0]["severity"] = {"level": "CRITICAL", "reasons": ["injected for the test"]}
    [summary] = parse_drift({"drift_report": report})["parsed_drift"]["resource_summaries"]
    assert summary["severity"] == "CRITICAL"


def test_ai_engine_never_imports_rating_logic():
    """Severity is decided by drift_engine from the raw plan; ai_engine must not re-derive it."""
    import ast

    package = Path(__file__).parent.parent / "src" / "ai_engine"
    forbidden = {"drift_engine.severity", "drift_engine.comparator", "drift_engine.parser"}
    for path in package.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                names = {node.module or ""} | {f"{node.module}.{a.name}" for a in node.names}
            elif isinstance(node, ast.Import):
                names = {a.name for a in node.names}
            else:
                continue
            assert not names & forbidden, f"{path.name} imports {names & forbidden}"


def test_pre_severity_report_rejected():
    report = report_for("external_drift")
    report["classification_version"] = "1"
    for resource in report["resources"]:
        del resource["severity"]
    with pytest.raises(DriftReportError, match="classification_version"):
        parse_drift({"drift_report": report})


def test_in_sync_resources_are_not_targets():
    parsed = parse_drift({"drift_report": report_for("resource_added")})["parsed_drift"]
    assert [s["classification"] for s in parsed["resource_summaries"]] == ["resource_added"]
    assert parsed["resource_summaries"][0]["is_drift"] is False  # a planned create is not drift

    parsed = parse_drift({"drift_report": report_for("in_sync")})["parsed_drift"]
    assert parsed["resources"] == [] and parsed["resource_summaries"] == [] and parsed["has_drift"] is False


def test_config_change_is_a_target_but_not_drift():
    summary = parse_drift({"drift_report": report_for("config_change")})["parsed_drift"]["resource_summaries"]
    assert [(s["classification"], s["is_drift"]) for s in summary] == [("config_change", False)]


def test_failed_report_yields_empty_parse_and_warning():
    update = parse_drift({"drift_report": report_for("failed_run")})
    assert update["parsed_drift"] == {"outcome": "failed", "has_drift": None, "resources": [],
                                      "resource_types": [], "resource_summaries": []}
    assert update["warnings"] == ["drift detection failed (detection_run, stage plan): "
                                  "drift status unknown, no resources to analyze"]


def test_log_event_has_counts_not_values(caplog):
    caplog.set_level(logging.INFO, logger="ai_engine")
    parse_drift({"drift_report": report_for("external_drift")})
    [record] = [r for r in caplog.records if getattr(r, "event", None) == "drift_parsed"]
    assert record.fields == {"outcome": "succeeded", "has_drift": True, "resources_total": 1,
                             "target_resources": 1, "resource_types": ["azurerm_resource_group"]}


# --------------------------------------------------------------------------- contract validation

SENSITIVE = "s3cr3t-value-must-not-leak"


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda r: r.pop("resources"),
        lambda r: r.__setitem__("unexpected", SENSITIVE),
        lambda r: r["resources"][0].__setitem__("classification", SENSITIVE),
        lambda r: r["resources"][0]["attribute_changes"][0]["real"].update(status=SENSITIVE),
        lambda r: r.__setitem__("has_drift", None),  # succeeded report must say true/false
        lambda r: r["summary"].__setitem__("drifted_resources", "1"),  # strict: no coercion
    ],
    ids=["missing-field", "extra-field", "bad-classification", "bad-view", "invariant", "strict-type"],
)
def test_contract_violations_rejected_without_values(corrupt):
    report = report_for("external_drift")
    corrupt(report)
    with pytest.raises(DriftReportError, match="does not match the drift_engine report contract") as info:
        parse_drift({"drift_report": report})
    assert SENSITIVE not in str(info.value)
    assert info.value.__cause__ is None and info.value.__suppress_context__


@pytest.mark.parametrize("value", [None, [], "drift_report.json"])
def test_non_object_report_rejected(value):
    with pytest.raises(DriftReportError, match="must be a JSON object"):
        validate_drift_report(value)


@pytest.mark.parametrize(
    ("text", "message"),
    [("{not json", "not valid JSON"), ('{"a": NaN}', "non-JSON constant NaN"), ("[]", "must be a JSON object")],
)
def test_load_rejects_bad_files(tmp_path, text, message):
    path = tmp_path / "drift_report.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(DriftReportError, match=message):
        load_drift_report(path)


# --------------------------------------------------------------------------- inside the graph


class _CountingLLM:
    """An available LLM that answers with no findings and counts its calls."""

    def __init__(self):
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        empty = {"findings": [], "summary": ""}
        return json.dumps({"security_analysis": empty, "cost_analysis": empty, "configuration_analysis": empty})


@requires_ai
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_graph_runs_parse_drift(scenario, report_file):
    report = load_drift_report(report_file(scenario))
    llm = _CountingLLM()
    state = run_analysis(report, llm=llm)
    assert state["parsed_drift"] == parse_drift({"drift_report": report})["parsed_drift"]
    assert isinstance(state["parsed_drift"], FrozenDict)
    assert state["drift_report"] == report
    # Deterministic data never lands in the AI output channel; only the AI node writes there.
    assert set(state["inferences"]) == {"analyze_security", "analyze_cost", "analyze_configuration"}
    assert state["llm"]["available"] is True
    # At most one LLM call per run (Task 6.4), and only when some section was routed.
    routed = any(state[k]["changes"] for k in ("security_targets", "cost_targets", "config_targets"))
    assert llm.calls == (1 if routed else 0) and state["llm_call"]["attempted"] is routed


@requires_ai
def test_graph_failed_report_warns_and_completes():
    state = run_analysis(report_for("failed_run"), config=load_config({}))
    assert state["parsed_drift"]["resources"] == []
    assert any("drift status unknown" in w for w in state["warnings"])


@requires_ai
def test_graph_rejects_contract_violation():
    report = report_for("external_drift")
    report["resources"][0]["classification"] = "made_up"
    with pytest.raises(DriftReportError):
        run_analysis(report, config=load_config({}))


def _graph_after_parse(node):
    graph = StateGraph(AiState)
    graph.add_node("parse_drift", parse_drift)
    graph.add_node("later", node)
    graph.add_edge(START, "parse_drift")
    graph.add_edge("parse_drift", "later")
    graph.add_edge("later", END)
    return graph.compile()


@requires_ai
def test_later_node_cannot_modify_parsed_drift():
    def node(state):
        state["parsed_drift"]["resource_summaries"][0]["changed_attributes"].append("invented")
        return {}

    with pytest.raises(EvidenceMutationError):
        _graph_after_parse(node).invoke({"drift_report": report_for("external_drift")})


@requires_ai
def test_later_node_cannot_replace_parsed_drift():
    def node(state):
        return {"parsed_drift": {"resources": []}}

    with pytest.raises(EvidenceMutationError, match="parsed_drift is immutable"):
        _graph_after_parse(node).invoke({"drift_report": report_for("external_drift")})


@requires_ai
def test_compiled_graph_order():
    edges = {(e.source, e.target) for e in build_graph(config=load_config({})).get_graph().edges}
    assert edges == {(START, "initialize"), ("initialize", "parse_drift"), ("parse_drift", "classify_drift"),
                     ("classify_drift", "route_cost_config"), ("route_cost_config", "analyze_drift"),
                     ("analyze_drift", END)}
