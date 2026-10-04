"""Local WHO path: the recorded caller of public investigation operations (Task 9B.3).

The public `drift_investigation.json` withholds every caller identity. A maintainer
who needs it runs `drift-engine who` locally, with their own `az login` (read-only),
the downloaded public file and a local Terraform JSON document that maps addresses
to ARM IDs (`terraform show -json` state, or plan JSON with `prior_state`). For each
public operation it collects a narrow historic window (the operation's start and end
+/- 1 s, `activity_logs.collect_window`), groups the rows exactly as the
investigation does (`investigation.group_operations`) and requires exactly one group
equal in operation name, start and end (to the microsecond), outcome, relations,
caller type and client application. Only then is the caller Azure recorded shown.

Local only (PROJECT_PLAN.md, Phase 9B G12): it refuses to run in GitHub Actions, and
its only output file is `who_evidence.local.json` (0600). It is a recorded caller of
an operation, never a statement of who caused the drift (G3). Fixed error codes:
`binding_failed`, `no_match`, `multiple_matches`, `retention_exceeded`,
`query_failed`; none of them carries a caller.

Never imported by ai_engine (G14).
"""

from __future__ import annotations

import logging
import os
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from drift_engine import activity_logs as al
from drift_engine import investigation as inv
from drift_engine import investigation_public as pub
from drift_engine.logs import log_event

logger = logging.getLogger(__name__)

WHO_VERSION = "1"
WHO_FILE = "who_evidence.local.json"
RETENTION = timedelta(days=90)  # Activity Log retention
QUERY_MARGIN = timedelta(seconds=1)
RESULT_CODES = ("matched", "multiple_matches", "no_match", "query_failed", "retention_exceeded")
BINDING_DETAILS = ("address_unknown", "binding_mismatch", "contract", "invalid_json", "invalid_resource_id",
                   "leak", "terraform_invalid", "too_large")


class WhoRefused(Exception):
    """`who` was asked to run where it must not (GitHub Actions)."""


@dataclass(frozen=True)
class WhoResult:
    document: dict
    complete: bool  # every operation matched


def refuse_in_ci(environ: Mapping[str, str]) -> None:
    if environ.get("GITHUB_ACTIONS") == "true":
        raise WhoRefused("drift-engine who is local-only and refuses to run in GitHub Actions")


def _module_resources(module: Any) -> list[dict]:
    if not isinstance(module, dict):
        return []
    found = [r for r in module.get("resources") or [] if isinstance(r, dict)]
    for child in module.get("child_modules") or []:
        found += _module_resources(child)
    return found


def terraform_resource_ids(data: bytes) -> dict[str, str]:
    """Address -> ARM ID of the managed resources in `terraform show -json` state
    (`values`) or plan JSON (`prior_state.values`). Raises ValueError."""
    raw = pub.strict_json(data)
    if not isinstance(raw, dict):
        raise ValueError("not a Terraform JSON document")
    values = raw.get("values")
    if values is None:
        values = (raw.get("prior_state") or {}).get("values")
    if not isinstance(values, dict):
        raise ValueError("no state values")
    ids = {}
    for resource in _module_resources(values.get("root_module")):
        rid = (resource.get("values") or {}).get("id")
        if resource.get("mode") == "managed" and isinstance(resource.get("address"), str) and isinstance(rid, str):
            ids[resource["address"]] = rid
    return ids


def _failed(public: pub.PublicInvestigation | None, detail: str, now: datetime) -> WhoResult:
    log_event(logger, logging.WARNING, "who_binding_failed", "WHO lookup not possible", detail=detail)
    return WhoResult(_document(public, now, {"code": "binding_failed", "detail": detail}, []), False)


def _document(public: pub.PublicInvestigation | None, now: datetime, failure: dict | None,
              results: list[dict]) -> dict:
    binding = public.binding if public is not None else None
    return {
        "who_version": WHO_VERSION,
        "local_only": True,
        "queried_at": al.format_timestamp(now),
        "public_binding": None if binding is None else {
            "run_id": binding.run_id, "plan_timestamp": binding.plan_timestamp,
            "drift_report_sha256": binding.drift_report_sha256},
        "failure": failure,
        "results": results,
    }


def run_who(public_bytes: bytes, terraform_bytes: bytes, *, source: al.ActivityLogSource, now: datetime,
            report_bytes: bytes | None = None, environ: Mapping[str, str] = os.environ) -> WhoResult:
    """Look up the recorded caller of every operation in a public investigation."""
    refuse_in_ci(environ)
    try:
        public = pub.load_public(public_bytes)
    except pub.PublicInvestigationError as exc:
        return _failed(None, exc.code, now)
    if report_bytes is not None:
        try:
            pub.check_binding(public, report_bytes)
        except pub.PublicInvestigationError as exc:
            return _failed(public, exc.code, now)
    try:
        ids = terraform_resource_ids(terraform_bytes)
    except (ValueError, RecursionError, UnicodeDecodeError):
        return _failed(public, "terraform_invalid", now)

    targets: dict[str, al.ArmId] = {}
    for resource in public.resources:
        if not resource.operations:
            continue
        rid = ids.get(resource.address)
        if rid is None:
            return _failed(public, "address_unknown", now)
        arm = al.parse_resource_id(rid)
        if arm is None or arm.resource_group is None:
            return _failed(public, "invalid_resource_id", now)
        targets[resource.address] = arm

    results = []
    for resource in public.resources:
        for op in resource.operations:
            results.append(_lookup(resource.address, targets[resource.address], op, source, now))
    complete = bool(results) and all(r["status"] == "matched" for r in results)
    log_event(logger, logging.INFO if complete else logging.WARNING, "who_finished", "WHO lookup finished",
              operations=len(results), statuses=dict(sorted(Counter(r["status"] for r in results).items())))
    return WhoResult(_document(public, now, None, results), complete)


def _lookup(address: str, arm: al.ArmId, op: pub.Operation, source: al.ActivityLogSource, now: datetime) -> dict:
    result = {"address": address, "op_id": op.op_id, "operation_name": op.operation_name, "start": op.start,
              "end": op.end, "status": "", "callers": []}
    start, end = al.parse_timestamp(op.start), al.parse_timestamp(op.end)
    if start < now - RETENTION:
        return dict(result, status="retention_exceeded")
    collection = al.collect_window(source, [(address, arm)], start - QUERY_MARGIN, end + QUERY_MARGIN)
    if any(scope["status"] != "complete" for scope in collection.scopes):
        return dict(result, status="query_failed")
    rows = [(event, match.relation) for event in collection.events for match in event.matches
            if match.address == address]
    groups, _, _ = inv.group_operations(rows)
    matches = [g for g in groups
               if g.operation == op.operation_name.lower()
               and al.format_timestamp(g.start) == op.start and al.format_timestamp(g.end) == op.end
               and g.outcome == op.outcome and list(g.relations) == list(op.relations)
               and g.caller_type == op.caller_type and g.client_app == op.client_app]
    if not matches:
        return dict(result, status="no_match")
    if len(matches) > 1:
        return dict(result, status="multiple_matches")
    return dict(result, status="matched", callers=list(matches[0].callers))
