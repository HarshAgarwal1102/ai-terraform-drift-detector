"""Deterministic report generation (Tasks 6.6, 9B.4: report v2). No LLM call.

`generate_report` (a LangGraph node after `analyze_drift`) builds the strict
`AiAnalysisReport` JSON (report version 2) from validated state only: the drift
report, the deterministic routing/origin/remediation fields, the deterministic
investigation facts (`investigation_facts`: WHAT / WHEN / WHO / correlation with
their fixed statements), the recommendation of policy v1, and the six AI
sections as already validated (rejected findings are counted, never shown).
The result is the write-once `AiState.report`.

Evidence and inference stay apart: `what` is Terraform evidence, `operations`
are Activity Log evidence (from the public investigation; the caller identity is
always `withheld`), `when` / `who` / `correlation` / `analysis.narrative` are
deterministic, and only the `analysis` sections are AI inference. Without an LLM
the report is still complete (G15). Every fact the evidence cannot prove renders
as "not confirmed by available evidence".

`render_markdown` renders Markdown **from that JSON only**, so the two cannot
disagree. `write_report(state, out_dir)` writes `ai_analysis_report.json` and
`ai_analysis_report.md`; it is a library function, not a CLI.

Untrusted text (Terraform/Azure values, AI explanations) is never trusted as
Markdown: running text is escaped (Markdown punctuation, `<`, `>`, `&`) and
links are neutralized (a zero-width space after `:`, `@` and in `www.`), and
values, HCL fragments and commands go into code spans / fenced blocks whose
fence is longer than any backtick run in the content. The output is
deterministic: the same state gives byte-identical files.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, JsonValue, model_validator

from ai_engine.nodes.common import CitedPath, Strict
from ai_engine.nodes.cost_analysis import ConfigTopic
from ai_engine.nodes.investigation_facts import (
    NOT_CONFIRMED,
    REPORT_REASONS,
    STATEMENTS_VERSION,
    Consistency,
    recommendation_statements,
    what_statements,
)
from ai_engine.nodes.remediation import CATALOGUE_VERSION, POLICY_VERSION, Recommendation, RemediationOption
from ai_engine.nodes.root_cause import Channel, Hypothesis, RiskKind
from ai_engine.nodes.security_analysis import Exposure, Impact
from drift_engine import investigation_public as pub
from drift_engine.logs import log_event

logger = logging.getLogger(__name__)

REPORT_VERSION = "2"
JSON_FILE = "ai_analysis_report.json"
MARKDOWN_FILE = "ai_analysis_report.md"
SECTION_KEYS = {"security": "analyze_security", "cost": "analyze_cost", "configuration": "analyze_configuration",
                "root_cause": "analyze_root_cause", "risk": "assess_risk", "investigation": "analyze_investigation"}
Status = Literal["ok", "skipped", "failed", "invalid_output"]

BASE_LIMITATIONS = (
    "Terraform evidence (drift_report.json) is the source of truth for WHAT changed; AI sections are inference.",
    "The Azure Activity Log records operations, not property values: an operation is related to drift only by "
    "inference (property link inferred_not_provable); only a deletion can be property-confirmed.",
    "Caller identities are withheld in public reports; WHO is available locally via drift-engine who.",
    "Client application azure_cli also covers Terraform run locally with Azure CLI authentication.",
    "Completeness-dependent statements cover only the Activity Log events available at the investigation's query "
    "time (queried_at); Microsoft publishes no ingestion SLA.",
    "No pricing data: monetary impact is not determinable from this evidence (Phase 10).",
    "Recommendations follow the deterministic recommendation policy v1; investigation verdicts and caller data never "
    "change them. Nothing has been executed; every option needs human approval (Phase 11).",
    "HCL value fragments do not say where a value is defined (resource block, module input or tfvars).",
)
STATUS_LIMITATIONS = {
    "not_available": "No drift investigation was provided: event time (WHEN), the recorded caller (WHO) and the "
                     "correlation are not confirmed by available evidence.",
    "failed": "The drift investigation failed: every drifted resource is not investigated (investigation_failed).",
    "incomplete": "The drift investigation is incomplete: some drifted resources were not investigated.",
}


# --------------------------------------------------------------------------- schema

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
OpId = Annotated[str, Field(pattern=r"^op-[1-9][0-9]*$")]
AutoRef = Annotated[str, Field(pattern=r"^auto-[1-9][0-9]*$")]
Timestamp = Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$")]
Count = Annotated[int, Field(ge=0)]


class Statement(Strict):
    id: Annotated[str, Field(pattern=r"^[a-z_]+\.[a-z_]+\.v1$")]
    text: Annotated[str, Field(min_length=1)]


class Versions(Strict):
    report: Literal["2"]
    investigation_public: Literal["1"] | None
    capable_operations_table: Literal["1"] | None
    deletion_rules: Literal["2"] | None
    statements: Literal["1"]
    recommendation_policy: Literal["1"]
    remediation_catalogue: Literal["1"]


class Provenance(Strict):
    drift_report_sha256: Sha256
    investigation_sha256: Sha256 | None
    classification_version: str
    run_id: str | None
    environment: str | None
    plan_timestamp: str | None
    versions: Versions


class Failure(Strict):
    source: str
    stage: str | None
    reason: str | None


class Summary(Strict):
    outcome: Literal["succeeded", "failed"]
    has_drift: bool | None
    highest_severity: str | None
    resources_total: int | None
    drifted_resources: int | None
    classification_counts: dict[str, int]
    failure: Failure | None


class InvestigationRun(Strict):
    status: Literal["not_available", "complete", "incomplete", "failed"]
    failure: pub.Failure | None
    observation: pub.Observation | None
    completeness: pub.Completeness | None
    anchors: pub.Anchors | None
    rules: pub.Rules | None
    exposure: pub.Exposure

    @model_validator(mode="after")
    def _consistent(self) -> InvestigationRun:
        if (self.status == "failed") != (self.failure is not None):
            raise ValueError("failure is set exactly when the investigation failed")
        if self.status == "not_available" and (self.completeness or self.anchors or self.rules):
            raise ValueError("no investigation details without an investigation")
        return self


class ChangeEntry(Strict):
    path: Annotated[list[str], Field(min_length=1)]
    attribute_class: str | None
    assessment: str
    severity: str
    severity_rules: list[str]
    origin: str | None
    redacted: bool
    state: dict[str, JsonValue]
    real: dict[str, JsonValue]
    desired: dict[str, JsonValue]


class What(Strict):
    basis: Literal["terraform_evidence"]
    classification: str
    action: str | None
    severity: str
    severity_reasons: list[str]
    risk_factors: list[str]
    moved: bool
    importing: bool
    changes: list[ChangeEntry]
    statements: list[Statement]


class ReportOperation(pub.Operation):
    caller_identity: Literal["withheld"]
    basis: Literal["activity_log_evidence"]


class ReportAutomatedEvent(pub.AutomatedEvent):
    basis: Literal["activity_log_evidence"]


class WindowRef(Strict):
    kind: Literal["anchor", "lookback"]
    start: Timestamp


class When(Strict):
    status: Literal["decisive_operation", "not_confirmed", "not_applicable"]
    decisive_operation: OpId | None
    event_start: Timestamp | None
    event_end: Timestamp | None
    available_at: Timestamp | None
    last_in_sync: pub.AnchorRef | None
    window: WindowRef | None
    observation: pub.Observation | None
    plan_timestamp: str | None
    gap_seconds: float | None
    statements: list[Statement]

    @model_validator(mode="after")
    def _consistent(self) -> When:
        decisive = self.status == "decisive_operation"
        if decisive != (self.decisive_operation is not None) or (self.gap_seconds is not None and not decisive):
            raise ValueError("event time and gap exist exactly with a decisive operation")
        return self


class RecordedCaller(Strict):
    status: Literal["recorded", "not_recorded", "multiple_operations", "no_decisive_operation", "not_investigated",
                    "not_applicable"]
    reason: Literal["caller_missing", "caller_inconsistent"] | None
    operation: OpId | None
    candidate_operations: Count
    caller_type: Literal[pub.CALLER_TYPES] | None
    client_app: Literal[pub.CLIENT_APPS] | None
    pipeline_identity: bool | None
    identity: Literal["withheld"]

    @model_validator(mode="after")
    def _consistent(self) -> RecordedCaller:
        recorded = self.status == "recorded"
        if (self.reason is not None) != (self.status == "not_recorded"):
            raise ValueError("a reason exists exactly for not_recorded")
        if (self.operation is not None) != (self.status in ("recorded", "not_recorded")):
            raise ValueError("an operation is named exactly for recorded / not_recorded")
        if not recorded and (self.caller_type or self.client_app or self.pipeline_identity is not None):
            raise ValueError("caller data only for a recorded caller")
        if recorded and (self.caller_type is None or self.client_app is None):
            raise ValueError("a recorded caller has a caller type and client application")
        if self.status == "multiple_operations" and self.candidate_operations < 2:
            raise ValueError("multiple_operations needs two or more candidate operations")
        return self


class ActorAttribution(Strict):
    status: Literal["confirmed", "not_confirmed_by_available_evidence", "not_applicable"]
    rule: Literal["external_deletion_v1"] | None
    claim: Literal["recorded_successful_delete"] | None

    @model_validator(mode="after")
    def _consistent(self) -> ActorAttribution:
        if (self.status == "confirmed") != (self.rule is not None and self.claim is not None):
            raise ValueError("a rule and claim exist exactly for a confirmed attribution")
        return self


class Who(Strict):
    recorded_caller: RecordedCaller
    actor_attribution: ActorAttribution
    statements: list[Statement]


class Counts(Strict):
    operations: Count
    capable: Count
    unclassified: Count
    irrelevant: Count
    candidates: Count
    after_observation: Count
    child: Count
    automated_signals: Count


class Correlation(Strict):
    status: Literal["investigated", "not_investigated", "not_applicable"]
    verdict: Literal[pub.VERDICTS] | None
    reason: Literal[pub.AMBIGUOUS_REASONS + pub.PRECONDITION_REASONS + REPORT_REASONS] | None
    property_link: Literal["confirmed", "inferred_not_provable", "none"] | None
    property_link_reason: Literal[pub.PROPERTY_LINK_REASONS] | None
    relevant_areas: list[Literal[pub.AREAS]]
    deletion_rule: pub.DeletionRule | None
    unreadable_events_in_scope: bool
    counts: Counts
    descendant_operations: dict[str, Annotated[int, Field(ge=1)]]
    statements: list[Statement]

    @model_validator(mode="after")
    def _consistent(self) -> Correlation:
        if (self.status == "not_applicable") != (self.verdict is None):
            raise ValueError("a verdict exists exactly for drifted resources")
        if (self.status == "not_investigated") != (self.verdict == "not_investigated"):
            raise ValueError("status not_investigated matches the verdict")
        return self


class ResourceAnalysis(Strict):
    basis: Literal["deterministic"]
    narrative: list[Statement]


class ResourceRecommendation(Recommendation):
    statements: list[Statement]


class ResourceRemediation(Strict):
    option_ids: list[str]
    recommendation: ResourceRecommendation


class ResourceEntry(Strict):
    address: str
    type: str
    investigation_scope: Literal["drift", "not_drift"]
    what: What
    operations: list[ReportOperation]
    automated_events: list[ReportAutomatedEvent]
    when: When
    who: Who
    correlation: Correlation
    analysis: ResourceAnalysis
    remediation: ResourceRemediation

    @model_validator(mode="after")
    def _consistent(self) -> ResourceEntry:
        not_drift = self.investigation_scope == "not_drift"
        flags = (self.when.status == "not_applicable", self.who.recorded_caller.status == "not_applicable",
                 self.who.actor_attribution.status == "not_applicable", self.correlation.status == "not_applicable")
        if any(flag != not_drift for flag in flags) or (not_drift and (self.operations or self.automated_events)):
            raise ValueError("not_drift resources are not_applicable everywhere, drifted resources nowhere")
        return self


# Validated findings as they appear in the report (Task 6.7). Strict and extra="forbid": a finding carries exactly
# the model's inference fields plus the deterministic fields the code attached, so no AI output can add a field
# that claims deterministic authority (classification, severity rating, actor, remediation, price, ...).
Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
Origin = Literal["outside_terraform", "outside_terraform_converged", "configuration_side", "both_sides",
                 "value_unknown_until_apply", "undetermined"]
Factor = Literal["apply_reverts_external_change", "apply_destroys_or_recreates", "ambiguous_intent",
                 "unmanaged_setting", "value_unknown_until_apply", "redacted_unreadable", "moved_or_importing"]
Address = Annotated[str, Field(min_length=1, max_length=512)]
Explanation = Annotated[str, Field(min_length=1, max_length=1500)]


class SecurityReportFinding(Strict):
    address: Address
    cited_paths: Annotated[list[CitedPath], Field(min_length=1)]
    exposure: Exposure
    deterministic_severity: Severity
    ai_assessed_impact: Impact
    ai_impact_below_deterministic: bool
    explanation: Explanation
    basis: Literal["inference"]


class CostReportFinding(Strict):
    address: Address
    cited_paths: Annotated[list[CitedPath], Field(min_length=1)]
    cost_driver: Literal["sku_or_tier", "capacity_or_count", "resource_lifecycle", "other"]
    direction: Literal["likely_increase", "likely_decrease", "likely_neutral", "undetermined"]
    monetary_impact: Literal["not_determinable_from_evidence"]
    pricing_source: None
    deterministic_severity: Severity
    classification: str
    action: str | None
    explanation: Explanation
    basis: Literal["inference"]


class ConfigurationFact(Strict):
    path: Annotated[list[str], Field(min_length=1)]
    class_: str | None = Field(alias="class")
    assessment: str

    model_config = Strict.model_config | {"validate_by_name": True, "validate_by_alias": True,
                                          "serialize_by_alias": True}


class ConfigurationReportFinding(Strict):
    address: Address
    cited_paths: Annotated[list[CitedPath], Field(min_length=1)]
    topic: ConfigTopic
    evidence_facts: list[ConfigurationFact]
    topic_conflicts_with_evidence: bool
    deterministic_severity: Severity
    explanation: Explanation
    basis: Literal["inference"]


class OriginFact(Strict):
    path: Annotated[list[str], Field(min_length=1)]
    origin: Origin
    lifecycle: bool
    risk_factors: list[Factor]


class RootCauseReportFinding(Strict):
    address: Address
    cited_paths: Annotated[list[CitedPath], Field(min_length=1)]
    hypothesis: Hypothesis
    possible_channels: Annotated[list[Channel], Field(min_length=1)]
    origin_facts: list[OriginFact]
    deterministic_severity: Severity
    explanation: Explanation
    basis: Literal["inference"]


class RiskReportFinding(Strict):
    address: Address
    cited_paths: Annotated[list[CitedPath], Field(min_length=1)]
    risk_kind: RiskKind
    risk_kind_unverified: bool
    risk_factors: list[Factor]
    deterministic_severity: Severity
    explanation: Explanation
    basis: Literal["inference"]


class InvestigationReportFinding(Strict):
    address: Annotated[str, Field(min_length=1, max_length=1024)]
    cited_operations: list[OpId]
    consistency: Consistency
    verdict: Literal[pub.VERDICTS]
    property_link: Literal["confirmed", "inferred_not_provable", "none"]
    actor_attribution: Literal["confirmed", "not_confirmed_by_available_evidence"]
    explanation: Explanation
    basis: Literal["inference"]


class _SectionBase(Strict):
    status: Status
    reason: str | None
    rejected_count: Annotated[int, Field(ge=0)]
    rejection_reasons: dict[str, int]
    summary: str | None
    basis: Literal["inference"]


class SecuritySection(_SectionBase):
    findings: list[SecurityReportFinding]


class CostReportSection(_SectionBase):
    findings: list[CostReportFinding]


class ConfigurationReportSection(_SectionBase):
    findings: list[ConfigurationReportFinding]


class RootCauseReportSection(_SectionBase):
    findings: list[RootCauseReportFinding]


class RiskReportSection(_SectionBase):
    findings: list[RiskReportFinding]


class InvestigationReportSection(_SectionBase):
    findings: list[InvestigationReportFinding]


class Analysis(Strict):
    security: SecuritySection
    cost: CostReportSection
    configuration: ConfigurationReportSection
    root_cause: RootCauseReportSection
    risk: RiskReportSection
    investigation: InvestigationReportSection


class EvidenceKey(Strict):
    address: Address
    path: Annotated[list[str], Field(min_length=1)]
    sections: Annotated[list[Literal["security", "cost", "configuration", "root_cause", "risk"]],
                        Field(min_length=1)]


class InvestigationKey(Strict):
    address: Annotated[str, Field(min_length=1, max_length=1024)]
    operations: list[OpId]
    automated_events: list[AutoRef]


class LlmInfo(Strict):
    attempted: bool
    status: str
    reason: str | None
    provider: str | None
    model: str | None
    max_retries: int | None
    evidence_sent: list[EvidenceKey]  # exactly what the model was given (keys and sections, never values)
    investigation_sent: list[InvestigationKey]  # the investigated resources and references sent (Task 9B.4)


class ReportRemediation(Strict):
    catalogue_version: Literal["1"]
    recommendation_policy_version: Literal["1"]
    options: list[RemediationOption]
    approval_required: Literal[True]
    automatic_apply: Literal[False]
    reason: str | None


class CostBoundary(Strict):
    monetary_impact: Literal["not_determinable_from_evidence"]
    pricing_source: None


class AiAnalysisReport(Strict):
    report_version: Literal["2"]
    provenance: Provenance
    summary: Summary
    investigation: InvestigationRun
    resources: list[ResourceEntry]
    analysis: Analysis
    remediation: ReportRemediation
    cost: CostBoundary
    llm: LlmInfo
    limitations: list[str]


# --------------------------------------------------------------------------- build (deterministic)


def drift_report_sha256(drift_report: Mapping[str, Any]) -> str:
    canonical = json.dumps(drift_report, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _section(result: Mapping[str, Any]) -> dict[str, Any]:
    reasons: dict[str, int] = {}
    for rejected in result["rejected_findings"]:
        reasons[rejected["reason"]] = reasons.get(rejected["reason"], 0) + 1
    return {"status": result["status"], "reason": result["reason"], "findings": list(result["findings"]),
            "rejected_count": len(result["rejected_findings"]), "rejection_reasons": dict(sorted(reasons.items())),
            "summary": result["summary"], "basis": "inference"}


def _strip(value: Any) -> Any:
    """Plain JSON copy of frozen state."""
    return json.loads(json.dumps(value))


def build_report(state: Mapping[str, Any]) -> dict[str, Any]:
    drift_report = state["drift_report"]
    parsed = state["parsed_drift"]
    facts = state["origin_facts"]
    investigation = _strip(state["investigation_facts"])
    plan_state = state["remediation_plan"]
    call = state["llm_call"]
    run = drift_report.get("run") or {}
    plan = drift_report.get("plan") or {}
    summary = drift_report.get("summary") or {}
    origins = {(c["address"], tuple(c["path"])): c["origin"] for c in facts["changes"]}
    resource_facts = {r["address"]: r for r in facts["resources"]}
    investigated = {r["address"]: r for r in investigation["resources"]}
    recommendations = {r["address"]: _strip(r) for r in plan_state["recommendations"]}

    resources = []
    for resource in parsed["resources"]:
        address = resource["address"]
        rf = resource_facts.get(address, {})
        inv = investigated[address]
        what = {
            "basis": "terraform_evidence", "classification": resource["classification"], "action": resource["action"],
            "severity": resource["severity"]["level"], "severity_reasons": list(resource["severity"]["reasons"]),
            "risk_factors": list(rf.get("risk_factors", [])), "moved": bool(rf.get("moved", False)),
            "importing": bool(rf.get("importing", False)),
            "changes": [{
                "path": list(c["path"]), "attribute_class": c["class"], "assessment": c["assessment"]["category"],
                "severity": c["severity"]["level"], "severity_rules": list(c["severity"]["rules"]),
                "origin": origins.get((address, tuple(c["path"]))), "redacted": c["redacted"],
                "state": dict(c["state"]), "real": dict(c["real"]), "desired": dict(c["desired"]),
            } for c in resource["attribute_changes"]],
            "statements": what_statements(resource),
        }
        recommendation = recommendations[address] | {"statements": []}
        recommendation["statements"] = recommendation_statements(recommendation)
        narrative = (what["statements"] + inv["when"]["statements"] + inv["who"]["statements"]
                     + inv["correlation"]["statements"] + recommendation["statements"])
        resources.append({
            "address": address, "type": resource["type"], "investigation_scope": inv["investigation_scope"],
            "what": what, "operations": inv["operations"], "automated_events": inv["automated_events"],
            "when": inv["when"], "who": inv["who"], "correlation": inv["correlation"],
            "analysis": {"basis": "deterministic", "narrative": narrative},
            "remediation": {"option_ids": [o["option_id"] for o in plan_state["options"] if o["address"] == address],
                            "recommendation": recommendation},
        })

    limitations = list(BASE_LIMITATIONS)
    if investigation["status"] in STATUS_LIMITATIONS:
        limitations.append(STATUS_LIMITATIONS[investigation["status"]])
    if not call["attempted"]:
        limitations.append(f"AI analysis was not performed: {call['reason']}.")
    if call.get("truncation") and call["truncation"]["truncated"]:
        limitations.append("The AI saw truncated evidence: some changes or values were omitted from its prompt.")
    versions = investigation["versions"]
    inv_run = investigation["run"]
    report = {
        "report_version": REPORT_VERSION,
        "provenance": {"drift_report_sha256": drift_report_sha256(drift_report),
                       "investigation_sha256": investigation["sha256"],
                       "classification_version": drift_report["classification_version"],
                       "run_id": run.get("run_id"), "environment": run.get("environment"),
                       "plan_timestamp": plan.get("timestamp"),
                       "versions": {"report": REPORT_VERSION,
                                    "investigation_public": versions["investigation_public"],
                                    "capable_operations_table": versions["capable_operations_table"],
                                    "deletion_rules": versions["deletion_rules"], "statements": STATEMENTS_VERSION,
                                    "recommendation_policy": POLICY_VERSION,
                                    "remediation_catalogue": CATALOGUE_VERSION}},
        "summary": {"outcome": drift_report["outcome"], "has_drift": drift_report["has_drift"],
                    "highest_severity": summary.get("highest_severity"),
                    "resources_total": summary.get("resources_total"),
                    "drifted_resources": summary.get("drifted_resources"),
                    "classification_counts": dict(summary.get("classification_counts") or {}),
                    "failure": drift_report.get("failure")},
        "investigation": {"status": investigation["status"], "failure": inv_run["failure"],
                          "observation": inv_run["observation"], "completeness": inv_run["completeness"],
                          "anchors": inv_run["anchors"], "rules": inv_run["rules"],
                          "exposure": investigation["exposure"]},
        "resources": resources,
        "analysis": {section: _section(state["inferences"][key]) for section, key in SECTION_KEYS.items()},
        "remediation": {key: plan_state[key] for key in ("catalogue_version", "recommendation_policy_version",
                                                           "options", "approval_required", "automatic_apply",
                                                           "reason")},
        "cost": {"monetary_impact": "not_determinable_from_evidence", "pricing_source": None},
        "llm": {key: call.get(key) for key in ("attempted", "status", "reason", "provider", "model", "max_retries")}
        | {"evidence_sent": list(call.get("evidence_sent") or []),
           "investigation_sent": list(call.get("investigation_sent") or [])},
        "limitations": limitations,
    }
    return AiAnalysisReport.model_validate_json(json.dumps(report)).model_dump(mode="json")


def generate_report(state: Mapping[str, Any]) -> dict[str, Any]:
    """LangGraph node: the deterministic report (JSON form) from validated state."""
    report = build_report(state)
    log_event(logger, logging.INFO, "report_generated", "AI analysis report generated",
              resources=len(report["resources"]), options=len(report["remediation"]["options"]),
              investigation=report["investigation"]["status"], llm_status=report["llm"]["status"])
    return {"report": report}


# --------------------------------------------------------------------------- Markdown (from JSON only)


_MD_PUNCT = set("\\`*_{}[]()#+-.!|~")
_ZWSP = "​"


def md_text(value: Any) -> str:
    """Untrusted text as inert inline Markdown: escaped, single line, links neutralized."""
    text = " ".join(str(value).split())
    out = []
    for ch in text:
        if ch in _MD_PUNCT:
            out.append("\\" + ch)
        elif ch == "&":
            out.append("&amp;")
        elif ch == "<":
            out.append("&lt;")
        elif ch == ">":
            out.append("&gt;")
        elif ch in ":@":
            out.append(ch + _ZWSP)  # breaks scheme://, mailto: and email autolinks
        else:
            out.append(ch)
    return re.sub(r"(?i)www", lambda m: m.group(0) + _ZWSP, "".join(out))


def _longest_backticks(text: str) -> int:
    return max((len(run) for run in re.findall(r"`+", text)), default=0)


def md_code(value: Any) -> str:
    """Untrusted text as a single-line code span (never interpreted)."""
    text = " ".join(str(value).split()) or " "
    fence = "`" * (_longest_backticks(text) + 1)
    return f"{fence} {text} {fence}"


def md_fenced(text: str, lang: str = "") -> list[str]:
    fence = "`" * max(3, _longest_backticks(text) + 1)
    return [f"{fence}{lang}", *text.splitlines(), fence]


def _path(path: list[str]) -> str:
    return md_code(".".join(path))


def _view(view: Mapping[str, Any]) -> str:
    if view["status"] == "value":
        return md_code(json.dumps(view["value"], sort_keys=True, ensure_ascii=False))
    if view["status"] == "withheld":  # Task 9B.4A: an identifier withheld from the public drift report
        named = (f"; resource {md_code(view['resource'])}" if view.get("resource")
                 else f"; ref {md_code(view['ref'])}" if view.get("ref") else "")
        return md_text(f"(withheld: {', '.join(view.get('kinds', []))}") + named + md_text(")")
    return md_text(f"({view['status']})")




def _fact(value: Any) -> str:
    """A deterministic fact as inert text; a missing one is never left blank."""
    if value is None:
        return md_text(NOT_CONFIRMED)
    if isinstance(value, bool):
        return "yes" if value else "no"
    return md_text(value)


def _statements(statements: list[Mapping[str, Any]]) -> list[str]:
    return [f"- {md_text(s['text'])}" for s in statements]


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |" for row in rows]
    return lines


SECTION_TITLES = {
    "security": "Security Impact", "cost": "Cost Impact", "configuration": "Configuration",
    "root_cause": "Root Cause (hypotheses)", "risk": "Risk", "investigation": "Investigation Interpretation",
}
_FINDING_SKIP = {"address", "cited_paths", "explanation", "basis"}


def _finding_lines(finding: Mapping[str, Any]) -> list[str]:
    cited = ", ".join(_path(p) for p in finding.get("cited_paths", []))
    lines = [f"- {md_code(finding['address'])}" + (f": {cited}" if cited else "")]
    for key in sorted(k for k in finding if k not in _FINDING_SKIP):
        value = finding[key]
        shown = md_text(value) if isinstance(value, (str, bool, int, float)) or value is None else \
            md_code(json.dumps(value, sort_keys=True, ensure_ascii=False))
        lines.append(f"  - {md_text(key)}: {shown}")
    lines.append(f"  > AI inference: {md_text(finding['explanation'])}")
    return lines


def _section_lines(name: str, section: Mapping[str, Any]) -> list[str]:
    lines = [f"### {SECTION_TITLES[name]}", "",
             f"Status: **{md_text(section['status'])}**" + (f" ({md_text(section['reason'])})"
                                                           if section["reason"] else "")]
    if name == "cost":
        lines += ["", "Monetary impact: **not determinable from evidence** (no pricing data)."]
    if name == "root_cause":
        lines += ["", "Hypotheses about the kind of origin only. Attribution comes only from the deterministic "
                      "investigation (see Who)."]
    if name == "risk":
        lines += ["", "No AI risk level: the deterministic severity is the only rating."]
    if name == "investigation":
        lines += ["", "Inference only: the verdict, property link and attribution shown with each finding are the "
                      "deterministic ones and cannot be changed by the AI."]
    if section["summary"]:
        lines += ["", f"> AI inference: {md_text(section['summary'])}"]
    if section["findings"]:
        lines += [""] + [line for f in section["findings"] for line in _finding_lines(f)]
    if section["rejected_count"]:
        reasons = ", ".join(f"{md_text(k)} ×{v}" for k, v in section["rejection_reasons"].items())
        lines += ["", f"Rejected AI findings (not shown): {section['rejected_count']} ({reasons})"]
    return lines + [""]


def _option_lines(n: int, option: Mapping[str, Any], recommended: bool) -> list[str]:
    role = "matches the current Terraform plan" if option["plan_default"] else "alternative"
    if recommended:
        role += "; **recommended by policy v1**"
    lines = [f"#### Option {n}: {md_text(option['kind'])} — {role}", "",
             f"- Direction: {md_text(option['direction'])}; mutates: {md_text(option['mutates'])}",
             f"- Destructive: **{'yes' if option['destructive'] else 'no'}**"
             + ("; data of the deleted object is not restored" if option["data_not_restored"] else ""),
             f"- Human decision required: {'yes' if option['human_decision_required'] else 'no'}",
             f"- {md_text(option['description'])}"]
    for fragment in option["fragments"]:
        lines += ["", f"HCL value for {_path(fragment['path'])} (from the current Azure value; where it is defined "
                      "is not determined):", "",
                  *md_fenced(fragment["assignment_hcl"] or fragment["value_hcl"], "hcl")]
    for gap in option["fragment_gaps"]:
        lines.append(f"- No HCL value for {_path(gap['path'])}: {md_text(gap['reason'])}")
    lines += ["", "Commands (catalogue only, **not executed**; placeholders in angle brackets must be filled in):",
              "", *md_fenced("\n".join(c["command"] for c in option["commands"]), "sh"),
              "", f"Approval: **{md_text(option['approval']['status'])}**"
              + ("; destructive confirmation required" if option["approval"]["destructive_confirmation_required"]
                 else "") + ". Execution allowed: **no**. Automatic apply: **no**.", ""]
    return lines


def _heading(resource: Mapping[str, Any]) -> list[str]:
    return [f"### {md_code(resource['address'])}", ""]


def _what_lines(resource: Mapping[str, Any]) -> list[str]:
    what = resource["what"]
    lines = _heading(resource) + _statements(what["statements"]) + [
        f"- Type: {md_text(resource['type'])}; classification: **{md_text(what['classification'])}**; "
        f"action: {_fact(what['action'])}; investigation scope: {md_text(resource['investigation_scope'])}",
        f"- Deterministic severity: **{md_text(what['severity'])}**"
        + (f" ({md_text('; '.join(what['severity_reasons']))})" if what["severity_reasons"] else ""),
        f"- Risk factors: {md_text(', '.join(what['risk_factors']) or 'none')}; moved: "
        f"{'yes' if what['moved'] else 'no'}; importing: {'yes' if what['importing'] else 'no'}", ""]
    rows = [[_path(c["path"]), md_text(c["attribute_class"]), md_text(c["assessment"]), md_text(c["origin"]),
             md_text(c["severity"]), _view(c["desired"]), _view(c["real"]), _view(c["state"])]
            for c in what["changes"]]
    return lines + _table(["Path", "Class", "Assessment", "Origin", "Severity", "Expected (desired)",
                           "Actual (real)", "Recorded (state)"], rows) + [""]


def _operations_lines(resource: Mapping[str, Any]) -> list[str]:
    lines = _heading(resource)
    if resource["investigation_scope"] == "not_drift":
        return lines + _statements(resource["correlation"]["statements"]) + [""]
    if not resource["operations"]:
        status = resource["correlation"]["status"]
        lines.append("- No recorded operations." if status == "investigated" else
                     f"- Recorded operations: {md_text(NOT_CONFIRMED)} (not investigated: "
                     f"{md_text(resource['correlation']['reason'])}).")
    else:
        rows = [[md_text(op["op_id"]), md_code(op["operation_name"]), md_text(op["outcome"]),
                 md_text(", ".join(op["relations"])), md_text(op["start"]), md_text(op["end"]),
                 _fact(op["available_at"]), md_text(op["timing"]), _fact(op["in_window"]), md_text(op["role"]),
                 md_text(", ".join(op["capable_areas"]) or "none"), md_text(op["caller_type"]),
                 md_text(op["client_app"]), _fact(op["pipeline_identity"]), md_text(op["caller_identity"])]
                for op in resource["operations"]]
        lines += _table(["Op", "Operation", "Outcome", "Relations", "Start (event)", "End (event)", "Available",
                         "Timing", "In window", "Role", "Capable areas", "Caller type", "Client", "Pipeline identity",
                         "Identity"], rows)
    if resource["automated_events"]:
        rows = [[md_text(e["ref"]), md_code(e["operation_name"]), md_text(e["category"]), md_text(e["event_timestamp"]),
                 md_text(e["timing"]), _fact(e["in_window"]), _fact(e["signal"])] for e in resource["automated_events"]]
        lines += [""] + _table(["Ref", "Operation", "Category", "Event time", "Timing", "In window", "Signal"], rows)
    counts = resource["correlation"]["counts"]
    if counts["child"]:
        names = ", ".join(f"{k}×{v}" for k, v in resource["correlation"]["descendant_operations"].items())
        lines += ["", f"- Operations on contained or child resources (never decide): {counts['child']} "
                      f"({md_text(names)})"]
    return lines + [""]


def _when_lines(resource: Mapping[str, Any]) -> list[str]:
    when = resource["when"]
    lines = _heading(resource) + _statements(when["statements"])
    if when["status"] == "not_applicable":
        return lines + [""]
    observation = when["observation"] or {}
    anchor = when["last_in_sync"]
    window = when["window"]
    return lines + [
        f"- Event time (Activity Log): start {_fact(when['event_start'])}, end {_fact(when['event_end'])}; "
        f"available {_fact(when['available_at'])}",
        f"- Detection time (Terraform): observation {_fact(observation.get('started_at'))} to "
        f"{_fact(observation.get('finished_at'))}; plan timestamp {_fact(when['plan_timestamp'])}",
        "- Gap between the operation end and the observation start: "
        + (f"{md_text(when['gap_seconds'])} s" if when["gap_seconds"] is not None else _fact(None)),
        "- Last in-sync observation: "
        + (f"run {md_text(anchor['run_id'])}, {md_text(anchor['started_at'])} to {md_text(anchor['finished_at'])}"
           if anchor else _fact(None)),
        "- Correlation window: " + (f"{md_text(window['kind'])} from {md_text(window['start'])}" if window
                                     else _fact(None)), ""]


def _who_lines(resource: Mapping[str, Any]) -> list[str]:
    who = resource["who"]
    caller, actor = who["recorded_caller"], who["actor_attribution"]
    lines = _heading(resource) + _statements(who["statements"])
    if caller["status"] == "not_applicable":
        return lines + [""]
    return lines + [
        f"- Recorded caller: **{md_text(caller['status'])}**"
        + (f" ({md_text(caller['reason'])})" if caller["reason"] else "")
        + f"; operation {_fact(caller['operation'])}; caller type {_fact(caller['caller_type'])}; client "
          f"{_fact(caller['client_app'])}; pipeline identity {_fact(caller['pipeline_identity'])}; identity "
          f"**{md_text(caller['identity'])}**; candidate operations {caller['candidate_operations']}",
        f"- Actor attribution: **{md_text(actor['status'])}**"
        + (f" (rule {md_text(actor['rule'])})" if actor["rule"] else ""), ""]


def _correlation_lines(resource: Mapping[str, Any]) -> list[str]:
    corr = resource["correlation"]
    lines = _heading(resource)
    if corr["status"] == "not_applicable":
        return lines + _statements(corr["statements"]) + [""]
    counts = corr["counts"]
    return lines + [
        f"- Verdict: **{md_text(corr['verdict'])}**" + (f" ({md_text(corr['reason'])})" if corr["reason"] else ""),
        f"- Property link: **{md_text(corr['property_link'])}**"
        + (f" ({md_text(corr['property_link_reason'])})" if corr["property_link_reason"] else ""),
        f"- Relevant property areas: {md_text(', '.join(corr['relevant_areas']))}; unreadable events in scope: "
        f"{_fact(corr['unreadable_events_in_scope'])}",
        "- Counts: " + md_text(", ".join(f"{k} {v}" for k, v in counts.items())),
    ] + _statements(corr["statements"]) + [""]


def render_markdown(report_json: Mapping[str, Any]) -> str:
    """Markdown for a report, from its validated JSON form only. Order: Summary, What changed, Recorded Azure
    operations, When, Who, Correlation, Analysis, Recommendation & options, Limitations, Provenance."""
    report = AiAnalysisReport.model_validate_json(json.dumps(report_json)).model_dump(mode="json")
    src, summary, llm, inv = report["provenance"], report["summary"], report["llm"], report["investigation"]
    resources = report["resources"]
    drifted = [r for r in resources if r["investigation_scope"] == "drift"]
    lines = [
        "# AI drift analysis report", "",
        "> Generated deterministically from validated evidence. Terraform evidence (what changed) and Activity Log "
        "evidence (recorded operations) are labelled as such; AI sections are **inference**. Nothing in this report "
        "has been executed.", "",
        "## Summary", "",
        f"- Outcome: **{md_text(summary['outcome'])}**; drift: **{md_text(summary['has_drift'])}**",
        f"- Highest deterministic severity: **{md_text(summary['highest_severity'])}**",
        f"- Resources: {md_text(summary['resources_total'])}; drifted: {md_text(summary['drifted_resources'])}; "
        f"classes: {md_text(', '.join(f'{k}={v}' for k, v in summary['classification_counts'].items()) or 'none')}",
    ]
    if summary["failure"]:
        failure = summary["failure"]
        lines.append(f"- Failure: {md_text(failure['source'])}/{md_text(failure['stage'])}: "
                     f"{md_text(failure['reason'])} (drift status unknown, never \"no drift\")")
    lines.append(f"- Drift investigation: **{md_text(inv['status'])}**"
                 + (f" ({md_text(inv['failure']['stage'])}/{md_text(inv['failure']['reason'])})"
                    if inv["failure"] else ""))
    if not resources:
        lines.append("- No changed resources: there are no investigation claims.")
    for resource in resources:
        rec = resource["remediation"]["recommendation"]
        corr = resource["correlation"]
        lines.append(f"- {md_code(resource['address'])}: {md_text(resource['what']['classification'])}; verdict "
                     f"{md_text(corr['verdict'] or 'not_applicable')}; recommendation {md_text(rec['decision'])}"
                     + (f" ({md_text(rec['kind'])})" if rec["kind"] else ""))
    lines += ["", "## What changed", "", "Basis: Terraform evidence (drift report).", ""]
    for resource in resources:
        lines += _what_lines(resource)
    lines += ["## Recorded Azure operations", "",
              "Basis: Activity Log evidence (public investigation). Caller identities, resource IDs and event IDs are "
              "withheld; WHO is available locally via `drift-engine who`.", ""]
    for resource in drifted:
        lines += _operations_lines(resource)
    lines += ["## When", "", "Event time (Activity Log) and detection time (Terraform) are reported separately.", ""]
    for resource in resources:
        lines += _when_lines(resource)
    lines += ["## Who", "", "A recorded caller is never presented as the author of the drift unless actor "
              "attribution is confirmed.", ""]
    for resource in resources:
        lines += _who_lines(resource)
    lines += ["## Correlation", ""]
    if inv["completeness"]:
        c = inv["completeness"]
        lines += [f"- Completeness: events available at {md_text(c['queried_at'])}; polls {c['polls']}; settled "
                  f"{_fact(c['settled'])}; maximum observed ingestion delay {_fact(c['max_ingestion_delay_ms'])} ms",
                  ""]
    for resource in resources:
        lines += _correlation_lines(resource)
    lines += ["## Analysis", "", "### Deterministic narrative", ""]
    for resource in resources:
        lines += [f"#### {md_code(resource['address'])}", ""] + _statements(resource["analysis"]["narrative"]) + [""]
    lines += ["### AI interpretation (inference)", ""]
    for name in SECTION_TITLES:
        lines += _section_lines(name, report["analysis"][name])
    remediation = report["remediation"]
    lines += ["## Recommendation & options", "",
              "Recommendations follow the deterministic recommendation policy v1; investigation verdicts and caller "
              "data never change them. \"Matches the current Terraform plan\" marks the plan direction.", ""]
    if remediation["reason"]:
        lines += [md_text(remediation["reason"]), ""]
    options_by_id = {o["option_id"]: o for o in remediation["options"]}
    for resource in resources:
        rec = resource["remediation"]["recommendation"]
        lines += _heading(resource) + _statements(rec["statements"]) + [
            f"- Decision: **{md_text(rec['decision'])}** (rule {md_text(rec['policy_rule'])}, rationale "
            f"{md_text(rec['rationale'])}); approval required: **yes**; execution allowed: **no**; automatic apply: "
            "**no**", ""]
        for n, option_id in enumerate(resource["remediation"]["option_ids"], start=1):
            lines += _option_lines(n, options_by_id[option_id], option_id == rec["option_id"])
    lines += ["### Approval Required", "",
              "- [ ] Re-run `terraform plan` and confirm its diff matches this report (drift report SHA-256 below).",
              "- [ ] Choose an option per resource; destructive options need an explicit destructive confirmation.",
              "- [ ] Replace every placeholder (e.g. `<var_file>`) before running any command.",
              "- [ ] Apply only through the approved, gated pipeline (Phase 11). Nothing here runs automatically.", "",
              "## Limitations", ""]
    lines += [f"- {md_text(item)}" for item in report["limitations"]]
    versions = src["versions"]
    lines += ["", "## Provenance", "",
              f"- Drift report SHA-256: {md_code(src['drift_report_sha256'])}",
              "- Investigation SHA-256: " + (md_code(src["investigation_sha256"]) if src["investigation_sha256"]
                                              else md_text("none (no investigation provided)")),
              f"- Classification version: {md_text(src['classification_version'])}; run: {md_text(src['run_id'])}; "
              f"environment: {md_text(src['environment'])}; plan timestamp: {md_text(src['plan_timestamp'])}",
              "- Versions: " + md_text(", ".join(f"{k} {v if v is not None else 'none'}" for k, v in versions.items())),
              "- Exposure: " + md_text(", ".join(f"{k} {v}" for k, v in inv["exposure"].items())),
              f"- LLM: attempted **{'yes' if llm['attempted'] else 'no'}**, status {md_text(llm['status'])}, provider "
              f"{md_text(llm['provider'])}, model {md_text(llm['model'])}, max retries {md_text(llm['max_retries'])}; "
              f"evidence sent: {len(llm['evidence_sent'])} change(s), {len(llm['investigation_sent'])} investigated "
              "resource(s)"]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- write


def _write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_report(state: Mapping[str, Any], out_dir: str | os.PathLike) -> dict[str, Path]:
    """Write ai_analysis_report.json and ai_analysis_report.md (Markdown rendered from the JSON)."""
    if "report" not in state or not state["report"]:
        raise ValueError("state has no report: run the graph (generate_report) first")
    report = AiAnalysisReport.model_validate_json(json.dumps(state["report"])).model_dump(mode="json")
    json_text = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    markdown = render_markdown(json.loads(json_text))  # from the serialized JSON: the two cannot disagree
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    paths = {"json": directory / JSON_FILE, "markdown": directory / MARKDOWN_FILE}
    _write_atomic(paths["json"], json_text)
    _write_atomic(paths["markdown"], markdown)
    log_event(logger, logging.INFO, "report_written", "AI analysis report written", directory=str(directory))
    return paths
