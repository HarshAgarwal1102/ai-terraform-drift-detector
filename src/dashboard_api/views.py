"""Response documents built from the artifact store (Task 13.1).

Pure functions over `store.Bundle`: every value comes from a real artifact, and a
value that no artifact provides is reported as unavailable, never estimated. No
caller identity appears here; `app.py` adds it on request.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from drift_engine.severity import HIGH, SEVERITIES

from dashboard_api.store import Bundle

HISTORY_LIMIT = 100
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


def drift_rows(bundle: Bundle) -> list[dict]:
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
        })
    return rows


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(value) if isinstance(value, str) else None
    except InvalidOperation:
        return None


def cost_impact(bundle: Bundle) -> dict:
    """Monthly cost impact of the drift, from the AI report's validated `cost_impact` (report v3)."""
    ai = bundle.ai_report
    if ai is None:
        return {"status": "no_ai_report", "monthly_cost_delta": None, "display": None, "complete": False}
    impact = ai.get("cost_impact")
    if isinstance(impact, dict) and impact.get("status") == "complete":
        drift = ((impact.get("cost_delta") or {}).get("totals") or {}).get("confirmed_drift") or {}
        return {"status": "complete", "monthly_cost_delta": drift.get("monthly_cost_delta"),
                "display": drift.get("display"), "complete": bool(drift.get("complete")),
                "pricing_source": impact.get("pricing_source")}
    status = impact.get("status") if isinstance(impact, dict) else "not_available"
    return {"status": status, "monthly_cost_delta": None, "display": None, "complete": False}


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
        "artifacts": {"ai_analysis_report": bundle.ai_report is not None,
                      "investigation": bundle.investigation is not None, "cost_run": bundle.cost_run is not None},
        "problems": list(bundle.problems),
    }


def summary(latest: list[Bundle], history: list[Bundle], problems: dict) -> dict:
    runs = [run_summary(b) for b in latest]
    costs = [r["monthly_cost_impact"] for r in runs]
    amounts = [_decimal(c["monthly_cost_delta"]) for c in costs if c["status"] == "complete"]
    cost_complete = bool(costs) and len(amounts) == len(costs) and None not in amounts
    return {
        "reports_total": len(history),
        "data_problems": dict(sorted(problems.items())),
        "overview": {
            "total_resources": sum(r["resources_total"] or 0 for r in runs),
            "active_drifts": sum(r["drifted_resources"] or 0 for r in runs),
            "security_exposure": sum(r["security_exposure"]["high_or_critical_drifts"] for r in runs),
            "monthly_cost_impact": {"monthly_cost_delta": str(sum(amounts)) if cost_complete else None,
                                    "complete": cost_complete, "currency": "USD" if cost_complete else None},
        },
        "environments": runs,
        "history": [{k: s[k] for k in ("report_id", "environment", "finished_at", "outcome", "has_drift",
                                       "drifted_resources", "highest_severity")}
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
