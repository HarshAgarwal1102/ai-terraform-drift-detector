"""Response documents built from the artifact store (Task 13.1).

Pure functions over `store.Bundle`: every value comes from a real artifact, and a
value that no artifact provides is reported as unavailable, never estimated. No
caller identity appears here; `app.py` adds it on request.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from drift_engine import investigation_public as pub
from drift_engine import cost as drift_cost
from drift_engine import unmanaged_cost, unmanaged_public
from drift_engine.severity import HIGH, SEVERITIES

from dashboard_api import issues as issue_states
from dashboard_api.store import Bundle

HISTORY_LIMIT = 100
# AI report versions (ai_engine report_generator): v2 has no cost estimate; v3 adds the validated drift cost
# (`cost.status`, `cost.cost_delta`, Task 10.3); v4 adds the separate `unmanaged` section (Task 10.4).
KNOWN_REPORT_VERSIONS = ("2", "3", "4")
COST_REPORT_VERSIONS = ("3", "4")
UNMANAGED_REPORT_VERSIONS = ("4",)
EXPOSED = SEVERITIES[SEVERITIES.index(HIGH):]  # HIGH and CRITICAL


def _path(parts: Any) -> str:
    if not isinstance(parts, list):
        return ""
    return "".join(f"[{p}]" if isinstance(p, int) else (f".{p}" if i else str(p)) for i, p in enumerate(parts))


def _ai_resource(bundle: Bundle, address: str) -> dict:
    resources = (bundle.ai_report or {}).get("resources") or []
    return next((r for r in resources if isinstance(r, dict) and r.get("address") == address), {})


def _operation(bundle: Bundle, address: str) -> dict | None:
    """The drift's identified change: the decisive operation of the public investigation."""
    if bundle.investigation is None:
        return None
    resource = next((r for r in bundle.investigation.resources if r.address == address), None)
    if resource is None:
        return None
    op = next((o for o in resource.operations if o.op_id == resource.decisive_operation), None)
    base = {"verdict": resource.verdict}
    if op is None:
        return dict(base, op_id=None)
    return dict(base, op_id=op.op_id, operation_name=op.operation_name, start=op.start, end=op.end,
                outcome=op.outcome, timing=op.timing, caller_type=op.caller_type, client_app=op.client_app,
                pipeline_identity=op.pipeline_identity)


def _recommendation(ai_resource: dict) -> dict | None:
    rec = (ai_resource.get("remediation") or {}).get("recommendation")
    if not isinstance(rec, dict):
        return None
    return {k: rec.get(k) for k in ("decision", "kind", "option_id", "policy_rule", "approval_required",
                                    "automatic_apply", "execution_allowed")}


def is_drifted(resource: dict) -> bool:
    """The drift report's own rule (classifier.py): the resource has drift actions."""
    return resource.get("drift_actions") is not None


def drift_rows(bundle: Bundle, snapshot: issue_states.Snapshot | None = None) -> list[dict]:
    rows = []
    for resource in bundle.report.get("resources") or []:
        if not isinstance(resource, dict) or not is_drifted(resource):
            continue
        address = resource.get("address")
        ai_resource = _ai_resource(bundle, address)
        rows.append({
            "report_id": bundle.run_id,
            "environment": bundle.environment,
            "address": address,
            "type": resource.get("type"),
            "classification": resource.get("classification"),
            "drift_actions": resource.get("drift_actions"),
            "severity": (resource.get("severity") or {}).get("level"),
            "severity_reasons": (resource.get("severity") or {}).get("reasons") or [],
            "changes": [{
                "property": _path(change.get("path")),
                "attribute_class": change.get("class"),
                "expected": change.get("desired"),
                "actual": change.get("real"),
                "state": change.get("state"),
                "redacted": change.get("redacted"),
                "severity": (change.get("severity") or {}).get("level"),
            } for change in resource.get("attribute_changes") or [] if isinstance(change, dict)],
            "operation": _operation(bundle, address),
            "ai_analysis": {"available": bool(ai_resource),
                            "narrative": [s.get("text") for s in (ai_resource.get("analysis") or {}).get("narrative")
                                          or [] if isinstance(s, dict)]},
            "remediation": _recommendation(ai_resource),
            "issue": issue_states.issue_status(snapshot, bundle.environment, address, bundle.run.get("finished_at")),
            "remediation_pr": dict(issue_states.REMEDIATION_PR),
        })
    return rows


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(value) if isinstance(value, str) else None
    except InvalidOperation:
        return None


def _report_version(bundle: Bundle) -> str | None:
    version = (bundle.ai_report or {}).get("report_version")
    return version if isinstance(version, str) else None


def cost_impact(bundle: Bundle) -> dict:
    """Monthly cost impact of the drift, from the AI report's `cost` section (report v3/v4 only). The embedded
    `cost_delta` is validated with drift_engine.cost.CostDelta and must be bound to this very run (run id and
    drift report SHA-256); otherwise no amount is shown."""
    none = {"monthly_cost_delta": None, "display": None, "complete": False}
    if bundle.ai_report is None:
        return dict(none, status="no_ai_report")
    version = _report_version(bundle)
    if version not in KNOWN_REPORT_VERSIONS:
        return dict(none, status="unsupported_report_version")
    if version not in COST_REPORT_VERSIONS:
        return dict(none, status="not_available")  # report v2: never an amount
    impact = bundle.ai_report.get("cost")
    status = impact.get("status") if isinstance(impact, dict) and isinstance(impact.get("status"), str) else "invalid"
    if status != "complete":
        return dict(none, status=status)
    try:
        delta = drift_cost.CostDelta.model_validate_json(json.dumps(impact.get("cost_delta")))
    except (ValidationError, ValueError, TypeError):
        return dict(none, status="cost_delta_invalid")
    if delta.binding.run_id != bundle.run_id or delta.binding.drift_report_sha256 != bundle.report_sha256:
        return dict(none, status="cost_delta_mismatch")
    drift = delta.totals.confirmed_drift
    return {"status": "complete", "monthly_cost_delta": drift.monthly_cost_delta, "display": drift.display,
            "complete": drift.complete, "with_cost": drift.with_cost, "pricing_source": impact.get("pricing_source")}


def security_exposure(bundle: Bundle) -> dict:
    drifted = [r for r in bundle.report.get("resources") or [] if isinstance(r, dict) and is_drifted(r)]
    security = ((bundle.ai_report or {}).get("analysis") or {}).get("security") or {}
    return {
        "high_or_critical_drifts": sum(1 for r in drifted if (r.get("severity") or {}).get("level") in EXPOSED),
        "ai_security_status": security.get("status") if bundle.ai_report else "no_ai_report",
        "ai_security_findings": len(security.get("findings") or []),
    }


def run_summary(bundle: Bundle) -> dict:
    summary, run, plan = bundle.report.get("summary") or {}, bundle.run, bundle.report.get("plan") or {}
    return {
        "report_id": bundle.run_id,
        "environment": bundle.environment,
        "outcome": bundle.report.get("outcome"),
        "has_drift": bundle.report.get("has_drift"),
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "plan_timestamp": plan.get("timestamp"),
        "git_commit": run.get("git_commit"),
        "resources_total": summary.get("resources_total"),
        "drifted_resources": summary.get("drifted_resources"),
        "highest_severity": summary.get("highest_severity"),
        "severity_counts": summary.get("severity_counts") or {},
        "classification_counts": summary.get("classification_counts") or {},
        "security_exposure": security_exposure(bundle),
        "monthly_cost_impact": cost_impact(bundle),
        "unmanaged": unmanaged_summary(bundle),
        "artifacts": {"ai_analysis_report": bundle.ai_report is not None,
                      "investigation": bundle.investigation is not None, "cost_run": bundle.cost_run is not None,
                      "unmanaged_inventory": bundle.inventory is not None},
        "problems": list(bundle.problems),
    }


def summary(latest: list[Bundle], history: list[Bundle], problems: dict,
            snapshot: issue_states.Snapshot | None = None) -> dict:
    runs = [run_summary(b) for b in latest]
    costs = [r["monthly_cost_impact"] for r in runs]
    validated = bool(costs) and all(c["status"] == "complete" for c in costs)
    priced = [c for c in costs if c["status"] == "complete" and c.get("with_cost")]
    amounts = [_decimal(c["monthly_cost_delta"]) for c in priced]
    if validated and not priced:
        cost_status = "no_drift_cost"  # every validated estimate: no cost line for confirmed drift (never "$0")
    elif validated and None not in amounts:
        cost_status = "estimated"
    else:
        cost_status = "not_available"
    cost_complete = cost_status == "estimated" and all(c["complete"] for c in priced)
    return {
        "reports_total": len(history),
        "data_problems": dict(sorted(problems.items())),
        "overview": {
            "total_resources": sum(r["resources_total"] or 0 for r in runs),
            "active_drifts": sum(r["drifted_resources"] or 0 for r in runs),
            "security_exposure": sum(r["security_exposure"]["high_or_critical_drifts"] for r in runs),
            "monthly_cost_impact": {"status": cost_status,
                                    "monthly_cost_delta": str(sum(amounts)) if cost_status == "estimated" else None,
                                    "complete": cost_complete,
                                    "currency": "USD" if cost_status == "estimated" else None},
        },
        "environments": runs,
        "issues": issue_states.summary(snapshot, {(b.environment, r.get("address")) for b in history
                                                  for r in b.report.get("resources") or []
                                                  if isinstance(r, dict) and b.environment and r.get("address")}),
        "history": [dict({k: s[k] for k in ("report_id", "environment", "finished_at", "outcome", "has_drift",
                                            "drifted_resources", "resources_total", "highest_severity")},
                         unmanaged={k: s["unmanaged"][k] for k in ("available", "unmanaged", "display", "cost_status")})
                    for s in (run_summary(b) for b in history[:HISTORY_LIMIT])],
    }


def remediations(bundle: Bundle) -> list[dict]:
    """Remediation options of the AI report with their approval and execution state (no approver identity)."""
    remediation = (bundle.ai_report or {}).get("remediation") or {}
    recommended = {}
    for resource in (bundle.ai_report or {}).get("resources") or []:
        rec = _recommendation(resource) if isinstance(resource, dict) else None
        if rec and rec.get("decision") == "recommended":
            recommended[rec.get("option_id")] = rec.get("policy_rule")
    out = []
    for option in remediation.get("options") or []:
        if not isinstance(option, dict):
            continue
        approval, execution = option.get("approval") or {}, option.get("execution") or {}
        out.append({
            "report_id": bundle.run_id,
            "environment": bundle.environment,
            "address": option.get("address"),
            "option_id": option.get("option_id"),
            "kind": option.get("kind"),
            "direction": option.get("direction"),
            "description": option.get("description"),
            "terraform_plan_action": option.get("terraform_plan_action"),
            "destructive": option.get("destructive"),
            "recommended": option.get("option_id") in recommended,
            "policy_rule": recommended.get(option.get("option_id")),
            "approval": {"required": approval.get("required"), "status": approval.get("status"),
                         "decided_at": approval.get("decided_at"),
                         "destructive_confirmation_required": approval.get("destructive_confirmation_required")},
            "execution": {"allowed": execution.get("allowed"), "mode": execution.get("mode"),
                          "automatic_apply": execution.get("automatic_apply")},
        })
    return out


# --------------------------------------------------------------------------- unmanaged resources (Task 10.4)

def _ai_unmanaged(bundle: Bundle) -> tuple[dict | None, str]:
    """The AI report's `unmanaged` section (report v4 only) and a status for it."""
    if bundle.ai_report is None:
        return None, "no_ai_report"
    version = _report_version(bundle)
    if version not in KNOWN_REPORT_VERSIONS:
        return None, "unsupported_report_version"
    if version not in UNMANAGED_REPORT_VERSIONS:
        return None, "not_in_ai_report"  # report v2/v3: no unmanaged section
    section = bundle.ai_report.get("unmanaged")
    if not isinstance(section, dict):
        return None, "invalid"
    return section, section.get("status") if isinstance(section.get("status"), str) else "invalid"


def _listing(bundle: Bundle, section: dict | None) -> tuple[unmanaged_public.Inventory | None, str | None, str | None]:
    """(inventory, its canonical SHA-256, source): the bound artifact, else the AI report's complete section."""
    if bundle.inventory is not None:
        return bundle.inventory, bundle.inventory_sha256, "unmanaged_inventory_artifact"
    raw = section.get("inventory") if section and section.get("status") == "complete" else None
    if raw is None:
        return None, None, None
    try:
        inventory = unmanaged_public.load_inventory(raw)
    except (ValidationError, ValueError, TypeError):
        return None, None, None
    if inventory.binding.run_id != bundle.run_id or inventory.binding.drift_report_sha256 != bundle.report_sha256:
        return None, None, None
    return inventory, pub.canonical_sha256(raw), "ai_report"


def _cost(bundle: Bundle, section: dict | None, status: str, listing_sha: str | None) -> tuple[dict, dict]:
    """(cost header, ref -> estimate). Amounts only from a complete AI section priced for this very inventory
    of this very run."""
    header = {"status": status, "reason": (section or {}).get("reason"), "pricing_source": None, "totals": None}
    if status != "complete" or listing_sha is None:
        return header, {}
    try:
        ai_inventory_sha = pub.canonical_sha256(section["inventory"])
        cost = unmanaged_cost.UnmanagedCost.model_validate_json(json.dumps(section["cost"]))
    except (ValidationError, ValueError, TypeError, KeyError):
        return dict(header, status="ai_section_invalid"), {}
    if (ai_inventory_sha != listing_sha or cost.binding.inventory_sha256 != listing_sha
            or cost.binding.run_id != bundle.run_id or cost.binding.drift_report_sha256 != bundle.report_sha256):
        return dict(header, status="inventory_mismatch"), {}
    totals = cost.totals.model_dump(mode="json")
    header = dict(header, status=cost.status, pricing_source=section.get("pricing_source"), totals=totals)
    return header, {r.ref: r for r in cost.resources}


def unmanaged(bundle: Bundle) -> dict:
    """Resources in the Terraform-managed resource groups that Terraform does not manage, with their
    list-price estimate. Never drift; never estimated here."""
    section, status = _ai_unmanaged(bundle)
    inventory, listing_sha, source = _listing(bundle, section)
    cost, estimates = _cost(bundle, section, status, listing_sha)
    base = {"report_id": bundle.run_id, "environment": bundle.environment, "available": inventory is not None,
            "source": source, "cost": cost}
    if inventory is None:
        return dict(base, outcome=None, failure=None, collected_at=None, counts=None, scopes=[], resources=[],
                    limitations=[])
    resources = []
    for item in inventory.resources:
        estimate = estimates.get(item.ref)
        resources.append({
            "ref": item.ref, "type": item.type, "name": item.name, "name_status": item.name_status,
            "resource_group": item.resource_group, "location": item.location, "category": item.category,
            "attached_to": None if item.attached_to is None else
            {"kind": item.attached_to.kind, "address": item.attached_to.address},
            "detail_status": item.detail_status,
            "power_state": item.pricing_inputs.power_state,
            "estimate": None if estimate is None else
            {"status": estimate.estimate_status, "reason": estimate.reason, "monthly_cost": estimate.monthly_cost,
             "display": estimate.display},
        })
    return dict(base, outcome=inventory.outcome, failure=inventory.failure, collected_at=inventory.collected_at,
                counts=inventory.counts.model_dump(mode="json"),
                scopes=[{"resource_group": s.resource_group, "status": s.status, "error": s.error}
                        for s in inventory.scopes],
                resources=resources, limitations=list(inventory.limitations))


def unmanaged_summary(bundle: Bundle) -> dict:
    view = unmanaged(bundle)
    totals = view["cost"]["totals"] or {}
    return {"available": view["available"], "outcome": view["outcome"],
            "unmanaged": (view["counts"] or {}).get("unmanaged"),
            "attached_to_managed": (view["counts"] or {}).get("attached_to_managed"),
            "cost_status": view["cost"]["status"], "estimated_monthly_cost": totals.get("estimated_monthly_cost"),
            "display": totals.get("display"), "complete": bool(totals.get("complete"))}
