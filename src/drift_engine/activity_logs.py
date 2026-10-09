"""Azure Activity Log evidence collector (Task 7.1; evidence v2, Task 9B.1).

Collects, validates, normalizes and scopes Azure Activity Log events for the
resources a drift report found drifted, and writes them as a separate document,
`activity_log_evidence.json`. It never changes the drift report, never decides who
or what caused a drift, and never fills `caller_identity`, `actor` or `confirmed`:
correlation is Task 7.2 and the meaning of missing or incomplete evidence is Task 7.3.

Activity Log data is **untrusted external evidence** (`trust: untrusted_external`).
An event in this document only says that Azure recorded an operation on a resource
inside the queried window; it does not say that the operation caused the drift.

Pipeline (deterministic except for the Azure call itself):

  plan.json + detection_run.json -> classifier.evaluate (the drift report)
    -> targets: every managed resource with a resource_drift entry (the has_drift
       definition), whatever its Terraform action (external updates and deletions
       alike); its ARM ID is the recorded-state `id` (else the refreshed one), and a
       drifted resource without a usable ID is kept with a non-queried status
    -> scopes: one query per (subscription, resource group), so child-resource
       events such as NSG security rules are not missed
    -> ActivityLogSource.pages(subscription_id, filter)   (AzureMonitorSource: Azure)
    -> normalize: allowlisted fields only, every value validated; events outside
       every target, outside the window or outside the kept categories are dropped
       and counted, never kept
    -> ActivityLogEvidence (strict model) -> render_evidence (byte-stable JSON)

Query: `eventTimestamp ge '<start>' and eventTimestamp le '<end>' and
resourceGroupName eq '<rg>'`, without `$select` (`caller` is not a documented
`$select` property). The window ends at the query time (`queried_at`, whole
seconds). It starts `lookback_days` (1-89, default 30) earlier (`basis: lookback`)
or at an explicit run-level `window_start` chosen by the caller (`basis: explicit`;
Task 9B.2 passes the earliest per-resource anchor or lookback start), never more than
89 days back. A caller may also give `not_before`: a collection whose query time is
earlier issues no query and fails with `query_before_not_before`. This module never
sleeps or polls; waiting, polling and completeness are Task 9B.2's. The evidence
records `queried_at`, `not_before` and the largest observed ingestion delay
(`submissionTimestamp - eventTimestamp`); whether that is settled enough for a
detection run is decided by the consumers (Task 9B.2: `queried_at >= finished_at + 10
minutes`). Pages, events and wall time per run are bounded (`Limits`); hitting a
bound marks the scope `truncated`, never silently complete.

Kept event fields (everything else, including the raw `claims`, `authorization`,
`httpRequest` with the client IP, `properties`, `description` and `tenantId`, is
never stored): event_data_id, correlation_id, operation_id, event_timestamp,
submission_timestamp, operation_name, status, sub_status, category, level,
resource_id, caller. Evidence v2 adds values derived on the spot, never the claims
themselves: `event_phase` (from eventName), `caller_type` (from the `idtyp` claim and
the presence of `xms_mirid`), `client_app` (the `appid` claim mapped through an
allowlist of verified first-party applications) and `pipeline_identity` (whether
`appid` equals the pipeline's client ID, given by the caller and never written).
Each kept event also records which target addresses it falls under, most specific
target only: `exact`, `extension` (only a verified extension type, currently
`<id>/providers/Microsoft.Resources/tags/default`) or `descendant` (anything else
below the target, including the resources a resource group contains).

The verified shape of a portal tag edit (real Azure, 2026-10-04): operation
`Microsoft.Resources/tags/write`, two rows with one correlationId, BeginRequest /
Started on `<rg-id>/providers/Microsoft.Resources/tags/default` (`extension`) and
EndRequest / Succeeded on `<rg-id>` itself (`exact`).

Failures are recorded, not raised: an input problem gives `outcome: failed` with
`failure.stage = "input"`; a query problem gives the scope a fixed error code
(`QUERY_FAILURE_CODES`, `LIMIT_CODES`), never exception text. No failure here can
change a drift detection result: this module only reads the drift report.

Azure access is confined to `AzureMonitorSource`, which imports the Azure SDK
(`[azure]` extra: azure-mgmt-monitor, azure-identity) only when it is first asked
for a page. It authenticates with `AzureCliCredential` only (the `az login` /
azure/login OIDC session; never DefaultAzureCredential or a secret) for the Azure
Resource Manager audience Azure CLI caches at login (Task 9B.5), sends GET
requests to the Activity Log endpoint on management.azure.com only (every other
request, redirect or nextLink is blocked before it is sent), and bounds retries,
Retry-After waits and timeouts. Nothing else in drift_engine imports the SDK.

Logs carry counts, resource group names and codes only: never a caller, a resource
ID, a subscription ID or a token.
"""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal, Protocol
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError, model_serializer, model_validator

from drift_engine.classifier import Evaluation, evaluate
from drift_engine.logs import log_event
from drift_engine.models import DriftReport

logger = logging.getLogger(__name__)

EVIDENCE_VERSION = "2"
EVIDENCE_FILE = "activity_log_evidence.json"
SOURCE = "azure_activity_log"
TRUST = "untrusted_external"

DEFAULT_LOOKBACK_DAYS = 30
# Azure keeps Activity Log events for 90 days and both ends of a query must fall
# inside them; 89 keeps the start clear of that edge while the query runs.
MAX_LOOKBACK_DAYS = 89
# Verified extension types (Phase 9B, G6): the suffix after a target's ID that makes
# an event an `extension` of that target. Anything else below a target, including
# the resources a resource group contains (same path shape), is `descendant`. A new
# entry needs a recorded real-Azure shape check.
VERIFIED_EXTENSIONS = ("/providers/microsoft.resources/tags/default",)

# Verified first-party client applications (claims.appid, 2026-10-03/04 real events).
# Any other application ID is `other_application`; a new entry needs recorded evidence.
CLIENT_APPS = {
    "c44b4083-3bb0-49c1-b47d-974e53cbdf3c": "azure_portal",
    "04b07795-8ddb-461a-bbee-02f9e1bf7b46": "azure_cli",
}
CLIENT_APP_VALUES = ("azure_cli", "azure_portal", "other_application", "unknown")
CALLER_TYPES = ("managed_identity", "service_principal", "unknown", "user")
EVENT_PHASES = ("begin", "end", "unknown")
RELATIONS = ("descendant", "exact", "extension")
# The pipeline's client ID for `pipeline_identity`; read by the CLI, never written.
PIPELINE_PRINCIPAL_ENV = "DRIFT_ENGINE_PIPELINE_PRINCIPAL"

# Categories that record operations changing resource state. Everything else
# (ServiceHealth, ResourceHealth, Alert, Recommendation, Security, ...) is dropped.
KEPT_CATEGORIES = ("Administrative", "Autoscale", "Policy")
LEVELS = ("Critical", "Error", "Informational", "Verbose", "Warning")

ARM_HOST = "management.azure.com"
ARM_ENDPOINT = f"https://{ARM_HOST}"
# Task 9B.5: the Azure Resource Manager audience Azure CLI caches at `az login`
# (`active_directory_resource_id`). The SDK default (`https://management.azure.com/.default`)
# misses that cache, and in CI Azure CLI then re-sends the GitHub OIDC assertion, which
# expires about 5 minutes after login. Requests still go to ARM_ENDPOINT only.
ARM_CREDENTIAL_SCOPE = "https://management.core.windows.net//.default"
# API version 2015-04-01, the only Activity Log version and the SDK's default.
_ACTIVITY_LOG_PATH = "/subscriptions/{subscription_id}/providers/microsoft.insights/eventtypes/management/values"

# Fixed codes. A query that fails has one of QUERY_FAILURE_CODES; one stopped by a
# bound has one of LIMIT_CODES. Exception text never reaches the evidence.
QUERY_FAILURE_CODES = (
    "authentication_failed",  # credential or service rejected the identity (401)
    "authorization_failed",  # 403: the identity may not read the Activity Log
    "azure_error",  # any other Azure SDK error
    "azure_sdk_unavailable",  # the [azure] extra is not installed
    "bad_request",  # 400: the service rejected the query
    "blocked_request",  # a request other than GET to the Activity Log endpoint was stopped
    "connection_failed",
    "credential_unavailable",  # no az login session (or az CLI missing)
    "http_error",  # any other unexpected HTTP status
    "invalid_response",  # a response the SDK cannot read as an event page
    "service_error",  # 5xx after retries
    "throttled",  # 429 after retries
    "timeout",
)
LIMIT_CODES = ("deadline_exceeded", "event_limit_exceeded", "page_limit_exceeded")
# Task 9B.5: why an `authentication_failed` query failed. Only the number after
# "AADSTS" is matched from the exception text (in memory); the text itself is never kept.
AUTH_REASONS = (
    "arm_rejected",  # Azure Resource Manager answered HTTP 401
    "assertion_expired",  # AADSTS700024: the client assertion is outside its validity window
    "federation_mismatch",  # AADSTS70021 / AADSTS700213: no matching federated credential
    "no_aadsts",  # the credential failed without an AADSTS number
    "other_aadsts",  # any other AADSTS number
)
_AADSTS_REASONS = {"700024": "assertion_expired", "70021": "federation_mismatch", "700213": "federation_mismatch"}
_AADSTS = re.compile(r"AADSTS(\d{5,7})(?!\d)")
DROP_REASONS = (
    "conflicting_duplicate",  # the same eventDataId with different content: every copy dropped
    "duplicate",  # an identical repeat of an event already kept
    "excluded_category",
    "invalid_event_data_id",
    "invalid_operation_name",
    "invalid_resource_id",
    "invalid_timestamp",
    "malformed_event",  # not a JSON object
    "out_of_scope",  # not a target and not under one
    "timestamp_outside_window",
)
ANOMALIES = (
    "caller_missing",
    "caller_rejected",
    "claims_missing",  # no claims: caller_type/client_app unknown, pipeline_identity null
    "claims_rejected",  # claims not an object
    "correlation_id_rejected",
    "level_rejected",
    "operation_id_rejected",
    "status_missing",
    "status_rejected",
    "sub_status_rejected",
    "submission_before_event",  # excluded from the ingestion delay
    "submission_timestamp_rejected",
)
TARGET_STATUSES = (
    "invalid_resource_id",  # the plan's id is not a valid ARM resource ID: not queried
    "no_resource_id",  # no usable id (absent, not a string, or marked sensitive): not queried
    "queried",  # its scope was queried completely
    "query_failed",
    "query_incomplete",  # its scope stopped at a bound
    "unsupported_scope",  # valid ID outside a resource group: not queried
)
INPUT_FAILURES = (
    "evidence_failed",
    "invalid_lookback",
    "invalid_not_before",
    "invalid_pipeline_principal",
    "invalid_query_time",
    "invalid_window_start",
    "query_before_not_before",  # queried_at is earlier than not_before: no query issued
)

QueryFailureCode = Literal[QUERY_FAILURE_CODES]
LimitCode = Literal[LIMIT_CODES]
DropReason = Literal[DROP_REASONS]
Anomaly = Literal[ANOMALIES]
TargetStatus = Literal[TARGET_STATUSES]
Category = Literal[KEPT_CATEGORIES]
Level = Literal[LEVELS]
CallerType = Literal[CALLER_TYPES]
ClientApp = Literal[CLIENT_APP_VALUES]
EventPhase = Literal[EVENT_PHASES]
Relation = Literal[RELATIONS]

MAX_RESOURCE_ID_LENGTH = 2048
MAX_CALLER_LENGTH = 256
MAX_OPERATION_NAME_LENGTH = 256


# ---------------------------------------------------------------------------
# Value validation (shared by normalization and the evidence model)
# ---------------------------------------------------------------------------

_GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
# Azure resource group names: letters, digits, underscore, hyphen, period and
# parentheses, at most 90 characters, not ending in a period. No quote, so a name
# can never break out of the OData filter literal.
_RESOURCE_GROUP = re.compile(r"[-\w.()]{1,90}")
_NAMESPACE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z][A-Za-z0-9]*)+")
_TYPE = re.compile(r"[A-Za-z][A-Za-z0-9]{0,79}")
_NAME = re.compile(r"[-\w.()~@+=:,]{1,260}")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_OPERATION_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9._-]+)+")
_STATUS = re.compile(r"[A-Za-z]+(?: [A-Za-z]+)*")
_SUB_STATUS = re.compile(r"[A-Za-z0-9]+(?:[ ._-][A-Za-z0-9]+)*")
# ASCII digits only: `\d` would also accept other scripts' digits (in Python and in
# pydantic's regex engine alike).
_TIMESTAMP_IN = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,9}))?(Z|\+00:00)"
)
TIMESTAMP_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$"


@dataclass(frozen=True)
class ArmId:
    """A syntactically valid ARM resource ID. `key` is its case-folded form (ARM IDs
    are case-insensitive); `text` is the ID as received."""

    text: str
    key: str
    subscription_id: str  # lower case
    resource_group: str | None  # as received; None for a subscription-level ID


def _valid_resource_group(name: str) -> bool:
    return bool(_RESOURCE_GROUP.fullmatch(name)) and not name.endswith(".")


def parse_resource_id(value: Any) -> ArmId | None:
    """Parse `/subscriptions/<guid>[/resourceGroups/<rg>][/providers/<ns>/<type>/<name>...]`.

    Extension resources (a further `/providers/...` after a type/name pair) are
    accepted. Anything else, including empty segments, a trailing slash, a type
    without a name or a character outside the allowed sets, returns None.
    """
    if not isinstance(value, str) or not value or len(value) > MAX_RESOURCE_ID_LENGTH:
        return None
    parts = value.split("/")
    if len(parts) < 3 or parts[0] != "" or parts[1].lower() != "subscriptions" or not _GUID.fullmatch(parts[2]):
        return None
    rest = parts[3:]
    resource_group = None
    if rest and rest[0].lower() == "resourcegroups":
        if len(rest) < 2 or not _valid_resource_group(rest[1]):
            return None
        resource_group = rest[1]
        rest = rest[2:]
    i = 0
    while i < len(rest):
        if rest[i].lower() != "providers" or i + 1 >= len(rest) or not _NAMESPACE.fullmatch(rest[i + 1]):
            return None
        i += 2
        pairs = 0
        while i < len(rest) and rest[i].lower() != "providers":
            if i + 1 >= len(rest) or not _TYPE.fullmatch(rest[i]) or not _NAME.fullmatch(rest[i + 1]):
                return None
            i += 2
            pairs += 1
        if pairs == 0:
            return None
    return ArmId(
        text=value,
        key="/".join(p.lower() for p in parts),
        subscription_id=parts[2].lower(),
        resource_group=resource_group,
    )


def valid_caller(value: Any) -> bool:
    """A caller is kept only as printable text: no control, format (incl. bidi and
    zero-width), private-use, surrogate or unassigned characters, no line or
    paragraph separators, no whitespace other than inner ASCII spaces, at most
    MAX_CALLER_LENGTH characters. Its content is never interpreted."""
    if not isinstance(value, str) or not value or len(value) > MAX_CALLER_LENGTH or value != value.strip(" "):
        return False
    for ch in value:
        category = unicodedata.category(ch)
        if category[0] == "C" or category in ("Zl", "Zp") or (category == "Zs" and ch != " "):
            return False
    return True


def parse_timestamp(value: Any) -> datetime | None:
    """ISO 8601 UTC (`Z` or `+00:00`), up to 9 fractional digits truncated to
    microseconds. Other offsets, lower-case `z` and impossible dates return None."""
    if not isinstance(value, str):
        return None
    m = _TIMESTAMP_IN.fullmatch(value)
    if m is None:
        return None
    fraction = (m.group(7) or "").ljust(6, "0")[:6]
    try:
        return datetime(*(int(m.group(n)) for n in range(1, 7)), int(fraction), tzinfo=timezone.utc)
    except ValueError:
        return None


def format_timestamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _check(predicate: Callable[[Any], bool], what: str):
    def check(value: Any) -> Any:
        if not predicate(value):
            raise ValueError(f"not a valid {what}")
        return value
    return AfterValidator(check)


def _event_resource_id(value: Any) -> bool:
    arm = parse_resource_id(value)
    return arm is not None and arm.resource_group is not None


# ---------------------------------------------------------------------------
# Evidence contract (strict, frozen, unknown fields rejected)
# ---------------------------------------------------------------------------

class _Model(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


Timestamp = Annotated[str, Field(pattern=TIMESTAMP_PATTERN)]
Count = Annotated[int, Field(ge=0)]
Token = Annotated[str, Field(pattern=rf"^{_TOKEN.pattern}$")]
EventResourceId = Annotated[str, _check(_event_resource_id, "resource-group-scoped ARM resource ID")]
TargetResourceId = Annotated[str, _check(lambda v: parse_resource_id(v) is not None, "ARM resource ID")]
Caller = Annotated[str, _check(valid_caller, "caller")]
OperationName = Annotated[
    str, Field(max_length=MAX_OPERATION_NAME_LENGTH, pattern=rf"^{_OPERATION_NAME.pattern}$")
]
Status = Annotated[str, Field(max_length=64, pattern=rf"^{_STATUS.pattern}$")]
SubStatus = Annotated[str, Field(max_length=64, pattern=rf"^{_SUB_STATUS.pattern}$")]
Address = Annotated[str, Field(min_length=1)]


class Window(_Model):
    """The queried interval (inclusive), on whole seconds, UTC. `end` is the query time.

    `basis` says where `start` came from: `lookback` (end minus `lookback_days`) or
    `explicit` (a run-level `window_start` given by the caller; `lookback_days` null).
    Whether the evidence is settled for a detection run is decided by its consumers
    from `collection.queried_at` (Phase 9B, G8), not here.
    """

    basis: Literal["lookback", "explicit"]
    start: Timestamp
    end: Timestamp
    lookback_days: Annotated[int, Field(ge=1, le=MAX_LOOKBACK_DAYS)] | None

    @model_validator(mode="after")
    def _consistent(self) -> Window:
        start, end = parse_timestamp(self.start), parse_timestamp(self.end)
        if start.microsecond or end.microsecond:
            raise ValueError("window start and end must be whole seconds")
        if self.basis == "lookback":
            if self.lookback_days is None or end - start != timedelta(days=self.lookback_days):
                raise ValueError("a lookback window must span exactly lookback_days")
        elif self.lookback_days is not None or not timedelta(0) < end - start <= timedelta(days=MAX_LOOKBACK_DAYS):
            raise ValueError("an explicit window has no lookback_days and spans more than 0 and at most "
                             f"{MAX_LOOKBACK_DAYS} days")
        return self


class Collection(_Model):
    """When this collection ran and what it saw of Azure's ingestion delay.

    `queried_at` is the query time (microseconds; the window ends at it, on whole
    seconds); `not_before` the earliest query time the caller allowed. The ingestion
    delay is `submission_timestamp - event_timestamp` over the kept events that have
    a usable, not earlier, submission time (`ingestion_delay_samples`); null without one.
    """

    queried_at: Timestamp
    not_before: Timestamp | None
    max_ingestion_delay_ms: Count | None
    ingestion_delay_samples: Count

    @model_validator(mode="after")
    def _consistent(self) -> Collection:
        if self.not_before is not None and parse_timestamp(self.not_before) > parse_timestamp(self.queried_at):
            raise ValueError("queried_at must not be earlier than not_before")
        if (self.max_ingestion_delay_ms is None) != (self.ingestion_delay_samples == 0):
            raise ValueError("max_ingestion_delay_ms is null exactly when there is no sample")
        return self


class Subject(_Model):
    """The detection run this evidence was collected for (copied, not interpreted)."""

    run_id: str | None
    plan_timestamp: str | None


class Failure(_Model):
    stage: Literal["input", "query"]
    reason: Literal[INPUT_FAILURES + ("all_queries_failed",)]

    @model_validator(mode="after")
    def _stage_reason(self) -> Failure:
        if (self.stage == "query") != (self.reason == "all_queries_failed"):
            raise ValueError("all_queries_failed is the only query-stage failure reason")
        return self


class QueryError(_Model):
    code: QueryFailureCode | LimitCode
    http_status: Annotated[int, Field(ge=100, le=599)] | None
    # Task 9B.5: present with `authentication_failed` only, omitted from the rendering
    # otherwise (documents without an authentication failure are unchanged)
    auth_reason: Literal[AUTH_REASONS] | None = None

    @model_validator(mode="after")
    def _auth_reason_with_authentication_failed_only(self) -> QueryError:
        if (self.code == "authentication_failed") != (self.auth_reason is not None):
            raise ValueError("auth_reason is required with authentication_failed and forbidden otherwise")
        return self

    @model_serializer(mode="wrap")
    def _omit_absent_auth_reason(self, handler: Any) -> dict:
        data = handler(self)
        if data.get("auth_reason") is None:
            data.pop("auth_reason", None)
        return data


class Scope(_Model):
    """One resource-group query and what became of the events it returned."""

    subscription_id: Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]
    resource_group: Annotated[str, _check(_valid_resource_group, "resource group name")]
    status: Literal["complete", "truncated", "failed"]
    error: QueryError | None
    pages: Count
    events_returned: Count  # processed events: events_kept + every dropped count
    events_kept: Count
    dropped: dict[DropReason, Annotated[int, Field(ge=1)]]

    @model_validator(mode="after")
    def _consistent(self) -> Scope:
        if self.status == "complete" and self.error is not None:
            raise ValueError("a complete scope has no error")
        if self.status == "truncated" and (self.error is None or self.error.code not in LIMIT_CODES):
            raise ValueError("a truncated scope needs a limit code")
        if self.status == "failed" and (self.error is None or self.error.code not in QUERY_FAILURE_CODES):
            raise ValueError("a failed scope needs a failure code")
        if list(self.dropped) != sorted(self.dropped):
            raise ValueError("dropped reasons must be sorted")
        if self.events_returned != self.events_kept + sum(self.dropped.values()):
            raise ValueError("events_returned must equal events_kept plus every dropped count")
        return self


class Target(_Model):
    """A drifted resource and whether its Activity Log was queried."""

    address: Address
    resource_id: TargetResourceId | None
    status: TargetStatus
    matched_events: Count

    @model_validator(mode="after")
    def _consistent(self) -> Target:
        without_id = self.status in ("no_resource_id", "invalid_resource_id")
        if without_id != (self.resource_id is None):
            raise ValueError("resource_id is null exactly for no_resource_id / invalid_resource_id")
        arm = parse_resource_id(self.resource_id)
        if arm is not None and (self.status == "unsupported_scope") != (arm.resource_group is None):
            raise ValueError("unsupported_scope is exactly a resource ID without a resource group")
        if self.status not in _QUERIED_STATUSES and self.matched_events:
            raise ValueError("a target that was not queried has no matched events")
        return self


class Match(_Model):
    address: Address
    relation: Relation


class Event(_Model):
    """One Activity Log event, allowlisted and validated. Untrusted external data."""

    event_data_id: Token
    correlation_id: Token | None
    operation_id: Token | None
    event_timestamp: Timestamp
    submission_timestamp: Timestamp | None
    operation_name: OperationName
    status: Status | None
    sub_status: SubStatus | None
    category: Category
    level: Level | None
    resource_id: EventResourceId
    caller: Caller | None
    event_phase: EventPhase
    caller_type: CallerType
    client_app: ClientApp
    pipeline_identity: bool | None
    anomalies: list[Anomaly]
    matches: Annotated[list[Match], Field(min_length=1)]

    @model_validator(mode="after")
    def _consistent(self) -> Event:
        if self.anomalies != sorted(set(self.anomalies)):
            raise ValueError("anomalies must be sorted and unique")
        if {"claims_missing", "claims_rejected"} & set(self.anomalies) and (
                self.caller_type != "unknown" or self.client_app != "unknown" or self.pipeline_identity is not None):
            raise ValueError("without usable claims, caller_type and client_app are unknown and "
                             "pipeline_identity is null")
        early = (self.submission_timestamp is not None
                 and parse_timestamp(self.submission_timestamp) < parse_timestamp(self.event_timestamp))
        if early != ("submission_before_event" in self.anomalies):
            raise ValueError("submission_before_event is set exactly when the submission time is earlier")
        addresses = [m.address for m in self.matches]
        if addresses != sorted(set(addresses)) or len({m.relation for m in self.matches}) != 1:
            raise ValueError("matches must be sorted, unique and share one relation")
        if self.caller is None and not {"caller_missing", "caller_rejected"} & set(self.anomalies):
            raise ValueError("a null caller must be explained by caller_missing or caller_rejected")
        if self.caller is not None and {"caller_missing", "caller_rejected"} & set(self.anomalies):
            raise ValueError("a kept caller cannot be missing or rejected")
        if self.status is None and not {"status_missing", "status_rejected"} & set(self.anomalies):
            raise ValueError("a null status must be explained by status_missing or status_rejected")
        return self


class ActivityLogEvidence(_Model):
    """The whole `activity_log_evidence.json` document (evidence_version 2)."""

    evidence_version: Literal["2"]
    source: Literal["azure_activity_log"]
    trust: Literal["untrusted_external"]
    outcome: Literal["complete", "incomplete", "failed"]
    failure: Failure | None
    subject: Subject
    window: Window | None
    collection: Collection | None
    scopes: list[Scope]
    targets: list[Target]
    events: list[Event]

    @model_validator(mode="after")
    def _invariants(self) -> ActivityLogEvidence:
        problems = _evidence_problems(self)
        if problems:
            raise ValueError("; ".join(problems))
        return self


_QUERIED_STATUSES = ("queried", "query_failed", "query_incomplete")
_SCOPE_TO_TARGET = {"complete": "queried", "truncated": "query_incomplete", "failed": "query_failed"}


def _expected_outcome(scope_statuses: list[str], target_statuses: list[str]) -> str:
    if scope_statuses and all(status == "failed" for status in scope_statuses):
        return "failed"
    if all(status == "queried" for status in target_statuses):
        return "complete"
    return "incomplete"


def _evidence_problems(doc: ActivityLogEvidence) -> list[str]:
    problems: list[str] = []
    if (doc.outcome == "failed") != (doc.failure is not None):
        problems.append("failure is set exactly when the outcome is failed")
    if doc.failure is not None and doc.failure.stage == "input":
        if doc.window is not None or doc.collection is not None or doc.scopes or doc.targets or doc.events:
            problems.append("an input failure has no window, collection, scopes, targets or events")
        return problems
    if doc.window is None or doc.collection is None:
        problems.append("window and collection are required unless the input failed")
        return problems
    if parse_timestamp(doc.window.end) != parse_timestamp(doc.collection.queried_at).replace(microsecond=0):
        problems.append("the window must end at queried_at (whole seconds)")
    delays = ingestion_delays_ms((e.event_timestamp, e.submission_timestamp) for e in doc.events)
    if (doc.collection.ingestion_delay_samples != len(delays)
            or doc.collection.max_ingestion_delay_ms != (max(delays) if delays else None)):
        problems.append("the ingestion delay does not match the events")

    scope_keys = [(s.subscription_id, s.resource_group.lower()) for s in doc.scopes]
    if scope_keys != sorted(set(scope_keys)):
        problems.append("scopes must be sorted by subscription and resource group, without repeats")
    addresses = [t.address for t in doc.targets]
    if addresses != sorted(set(addresses)):
        problems.append("targets must be sorted by address, without repeats")

    scope_status = dict(zip(scope_keys, (s.status for s in doc.scopes)))
    used_scopes = set()
    for target in doc.targets:
        arm = parse_resource_id(target.resource_id)
        if target.status in _QUERIED_STATUSES:
            key = (arm.subscription_id, arm.resource_group.lower())
            used_scopes.add(key)
            if _SCOPE_TO_TARGET.get(scope_status.get(key)) != target.status:
                problems.append(f"target {target.address}: status does not match its scope")
    if used_scopes != set(scope_keys):
        problems.append("every scope must belong to at least one queried target")

    expected = _expected_outcome([s.status for s in doc.scopes], [t.status for t in doc.targets])
    if doc.outcome != expected:
        problems.append(f"outcome must be {expected}")
    if doc.failure is not None and doc.failure.stage == "query" and expected != "failed":
        problems.append("all_queries_failed needs every scope failed")

    order = [(e.event_timestamp, e.event_data_id.lower()) for e in doc.events]
    if order != sorted(order):
        problems.append("events must be sorted by event_timestamp then event_data_id")
    if len({e.event_data_id.lower() for e in doc.events}) != len(doc.events):
        problems.append("event_data_id must be unique")

    start, end = parse_timestamp(doc.window.start), parse_timestamp(doc.window.end)
    targets = {t.address: t for t in doc.targets}
    matched = Counter()
    kept = Counter()
    for event in doc.events:
        moment = parse_timestamp(event.event_timestamp)
        if not start <= moment <= end:
            problems.append(f"event {event.event_data_id} is outside the window")
        arm = parse_resource_id(event.resource_id)
        scope_key = (arm.subscription_id, arm.resource_group.lower())
        if scope_key not in scope_status:
            problems.append(f"event {event.event_data_id} is outside every scope")
        kept[scope_key] += 1
        for match in event.matches:
            target = targets.get(match.address)
            if target is None or target.status not in _QUERIED_STATUSES:
                problems.append(f"event {event.event_data_id} matches an unknown or unqueried target")
                continue
            relation = relation_to(arm.key, parse_resource_id(target.resource_id).key)
            if relation != match.relation:
                problems.append(f"event {event.event_data_id}: relation to {match.address} is wrong")
            matched[match.address] += 1
    for target in doc.targets:
        if target.matched_events != matched[target.address]:
            problems.append(f"target {target.address}: matched_events does not match the events")
    for scope, key in zip(doc.scopes, scope_keys):
        if scope.events_kept != kept[key]:
            problems.append(f"scope {scope.resource_group}: events_kept does not match the events")
    return problems


def relation_to(event_key: str, target_key: str) -> str | None:
    """How a (case-folded) event resource ID relates to a target's: `exact`, `extension`
    (only a verified extension type, G6), `descendant` (anything else below it) or None."""
    if event_key == target_key:
        return "exact"
    if event_key.startswith(target_key + "/"):
        return "extension" if event_key[len(target_key):] in VERIFIED_EXTENSIONS else "descendant"
    return None


def ingestion_delays_ms(times: Iterable[tuple[str, str | None]]) -> list[int]:
    """`submission - event` in whole milliseconds (rounded down) for each (event
    timestamp, submission timestamp) pair whose submission time exists and is not
    earlier than the event time."""
    delays = []
    for moment, submission in times:
        if submission is None:
            continue
        delta = parse_timestamp(submission) - parse_timestamp(moment)
        if delta >= timedelta(0):
            delays.append(delta // timedelta(milliseconds=1))
    return delays


def render_evidence(evidence: ActivityLogEvidence) -> str:
    """The evidence as JSON: sorted keys, two-space indent, ASCII, trailing newline
    (the drift report's style). Identical evidence always renders identically."""
    return json.dumps(evidence.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# Targets, window, query filter
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TargetSpec:
    """A drifted resource before querying. `status` is final unless it is "pending"."""

    address: str
    arm: ArmId | None
    status: str  # "pending" | no_resource_id | invalid_resource_id | unsupported_scope


def _id_marked_sensitive(masks: tuple) -> bool:
    return any(mask is True or (isinstance(mask, dict) and mask.get("id") is True) for mask in masks)


def _plan_id(state: Any, real: Any) -> Any:
    for view in (state, real):
        if isinstance(view, dict) and view.get("id") is not None:
            return view["id"]
    return None


def select_targets(evaluation: Evaluation) -> list[TargetSpec]:
    """Every managed resource with a resource_drift entry, sorted by address.

    Selection depends only on the presence of the drift entry, never on its
    Terraform actions (update, delete, create, replace, ...) or on the report's
    classification: an externally deleted object is a target like an externally
    changed one. The resource ID comes from the parsed plan, the drift entry's
    `before` (recorded state) first, else its `after` (refreshed state); the drift
    report itself has no ARM IDs. An id marked sensitive is not used. A drifted
    resource without a usable ID stays a target with a non-queried status
    (no_resource_id, invalid_resource_id, unsupported_scope), never silently
    dropped. Resources without a drift entry (configuration-only changes) are
    never targets: nothing outside Terraform was detected there.
    """
    if evaluation.parsed is None:
        return []
    specs = []
    for ev in evaluation.parsed.resources:  # managed resources only (the parser drops data sources)
        if ev.drift_actions is None:
            continue
        raw = None if _id_marked_sensitive(ev.sensitive_masks) else _plan_id(ev.state, ev.real)
        if not isinstance(raw, str) or not raw:
            specs.append(TargetSpec(ev.address, None, "no_resource_id"))
            continue
        arm = parse_resource_id(raw)
        if arm is None:
            status = "invalid_resource_id"
        elif arm.resource_group is None:
            status = "unsupported_scope"
        else:
            status = "pending"
        specs.append(TargetSpec(ev.address, arm, status))
    return sorted(specs, key=lambda s: s.address)


class _InputError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _aware(moment: Any) -> bool:
    return isinstance(moment, datetime) and moment.utcoffset() is not None


def build_window(queried_at: datetime, lookback_days: int, window_start: datetime | None = None) -> Window:
    """The query window on whole seconds, UTC, ending at `queried_at`.

    Without `window_start`: [queried_at - lookback_days, queried_at] (`lookback`).
    With it: [window_start rounded down to the second, queried_at] (`explicit`); it
    must be earlier than the end and at most MAX_LOOKBACK_DAYS before it.
    """
    if type(lookback_days) is not int or not 1 <= lookback_days <= MAX_LOOKBACK_DAYS:
        raise _InputError("invalid_lookback")
    if not _aware(queried_at):
        raise _InputError("invalid_query_time")
    end = queried_at.astimezone(timezone.utc).replace(microsecond=0)
    if window_start is None:
        return Window(
            basis="lookback",
            start=format_timestamp(end - timedelta(days=lookback_days)),
            end=format_timestamp(end),
            lookback_days=lookback_days,
        )
    if not _aware(window_start):
        raise _InputError("invalid_window_start")
    start = window_start.astimezone(timezone.utc).replace(microsecond=0)
    if not end - timedelta(days=MAX_LOOKBACK_DAYS) <= start < end:
        raise _InputError("invalid_window_start")
    return Window(
        basis="explicit",
        start=format_timestamp(start),
        end=format_timestamp(end),
        lookback_days=None,
    )


def check_not_before(queried_at: datetime, not_before: datetime | None) -> None:
    """A collection may not query before `not_before` (Phase 9B, G8). The collector
    never waits: the caller schedules the collection."""
    if not_before is None:
        return
    if not _aware(not_before):
        raise _InputError("invalid_not_before")
    if queried_at < not_before:
        raise _InputError("query_before_not_before")


def check_pipeline_principal(value: str | None) -> str | None:
    """The pipeline's client ID (a GUID), lower case; None when not given."""
    if value is None:
        return None
    if not isinstance(value, str) or not _GUID.fullmatch(value):
        raise _InputError("invalid_pipeline_principal")
    return value.lower()


def query_filter(window: Window, resource_group: str) -> str:
    """The Activity Log `$filter` for one resource group (the only shape used)."""
    if not _valid_resource_group(resource_group):
        raise ValueError("invalid resource group name")
    start = parse_timestamp(window.start).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = parse_timestamp(window.end).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"eventTimestamp ge '{start}' and eventTimestamp le '{end}' and resourceGroupName eq '{resource_group}'"


# ---------------------------------------------------------------------------
# Source protocol
# ---------------------------------------------------------------------------

class SourceError(Exception):
    """A query failed; `code` is one of QUERY_FAILURE_CODES."""

    def __init__(self, code: str, http_status: int | None = None, auth_reason: str | None = None) -> None:
        if code not in QUERY_FAILURE_CODES:
            raise ValueError(f"unknown query failure code {code!r}")
        if code == "authentication_failed":
            auth_reason = auth_reason or ("arm_rejected" if http_status == 401 else "no_aadsts")
            if auth_reason not in AUTH_REASONS:
                raise ValueError(f"unknown auth reason {auth_reason!r}")
        elif auth_reason is not None:
            raise ValueError("auth_reason is only valid with authentication_failed")
        super().__init__(code)
        self.code = code
        self.http_status = http_status
        self.auth_reason = auth_reason


@dataclass(frozen=True)
class Page:
    """One page of raw, REST-shaped Activity Log records (untrusted)."""

    events: tuple
    has_more: bool


class ActivityLogSource(Protocol):
    def pages(self, subscription_id: str, query_filter: str) -> Iterator[Page]:
        """Yield the result pages in order; raise SourceError when a request fails."""
        ...


@dataclass(frozen=True)
class Limits:
    max_pages_per_scope: int = 100
    max_events_per_scope: int = 10_000
    deadline_seconds: float = 180.0  # whole run, checked before each page request

    def __post_init__(self) -> None:
        for name in ("max_pages_per_scope", "max_events_per_scope"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.deadline_seconds, (int, float)) or not self.deadline_seconds > 0:
            raise ValueError("deadline_seconds must be positive")


DEFAULT_LIMITS = Limits()


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

@dataclass
class _ScopePlan:
    subscription_id: str
    resource_group: str
    index: dict[str, list[str]]  # target key -> addresses (sorted)


def _localizable(raw: Mapping, key: str) -> tuple[bool, Any]:
    """(present, value) of a REST LocalizableString field; a non-object is present but invalid."""
    field = raw.get(key)
    if field is None:
        return False, None
    if not isinstance(field, dict):
        return True, None
    value = field.get("value")
    if value is None or value == "":
        return False, None
    return True, value


def _optional_token(raw: Mapping, key: str, anomaly: str, anomalies: list[str]) -> str | None:
    value = raw.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, str) and _TOKEN.fullmatch(value):
        return value
    anomalies.append(anomaly)
    return None


def _canonical(value: Any, allowed: tuple[str, ...]) -> str | None:
    if not isinstance(value, str):
        return None
    folded = {a.lower(): a for a in allowed}
    return folded.get(value.lower())


def _match(arm: ArmId, scope: _ScopePlan) -> list[dict] | None:
    """Most specific target the event's resource is, or is under (`relation_to`)."""
    parts = arm.key.split("/")
    for end in range(len(parts), 0, -1):
        prefix = "/".join(parts[:end])
        if prefix in scope.index:
            relation = relation_to(arm.key, prefix)
            return [{"address": a, "relation": relation} for a in scope.index[prefix]]
    return None


_EVENT_PHASES = {"beginrequest": "begin", "endrequest": "end"}


def derive_identity(claims: Any, pipeline_principal: str | None) -> tuple[dict, str | None]:
    """(caller_type, client_app, pipeline_identity) from the raw claims, and an anomaly.

    Only `idtyp`, `appid` and the presence of `xms_mirid` are read; no claim value is
    returned or stored. `pipeline_identity` is True/False only when both `appid` and the
    pipeline principal are known (a user's token carries the client application,
    e.g. the Azure Portal, as `appid`, never the pipeline's ID).
    """
    unknown = {"caller_type": "unknown", "client_app": "unknown", "pipeline_identity": None}
    if claims is None:  # absent; an object without the claims read is present but uninformative
        return unknown, "claims_missing"
    if not isinstance(claims, dict):
        return unknown, "claims_rejected"
    idtyp = claims.get("idtyp")
    idtyp = idtyp.lower() if isinstance(idtyp, str) else None
    if idtyp == "user":
        caller_type = "user"
    elif idtyp == "app":
        caller_type = "managed_identity" if claims.get("xms_mirid") else "service_principal"
    else:
        caller_type = "unknown"
    appid = claims.get("appid")
    appid = appid.lower() if isinstance(appid, str) and _GUID.fullmatch(appid) else None
    client_app = "unknown" if appid is None else CLIENT_APPS.get(appid, "other_application")
    pipeline_identity = None if appid is None or pipeline_principal is None else appid == pipeline_principal
    return {"caller_type": caller_type, "client_app": client_app, "pipeline_identity": pipeline_identity}, None


def normalize_event(raw: Any, window: Window, scope: _ScopePlan,
                    pipeline_principal: str | None = None) -> tuple[dict | None, str | None]:
    """(event, None) for a kept event or (None, drop reason). Never raises for bad data."""
    if not isinstance(raw, dict):
        return None, "malformed_event"
    event_data_id = raw.get("eventDataId")
    if not isinstance(event_data_id, str) or not _TOKEN.fullmatch(event_data_id):
        return None, "invalid_event_data_id"
    moment = parse_timestamp(raw.get("eventTimestamp"))
    if moment is None:
        return None, "invalid_timestamp"
    if not parse_timestamp(window.start) <= moment <= parse_timestamp(window.end):
        return None, "timestamp_outside_window"
    arm = parse_resource_id(raw.get("resourceId"))
    if arm is None or arm.resource_group is None:
        return None, "invalid_resource_id"
    _, operation_name = _localizable(raw, "operationName")
    if (not isinstance(operation_name, str) or len(operation_name) > MAX_OPERATION_NAME_LENGTH
            or not _OPERATION_NAME.fullmatch(operation_name)):
        return None, "invalid_operation_name"
    _, category = _localizable(raw, "category")
    category = _canonical(category, KEPT_CATEGORIES)
    if category is None:
        return None, "excluded_category"
    matches = _match(arm, scope)
    if matches is None:
        return None, "out_of_scope"

    anomalies: list[str] = []
    submission = raw.get("submissionTimestamp")
    submission_moment = parse_timestamp(submission)
    if submission is not None and submission_moment is None:
        anomalies.append("submission_timestamp_rejected")
    elif submission_moment is not None and submission_moment < moment:
        anomalies.append("submission_before_event")

    present, status = _localizable(raw, "status")
    if not present:
        anomalies.append("status_missing")
        status = None
    elif not isinstance(status, str) or len(status) > 64 or not _STATUS.fullmatch(status):
        anomalies.append("status_rejected")
        status = None

    present, sub_status = _localizable(raw, "subStatus")
    if present and (not isinstance(sub_status, str) or len(sub_status) > 64 or not _SUB_STATUS.fullmatch(sub_status)):
        anomalies.append("sub_status_rejected")
        sub_status = None
    elif not present:
        sub_status = None

    level = raw.get("level")
    if level is not None and level != "":
        canonical_level = _canonical(level, LEVELS)
        if canonical_level is None:
            anomalies.append("level_rejected")
        level = canonical_level
    else:
        level = None

    caller = raw.get("caller")
    if caller is None or caller == "":
        anomalies.append("caller_missing")
        caller = None
    elif not valid_caller(caller):
        anomalies.append("caller_rejected")
        caller = None

    _, event_name = _localizable(raw, "eventName")
    event_phase = _EVENT_PHASES.get(event_name.lower(), "unknown") if isinstance(event_name, str) else "unknown"
    identity, claims_anomaly = derive_identity(raw.get("claims"), pipeline_principal)
    if claims_anomaly is not None:
        anomalies.append(claims_anomaly)

    event = {
        "event_data_id": event_data_id,
        "correlation_id": _optional_token(raw, "correlationId", "correlation_id_rejected", anomalies),
        "operation_id": _optional_token(raw, "operationId", "operation_id_rejected", anomalies),
        "event_timestamp": format_timestamp(moment),
        "submission_timestamp": format_timestamp(submission_moment) if submission_moment else None,
        "operation_name": operation_name,
        "status": status,
        "sub_status": sub_status,
        "category": category,
        "level": level,
        "resource_id": arm.text,
        "caller": caller,
        "event_phase": event_phase,
        **identity,
        "anomalies": sorted(set(anomalies)),
        "matches": sorted(matches, key=lambda m: m["address"]),
    }
    return event, None


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

@dataclass
class _ScopeResult:
    plan: _ScopePlan
    status: str = "complete"
    error: dict | None = None
    pages: int = 0
    returned: int = 0


def _scope_plans(targets: list[TargetSpec]) -> list[_ScopePlan]:
    plans: dict[tuple[str, str], _ScopePlan] = {}
    for spec in targets:  # sorted by address, so the displayed resource group name is stable
        if spec.status != "pending":
            continue
        key = (spec.arm.subscription_id, spec.arm.resource_group.lower())
        plan = plans.setdefault(key, _ScopePlan(spec.arm.subscription_id, spec.arm.resource_group, {}))
        plan.index.setdefault(spec.arm.key, []).append(spec.address)
    return [plans[key] for key in sorted(plans)]


def _run_scope(plan: _ScopePlan, source: ActivityLogSource, window: Window, limits: Limits,
               monotonic: Callable[[], float], deadline: float,
               occurrences: list[tuple[int, dict]], dropped: list[Counter], index: int,
               pipeline_principal: str | None = None) -> _ScopeResult:
    result = _ScopeResult(plan)
    if monotonic() >= deadline:
        result.status, result.error = "truncated", {"code": "deadline_exceeded", "http_status": None}
        return result
    pages = source.pages(plan.subscription_id, query_filter(window, plan.resource_group))
    try:
        for page in pages:
            result.pages += 1
            for raw in page.events:
                if result.returned >= limits.max_events_per_scope:
                    result.status, result.error = "truncated", {"code": "event_limit_exceeded", "http_status": None}
                    return result
                result.returned += 1
                event, reason = normalize_event(raw, window, plan, pipeline_principal)
                if event is None:
                    dropped[index][reason] += 1
                else:
                    occurrences.append((index, event))
            if not page.has_more:
                return result
            if result.returned >= limits.max_events_per_scope:  # do not fetch a page that cannot be used
                result.status, result.error = "truncated", {"code": "event_limit_exceeded", "http_status": None}
                return result
            if result.pages >= limits.max_pages_per_scope:
                result.status, result.error = "truncated", {"code": "page_limit_exceeded", "http_status": None}
                return result
            if monotonic() >= deadline:
                result.status, result.error = "truncated", {"code": "deadline_exceeded", "http_status": None}
                return result
        # the source stopped without a final page (none at all, or after promising
        # more): the result cannot be shown to be complete
        result.status, result.error = "failed", {"code": "invalid_response", "http_status": None}
        return result
    except SourceError as exc:
        result.status, result.error = "failed", {"code": exc.code, "http_status": exc.http_status}
        if exc.auth_reason is not None:
            result.error["auth_reason"] = exc.auth_reason
        return result
    finally:
        close = getattr(pages, "close", None)
        if close is not None:
            close()


def _deduplicate(occurrences: list[tuple[int, dict]], dropped: list[Counter]) -> list[tuple[int, dict]]:
    """Keep one copy of identical repeats; drop every copy of a conflicting eventDataId."""
    groups: dict[str, list[tuple[int, dict]]] = {}
    for occurrence in occurrences:
        groups.setdefault(occurrence[1]["event_data_id"].lower(), []).append(occurrence)
    kept = []
    for group in groups.values():
        first = group[0][1]
        if all(event == first for _, event in group):
            kept.append(group[0])
            for scope_index, _ in group[1:]:
                dropped[scope_index]["duplicate"] += 1
        else:
            for scope_index, _ in group:
                dropped[scope_index]["conflicting_duplicate"] += 1
    return kept


def _subject(report: dict) -> dict:
    run = report.get("run") or {}
    plan = report.get("plan") or {}
    return {"run_id": run.get("run_id"), "plan_timestamp": plan.get("timestamp")}


def _failed_input(subject: dict, reason: str) -> ActivityLogEvidence:
    log_event(logger, logging.WARNING, "activity_log_input_failed",
              "Activity Log evidence not collected: invalid input", reason=reason)
    return ActivityLogEvidence.model_validate({
        "evidence_version": EVIDENCE_VERSION, "source": SOURCE, "trust": TRUST,
        "outcome": "failed", "failure": {"stage": "input", "reason": reason},
        "subject": subject, "window": None, "collection": None, "scopes": [], "targets": [], "events": [],
    })


def collect_evidence(
    plan_path: str,
    manifest_path: str,
    *,
    source: ActivityLogSource,
    queried_at: datetime,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    window_start: datetime | None = None,
    not_before: datetime | None = None,
    pipeline_principal: str | None = None,
    limits: Limits = DEFAULT_LIMITS,
    monotonic: Callable[[], float] = time.monotonic,
) -> ActivityLogEvidence:
    """Collect Activity Log evidence for the drifted resources of one detection run.

    The drift report is recomputed from the same plan and manifest (deterministic),
    so the targets always belong to that evidence; the plan files are only read.
    `source` is asked for pages only when there is something to query: no drift
    (including configuration-only changes), or drift without a usable resource ID,
    never reaches Azure. Bad input and failed queries are recorded in the result,
    never raised.

    `window_start` (optional) is the run-level start chosen by the caller (Task 9B.2:
    the earliest per-resource anchor or lookback start); without it the window is the
    lookback. `not_before` (optional) is the earliest allowed query time: an earlier
    `queried_at` fails with `query_before_not_before` before any query. One call is
    one collection; this function never waits or polls. `pipeline_principal` is the
    pipeline's client ID (GUID) for `pipeline_identity`; it is never written or logged.
    """
    evaluation = evaluate(plan_path, manifest_path)
    try:
        # the same contract check `drift-engine analyze` applies before writing a report
        DriftReport.model_validate(evaluation.report)
    except ValidationError:
        return _failed_input({"run_id": None, "plan_timestamp": None}, "evidence_failed")
    subject = _subject(evaluation.report)
    if evaluation.report["outcome"] != "succeeded":
        return _failed_input(subject, "evidence_failed")
    try:
        window = build_window(queried_at, lookback_days, window_start)
        check_not_before(queried_at, not_before)
        principal = check_pipeline_principal(pipeline_principal)
    except _InputError as exc:
        return _failed_input(subject, exc.reason)

    targets = select_targets(evaluation)
    plans = _scope_plans(targets)
    log_event(logger, logging.INFO, "activity_log_targets_selected", "Activity Log targets selected",
              targets=len(targets), scopes=len(plans),
              target_statuses=dict(sorted(Counter(t.status for t in targets).items())),
              window_basis=window.basis, lookback_days=window.lookback_days)

    deadline = monotonic() + limits.deadline_seconds
    occurrences: list[tuple[int, dict]] = []
    dropped = [Counter() for _ in plans]
    results = []
    for index, plan in enumerate(plans):
        result = _run_scope(plan, source, window, limits, monotonic, deadline, occurrences, dropped, index,
                            principal)
        results.append(result)
    kept = _deduplicate(occurrences, dropped)

    kept_per_scope = Counter(scope_index for scope_index, _ in kept)
    events = sorted((event for _, event in kept), key=lambda e: (e["event_timestamp"], e["event_data_id"].lower()))
    matched = Counter(m["address"] for event in events for m in event["matches"])
    scope_status = {(r.plan.subscription_id, r.plan.resource_group.lower()): r.status for r in results}

    target_docs = []
    for spec in targets:
        status = spec.status
        if status == "pending":
            status = _SCOPE_TO_TARGET[scope_status[(spec.arm.subscription_id, spec.arm.resource_group.lower())]]
        target_docs.append({
            "address": spec.address,
            "resource_id": spec.arm.text if spec.arm is not None else None,
            "status": status,
            "matched_events": matched[spec.address] if status in _QUERIED_STATUSES else 0,
        })

    scope_docs = []
    for index, result in enumerate(results):
        scope_docs.append({
            "subscription_id": result.plan.subscription_id,
            "resource_group": result.plan.resource_group,
            "status": result.status,
            "error": result.error,
            "pages": result.pages,
            "events_returned": result.returned,
            "events_kept": kept_per_scope[index],
            "dropped": dict(sorted(dropped[index].items())),
        })
        log_event(logger, logging.INFO if result.status == "complete" else logging.WARNING,
                  "activity_log_query_finished", "Activity Log query finished",
                  resource_group=result.plan.resource_group, status=result.status,
                  error=result.error["code"] if result.error else None,
                  http_status=result.error["http_status"] if result.error else None,
                  pages=result.pages, events_returned=result.returned, events_kept=kept_per_scope[index],
                  dropped=dict(sorted(dropped[index].items())))

    outcome = _expected_outcome([r.status for r in results], [t["status"] for t in target_docs])
    delays = ingestion_delays_ms((e["event_timestamp"], e["submission_timestamp"]) for e in events)
    collection = {
        "queried_at": format_timestamp(queried_at),
        "not_before": format_timestamp(not_before) if not_before is not None else None,
        "max_ingestion_delay_ms": max(delays) if delays else None,
        "ingestion_delay_samples": len(delays),
    }
    evidence = ActivityLogEvidence.model_validate({
        "evidence_version": EVIDENCE_VERSION, "source": SOURCE, "trust": TRUST,
        "outcome": outcome,
        "failure": {"stage": "query", "reason": "all_queries_failed"} if outcome == "failed" else None,
        "subject": subject,
        "window": window.model_dump(),
        "collection": collection,
        "scopes": scope_docs,
        "targets": target_docs,
        "events": events,
    })
    log_event(logger, logging.INFO if outcome == "complete" else logging.WARNING,
              "activity_log_collection_finished", "Activity Log evidence collected",
              outcome=outcome, targets=len(target_docs), scopes=len(scope_docs), events=len(events),
              max_ingestion_delay_ms=collection["max_ingestion_delay_ms"])
    return evidence


@dataclass(frozen=True)
class WindowCollection:
    """Events of one bounded historic window (`collect_window`). `scopes` hold the
    per-scope status, error code and drop counts; never a caller or an ID."""

    window: Window
    events: tuple
    scopes: tuple


def collect_window(
    source: ActivityLogSource,
    targets: Iterable[tuple[str, ArmId]],
    start: datetime,
    end: datetime,
    *,
    pipeline_principal: str | None = None,
    limits: Limits = DEFAULT_LIMITS,
    monotonic: Callable[[], float] = time.monotonic,
) -> WindowCollection:
    """Collect one bounded window [start, end] for explicit (address, ARM ID) targets
    (Task 9B.3, the local WHO path; Phase 9B G12). Unlike `collect_evidence` it needs
    no drift plan and its window need not end now. Start is rounded down and end up to
    whole seconds; the span must be positive and at most MAX_LOOKBACK_DAYS. The same
    scope query, normalization, limits and Azure safeguards apply. Raises ValueError
    for unusable input; query problems are reported per scope, never raised."""
    if not (_aware(start) and _aware(end)):
        raise ValueError("start and end must be timezone-aware")
    low = start.astimezone(timezone.utc).replace(microsecond=0)
    high = end.astimezone(timezone.utc)
    if high.microsecond:
        high = high.replace(microsecond=0) + timedelta(seconds=1)
    if not timedelta(0) < high - low <= timedelta(days=MAX_LOOKBACK_DAYS):
        raise ValueError(f"the window must span more than 0 and at most {MAX_LOOKBACK_DAYS} days")
    try:
        principal = check_pipeline_principal(pipeline_principal)
    except _InputError:
        raise ValueError("invalid pipeline principal") from None
    specs = []
    for address, arm in targets:
        if arm is None or arm.resource_group is None:
            raise ValueError("every target needs a resource-group-scoped ARM ID")
        specs.append(TargetSpec(address, arm, "pending"))
    window = Window(basis="explicit", start=format_timestamp(low), end=format_timestamp(high), lookback_days=None)
    plans = _scope_plans(sorted(specs, key=lambda spec: spec.address))
    deadline = monotonic() + limits.deadline_seconds
    occurrences: list[tuple[int, dict]] = []
    dropped = [Counter() for _ in plans]
    results = [_run_scope(plan, source, window, limits, monotonic, deadline, occurrences, dropped, index, principal)
               for index, plan in enumerate(plans)]
    kept = _deduplicate(occurrences, dropped)
    events = sorted((event for _, event in kept), key=lambda e: (e["event_timestamp"], e["event_data_id"].lower()))
    scopes = tuple({"resource_group": r.plan.resource_group, "status": r.status,
                    "error": r.error["code"] if r.error else None, "dropped": dict(sorted(dropped[i].items()))}
                   for i, r in enumerate(results))
    log_event(logger, logging.INFO, "activity_log_window_collected", "Activity Log window collected",
              scopes=len(scopes), events=len(events),
              statuses=dict(sorted(Counter(scope["status"] for scope in scopes).items())))
    return WindowCollection(window, tuple(Event.model_validate(e) for e in events), scopes)


# ---------------------------------------------------------------------------
# Azure Monitor source (the only code that talks to Azure)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RequestSettings:
    retry_total: int = 3
    retry_backoff_factor: float = 0.8
    retry_backoff_max: float = 30.0
    retry_after_max: float = 30.0  # a longer Retry-After is shortened to this
    retry_timeout: float = 120.0  # per page, all attempts together
    connection_timeout: float = 10.0
    read_timeout: float = 90.0  # the service answers within 75 s
    cli_process_timeout: int = 20  # az account get-access-token


class _BlockedRequest(Exception):
    """A request the source must not send (raised before it leaves the process)."""


def _allowed_url(url: str, subscription_id: str) -> bool:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    expected = _ACTIVITY_LOG_PATH.format(subscription_id=subscription_id.lower())
    return (
        parts.scheme == "https"
        and parts.hostname == ARM_HOST
        and port in (None, 443)
        and parts.username is None
        and parts.password is None
        and parts.path.lower() == expected
    )


def _request_guard(subscription_id: str) -> Callable[[Any], None]:
    """Pipeline hook, run after authentication on every attempt: only GET requests to
    this subscription's Activity Log endpoint may be sent. It blocks nextLinks and
    redirects to other hosts and the SDK's automatic provider registration (a POST)."""
    def guard(request: Any) -> None:
        http_request = request.http_request
        if http_request.method != "GET" or not _allowed_url(http_request.url, subscription_id):
            raise _BlockedRequest()
    return guard


def _localizable_record(value: Any) -> dict | None:
    if value is None:
        return None
    return {"value": getattr(value, "value", None)}


def _timestamp_record(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _event_record(event: Any) -> dict:
    """The allowlisted fields of an SDK EventData, in REST shape. Read attribute by
    attribute, so authorization, httpRequest, properties, description, tenantId and
    every claim except `idtyp`, `appid` and `xms_mirid` never leave the SDK object."""
    return {
        "eventDataId": getattr(event, "event_data_id", None),
        "correlationId": getattr(event, "correlation_id", None),
        "operationId": getattr(event, "operation_id", None),
        "eventTimestamp": _timestamp_record(getattr(event, "event_timestamp", None)),
        "submissionTimestamp": _timestamp_record(getattr(event, "submission_timestamp", None)),
        "operationName": _localizable_record(getattr(event, "operation_name", None)),
        "status": _localizable_record(getattr(event, "status", None)),
        "subStatus": _localizable_record(getattr(event, "sub_status", None)),
        "category": _localizable_record(getattr(event, "category", None)),
        "level": getattr(event, "level", None),
        "resourceId": getattr(event, "resource_id", None),
        "caller": getattr(event, "caller", None),
        "eventName": _localizable_record(getattr(event, "event_name", None)),
        "claims": _claims_record(getattr(event, "claims", None)),
    }


# The only claims read (Task 9B.1, G13): `appid`, `idtyp` and whether `xms_mirid` is
# present. Every other claim (names, UPN, object IDs, IP address, ...) stays in the
# SDK object.
def _claims_record(claims: Any) -> Any:
    """The claims `derive_identity` reads, or the non-object marker for invalid claims."""
    if claims is None:
        return None
    if not isinstance(claims, dict):
        return []
    record = {key: claims[key] for key in ("appid", "idtyp") if key in claims}
    if claims.get("xms_mirid"):
        record["xms_mirid"] = True  # presence only: the value is a managed identity's resource ID
    return record


def _error_code(exc: BaseException) -> tuple[str, int | None]:
    """Map an exception raised while fetching a page to a fixed code."""
    from azure.core import exceptions as core

    if isinstance(exc, _BlockedRequest):
        return "blocked_request", None
    try:
        from azure.identity import CredentialUnavailableError
    except ImportError:  # pragma: no cover - azure-identity ships with the [azure] extra
        CredentialUnavailableError = ()
    if CredentialUnavailableError and isinstance(exc, CredentialUnavailableError):
        return "credential_unavailable", None
    if isinstance(exc, core.ClientAuthenticationError):
        return "authentication_failed", _status(exc)
    if isinstance(exc, (core.ServiceRequestTimeoutError, core.ServiceResponseTimeoutError)):
        return "timeout", None
    if isinstance(exc, (core.DecodeError, core.DeserializationError)):
        return "invalid_response", None
    if isinstance(exc, core.HttpResponseError):
        status = _status(exc)
        if status == 400:
            return "bad_request", status
        if status == 403:
            return "authorization_failed", status
        if status == 429:
            return "throttled", status
        if status is not None and 500 <= status <= 599:
            return "service_error", status
        return "http_error", status
    if isinstance(exc, (core.ServiceRequestError, core.ServiceResponseError)):
        return "connection_failed", None
    if isinstance(exc, core.AzureError):
        return "azure_error", None
    # TypeError/ValueError/AttributeError/KeyError from inside the SDK's page parsing,
    # e.g. a page whose `value` is missing.
    return "invalid_response", None


def _status(exc: Any) -> int | None:
    status = getattr(exc, "status_code", None)
    return status if type(status) is int and 100 <= status <= 599 else None


def _auth_reason(exc: BaseException, http_status: int | None) -> str:
    """The fixed AUTH_REASONS value for an `authentication_failed` exception. Only the
    number after "AADSTS" is read from the exception text; the text is never kept."""
    if http_status == 401:
        return "arm_rejected"
    match = _AADSTS.search(str(exc))
    if match is None:
        return "no_aadsts"
    return _AADSTS_REASONS.get(match.group(1), "other_aadsts")


class _RedactExceptionArguments(logging.Filter):
    """Task 9B.5: two azure-identity records can expose identifiers.

    - A failed `get_token` is logged at WARNING with the exception as an argument
      ("AzureCliCredential.get_token_info failed: <exception>"). For AzureCliCredential that
      text is Azure CLI's stderr: tenant and client IDs, trace and correlation IDs, a UPN,
      timestamps. Such records are kept; each exception argument becomes its type name and any
      traceback is dropped.
    - A successful `get_token` is logged at DEBUG with the token's claims pre-formatted into
      the message ("[Authenticated account] Client ID ... Tenant ID ... User Principal Name
      ... Object ID"), which no argument redaction can reach. Every azure.identity record
      below WARNING is therefore dropped (only when a host enables those levels do they exist).
    Installed only on azure.identity loggers; no other logger is affected."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno < logging.WARNING:
            return False
        # LogRecord keeps positional arguments as a tuple (only a single mapping is unwrapped)
        if isinstance(record.args, tuple) and any(isinstance(a, BaseException) for a in record.args):
            record.args = tuple(type(a).__name__ if isinstance(a, BaseException) else a for a in record.args)
        if record.exc_info:
            record.exc_info, record.exc_text = None, None
        return True


_REDACT_EXCEPTION_ARGUMENTS = _RedactExceptionArguments()


def _redact_azure_identity_logs() -> None:
    """Install the redaction filter on every `azure.identity` logger (they are created when
    the package is imported; logger filters are not inherited by child loggers). Idempotent;
    other loggers are not touched."""
    for name in list(logging.root.manager.loggerDict):
        if name == "azure.identity" or name.startswith("azure.identity."):
            identity_logger = logging.getLogger(name)
            if _REDACT_EXCEPTION_ARGUMENTS not in identity_logger.filters:
                identity_logger.addFilter(_REDACT_EXCEPTION_ARGUMENTS)


class AzureMonitorSource:
    """ActivityLogSource backed by azure-mgmt-monitor (`[azure]` extra).

    `credential` defaults to `AzureCliCredential`, created on first use; tests pass a
    fake credential and an azure-core `transport`. Clients are created per
    subscription on first use, so constructing this source never imports the SDK.
    """

    def __init__(self, credential: Any = None, *, transport: Any = None,
                 settings: RequestSettings = RequestSettings()) -> None:
        self._credential = credential
        self._transport = transport
        self._settings = settings
        self._clients: dict[str, Any] = {}

    def _get_credential(self) -> Any:
        if self._credential is None:
            from azure.identity import AzureCliCredential

            self._credential = AzureCliCredential(process_timeout=self._settings.cli_process_timeout)
        return self._credential

    def _client(self, subscription_id: str) -> Any:
        if subscription_id in self._clients:
            return self._clients[subscription_id]
        try:
            import azure.identity  # noqa: F401  (its loggers must exist for the redaction filter)
            from azure.core.pipeline.policies import RetryPolicy
            from azure.mgmt.monitor import MonitorManagementClient
            credential = self._get_credential()
        except ImportError:
            raise SourceError("azure_sdk_unavailable") from None
        _redact_azure_identity_logs()
        settings = self._settings

        class BoundedRetryPolicy(RetryPolicy):
            def get_retry_after(self, response: Any) -> float | None:
                retry_after = super().get_retry_after(response)
                return None if retry_after is None else min(retry_after, settings.retry_after_max)

        kwargs: dict[str, Any] = {
            "retry_policy": BoundedRetryPolicy(
                retry_total=settings.retry_total,
                retry_backoff_factor=settings.retry_backoff_factor,
                retry_backoff_max=settings.retry_backoff_max,
                timeout=settings.retry_timeout,
            ),
            "permit_redirects": False,
            "raw_request_hook": _request_guard(subscription_id),
            "logging_enable": False,
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport
        client = MonitorManagementClient(credential, subscription_id, base_url=ARM_ENDPOINT,
                                         credential_scopes=[ARM_CREDENTIAL_SCOPE], **kwargs)
        self._clients[subscription_id] = client
        return client

    def pages(self, subscription_id: str, query_filter: str) -> Iterator[Page]:
        client = self._client(subscription_id)
        from azure.core.exceptions import AzureError

        pager = client.activity_logs.list(
            filter=query_filter,
            connection_timeout=self._settings.connection_timeout,
            read_timeout=self._settings.read_timeout,
        ).by_page()
        while True:
            try:
                page = next(pager, None)
                if page is None:  # pragma: no cover - the pager always returns a page when asked
                    return
                events = tuple(_event_record(event) for event in page)
            except (AzureError, _BlockedRequest, TypeError, ValueError, AttributeError, KeyError) as exc:
                code, http_status = _error_code(exc)
                reason = _auth_reason(exc, http_status) if code == "authentication_failed" else None
                raise SourceError(code, http_status, reason) from None
            next_link = pager.continuation_token
            yield Page(events, has_more=bool(next_link))
            if not next_link:
                return
            if not _allowed_url(next_link, subscription_id):
                # checked here as well as in the pipeline hook: a nextLink to another
                # host or path is never requested, and the scope is not complete
                raise SourceError("blocked_request")
