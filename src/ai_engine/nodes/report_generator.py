"""Deterministic report generation (Task 6.6). No LLM call.

`generate_report` (a LangGraph node after `analyze_drift`) builds the strict
`AiAnalysisReport` JSON from validated state only: the drift report, the
deterministic routing/origin/remediation fields, and the five AI sections as
already validated (rejected findings are counted, never shown). The result is
the write-once `AiState.report`.

`render_markdown` renders Markdown **from that JSON only**, so the two cannot
disagree. `write_report(state, out_dir)` writes `ai_analysis_report.json` and
`ai_analysis_report.md`; it is a library function, not a CLI.

Untrusted text (Terraform/Azure values, AI explanations) is never trusted as
Markdown: running text is escaped (Markdown punctuation, `<`, `>`, `&`) and
links are neutralized (a zero-width space after `:`, `@` and in `www.`), and
values, HCL fragments and commands go into code spans / fenced blocks whose
fence is longer than any backtick run in the content. The output is
deterministic: the same state gives byte-identical files.

Deterministic severity and classification are authoritative; attribution stays
`unknown` / unconfirmed until Phase 7; monetary impact is not determinable.
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

from pydantic import Field, JsonValue

from ai_engine.nodes.common import Strict
from ai_engine.nodes.remediation import RemediationPlan
from drift_engine.logs import log_event

logger = logging.getLogger(__name__)

REPORT_VERSION = "1"
JSON_FILE = "ai_analysis_report.json"
MARKDOWN_FILE = "ai_analysis_report.md"
SECTION_KEYS = {"security": "analyze_security", "cost": "analyze_cost", "configuration": "analyze_configuration",
                "root_cause": "analyze_root_cause", "risk": "assess_risk"}
Status = Literal["ok", "skipped", "failed", "invalid_output"]

BASE_LIMITATIONS = (
    "Terraform evidence (drift_report.json) is the source of truth; AI sections are inference.",
    "Who made a change, when and through which channel is unknown until Activity Log evidence (Phase 7).",
    "No pricing data: monetary impact is not determinable from this evidence (Phase 10).",
    "Remediation options are deterministic and not ranked; plan_default only marks the current Terraform plan "
    "direction. Nothing has been executed; every option needs human approval (Phase 11).",
    "HCL value fragments do not say where a value is defined (resource block, module input or tfvars).",
)


# --------------------------------------------------------------------------- schema


class Provenance(Strict):
    drift_report_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    classification_version: str
    run_id: str | None
    environment: str | None
    plan_timestamp: str | None


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


class ResourceEntry(Strict):
    address: str
    type: str
    classification: str
    action: str | None
    severity: str
    severity_reasons: list[str]
    risk_factors: list[str]
    moved: bool
    importing: bool
    changes: list[ChangeEntry]


class AnalysisSection(Strict):
    status: Status
    reason: str | None
    findings: list[dict[str, JsonValue]]
    rejected_count: int
    rejection_reasons: dict[str, int]
    summary: str | None
    basis: Literal["inference"]


class Analysis(Strict):
    security: AnalysisSection
    cost: AnalysisSection
    configuration: AnalysisSection
    root_cause: AnalysisSection
    risk: AnalysisSection


class LlmInfo(Strict):
    attempted: bool
    status: str
    reason: str | None
    provider: str | None
    model: str | None
    max_retries: int | None


class Attribution(Strict):
    actor: Literal["unknown"]
    confirmed: Literal[False]
    pending: Literal["phase_7_activity_log"]


class CostBoundary(Strict):
    monetary_impact: Literal["not_determinable_from_evidence"]
    pricing_source: None


class AiAnalysisReport(Strict):
    report_version: Literal["1"]
    generated_from: Provenance
    summary: Summary
    resources: list[ResourceEntry]
    analysis: Analysis
    remediation: RemediationPlan
    attribution: Attribution
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


def build_report(state: Mapping[str, Any]) -> dict[str, Any]:
    drift_report = state["drift_report"]
    parsed = state["parsed_drift"]
    facts = state["origin_facts"]
    call = state["llm_call"]
    run = drift_report.get("run") or {}
    plan = drift_report.get("plan") or {}
    summary = drift_report.get("summary") or {}
    origins = {(c["address"], tuple(c["path"])): c["origin"] for c in facts["changes"]}
    resource_facts = {r["address"]: r for r in facts["resources"]}

    resources = []
    for resource in parsed["resources"]:
        rf = resource_facts.get(resource["address"], {})
        resources.append({
            "address": resource["address"], "type": resource["type"], "classification": resource["classification"],
            "action": resource["action"], "severity": resource["severity"]["level"],
            "severity_reasons": list(resource["severity"]["reasons"]), "risk_factors": list(rf.get("risk_factors", [])),
            "moved": bool(rf.get("moved", False)), "importing": bool(rf.get("importing", False)),
            "changes": [{
                "path": list(c["path"]), "attribute_class": c["class"], "assessment": c["assessment"]["category"],
                "severity": c["severity"]["level"], "severity_rules": list(c["severity"]["rules"]),
                "origin": origins.get((resource["address"], tuple(c["path"]))), "redacted": c["redacted"],
                "state": dict(c["state"]), "real": dict(c["real"]), "desired": dict(c["desired"]),
            } for c in resource["attribute_changes"]],
        })

    limitations = list(BASE_LIMITATIONS)
    if not call["attempted"]:
        limitations.append(f"AI analysis was not performed: {call['reason']}.")
    if call.get("truncation") and call["truncation"]["truncated"]:
        limitations.append("The AI saw truncated evidence: some changes or values were omitted from its prompt.")

    report = {
        "report_version": REPORT_VERSION,
        "generated_from": {"drift_report_sha256": drift_report_sha256(drift_report),
                           "classification_version": drift_report["classification_version"],
                           "run_id": run.get("run_id"), "environment": run.get("environment"),
                           "plan_timestamp": plan.get("timestamp")},
        "summary": {"outcome": drift_report["outcome"], "has_drift": drift_report["has_drift"],
                    "highest_severity": summary.get("highest_severity"),
                    "resources_total": summary.get("resources_total"),
                    "drifted_resources": summary.get("drifted_resources"),
                    "classification_counts": dict(summary.get("classification_counts") or {}),
                    "failure": drift_report.get("failure")},
        "resources": resources,
        "analysis": {section: _section(state["inferences"][key]) for section, key in SECTION_KEYS.items()},
        "remediation": state["remediation_plan"],
        "attribution": {"actor": "unknown", "confirmed": False, "pending": "phase_7_activity_log"},
        "cost": {"monetary_impact": "not_determinable_from_evidence", "pricing_source": None},
        "llm": {key: call.get(key) for key in ("attempted", "status", "reason", "provider", "model", "max_retries")},
        "limitations": limitations,
    }
    return AiAnalysisReport.model_validate_json(json.dumps(report)).model_dump(mode="json")


def generate_report(state: Mapping[str, Any]) -> dict[str, Any]:
    """LangGraph node: the deterministic report (JSON form) from validated state."""
    report = build_report(state)
    log_event(logger, logging.INFO, "report_generated", "AI analysis report generated",
              resources=len(report["resources"]), options=len(report["remediation"]["options"]),
              llm_status=report["llm"]["status"])
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
    return md_text(f"({view['status']})")


SECTION_TITLES = {
    "security": "Security Impact", "cost": "Cost Impact", "configuration": "Configuration",
    "root_cause": "Root Cause (unconfirmed until Phase 7)", "risk": "Risk",
}
_FINDING_SKIP = {"address", "cited_paths", "explanation", "basis"}


def _finding_lines(finding: Mapping[str, Any]) -> list[str]:
    cited = ", ".join(_path(p) for p in finding["cited_paths"])
    lines = [f"- {md_code(finding['address'])}: {cited}"]
    for key in sorted(k for k in finding if k not in _FINDING_SKIP):
        value = finding[key]
        shown = md_text(value) if isinstance(value, (str, bool, int, float)) or value is None else \
            md_code(json.dumps(value, sort_keys=True, ensure_ascii=False))
        lines.append(f"  - {md_text(key)}: {shown}")
    lines.append(f"  > AI inference: {md_text(finding['explanation'])}")
    return lines


def _section_lines(name: str, section: Mapping[str, Any]) -> list[str]:
    lines = [f"## {SECTION_TITLES[name]}", "",
             f"Status: **{md_text(section['status'])}**" + (f" ({md_text(section['reason'])})"
                                                           if section["reason"] else "")]
    if name == "cost":
        lines += ["", "Monetary impact: **not determinable from evidence** (no pricing data)."]
    if name == "root_cause":
        lines += ["", "Actor: **unknown**. Confirmed: **no** (requires Activity Log evidence)."]
    if name == "risk":
        lines += ["", "No AI risk level: the deterministic severity is the only rating."]
    if section["summary"]:
        lines += ["", f"> AI inference: {md_text(section['summary'])}"]
    if section["findings"]:
        lines += [""] + [line for f in section["findings"] for line in _finding_lines(f)]
    if section["rejected_count"]:
        reasons = ", ".join(f"{md_text(k)} ×{v}" for k, v in section["rejection_reasons"].items())
        lines += ["", f"Rejected AI findings (not shown): {section['rejected_count']} ({reasons})"]
    return lines + [""]


def _option_lines(n: int, option: Mapping[str, Any]) -> list[str]:
    role = "matches the current Terraform plan; not a recommendation" if option["plan_default"] else "alternative"
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


def render_markdown(report_json: Mapping[str, Any]) -> str:
    """Markdown for a report, from its validated JSON form only."""
    report = AiAnalysisReport.model_validate_json(json.dumps(report_json)).model_dump(mode="json")
    src, summary, llm = report["generated_from"], report["summary"], report["llm"]
    lines = [
        "# AI drift analysis report", "",
        "> Generated deterministically from validated evidence. AI sections are **inference**, not Terraform "
        "evidence. Nothing in this report has been executed.", "",
        f"- Drift report SHA-256: {md_code(src['drift_report_sha256'])}",
        f"- Classification version: {md_text(src['classification_version'])}; run: {md_text(src['run_id'])}; "
        f"environment: {md_text(src['environment'])}; plan timestamp: {md_text(src['plan_timestamp'])}",
        f"- LLM: attempted **{'yes' if llm['attempted'] else 'no'}**, status {md_text(llm['status'])}, provider "
        f"{md_text(llm['provider'])}, model {md_text(llm['model'])}, max retries {md_text(llm['max_retries'])}",
        "", "## Summary", "",
        f"- Outcome: **{md_text(summary['outcome'])}**; drift: **{md_text(summary['has_drift'])}**",
        f"- Highest deterministic severity: **{md_text(summary['highest_severity'])}**",
        f"- Resources: {md_text(summary['resources_total'])}; drifted: {md_text(summary['drifted_resources'])}; "
        f"classes: {md_text(', '.join(f'{k}={v}' for k, v in summary['classification_counts'].items()) or 'none')}",
    ]
    if summary["failure"]:
        failure = summary["failure"]
        lines.append(f"- Failure: {md_text(failure['source'])}/{md_text(failure['stage'])}: "
                     f"{md_text(failure['reason'])} (drift status unknown, never \"no drift\")")
    lines += ["", "## Resources", ""]
    for resource in report["resources"]:
        lines += [f"### {md_code(resource['address'])}", "",
                  f"- Type: {md_text(resource['type'])}; classification: **{md_text(resource['classification'])}**; "
                  f"action: {md_text(resource['action'])}",
                  f"- Deterministic severity: **{md_text(resource['severity'])}**"
                  + (f" ({md_text('; '.join(resource['severity_reasons']))})" if resource["severity_reasons"] else ""),
                  f"- Risk factors: {md_text(', '.join(resource['risk_factors']) or 'none')}; moved: "
                  f"{'yes' if resource['moved'] else 'no'}; importing: {'yes' if resource['importing'] else 'no'}",
                  "", "| Path | Class | Assessment | Origin | Severity | State | Real | Desired |",
                  "|---|---|---|---|---|---|---|---|"]
        for change in resource["changes"]:
            cells = [_path(change["path"]), md_text(change["attribute_class"]), md_text(change["assessment"]),
                     md_text(change["origin"]), md_text(change["severity"]), _view(change["state"]),
                     _view(change["real"]), _view(change["desired"])]
            lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
        lines.append("")
    for name in ("security", "cost", "configuration", "root_cause", "risk"):
        lines += _section_lines(name, report["analysis"][name])
    remediation = report["remediation"]
    lines += ["## Remediation Options", "",
              "Options are deterministic and **not ranked**. \"Matches the current Terraform plan\" only marks the "
              "plan direction; it is not a recommendation.", ""]
    if remediation["reason"]:
        lines += [md_text(remediation["reason"]), ""]
    by_address: dict[str, list] = {}
    for option in remediation["options"]:
        by_address.setdefault(option["address"], []).append(option)
    for address, options in by_address.items():
        lines += [f"### {md_code(address)}", ""]
        for n, option in enumerate(options, start=1):
            lines += _option_lines(n, option)
    lines += ["## Approval Required", "",
              "- [ ] Re-run `terraform plan` and confirm its diff matches this report (drift report SHA-256 above).",
              "- [ ] Choose an option per resource; destructive options need an explicit destructive confirmation.",
              "- [ ] Replace every placeholder (e.g. `<var_file>`) before running any command.",
              "- [ ] Apply only through the approved, gated pipeline (Phase 11). Nothing here runs automatically.", "",
              "## Limitations", ""]
    lines += [f"- {md_text(item)}" for item in report["limitations"]]
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
