"""Drift investigation: correlation v2 and the last-in-sync anchor (Task 9B.2).

Relates each drifted resource of a drift report to the Activity Log evidence of the
same run (activity_logs.py, evidence v2) and writes a restricted document,
`drift_investigation.restricted.json`. It holds recorded callers and ARM resource
IDs, so it never leaves the runner / the maintainer's machine; the public
projection is Task 9B.3. The drift report is never changed.

Three claims are kept apart (PROJECT_PLAN.md, Phase 9B, G3):

  1. recorded operations: Azure recorded operation O on this resource at T (each
     `operations[]` entry, with its recorded caller, caller type and client app);
  2. relationship to the drift: `verdict` (G4) and `property_link` (G5);
  3. actor attribution: `confirmed` only when the property link is confirmed.

`sole_capable_operation` / `latest_capable_operation` mean only that the operation
can explain every relevant drifted property area; never that the exact Terraform
property or value was proven. The Activity Log records no property values, so
update, create and replace drift is never property-confirmed. Only a deletion can
be (`external_deletion_v1`, rules version 2, attribution.py), and only under a
decisive verdict (`sole` / `latest`, Option A).

Capable operations (table v1, verified shapes only; G6). Only Administrative groups
count; a group is (correlationId, case-folded operation) over the target's `exact`
and `extension` rows:

  area                 capable operation
  tags                 Microsoft.Resources/tags/write (exact or tags extension);
                       the resource's lifecycle write
  other                the resource's lifecycle write
  existence_create     the resource's lifecycle write
  existence_delete     the resource's lifecycle delete

Relevant areas come from the drift report: `tags` / `other` from the first element
of every non-noise drifted path (an update without one is `other`),
`existence_delete` for deletion drift, `existence_create` for create drift, both for
replace drift. A table operation capable only for areas that did not drift is
`irrelevant` (listed, no effect); any other Administrative operation on the exact
resource or a verified extension is `unclassified`. Policy/Autoscale events attach
to a candidate group with the same correlationId, otherwise they are an
automated-activity signal.

Timing (G7, G8): observation = [run.started_at, run.finished_at] of the plan
evidence; `before_observation` ends before started_at - 60 s, `after_observation`
starts after finished_at + 60 s, otherwise `during_observation`. A group belongs to a
resource's window when its end is at or after the window start: the last-in-sync
anchor's started_at - 60 s (G9), else the lookback start. The first query runs at
finished_at + 10 min (M); while a queried drifted resource has no capable operation,
the evidence is collected again every 2 minutes up to finished_at + 20 min (C). With
no queryable target there is no wait and no Azure query.

Verdicts (G4), first match: a candidate during observation, an unresolved
candidate, an automated-activity signal -> `ambiguous`; no successful candidate ->
`no_capable_operation_found` (or `not_investigated` when the target's scope has
unreadable events); with an anchor exactly one capable group explaining every area
-> `sole_capable_operation`; without one the most recent, non-overlapping candidate
explaining every area -> `latest_capable_operation`; anything else `ambiguous`,
including unreadable events. Preconditions (detection time, target query status,
settledness, window coverage, binding) give `not_investigated`.

Anchor candidates (G9) are subdirectories of the given directory holding `run.json`
({id, run_attempt, repository, workflow_path, head_branch, event}) and
`drift_report.json` (a downloaded public artifact: the public drift report of Task
9B.4A; an internal-format report is `report_invalid`). Other entries are
`not_a_candidate`. Candidates are examined in directory-name order, at most 50; each
rejection is recorded with a fixed code.

Binding (Task 9B.4A): the investigation reads the internal drift report, but its
`binding.drift_report_sha256` is the canonical SHA-256 of that report's **public**
projection (report_public.py), so the public investigation binds to the public artifact
and no document carries a hash of the internal report.

Deterministic apart from the clock and the Azure source, both injected. Logs carry
counts and codes only, never a caller, resource ID or candidate content.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from drift_engine import activity_logs as al
from drift_engine import attribution as at
from drift_engine import investigation_public as pub
from drift_engine import report_public
from drift_engine.classifier import evaluate
from drift_engine.logs import log_event
from drift_engine.models import Action, DriftReport

logger = logging.getLogger(__name__)

# the canonical drift report hash (Task 9A.1), shared with the public document
canonical_sha256 = pub.canonical_sha256

INVESTIGATION_VERSION = "1"
TABLE_VERSION = "1"
INVESTIGATION_FILE = "drift_investigation.restricted.json"

SKEW = at.SKEW  # 60 s (G7)
SETTLE_MARGIN = at.SETTLE_MARGIN  # M = 10 min (G8)
POLL_INTERVAL = timedelta(minutes=2)
POLL_CAP = timedelta(minutes=20)  # C
POLL_INTERVAL_MINUTES = 2
POLL_CAP_MINUTES = 20
MAX_ANCHOR_CANDIDATES = 50
# Anchors must fit the collector's maximum window (89 days) with a day to spare.
ANCHOR_MAX_AGE = timedelta(days=al.MAX_LOOKBACK_DAYS - 1)
MAX_INPUT_BYTES = 50 * 1024 * 1024
WORKFLOW_PATH = ".github/workflows/drift-detection.yml"
ANCHOR_BRANCH = "main"
ANCHOR_EVENTS = ("schedule", "workflow_dispatch")
RUN_METADATA_FILE = "run.json"
ANCHOR_REPORT_FILE = "drift_report.json"

TAGS_WRITE = "microsoft.resources/tags/write"
DRIFT_CLASSES = ("drifted", "drifted_converged", "drifted_and_config_changed")
AREAS = ("existence_create", "existence_delete", "other", "tags")
LIFECYCLE_WRITE_AREAS = ("existence_create", "other", "tags")

VERDICTS = ("ambiguous", "latest_capable_operation", "no_capable_operation_found", "not_investigated",
            "sole_capable_operation")
DECISIVE_VERDICTS = ("latest_capable_operation", "sole_capable_operation")
AMBIGUOUS_REASONS = ("automated_activity", "during_observation", "multiple_capable_operations",
                     "partial_capability", "unclassified_operation", "unreadable_events_in_scope",
                     "unresolved_operation")
PRECONDITION_REASONS = ("detection_time_unknown", "evidence_failed", "evidence_incomplete", "evidence_mismatch",
                        "evidence_not_settled", "invalid_resource_id", "no_resource_id", "unsupported_scope")
NOT_INVESTIGATED_REASONS = PRECONDITION_REASONS + ("unreadable_events_in_scope",)
PROPERTY_LINK_REASONS = ("decisive_operation_mismatch", "deletion_rule_not_confirmed",
                         "no_property_values_in_activity_log", "verdict_not_decisive")
ANCHOR_REJECTIONS = ("candidate_limit", "environment_mismatch", "metadata_invalid", "not_a_candidate",
                     "not_earlier", "observation_unknown", "outside_retention", "plan_not_earlier",
                     "report_failed", "report_invalid", "run_binding_mismatch", "same_run", "wrong_branch",
                     "wrong_event", "wrong_repository", "wrong_workflow")
FAILURE_REASONS = {
    "input": ("anchor_directory_unreadable", "report_failed", "report_invalid", "report_mismatch"),
    "binding": ("evidence_mismatch",),
    "evidence": ("evidence_failed",),
}

Area = Literal[AREAS]
Verdict = Literal[VERDICTS]
Timing = Literal["after_observation", "before_observation", "during_observation"]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

_GITHUB_RUN_ID = re.compile(r"github-([0-9]+)-([0-9]+)")




# ---------------------------------------------------------------------------
# Output contract (strict, frozen, unknown fields rejected)
# ---------------------------------------------------------------------------

class _Model(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


def _sorted_unique(values: list) -> bool:
    return values == sorted(set(values))


class Rules(_Model):
    table_version: Literal["1"]
    deletion_rules_version: Literal["2"]
    skew_seconds: Literal[60]
    settle_margin_minutes: Literal[10]
    poll_interval_minutes: Literal[2]
    poll_cap_minutes: Literal[20]
    automated_overlap_minutes: Literal[5]
    lookback_days: Annotated[int, Field(ge=1, le=al.MAX_LOOKBACK_DAYS)]


class Observation(_Model):
    started_at: al.Timestamp
    finished_at: al.Timestamp


class Binding(_Model):
    run_id: str | None
    plan_timestamp: str | None
    drift_report_sha256: Sha256 | None
    evidence_sha256: Sha256 | None
    evidence_outcome: Literal["complete", "incomplete", "failed"] | None
    observation: Observation | None


class Completeness(_Model):
    not_before: al.Timestamp | None
    queried_at: al.Timestamp
    polls: Annotated[int, Field(ge=1)]
    settled: bool
    max_ingestion_delay_ms: al.Count | None


class AcceptedAnchor(_Model):
    candidate: Annotated[str, Field(min_length=1)]
    run_id: Annotated[str, Field(min_length=1)]
    plan_timestamp: Annotated[str, Field(min_length=1)]
    started_at: al.Timestamp
    finished_at: al.Timestamp
    report_sha256: Sha256


class RejectedAnchor(_Model):
    candidate: Annotated[str, Field(min_length=1)]
    reason: Literal[ANCHOR_REJECTIONS]


class AnchorCandidates(_Model):
    examined: Annotated[int, Field(ge=0, le=MAX_ANCHOR_CANDIDATES)]
    accepted: list[AcceptedAnchor]
    rejected: list[RejectedAnchor]

    @model_validator(mode="after")
    def _consistent(self) -> AnchorCandidates:
        names = [a.candidate for a in self.accepted] + [r.candidate for r in self.rejected]
        if len(names) != len(set(names)):
            raise ValueError("a candidate appears more than once")
        if [a.candidate for a in self.accepted] != sorted(a.candidate for a in self.accepted):
            raise ValueError("accepted anchors must be sorted by candidate")
        if [r.candidate for r in self.rejected] != sorted(r.candidate for r in self.rejected):
            raise ValueError("rejected anchors must be sorted by candidate")
        counted = len(self.accepted) + sum(1 for r in self.rejected
                                           if r.reason not in ("not_a_candidate", "candidate_limit"))
        if counted != self.examined:
            raise ValueError("examined must count the accepted and checked candidates")
        return self


class Window(_Model):
    kind: Literal["anchor", "lookback"]
    start: al.Timestamp
    anchor: Annotated[str, Field(min_length=1)] | None  # the accepted candidate

    @model_validator(mode="after")
    def _consistent(self) -> Window:
        if (self.kind == "anchor") != (self.anchor is not None):
            raise ValueError("an anchor window names its anchor, a lookback window none")
        return self


class Operation(_Model):
    """One Administrative operation group on the resource or a verified extension."""

    op_id: Annotated[str, Field(pattern=r"^op-[1-9][0-9]*$")]
    operation_name: al.OperationName
    correlation_id: al.Token | None
    event_ids: Annotated[list[al.Token], Field(min_length=1)]
    relations: Annotated[list[Literal["exact", "extension"]], Field(min_length=1)]
    outcome: Literal["successful", "failed", "unresolved"]
    start: al.Timestamp
    end: al.Timestamp
    available_at: al.Timestamp | None
    timing: Timing
    in_window: bool
    role: Literal["capable", "irrelevant", "unclassified"]
    capable_areas: list[Area]
    caller: al.Caller | None
    caller_status: Literal["recorded", "missing", "inconsistent"]
    caller_type: al.CallerType
    client_app: al.ClientApp
    pipeline_identity: bool | None
    attached_event_ids: list[al.Token]

    @model_validator(mode="after")
    def _consistent(self) -> Operation:
        problems = []
        for name in ("event_ids", "relations", "capable_areas", "attached_event_ids"):
            if not _sorted_unique(getattr(self, name)):
                problems.append(f"{name} must be sorted and unique")
        if set(self.event_ids) & set(self.attached_event_ids):
            problems.append("an attached event is not a row of the group")
        if al.parse_timestamp(self.start) > al.parse_timestamp(self.end):
            problems.append("start must not be after end")
        if (self.role == "unclassified") != (not self.capable_areas):
            problems.append("exactly an unclassified operation has no capable areas")
        if (self.caller_status == "recorded") != (self.caller is not None):
            problems.append("a caller is kept exactly when it is recorded")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class AutomatedEvent(_Model):
    """A Policy/Autoscale event on the resource or a verified extension that is not
    attached to a candidate group. `signal` makes the verdict ambiguous (G6)."""

    event_id: al.Token
    operation_name: al.OperationName
    category: Literal["Autoscale", "Policy"]
    event_timestamp: al.Timestamp
    timing: Timing
    in_window: bool
    signal: bool

    @model_validator(mode="after")
    def _consistent(self) -> AutomatedEvent:
        if self.signal != (self.in_window and self.timing != "after_observation"):
            raise ValueError("signal is exactly an in-window event that is not after observation")
        return self


class ActorAttribution(_Model):
    status: Literal["confirmed", "not_confirmed"]
    rule: Literal["external_deletion_v1"] | None
    claim: Literal["recorded_successful_delete"] | None
    caller: al.Caller | None

    @model_validator(mode="after")
    def _consistent(self) -> ActorAttribution:
        confirmed = self.status == "confirmed"
        if confirmed != all(v is not None for v in (self.rule, self.claim, self.caller)) or (
                not confirmed and any(v is not None for v in (self.rule, self.claim, self.caller))):
            raise ValueError("a confirmed attribution has rule, claim and caller; otherwise none")
        return self


def _capable(op: Operation) -> bool:
    return (op.role == "capable" and op.outcome == "successful" and op.in_window
            and op.timing != "after_observation")


class ResourceInvestigation(_Model):
    address: Annotated[str, Field(min_length=1)]
    drift_action: Action | None
    resource_id: al.TargetResourceId | None
    relevant_areas: Annotated[list[Area], Field(min_length=1)]
    window: Window | None
    verdict: Verdict
    reason: Literal[AMBIGUOUS_REASONS + PRECONDITION_REASONS] | None
    decisive_operation: str | None
    property_link: Literal["confirmed", "inferred_not_provable", "none"]
    property_link_reason: Literal[PROPERTY_LINK_REASONS] | None
    deletion_rule: at.Attribution | None
    actor_attribution: ActorAttribution
    unreadable_events_in_scope: bool
    operations: list[Operation]
    automated_events: list[AutomatedEvent]
    descendant_events: al.Count
    descendant_operations: dict[str, Annotated[int, Field(ge=1)]]

    @model_validator(mode="after")
    def _invariants(self) -> ResourceInvestigation:
        problems = _resource_problems(self)
        if problems:
            raise ValueError("; ".join(problems))
        return self


def _resource_problems(r: ResourceInvestigation) -> list[str]:
    problems: list[str] = []
    if not _sorted_unique(r.relevant_areas):
        problems.append("relevant_areas must be sorted and unique")
    if list(r.descendant_operations) != sorted(r.descendant_operations):
        problems.append("descendant_operations must be sorted")
    if sum(r.descendant_operations.values()) != r.descendant_events:
        problems.append("descendant_events must equal the descendant operation counts")
    ids = [op.op_id for op in r.operations]
    if ids != [f"op-{n}" for n in range(1, len(ids) + 1)]:
        problems.append("operations must be numbered op-1, op-2, ... in order")
    order = [(op.start, op.end, op.event_ids) for op in r.operations]
    if order != sorted(order):
        problems.append("operations must be sorted by start, end and event ids")
    every = [i for op in r.operations for i in op.event_ids + op.attached_event_ids] + [
        e.event_id for e in r.automated_events]
    if len(every) != len(set(every)):
        problems.append("an event id appears more than once")

    # verdict and reason
    if r.verdict in DECISIVE_VERDICTS + ("no_capable_operation_found",):
        if r.reason is not None:
            problems.append(f"{r.verdict} has no reason")
    elif r.verdict == "ambiguous" and r.reason not in AMBIGUOUS_REASONS:
        problems.append("an ambiguous verdict needs an ambiguity reason")
    elif r.verdict == "not_investigated" and r.reason not in NOT_INVESTIGATED_REASONS:
        problems.append("a not_investigated verdict needs a not-investigated reason")
    precondition = r.verdict == "not_investigated" and r.reason in PRECONDITION_REASONS
    if precondition and (r.window is not None or r.operations or r.automated_events or r.descendant_events
                         or r.deletion_rule is not None or r.unreadable_events_in_scope):
        problems.append("a resource that failed a precondition lists no window, operations or deletion rule")
    if not precondition and r.window is None:
        problems.append("an investigated resource has a window")
    if r.verdict == "sole_capable_operation" and (r.window is None or r.window.kind != "anchor"):
        problems.append("sole_capable_operation needs an anchor window")
    if r.verdict == "latest_capable_operation" and (r.window is None or r.window.kind != "lookback"):
        problems.append("latest_capable_operation needs a lookback window")
    if r.unreadable_events_in_scope and r.verdict in DECISIVE_VERDICTS + ("no_capable_operation_found",):
        problems.append("unreadable events in scope allow no sole, latest or none verdict")

    # decisive operation
    decisive = next((op for op in r.operations if op.op_id == r.decisive_operation), None)
    if (r.decisive_operation is not None) != (r.verdict in DECISIVE_VERDICTS):
        problems.append("a decisive operation exists exactly for sole / latest")
    elif r.decisive_operation is not None:
        if decisive is None:
            problems.append("the decisive operation is not listed")
        elif not (_capable(decisive) and decisive.timing == "before_observation"
                  and set(r.relevant_areas) <= set(decisive.capable_areas)):
            problems.append("the decisive operation must be a successful, in-window capable operation before "
                            "observation that explains every relevant area")

    # property link (G5, Option A) and actor attribution (G3)
    has_capable = any(_capable(op) for op in r.operations)
    if r.verdict == "no_capable_operation_found" and has_capable:
        problems.append("no_capable_operation_found lists no successful capable operation")
    if (r.property_link == "none") != (not has_capable):
        problems.append("property_link is none exactly when there is no successful capable operation")
    if (r.property_link_reason is None) != (r.property_link in ("confirmed", "none")):
        problems.append("property_link_reason is set exactly for inferred_not_provable")
    if r.drift_action != "delete" and r.deletion_rule is not None:
        problems.append("only a deletion is checked by the deletion rule")
    if r.property_link == "confirmed":
        rule = r.deletion_rule
        if r.drift_action != "delete":
            problems.append("only a deletion can be property-confirmed")
        if r.verdict not in DECISIVE_VERDICTS:
            problems.append("a confirmed property link needs a sole or latest verdict (Option A)")
        if rule is None or rule.status != "confirmed":
            problems.append("a confirmed property link needs a confirmed deletion rule")
        elif decisive is not None and decisive.event_ids != rule.decisive_event_ids:
            problems.append("the deletion rule and the verdict must decide on the same operation")
    actor = r.actor_attribution
    if (actor.status == "confirmed") != (r.property_link == "confirmed"):
        problems.append("actor attribution is confirmed exactly with a confirmed property link")
    if actor.status == "confirmed" and (r.deletion_rule is None or actor.caller != r.deletion_rule.caller):
        problems.append("a confirmed actor is the deletion rule's caller")
    return problems


class Failure(_Model):
    stage: Literal["input", "binding", "evidence"]
    reason: Literal[sum(FAILURE_REASONS.values(), ())]

    @model_validator(mode="after")
    def _stage_reason(self) -> Failure:
        if self.reason not in FAILURE_REASONS[self.stage]:
            raise ValueError(f"{self.reason} is not a {self.stage} failure")
        return self


class DriftInvestigation(_Model):
    """The whole `drift_investigation.restricted.json` (investigation_version 1).
    Restricted: it holds recorded callers and ARM resource IDs."""

    investigation_version: Literal["1"]
    trust: Literal["restricted"]
    rules: Rules
    outcome: Literal["complete", "incomplete", "failed"]
    failure: Failure | None
    binding: Binding
    completeness: Completeness | None
    anchor_candidates: AnchorCandidates
    resources: list[ResourceInvestigation]

    @model_validator(mode="after")
    def _invariants(self) -> DriftInvestigation:
        problems = []
        addresses = [r.address for r in self.resources]
        if addresses != sorted(set(addresses)):
            problems.append("resources must be sorted by address, without repeats")
        if (self.outcome == "failed") != (self.failure is not None):
            problems.append("failure is set exactly when the outcome is failed")
        reasons = [r.reason for r in self.resources]
        if self.failure is not None:
            if self.failure.stage == "input" and (self.resources or self.completeness is not None):
                problems.append("an input failure lists no resources and no completeness")
            if self.failure.stage == "binding" and any(r != "evidence_mismatch" for r in reasons):
                problems.append("a binding failure makes every resource evidence_mismatch")
            if self.failure.stage == "evidence" and any(r != "evidence_failed" for r in reasons):
                problems.append("an evidence failure makes every resource evidence_failed")
        else:
            if any(r == "evidence_mismatch" for r in reasons):
                problems.append("evidence_mismatch is a document failure")
            expected = ("incomplete" if any(r.verdict == "not_investigated" for r in self.resources)
                        else "complete")
            if self.outcome != expected:
                problems.append(f"outcome must be {expected}")
            if self.binding.drift_report_sha256 is None:
                problems.append("a non-failed investigation is bound to its drift report")
        if self.completeness is not None and self.binding.evidence_sha256 is None:
            problems.append("completeness needs bound evidence")
        if problems:
            raise ValueError("; ".join(problems))
        return self


def render_investigation(document: DriftInvestigation) -> str:
    """Sorted keys, two-space indent, ASCII, trailing newline: byte-stable."""
    return json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def _read(path: str) -> bytes | None:
    try:
        if os.path.getsize(path) > MAX_INPUT_BYTES:
            return None
        with open(path, "rb") as fh:
            data = fh.read(MAX_INPUT_BYTES + 1)
        return data if len(data) <= MAX_INPUT_BYTES else None
    except OSError:
        return None


def _load_report_json(data: bytes | None, model: type[DriftReport] = DriftReport) -> dict | None:
    """The parsed JSON of a contract-valid drift report (strict JSON), else None. `model` is the internal
    contract for this run's report, the public contract for anchor candidates (Task 9B.4A)."""
    if data is None:
        return None
    try:
        raw = at._json(data)
        model.model_validate(raw)
    except (ValueError, ValidationError, RecursionError, UnicodeDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


class RunMetadata(_Model):
    id: Annotated[int, Field(ge=1)]
    run_attempt: Annotated[int, Field(ge=1)]
    repository: Annotated[str, Field(min_length=1, max_length=200)]
    workflow_path: Annotated[str, Field(min_length=1, max_length=300)]
    head_branch: Annotated[str, Field(min_length=1, max_length=300)]
    event: Annotated[str, Field(min_length=1, max_length=100)]


@dataclass(frozen=True)
class AnchorRun:
    candidate: str
    run_id: str
    plan_timestamp: str
    started: datetime
    finished: datetime
    report_sha256: str
    in_sync: frozenset[str]

    def doc(self) -> dict:
        return {"candidate": self.candidate, "run_id": self.run_id, "plan_timestamp": self.plan_timestamp,
                "started_at": al.format_timestamp(self.started), "finished_at": al.format_timestamp(self.finished),
                "report_sha256": self.report_sha256}


@dataclass
class AnchorSelection:
    examined: int = 0
    accepted: list[AnchorRun] = field(default_factory=list)
    rejected: list[tuple[str, str]] = field(default_factory=list)

    def for_address(self, address: str) -> AnchorRun | None:
        """The latest accepted run that saw `address` in sync (G9)."""
        runs = [run for run in self.accepted if address in run.in_sync]
        return max(runs, key=lambda r: (r.finished, al.parse_timestamp(r.plan_timestamp), r.candidate),
                   default=None)

    def doc(self) -> dict:
        return {"examined": self.examined,
                "accepted": [run.doc() for run in sorted(self.accepted, key=lambda r: r.candidate)],
                "rejected": [{"candidate": name, "reason": reason} for name, reason in sorted(self.rejected)]}


def _current_workflow_run_id(run_id: Any) -> int | None:
    m = _GITHUB_RUN_ID.fullmatch(run_id) if isinstance(run_id, str) else None
    return int(m.group(1)) if m else None


def _check_candidate(path: str, report: dict, repository: str) -> AnchorRun | str:
    """An accepted anchor run, or the fixed rejection code of the first failed check."""
    data = _read(os.path.join(path, RUN_METADATA_FILE))
    try:
        metadata = RunMetadata.model_validate(at._json(data)) if data is not None else None
    except (ValueError, ValidationError, RecursionError, UnicodeDecodeError):
        metadata = None
    if metadata is None:
        return "metadata_invalid"
    if metadata.repository.casefold() != repository.casefold():
        return "wrong_repository"
    if metadata.workflow_path != WORKFLOW_PATH:
        return "wrong_workflow"
    if metadata.head_branch != ANCHOR_BRANCH:
        return "wrong_branch"
    if metadata.event not in ANCHOR_EVENTS:
        return "wrong_event"
    run = report.get("run") or {}
    if metadata.id == _current_workflow_run_id(run.get("run_id")):
        return "same_run"  # every attempt of the current run, including the current one
    # anchor candidates are public artifacts: the public drift report (Task 9B.4A); older internal-format
    # reports are report_invalid
    raw = _load_report_json(_read(os.path.join(path, ANCHOR_REPORT_FILE)), report_public.PublicDriftReport)
    if raw is None:
        return "report_invalid"
    if raw["outcome"] != "succeeded":
        return "report_failed"
    candidate_run = raw.get("run") or {}
    if candidate_run.get("run_id") != f"github-{metadata.id}-{metadata.run_attempt}":
        return "run_binding_mismatch"
    if candidate_run.get("environment") is None or candidate_run.get("environment") != run.get("environment"):
        return "environment_mismatch"
    started = al.parse_timestamp(candidate_run.get("started_at"))
    finished = al.parse_timestamp(candidate_run.get("finished_at"))
    if started is None or finished is None or started > finished:
        return "observation_unknown"
    current_started = al.parse_timestamp(run.get("started_at"))
    if current_started is None or not finished < current_started:
        return "not_earlier"
    plan_ts = (raw.get("plan") or {}).get("timestamp")
    current_plan = al.parse_timestamp((report.get("plan") or {}).get("timestamp"))
    if al.parse_timestamp(plan_ts) is None or current_plan is None or not al.parse_timestamp(plan_ts) < current_plan:
        return "plan_not_earlier"
    if started - SKEW < current_started - ANCHOR_MAX_AGE:
        return "outside_retention"
    in_sync = frozenset(r["address"] for r in raw["resources"] if r["classification"] == "in_sync")
    return AnchorRun(os.path.basename(path), candidate_run["run_id"], plan_ts, started, finished,
                     canonical_sha256(raw), in_sync)


def select_anchor_runs(directory: str, report: dict, repository: str) -> AnchorSelection:
    """Trust-check the anchor candidates in `directory` (G9). Raises OSError when the
    directory cannot be listed."""
    selection = AnchorSelection()
    candidates = []
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        if (os.path.isdir(path) and not os.path.islink(path)
                and os.path.isfile(os.path.join(path, RUN_METADATA_FILE))):
            candidates.append(name)
        else:
            selection.rejected.append((name, "not_a_candidate"))
    for name in candidates[MAX_ANCHOR_CANDIDATES:]:
        selection.rejected.append((name, "candidate_limit"))
    for name in candidates[:MAX_ANCHOR_CANDIDATES]:
        selection.examined += 1
        result = _check_candidate(os.path.join(directory, name), report, repository)
        if isinstance(result, str):
            selection.rejected.append((name, result))
        else:
            selection.accepted.append(result)
    return selection


# ---------------------------------------------------------------------------
# Correlation (G4-G7)
# ---------------------------------------------------------------------------

def relevant_areas(item: dict) -> list[str]:
    """The drifted property areas of a drift report resource (G6)."""
    action = item.get("drift_action")
    if action == "delete":
        return ["existence_delete"]
    if action == "create":
        return ["existence_create"]
    if action == "replace":
        return ["existence_create", "existence_delete"]
    areas = set()
    for change in item.get("attribute_changes") or []:
        if change.get("class") in DRIFT_CLASSES and (change.get("assessment") or {}).get("category") != "noise":
            areas.add("tags" if change["path"][0] == "tags" else "other")
    return sorted(areas) or ["other"]


def capable_areas(operation: str, relations: set[str], arm: al.ArmId) -> list[str]:
    """Capable-operations table v1 (G6): the areas an operation group can change."""
    write_op, delete_op = at.lifecycle_operations(arm)
    if operation == write_op and relations == {"exact"}:
        return list(LIFECYCLE_WRITE_AREAS)
    if operation == delete_op and relations == {"exact"}:
        return ["existence_delete"]
    if operation == TAGS_WRITE:
        return ["tags"]
    return []


def _timing(start: datetime, end: datetime, started: datetime, finished: datetime) -> str:
    if end < started - SKEW:
        return "before_observation"
    if start > finished + SKEW:
        return "after_observation"
    return "during_observation"


def _single(values: Iterable, unknown: Any) -> Any:
    distinct = set(values)
    return distinct.pop() if len(distinct) == 1 else unknown


@dataclass
class _Group:
    key: tuple
    rows: list = field(default_factory=list)
    relations: set = field(default_factory=set)


@dataclass(frozen=True)
class OperationGroup:
    """One Administrative operation group (correlationId, case-folded operation) over a
    target's exact and extension rows, summarised from its rows only. Shared by the
    investigation and the local WHO path (who.py), so both group identically."""

    operation: str  # case-folded group key
    operation_name: str  # as recorded (earliest row)
    correlation_id: str | None
    event_ids: tuple[str, ...]
    relations: tuple[str, ...]
    outcome: str
    start: datetime
    end: datetime
    available_at: datetime | None
    caller: str | None
    caller_status: str
    callers: tuple[str, ...]  # every distinct recorded caller
    caller_type: str
    client_app: str
    pipeline_identity: bool | None


def group_operations(rows: Iterable[tuple]) -> tuple[list[OperationGroup], list, Counter]:
    """(Administrative groups, other exact/extension events, descendant counts) from
    (event, relation) pairs of one address."""
    groups: dict[tuple, _Group] = {}
    other: list = []
    descendants: Counter = Counter()
    for event, relation in rows:
        if relation == "descendant":
            descendants[event.operation_name.lower()] += 1
        elif event.category == at.LIFECYCLE_CATEGORY:
            key = (("correlation", event.correlation_id) if event.correlation_id is not None
                   else ("event", event.event_data_id), event.operation_name.lower())
            group = groups.setdefault(key, _Group(key))
            group.rows.append(event)
            group.relations.add(relation)
        else:
            other.append(event)
    summaries = []
    for group in groups.values():
        group.rows.sort(key=lambda e: (al.parse_timestamp(e.event_timestamp), e.event_data_id))
        times = [al.parse_timestamp(e.event_timestamp) for e in group.rows]
        succeeded = [t for e, t in zip(group.rows, times) if e.status == at.SUCCEEDED]
        outcome = ("successful" if succeeded else
                   "failed" if any(e.status in at.TERMINAL_FAILURES for e in group.rows) else "unresolved")
        callers = [e.caller for e in group.rows]
        named = sorted({c for c in callers if c is not None})
        caller_status = "inconsistent" if len(named) > 1 else ("missing" if None in callers else "recorded")
        submissions = [al.parse_timestamp(e.submission_timestamp) for e in group.rows if e.submission_timestamp]
        summaries.append(OperationGroup(
            operation=group.key[1], operation_name=group.rows[0].operation_name,
            correlation_id=group.rows[0].correlation_id,
            event_ids=tuple(sorted(e.event_data_id for e in group.rows)),
            relations=tuple(sorted(group.relations)), outcome=outcome,
            start=min(times), end=max(succeeded) if succeeded else max(times),
            available_at=max(submissions) if submissions else None,
            caller=named[0] if caller_status == "recorded" else None, caller_status=caller_status,
            callers=tuple(named),
            caller_type=_single((e.caller_type for e in group.rows), "unknown"),
            client_app=_single((e.client_app for e in group.rows), "unknown"),
            pipeline_identity=_single((e.pipeline_identity for e in group.rows), None),
        ))
    return summaries, other, descendants


def _operations(rows: list[tuple], arm: al.ArmId, areas: list[str], window_start: datetime,
                started: datetime, finished: datetime) -> tuple[list[dict], list[dict], Counter]:
    """(operations, automated events, descendant counts) for one resource."""
    groups, automated, descendants = group_operations(rows)
    built = []
    for group in groups:
        start, end = group.start, group.end
        cap = capable_areas(group.operation, set(group.relations), arm)
        role = "unclassified" if not cap else ("capable" if set(cap) & set(areas) else "irrelevant")
        built.append({
            "group": group, "start_dt": start, "end_dt": end,
            "doc": {
                "operation_name": group.operation_name,
                "correlation_id": group.correlation_id,
                "event_ids": list(group.event_ids),
                "relations": list(group.relations),
                "outcome": group.outcome,
                "start": al.format_timestamp(start),
                "end": al.format_timestamp(end),
                "available_at": al.format_timestamp(group.available_at) if group.available_at else None,
                "timing": _timing(start, end, started, finished),
                "in_window": end >= window_start,
                "role": role,
                "capable_areas": sorted(cap),
                "caller": group.caller,
                "caller_status": group.caller_status,
                "caller_type": group.caller_type,
                "client_app": group.client_app,
                "pipeline_identity": group.pipeline_identity,
                "attached_event_ids": [],
            },
        })
    built.sort(key=lambda b: (b["doc"]["start"], b["doc"]["end"], b["doc"]["event_ids"]))
    for n, item in enumerate(built, 1):
        item["doc"]["op_id"] = f"op-{n}"

    candidates_by_correlation: dict[str, dict] = {}
    for item in built:
        doc = item["doc"]
        if (doc["role"] in ("capable", "unclassified") and doc["outcome"] != "failed"
                and doc["timing"] != "after_observation" and doc["in_window"] and doc["correlation_id"] is not None):
            candidates_by_correlation.setdefault(doc["correlation_id"], doc)
    automated_docs = []
    for event in sorted(automated, key=lambda e: (e.event_timestamp, e.event_data_id)):
        host = candidates_by_correlation.get(event.correlation_id) if event.correlation_id is not None else None
        if host is not None:
            host["attached_event_ids"] = sorted(host["attached_event_ids"] + [event.event_data_id])
            continue
        moment = al.parse_timestamp(event.event_timestamp)
        timing = _timing(moment, moment, started, finished)
        in_window = moment >= window_start
        automated_docs.append({"event_id": event.event_data_id, "operation_name": event.operation_name,
                               "category": event.category, "event_timestamp": event.event_timestamp,
                               "timing": timing, "in_window": in_window,
                               "signal": in_window and timing != "after_observation"})
    return built, automated_docs, descendants


def _verdict(built: list[dict], automated: list[dict], areas: list[str], anchored: bool,
             unreadable: bool) -> tuple[str, str | None, dict | None]:
    """(verdict, reason, decisive operation) per G4."""
    candidates = [b["doc"] for b in built
                  if b["doc"]["role"] in ("capable", "unclassified") and b["doc"]["outcome"] != "failed"
                  and b["doc"]["timing"] != "after_observation" and b["doc"]["in_window"]]
    ends = {b["doc"]["op_id"]: (b["start_dt"], b["end_dt"]) for b in built}
    if any(c["timing"] == "during_observation" for c in candidates):
        return "ambiguous", "during_observation", None
    if any(c["outcome"] == "unresolved" for c in candidates):
        return "ambiguous", "unresolved_operation", None
    if any(a["signal"] for a in automated):
        return "ambiguous", "automated_activity", None
    if not candidates:
        return ("not_investigated", "unreadable_events_in_scope", None) if unreadable else (
            "no_capable_operation_found", None, None)
    needed = set(areas)
    if anchored:
        if any(c["role"] == "unclassified" for c in candidates):
            return "ambiguous", "unclassified_operation", None
        capable = [c for c in candidates if c["role"] == "capable"]
        if len(capable) > 1:
            return "ambiguous", "multiple_capable_operations", None
        decisive, verdict = capable[0], "sole_capable_operation"
    else:
        decisive = max(candidates, key=lambda c: (ends[c["op_id"]][1], ends[c["op_id"]][0], c["event_ids"]))
        overlapping = [c for c in candidates
                       if c is not decisive and ends[c["op_id"]][1] >= ends[decisive["op_id"]][0]]
        if overlapping:
            capable_overlap = any(c["role"] == "capable" for c in overlapping)
            return "ambiguous", "multiple_capable_operations" if capable_overlap else "unclassified_operation", None
        if decisive["role"] == "unclassified":
            return "ambiguous", "unclassified_operation", None
        verdict = "latest_capable_operation"
    if not needed <= set(decisive["capable_areas"]):
        return "ambiguous", "partial_capability", None
    if unreadable:
        return "ambiguous", "unreadable_events_in_scope", None
    return verdict, None, decisive


def _not_investigated(item: dict, resource_id: str | None, reason: str) -> dict:
    return {"address": item["address"], "drift_action": item["drift_action"], "resource_id": resource_id,
            "relevant_areas": relevant_areas(item), "window": None, "verdict": "not_investigated",
            "reason": reason, "decisive_operation": None, "property_link": "none",
            "property_link_reason": None, "deletion_rule": None,
            "actor_attribution": {"status": "not_confirmed", "rule": None, "claim": None, "caller": None},
            "unreadable_events_in_scope": False, "operations": [], "automated_events": [],
            "descendant_events": 0, "descendant_operations": {}}


def correlate(report: dict, evidence: al.ActivityLogEvidence, anchors: AnchorSelection,
              lookback_days: int) -> tuple[dict | None, list[dict]]:
    """(failure, resource documents) for a drift report and its evidence."""
    drifted = at._drifted(report)
    run = report.get("run") or {}
    plan = report.get("plan") or {}
    subject = evidence.subject
    if (run.get("run_id") is None or plan.get("timestamp") is None or subject.run_id != run.get("run_id")
            or subject.plan_timestamp != plan.get("timestamp")):
        return ({"stage": "binding", "reason": "evidence_mismatch"},
                [_not_investigated(r, None, "evidence_mismatch") for r in drifted])
    targets = {t.address: t for t in evidence.targets}
    if evidence.outcome == "failed":
        return ({"stage": "evidence", "reason": "evidence_failed"},
                [_not_investigated(r, targets[r["address"]].resource_id if r["address"] in targets else None,
                                   "evidence_failed") for r in drifted])
    if set(targets) != {r["address"] for r in drifted}:
        return ({"stage": "binding", "reason": "evidence_mismatch"},
                [_not_investigated(r, None, "evidence_mismatch") for r in drifted])

    started = al.parse_timestamp(run.get("started_at"))
    finished = al.parse_timestamp(run.get("finished_at"))
    known = started is not None and finished is not None and started <= finished
    queried_at = al.parse_timestamp(evidence.collection.queried_at)
    evidence_start = al.parse_timestamp(evidence.window.start)
    lookback_start = al.parse_timestamp(evidence.window.end) - timedelta(days=lookback_days)
    unreadable_scopes = at.unreadable_scopes(evidence)
    by_address = {}
    for event in evidence.events:
        for match in event.matches:
            by_address.setdefault(match.address, []).append((event, match.relation))

    resources = []
    for item in drifted:
        target = targets[item["address"]]
        if not known:
            resources.append(_not_investigated(item, target.resource_id, "detection_time_unknown"))
            continue
        if target.status != "queried":
            resources.append(_not_investigated(item, target.resource_id, at._TARGET_STATUS_REASON[target.status]))
            continue
        if not at.settled(queried_at, finished):
            resources.append(_not_investigated(item, target.resource_id, "evidence_not_settled"))
            continue
        anchor = anchors.for_address(item["address"])
        window_start = anchor.started - SKEW if anchor is not None else lookback_start
        if window_start < evidence_start:
            resources.append(_not_investigated(item, target.resource_id, "evidence_incomplete"))
            continue
        arm = al.parse_resource_id(target.resource_id)
        areas = relevant_areas(item)
        unreadable = at.scope_key(target.resource_id) in unreadable_scopes
        rows = by_address.get(item["address"], [])
        built, automated, descendants = _operations(rows, arm, areas, window_start, started, finished)
        verdict, reason, decisive = _verdict(built, automated, areas, anchor is not None, unreadable)
        operations = [b["doc"] for b in built]

        deletion_rule = None
        if item["drift_action"] == "delete":
            if unreadable:
                deletion_rule = at._attribution("unknown", "unreadable_events_in_scope")
            else:
                prior = at.PriorAnchor(anchor.run_id, anchor.started, anchor.finished) if anchor else None
                deletion_rule = at.decide("delete", arm, [e for e, _ in rows], started, finished, prior)
        has_capable = any(op["role"] == "capable" and op["outcome"] == "successful" and op["in_window"]
                          and op["timing"] != "after_observation" for op in operations)
        link, link_reason = "none", None
        if has_capable:
            link, link_reason = "inferred_not_provable", "no_property_values_in_activity_log"
            if deletion_rule is not None:
                link_reason = "deletion_rule_not_confirmed"
                if deletion_rule["status"] == "confirmed":
                    if verdict not in DECISIVE_VERDICTS:
                        link_reason = "verdict_not_decisive"
                    elif decisive["event_ids"] != deletion_rule["decisive_event_ids"]:
                        link_reason = "decisive_operation_mismatch"
                    else:
                        link, link_reason = "confirmed", None
        confirmed = link == "confirmed"
        resources.append({
            "address": item["address"], "drift_action": item["drift_action"], "resource_id": target.resource_id,
            "relevant_areas": areas,
            "window": {"kind": "anchor" if anchor else "lookback", "start": al.format_timestamp(window_start),
                       "anchor": anchor.candidate if anchor else None},
            "verdict": verdict, "reason": reason,
            "decisive_operation": decisive["op_id"] if decisive else None,
            "property_link": link, "property_link_reason": link_reason,
            "deletion_rule": deletion_rule,
            "actor_attribution": {"status": "confirmed" if confirmed else "not_confirmed",
                                  "rule": at.RULE if confirmed else None, "claim": at.CLAIM if confirmed else None,
                                  "caller": deletion_rule["caller"] if confirmed else None},
            "unreadable_events_in_scope": unreadable,
            "operations": operations, "automated_events": automated,
            "descendant_events": sum(descendants.values()),
            "descendant_operations": dict(sorted(descendants.items())),
        })
    return None, resources


def _needs_poll(resources: list[dict]) -> bool:
    """A queried drifted resource still has no successful capable operation (G8)."""
    for r in resources:
        if r["verdict"] == "not_investigated" and r["reason"] in PRECONDITION_REASONS:
            continue
        if not any(op["role"] == "capable" and op["outcome"] == "successful" and op["in_window"]
                   and op["timing"] != "after_observation" for op in r["operations"]):
            return True
    return False


# ---------------------------------------------------------------------------
# Investigation (collection, settling, polling, document)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Result:
    document: DriftInvestigation
    evidence_bytes: bytes | None  # the rendered evidence the document is bound to


def _rules(lookback_days: int) -> dict:
    return {"table_version": TABLE_VERSION, "deletion_rules_version": at.RULES_VERSION,
            "skew_seconds": at.SKEW_SECONDS, "settle_margin_minutes": at.SETTLE_MARGIN_MINUTES,
            "poll_interval_minutes": POLL_INTERVAL_MINUTES, "poll_cap_minutes": POLL_CAP_MINUTES,
            "automated_overlap_minutes": at.AUTOMATED_OVERLAP_MINUTES, "lookback_days": lookback_days}


def investigate(
    plan_path: str,
    manifest_path: str,
    report_bytes: bytes | None,
    *,
    source: al.ActivityLogSource,
    clock: Callable[[], datetime],
    sleep: Callable[[float], None],
    anchors_dir: str | None = None,
    repository: str | None = None,
    pipeline_principal: str | None = None,
    lookback_days: int = al.DEFAULT_LOOKBACK_DAYS,
    limits: al.Limits = al.DEFAULT_LIMITS,
    monotonic: Callable[[], float] = time.monotonic,
) -> Result:
    """Investigate the drifted resources of one detection run.

    `report_bytes` must be the (internal) drift report `drift-engine analyze` wrote for the same
    plan and manifest (verified by canonical hash); the binding records its public projection's hash. Anchor candidates are read only
    when `anchors_dir` is given, which needs `repository` (owner/name). Bad input is
    recorded in the result, never raised.
    """
    if type(lookback_days) is not int or not 1 <= lookback_days <= al.MAX_LOOKBACK_DAYS:
        raise ValueError("lookback_days must be between 1 and 89")
    if anchors_dir is not None and not repository:
        raise ValueError("anchor candidates need the current repository")
    rules = _rules(lookback_days)
    empty_anchors = AnchorSelection().doc()
    binding = {"run_id": None, "plan_timestamp": None, "drift_report_sha256": None, "evidence_sha256": None,
               "evidence_outcome": None, "observation": None}

    def failed_input(reason: str, anchors: dict = empty_anchors) -> Result:
        log_event(logger, logging.WARNING, "investigation_failed", "investigation not possible",
                  stage="input", reason=reason)
        return Result(DriftInvestigation.model_validate({
            "investigation_version": INVESTIGATION_VERSION, "trust": "restricted", "rules": rules,
            "outcome": "failed", "failure": {"stage": "input", "reason": reason}, "binding": binding,
            "completeness": None, "anchor_candidates": anchors, "resources": []}), None)

    evaluation = evaluate(plan_path, manifest_path)
    try:
        # exactly what `drift-engine analyze` writes (cli.analyze)
        recomputed = DriftReport.model_validate(evaluation.report).model_dump(mode="json")
    except ValidationError:
        return failed_input("report_invalid")
    given = _load_report_json(report_bytes)
    if given is None:
        return failed_input("report_invalid")
    report_sha = canonical_sha256(given)
    run, plan = given.get("run") or {}, given.get("plan") or {}
    binding.update(run_id=run.get("run_id"), plan_timestamp=plan.get("timestamp"))
    if report_sha != canonical_sha256(recomputed):
        return failed_input("report_mismatch")
    try:
        # the public investigation binds to the public drift report (Task 9B.4A); the internal report's
        # hash is never written to any document
        public_text = report_public.publish_report(given, evaluation.plan or {})
    except report_public.PublicReportError:
        return failed_input("report_invalid")
    binding["drift_report_sha256"] = report_public.public_sha256(json.loads(public_text))
    if given["outcome"] != "succeeded":
        return failed_input("report_failed")
    started, finished = al.parse_timestamp(run.get("started_at")), al.parse_timestamp(run.get("finished_at"))
    known = started is not None and finished is not None and started <= finished
    if known:
        binding["observation"] = {"started_at": al.format_timestamp(started),
                                  "finished_at": al.format_timestamp(finished)}

    selection = AnchorSelection()
    if anchors_dir is not None:
        try:
            selection = select_anchor_runs(anchors_dir, given, repository)
        except OSError:
            return failed_input("anchor_directory_unreadable")

    drifted = at._drifted(given)
    queryable = [t for t in al.select_targets(evaluation) if t.status == "pending"]
    if drifted and not known:
        # nothing can be correlated without the detection time: no Azure query
        resources = [_not_investigated(r, None, "detection_time_unknown") for r in drifted]
        return _finish(rules, binding, None, selection, resources, None, None)

    not_before = finished + SETTLE_MARGIN if queryable else None
    polls = 0
    while True:
        now = clock()
        if not_before is not None and now < not_before:
            sleep((not_before - now).total_seconds())
            now = clock()
        window_start = _window_start(queryable, selection, now, lookback_days)
        evidence = al.collect_evidence(plan_path, manifest_path, source=source, queried_at=now,
                                       lookback_days=lookback_days, window_start=window_start,
                                       not_before=not_before, pipeline_principal=pipeline_principal,
                                       limits=limits, monotonic=monotonic)
        polls += 1
        failure, resources = correlate(given, evidence, selection, lookback_days)
        # a collector input failure (no collection) or a document failure ends the loop
        if evidence.collection is None or failure is not None or not_before is None or not _needs_poll(resources):
            break
        if clock() + POLL_INTERVAL > finished + POLL_CAP:
            break
        sleep(POLL_INTERVAL.total_seconds())
        log_event(logger, logging.INFO, "investigation_poll", "re-querying the Activity Log", polls=polls)

    evidence_bytes = al.render_evidence(evidence).encode("utf-8")
    binding.update(evidence_sha256=hashlib.sha256(evidence_bytes).hexdigest(), evidence_outcome=evidence.outcome)
    completeness = None
    if evidence.collection is not None:
        queried = al.parse_timestamp(evidence.collection.queried_at)
        completeness = {"not_before": evidence.collection.not_before, "queried_at": evidence.collection.queried_at,
                        "polls": polls, "settled": bool(known and at.settled(queried, finished)),
                        "max_ingestion_delay_ms": evidence.collection.max_ingestion_delay_ms}
    return _finish(rules, binding, failure, selection, resources, completeness, evidence_bytes)


def _window_start(queryable: list, selection: AnchorSelection, now: datetime, lookback_days: int) -> datetime | None:
    """The run-level collection window start (G9): the earliest per-address start,
    or None (the collector's lookback) when no queryable address has an anchor."""
    anchors = [selection.for_address(t.address) for t in queryable]
    if not any(anchors):
        return None
    lookback = now.astimezone(timezone.utc).replace(microsecond=0) - timedelta(days=lookback_days)
    starts = [a.started - SKEW if a is not None else lookback for a in anchors]
    return min(starts)


def _finish(rules: dict, binding: dict, failure: dict | None, selection: AnchorSelection, resources: list[dict],
            completeness: dict | None, evidence_bytes: bytes | None) -> Result:
    if failure is None:
        outcome = "incomplete" if any(r["verdict"] == "not_investigated" for r in resources) else "complete"
    else:
        outcome = "failed"
    document = DriftInvestigation.model_validate({
        "investigation_version": INVESTIGATION_VERSION, "trust": "restricted", "rules": rules,
        "outcome": outcome, "failure": failure, "binding": binding, "completeness": completeness,
        "anchor_candidates": selection.doc(), "resources": resources})
    log_event(logger, logging.INFO if outcome == "complete" else logging.WARNING, "investigation_finished",
              "investigation computed", outcome=outcome, resources=len(resources),
              verdicts=dict(sorted(Counter(r["verdict"] for r in resources).items())),
              property_links=dict(sorted(Counter(r["property_link"] for r in resources).items())),
              anchors_accepted=len(selection.accepted), anchors_rejected=len(selection.rejected),
              polls=(completeness or {}).get("polls"))
    return Result(document, evidence_bytes)


# ---------------------------------------------------------------------------
# Independent re-check against the evidence (defense in depth)
# ---------------------------------------------------------------------------

def verify_against_evidence(document: DriftInvestigation, evidence_bytes: bytes | None) -> list[str]:
    """Re-check an investigation against the evidence it names, independently of
    `correlate`: the evidence hash and subject; every operation's rows (existence,
    match and relation, Administrative, one group key, times, outcome, caller,
    timing, capability per a restated table); attached and automated events; the
    decisive operation; and a confirmed deletion's rows. Returns the problems found."""
    if document.failure is not None and document.failure.stage == "input":
        return []
    if evidence_bytes is None and document.binding.evidence_sha256 is None:
        # nothing was collected (no detection time): only precondition results
        if any(r.operations or r.automated_events or r.window is not None for r in document.resources):
            return ["resources were correlated without bound evidence"]
        return []
    if evidence_bytes is None or hashlib.sha256(evidence_bytes).hexdigest() != document.binding.evidence_sha256:
        return ["evidence_sha256 does not match the evidence"]
    try:
        evidence = al.ActivityLogEvidence.model_validate(at._json(evidence_bytes))
    except (ValueError, ValidationError, RecursionError, UnicodeDecodeError):
        return ["the evidence does not satisfy its contract"]
    problems = []
    if document.failure is None and (evidence.subject.run_id, evidence.subject.plan_timestamp) != (
            document.binding.run_id, document.binding.plan_timestamp):
        problems.append("binding does not match the evidence subject")
    events = {e.event_data_id: e for e in evidence.events}
    observation = document.binding.observation
    for resource in document.resources:
        address = resource.address

        def relation_of(event_id: str) -> str | None:
            event = events.get(event_id)
            return next((m.relation for m in event.matches if m.address == address), None) if event else None

        for op in resource.operations:
            rows = [events.get(i) for i in op.event_ids]
            if any(row is None for row in rows):
                problems.append(f"{address} {op.op_id}: an event is not in the evidence")
                continue
            relations = {relation_of(i) for i in op.event_ids}
            if None in relations or "descendant" in relations or sorted(relations) != op.relations:
                problems.append(f"{address} {op.op_id}: rows are not exact/extension rows of this resource")
            if any(row.category != "Administrative" for row in rows):
                problems.append(f"{address} {op.op_id}: rows are not Administrative")
            keys = {(row.correlation_id, row.operation_name.lower()) for row in rows}
            if len(keys) != 1 or (rows[0].correlation_id is None and len(rows) > 1):
                problems.append(f"{address} {op.op_id}: rows are not one operation group")
            times = [al.parse_timestamp(row.event_timestamp) for row in rows]
            succeeded = [t for row, t in zip(rows, times) if row.status == "Succeeded"]
            if al.format_timestamp(min(times)) != op.start or al.format_timestamp(
                    max(succeeded) if succeeded else max(times)) != op.end:
                problems.append(f"{address} {op.op_id}: start/end do not match the rows")
            if (op.outcome == "successful") != bool(succeeded):
                problems.append(f"{address} {op.op_id}: outcome does not match the rows")
            if op.caller is not None and any(row.caller != op.caller for row in rows):
                problems.append(f"{address} {op.op_id}: caller does not match the rows")
            if observation is not None:
                s, f = al.parse_timestamp(observation.started_at), al.parse_timestamp(observation.finished_at)
                if _timing(al.parse_timestamp(op.start), al.parse_timestamp(op.end), s, f) != op.timing:
                    problems.append(f"{address} {op.op_id}: timing does not match the observation")
            name = rows[0].operation_name.lower()
            if name == TAGS_WRITE:
                expected = ["tags"]
            elif name.endswith("/write") and op.relations == ["exact"] and name == at.lifecycle_operations(
                    al.parse_resource_id(resource.resource_id))[0]:
                expected = ["existence_create", "other", "tags"]
            elif name.endswith("/delete") and op.relations == ["exact"] and name == at.lifecycle_operations(
                    al.parse_resource_id(resource.resource_id))[1]:
                expected = ["existence_delete"]
            else:
                expected = []
            if op.capable_areas != expected:
                problems.append(f"{address} {op.op_id}: capable areas do not match table v1")
            for attached in op.attached_event_ids:
                event = events.get(attached)
                if event is None or event.category not in ("Policy", "Autoscale") or event.correlation_id != \
                        op.correlation_id or relation_of(attached) not in ("exact", "extension"):
                    problems.append(f"{address} {op.op_id}: attached event {attached} does not belong to it")
        for automated in resource.automated_events:
            event = events.get(automated.event_id)
            if event is None or event.category != automated.category or relation_of(
                    automated.event_id) not in ("exact", "extension"):
                problems.append(f"{address}: automated event {automated.event_id} does not match the evidence")
        rule = resource.deletion_rule
        if resource.property_link == "confirmed" and rule is not None:
            decisive = [events.get(i) for i in rule.decisive_event_ids]
            arm = al.parse_resource_id(resource.resource_id)
            delete_op = at.lifecycle_operations(arm)[1]
            if any(e is None or e.operation_name.lower() != delete_op or relation_of(e.event_data_id) != "exact"
                   or e.caller != rule.caller for e in decisive):
                problems.append(f"{address}: the confirmed deletion's rows do not match the evidence")
    return problems


# ---------------------------------------------------------------------------
# Public projection (Task 9B.3; Phase 9B G11)
# ---------------------------------------------------------------------------

EXPOSURE = {"caller_identity": "withheld", "resource_id": "withheld", "event_id": "withheld",
            "correlation_id": "withheld", "who_path": "local_only"}


def project(document: DriftInvestigation) -> dict:
    """The public investigation of a restricted one: only the G11 public schema.
    Callers, resource IDs, event / correlation IDs, restricted-content hashes and
    anchor candidate names never cross over."""
    candidates = document.anchor_candidates
    accepted = {a.candidate: a for a in candidates.accepted}
    resources = []
    for r in document.resources:
        window = None
        if r.window is not None:
            anchor = None
            if r.window.anchor is not None:
                a = accepted[r.window.anchor]
                anchor = {"run_id": a.run_id, "plan_timestamp": a.plan_timestamp, "started_at": a.started_at,
                          "finished_at": a.finished_at, "report_sha256": a.report_sha256}
            window = {"kind": r.window.kind, "start": r.window.start, "anchor": anchor}
        rule = r.deletion_rule
        deletion = None if rule is None else {
            "status": rule.status, "reason": rule.reason, "rule": rule.rule, "claim": rule.claim,
            "anchor_kind": rule.anchor.kind if rule.anchor else None,
            "anchor_time": rule.anchor.time if rule.anchor else None,
            "anchor_run_id": rule.anchor.run_id if rule.anchor else None,
            "decisive_events": len(rule.decisive_event_ids), "candidate_events": len(rule.candidate_event_ids),
            "related_events": len(rule.related_event_ids),
            "after_detection_events": len(rule.after_detection_event_ids)}
        resources.append({
            "address": r.address, "drift_action": r.drift_action, "relevant_areas": list(r.relevant_areas),
            "window": window, "verdict": r.verdict, "reason": r.reason,
            "decisive_operation": r.decisive_operation, "property_link": r.property_link,
            "property_link_reason": r.property_link_reason, "deletion_rule": deletion,
            "actor_attribution": {"status": r.actor_attribution.status, "rule": r.actor_attribution.rule,
                                  "claim": r.actor_attribution.claim},
            "unreadable_events_in_scope": r.unreadable_events_in_scope,
            "operations": [{
                "op_id": op.op_id, "operation_name": op.operation_name, "outcome": op.outcome,
                "relations": list(op.relations), "start": op.start, "end": op.end,
                "available_at": op.available_at, "timing": op.timing, "in_window": op.in_window,
                "role": op.role, "capable_areas": list(op.capable_areas), "caller_status": op.caller_status,
                "caller_type": op.caller_type, "client_app": op.client_app,
                "pipeline_identity": op.pipeline_identity, "attached_events": len(op.attached_event_ids),
            } for op in r.operations],
            "automated_events": [{
                "ref": f"auto-{n}", "operation_name": a.operation_name, "category": a.category,
                "event_timestamp": a.event_timestamp, "timing": a.timing, "in_window": a.in_window,
                "signal": a.signal,
            } for n, a in enumerate(r.automated_events, 1)],
            "descendant_events": r.descendant_events,
            "descendant_operations": dict(r.descendant_operations),
        })
    binding = document.binding
    return {
        "public_version": pub.PUBLIC_VERSION,
        "exposure": dict(EXPOSURE),
        "rules": document.rules.model_dump(mode="json"),
        "outcome": document.outcome,
        "failure": document.failure.model_dump(mode="json") if document.failure else None,
        "binding": {"run_id": binding.run_id, "plan_timestamp": binding.plan_timestamp,
                    "drift_report_sha256": binding.drift_report_sha256,
                    "evidence_outcome": binding.evidence_outcome,
                    "observation": binding.observation.model_dump(mode="json") if binding.observation else None},
        "completeness": document.completeness.model_dump(mode="json") if document.completeness else None,
        "anchors": {"examined": candidates.examined, "accepted": len(candidates.accepted),
                    "rejected": dict(sorted(Counter(r.reason for r in candidates.rejected).items()))},
        "resources": resources,
    }


def verify_projection(public: pub.PublicInvestigation, document: DriftInvestigation) -> list[str]:
    """Re-derive every public field from the restricted document independently of
    `project` and report each difference (location only, never a value)."""
    problems = []

    def same(label: str, public_value: Any, restricted_value: Any) -> None:
        if public_value != restricted_value:
            problems.append(f"{label} does not match the restricted investigation")

    same("outcome", public.outcome, document.outcome)
    same("failure", public.failure and (public.failure.stage, public.failure.reason),
         document.failure and (document.failure.stage, document.failure.reason))
    same("rules", public.rules.model_dump(), document.rules.model_dump())
    b, rb = public.binding, document.binding
    same("binding", (b.run_id, b.plan_timestamp, b.drift_report_sha256, b.evidence_outcome),
         (rb.run_id, rb.plan_timestamp, rb.drift_report_sha256, rb.evidence_outcome))
    same("binding.observation", b.observation and (b.observation.started_at, b.observation.finished_at),
         rb.observation and (rb.observation.started_at, rb.observation.finished_at))
    same("completeness", public.completeness and public.completeness.model_dump(),
         document.completeness and document.completeness.model_dump())
    same("anchors.examined", public.anchors.examined, document.anchor_candidates.examined)
    same("anchors.accepted", public.anchors.accepted, len(document.anchor_candidates.accepted))
    reasons: dict[str, int] = {}
    for rejected in document.anchor_candidates.rejected:
        reasons[rejected.reason] = reasons.get(rejected.reason, 0) + 1
    same("anchors.rejected", dict(public.anchors.rejected), reasons)
    if [r.address for r in public.resources] != [r.address for r in document.resources]:
        return problems + ["resources do not match the restricted investigation"]
    accepted = {a.candidate: a for a in document.anchor_candidates.accepted}
    for p, r in zip(public.resources, document.resources):
        at_ = p.address
        same(f"{at_} scalars", (p.drift_action, p.relevant_areas, p.verdict, p.reason, p.decisive_operation,
                                p.property_link, p.property_link_reason, p.unreadable_events_in_scope,
                                p.descendant_events, p.descendant_operations),
             (r.drift_action, r.relevant_areas, r.verdict, r.reason, r.decisive_operation, r.property_link,
              r.property_link_reason, r.unreadable_events_in_scope, r.descendant_events, r.descendant_operations))
        same(f"{at_} actor", (p.actor_attribution.status, p.actor_attribution.rule, p.actor_attribution.claim),
             (r.actor_attribution.status, r.actor_attribution.rule, r.actor_attribution.claim))
        if (p.window is None) != (r.window is None):
            problems.append(f"{at_} window does not match the restricted investigation")
        elif p.window is not None:
            same(f"{at_} window", (p.window.kind, p.window.start), (r.window.kind, r.window.start))
            anchor = accepted.get(r.window.anchor) if r.window.anchor else None
            same(f"{at_} window.anchor",
                 p.window.anchor and (p.window.anchor.run_id, p.window.anchor.plan_timestamp,
                                      p.window.anchor.started_at, p.window.anchor.finished_at,
                                      p.window.anchor.report_sha256),
                 anchor and (anchor.run_id, anchor.plan_timestamp, anchor.started_at, anchor.finished_at,
                             anchor.report_sha256))
        rule, prule = r.deletion_rule, p.deletion_rule
        same(f"{at_} deletion_rule",
             prule and (prule.status, prule.reason, prule.rule, prule.claim, prule.anchor_kind, prule.anchor_time,
                        prule.anchor_run_id, prule.decisive_events, prule.candidate_events, prule.related_events,
                        prule.after_detection_events),
             rule and (rule.status, rule.reason, rule.rule, rule.claim, rule.anchor and rule.anchor.kind,
                       rule.anchor and rule.anchor.time, rule.anchor and rule.anchor.run_id,
                       len(rule.decisive_event_ids), len(rule.candidate_event_ids), len(rule.related_event_ids),
                       len(rule.after_detection_event_ids)))
        if len(p.operations) != len(r.operations):
            problems.append(f"{at_} operations do not match the restricted investigation")
        for pop, rop in zip(p.operations, r.operations):
            same(f"{at_} {pop.op_id}",
                 (pop.op_id, pop.operation_name, pop.outcome, pop.relations, pop.start, pop.end, pop.available_at,
                  pop.timing, pop.in_window, pop.role, pop.capable_areas, pop.caller_status, pop.caller_type,
                  pop.client_app, pop.pipeline_identity, pop.attached_events),
                 (rop.op_id, rop.operation_name, rop.outcome, rop.relations, rop.start, rop.end, rop.available_at,
                  rop.timing, rop.in_window, rop.role, rop.capable_areas, rop.caller_status, rop.caller_type,
                  rop.client_app, rop.pipeline_identity, len(rop.attached_event_ids)))
        if len(p.automated_events) != len(r.automated_events):
            problems.append(f"{at_} automated events do not match the restricted investigation")
        for n, (pa, ra) in enumerate(zip(p.automated_events, r.automated_events), 1):
            same(f"{at_} auto-{n}", (pa.ref, pa.operation_name, pa.category, pa.event_timestamp, pa.timing,
                                     pa.in_window, pa.signal),
                 (f"auto-{n}", ra.operation_name, ra.category, ra.event_timestamp, ra.timing, ra.in_window,
                  ra.signal))
    return problems


def publish(document: DriftInvestigation) -> tuple[str | None, list[str]]:
    """(public JSON text, []) or (None, problems): project, check the public contract,
    re-derive every field from the restricted document and run the leak scan, all
    before anything is rendered."""
    try:
        public = pub.PublicInvestigation.model_validate(project(document))
    except ValidationError:
        return None, ["the projection does not satisfy the public contract"]
    problems = verify_projection(public, document)
    problems += [f"leak {finding}" for finding in pub.leak_findings(public.model_dump(mode="json"))]
    if problems:
        return None, problems
    return pub.render_public(public), []
