"""Unmanaged Azure resource inventory (Task 10.4).

Lists what actually exists in every resource group that Terraform manages (an
`azurerm_resource_group` in the run's `plan.json`) and compares each ARM resource ID,
case-insensitively, with the IDs Terraform manages in the same plan. Resources Azure has
and Terraform does not are **unmanaged**. The result is `unmanaged_inventory.json`
(`unmanaged_inventory_version` 1), bound to the run's public drift report.

Unmanaged detection is not drift detection (spec §6.3): it never creates, changes or
invalidates a drift result, the drift report, `drift_detected`, issues or the Infracost
cost estimate. A resource outside Terraform is a separate finding with its own status.

Pipeline (deterministic except for the Azure calls):

  plan.json -> managed ARM IDs (report_public.build_index: prior state, planned values,
       resource changes and drift; case-folded) and the scope: every resource group whose
       ID is a managed resource's ID
    -> per scope: GET .../resourceGroups/<rg>/resources (all pages, bounded)
    -> per listed resource: managed (exact case-folded ID match), `attached_to_managed`
       (a disk whose managedBy is a managed VM: possibly the inline OS disk of a Terraform
       VM, so never called unmanaged and never priced), or `unmanaged`
    -> details (GET <id>) for the types whose pricing or grouping needs them: virtual
       machines (with instanceView), disks, public IP addresses, network interfaces
    -> parent (a resource whose ID is below another's, e.g. a VM extension) and attachment
       (disk -> VM, NIC -> VM, public IP -> NIC) links, by reference only
    -> Inventory (strict model) -> render_inventory (byte-stable JSON)

Outcome: `complete` only when every scope was listed completely and every required detail
was read; `incomplete` when a listing stopped at a bound or a detail read failed; `failed`
when an input check failed or a scope could not be listed. Never a clean result after a
failed collection: an incomplete or failed inventory lists only what was seen.

Published (decision 3, user-approved 2026-10-11): ARM type, resource name (unless it looks
like an identifier: GUID, e-mail, URL, IP address or ARM path, then
`withheld_identifier_like`), resource group, location and allowlisted pricing inputs. Never
an ARM resource ID, subscription ID, tag, IP address value or any other property.

Azure access is confined to `AzureResourceSource`: AzureCliCredential only (the job's
`azure/login` session; Reader), the Azure Resource Manager audience Azure CLI caches at
login, GET requests to management.azure.com under a scoped resource group only (anything
else is blocked before a token is requested), no redirects, bounded retries, Retry-After
and timeouts. It imports azure-core / azure-identity (`[azure]` extra) lazily, so nothing
else in drift_engine depends on the Azure SDK. It never writes, imports or deletes anything.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlsplit

from drift_engine.activity_logs import (
    ARM_CREDENTIAL_SCOPE, ARM_ENDPOINT, ARM_HOST, ArmId, RequestSettings, format_timestamp, parse_resource_id,
)
from drift_engine.investigation_public import canonical_sha256, leak_findings
from drift_engine.logs import log_event
from drift_engine.report_public import build_index, identifier_kinds
# The public contract (unmanaged_public.py) is re-exported here for the collector's callers.
from drift_engine.unmanaged_public import (  # noqa: F401
    CATEGORIES, DETAIL_STATUSES, INPUT_FAILURES, INVENTORY_FILE, INVENTORY_VERSION, LIMIT_CODES, LIMITATIONS,
    NAME_STATUSES, POWER_STATES, SCOPE_FAILURE_CODES, Binding, Counts, Inventory, Item, Link, PricingInputs,
    ScopeResult, inventory_problems, iter_unmanaged, load_inventory, render_inventory,
)

logger = logging.getLogger(__name__)

LIST_API_VERSION = "2021-04-01"
# ARM type (case-folded) -> (api-version, $expand) of the detail read. Only these are read.
DETAIL_APIS = {
    "microsoft.compute/virtualmachines": ("2024-07-01", "instanceView"),
    "microsoft.compute/disks": ("2024-03-02", None),
    "microsoft.network/publicipaddresses": ("2024-05-01", None),
    "microsoft.network/networkinterfaces": ("2024-05-01", None),
}
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
_LOCATION = re.compile(r"[a-z0-9]{1,40}")


class InventoryInputError(Exception):
    """The inputs cannot be used; `code` is one of INPUT_FAILURES (never a value)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# ---------------------------------------------------------------------------
# Managed IDs and scope (from plan.json; runner-only, never published)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Managed:
    keys: Mapping[str, str | None]  # case-folded ARM ID -> Terraform address (None when shared)
    scopes: tuple[ArmId, ...]  # managed resource groups, sorted by name


def managed_index(plan: Any) -> Managed:
    """The managed ARM IDs of the plan and the resource groups among them. Raises InventoryInputError."""
    if not isinstance(plan, Mapping):
        raise InventoryInputError("invalid_plan")
    keys = build_index(plan)
    scopes = {}
    for key in keys:
        arm = parse_resource_id(key)
        if arm is not None and arm.resource_group is not None and key.count("/") == 4:
            scopes[arm.key] = arm  # exactly /subscriptions/<sub>/resourcegroups/<rg>
    if not scopes:
        raise InventoryInputError("no_managed_resource_group")
    return Managed(keys=keys, scopes=tuple(sorted(scopes.values(), key=lambda a: a.key)))


def check_binding(plan: Mapping[str, Any], public_report: Any) -> dict[str, str]:
    """The binding of a public drift report to this plan (same plan timestamp). Raises InventoryInputError."""
    from pydantic import ValidationError

    from drift_engine.report_public import validate_public

    try:
        report = validate_public(public_report)
    except ValidationError:
        raise InventoryInputError("not_public_report") from None
    if report.outcome != "succeeded" or report.run is None or report.plan is None:
        raise InventoryInputError("binding_mismatch")
    if not report.run.run_id or not report.run.environment or plan.get("timestamp") != report.plan.timestamp:
        raise InventoryInputError("binding_mismatch")
    return {"run_id": report.run.run_id, "environment": report.run.environment,
            "plan_timestamp": report.plan.timestamp, "drift_report_sha256": canonical_sha256(public_report)}


# ---------------------------------------------------------------------------
# Source protocol
# ---------------------------------------------------------------------------

class InventorySourceError(Exception):
    """A request failed; `code` is one of SCOPE_FAILURE_CODES."""

    def __init__(self, code: str, http_status: int | None = None) -> None:
        if code not in SCOPE_FAILURE_CODES:
            raise ValueError(f"unknown inventory failure code {code!r}")
        super().__init__(code)
        self.code = code
        self.http_status = http_status


class InventorySource(Protocol):
    def list_page(self, url: str) -> tuple[list[Any], str | None]:
        """One page of a resource-group listing: (items, nextLink or None)."""
        ...

    def get(self, url: str) -> Any:
        """One resource document (parsed JSON)."""
        ...


@dataclass(frozen=True)
class Limits:
    max_pages_per_scope: int = 50
    max_resources_per_scope: int = 5000
    max_detail_reads: int = 500
    deadline_seconds: float = 240.0  # inside scripts/inventory_analysis.sh's 300 s hard bound (review fix)

    def __post_init__(self) -> None:
        for name in ("max_pages_per_scope", "max_resources_per_scope", "max_detail_reads"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.deadline_seconds, (int, float)) or not self.deadline_seconds > 0:
            raise ValueError("deadline_seconds must be positive")


DEFAULT_LIMITS = Limits()


def list_url(scope: ArmId) -> str:
    return (f"{ARM_ENDPOINT}/subscriptions/{scope.subscription_id}/resourceGroups/{scope.resource_group}"
            f"/resources?api-version={LIST_API_VERSION}")


def detail_url(arm: ArmId, type_key: str) -> str:
    version, expand = DETAIL_APIS[type_key]
    return f"{ARM_ENDPOINT}{arm.text}?api-version={version}" + (f"&$expand={expand}" if expand else "")


# ---------------------------------------------------------------------------
# Normalization (allowlisted fields only)
# ---------------------------------------------------------------------------

def _token(value: Any) -> str | None:
    return value if isinstance(value, str) and _TOKEN.fullmatch(value) else None


def _get(document: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(document, Mapping):
            return None
        document = document.get(key)
    return document


def arm_type(arm: ArmId) -> str:
    """`Namespace/type[/childType...]` of an ARM ID as received (e.g. Microsoft.Compute/virtualMachines/extensions)."""
    parts = arm.text.split("/")
    i = [n for n, p in enumerate(parts) if p.lower() == "providers"][-1]
    rest = parts[i + 1:]
    return "/".join([rest[0]] + rest[1::2])


def resource_name(arm: ArmId) -> str:
    """The name segments of an ARM ID after its last provider namespace, joined by '/' (e.g. vm1/ext1)."""
    parts = arm.text.split("/")
    i = [n for n, p in enumerate(parts) if p.lower() == "providers"][-1]
    return "/".join(parts[i + 3::2])


def publishable_name(name: str) -> bool:
    """A resource name is published unless it looks like an identifier (decision 3): the public leak scan (GUID,
    e-mail/@, URL, IP address, subscription or provider path) or a report_public identifier kind (ARM resource
    ID, GUID, identity). An undashed hexadecimal suffix, as in a portal OS disk name
    (`<vm>_OsDisk_1_<32 hex>`), is part of the resource's own name and is published (review fix 2026-10-11)."""
    return not (leak_findings(name) or identifier_kinds(name))


def _power_state(view: Any) -> str | None:
    if not isinstance(view, Mapping):
        return None
    for status in view.get("statuses") or []:
        code = _get(status, "code")
        if isinstance(code, str) and code.startswith("PowerState/"):
            state = code.split("/", 1)[1].lower()
            return state if state in POWER_STATES else "unknown"
    return "unknown"


def pricing_inputs(type_key: str, details: Mapping[str, Any]) -> dict[str, Any]:
    """The allowlisted pricing inputs of a detail document. Invalid values are left out (not reported)."""
    out: dict[str, Any] = {}
    props = details.get("properties") if isinstance(details.get("properties"), Mapping) else {}
    if type_key == "microsoft.compute/virtualmachines":
        out["vm_size"] = _token(_get(props, "hardwareProfile", "vmSize"))
        os_type = _get(props, "storageProfile", "osDisk", "osType")
        out["os_type"] = os_type if os_type in ("Linux", "Windows") else None
        out["license_type"] = _token(props.get("licenseType"))
        priority = props.get("priority")
        out["priority"] = priority if priority in ("Regular", "Spot", "Low") else None
        out["image_publisher"] = _token(_get(props, "storageProfile", "imageReference", "publisher"))
        out["marketplace_plan"] = isinstance(details.get("plan"), Mapping)
        out["power_state"] = _power_state(props.get("instanceView"))
    elif type_key == "microsoft.compute/disks":
        out["disk_sku"] = _token(_get(details, "sku", "name"))
        size = props.get("diskSizeGB")
        out["disk_size_gb"] = size if type(size) is int and 1 <= size <= 65536 else None
        out["disk_tier"] = _token(props.get("tier"))
        out["disk_state"] = _token(props.get("diskState"))
        shares = props.get("maxShares")
        out["max_shares"] = shares if type(shares) is int and 1 <= shares <= 100 else None
    elif type_key == "microsoft.network/publicipaddresses":
        out["ip_sku"] = _token(_get(details, "sku", "name"))
        out["ip_tier"] = _token(_get(details, "sku", "tier"))
        out["ip_version"] = _token(props.get("publicIPAddressVersion"))
        out["ip_allocation"] = _token(props.get("publicIPAllocationMethod"))
    return {key: value for key, value in out.items() if value is not None}


def attachment_id(type_key: str, details: Mapping[str, Any], listed: Mapping[str, Any]) -> ArmId | None:
    """The resource this one is attached to: disk -> managedBy (VM), NIC -> virtualMachine,
    public IP -> the NIC of its ipConfiguration."""
    if type_key == "microsoft.compute/disks":
        raw = details.get("managedBy") if details else listed.get("managedBy")
    elif type_key == "microsoft.network/networkinterfaces":
        raw = _get(details, "properties", "virtualMachine", "id")
    elif type_key == "microsoft.network/publicipaddresses":
        raw = _get(details, "properties", "ipConfiguration", "id")
        arm = parse_resource_id(raw)
        if arm is None:
            return None
        parts = arm.text.split("/")  # .../networkInterfaces/<nic>/ipConfigurations/<cfg> -> the NIC
        return parse_resource_id("/".join(parts[:-2])) if len(parts) > 2 else None
    else:
        return None
    return parse_resource_id(raw)


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

@dataclass
class _Listed:
    arm: ArmId
    type: str
    location: str | None
    raw: Mapping[str, Any]


def _list_scope(scope: ArmId, source: InventorySource, limits: Limits, deadline: float,
                clock: Callable[[], float]) -> tuple[dict[str, Any], list[_Listed]]:
    result = {"resource_group": scope.resource_group, "status": "complete", "error": None, "http_status": None,
              "pages": 0, "listed": 0}
    items: list[_Listed] = []
    url: str | None = list_url(scope)
    while url is not None:
        if result["pages"] >= limits.max_pages_per_scope:
            return {**result, "status": "truncated", "error": "page_limit_exceeded"}, items
        if clock() > deadline:
            return {**result, "status": "truncated", "error": "deadline_exceeded"}, items
        try:
            page, url = source.list_page(url)
        except InventorySourceError as exc:
            return {**result, "status": "failed", "error": exc.code, "http_status": exc.http_status}, items
        result["pages"] += 1
        for entry in page:
            arm = parse_resource_id(_get(entry, "id"))
            if arm is None or arm.resource_group is None or arm.key.count("/") < 8 \
                    or arm.subscription_id != scope.subscription_id \
                    or arm.resource_group.lower() != scope.resource_group.lower():
                return {**result, "status": "failed", "error": "invalid_response"}, items
            location = _get(entry, "location")
            location = location.lower().replace(" ", "") if isinstance(location, str) else None
            derived = arm_type(arm)
            listed_type = _get(entry, "type")  # ARM's canonical casing when it names the same type
            canonical = listed_type if isinstance(listed_type, str) and listed_type.lower() == derived.lower() \
                else derived
            items.append(_Listed(arm, canonical, location if location and _LOCATION.fullmatch(location) else None,
                                 entry))
            result["listed"] += 1
            if result["listed"] > limits.max_resources_per_scope:
                return {**result, "status": "truncated", "error": "resource_limit_exceeded"}, items
    return result, items


def _input_failure(binding: Mapping[str, str], code: str) -> Inventory:
    return Inventory(unmanaged_inventory_version=INVENTORY_VERSION, binding=Binding(**binding), outcome="failed",
                     failure=code, collected_at=None, scopes=[],
                     counts=Counts(listed=0, duplicates_dropped=0, managed=0, attached_to_managed=0, unmanaged=0),
                     unmanaged_by_type={}, resources=[], limitations=list(LIMITATIONS))


def _link(target: ArmId | None, refs: Mapping[str, str], managed: Mapping[str, str | None]) -> dict | None:
    if target is None:
        return None
    if target.key in refs:
        return {"kind": "inventory", "ref": refs[target.key], "address": None}
    if target.key in managed and managed[target.key] is not None:
        return {"kind": "managed", "ref": None, "address": managed[target.key]}
    return {"kind": "other", "ref": None, "address": None}


def _parent(arm: ArmId, refs: Mapping[str, str], managed: Mapping[str, str | None]) -> dict | None:
    """The nearest listed or managed resource whose ID is a prefix of this one (a child resource)."""
    parts = arm.key.split("/")
    for end in range(len(parts) - 2, 8, -2):
        prefix = "/".join(parts[:end])
        if prefix in refs or (prefix in managed and managed[prefix] is not None):
            return _link(parse_resource_id(prefix), refs, managed)
    return None


def collect_inventory(plan: Any, public_report: Any, source: InventorySource, *,
                      now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                      clock: Callable[[], float] = time.monotonic, limits: Limits = DEFAULT_LIMITS) -> Inventory:
    """The unmanaged inventory of one run. Input problems raise InventoryInputError when no binding can be
    made (not a public report) and give a `failed` document otherwise; Azure problems are recorded."""
    if not isinstance(plan, Mapping):
        raise InventoryInputError("invalid_plan")
    binding = check_binding(plan, public_report)
    try:
        managed = managed_index(plan)
    except InventoryInputError as exc:
        return _input_failure(binding, exc.code)

    collected_at = format_timestamp(now())
    deadline = clock() + limits.deadline_seconds
    scopes, listed = [], []
    for scope in managed.scopes:
        result, items = _list_scope(scope, source, limits, deadline, clock)
        scopes.append(result)
        listed += items
        log_event(logger, logging.INFO, "inventory_scope_listed", "resource group listed",
                  resource_group=scope.resource_group, status=result["status"], listed=result["listed"])

    unique: dict[str, _Listed] = {}
    for item in listed:
        unique.setdefault(item.arm.key, item)
    duplicates = len(listed) - len(unique)
    candidates = sorted((i for k, i in unique.items() if k not in managed.keys), key=lambda i: i.arm.key)
    managed_count = len(unique) - len(candidates)

    details: dict[str, tuple[str, Any, str | None]] = {}  # key -> (status, document, error)
    reads = 0
    for item in candidates:
        type_key = item.type.lower()
        if type_key not in DETAIL_APIS:
            details[item.arm.key] = ("not_required", None, None)
            continue
        if reads >= limits.max_detail_reads or clock() > deadline:
            details[item.arm.key] = ("failed", None, "timeout")
            continue
        reads += 1
        try:
            document = source.get(detail_url(item.arm, type_key))
        except InventorySourceError as exc:
            details[item.arm.key] = ("failed", None, exc.code)
            continue
        if not isinstance(document, Mapping) or parse_resource_id(document.get("id")) is None \
                or parse_resource_id(document.get("id")).key != item.arm.key:
            details[item.arm.key] = ("failed", None, "invalid_details")
            continue
        details[item.arm.key] = ("read", document, None)

    refs = {item.arm.key: f"res-{n}" for n, item in enumerate(candidates, start=1)}
    resources = []
    for item in candidates:
        status, document, error = details[item.arm.key]
        type_key = item.type.lower()
        attached = attachment_id(type_key, document or {}, item.raw)
        attached_link = _link(attached, refs, managed.keys)
        category = "unmanaged"
        if type_key == "microsoft.compute/disks" and attached_link and attached_link["kind"] == "managed":
            category = "attached_to_managed"
        name = resource_name(item.arm)
        published = publishable_name(name)
        resources.append({
            "ref": refs[item.arm.key], "type": item.type, "name": name if published else None,
            "name_status": "published" if published else "withheld_identifier_like",
            "resource_group": item.arm.resource_group, "location": item.location, "category": category,
            "parent": _parent(item.arm, refs, managed.keys), "attached_to": attached_link,
            "detail_status": status, "detail_error": error,
            "pricing_inputs": pricing_inputs(type_key, document) if document else {},
        })

    by_category = Counter(r["category"] for r in resources)
    failed = any(s["status"] == "failed" for s in scopes)
    incomplete = any(s["status"] == "truncated" for s in scopes) or any(r["detail_status"] == "failed"
                                                                         for r in resources)
    doc = {
        "unmanaged_inventory_version": INVENTORY_VERSION, "binding": binding,
        "outcome": "failed" if failed else "incomplete" if incomplete else "complete",
        "failure": "listing_failed" if failed else None, "collected_at": collected_at,
        "scopes": sorted(scopes, key=lambda s: s["resource_group"].lower()),
        "counts": {"listed": len(unique), "duplicates_dropped": duplicates, "managed": managed_count,
                   "attached_to_managed": by_category["attached_to_managed"], "unmanaged": by_category["unmanaged"]},
        "unmanaged_by_type": dict(sorted(Counter(r["type"] for r in resources
                                                 if r["category"] == "unmanaged").items())),
        "resources": resources, "limitations": list(LIMITATIONS),
    }
    inventory = Inventory.model_validate_json(json.dumps(doc))
    log_event(logger, logging.INFO, "inventory_collected", "unmanaged inventory collected",
              outcome=inventory.outcome, listed=inventory.counts.listed, unmanaged=inventory.counts.unmanaged)
    return inventory


# ---------------------------------------------------------------------------
# Azure Resource Manager source (the only code here that talks to Azure)
# ---------------------------------------------------------------------------

class _BlockedRequest(Exception):
    """A request the source must not send (raised before a token is requested)."""


def allowed_url(url: str) -> bool:
    """GET targets this source may request: a resource-group listing (any query: nextLink) or a
    resource-group-scoped resource ID, over https on management.azure.com."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    if parts.scheme != "https" or parts.hostname != ARM_HOST or port not in (None, 443) \
            or parts.username is not None or parts.password is not None or parts.fragment:
        return False
    path = parts.path
    if path.lower().endswith("/resources"):
        arm = parse_resource_id(path[: -len("/resources")])
        return arm is not None and arm.resource_group is not None and arm.key.count("/") == 4
    arm = parse_resource_id(path)
    return arm is not None and arm.resource_group is not None and arm.key.count("/") >= 8


def _status_code(status: int) -> str:
    if status == 400:
        return "bad_request"
    if status == 401:
        return "authentication_failed"
    if status == 403:
        return "authorization_failed"
    if status == 404:
        return "not_found"
    if status == 429:
        return "throttled"
    if 500 <= status <= 599:
        return "service_error"
    return "http_error"


class AzureResourceSource:
    """InventorySource over Azure Resource Manager (read-only GETs, `[azure]` extra).

    `credential` defaults to `AzureCliCredential`, created on first use; tests pass a fake credential
    and an azure-core `transport`. Constructing this source never imports the SDK.
    """

    def __init__(self, credential: Any = None, *, transport: Any = None,
                 settings: RequestSettings = RequestSettings()) -> None:
        self._credential = credential
        self._transport = transport
        self._settings = settings
        self._client: Any = None

    def _pipeline(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import azure.identity  # noqa: F401  (its loggers must exist for the redaction filter)
            from azure.core import PipelineClient
            from azure.core.pipeline.policies import (
                BearerTokenCredentialPolicy, HeadersPolicy, RetryPolicy, SansIOHTTPPolicy,
            )
            if self._credential is None:
                from azure.identity import AzureCliCredential

                self._credential = AzureCliCredential(process_timeout=self._settings.cli_process_timeout)
        except ImportError:
            raise InventorySourceError("azure_sdk_unavailable") from None
        from drift_engine.activity_logs import _redact_azure_identity_logs

        _redact_azure_identity_logs()
        settings = self._settings

        class Guard(SansIOHTTPPolicy):
            def on_request(self, request: Any) -> None:
                http_request = request.http_request
                if http_request.method != "GET" or not allowed_url(http_request.url):
                    raise _BlockedRequest()

        class BoundedRetryPolicy(RetryPolicy):
            def get_retry_after(self, response: Any) -> float | None:
                retry_after = super().get_retry_after(response)
                return None if retry_after is None else min(retry_after, settings.retry_after_max)

        policies = [
            HeadersPolicy({"Accept": "application/json"}),
            Guard(),  # before the retry and token policies: a blocked request never gets a token
            BoundedRetryPolicy(retry_total=settings.retry_total, retry_backoff_factor=settings.retry_backoff_factor,
                               retry_backoff_max=settings.retry_backoff_max, timeout=settings.retry_timeout),
            BearerTokenCredentialPolicy(self._credential, ARM_CREDENTIAL_SCOPE),
        ]
        kwargs = {"transport": self._transport} if self._transport is not None else {}
        self._client = PipelineClient(base_url=ARM_ENDPOINT, policies=policies, **kwargs)
        return self._client

    def _send(self, url: str) -> Any:
        if not allowed_url(url):
            raise InventorySourceError("blocked_request")
        client = self._pipeline()
        from azure.core.exceptions import AzureError
        from azure.core.rest import HttpRequest

        from drift_engine.activity_logs import _error_code

        try:
            response = client.send_request(HttpRequest("GET", url),
                                           connection_timeout=self._settings.connection_timeout,
                                           read_timeout=self._settings.read_timeout)
            status = response.status_code
            body = response.text() if status == 200 else None
        except (AzureError, _BlockedRequest, TypeError, ValueError, AttributeError, KeyError) as exc:
            code, http_status = _error_code(exc)
            code = "blocked_request" if isinstance(exc, _BlockedRequest) else code
            raise InventorySourceError(code, http_status) from None
        if status != 200:
            raise InventorySourceError(_status_code(status), status)
        try:
            from drift_engine.investigation_public import strict_json

            return strict_json(body.encode("utf-8"))
        except (ValueError, RecursionError, UnicodeError):
            raise InventorySourceError("invalid_response") from None

    def list_page(self, url: str) -> tuple[list[Any], str | None]:
        document = self._send(url)
        items = document.get("value") if isinstance(document, Mapping) else None
        next_link = document.get("nextLink") if isinstance(document, Mapping) else None
        if not isinstance(items, list) or (next_link is not None and not isinstance(next_link, str)):
            raise InventorySourceError("invalid_response")
        if next_link and not allowed_url(next_link):
            raise InventorySourceError("blocked_request")  # never requested: the scope is not complete
        return items, next_link or None

    def get(self, url: str) -> Any:
        return self._send(url)
