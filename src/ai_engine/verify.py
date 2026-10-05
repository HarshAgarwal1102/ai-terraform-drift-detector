"""Independent end-to-end verification of a final AI analysis report (Task 6.7).

`verify_report(report_json, drift_report_json, investigation_json=None)` checks the whole chain

    drift_report (+ public investigation) -> parsed evidence -> evidence sent to the model
        -> validated AI output -> final report (version 2)

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
  interpolation, commands exactly from the catalogue, nothing executable;
  recommendation policy v1 restated (R0-R4) per resource;
- investigation (Task 9B.4), against the public investigation file and the
  drift report: its contract, leak scan, binding and scope; the provenance hash
  and versions; the run-level status, failure, completeness, anchors, rules and
  the observation window; per resource the scope (`drift` / `not_drift`), the
  verdict, reason, property link (never confirmed for update drift), deletion
  rule, operations, counts, WHEN (decisive operation times, `gap_seconds`), WHO
  (the D1 caller statuses, actor attribution), every statement against its fixed
  template, the "not confirmed by available evidence" wording for unknown
  facts, the narrative order, and a leak scan of the investigation sections;
  `llm.investigation_sent` and the investigation section's citations,
  consistency and deterministic fields; the free-text guards re-run with the
  references actually sent.

`ai-analysis` runs this check on every report before writing it (design review
D4): any problem means exit 70 and nothing written.

`verify_markdown(markdown, report_json)` checks the Markdown is the rendering
of the validated JSON and nothing else.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from ai_engine.nodes.common import EvidenceRefs, free_text_violation, timestamp_forms
from ai_engine.nodes.investigation_facts import TEMPLATES
from ai_engine.nodes.remediation import ACCEPT_REMOTE_NOTE, COMMAND_CATALOGUE
from ai_engine.nodes.report_generator import AiAnalysisReport, render_markdown
from drift_engine import investigation_public as pub

SECTIONS = ("security", "cost", "configuration", "root_cause", "risk")
ALL_SECTIONS = SECTIONS + ("investigation",)
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


def verify_report(report_json: Mapping[str, Any], drift_report_json: Mapping[str, Any],
                  investigation_json: Mapping[str, Any] | None = None) -> list[str]:
    """Problems found in `report_json` against `drift_report_json` and, when the report was generated with one,
    the public `investigation_json` (empty list = valid)."""
    try:
        report = AiAnalysisReport.model_validate_json(json.dumps(report_json)).model_dump(mode="json")
    except ValidationError as exc:
        locations = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        return [f"schema: {exc.error_count()} error(s) at {', '.join(locations[:10])}"]
    drift = json.loads(json.dumps(drift_report_json))
    inv = json.loads(json.dumps(investigation_json)) if investigation_json is not None else None
    problems: list[str] = []
    add = problems.append

    # provenance
    src = report["provenance"]
    if src["drift_report_sha256"] != _fingerprint(drift):
        add("provenance: drift_report_sha256 does not match the drift report")
    run, plan, summary = drift.get("run") or {}, drift.get("plan") or {}, drift.get("summary") or {}
    for field, expected in (("classification_version", drift["classification_version"]),
                            ("run_id", run.get("run_id")), ("environment", run.get("environment")),
                            ("plan_timestamp", plan.get("timestamp"))):
        if src[field] != expected:
            add(f"provenance: {field} differs from the drift report")
    expected_inv_sha = _fingerprint(inv) if inv is not None else None
    if src["investigation_sha256"] != expected_inv_sha:
        add("provenance: investigation_sha256 does not match the investigation")
    versions = src["versions"]
    expected_versions = {"investigation_public": inv["public_version"] if inv else None,
                         "capable_operations_table": inv["rules"]["table_version"] if inv else None,
                         "deletion_rules": inv["rules"]["deletion_rules_version"] if inv else None}
    for field, expected in expected_versions.items():
        if versions[field] != expected:
            add(f"provenance: version {field} does not match the investigation")
    if inv is not None:
        problems.extend(_investigation_binding_problems(inv, drift))

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

    # resources and changes (WHAT: Terraform evidence)
    changed = [r for r in drift["resources"] if r["classification"] != "in_sync"]
    by_address = {r["address"]: r for r in changed}
    if [r["address"] for r in report["resources"]] != [r["address"] for r in changed]:
        add("resources: not exactly the changed resources of the drift report, in order")
    for entry in report["resources"]:
        resource = by_address.get(entry["address"])
        if resource is None:
            continue
        what = entry["what"]
        if entry["type"] != resource["type"]:
            add(f"resource {entry['address']}: type differs from the drift report")
        for field, expected in (("classification", resource["classification"]),
                                ("action", resource["action"]), ("severity", resource["severity"]["level"]),
                                ("severity_reasons", resource["severity"]["reasons"]),
                                ("moved", resource["previous_address"] is not None),
                                ("importing", resource["importing"])):
            if what[field] != expected:
                add(f"resource {entry['address']}: {field} differs from the drift report")
        union = [f for f in FACTOR_ORDER if any(f in _factors(resource, c)
                                                 for c in resource["attribute_changes"] if not _is_noise(c))]
        if what["risk_factors"] != union:
            add(f"resource {entry['address']}: risk_factors differ from the evidence")
        if len(what["changes"]) != len(resource["attribute_changes"]):
            add(f"resource {entry['address']}: change count differs from the drift report")
            continue
        for got_change, change in zip(what["changes"], resource["attribute_changes"]):
            expected = {"path": change["path"], "attribute_class": change["class"],
                        "assessment": change["assessment"]["category"], "severity": change["severity"]["level"],
                        "severity_rules": change["severity"]["rules"], "redacted": change["redacted"],
                        "state": change["state"], "real": change["real"], "desired": change["desired"],
                        "origin": None if _is_noise(change) else _origin(resource, change)}
            if got_change != expected:
                add(f"resource {entry['address']} {'.'.join(change['path'])}: change differs from the drift report")

    changes = {(r["address"], tuple(c["path"])): (r, c) for r in changed for c in r["attribute_changes"]}

    # investigation: run-level, then WHEN / WHO / correlation per resource
    problems.extend(_verify_investigation(report, drift, inv, by_address))

    # evidence actually sent to the model
    llm = report["llm"]
    sent: dict[tuple[str, tuple[str, ...]], set[str]] = {}
    if not llm["attempted"] and (llm["evidence_sent"] or llm["investigation_sent"]):
        add("llm: evidence_sent / investigation_sent is not empty although no call was made")
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
    inv_sent = _investigation_sent(llm, inv, add)
    applicable = {s: any(s in secs for secs in sent.values()) for s in SECTIONS}
    applicable["investigation"] = bool(inv_sent)
    truncated = any("truncated evidence" in item for item in report["limitations"])
    all_refs = _refs(inv, drift, list(inv_sent.values()))

    # AI sections
    for section in ALL_SECTIONS:
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
        texts = [result["summary"]] + ([] if section == "investigation" else [f["explanation"]
                                                                            for f in result["findings"]])
        for text in texts:
            violation = free_text_violation(text, all_refs)
            if violation:
                add(f"{where}: AI text breaks the {violation} guard")
        for index, finding in enumerate(result["findings"]):
            if section == "investigation":
                problems.extend(_verify_investigation_finding(index, finding, inv_sent, inv, drift))
            else:
                problems.extend(_verify_finding(section, index, finding, sent, changes, truncated))

    problems.extend(_verify_remediation(report, drift, changed, changes))
    return problems


# --------------------------------------------------------------------------- investigation (Task 9B.4)

_NOT_CONFIRMED = "not confirmed by available evidence"
_DECISIVE = ("sole_capable_operation", "latest_capable_operation")
_TS = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(?:Z|\+00:00)")


def _utc(value: Any) -> datetime | None:
    match = _TS.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        return None
    try:
        return datetime(*(int(match.group(n)) for n in range(1, 7)), int((match.group(7) or "").ljust(6, "0")[:6]),
                        tzinfo=timezone.utc)
    except ValueError:
        return None


def _observation(drift: Mapping[str, Any]) -> dict[str, str] | None:
    run = drift.get("run") or {}
    started, finished = _utc(run.get("started_at")), _utc(run.get("finished_at"))
    if started is None or finished is None or finished < started:
        return None
    return {"started_at": started.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "finished_at": finished.strftime("%Y-%m-%dT%H:%M:%S.%fZ")}


def _areas(resource: Mapping[str, Any]) -> list[str]:
    """Relevant property areas (G6), restated independently from the drift report."""
    if resource["drift_action"] in ("delete", "create", "replace"):
        return {"delete": ["existence_delete"], "create": ["existence_create"],
                "replace": ["existence_create", "existence_delete"]}[resource["drift_action"]]
    areas = sorted({"tags" if c["path"][0] == "tags" else "other" for c in resource["attribute_changes"]
                    if c["class"] in ("drifted", "drifted_converged", "drifted_and_config_changed")
                    and not _is_noise(c)})
    return areas or ["other"]


def _investigation_binding_problems(inv: Mapping[str, Any], drift: Mapping[str, Any]) -> list[str]:
    try:
        model = pub.PublicInvestigation.model_validate_json(json.dumps(inv))
    except ValidationError:
        return ["investigation: does not match the public investigation contract"]
    out = []
    if pub.leak_findings(inv):
        out.append("investigation: fails the public leak scan")
    binding = model.binding
    if (binding.drift_report_sha256 != _fingerprint(drift) or binding.run_id != (drift.get("run") or {}).get("run_id")
            or binding.plan_timestamp != (drift.get("plan") or {}).get("timestamp")):
        out.append("investigation: not bound to this drift report")
    if binding.observation is not None and binding.observation.model_dump() != _observation(drift):
        out.append("investigation: observation window differs from the drift report")
    drifted = sorted((r for r in drift["resources"] if r["drift_actions"] is not None), key=lambda r: r["address"])
    if not (model.outcome == "failed" and not model.resources):
        if [r.address for r in model.resources] != [r["address"] for r in drifted] or any(
                p.drift_action != d["drift_action"] or p.relevant_areas != _areas(d)
                for p, d in zip(model.resources, drifted)):
            out.append("investigation: resources are not exactly the drifted resources of the drift report")
    return out


def _template_regex(template_id: str) -> re.Pattern | None:
    template = TEMPLATES.get(template_id)
    if template is None:
        return None
    parts = re.split(r"\{[a-z_]+\}", template)
    return re.compile("(?s)" + ".+?".join(re.escape(part) for part in parts))


def _statement_problems(where: str, statements: list[Mapping[str, Any]]) -> list[str]:
    out = []
    for item in statements:
        pattern = _template_regex(item["id"])
        if pattern is None or not pattern.fullmatch(item["text"]):
            out.append(f"{where}: statement {item['id']} is not its fixed template")
    return out


def _expected_caller(public: Mapping[str, Any], candidates: int) -> dict[str, Any]:
    """recorded_caller restated (design review D1)."""
    base = {"reason": None, "operation": None, "candidate_operations": candidates, "caller_type": None,
            "client_app": None, "pipeline_identity": None, "identity": "withheld"}
    if public["verdict"] == "not_investigated":
        return base | {"status": "not_investigated"}
    if public["verdict"] in _DECISIVE:
        op = next(o for o in public["operations"] if o["op_id"] == public["decisive_operation"])
        if op["caller_status"] == "recorded":
            return base | {"status": "recorded", "operation": op["op_id"], "caller_type": op["caller_type"],
                           "client_app": op["client_app"], "pipeline_identity": op["pipeline_identity"]}
        return base | {"status": "not_recorded", "operation": op["op_id"],
                       "reason": {"missing": "caller_missing", "inconsistent": "caller_inconsistent"}[
                           op["caller_status"]]}
    if public["verdict"] == "ambiguous" and candidates > 1:
        return base | {"status": "multiple_operations"}
    return base | {"status": "no_decisive_operation"}


def _verify_investigation(report: Mapping[str, Any], drift: Mapping[str, Any], inv: Mapping[str, Any] | None,
                          changed: Mapping[str, Mapping[str, Any]]) -> list[str]:
    out = []
    run = report["investigation"]
    status = inv["outcome"] if inv is not None else "not_available"
    observation = _observation(drift)
    expected_run = {"status": status, "observation": observation,
                    "failure": inv["failure"] if inv else None, "completeness": inv["completeness"] if inv else None,
                    "anchors": inv["anchors"] if inv else None, "rules": inv["rules"] if inv else None}
    for field, expected in expected_run.items():
        if run[field] != expected:
            out.append(f"investigation: {field} differs from the investigation / drift report")
    leaks = pub.leak_findings(run)
    public = {r["address"]: r for r in (inv or {}).get("resources", [])}
    plan_ts = (drift.get("plan") or {}).get("timestamp")
    for entry in report["resources"]:
        address = entry["address"]
        resource = changed.get(address)
        if resource is None:
            continue
        where = f"resource {address}"
        is_drift = resource["drift_actions"] is not None
        if entry["investigation_scope"] != ("drift" if is_drift else "not_drift"):
            out.append(f"{where}: investigation_scope does not match the drift report")
            continue
        for block in ("when", "who", "correlation"):
            out.extend(_statement_problems(f"{where} {block}", entry[block]["statements"]))
        out.extend(_statement_problems(f"{where} what", entry["what"]["statements"]))
        rec = entry["remediation"]["recommendation"]
        out.extend(_statement_problems(f"{where} recommendation", rec["statements"]))
        narrative = (entry["what"]["statements"] + entry["when"]["statements"] + entry["who"]["statements"]
                     + entry["correlation"]["statements"] + rec["statements"])
        if entry["analysis"]["narrative"] != narrative:
            out.append(f"{where}: narrative is not the deterministic statements in order")
        leaks += pub.leak_findings([entry["operations"], entry["automated_events"],
                                    {k: v for k, v in entry["when"].items() if k != "statements"},
                                    {k: v for k, v in entry["who"].items() if k != "statements"},
                                    {k: v for k, v in entry["correlation"].items() if k != "statements"}])
        if not is_drift:
            continue  # the schema enforces not_applicable everywhere for not_drift
        if inv is None or status == "failed":
            reason = "investigation_not_provided" if inv is None else "investigation_failed"
            p = {"verdict": "not_investigated", "reason": reason, "decisive_operation": None,
                 "property_link": "none", "property_link_reason": None, "deletion_rule": None,
                 "unreadable_events_in_scope": False, "relevant_areas": _areas(resource), "operations": [],
                 "automated_events": [], "descendant_events": 0, "descendant_operations": {}, "window": None,
                 "actor_attribution": {"status": "not_confirmed", "rule": None, "claim": None}}
        elif address in public:
            p = public[address]
        else:
            out.append(f"{where}: drifted resource missing from the investigation")
            continue
        corr = entry["correlation"]
        for field in ("verdict", "reason", "property_link", "property_link_reason", "deletion_rule",
                      "unreadable_events_in_scope", "descendant_operations"):
            if corr[field] != p[field]:
                out.append(f"{where}: correlation {field} differs from the investigation")
        if corr["relevant_areas"] != _areas(resource) or corr["relevant_areas"] != p["relevant_areas"]:
            out.append(f"{where}: relevant areas differ from the drift report")
        if corr["status"] != ("not_investigated" if p["verdict"] == "not_investigated" else "investigated"):
            out.append(f"{where}: correlation status does not match the verdict")
        # G5 invariants: update drift is never property-confirmed; only a decisive deletion can be
        if corr["property_link"] == "confirmed" and (resource["drift_action"] != "delete"
                                                     or corr["verdict"] not in _DECISIVE):
            out.append(f"{where}: property link confirmed outside a decisive deletion")
        ops = [dict(op) | {"caller_identity": "withheld", "basis": "activity_log_evidence"} for op in p["operations"]]
        if entry["operations"] != ops:
            out.append(f"{where}: operations differ from the investigation")
        if entry["automated_events"] != [dict(e) | {"basis": "activity_log_evidence"} for e in p["automated_events"]]:
            out.append(f"{where}: automated events differ from the investigation")
        candidates = [op for op in p["operations"] if op["role"] in ("capable", "unclassified")
                      and op["outcome"] in ("successful", "unresolved") and op["timing"] != "after_observation"
                      and op["in_window"]]
        counts = {"operations": len(ops), "capable": sum(o["role"] == "capable" for o in ops),
                  "unclassified": sum(o["role"] == "unclassified" for o in ops),
                  "irrelevant": sum(o["role"] == "irrelevant" for o in ops), "candidates": len(candidates),
                  "after_observation": sum(o["timing"] == "after_observation" for o in ops),
                  "child": p["descendant_events"],
                  "automated_signals": sum(bool(e["signal"]) for e in p["automated_events"])}
        if corr["counts"] != counts:
            out.append(f"{where}: correlation counts differ from the investigation")
        # WHEN
        when = entry["when"]
        decisive = next((o for o in p["operations"] if o["op_id"] == p["decisive_operation"]), None)
        expected_when = {
            "status": "decisive_operation" if decisive else "not_confirmed",
            "decisive_operation": decisive["op_id"] if decisive else None,
            "event_start": decisive["start"] if decisive else None, "event_end": decisive["end"] if decisive else None,
            "available_at": decisive["available_at"] if decisive else None,
            "last_in_sync": (p["window"] or {}).get("anchor"),
            "window": {"kind": p["window"]["kind"], "start": p["window"]["start"]} if p["window"] else None,
            "observation": observation, "plan_timestamp": plan_ts,
            "gap_seconds": round((_utc(observation["started_at"]) - _utc(decisive["end"])).total_seconds(), 6)
            if decisive and observation else None}
        for field, expected in expected_when.items():
            if when[field] != expected:
                out.append(f"{where}: when {field} differs from the investigation / drift report")
        first = when["statements"][0] if when["statements"] else {"id": None, "text": ""}
        if decisive is None and (first["id"] != "when.not_confirmed.v1" or _NOT_CONFIRMED not in first["text"]):
            out.append(f"{where}: an unknown event time must read '{_NOT_CONFIRMED}'")
        if decisive is not None and first["id"] != "when.decisive.v1":
            out.append(f"{where}: the decisive operation's event time is not stated")
        # WHO
        who = entry["who"]
        if who["recorded_caller"] != _expected_caller(p, len(candidates)):
            out.append(f"{where}: recorded_caller differs from the investigation (D1)")
        confirmed = p["actor_attribution"]["status"] == "confirmed"
        expected_actor = ({"status": "confirmed", "rule": p["actor_attribution"]["rule"],
                           "claim": p["actor_attribution"]["claim"]} if confirmed else
                          {"status": "not_confirmed_by_available_evidence", "rule": None, "claim": None})
        if who["actor_attribution"] != expected_actor:
            out.append(f"{where}: actor attribution differs from the investigation")
        if confirmed != (corr["property_link"] == "confirmed"):
            out.append(f"{where}: actor attribution is confirmed exactly with a confirmed property link")
        ids = [s["id"] for s in who["statements"]]
        actor_id = "who.actor_confirmed.v1" if confirmed else "who.actor_not_confirmed.v1"
        if not ids or ids[-1] != actor_id:
            out.append(f"{where}: actor attribution statement missing")
        if who["recorded_caller"]["status"] != "recorded" and who["statements"] and \
                _NOT_CONFIRMED not in who["statements"][0]["text"]:
            out.append(f"{where}: an unknown recorded caller must read '{_NOT_CONFIRMED}'")
        if not confirmed and _NOT_CONFIRMED not in who["statements"][-1]["text"]:
            out.append(f"{where}: unconfirmed attribution must read '{_NOT_CONFIRMED}'")
        verdict_id = {"sole_capable_operation": "correlation.sole.v1", "latest_capable_operation":
                      "correlation.latest.v1", "ambiguous": "correlation.ambiguous.v1",
                      "no_capable_operation_found": "correlation.none.v1",
                      "not_investigated": "correlation.not_investigated.v1"}[p["verdict"]]
        if verdict_id not in [s["id"] for s in corr["statements"]]:
            out.append(f"{where}: the verdict statement is missing")
    if leaks:
        out.append(f"investigation sections: {len(leaks)} leak-scan finding(s)")
    return out


def _investigation_sent(llm: Mapping[str, Any], inv: Mapping[str, Any] | None, add) -> dict[str, dict]:
    """address -> sent public resource (restricted to the references sent); problems reported through `add`."""
    public = {r["address"]: r for r in (inv or {}).get("resources", [])}
    usable = inv is not None and inv["outcome"] in ("complete", "incomplete")
    sent: dict[str, dict] = {}
    for key in llm["investigation_sent"]:
        resource = public.get(key["address"]) if usable else None
        if resource is None or resource["verdict"] == "not_investigated" or key["address"] in sent:
            add(f"llm: investigation_sent names {key['address']}, which was not an investigated resource")
            continue
        ops = [op for op in resource["operations"] if op["op_id"] in key["operations"]]
        events = [e for e in resource["automated_events"] if e["ref"] in key["automated_events"]]
        if [op["op_id"] for op in ops] != key["operations"] or [e["ref"] for e in events] != key["automated_events"]:
            add(f"llm: investigation_sent for {key['address']} names operations absent from the investigation")
        sent[key["address"]] = dict(resource) | {"operations": ops, "automated_events": events}
    return sent


def _refs(inv: Mapping[str, Any] | None, drift: Mapping[str, Any], resources: list) -> EvidenceRefs:
    """What AI text may cite, restated: the timestamps, operation names and references of the investigation evidence
    sent, and the drift report's values for quoted IP addresses / URLs."""
    timestamps: set[str] = set()
    operations: set[str] = set()
    refs: set[str] = set()
    stamps: list[Any] = []
    if resources:
        stamps += list((_observation(drift) or {}).values())
        stamps.append(((inv or {}).get("completeness") or {}).get("queried_at"))
    for resource in resources:
        stamps.append((resource.get("window") or {}).get("start"))
        for op in resource["operations"]:
            stamps += [op["start"], op["end"], op["available_at"]]
            operations.add(op["operation_name"].casefold())
            refs.add(op["op_id"])
        for event in resource["automated_events"]:
            stamps.append(event["event_timestamp"])
            operations.add(event["operation_name"].casefold())
            refs.add(event["ref"])
    for stamp in stamps:
        if stamp:
            timestamps |= timestamp_forms(stamp)
    return EvidenceRefs(frozenset(timestamps), frozenset(operations), frozenset(refs),
                        json.dumps(drift, sort_keys=True, ensure_ascii=False))


def _verify_investigation_finding(index: int, finding: Mapping[str, Any], sent: Mapping[str, dict],
                                  inv: Mapping[str, Any] | None, drift: Mapping[str, Any]) -> list[str]:
    where = f"analysis.investigation.findings[{index}]"
    resource = sent.get(finding["address"])
    if resource is None:
        return [f"{where}: cites a resource whose investigation was not sent"]
    ops = {op["op_id"]: op for op in resource["operations"]}
    if not all(op_id in ops for op_id in finding["cited_operations"]):
        return [f"{where}: cites operations that were not sent for this resource"]
    out = []
    actor = ("confirmed" if resource["actor_attribution"]["status"] == "confirmed"
             else "not_confirmed_by_available_evidence")
    for field, expected in (("verdict", resource["verdict"]), ("property_link", resource["property_link"]),
                            ("actor_attribution", actor)):
        if finding[field] != expected:
            out.append(f"{where}: {field} differs from the investigation")
    cited = [ops[i] for i in finding["cited_operations"]]
    explains = [op["role"] == "capable" and op["outcome"] == "successful" and op["in_window"]
                and op["timing"] != "after_observation" for op in cited]
    if finding["consistency"] == "consistent_with_drift" and not (
            cited and all(explains) and resource["verdict"] in _DECISIVE + ("ambiguous",)):
        out.append(f"{where}: consistent_with_drift exceeds the deterministic evidence")
    if finding["consistency"] == "not_consistent_with_drift" and not (cited and not any(explains)):
        out.append(f"{where}: not_consistent_with_drift contradicts the deterministic evidence")
    violation = free_text_violation(finding["explanation"], _refs(inv, drift, [resource]))
    if violation:
        out.append(f"{where}: AI text breaks the {violation} guard")
    return out


def _verify_recommendation(address: str, rec: Mapping[str, Any], options: list[Mapping[str, Any]],
                           classification: str) -> list[str]:
    """Recommendation policy v1, restated (first matching rule wins)."""
    expected = {"option_id": None, "kind": None, "notes": []}
    plan = next((o for o in options if o["plan_default"]), None)
    if not options:
        expected |= {"decision": "no_options", "policy_rule": "R0", "rationale": "no_options"}
    elif any(o["human_decision_required"] for o in options):
        expected |= {"decision": "human_decision_required", "policy_rule": "R1", "rationale": "ambiguous_intent"}
    elif plan is not None and (plan["destructive"] or plan["data_not_restored"]):
        expected |= {"decision": "human_decision_required", "policy_rule": "R2",
                     "rationale": "plan_direction_destructive"}
    elif classification == "converged_drift" and any(o["kind"] == "refresh_state_only" for o in options):
        refresh = next(o for o in options if o["kind"] == "refresh_state_only")
        expected |= {"decision": "recommended", "policy_rule": "R3", "rationale": "record_converged_state",
                     "option_id": refresh["option_id"], "kind": "refresh_state_only"}
    elif plan is not None:
        expected |= {"decision": "recommended", "policy_rule": "R4", "rationale": "terraform_is_source_of_truth",
                     "option_id": plan["option_id"], "kind": plan["kind"],
                     "notes": [ACCEPT_REMOTE_NOTE] if any(o["kind"] == "accept_remote_value" for o in options)
                     else []}
    out = []
    for field, value in expected.items():
        if rec[field] != value:
            out.append(f"recommendation {address}: {field} does not follow policy v1")
    if rec["address"] != address:
        out.append(f"recommendation {address}: names another resource")
    return out


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
    for entry in report["resources"]:
        options = by_address.get(entry["address"], [])
        if entry["remediation"]["option_ids"] != [o["option_id"] for o in options]:
            out.append(f"remediation {entry['address']}: option_ids are not the resource's options, in order")
        resource = next((r for r in changed if r["address"] == entry["address"]), None)
        if resource is not None:
            out.extend(_verify_recommendation(entry["address"], entry["remediation"]["recommendation"], options,
                                              resource["classification"]))
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


def assert_report_valid(report_json: Mapping[str, Any], drift_report_json: Mapping[str, Any],
                        investigation_json: Mapping[str, Any] | None = None) -> None:
    problems = verify_report(report_json, drift_report_json, investigation_json)
    if problems:
        raise ReportVerificationError(problems)
