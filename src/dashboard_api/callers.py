"""`Caller recorded by Azure`, looked up on demand (Phase 13 required feature, Task 13.1).

For a drifted resource, the drift's identified change is its decisive operation in
the bound public investigation (verdict `sole_capable_operation` or
`latest_capable_operation`). Its Activity Log record is found exactly as
`drift-engine who` finds it, by `who.lookup_operation`: `collect_window` over the
operation's start/end +/- 1 s, `investigation.group_operations`, and exactly one
group equal in operation name, start, end, outcome, relations, caller type and
client application. The investigation already applied G8, so no settling margin is
added here.

A drift without a decisive operation (e.g. verdict `ambiguous`: several capable
operations) has no single caller: its value stays `Unknown` (`no_decisive_operation`),
and `operations` lists each of the resource's operations with its own recorded caller
and status, found by the same `who.lookup_operation`, as `drift-engine who` lists them.

The value is the one caller Azure recorded, or `Unknown` when it cannot be
determined reliably. `status` says why, as a fixed code:
`matched`, `no_investigation`, `no_decisive_operation`, `caller_missing`,
`caller_inconsistent`, `address_unknown`, `invalid_resource_id`, `local_only`,
`resource_ids_unavailable` (no usable `DASHBOARD_TERRAFORM_JSON`),
`activity_log_not_settled` (the investigation's evidence did not pass the G8 settling
margin, or the resource's verdict says `evidence_not_settled`: no lookup is made),
`azure_sign_in_unavailable` (no usable `az login` on the dashboard host: the Azure query
failed with `credential_unavailable` or `authentication_failed`), `azure_access_denied`
(`authorization_failed`: the signed-in identity may not read the Activity Log), plus
who.py's `no_match`, `multiple_matches`, `retention_exceeded` and `query_failed`.

Nothing here stores or logs a caller: the result lives only in the response.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime

from drift_engine import activity_logs as al
from drift_engine import investigation_public as pub
from drift_engine import who

logger = logging.getLogger(__name__)

UNKNOWN = "Unknown"
LABEL = "Caller recorded by Azure"


def _result(status: str, value: str = UNKNOWN, caller_type: str = "unknown") -> dict:
    return {"label": LABEL, "value": value, "caller_type": caller_type, "status": status}


SIGN_IN_CODES = ("credential_unavailable", "authentication_failed")
ACCESS_CODES = ("authorization_failed",)


class _RecordingSource:
    """Passes pages through and remembers the fixed failure code of every SourceError, so a failed
    lookup can say whether Azure sign-in or access was the cause. Codes only; never a message."""

    def __init__(self, source: al.ActivityLogSource) -> None:
        self.source, self.codes = source, []

    def pages(self, subscription_id: str, query_filter: str):
        try:
            yield from self.source.pages(subscription_id, query_filter)
        except al.SourceError as exc:
            self.codes.append(exc.code)
            raise


def _failure_status(codes: list[str]) -> str:
    if any(code in SIGN_IN_CODES for code in codes):
        return "azure_sign_in_unavailable"
    if any(code in ACCESS_CODES for code in codes):
        return "azure_access_denied"
    return "query_failed"


def _target(address: str, resource_ids: Mapping[str, str] | None,
             environ: Mapping[str, str]) -> al.ArmId | str:
    """The ARM ID to query for `address`, or the fixed code saying why there is none."""
    try:
        who.refuse_in_ci(environ)  # G12: caller lookups never run in GitHub Actions
    except who.WhoRefused:
        return "local_only"
    if resource_ids is None:
        return "resource_ids_unavailable"
    resource_id = resource_ids.get(address)
    if resource_id is None:
        return "address_unknown"
    arm = al.parse_resource_id(resource_id)
    if arm is None or arm.resource_group is None:
        return "invalid_resource_id"
    return arm


def recorded_caller(investigation: pub.PublicInvestigation | None, address: str,
                    resource_ids: Mapping[str, str] | None, source: al.ActivityLogSource, now: datetime,
                    environ: Mapping[str, str]) -> dict:
    """The recorded caller of the drift's decisive operation, or `Unknown` with a reason code.

    Without a decisive operation (e.g. verdict `ambiguous`) the drift has no single caller
    and stays `Unknown` (`no_decisive_operation`); `operations` then lists the recorded caller
    of each of the resource's operations, looked up one by one exactly as `drift-engine who`
    looks them up. None of them is presented as the drift's caller."""
    resource = None if investigation is None else next(
        (r for r in investigation.resources if r.address == address), None)
    if resource is None:
        return _result("no_investigation")
    settled = investigation.completeness is not None and investigation.completeness.settled
    if not settled or resource.reason == "evidence_not_settled":
        return _result("activity_log_not_settled")  # G8: never look up evidence that had not settled
    target = _target(address, resource_ids, environ)
    op = next((o for o in resource.operations if o.op_id == resource.decisive_operation), None)
    if op is not None:
        return _operation_caller(address, op, target, source, now)
    result = _result("no_decisive_operation")
    if resource.operations:
        result["operations"] = [
            {"op_id": o.op_id, "operation_name": o.operation_name, "start": o.start, "end": o.end, "role": o.role,
             **{k: v for k, v in _operation_caller(address, o, target, source, now).items() if k != "label"}}
            for o in resource.operations]
    return result


def _operation_caller(address: str, op: pub.Operation, target: al.ArmId | str, source: al.ActivityLogSource,
                      now: datetime) -> dict:
    """The recorded caller of one public operation via `who.lookup_operation`, or `Unknown`."""
    if op.caller_status != "recorded":
        return _result(f"caller_{op.caller_status}", caller_type=op.caller_type)
    if isinstance(target, str):
        return _result(target, caller_type=op.caller_type)
    recording = _RecordingSource(source)
    try:
        found = who.lookup_operation(address, target, op, recording, now)
    except Exception:  # noqa: BLE001  (any lookup failure is Unknown, never a crash; nothing is logged)
        return _result(_failure_status(recording.codes), caller_type=op.caller_type)
    if found["status"] == "query_failed":
        return _result(_failure_status(recording.codes), caller_type=op.caller_type)
    if found["status"] != "matched":
        return _result(found["status"], caller_type=op.caller_type)
    if len(found["callers"]) != 1:
        return _result("caller_inconsistent" if found["callers"] else "caller_missing", caller_type=op.caller_type)
    return _result("matched", found["callers"][0], op.caller_type)
