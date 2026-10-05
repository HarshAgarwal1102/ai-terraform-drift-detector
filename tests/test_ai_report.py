"""Task 6.6: deterministic remediation options and deterministic report generation.

Reports come from drift_engine run on the real and synthetic fixtures (incl.
tests/fixtures/report_plans, see build.py there). Every LLM is a fake or a local
httpx.MockTransport; tests/conftest.py blocks any non-loopback connection.
Nothing is ever executed.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import shlex
from pathlib import Path

import pytest

from ai_engine.nodes.cost_analysis import route_cost_config
from ai_engine.nodes.parse_drift import parse_drift
from ai_engine.nodes.report_generator import (  # pydantic only: no 'ai' extra needed
    AiAnalysisReport,
    md_code,
    md_text,
    render_markdown,
    write_report,
)
from ai_engine.nodes.remediation import (
    COMMAND_CATALOGUE,
    RemediationPlan,
    hcl_string,
    hcl_value,
    plan_remediation,
    render_command,
    value_fragment,
)
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
SECTIONS = ("analyze_security", "analyze_cost", "analyze_configuration", "analyze_root_cause", "assess_risk")
AVAILABLE = {"available": True, "provider": "fake", "model": "fake-model", "reason": None}
RG = 'module.resource_group.azurerm_resource_group.this["main"]'


def report(group: str, name: str) -> dict:
    base = FIXTURES / group / name
    plan = next((base / f for f in ("plan.synthetic.json", "plan.sanitized.json") if (base / f).exists()),
                base / "plan.json")
    return _public(evaluate(str(plan), str(base / "detection_run.json")))


def deterministic_state(drift_report: dict) -> dict:
    state = {"drift_report": drift_report, "llm": AVAILABLE}
    for node in (parse_drift, classify_drift, route_cost_config, derive_origin_risk, plan_remediation):
        state.update(node(state))
    return state


def options(group, name):
    return deterministic_state(report(group, name))["remediation_plan"]["options"]


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


# --------------------------------------------------------------------------- option table

TABLE = [
    ("plan_evidence", "external_drift", [("restore_declared", True, False), ("accept_remote_value", False, False)]),
    ("plan_evidence", "config_change", [("apply_pending_change", True, False), ("keep_current_value", False, False)]),
    ("plan_evidence", "converged_drift", [("no_infrastructure_change", True, False),
                                          ("refresh_state_only", False, False)]),
    ("plan_evidence", "drift_and_config_change", [("restore_declared", True, False),
                                                  ("accept_remote_value", False, False),
                                                  ("investigate", False, False)]),
    ("plan_evidence", "external_deletion", [("recreate_deleted_object", True, False),
                                            ("stop_managing_without_destroy", False, False)]),
    ("plan_evidence", "resource_added", [("create_declared_object", True, False)]),
    ("plan_evidence", "replace", [("replace_object", True, True), ("keep_current_value", False, False)]),
    ("root_cause_plans", "undetermined_change", [("restore_declared", True, False),
                                                 ("investigate", False, False)]),
    ("root_cause_plans", "moved_resource", [("apply_pending_change", True, False),
                                            ("keep_current_value", False, False)]),
]


@pytest.mark.parametrize(("group", "name", "expected"), TABLE, ids=[n for _, n, _ in TABLE])
def test_option_table(group, name, expected):
    got = [(o["kind"], o["plan_default"], o["destructive"]) for o in options(group, name)]
    changed = {o["address"] for o in options(group, name)}  # in-sync resources get no options
    assert len(changed) == 1
    assert got == expected


def test_resource_removed_delete_is_destructive_with_non_destructive_alternative():
    by_kind = {o["kind"]: o for o in options("plan_evidence", "resource_removed")
               if o["address"].endswith('["main"]')}
    delete = by_kind["delete_undeclared_object"]
    assert (delete["plan_default"], delete["destructive"], delete["mutates"]) == (True, True, "infrastructure")
    assert delete["approval"]["destructive_confirmation_required"] is True
    keep = by_kind["stop_managing_without_destroy"]
    assert (keep["destructive"], keep["mutates"]) == (False, "configuration_and_state")
    assert [c["template_id"] for c in keep["commands"]] == ["state_rm", "plan_review"]


def test_external_deletion_flags_data_not_restored():
    [recreate] = [o for o in options("plan_evidence", "external_deletion") if o["kind"] == "recreate_deleted_object"]
    assert recreate["data_not_restored"] is True and recreate["destructive"] is False


def test_ambiguous_and_undetermined_require_human_decision():
    for group, name in (("plan_evidence", "drift_and_config_change"), ("root_cause_plans", "undetermined_change")):
        assert {o["human_decision_required"] for o in options(group, name)} == {True}
    assert {o["human_decision_required"] for o in options("plan_evidence", "external_drift")} == {False}


def test_plan_default_marks_only_the_plan_direction():
    for group, name, _ in TABLE:
        opts = options(group, name)
        defaults = [o for o in opts if o["plan_default"]]
        assert len(defaults) == 1  # exactly the option that mirrors the plan
        [changed] = [r for r in report(group, name)["resources"] if r["classification"] != "in_sync"]
        assert defaults[0]["terraform_plan_action"] == changed["action"]
        assert all(o["terraform_plan_action"] is None for o in opts if not o["plan_default"])
    plan = deterministic_state(report("plan_evidence", "replace"))["remediation_plan"]
    assert plan["recommendation_policy_version"] == "1"
    # A destructive plan direction is still marked plan_default: it describes the plan, it does not endorse it,
    # and policy v1 (R2) recommends nothing for it (Task 9B.4).
    [replace] = [o for o in plan["options"] if o["plan_default"]]
    assert replace["destructive"] is True and replace["terraform_plan_action"] == "replace"
    [recommendation] = plan["recommendations"]
    assert (recommendation["decision"], recommendation["policy_rule"], recommendation["option_id"]) == (
        "human_decision_required", "R2", None)
    schema = RemediationPlan.model_json_schema()
    option_schema = str(schema["$defs"]["RemediationOption"]).lower()
    assert "rank" not in option_schema and "recommend" not in option_schema  # options carry no ranking


def test_failed_report_has_no_options():
    plan = deterministic_state(report("plan_evidence", "failed_run"))["remediation_plan"]
    assert plan["options"] == [] and "drift status unknown" in plan["reason"]


# --------------------------------------------------------------------------- execution, commands, scope


ALL_FIXTURES = [(g, p.name) for g in ("plan_evidence", "security_plans", "cost_config_plans", "root_cause_plans",
                                      "report_plans") for p in sorted((FIXTURES / g).iterdir()) if p.is_dir()]


@pytest.mark.parametrize(("group", "name"), ALL_FIXTURES, ids=[f"{g}/{n}" for g, n in ALL_FIXTURES])
def test_no_execution_and_catalogue_only_commands(group, name):
    drift_report = report(group, name)
    state = deterministic_state(drift_report)
    plan = state["remediation_plan"]
    assert (plan["approval_required"], plan["automatic_apply"]) == (True, False)
    working_dir = (drift_report.get("run") or {}).get("working_dir")
    changed = {r["address"]: r for r in state["parsed_drift"]["resources"]}
    for option in plan["options"]:
        assert option["execution"] == {"allowed": False, "automatic_apply": False, "mode": "manual_after_approval"}
        assert option["approval"]["status"] == "pending" and option["approval"]["required"] is True
        # scope: only affected resources and their own changed paths
        assert option["address"] in changed
        paths = {tuple(c["path"]) for c in changed[option["address"]]["attribute_changes"]}
        for item in option["fragments"] + option["fragment_gaps"] + option["evidence"]:
            assert tuple(item["path"]) in paths
        # commands: exactly a catalogue template, rendered from report values only
        for command in option["commands"]:
            expected = render_command(command["template_id"], working_dir,
                                      option["address"] if command["template_id"] == "state_rm" else None)
            assert command == expected
            assert "-auto-approve" not in command["command"] and "destroy" not in command["command"]


def test_catalogue_is_fixed_and_has_no_auto_apply():
    assert set(COMMAND_CATALOGUE) == {"plan_review", "plan_save", "apply_reviewed_plan", "plan_refresh_only",
                                      "apply_refresh_only", "state_rm"}
    for template, read_only, mutates in COMMAND_CATALOGUE.values():
        assert "-auto-approve" not in template and "destroy" not in template
        assert read_only == (mutates == "none")


def test_command_values_are_shell_quoted():
    command = render_command("state_rm", "dir with space", "azurerm_x.y[\"k'1\"]")["command"]
    assert shlex.split(command)[-1] == "azurerm_x.y[\"k'1\"]"
    assert shlex.split(command)[1] == "-chdir=dir with space"
    missing = render_command("plan_review", None)
    assert missing["placeholders"] == ["var_file", "working_dir"] and "<working_dir>" in missing["command"]


def test_options_unchanged_by_ai_output():
    drift_report = report("report_plans", "injected_instructions")
    baseline = deterministic_state(drift_report)["remediation_plan"]
    state = deterministic_state(copy.deepcopy(drift_report))
    assert state["remediation_plan"] == baseline
    assert all(c["template_id"] in COMMAND_CATALOGUE for o in baseline["options"] for c in o["commands"])
    text = json.dumps([c["command"] for o in baseline["options"] for c in o["commands"]])
    assert "destroy" not in text and "everything" not in text  # injected instructions never become commands


# --------------------------------------------------------------------------- HCL fragments


@pytest.mark.parametrize(("value", "hcl"), [
    ("GRS", '"GRS"'), (30, "30"), (1.5, "1.5"), (True, "true"), (False, "false"), (None, "null"),
    (["a", 1, None], '["a", 1, null]'), ({"team": "x", "cost-center": "42", "a b": True},
                                         '{ "a b" = true, cost-center = "42", team = "x" }'),
    ({}, "{}"), ([], "[]"), ({"n": {"m": [1]}}, "{ n = { m = [1] } }"),
])
def test_hcl_value_types(value, hcl):
    assert hcl_value(value) == hcl


@pytest.mark.parametrize(("text", "hcl"), [
    ('${file("/etc/passwd")}', '"$${file(\\"/etc/passwd\\")}"'),
    ("%{ if x }y%{ endif }", '"%%{ if x }y%%{ endif }"'),
    ("line\nbreak\ttab\r", '"line\\nbreak\\ttab\\r"'),
    ("back\\slash", '"back\\\\slash"'),
    ("\x00\x1f\x7f", '"\\u0000\\u001f\\u007f"'),
    ("$ alone and % alone", '"$ alone and % alone"'),
])
def test_hcl_string_escaping(text, hcl):
    assert hcl_string(text) == hcl
    assert "${" not in hcl.replace("$${", "") and "%{" not in hcl.replace("%%{", "")


def test_value_types_fixture_fragments():
    [accept] = [o for o in options("report_plans", "value_types") if o["kind"] == "accept_remote_value"]
    assert {tuple(f["path"]): f["assignment_hcl"] for f in accept["fragments"]} == {
        ("allowed_ips",): 'allowed_ips = ["10.0.0.1", "10.0.0.2"]',
        ("description",): "description = null",
        ("labels",): 'labels = { cost-center = "42", team = "platform" }',
        ("local_auth_enabled",): "local_auth_enabled = false",
        ("retention_days",): "retention_days = 30",
    }
    assert {(f["value_source"], f["location"]) for f in accept["fragments"]} == {("real_view", "not_determined")}


@pytest.mark.parametrize(("group", "name", "path", "reason"), [
    ("security_plans", "web_app_secret_changed", ["site_config"], "redacted"),
    ("plan_evidence", "external_drift", ["tags", "probe"], "value_absent"),
])
def test_no_fragment_for_redacted_or_absent_values(group, name, path, reason):
    [accept] = [o for o in options(group, name) if o["kind"] == "accept_remote_value"]
    assert accept["fragments"] == [] and accept["fragment_gaps"] == [{"path": path, "reason": reason}]
    assert "SYNTHETIC-SECRET" not in json.dumps(options(group, name))


def test_no_fragment_for_unknown_or_object_level_values():
    unknown = {"class": "unknown_until_apply", "redacted": False, "path": ["instances"],
               "real": {"status": "value", "value": 2}, "desired": {"status": "unknown"}}
    assert value_fragment(unknown) == (None, "unknown_until_apply")
    created = {"class": None, "redacted": False, "path": ["name"], "real": {"status": "absent"}}
    assert value_fragment(created) == (None, "object_level")
    big = {"class": "drifted", "redacted": False, "path": ["x"], "real": {"status": "value", "value": "y" * 5000}}
    assert value_fragment(big) == (None, "value_too_large")
    # Object-level resources (create/delete) offer no keep/accept fragments at all.
    for group, name in (("plan_evidence", "resource_added"), ("plan_evidence", "external_deletion")):
        assert all(o["fragments"] == [] for o in options(group, name))


def test_nested_paths_have_no_assignment():
    [accept] = [o for o in options("cost_config_plans", "combined_security_cost_config")
                if o["kind"] == "accept_remote_value" and o["address"].startswith("azurerm_storage")]
    nested = [f for f in accept["fragments"] if len(f["path"]) > 1]
    assert nested and all(f["assignment_hcl"] is None for f in nested)


# --------------------------------------------------------------------------- report: schema, determinism


@requires_ai
def test_report_schema_is_strict_and_constants_hold():
    state = run_analysis(report("plan_evidence", "external_drift"), config=load_config({}))
    built = dict(state["report"])
    AiAnalysisReport.model_validate_json(json.dumps(built))
    for path, bad in ((("resources", 0, "who", "actor_attribution", "status"), "confirmed"),
                      (("resources", 0, "who", "recorded_caller", "identity"), "alice"),
                      (("resources", 0, "remediation", "recommendation", "execution_allowed"), True),
                      (("resources", 0, "remediation", "recommendation", "automatic_apply"), True),
                      (("investigation", "exposure", "caller_identity"), "shown"),
                      (("cost", "monetary_impact"), "$20"), (("remediation", "automatic_apply"), True),
                      (("report_version",), "1"), (("extra",), 1)):
        broken = json.loads(json.dumps(built))
        target = broken
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = bad
        with pytest.raises(Exception):
            AiAnalysisReport.model_validate_json(json.dumps(broken))
    option = json.loads(json.dumps(built))
    option["remediation"]["options"][0]["execution"]["allowed"] = True
    with pytest.raises(Exception):
        AiAnalysisReport.model_validate_json(json.dumps(option))


@requires_ai
def test_write_report_is_deterministic_and_markdown_comes_from_json(tmp_path):
    drift_report = report("cost_config_plans", "combined_security_cost_config")
    a = write_report(run_analysis(copy.deepcopy(drift_report), config=load_config({})), tmp_path / "a")
    b = write_report(run_analysis(copy.deepcopy(drift_report), config=load_config({})), tmp_path / "b")
    for kind in ("json", "markdown"):
        assert a[kind].read_bytes() == b[kind].read_bytes()
        assert a[kind].name in ("ai_analysis_report.json", "ai_analysis_report.md")
    rendered = render_markdown(json.loads(a["json"].read_text(encoding="utf-8")))
    assert rendered == a["markdown"].read_text(encoding="utf-8")  # Markdown derives from the JSON only
    assert sorted(p.name for p in (tmp_path / "a").iterdir()) == ["ai_analysis_report.json", "ai_analysis_report.md"]


@requires_ai
def test_write_report_requires_a_report(tmp_path):
    with pytest.raises(ValueError, match="no report"):
        write_report({}, tmp_path)


@requires_ai
def test_markdown_sections_and_boundaries(tmp_path):
    state = run_analysis(report("plan_evidence", "resource_removed"), config=load_config({}))
    md = write_report(state, tmp_path)["markdown"].read_text(encoding="utf-8")
    headings = ["## Summary", "## What changed", "## Recorded Azure operations", "## When", "## Who",
                "## Correlation", "## Analysis", "## Recommendation & options", "## Limitations", "## Provenance"]
    assert [line for line in md.splitlines() if line.startswith("## ")] == headings  # locked order (Task 9B.4)
    for heading in ("### Security Impact", "### Cost Impact", "### Configuration", "### Root Cause (hypotheses)",
                    "### Risk", "### Investigation Interpretation", "### Approval Required"):
        assert heading in md
    assert "not determinable from evidence" in md
    assert "Destructive: **yes**" in md and "destructive confirmation required" in md
    assert "Execution allowed: **no**. Automatic apply: **no**." in md
    # resource_removed: the plan deletes one object, so policy v1 (R2) recommends nothing for it; the added object
    # follows the plan (R4)
    assert "Decision: **human\\_decision\\_required** (rule R2" in md
    assert "Decision: **recommended** (rule R4" in md and md.count("recommended by policy v1") == 1


@requires_ai
@pytest.mark.parametrize("name", ["markdown_html_injection", "interpolation_injection", "injected_instructions"])
def test_hostile_values_are_inert_in_markdown(name, tmp_path):
    md = write_report(run_analysis(report("report_plans", name), config=load_config({})), tmp_path)["markdown"] \
        .read_text(encoding="utf-8")
    prose, blocks = split_markdown(md)
    # Outside fenced/inline code there is no raw HTML, link syntax, heading injection or autolink.
    assert "<script" not in prose and "<img" not in prose
    assert "](" not in prose and "javascript:" not in prose
    assert not re.search(r"https?://", prose) and "www.evil" not in prose
    assert not re.search(r"(?m)^# Injected", md)
    # A fenced block can only close on its own fence line: no line inside starts with that fence.
    for fence, body in blocks:
        assert not any(line.startswith(fence) for line in body)
    if name == "interpolation_injection":
        assert "$${file(" in md and "%%{ if true }" in md


def split_markdown(md: str) -> tuple[str, list[tuple[str, list[str]]]]:
    """CommonMark-style split: fenced blocks only open at line start; inline code spans removed from prose."""
    prose, blocks, fence, body = [], [], None, []
    for line in md.split("\n"):
        if fence is not None:
            if line == fence:
                blocks.append((fence, body))
                fence, body = None, []
            else:
                body.append(line)
            continue
        opener = re.match(r"^(`{3,})", line)
        if opener:
            fence = opener.group(1)
            continue
        out, i = [], 0
        while i < len(line):
            run = re.match(r"`+", line[i:])
            if run:
                close = line.find(run.group(0), i + len(run.group(0)))
                while close != -1 and line[close + len(run.group(0)):close + len(run.group(0)) + 1] == "`":
                    close = line.find(run.group(0), close + 1)
                if close != -1:
                    i = close + len(run.group(0))
                    continue
            out.append(line[i])
            i += 1
        prose.append("".join(out))
    assert fence is None, "unclosed fenced block"
    return "\n".join(prose), blocks


def test_md_helpers_neutralize_untrusted_text():
    hostile = "](https://x.example) <b>& *bold* `code` # h | pipe www.example.com a@b.co\nnext"
    text = md_text(hostile)
    assert "<b>" not in text and "&lt;b&gt;" in text and "\n" not in text
    assert "](" not in text and "https://" not in text and "www.example" not in text and "a@b" not in text
    code = md_code("a ``` b `` c")
    assert code.startswith("````") and code.endswith("````")


# --------------------------------------------------------------------------- AI statuses in the report


def _cause(address, path):
    return {"address": address, "cited_paths": [path], "hypothesis": "out_of_band_change",
            "possible_channels": ["unknown"],
            "explanation": "Azure differs from the recorded state.", "basis": "inference"}


@requires_ai
@pytest.mark.parametrize(("llm", "statuses"), [
    (None, {"skipped"}),
    ("failed", {"failed", "skipped"}),
    ("invalid", {"invalid_output", "skipped"}),
    ("ok", {"ok", "skipped"}),
])
def test_report_renders_every_ai_status(llm, statuses, tmp_path):
    drift_report = report("plan_evidence", "external_drift")
    fake = {None: None, "failed": ScriptedLLM(error=TimeoutError("down")), "invalid": ScriptedLLM("not json"),
            "ok": ScriptedLLM(envelope(root_cause_analysis={"findings": [_cause(RG, ["tags", "probe"]),
                                                                          _cause("x.y", ["nope"])],
                                                             "summary": "Changed outside Terraform."}))}[llm]
    state = run_analysis(drift_report, llm=fake) if fake else run_analysis(drift_report, config=load_config({}))
    built = state["report"]
    assert {s["status"] for s in built["analysis"].values()} == statuses
    md = write_report(state, tmp_path)["markdown"].read_text(encoding="utf-8")
    for status in statuses:
        assert f"Status: **{md_text(status)}**" in md
    if llm == "ok":
        root = built["analysis"]["root_cause"]
        assert len(root["findings"]) == 1 and root["rejected_count"] == 1
        assert root["rejection_reasons"] == {"unsupported_citation": 1}
        assert "x.y" not in md  # rejected findings are counted, never shown
        assert "AI inference: Azure differs from the recorded state" in md


@requires_ai
@pytest.mark.parametrize("llm_kind", ["ok", "failed", "invalid"])
def test_deterministic_report_parts_identical_with_and_without_llm(llm_kind):
    drift_report = report("cost_config_plans", "combined_security_cost_config")
    without = run_analysis(copy.deepcopy(drift_report), config=load_config({}))["report"]
    llm = {"ok": ScriptedLLM(envelope()), "failed": ScriptedLLM(error=TimeoutError("x")),
           "invalid": ScriptedLLM("nope")}[llm_kind]
    with_llm = run_analysis(copy.deepcopy(drift_report), llm=llm)["report"]
    for key in ("report_version", "provenance", "summary", "investigation", "resources", "remediation", "cost"):
        assert with_llm[key] == without[key]


# --------------------------------------------------------------------------- one call, frozen state


@requires_ai
def test_whole_graph_still_one_call_one_http_request(tmp_path):
    config = load_config({"AI_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "sk-test-not-real", "AI_LLM_MODEL": "m",
                          "OPENAI_BASE_URL": "https://llm.example.invalid/v1"})
    requests: list = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "c", "object": "chat.completion", "created": 0, "model": "m",
                                         "choices": [{"index": 0, "finish_reason": "stop",
                                                      "message": {"role": "assistant", "content": envelope()}}]})

    model, _ = create_chat_model(config, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    state = run_analysis(report("report_plans", "multi_resource"), config=config, llm=model)
    write_report(state, tmp_path)
    assert len(requests) == 1 and state["llm_call"]["attempted"] is True
    assert state["report"]["llm"]["max_retries"] == 0
    sent = json.loads(requests[0].content)["messages"][1]["content"]
    assert "remediation" not in sent and "plan_default" not in sent  # remediation never enters the prompt


@requires_ai
@pytest.mark.parametrize("field", ["remediation_plan", "report"])
@pytest.mark.parametrize("mode", ["replace", "mutate"])
def test_remediation_plan_and_report_are_write_once(field, mode):
    def later(state):
        if mode == "mutate":
            target = state[field]["options"] if field == "remediation_plan" else state[field]["limitations"]
            target.pop()
            return {}
        return {field: {"options": []}}

    from ai_engine.nodes.analyze_drift import make_analyze_drift
    from ai_engine.nodes.investigation_facts import derive_investigation
    from ai_engine.nodes.report_generator import generate_report

    graph = StateGraph(AiState)
    steps = [("parse_drift", parse_drift), ("classify_drift", classify_drift), ("route_cost_config",
             route_cost_config), ("derive_origin_risk", derive_origin_risk),
             ("derive_investigation", derive_investigation), ("plan_remediation", plan_remediation),
             ("analyze_drift", make_analyze_drift(None)), ("generate_report", generate_report), ("later", later)]
    for name, node in steps:
        graph.add_node(name, node)
    graph.add_edge(START, steps[0][0])
    for (a, _), (b, _) in zip(steps, steps[1:]):
        graph.add_edge(a, b)
    graph.add_edge(steps[-1][0], END)
    with pytest.raises(EvidenceMutationError):
        graph.compile().invoke({"drift_report": report("plan_evidence", "external_drift"),
                                "llm": {"available": False, "provider": "none", "model": None, "reason": "off"}})


@requires_ai
def test_report_state_is_frozen():
    state = run_analysis(report("plan_evidence", "external_drift"), config=load_config({}))
    assert isinstance(state["report"], FrozenDict) and isinstance(state["remediation_plan"], FrozenDict)


# --------------------------------------------------------------------------- gaps found by the mutation check


def test_remediation_schema_forbids_ranking():
    plan = deterministic_state(report("plan_evidence", "external_drift"))["remediation_plan"]
    for bad in ({"ranking": "by_severity"}, {"approval_required": False}, {"automatic_apply": True}):
        with pytest.raises(Exception):
            RemediationPlan.model_validate_json(json.dumps({**plan, **bad}))


@requires_ai
def test_www_autolinks_are_broken_not_just_escaped():
    text = md_text("see www.evil.example and WWW.Evil.example")
    assert "www\\." not in text and "WWW\\." not in text  # the escaped dot alone could still autolink
    assert "www​" in text and "WWW​" in text


@requires_ai
def test_fenced_blocks_outgrow_backtick_runs():
    from ai_engine.nodes.report_generator import md_fenced

    block = md_fenced("```\n# not a heading\n`````", "hcl")
    assert block[0] == "``````hcl" and block[-1] == "``````"
    assert md_fenced("plain")[0] == "```"


@requires_ai
def test_table_rows_survive_pipes_in_values(tmp_path):
    drift = report("report_plans", "markdown_html_injection")
    # the fixture's note holds an email, which the public report withholds (Task 9B.4A): plant pipes without one
    for resource in drift["resources"]:
        for change in resource["attribute_changes"]:
            if change["path"][0] == "tags" and change["real"]["status"] in ("value", "withheld"):
                change["real"] = {"status": "value", "value": "a | b || c"}
    md = write_report(run_analysis(drift, config=load_config({})), tmp_path)["markdown"].read_text(encoding="utf-8")
    assert "a \\| b \\|\\| c" in md
    rows = [line for line in md.splitlines() if line.startswith("| ") and "tags" in line]
    assert rows
    for row in rows:
        unescaped = len(re.findall(r"(?<!\\)\|", row))
        assert unescaped == 9  # 8 columns: every pipe inside a value is escaped


@requires_ai
def test_remediation_identical_when_ai_returns_findings():
    drift_report = report("plan_evidence", "external_drift")
    baseline = run_analysis(copy.deepcopy(drift_report), config=load_config({}))["report"]
    reply = envelope(root_cause_analysis={"findings": [_cause(RG, ["tags", "probe"])], "summary": "x"},
                     risk_assessment={"findings": [{"address": RG, "cited_paths": [["tags", "probe"]],
                                                    "risk_kind": "apply_reverts_external_change",
                                                    "explanation": "Applying the plan would revert the tag.",
                                                    "basis": "inference"}], "summary": "y"})
    with_findings = run_analysis(copy.deepcopy(drift_report), llm=ScriptedLLM(reply))["report"]
    assert with_findings["analysis"]["root_cause"]["findings"] and with_findings["analysis"]["risk"]["findings"]
    assert with_findings["remediation"] == baseline["remediation"]  # AI output cannot alter options
