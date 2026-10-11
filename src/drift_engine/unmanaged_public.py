"""Public contract of the unmanaged resource inventory (Task 10.4, `unmanaged_inventory_version` 1).

The strict model of `unmanaged_inventory.json`, its invariants and its rendering, without the code that
collects it (drift_engine.inventory, which reads Azure and plan.json). This module loads no restricted
module (Activity Log, attribution, investigation, WHO) and no Azure SDK, so ai_engine may import it
(Phase 9B G14 addendum, Task 10.4), as drift_engine.unmanaged_cost does.

Published per resource (decision 3, user-approved 2026-10-11): ARM type, resource name (unless it looks
like an identifier), resource group, location and allowlisted pricing inputs; never an ARM resource ID,
subscription ID, tag, IP address or any other property. Every document passes the fail-closed public
leak scan (investigation_public.leak_findings) as part of its validation.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterator
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from drift_engine.investigation_public import leak_findings

INVENTORY_VERSION = "1"
INVENTORY_FILE = "unmanaged_inventory.json"
# drift_engine.activity_logs.QUERY_FAILURE_CODES, copied (kept equal by a test) so this module never
# loads the Activity Log module.
QUERY_FAILURE_CODES = (
    "authentication_failed", "authorization_failed", "azure_error", "azure_sdk_unavailable", "bad_request",
    "blocked_request", "connection_failed", "credential_unavailable", "http_error", "invalid_response",
    "service_error", "throttled", "timeout",
)
SCOPE_FAILURE_CODES = tuple(sorted(QUERY_FAILURE_CODES + ("not_found",)))
LIMIT_CODES = ("deadline_exceeded", "page_limit_exceeded", "resource_limit_exceeded")
INPUT_FAILURES = ("binding_mismatch", "invalid_plan", "no_managed_resource_group", "not_public_report")
CATEGORIES = ("attached_to_managed", "unmanaged")
NAME_STATUSES = ("published", "withheld_identifier_like")
DETAIL_STATUSES = ("failed", "not_required", "read")
POWER_STATES = ("deallocated", "deallocating", "running", "starting", "stopped", "stopping", "unknown")
# Fixed codes, always all published.
LIMITATIONS = (
    "terraform_managed_resource_groups_only",  # only resource groups Terraform manages are listed
    "arm_resource_list_only",  # what ARM's resource list returns (no data-plane objects, no hidden types)
    "exact_case_insensitive_id_match",  # Terraform `id` must equal the ARM ID (case-folded)
    "attached_to_managed_not_unmanaged",  # disks attached to a managed VM are reported, never priced
    "snapshot_after_plan",  # listed after the plan's refresh; a change in between is not reconciled
    "not_drift",  # unmanaged resources never change the drift result
)

_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
_LOCATION = re.compile(r"[a-z0-9]{1,40}")
_REF = r"^res-[1-9][0-9]*$"
_TYPE = r"^[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z][A-Za-z0-9]*)+(?:/[A-Za-z][A-Za-z0-9]*)+$"
_TIMESTAMP = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$"


# ---------------------------------------------------------------------------
# Contract (unmanaged_inventory_version 1)
# ---------------------------------------------------------------------------

class _Model(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


Count = Annotated[int, Field(ge=0)]
Ref = Annotated[str, Field(pattern=_REF)]
Token = Annotated[str, Field(pattern=rf"^{_TOKEN.pattern}$")]
ArmType = Annotated[str, Field(pattern=_TYPE, max_length=200)]


class Binding(_Model):
    run_id: str
    environment: str
    plan_timestamp: str
    drift_report_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ScopeResult(_Model):
    resource_group: Annotated[str, Field(pattern=r"^[-\w.()]{1,90}$")]
    status: Literal["complete", "truncated", "failed"]
    error: Literal[SCOPE_FAILURE_CODES + LIMIT_CODES] | None  # type: ignore[valid-type]
    http_status: Annotated[int, Field(ge=100, le=599)] | None
    pages: Count
    listed: Count

    @model_validator(mode="after")
    def _consistent(self) -> ScopeResult:
        if (self.status == "complete") != (self.error is None):
            raise ValueError("a scope has an error exactly when it is not complete")
        if self.status == "truncated" and self.error not in LIMIT_CODES:
            raise ValueError("a truncated scope needs a limit code")
        if self.status == "failed" and self.error not in SCOPE_FAILURE_CODES:
            raise ValueError("a failed scope needs a failure code")
        return self


class Link(_Model):
    """A parent or attachment: another listed resource (`ref`), a Terraform-managed resource (`address`),
    or a resource that is neither (`other`: outside the listed scope)."""
    kind: Literal["inventory", "managed", "other"]
    ref: Ref | None
    address: str | None

    @model_validator(mode="after")
    def _consistent(self) -> Link:
        if (self.ref is not None) != (self.kind == "inventory") \
                or (self.address is not None) != (self.kind == "managed"):
            raise ValueError("a link names a ref for inventory, an address for managed and nothing for other")
        return self


class PricingInputs(_Model):
    """Allowlisted properties only (no IDs, IP addresses, tags or names). Absent means not reported."""
    vm_size: Token | None = None
    os_type: Literal["Linux", "Windows"] | None = None
    license_type: Token | None = None
    priority: Literal["Regular", "Spot", "Low"] | None = None
    image_publisher: Token | None = None
    marketplace_plan: bool | None = None
    power_state: Literal[POWER_STATES] | None = None  # type: ignore[valid-type]
    disk_sku: Token | None = None
    disk_size_gb: Annotated[int, Field(ge=1, le=65536)] | None = None
    disk_tier: Token | None = None
    disk_state: Token | None = None
    max_shares: Annotated[int, Field(ge=1, le=100)] | None = None
    ip_sku: Token | None = None
    ip_tier: Token | None = None
    ip_version: Token | None = None
    ip_allocation: Token | None = None


class Item(_Model):
    ref: Ref
    type: ArmType
    name: Annotated[str, Field(min_length=1, max_length=600)] | None
    name_status: Literal[NAME_STATUSES]  # type: ignore[valid-type]
    resource_group: Annotated[str, Field(pattern=r"^[-\w.()]{1,90}$")]
    location: Annotated[str, Field(pattern=rf"^{_LOCATION.pattern}$")] | None
    category: Literal[CATEGORIES]  # type: ignore[valid-type]
    parent: Link | None
    attached_to: Link | None
    detail_status: Literal[DETAIL_STATUSES]  # type: ignore[valid-type]
    detail_error: Literal[SCOPE_FAILURE_CODES + ("invalid_details",)] | None  # type: ignore[valid-type]
    pricing_inputs: PricingInputs

    @model_validator(mode="after")
    def _consistent(self) -> Item:
        if (self.name is None) != (self.name_status != "published"):
            raise ValueError("a name is published exactly when name_status is published")
        if (self.detail_error is not None) != (self.detail_status == "failed"):
            raise ValueError("detail_error is set exactly when the detail read failed")
        if self.category == "attached_to_managed" and (self.attached_to is None or self.attached_to.kind != "managed"):
            raise ValueError("attached_to_managed needs a managed attachment")
        return self


class Counts(_Model):
    listed: Count  # distinct resources listed (after dropping duplicates)
    duplicates_dropped: Count
    managed: Count
    attached_to_managed: Count
    unmanaged: Count


class Inventory(_Model):
    unmanaged_inventory_version: Literal["1"]
    binding: Binding
    outcome: Literal["complete", "incomplete", "failed"]
    failure: Literal[INPUT_FAILURES + ("listing_failed",)] | None  # type: ignore[valid-type]
    collected_at: Annotated[str, Field(pattern=_TIMESTAMP)] | None
    scopes: list[ScopeResult]
    counts: Counts
    unmanaged_by_type: dict[ArmType, Annotated[int, Field(ge=1)]]
    resources: list[Item]
    limitations: list[Literal[LIMITATIONS]]  # type: ignore[valid-type]

    @model_validator(mode="after")
    def _invariants(self) -> Inventory:
        problems = inventory_problems(self)
        if problems:
            raise ValueError("; ".join(problems))
        return self


def inventory_problems(doc: Inventory) -> list[str]:
    problems: list[str] = []
    if list(doc.limitations) != list(LIMITATIONS):
        problems.append("limitations must be exactly the defined codes in order")
    if (doc.outcome == "failed") != (doc.failure is not None):
        problems.append("failure is set exactly when the outcome is failed")
    statuses = [s.status for s in doc.scopes]
    if doc.failure in INPUT_FAILURES:
        if doc.scopes or doc.resources or doc.collected_at is not None or any(doc.counts.model_dump().values()):
            problems.append("an input failure has no scopes, resources, counts or collection time")
        return problems
    if doc.collected_at is None or not doc.scopes:
        problems.append("a collection has a time and at least one scope")
    expected = ("failed" if "failed" in statuses else
                "incomplete" if "truncated" in statuses or any(r.detail_status == "failed" for r in doc.resources)
                else "complete")
    if doc.outcome != expected or (expected == "failed") != (doc.failure == "listing_failed"):
        problems.append(f"outcome must be {expected}")
    groups = [s.resource_group.lower() for s in doc.scopes]
    if groups != sorted(set(groups)):
        problems.append("scopes must be sorted and unique")
    refs = [r.ref for r in doc.resources]
    if refs != [f"res-{n}" for n in range(1, len(refs) + 1)]:
        problems.append("refs must be res-1..res-n in order")
    known = set(refs)
    for item in doc.resources:
        for link in (item.parent, item.attached_to):
            if link is not None and link.kind == "inventory" and (link.ref not in known or link.ref == item.ref):
                problems.append(f"{item.ref}: a link names an unknown ref")
        if item.resource_group.lower() not in groups:
            problems.append(f"{item.ref}: resource group outside every scope")
    by_category = Counter(r.category for r in doc.resources)
    counts = doc.counts
    if (counts.unmanaged, counts.attached_to_managed) != (by_category["unmanaged"], by_category["attached_to_managed"]):
        problems.append("counts do not match the resources")
    if counts.listed != counts.managed + counts.unmanaged + counts.attached_to_managed:
        problems.append("listed must equal managed + attached_to_managed + unmanaged")
    if sum(s.listed for s in doc.scopes) != counts.listed + counts.duplicates_dropped:
        problems.append("scope listings do not add up to the counts")
    by_type = Counter(r.type for r in doc.resources if r.category == "unmanaged")
    if doc.unmanaged_by_type != dict(sorted(by_type.items())):
        problems.append("unmanaged_by_type does not match the resources")
    findings = leak_findings(doc.model_dump(mode="json"))
    if findings:
        problems.append("identifier-like values: " + ", ".join(findings))
    return problems


def render_inventory(doc: Inventory) -> str:
    """Sorted keys, two-space indent, ASCII, trailing newline (the drift report's style)."""
    return json.dumps(doc.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def load_inventory(raw: Any) -> Inventory:
    """Validate a parsed inventory document (raises pydantic.ValidationError)."""
    return Inventory.model_validate_json(json.dumps(raw))


def iter_unmanaged(doc: Inventory) -> Iterator[Item]:
    """The `unmanaged` resources of an inventory (never `attached_to_managed`)."""
    return (item for item in doc.resources if item.category == "unmanaged")
