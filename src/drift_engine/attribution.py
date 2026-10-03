"""Deterministic Activity Log attribution for drifted resources (Task 7.2).

Correlates a drift report (drift-engine analyze) with the Activity Log evidence of
the same run (activity_logs.py, Task 7.1) and writes a separate document,
`drift_attribution.json`. The drift report, its schema and the AI layer are not
changed: the AI report keeps `actor = "unknown"` / `confirmed = false`, and AI never
performs attribution.

What `confirmed` means, and nothing more:

    "Azure recorded caller X performing the successful delete of this exact
     resource under the correlation rules."

It never means that X caused the drift or made an out-of-band change. Only one
rule can confirm (`external_deletion_v1`); every other case is `unknown` with a
fixed reason code. Update, create and replace drift is always `unknown`
(`update_not_attributable`): Activity Log events carry no property diffs.

Matching (verified read-only against real Activity Log data, 2026-10-03):
  - resource identity: case-insensitive exact equality with the target's ARM ID;
    child, parent and sibling events never decide
  - operation: case-insensitive exact equality with `<namespace>/<types>/write` or
    `/delete` derived from the target's ID (a resource group:
    `Microsoft.Resources/subscriptions/resourceGroups/...`); category Administrative
  - operation group: (correlationId, operation name) on the exact resource; neither
    correlationId nor operationId alone is an operation key; an event without a
    correlationId is a group of its own
  - group outcome: successful = at least one Succeeded row (Succeeded-only groups and
    groups with an earlier Failed attempt included); failed = Failed/Canceled rows
    and no Succeeded row; unresolved = no terminal row. subStatus is never used
    (a 204 NoContent delete is a successful delete)
  - group interval: [earliest row, latest Succeeded row] ([earliest, latest row]
    without a Succeeded row)
  - detection window: T_start = run.started_at - 5 min, T_end = run.finished_at +
    5 min (skew); evidence is settled when window.settled_until >= T_end (Task 7.1's
    20-minute ingestion margin: a project margin, not an Azure SLA)

Per drifted resource, the first failing step decides (`decide` implements R0-R7):

  P1 binding    evidence subject (run_id, plan_timestamp) equals the report, and its
                targets are exactly the report's drifted addresses (document level)
  P2 report     the drift report is valid and succeeded (document level)
  P3 detection  run.started_at / finished_at known
  P4 evidence   evidence not failed; the target's scope was queried completely
  P5 settled    window.settled_until >= T_end
  R0            drift action is delete, else update_not_attributable
  R1            lifecycle groups (successful or unresolved, start <= T_end) do not
                overlap or touch, else order_ambiguous
  R2            there is one, else no_deletion_event; the last one is a delete, else
                latest_operation_is_write
  R3            existence anchor A: the latest successful write; none ->
                no_existence_anchor. It only proves the resource existed then.
  R4            after the anchor: exactly one successful delete (the candidate),
                else multiple_successful_deletes; no unresolved group, else
                unresolved_operation
  R5            every candidate row has a caller (caller_missing) and they are one
                caller (caller_inconsistent)
  R6            the candidate ends before T_start, else concurrent_with_detection
  R7            no Policy/Autoscale event on the exact resource within the candidate
                interval +/- 5 min, else automated_activity_overlap

Anchor B (a trusted prior detection run) is reserved in the rules but has no
input yet: rules_version 1 accepts only write-event anchors.

Fallback (Task 7.3): `origin_statement` is the single display mapping. A drifted
resource shows the claim above only when confirmed; every other case (any unknown
reason, a failed document, a missing document or address) shows "Change origin
could not be confirmed". No `caller_identity` field exists and the drift report is
not changed.

Pure and deterministic: standard library and pydantic only, no Azure SDK, no
network, no clock. Identical inputs give byte-identical output regardless of event
order. Callers are untrusted text copied verbatim from validated evidence; they are
never logged. Logs carry counts, statuses and reason codes only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from drift_engine.activity_logs import (
    INGESTION_LAG,
    ActivityLogEvidence,
    ArmId,
    Caller,
    Event,
    TargetResourceId,
    Timestamp,
    Token,
    format_timestamp,
    parse_resource_id,
    parse_timestamp,
)
from drift_engine.logs import log_event
from drift_engine.models import Action, DriftReport

logger = logging.getLogger(__name__)

ATTRIBUTION_VERSION = "1"
RULES_VERSION = "1"
ATTRIBUTION_FILE = "drift_attribution.json"
RULE = "external_deletion_v1"
CLAIM = "recorded_successful_delete"
CLAIM_TEMPLATE = (
    "Azure recorded caller {caller} performing the successful delete of this exact resource "
    "under the correlation rules."
)
# Task 7.3 fallback: the display statement for every drifted resource whose origin
# is not confirmed. A rendering, never a stored identity value.
UNCONFIRMED_ORIGIN = "Change origin could not be confirmed"

SKEW = timedelta(minutes=5)
SETTLE_MARGIN = INGESTION_LAG  # 20 minutes (Task 7.1); a project margin, not an Azure SLA
SKEW_MINUTES = int(SKEW / timedelta(minutes=1))
SETTLE_MARGIN_MINUTES = int(SETTLE_MARGIN / timedelta(minutes=1))
MAX_INPUT_BYTES = 50 * 1024 * 1024

SUCCEEDED = "Succeeded"
TERMINAL_FAILURES = ("Failed", "Canceled")
LIFECYCLE_CATEGORY = "Administrative"
AUTOMATED_CATEGORIES = ("Policy", "Autoscale")

PRECONDITION_REASONS = (
    "evidence_mismatch",
    "evidence_failed",
    "evidence_incomplete",
    "evidence_not_settled",
    "detection_time_unknown",
    "no_resource_id",
    "invalid_resource_id",
    "unsupported_scope",
)
RULE_REASONS = (
    "update_not_attributable",
    "no_deletion_event",
    "order_ambiguous",
    "latest_operation_is_write",
    "no_existence_anchor",
    "multiple_successful_deletes",
    "unresolved_operation",
    "caller_missing",
    "caller_inconsistent",
    "concurrent_with_detection",
    "automated_activity_overlap",
)
REASONS = PRECONDITION_REASONS + RULE_REASONS
FAILURE_REASONS = {
    "input": ("report_invalid", "evidence_invalid", "report_failed"),
    "binding": ("evidence_mismatch",),
    "evidence": ("evidence_failed",),
}
# Reasons that make a non-failed document `incomplete`: the resource could not be
# evaluated against complete, settled, bound evidence.
INCOMPLETE_REASONS = tuple(r for r in PRECONDITION_REASONS if r != "evidence_mismatch")
_NULL_ID_REASONS = ("no_resource_id", "invalid_resource_id", "evidence_mismatch", "evidence_failed")
_TARGET_STATUS_REASON = {
    "query_incomplete": "evidence_incomplete",
    "query_failed": "evidence_failed",
    "no_resource_id": "no_resource_id",
    "invalid_resource_id": "invalid_resource_id",
    "unsupported_scope": "unsupported_scope",
}

Reason = Literal[REASONS]


# ---------------------------------------------------------------------------
# Output contract (strict, frozen, unknown fields rejected)
# ---------------------------------------------------------------------------

class _Model(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


def _sorted_unique(ids: list[str]) -> bool:
    return ids == sorted(set(ids))


class Anchor(_Model):
    """Existence anchor A: the successful exact-resource write group before the
    candidate delete. `time` is its latest Succeeded row. It proves only that the
    resource existed at that time."""

    kind: Literal["write_event"]  # "prior_detection_run" (Anchor B) is not accepted in rules_version 1
    event_ids: Annotated[list[Token], Field(min_length=1)]
    run_id: None  # reserved for Anchor B
    time: Timestamp

    @model_validator(mode="after")
    def _consistent(self) -> Anchor:
        if not _sorted_unique(self.event_ids):
            raise ValueError("anchor event_ids must be sorted and unique")
        return self


class Attribution(_Model):
    status: Literal["confirmed", "unknown"]
    reason: Reason | None
    rule: Literal["external_deletion_v1"] | None
    claim: Literal["recorded_successful_delete"] | None
    caller: Caller | None
    anchor: Anchor | None
    decisive_event_ids: list[Token]
    candidate_event_ids: list[Token]
    related_event_ids: list[Token]
    after_detection_event_ids: list[Token]

    @model_validator(mode="after")
    def _consistent(self) -> Attribution:
        lists = {
            "decisive_event_ids": self.decisive_event_ids,
            "candidate_event_ids": self.candidate_event_ids,
            "related_event_ids": self.related_event_ids,
            "after_detection_event_ids": self.after_detection_event_ids,
        }
        problems = [f"{name} must be sorted and unique" for name, ids in lists.items() if not _sorted_unique(ids)]
        every = [i for ids in lists.values() for i in ids] + (self.anchor.event_ids if self.anchor else [])
        if len(every) != len(set(every)):
            problems.append("an event id appears in more than one list")
        if self.status == "confirmed":
            if self.reason is not None:
                problems.append("a confirmed attribution has no reason")
            if None in (self.rule, self.claim, self.caller, self.anchor):
                problems.append("a confirmed attribution needs rule, claim, caller and anchor")
            if not self.decisive_event_ids:
                problems.append("a confirmed attribution needs decisive events")
        else:
            if self.reason is None:
                problems.append("an unknown attribution needs a reason")
            if any(v is not None for v in (self.rule, self.claim, self.caller, self.anchor)) or self.decisive_event_ids:
                problems.append("an unknown attribution has no rule, claim, caller, anchor or decisive events")
            if self.reason in PRECONDITION_REASONS and any(lists.values()):
                problems.append("a resource that failed a precondition lists no events")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class ResourceAttribution(_Model):
    address: Annotated[str, Field(min_length=1)]
    drift_action: Action
    resource_id: TargetResourceId | None
    attribution: Attribution

    @model_validator(mode="after")
    def _consistent(self) -> ResourceAttribution:
        reason = self.attribution.reason
        problems = []
        if self.drift_action != "delete":
            if self.attribution.status == "confirmed":
                problems.append("only a deletion can be confirmed")
            elif reason not in PRECONDITION_REASONS + ("update_not_attributable",):
                problems.append("a non-delete drift is unknown with update_not_attributable or a precondition reason")
        elif reason == "update_not_attributable":
            problems.append("update_not_attributable is not a reason for a deletion")
        if self.resource_id is None and reason not in _NULL_ID_REASONS:
            problems.append("resource_id is null only for no_resource_id, invalid_resource_id, evidence_mismatch "
                            "or evidence_failed")
        if self.resource_id is not None and reason in ("no_resource_id", "invalid_resource_id", "evidence_mismatch"):
            problems.append(f"{reason} has no resource_id")
        if self.attribution.status == "confirmed":
            arm = parse_resource_id(self.resource_id)
            if arm is None or arm.resource_group is None:
                problems.append("a confirmed attribution needs a resource-group-scoped resource_id")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class EvidenceWindow(_Model):
    start: Timestamp
    end: Timestamp
    settled_until: Timestamp


class Binding(_Model):
    """What this attribution was computed from. `evidence_sha256` is the hash of the
    exact evidence bytes read."""

    run_id: str | None
    plan_timestamp: str | None
    evidence_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None
    evidence_outcome: Literal["complete", "incomplete", "failed"] | None
    window: EvidenceWindow | None
    settle_margin_minutes: Literal[SETTLE_MARGIN_MINUTES]
    skew_minutes: Literal[SKEW_MINUTES]


class Failure(_Model):
    stage: Literal["input", "binding", "evidence"]
    reason: Literal[sum(FAILURE_REASONS.values(), ())]

    @model_validator(mode="after")
    def _stage_reason(self) -> Failure:
        if self.reason not in FAILURE_REASONS[self.stage]:
            raise ValueError(f"{self.reason} is not a {self.stage} failure")
        return self


class DriftAttribution(_Model):
    """The whole `drift_attribution.json` document (attribution_version 1)."""

    attribution_version: Literal["1"]
    rules_version: Literal["1"]
    outcome: Literal["complete", "incomplete", "failed"]
    failure: Failure | None
    binding: Binding
    resources: list[ResourceAttribution]

    @model_validator(mode="after")
    def _invariants(self) -> DriftAttribution:
        problems = []
        addresses = [r.address for r in self.resources]
        if addresses != sorted(set(addresses)):
            problems.append("resources must be sorted by address, without repeats")
        reasons = [r.attribution.reason for r in self.resources]
        if (self.outcome == "failed") != (self.failure is not None):
            problems.append("failure is set exactly when the outcome is failed")
        if self.failure is not None:
            if self.failure.stage == "input" and self.resources:
                problems.append("an input failure lists no resources")
            if self.failure.stage == "binding" and any(r != "evidence_mismatch" for r in reasons):
                problems.append("a binding failure makes every resource evidence_mismatch")
            if self.failure.stage == "evidence" and any(r != "evidence_failed" for r in reasons):
                problems.append("an evidence failure makes every resource evidence_failed")
            if self.failure.stage != "input" and self.binding.evidence_sha256 is None:
                problems.append("evidence_sha256 is required once the evidence was read")
        else:
            if "evidence_mismatch" in reasons:
                problems.append("evidence_mismatch is a document failure")
            if self.binding.evidence_sha256 is None or self.binding.window is None:
                problems.append("evidence_sha256 and window are required")
            if self.binding.evidence_outcome in (None, "failed"):
                problems.append("evidence_outcome must be complete or incomplete")
            expected = "incomplete" if any(r in INCOMPLETE_REASONS for r in reasons) else "complete"
            if self.outcome != expected:
                problems.append(f"outcome must be {expected}")
        if problems:
            raise ValueError("; ".join(problems))
        return self


def render_attribution(document: DriftAttribution) -> str:
    """Sorted keys, two-space indent, ASCII, trailing newline: byte-stable."""
    return json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def render_claim(resource: ResourceAttribution) -> str | None:
    """The only sentence a confirmed attribution may be shown as; None when unknown."""
    if resource.attribution.status != "confirmed":
        return None
    return CLAIM_TEMPLATE.format(caller=resource.attribution.caller)


def origin_statement(document: DriftAttribution | None, address: str) -> str:
    """How the change origin of a drifted resource may be displayed (Task 7.3).

    The confirmed-claim template only when `document` is a non-failed attribution
    that lists `address` as confirmed; otherwise, always UNCONFIRMED_ORIGIN: any
    `unknown` reason (missing, expired, empty, unsettled, incomplete or ambiguous
    Activity Log evidence), a failed document (invalid, mismatched or failed
    evidence or report), an address it does not list, or no document at all.
    Display text only: the machine-readable `status`, `reason` and `caller` (null
    unless confirmed) stay in the document unchanged.
    """
    if document is None or document.failure is not None:
        return UNCONFIRMED_ORIGIN
    resource = next((r for r in document.resources if r.address == address), None)
    claim = render_claim(resource) if resource is not None else None
    return claim if claim is not None else UNCONFIRMED_ORIGIN


# ---------------------------------------------------------------------------
# Correlation rules (R0-R7)
# ---------------------------------------------------------------------------

def lifecycle_operations(arm: ArmId) -> tuple[str, str]:
    """(write, delete) operation names for the resource, lower case.

    `<namespace>/<type>[/<child type>...]` after the last `providers` segment; a
    resource group is `microsoft.resources/subscriptions/resourcegroups`.
    """
    parts = arm.text.split("/")
    lowered = [p.lower() for p in parts]
    if "providers" not in lowered:
        base = "microsoft.resources/subscriptions/resourcegroups"
    else:
        last = len(lowered) - 1 - lowered[::-1].index("providers")
        rest = lowered[last + 1:]
        base = "/".join([rest[0]] + rest[1::2])
    return f"{base}/write", f"{base}/delete"


@dataclass(frozen=True)
class _Group:
    kind: str  # "write" | "delete"
    outcome: str  # "successful" | "failed" | "unresolved"
    start: datetime
    end: datetime
    ids: tuple[str, ...]
    callers: tuple[str | None, ...]


def _event_time(event: Event) -> datetime:
    return parse_timestamp(event.event_timestamp)


def _same_resource(event: Event, arm: ArmId) -> bool:
    target = parse_resource_id(event.resource_id)
    return target is not None and target.key == arm.key


def _groups(events: Iterable[Event], arm: ArmId) -> tuple[list[_Group], list[Event]]:
    """Exact-resource Administrative write/delete operation groups (sorted), and every
    other event."""
    write_op, delete_op = lifecycle_operations(arm)
    buckets: dict[tuple, list[Event]] = {}
    other: list[Event] = []
    for event in events:
        operation = event.operation_name.lower()
        if (event.category != LIFECYCLE_CATEGORY or operation not in (write_op, delete_op)
                or not _same_resource(event, arm)):
            other.append(event)
            continue
        key = ("correlation", event.correlation_id) if event.correlation_id is not None else ("event", event.event_data_id)
        buckets.setdefault((key, operation), []).append(event)
    groups = []
    for (_, operation), rows in buckets.items():
        rows.sort(key=lambda e: (_event_time(e), e.event_data_id))
        times = [_event_time(e) for e in rows]
        succeeded = [t for e, t in zip(rows, times) if e.status == SUCCEEDED]
        if succeeded:
            outcome = "successful"
        elif any(e.status in TERMINAL_FAILURES for e in rows):
            outcome = "failed"
        else:
            outcome = "unresolved"
        groups.append(_Group(
            kind="write" if operation == write_op else "delete",
            outcome=outcome,
            start=min(times),
            end=max(succeeded) if succeeded else max(times),
            ids=tuple(e.event_data_id for e in rows),
            callers=tuple(e.caller for e in rows),
        ))
    groups.sort(key=lambda g: (g.start, g.end, g.ids))
    return groups, other


def _ids(groups: Iterable[_Group]) -> list[str]:
    return [i for g in groups for i in g.ids]


def decide(drift_action: str, arm: ArmId, events: Iterable[Event],
           run_started: datetime, run_finished: datetime) -> dict:
    """R0-R7 for one drifted resource whose preconditions passed (P1-P5).

    `events` are the evidence events matched to the resource's address, in any
    order. Returns the attribution as a plain dict (see `Attribution`).
    """
    t_start, t_end = run_started - SKEW, run_finished + SKEW
    groups, other = _groups(events, arm)
    lifecycle = [g for g in groups if g.outcome != "failed" and g.start <= t_end]
    failed = [g for g in groups if g.outcome == "failed" and g.start <= t_end]
    after = [g for g in groups if g.start > t_end]
    related = _ids(failed) + [e.event_data_id for e in other]

    def unknown(reason: str) -> dict:
        return _attribution("unknown", reason, candidate=_ids(lifecycle), related=related, after=_ids(after))

    if drift_action != "delete":
        return unknown("update_not_attributable")
    for earlier, later in zip(lifecycle, lifecycle[1:]):
        if earlier.end >= later.start:
            return unknown("order_ambiguous")
    if not lifecycle:
        return unknown("no_deletion_event")
    if lifecycle[-1].kind == "write":
        return unknown("latest_operation_is_write")
    anchors = [i for i, g in enumerate(lifecycle) if g.kind == "write" and g.outcome == "successful"]
    if not anchors:
        return unknown("no_existence_anchor")
    anchor = lifecycle[anchors[-1]]
    since_anchor = lifecycle[anchors[-1] + 1:]
    deletes = [g for g in since_anchor if g.kind == "delete" and g.outcome == "successful"]
    if len(deletes) > 1:
        return unknown("multiple_successful_deletes")
    if any(g.outcome == "unresolved" for g in since_anchor):
        return unknown("unresolved_operation")
    candidate = deletes[0]
    if any(caller is None for caller in candidate.callers):
        return unknown("caller_missing")
    if len(set(candidate.callers)) != 1:
        return unknown("caller_inconsistent")
    if not candidate.end < t_start:
        return unknown("concurrent_with_detection")
    low, high = candidate.start - SKEW, candidate.end + SKEW
    for event in other:
        if (event.category in AUTOMATED_CATEGORIES and _same_resource(event, arm)
                and low <= _event_time(event) <= high):
            return unknown("automated_activity_overlap")
    return _attribution(
        "confirmed", None,
        candidate=[i for i in _ids(lifecycle) if i not in candidate.ids and i not in anchor.ids],
        related=related, after=_ids(after),
        caller=candidate.callers[0], decisive=list(candidate.ids),
        anchor={"kind": "write_event", "event_ids": sorted(anchor.ids), "run_id": None,
                "time": format_timestamp(anchor.end)},
    )


def _attribution(status: str, reason: str | None, *, candidate: list[str] = (), related: list[str] = (),
                 after: list[str] = (), caller: str | None = None, decisive: list[str] = (),
                 anchor: dict | None = None) -> dict:
    confirmed = status == "confirmed"
    return {
        "status": status,
        "reason": reason,
        "rule": RULE if confirmed else None,
        "claim": CLAIM if confirmed else None,
        "caller": caller,
        "anchor": anchor,
        "decisive_event_ids": sorted(set(decisive)),
        "candidate_event_ids": sorted(set(candidate)),
        "related_event_ids": sorted(set(related)),
        "after_detection_event_ids": sorted(set(after)),
    }


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict:
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate JSON key")
    return dict(pairs)


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-standard JSON constant {name}")


def _json(data: bytes) -> Any:
    return json.loads(data.decode("utf-8"), object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant)


def _load_report(data: bytes | None) -> dict | None:
    if data is None:
        return None
    try:
        return DriftReport.model_validate(_json(data)).model_dump(mode="json")
    except (ValueError, ValidationError, RecursionError):
        return None


def _load_evidence(data: bytes | None) -> ActivityLogEvidence | None:
    if data is None:
        return None
    try:
        return ActivityLogEvidence.model_validate(_json(data))
    except (ValueError, ValidationError, RecursionError):
        return None


def _drifted(report: dict) -> list[dict]:
    return sorted((r for r in report["resources"] if r["drift_actions"] is not None), key=lambda r: r["address"])


def _resource(item: dict, resource_id: str | None, attribution: dict) -> dict:
    return {"address": item["address"], "drift_action": item["drift_action"], "resource_id": resource_id,
            "attribution": attribution}


def attribute(report_bytes: bytes | None, evidence_bytes: bytes | None) -> DriftAttribution:
    """Attribute the drifted resources of a drift report from Activity Log evidence.

    Inputs are the exact bytes of the drift report (JSON, as written by `drift-engine
    analyze`) and of `activity_log_evidence.json`; None means unreadable. Invalid,
    failed or mismatched input is recorded in the result, never raised.
    """
    report = _load_report(report_bytes)
    evidence = _load_evidence(evidence_bytes)
    run = (report or {}).get("run") or {}
    plan = (report or {}).get("plan") or {}
    binding = {
        "run_id": run.get("run_id"),
        "plan_timestamp": plan.get("timestamp"),
        "evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest() if evidence_bytes is not None else None,
        "evidence_outcome": evidence.outcome if evidence is not None else None,
        "window": ({k: getattr(evidence.window, k) for k in ("start", "end", "settled_until")}
                   if evidence is not None and evidence.window is not None else None),
        "settle_margin_minutes": SETTLE_MARGIN_MINUTES,
        "skew_minutes": SKEW_MINUTES,
    }

    def failed(stage: str, reason: str, resources: list[dict]) -> DriftAttribution:
        log_event(logger, logging.WARNING, "attribution_failed", "attribution not possible",
                  stage=stage, reason=reason, resources=len(resources))
        return DriftAttribution.model_validate({
            "attribution_version": ATTRIBUTION_VERSION, "rules_version": RULES_VERSION, "outcome": "failed",
            "failure": {"stage": stage, "reason": reason}, "binding": binding, "resources": resources,
        })

    if report is None:
        return failed("input", "report_invalid", [])
    if evidence is None:
        return failed("input", "evidence_invalid", [])
    if report["outcome"] != "succeeded":
        return failed("input", "report_failed", [])

    drifted = _drifted(report)
    subject = evidence.subject
    if (binding["run_id"] is None or binding["plan_timestamp"] is None
            or subject.run_id != binding["run_id"] or subject.plan_timestamp != binding["plan_timestamp"]):
        return failed("binding", "evidence_mismatch",
                      [_resource(r, None, _attribution("unknown", "evidence_mismatch")) for r in drifted])
    targets = {t.address: t for t in evidence.targets}
    if evidence.outcome == "failed":
        return failed("evidence", "evidence_failed",
                      [_resource(r, targets[r["address"]].resource_id if r["address"] in targets else None,
                                 _attribution("unknown", "evidence_failed")) for r in drifted])
    if set(targets) != {r["address"] for r in drifted}:
        return failed("binding", "evidence_mismatch",
                      [_resource(r, None, _attribution("unknown", "evidence_mismatch")) for r in drifted])

    started = parse_timestamp(run.get("started_at"))
    finished = parse_timestamp(run.get("finished_at"))
    detection_known = started is not None and finished is not None and started <= finished
    settled_until = parse_timestamp(evidence.window.settled_until)
    events_by_address: dict[str, list[Event]] = {}
    for event in evidence.events:
        for match in event.matches:
            events_by_address.setdefault(match.address, []).append(event)

    resources = []
    for item in drifted:
        target = targets[item["address"]]
        if not detection_known:
            attribution = _attribution("unknown", "detection_time_unknown")
        elif target.status != "queried":
            attribution = _attribution("unknown", _TARGET_STATUS_REASON[target.status])
        elif settled_until < finished + SKEW:
            attribution = _attribution("unknown", "evidence_not_settled")
        else:
            attribution = decide(item["drift_action"], parse_resource_id(target.resource_id),
                                 events_by_address.get(item["address"], []), started, finished)
        resources.append(_resource(item, target.resource_id, attribution))

    reasons = [r["attribution"]["reason"] for r in resources]
    outcome = "incomplete" if any(r in INCOMPLETE_REASONS for r in reasons) else "complete"
    document = DriftAttribution.model_validate({
        "attribution_version": ATTRIBUTION_VERSION, "rules_version": RULES_VERSION, "outcome": outcome,
        "failure": None, "binding": binding, "resources": resources,
    })
    log_event(logger, logging.INFO if outcome == "complete" else logging.WARNING, "attribution_finished",
              "attribution computed", outcome=outcome, resources=len(resources),
              confirmed=sum(1 for r in resources if r["attribution"]["status"] == "confirmed"),
              reasons=dict(sorted(Counter(r for r in reasons if r is not None).items())))
    return document


def _read(path: str) -> bytes | None:
    try:
        if os.path.getsize(path) > MAX_INPUT_BYTES:
            return None
        with open(path, "rb") as fh:
            data = fh.read(MAX_INPUT_BYTES + 1)
        return data if len(data) <= MAX_INPUT_BYTES else None
    except OSError:
        return None


def attribute_files(report_path: str, evidence_path: str) -> tuple[DriftAttribution, bytes | None]:
    """`attribute` on two files (unreadable or oversized files count as invalid).
    Also returns the evidence bytes, for `verify_against_evidence`."""
    evidence_bytes = _read(evidence_path)
    return attribute(_read(report_path), evidence_bytes), evidence_bytes


# ---------------------------------------------------------------------------
# Independent re-check against the evidence (defense in depth)
# ---------------------------------------------------------------------------

def verify_against_evidence(document: DriftAttribution, evidence_bytes: bytes | None) -> list[str]:
    """Re-check every reference of an attribution against the evidence it names.

    Independent of `decide`: the evidence hash and subject, every event id exists
    and is matched to the resource, and for each confirmation the decisive rows are
    one Administrative exact-resource delete group with a Succeeded row and only the
    confirmed caller, and the anchor rows are one successful exact-resource write group
    whose latest Succeeded row is `anchor.time` and precedes every decisive row.
    Returns the problems found (empty when consistent).
    """
    if document.failure is not None and document.failure.stage == "input":
        return []
    if evidence_bytes is None or hashlib.sha256(evidence_bytes).hexdigest() != document.binding.evidence_sha256:
        return ["evidence_sha256 does not match the evidence"]
    evidence = _load_evidence(evidence_bytes)
    if evidence is None:
        return ["the evidence does not satisfy its contract"]
    problems = []
    if (evidence.subject.run_id, evidence.subject.plan_timestamp) != (
            document.binding.run_id, document.binding.plan_timestamp) and document.failure is None:
        problems.append("binding does not match the evidence subject")
    events = {e.event_data_id: e for e in evidence.events}
    for resource in document.resources:
        attribution = resource.attribution
        referenced = (attribution.decisive_event_ids + attribution.candidate_event_ids
                      + attribution.related_event_ids + attribution.after_detection_event_ids
                      + (attribution.anchor.event_ids if attribution.anchor else []))
        for event_id in referenced:
            event = events.get(event_id)
            if event is None:
                problems.append(f"{resource.address}: event {event_id} is not in the evidence")
            elif resource.address not in {m.address for m in event.matches}:
                problems.append(f"{resource.address}: event {event_id} is not matched to this resource")
        if attribution.status != "confirmed" or any(i not in events for i in referenced):
            continue
        arm = parse_resource_id(resource.resource_id)
        write_op, delete_op = lifecycle_operations(arm)
        decisive = [events[i] for i in attribution.decisive_event_ids]
        anchor = [events[i] for i in attribution.anchor.event_ids]
        for rows, operation, name in ((decisive, delete_op, "decisive"), (anchor, write_op, "anchor")):
            if any(e.operation_name.lower() != operation or e.category != LIFECYCLE_CATEGORY
                   or not _same_resource(e, arm) for e in rows):
                problems.append(f"{resource.address}: {name} events are not exact-resource {operation} events")
            if len({e.correlation_id for e in rows}) != 1 or (rows[0].correlation_id is None and len(rows) > 1):
                problems.append(f"{resource.address}: {name} events are not one operation group")
            if not any(e.status == SUCCEEDED for e in rows):
                problems.append(f"{resource.address}: {name} group has no Succeeded row")
        if any(e.caller != attribution.caller for e in decisive):
            problems.append(f"{resource.address}: decisive events do not all carry the confirmed caller")
        anchor_time = max((_event_time(e) for e in anchor if e.status == SUCCEEDED), default=None)
        if anchor_time is None or format_timestamp(anchor_time) != attribution.anchor.time:
            problems.append(f"{resource.address}: anchor time is not its latest Succeeded row")
        elif not anchor_time < min(_event_time(e) for e in decisive):
            problems.append(f"{resource.address}: the anchor does not precede the decisive delete")
    return problems
