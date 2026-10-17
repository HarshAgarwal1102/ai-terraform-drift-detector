"""`Caller recorded by Azure`, looked up on demand (Phase 13 required feature, Task 13.1).

For a drifted resource, the drift's identified change is its decisive operation in
the bound public investigation (verdict `sole_capable_operation` or
`latest_capable_operation`). Its Activity Log record is found exactly as
`drift-engine who` finds it, by `who.lookup_operation`: `collect_window` over the
operation's start/end +/- 1 s, `investigation.group_operations`, and exactly one
group equal in operation name, start, end, outcome, relations, caller type and
client application. The investigation already applied G8, so no settling margin is
added here.

The value is the one caller Azure recorded, or `Unknown` when it cannot be
determined reliably. `status` says why, as a fixed code:
`matched`, `no_investigation`, `no_decisive_operation`, `caller_missing`,
`caller_inconsistent`, `address_unknown`, `invalid_resource_id`, `local_only`,
`resource_ids_unavailable` (no usable `DASHBOARD_TERRAFORM_JSON`), plus who.py's
`no_match`, `multiple_matches`, `retention_exceeded` and `query_failed`.

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


def recorded_caller(investigation: pub.PublicInvestigation | None, address: str,
                    resource_ids: Mapping[str, str] | None, source: al.ActivityLogSource, now: datetime,
                    environ: Mapping[str, str]) -> dict:
    """The recorded caller of the drift's decisive operation, or `Unknown` with a reason code."""
    resource = None if investigation is None else next(
        (r for r in investigation.resources if r.address == address), None)
    if resource is None:
        return _result("no_investigation")
    op = next((o for o in resource.operations if o.op_id == resource.decisive_operation), None)
    if op is None:
        return _result("no_decisive_operation")
    if op.caller_status != "recorded":
        return _result(f"caller_{op.caller_status}", caller_type=op.caller_type)
    try:
        who.refuse_in_ci(environ)  # G12: caller lookups never run in GitHub Actions
    except who.WhoRefused:
        return _result("local_only", caller_type=op.caller_type)
    if resource_ids is None:
        return _result("resource_ids_unavailable", caller_type=op.caller_type)
    resource_id = resource_ids.get(address)
    if resource_id is None:
        return _result("address_unknown", caller_type=op.caller_type)
    arm = al.parse_resource_id(resource_id)
    if arm is None or arm.resource_group is None:
        return _result("invalid_resource_id", caller_type=op.caller_type)
    try:
        found = who.lookup_operation(address, arm, op, source, now)
    except Exception:  # noqa: BLE001  (any lookup failure is Unknown, never a crash; nothing is logged)
        return _result("query_failed", caller_type=op.caller_type)
    if found["status"] != "matched":
        return _result(found["status"], caller_type=op.caller_type)
    if len(found["callers"]) != 1:
        return _result("caller_inconsistent" if found["callers"] else "caller_missing", caller_type=op.caller_type)
    return _result("matched", found["callers"][0], op.caller_type)
