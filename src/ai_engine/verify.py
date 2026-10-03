"""Independent end-to-end verification of a final AI analysis report (Task 6.7).

`verify_report(report_json, drift_report_json)` checks the whole chain

    drift_report -> parsed evidence -> evidence sent to the model -> validated AI output -> final report

and returns a list of problems (empty = valid). It deliberately does **not**
re-run the report-generation path and compare it with itself: every expected
value is derived here, directly from the drift report's contract fields, with
an independently written restatement of the rules (origin categories, risk
factors, routing eligibility, remediation invariants). A defect in the
graph's own nodes therefore shows up as a disagreement instead of being
reproduced on both sides.

What is checked:
- schema (strict; constants such as `actor = "unknown"` are schema-enforced);
- provenance: fingerprint, classification version, run id, plan timestamp;
- deterministic facts: summary, every changed resource and change, origins,
  risk factors, moved/importing — against the drift report;
- `llm.evidence_sent`: every key exists, is not proven noise, and is eligible
  for each section it is tagged with; empty when no call was made;
- AI sections: status/finding consistency, section applicability, citations
  scoped to the evidence sent for that section, every code-attached field
  (`deterministic_severity`, `origin_facts`, `evidence_facts`,
  `classification` / `action`, `risk_factors`, flags) recomputed, hypothesis /
  risk-kind consistency, and the free-text guards re-run on all AI text;
- remediation: scope (only changed resources and their paths), exactly one
  `plan_default` per resource matching the plan action, destructive / data /
  human-decision flags, fragments only from readable values with escaped
  interpolation, commands exactly from the catalogue, nothing executable.

`verify_markdown(markdown, report_json)` checks the Markdown is the rendering
of the validated JSON and nothing else.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from ai_engine.nodes.common import free_text_violation
from ai_engine.nodes.remediation import COMMAND_CATALOGUE
from ai_engine.nodes.report_generator import AiAnalysisReport, render_markdown

SECTIONS = ("security", "cost", "configuration", "root_cause", "risk")
LEVELS = ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL")
FACTOR_ORDER = ("apply_reverts_external_change", "apply_destroys_or_recreates", "ambiguous_intent",
                "unmanaged_setting", "value_unknown_until_apply", "redacted_unreadable", "moved_or_importing")
_CLASS_ORIGIN = {"drifted": "outside_terraform", "drifted_converged": "outside_terraform_converged",
                 "config_changed": "configuration_side", "drifted_and_config_changed": "both_sides",
                 "unknown_until_apply": "value_unknown_until_apply"}
_OBJECT_ORIGIN = {"external_drift": "outside_terraform", "external_deletion": "outside_terraform",
                  "converged_drift": "outside_terraform_converged", "config_change": "configuration_side",
                  "resource_added": "configuration_side", "resource_removed": "configuration_side",
                  "drift_and_config_change": "both_sides"}
_HYPOTHESIS_ALLOWS = {"out_of_band_change": {"outside_terraform", "outside_terraform_converged", "both_sides"},
                      "azure_policy_or_automation": {"outside_terraform", "outside_terraform_converged", "both_sides"},
                      "configuration_change": {"configuration_side", "both_sides"},
                      "provider_or_platform_behavior": {"outside_terraform", "outside_terraform_converged",
                                                        "configuration_side", "both_sides",
                                                        "value_unknown_until_apply"}}


class ReportVerificationError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("report verification failed: " + "; ".join(problems[:10]))
        self.problems = problems


# --------------------------------------------------------------------------- independent restatement of the rules


def _fingerprint(drift_report: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(drift_report, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def _is_noise(change: Mapping[str, Any]) -> bool:
    return change["assessment"]["category"] == "noise"


def _origin(resource: Mapping[str, Any], change: Mapping[str, Any]) -> str:
    if resource["classification"] == "undetermined":
        return "undetermined"
    if change["class"] is not None:
        return _CLASS_ORIGIN[change["class"]]
    return _OBJECT_ORIGIN[resource["classification"]]


def _factors(resource: Mapping[str, Any], change: Mapping[str, Any]) -> list[str]:
    action, cls = resource["action"], resource["classification"]
    present = {
        "apply_reverts_external_change": action == "update" and change["class"] in ("drifted",
                                                                                   "drifted_and_config_changed"),
        "apply_destroys_or_recreates": action in ("replace", "delete") or cls == "external_deletion",
        "ambiguous_intent": change["class"] == "drifted_and_config_changed" or resource["ambiguous"] is True,
        "unmanaged_setting": change["assessment"]["category"] == "unconfigured",
        "value_unknown_until_apply": change["class"] == "unknown_until_apply" or change["desired"]["status"] == "unknown",
        "redacted_unreadable": change["redacted"] is True,
        "moved_or_importing": resource["previous_address"] is not None or resource["importing"] is True,
    }
    return [f for f in FACTOR_ORDER if present[f]]


def _section_eligible(section: str, resource: Mapping[str, Any], change: Mapping[str, Any]) -> bool:
    if _is_noise(change):
        return False
    if section == "security":  # rated HIGH+, redacted, or MEDIUM with no rule (impact unknown)
        severity = change["severity"]
        return severity["level"] in ("HIGH", "CRITICAL") or change["redacted"] or (
            severity["level"] == "MEDIUM" and not severity["rules"])
    if section == "risk":
        return bool(_factors(resource, change))
    return True  # cost / configuration / root cause: any non-noise change of a changed resource is plausible


# --------------------------------------------------------------------------- verification


def verify_report(report_json: Mapping[str, Any], drift_report_json: Mapping[str, Any]) -> list[str]:
    """Problems found in `report_json` against `drift_report_json` (empty list = valid)."""
    try:
        report = AiAnalysisReport.model_validate_json(json.dumps(report_json)).model_dump(mode="json")
    except ValidationError as exc:
        locations = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        return [f"schema: {exc.error_count()} error(s) at {', '.join(locations[:10])}"]
    drift = json.loads(json.dumps(drift_report_json))
    problems: list[str] = []
    add = problems.append

    # provenance
    src = report["generated_from"]
    if src["drift_report_sha256"] != _fingerprint(drift):
        add("provenance: drift_report_sha256 does not match the drift report")
    run, plan, summary = drift.get("run") or {}, drift.get("plan") or {}, drift.get("summary") or {}
    for field, expected in (("classification_version", drift["classification_version"]),
                            ("run_id", run.get("run_id")), ("environment", run.get("environment")),
                            ("plan_timestamp", plan.get("timestamp"))):
        if src[field] != expected:
            add(f"provenance: {field} differs from the drift report")

    # summary
    got = report["summary"]
    for field, expected in (("outcome", drift["outcome"]), ("has_drift", drift["has_drift"]),
                            ("highest_severity", summary.get("highest_severity")),
                            ("resources_total", summary.get("resources_total")),
                            ("drifted_resources", summary.get("drifted_resources")),
                            ("classification_counts", summary.get("classification_counts") or {}),
                            ("failure", drift.get("failure"))):
        if got[field] != expected:
            add(f"summary: {field} differs from the drift report")

    # resources and changes
    changed = [r for r in drift["resources"] if r["classification"] != "in_sync"]
    by_address = {r["address"]: r for r in changed}
    if [r["address"] for r in report["resources"]] != [r["address"] for r in changed]:
        add("resources: not exactly the changed resources of the drift report, in order")
    for entry in report["resources"]:
        resource = by_address.get(entry["address"])
        if resource is None:
            continue
        for field, expected in (("type", resource["type"]), ("classification", resource["classification"]),
                                ("action", resource["action"]), ("severity", resource["severity"]["level"]),
                                ("severity_reasons", resource["severity"]["reasons"]),
                                ("moved", resource["previous_address"] is not None),
                                ("importing", resource["importing"])):
            if entry[field] != expected:
                add(f"resource {entry['address']}: {field} differs from the drift report")
        union = [f for f in FACTOR_ORDER if any(f in _factors(resource, c)
                                                 for c in resource["attribute_changes"] if not _is_noise(c))]
        if entry["risk_factors"] != union:
            add(f"resource {entry['address']}: risk_factors differ from the evidence")
        if len(entry["changes"]) != len(resource["attribute_changes"]):
            add(f"resource {entry['address']}: change count differs from the drift report")
            continue
        for got_change, change in zip(entry["changes"], resource["attribute_changes"]):
            expected = {"path": change["path"], "attribute_class": change["class"],
                        "assessment": change["assessment"]["category"], "severity": change["severity"]["level"],
                        "severity_rules": change["severity"]["rules"], "redacted": change["redacted"],
                        "state": change["state"], "real": change["real"], "desired": change["desired"],
                        "origin": None if _is_noise(change) else _origin(resource, change)}
            if got_change != expected:
                add(f"resource {entry['address']} {'.'.join(change['path'])}: change differs from the drift report")

    changes = {(r["address"], tuple(c["path"])): (r, c) for r in changed for c in r["attribute_changes"]}

    # evidence actually sent to the model
    llm = report["llm"]
    sent: dict[tuple[str, tuple[str, ...]], set[str]] = {}
    if not llm["attempted"] and llm["evidence_sent"]:
        add("llm: evidence_sent is not empty although no call was made")
    for key in llm["evidence_sent"]:
        k = (key["address"], tuple(key["path"]))
        if k in sent:
            add(f"llm: evidence_sent repeats {key['address']} {'.'.join(key['path'])}")
        sent[k] = set(key["sections"])
        if k not in changes:
            add(f"llm: evidence_sent cites {key['address']} {'.'.join(key['path'])}, absent from the drift report")
            continue
        for section in key["sections"]:
            if not _section_eligible(section, *changes[k]):
                add(f"llm: {key['address']} {'.'.join(key['path'])} was not eligible for the {section} section")
    applicable = {s: any(s in secs for secs in sent.values()) for s in SECTIONS}
    truncated = any("truncated evidence" in item for item in report["limitations"])

    # AI sections
    for section in SECTIONS:
        result = report["analysis"][section]
        where = f"analysis.{section}"
        if result["rejected_count"] != sum(result["rejection_reasons"].values()):
            add(f"{where}: rejected_count does not match rejection_reasons")
        if result["status"] != "ok" and (result["findings"] or result["summary"]):
            add(f"{where}: status {result['status']} but findings or summary present")
        if not llm["attempted"] and result["status"] != "skipped":
            add(f"{where}: status {result['status']} although no call was made")
        if result["findings"] and not applicable[section]:
            add(f"{where}: findings although no evidence was sent for this section")
        for text in [result["summary"]] + [f["explanation"] for f in result["findings"]]:
            violation = free_text_violation(text)
            if violation:
                add(f"{where}: AI text breaks the {violation} guard")
        for index, finding in enumerate(result["findings"]):
            problems.extend(_verify_finding(section, index, finding, sent, changes, truncated))

    problems.extend(_verify_remediation(report, drift, changed, changes))
    return problems


def _verify_finding(section: str, index: int, finding: Mapping[str, Any], sent: Mapping, changes: Mapping,
                    truncated: bool) -> list[str]:
    where = f"analysis.{section}.findings[{index}]"
    keys = [(finding["address"], tuple(p)) for p in finding["cited_paths"]]
    if not all(section in sent.get(k, set()) and k in changes for k in keys):
        return [f"{where}: cites evidence that was not sent for the {section} section"]
    out = []
    cited = [changes[k] for k in keys]
    expected_severity = max((c["severity"]["level"] for _, c in cited), key=LEVELS.index)
    if finding["deterministic_severity"] != expected_severity:
        out.append(f"{where}: deterministic_severity differs from the cited evidence")
    if section == "security":
        below = LEVELS.index(finding["ai_assessed_impact"]) < LEVELS.index(expected_severity)
        if finding["ai_impact_below_deterministic"] != below:
            out.append(f"{where}: ai_impact_below_deterministic is wrong")
    elif section == "cost":
        resource = cited[0][0]
        if (finding["classification"], finding["action"]) != (resource["classification"], resource["action"]):
            out.append(f"{where}: classification/action differ from the drift report")
    elif section == "configuration":
        facts = [{"path": c["path"], "class": c["class"], "assessment": c["assessment"]["category"]} for _, c in cited]
        if finding["evidence_facts"] != facts:
            out.append(f"{where}: evidence_facts differ from the drift report")
        if finding["topic"] == "other" and finding["topic_conflicts_with_evidence"]:
            out.append(f"{where}: topic 'other' cannot conflict with evidence")
    elif section == "root_cause":
        facts = [{"path": c["path"], "origin": _origin(r, c), "lifecycle": c["class"] is None,
                  "risk_factors": _factors(r, c)} for r, c in cited]
        if finding["origin_facts"] != facts:
            out.append(f"{where}: origin_facts differ from the evidence")
        hypothesis = finding["hypothesis"]
        for fact in facts:
            if hypothesis == "lifecycle_change" and not fact["lifecycle"]:
                out.append(f"{where}: lifecycle_change cited a non-lifecycle change")
            elif hypothesis in _HYPOTHESIS_ALLOWS and fact["origin"] not in _HYPOTHESIS_ALLOWS[hypothesis]:
                out.append(f"{where}: hypothesis {hypothesis} contradicts origin {fact['origin']}")
    elif section == "risk":
        union = [f for f in FACTOR_ORDER if any(f in _factors(r, c) for r, c in cited)]
        if finding["risk_factors"] != union:
            out.append(f"{where}: risk_factors differ from the evidence")
        kind = finding["risk_kind"]
        if finding["risk_kind_unverified"] != (kind == "other"):
            out.append(f"{where}: risk_kind_unverified is wrong")
        if kind == "evidence_incomplete":
            if "redacted_unreadable" not in union and not truncated:
                out.append(f"{where}: evidence_incomplete without redaction or truncation")
        elif kind != "other" and kind not in union:
            out.append(f"{where}: risk_kind {kind} is not a factor of the cited changes")
    return out


def _verify_remediation(report: Mapping[str, Any], drift: Mapping[str, Any], changed: list, changes: Mapping
                        ) -> list[str]:
    out = []
    plan = report["remediation"]
    if drift["outcome"] != "succeeded":
        if plan["options"] or not plan["reason"]:
            out.append("remediation: a failed drift report must have no options and a reason")
        return out
    working_dir = (drift.get("run") or {}).get("working_dir")
    by_address: dict[str, list] = {}
    for option in plan["options"]:
        by_address.setdefault(option["address"], []).append(option)
    if list(by_address) != [r["address"] for r in changed]:
        out.append("remediation: options are not exactly per changed resource, in order")
    for resource in changed:
        address, action, cls = resource["address"], resource["action"], resource["classification"]
        options = by_address.get(address, [])
        defaults = [o for o in options if o["plan_default"]]
        if len(defaults) != 1:
            out.append(f"remediation {address}: not exactly one plan_default option")
        human = resource["ambiguous"] is True or cls in ("drift_and_config_change", "undetermined")
        paths = {tuple(c["path"]) for c in resource["attribute_changes"]}
        evidence = [{"path": c["path"], "attribute_class": c["class"], "assessment": c["assessment"]["category"],
                     "origin": _origin(resource, c), "severity": c["severity"]["level"]}
                    for c in resource["attribute_changes"] if not _is_noise(c)]
        for n, option in enumerate(options, start=1):
            where = f"remediation {option['option_id']}"
            if option["option_id"] != f"{address}#{n}":
                out.append(f"{where}: option_id is not sequential for its resource")
            expected_action = action if option["plan_default"] else None
            if option["terraform_plan_action"] != expected_action:
                out.append(f"{where}: terraform_plan_action does not match the plan")
            destructive = option["plan_default"] and action in ("replace", "delete")
            if option["destructive"] != destructive or option["approval"]["destructive_confirmation_required"] \
                    != destructive:
                out.append(f"{where}: destructive flags do not match the plan action")
            if option["data_not_restored"] != (option["kind"] == "recreate_deleted_object"):
                out.append(f"{where}: data_not_restored is wrong")
            if option["kind"] == "recreate_deleted_object" and cls != "external_deletion":
                out.append(f"{where}: recreate offered for a resource that was not deleted outside Terraform")
            if option["human_decision_required"] != human:
                out.append(f"{where}: human_decision_required is wrong")
            if option["evidence"] != evidence:
                out.append(f"{where}: evidence differs from the drift report")
            for fragment in option["fragments"]:
                change = changes.get((address, tuple(fragment["path"])), (None, None))[1]
                if change is None or tuple(fragment["path"]) not in paths:
                    out.append(f"{where}: fragment for a path outside the resource's changes")
                    continue
                readable = (change["class"] is not None and not change["redacted"]
                            and change["real"]["status"] == "value" and change["class"] != "unknown_until_apply")
                if not readable:
                    out.append(f"{where}: fragment for a value that must not produce one")
                value = fragment["value_hcl"]
                if "${" in value.replace("$${", "") or "%{" in value.replace("%%{", ""):
                    out.append(f"{where}: fragment contains an unescaped template sequence")
                if (fragment["assignment_hcl"] is not None) != (len(fragment["path"]) == 1 and bool(
                        re.match(r"\A[A-Za-z_][A-Za-z0-9_-]*\Z", fragment["path"][0]))):
                    out.append(f"{where}: assignment_hcl present for a nested path (or missing)")
            for gap in option["fragment_gaps"]:
                if tuple(gap["path"]) not in paths:
                    out.append(f"{where}: fragment gap for a path outside the resource's changes")
            for command in option["commands"]:
                problem = _command_problem(command, working_dir, address)
                if problem:
                    out.append(f"{where}: {problem}")
    return out


def _command_problem(command: Mapping[str, Any], working_dir: str | None, address: str) -> str | None:
    entry = COMMAND_CATALOGUE.get(command["template_id"])
    if entry is None:
        return f"command template {command['template_id']!r} is not in the catalogue"
    if "-auto-approve" in command["command"] or re.search(r"\bdestroy\b", command["command"]):
        return "command would apply or destroy without review"
    template, read_only, mutates = entry
    expected = template.format(working_dir=shlex.quote(working_dir) if working_dir is not None else "<working_dir>",
                               var_file="<var_file>", address=shlex.quote(address))
    if command["command"] != expected or command["read_only"] != read_only or command["mutates"] != mutates:
        return "command differs from its catalogue template"
    return None


def verify_markdown(markdown: str, report_json: Mapping[str, Any]) -> list[str]:
    """Problems if `markdown` is not exactly the rendering of the validated report JSON."""
    try:
        expected = render_markdown(report_json)
    except ValidationError:
        return ["markdown: the report JSON is not valid"]
    return [] if markdown == expected else ["markdown: not the rendering of the report JSON"]


def assert_report_valid(report_json: Mapping[str, Any], drift_report_json: Mapping[str, Any]) -> None:
    problems = verify_report(report_json, drift_report_json)
    if problems:
        raise ReportVerificationError(problems)
