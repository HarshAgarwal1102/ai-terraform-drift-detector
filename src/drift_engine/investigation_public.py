"""Public drift investigation document (Task 9B.3).

`drift_investigation.json` is the public projection of the restricted investigation
(investigation.py). It carries only the fields of the Phase 9B public schema
(PROJECT_PLAN.md, G11): operation metadata, timestamps, caller *type*, client
application, the pipeline-identity flag, verdicts, links, reason codes, counts and
safe references (the per-resource ordinals `op-<n>` / `auto-<n>`, the drift report's
run id and canonical SHA-256, the anchor run's GitHub run id and report SHA-256).

It never carries a caller identity in any form, ARM resource / subscription / tenant
IDs, event or correlation IDs, IP addresses, claims, raw Activity Log text, any hash
of restricted content, or anchor candidate names and rejection details. Two layers
guard that: the strict allowlist model below, and `leak_findings`, a fail-closed scan
of every string (keys included) for GUIDs, `@`, IP addresses, `/subscriptions/` and
`/providers/` paths and URLs.

This module imports nothing from activity_logs, attribution, investigation or who:
it is the only investigation module `ai_engine` may use (Phase 9B, G14).
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

PUBLIC_VERSION = "1"
PUBLIC_FILE = "drift_investigation.json"
MAX_INPUT_BYTES = 50 * 1024 * 1024

# Kept equal to investigation.py / attribution.py / activity_logs.py by a test.
AREAS = ("existence_create", "existence_delete", "other", "tags")
VERDICTS = ("ambiguous", "latest_capable_operation", "no_capable_operation_found", "not_investigated",
            "sole_capable_operation")
DECISIVE_VERDICTS = ("latest_capable_operation", "sole_capable_operation")
AMBIGUOUS_REASONS = ("automated_activity", "during_observation", "multiple_capable_operations",
                     "partial_capability", "unclassified_operation", "unreadable_events_in_scope",
                     "unresolved_operation")
PRECONDITION_REASONS = ("detection_time_unknown", "evidence_failed", "evidence_incomplete", "evidence_mismatch",
                        "evidence_not_settled", "invalid_resource_id", "no_resource_id", "unsupported_scope")
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
DELETION_REASONS = (
    "evidence_mismatch", "evidence_failed", "evidence_incomplete", "evidence_not_settled",
    "unreadable_events_in_scope", "detection_time_unknown", "no_resource_id", "invalid_resource_id",
    "unsupported_scope", "update_not_attributable", "no_deletion_event", "order_ambiguous",
    "latest_operation_is_write", "no_existence_anchor", "multiple_successful_deletes", "unresolved_operation",
    "caller_missing", "caller_inconsistent", "concurrent_with_detection", "automated_activity_overlap",
)
CALLER_TYPES = ("managed_identity", "service_principal", "unknown", "user")
CLIENT_APPS = ("azure_cli", "azure_portal", "other_application", "unknown")
ACTIONS = ("no-op", "read", "create", "update", "delete", "replace", "unrecognized")

_TIMESTAMP = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$"
_OPERATION_NAME = r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9._-]+)+$"

Timestamp = Annotated[str, Field(pattern=_TIMESTAMP)]
OperationName = Annotated[str, Field(max_length=256, pattern=_OPERATION_NAME)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
GithubRunId = Annotated[str, Field(pattern=r"^github-[0-9]+-[0-9]+$")]
Count = Annotated[int, Field(ge=0)]
Positive = Annotated[int, Field(ge=1)]
Timing = Literal["after_observation", "before_observation", "during_observation"]


def canonical_sha256(document: Any) -> str:
    """SHA-256 of the canonical JSON (sorted keys, compact separators, UTF-8): the drift
    report hash of Task 9A.1 (`ai_engine`'s `drift_report_sha256`)."""
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Leak scan (fail closed)
# ---------------------------------------------------------------------------

_GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://|\bwww\.", re.IGNORECASE)
_IP_TOKEN = re.compile(r"[0-9A-Fa-f:.]+")
_SCHEMA_KEY = re.compile(r"[a-z][a-z0-9_]{0,40}")
LEAK_KINDS = ("at_sign", "guid", "ip_address", "providers_path", "subscriptions_path", "url")


def _ip_like(text: str) -> bool:
    for token in _IP_TOKEN.findall(text):
        candidate = token.strip(".")
        if (":" in candidate and candidate.count(":") >= 2) or candidate.count(".") == 3:
            try:
                ipaddress.ip_address(candidate)
                return True
            except ValueError:
                continue
    return False


def _string_findings(text: str) -> list[str]:
    found = []
    if "@" in text:
        found.append("at_sign")
    if _GUID.search(text):
        found.append("guid")
    if _ip_like(text):
        found.append("ip_address")
    lowered = text.lower()
    if "/providers/" in lowered:
        found.append("providers_path")
    if "/subscriptions/" in lowered:
        found.append("subscriptions_path")
    if _URL.search(text):
        found.append("url")
    return found


def leak_findings(value: Any, path: str = "$") -> list[str]:
    """`<json path>: <kind>` for every string (keys included) that looks like a
    forbidden value. Only the location and kind are reported, never the value."""
    findings = []
    if isinstance(value, str):
        findings += [f"{path}: {kind}" for kind in _string_findings(value)]
    elif isinstance(value, dict):
        for key, item in value.items():
            # only schema-shaped keys appear in a path; other keys are content
            segment = key if isinstance(key, str) and _SCHEMA_KEY.fullmatch(key) else "<key>"
            findings += [f"{path}.{segment}<key>: {kind}" for kind in _string_findings(str(key))]
            findings += leak_findings(item, f"{path}.{segment}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            findings += leak_findings(item, f"{path}[{index}]")
    return findings


# ---------------------------------------------------------------------------
# Public model (strict, frozen, unknown fields rejected)
# ---------------------------------------------------------------------------

class _Model(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class Rules(_Model):
    table_version: Literal["1"]
    deletion_rules_version: Literal["2"]
    skew_seconds: Literal[60]
    settle_margin_minutes: Literal[10]
    poll_interval_minutes: Literal[2]
    poll_cap_minutes: Literal[20]
    automated_overlap_minutes: Literal[5]
    lookback_days: Annotated[int, Field(ge=1, le=89)]


class Exposure(_Model):
    caller_identity: Literal["withheld"]
    resource_id: Literal["withheld"]
    event_id: Literal["withheld"]
    correlation_id: Literal["withheld"]
    who_path: Literal["local_only"]


class Failure(_Model):
    stage: Literal["input", "binding", "evidence"]
    reason: Literal[sum(FAILURE_REASONS.values(), ())]

    @model_validator(mode="after")
    def _stage_reason(self) -> Failure:
        if self.reason not in FAILURE_REASONS[self.stage]:
            raise ValueError(f"{self.reason} is not a {self.stage} failure")
        return self


class Observation(_Model):
    started_at: Timestamp
    finished_at: Timestamp


class Binding(_Model):
    run_id: Annotated[str, Field(min_length=1, max_length=200)] | None
    plan_timestamp: Annotated[str, Field(min_length=1, max_length=64)] | None
    drift_report_sha256: Sha256 | None
    evidence_outcome: Literal["complete", "incomplete", "failed"] | None
    observation: Observation | None


class Completeness(_Model):
    not_before: Timestamp | None
    queried_at: Timestamp
    polls: Positive
    settled: bool
    max_ingestion_delay_ms: Count | None


class Anchors(_Model):
    examined: Annotated[int, Field(ge=0, le=50)]
    accepted: Count
    rejected: dict[Literal[ANCHOR_REJECTIONS], Positive]

    @model_validator(mode="after")
    def _sorted(self) -> Anchors:
        if list(self.rejected) != sorted(self.rejected):
            raise ValueError("rejected reasons must be sorted")
        return self


class AnchorRef(_Model):
    run_id: GithubRunId
    plan_timestamp: Annotated[str, Field(min_length=1, max_length=64)]
    started_at: Timestamp
    finished_at: Timestamp
    report_sha256: Sha256


class Window(_Model):
    kind: Literal["anchor", "lookback"]
    start: Timestamp
    anchor: AnchorRef | None

    @model_validator(mode="after")
    def _consistent(self) -> Window:
        if (self.kind == "anchor") != (self.anchor is not None):
            raise ValueError("an anchor window names its anchor run, a lookback window none")
        return self


class Operation(_Model):
    op_id: Annotated[str, Field(pattern=r"^op-[1-9][0-9]*$")]
    operation_name: OperationName
    outcome: Literal["successful", "failed", "unresolved"]
    relations: Annotated[list[Literal["exact", "extension"]], Field(min_length=1)]
    start: Timestamp
    end: Timestamp
    available_at: Timestamp | None
    timing: Timing
    in_window: bool
    role: Literal["capable", "irrelevant", "unclassified"]
    capable_areas: list[Literal[AREAS]]
    caller_status: Literal["recorded", "missing", "inconsistent"]
    caller_type: Literal[CALLER_TYPES]
    client_app: Literal[CLIENT_APPS]
    pipeline_identity: bool | None
    attached_events: Count


class AutomatedEvent(_Model):
    ref: Annotated[str, Field(pattern=r"^auto-[1-9][0-9]*$")]
    operation_name: OperationName
    category: Literal["Autoscale", "Policy"]
    event_timestamp: Timestamp
    timing: Timing
    in_window: bool
    signal: bool


class DeletionRule(_Model):
    status: Literal["confirmed", "unknown"]
    reason: Literal[DELETION_REASONS] | None
    rule: Literal["external_deletion_v1"] | None
    claim: Literal["recorded_successful_delete"] | None
    anchor_kind: Literal["write_event", "prior_detection_run"] | None
    anchor_time: Timestamp | None
    anchor_run_id: GithubRunId | None
    decisive_events: Count
    candidate_events: Count
    related_events: Count
    after_detection_events: Count


class ActorAttribution(_Model):
    status: Literal["confirmed", "not_confirmed"]
    rule: Literal["external_deletion_v1"] | None
    claim: Literal["recorded_successful_delete"] | None


class Resource(_Model):
    address: Annotated[str, Field(min_length=1, max_length=1024)]
    drift_action: Literal[ACTIONS] | None
    relevant_areas: Annotated[list[Literal[AREAS]], Field(min_length=1)]
    window: Window | None
    verdict: Literal[VERDICTS]
    reason: Literal[AMBIGUOUS_REASONS + PRECONDITION_REASONS] | None
    decisive_operation: Annotated[str, Field(pattern=r"^op-[1-9][0-9]*$")] | None
    property_link: Literal["confirmed", "inferred_not_provable", "none"]
    property_link_reason: Literal[PROPERTY_LINK_REASONS] | None
    deletion_rule: DeletionRule | None
    actor_attribution: ActorAttribution
    unreadable_events_in_scope: bool
    operations: list[Operation]
    automated_events: list[AutomatedEvent]
    descendant_events: Count
    descendant_operations: dict[str, Positive]

    @model_validator(mode="after")
    def _invariants(self) -> Resource:
        problems = []
        if [op.op_id for op in self.operations] != [f"op-{n}" for n in range(1, len(self.operations) + 1)]:
            problems.append("operations must be numbered op-1, op-2, ... in order")
        if [a.ref for a in self.automated_events] != [f"auto-{n}" for n in range(1, len(self.automated_events) + 1)]:
            problems.append("automated events must be numbered auto-1, auto-2, ... in order")
        decisive = next((op for op in self.operations if op.op_id == self.decisive_operation), None)
        if (self.decisive_operation is not None) != (self.verdict in DECISIVE_VERDICTS) or (
                self.decisive_operation is not None and decisive is None):
            problems.append("a listed decisive operation exists exactly for sole / latest")
        if self.property_link == "confirmed" and (self.drift_action != "delete"
                                                  or self.verdict not in DECISIVE_VERDICTS):
            problems.append("only a deletion under a sole / latest verdict can be property-confirmed")
        if (self.actor_attribution.status == "confirmed") != (self.property_link == "confirmed"):
            problems.append("actor attribution is confirmed exactly with a confirmed property link")
        if self.unreadable_events_in_scope and self.verdict in DECISIVE_VERDICTS + ("no_capable_operation_found",):
            problems.append("unreadable events in scope allow no sole, latest or none verdict")
        if list(self.descendant_operations) != sorted(self.descendant_operations) or sum(
                self.descendant_operations.values()) != self.descendant_events:
            problems.append("descendant operations must be sorted and add up to descendant_events")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class PublicInvestigation(_Model):
    """The whole public `drift_investigation.json` (public_version 1)."""

    public_version: Literal["1"]
    exposure: Exposure
    rules: Rules
    outcome: Literal["complete", "incomplete", "failed"]
    failure: Failure | None
    binding: Binding
    completeness: Completeness | None
    anchors: Anchors
    resources: list[Resource]

    @model_validator(mode="after")
    def _invariants(self) -> PublicInvestigation:
        addresses = [r.address for r in self.resources]
        if addresses != sorted(set(addresses)):
            raise ValueError("resources must be sorted by address, without repeats")
        if (self.outcome == "failed") != (self.failure is not None):
            raise ValueError("failure is set exactly when the outcome is failed")
        return self


def render_public(document: PublicInvestigation) -> str:
    """Sorted keys, two-space indent, ASCII, trailing newline: byte-stable."""
    return json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# Loading and checking a public file
# ---------------------------------------------------------------------------

class PublicInvestigationError(Exception):
    """A public investigation was rejected; `code` is fixed, never the offending value."""

    CODES = ("binding_mismatch", "contract", "invalid_json", "leak", "too_large")

    def __init__(self, code: str, findings: list[str] | None = None) -> None:
        if code not in self.CODES:
            raise ValueError(f"unknown code {code!r}")
        super().__init__(code)
        self.code = code
        self.findings = findings or []


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict:
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate JSON key")
    return dict(pairs)


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-standard JSON constant {name}")


def strict_json(data: bytes) -> Any:
    """JSON with duplicate keys and NaN/Infinity rejected."""
    return json.loads(data.decode("utf-8"), object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant)


def load_public(data: bytes) -> PublicInvestigation:
    """Parse and check a public investigation: strict JSON, the leak scan over the raw
    document, then the strict model. Raises PublicInvestigationError."""
    if len(data) > MAX_INPUT_BYTES:
        raise PublicInvestigationError("too_large")
    try:
        raw = strict_json(data)
    except (ValueError, RecursionError, UnicodeDecodeError):
        raise PublicInvestigationError("invalid_json") from None
    findings = leak_findings(raw)
    if findings:
        raise PublicInvestigationError("leak", findings)
    try:
        return PublicInvestigation.model_validate(raw)
    except ValidationError:
        raise PublicInvestigationError("contract") from None


def check_binding(document: PublicInvestigation, report_bytes: bytes) -> None:
    """The public investigation was computed for this drift report (run id, plan
    timestamp, canonical SHA-256). Raises PublicInvestigationError("binding_mismatch")."""
    try:
        report = strict_json(report_bytes)
    except (ValueError, RecursionError, UnicodeDecodeError):
        raise PublicInvestigationError("binding_mismatch") from None
    run = (report.get("run") or {}) if isinstance(report, dict) else {}
    plan = (report.get("plan") or {}) if isinstance(report, dict) else {}
    binding = document.binding
    if (binding.drift_report_sha256 != canonical_sha256(report) or binding.run_id != run.get("run_id")
            or binding.plan_timestamp != plan.get("timestamp")):
        raise PublicInvestigationError("binding_mismatch")
