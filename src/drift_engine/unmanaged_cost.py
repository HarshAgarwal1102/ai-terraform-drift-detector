"""Monthly list-price estimate of unmanaged Azure resources (Task 10.4).

`estimate_costs(inventory, source)` prices the `unmanaged` resources of one
`unmanaged_inventory.json` (drift_engine.inventory) with the public **Azure Retail Prices
API** (`https://prices.azure.com/api/retail/prices`, api-version 2023-01-01-preview, USD,
`priceType eq 'Consumption'`) and returns the `unmanaged_cost_version` 1 document,
`unmanaged_cost.json`.

Scope of the amounts (Phase 10 amendment, user decision 2026-10-11, Task 10.4):
- They are pay-as-you-go **list-price estimates**, never actual Azure billing: no discounts,
  reservations, savings plans, credits or usage-based charges (transactions, data transfer).
- They cover resources **outside Terraform** only. They are never added to, compared with
  or subtracted from the Infracost estimate of the Terraform plan (Tasks 10.1-10.3), and
  they are never drift cost.
- Infracost is not used here: it prices a Terraform plan, and these resources are not in it.

Rules:
- Every amount comes from one matched Retail Prices API meter: unit price x quantity,
  computed exactly with Decimal (JSON numbers are parsed as Decimal, never float). Hourly
  meters use 730 hours per month (Azure's convention); monthly meters use 1.
- A meter matches only when exactly one item satisfies the type's rule (product, SKU,
  meter name, unit, region; Spot and Low Priority excluded). None is `price_not_found`,
  several are `ambiguous_price`: the estimate is `unavailable` with that reason, never 0.
- Unknown is never zero: an unsupported type, a missing pricing input or a failed query is
  `unavailable` with a reason code and no amount. Only the fixed NO_DIRECT_CHARGE_TYPES
  (resources Azure does not bill by themselves, e.g. network interfaces, NSGs, virtual
  networks, VM extensions) carry an explicit `0` (`no_direct_charge`).
- No double counting: each unmanaged resource is priced at most once, by its own type rule
  only. A VM is priced for compute only; its disks and public IPs are priced as their own
  resources. Disks attached to a Terraform-managed VM are `attached_to_managed` in the
  inventory and never priced here.
- Totals: the exact sum of the resources that have an amount, with the counts of those
  without one; `complete` is true only when every resource has an amount.

Status: `complete` (every resource priced or no direct charge), `partial` (some estimates
unavailable or partial; the API answered), `failed` (a Retail Prices API request failed:
an explicit failure, never shown as $0), `not_run` (the inventory is not complete; nothing
is priced).

Network: GET requests to prices.azure.com only (no redirects, no other host or path,
bounded pages, retries and timeouts). The requests carry only service, product, SKU and
region filter values; never a resource name, ID or credential.
"""

from __future__ import annotations

import json
import logging
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Context, Decimal, Inexact, InvalidOperation
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from drift_engine.investigation_public import canonical_sha256, leak_findings
from drift_engine.logs import log_event
from drift_engine.unmanaged_public import Inventory, iter_unmanaged, load_inventory

logger = logging.getLogger(__name__)

UNMANAGED_COST_VERSION = "1"
COST_FILE = "unmanaged_cost.json"
PRICES_HOST = "prices.azure.com"
PRICES_PATH = "/api/retail/prices"
PRICES_API_VERSION = "2023-01-01-preview"
PRICES_ENDPOINT = f"https://{PRICES_HOST}{PRICES_PATH}"
HOURS_PER_MONTH = "730"
PRICING_SOURCE = "azure_retail_prices_api_list_prices_usd"
TOTAL_LABEL = ("Estimated monthly list-price cost of Azure resources not managed by Terraform (Azure Retail Prices "
               "API, USD, pay-as-you-go); not actual Azure billing; separate from the Infracost Terraform plan "
               "estimate; never drift cost")

ESTIMATE_STATUSES = ("estimated", "partial", "no_direct_charge", "unavailable")
UNAVAILABLE_REASONS = ("ambiguous_price", "location_unknown", "missing_pricing_input", "performance_tier_differs",
                       "price_not_found", "pricing_api_failed", "shared_disk", "spot_or_low_priority",
                       "unsupported_disk_size", "unsupported_ip_configuration", "unsupported_resource_type",
                       "unsupported_sku")
PARTIAL_REASONS = ("image_software_license_not_priced",)
ASSUMPTIONS = ("compute_only_disks_and_ips_priced_separately", "disk_billed_at_tier_size",
               "linux_rate_azure_hybrid_benefit", "observed_deallocated_priced_as_running",
               "pay_as_you_go_list_price", "runs_730_hours_per_month", "windows_license_included")
EXCLUSIONS = ("data_transfer", "disk_transactions", "image_software_license", "snapshots_and_backups",
              "usage_based_charges")
API_FAILURES = ("blocked_request", "connection_failed", "http_error", "invalid_response", "page_limit_exceeded",
                "service_error", "throttled", "timeout")
FAILURES = API_FAILURES + ("inventory_not_complete",)
# Fixed codes, always all published.
LIMITATIONS = ("list_prices_usd_pay_as_you_go", "estimate_not_billing", "usage_based_charges_not_priced",
               "separate_from_infracost_plan_estimate", "not_drift_cost", "prices_change_over_time",
               "unknown_is_never_zero")

# Resource types Azure does not bill by themselves (case-folded). Traffic or services they enable may be billed
# elsewhere (excluded: usage_based_charges). A new entry needs a documented Azure pricing reference.
NO_DIRECT_CHARGE_TYPES = (
    "microsoft.compute/sshpublickeys",
    "microsoft.compute/virtualmachines/extensions",
    "microsoft.devtestlab/schedules",
    "microsoft.network/applicationsecuritygroups",
    "microsoft.network/networkinterfaces",
    "microsoft.network/networksecuritygroups",
    "microsoft.network/routetables",
    "microsoft.network/virtualnetworks",
)
# Managed disk SKU -> (Retail Prices product name, tier letter, redundancy).
DISK_SKUS = {
    "Standard_LRS": ("Standard HDD Managed Disks", "S", "LRS"),
    "StandardSSD_LRS": ("Standard SSD Managed Disks", "E", "LRS"),
    "StandardSSD_ZRS": ("Standard SSD Managed Disks", "E", "ZRS"),
    "Premium_LRS": ("Premium SSD Managed Disks", "P", "LRS"),
    "Premium_ZRS": ("Premium SSD Managed Disks", "P", "ZRS"),
}
# Billed tier by provisioned size (GiB, the smallest tier at least as large). Standard HDD starts at S4 (32 GiB);
# verified against the Retail Prices API (Central India, 2026-10-11): S4..S80, E1..E80, P1..P80 exist, S1-S3 do not.
_TIER_SIZES = ((4, "1"), (8, "2"), (16, "3"), (32, "4"), (64, "6"), (128, "10"), (256, "15"), (512, "20"),
               (1024, "30"), (2048, "40"), (4096, "50"), (8192, "60"), (16384, "70"), (32767, "80"))
# Linux images with separately billed software (license not priced: partial).
PAID_IMAGE_PUBLISHERS = ("microsoftsqlserver", "redhat", "suse")
AHB_LICENSES = ("Windows_Client", "Windows_Server")
PUBLIC_IP_METER = "Standard IPv4 Static Public IP"

_MONEY = r"^[0-9]+(\.[0-9]+)?$"
_FILTER_VALUE = re.compile(r"[A-Za-z0-9_]{1,80}")
_LOCATION = re.compile(r"[a-z0-9]{1,40}")
_EXACT = Context(prec=200, traps=[Inexact])
_CENT = Decimal("0.01")


# ---------------------------------------------------------------------------
# Contract (unmanaged_cost_version 1)
# ---------------------------------------------------------------------------

class _Model(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


Money = Annotated[str, Field(pattern=_MONEY, max_length=60)]
Count = Annotated[int, Field(ge=0)]
Text = Annotated[str, Field(min_length=1, max_length=200)]
Timestamp = Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$")]


class Binding(_Model):
    run_id: str
    environment: str
    drift_report_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    inventory_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Source(_Model):
    name: Literal["azure_retail_prices_api"]
    endpoint: Literal["prices.azure.com/api/retail/prices"]  # host and path (https); no scheme: public leak rule
    api_version: Literal["2023-01-01-preview"]
    currency: Literal["USD"]
    price_type: Literal["Consumption"]
    hours_per_month: Literal["730"]
    queried_at: Timestamp | None


class Component(_Model):
    """One matched Retail Prices API meter, copied as returned, and its monthly amount. The meter's `meterId` is a
    GUID and is not published (public leak rule); product, SKU, meter name and effective date identify it."""
    product_name: Text
    sku_name: Text
    meter_name: Text
    arm_region_name: Text
    unit_of_measure: Literal["1 Hour", "1/Month"]
    unit_price: Money
    effective_start_date: Text
    quantity: Literal["730", "1"]
    monthly_cost: Money

    @model_validator(mode="after")
    def _arithmetic(self) -> Component:
        if self.quantity != ("730" if self.unit_of_measure == "1 Hour" else "1"):
            raise ValueError("quantity must be 730 for an hourly meter and 1 for a monthly meter")
        if Decimal(self.monthly_cost) != _EXACT.multiply(Decimal(self.unit_price), Decimal(self.quantity)):
            raise ValueError("monthly_cost must equal unit_price x quantity")
        return self


class ResourceEstimate(_Model):
    ref: Annotated[str, Field(pattern=r"^res-[1-9][0-9]*$")]
    type: Text
    name: Annotated[str, Field(min_length=1, max_length=600)] | None
    location: Text | None
    estimate_status: Literal[ESTIMATE_STATUSES]  # type: ignore[valid-type]
    reason: Literal[UNAVAILABLE_REASONS + PARTIAL_REASONS] | None  # type: ignore[valid-type]
    monthly_cost: Money | None
    display: str | None
    components: list[Component]
    assumptions: list[Literal[ASSUMPTIONS]]  # type: ignore[valid-type]
    exclusions: list[Literal[EXCLUSIONS]]  # type: ignore[valid-type]

    @model_validator(mode="after")
    def _consistent(self) -> ResourceEstimate:
        status = self.estimate_status
        if any(list(codes) != sorted(set(codes)) for codes in (self.assumptions, self.exclusions)):
            raise ValueError("assumptions and exclusions must be sorted and unique")
        if status == "unavailable":
            if self.reason not in UNAVAILABLE_REASONS or self.monthly_cost is not None or self.components \
                    or self.display is not None:
                raise ValueError("an unavailable estimate has an unavailable reason and no amount or component")
            return self
        if self.monthly_cost is None or self.display != format_usd(Decimal(self.monthly_cost)):
            raise ValueError("an estimate has an amount and its display")
        if status == "no_direct_charge":
            if self.reason is not None or self.components or Decimal(self.monthly_cost) != 0:
                raise ValueError("no_direct_charge is exactly 0 without components or reason")
            return self
        if len(self.components) != 1:
            raise ValueError("an estimate has exactly one component")
        if Decimal(self.monthly_cost) != _sum([Decimal(c.monthly_cost) for c in self.components]):
            raise ValueError("monthly_cost must equal the sum of its components")
        if (status == "partial") != (self.reason in PARTIAL_REASONS) \
                or (status == "estimated") != (self.reason is None):
            raise ValueError("a partial estimate has a partial reason; a full estimate has none")
        return self


class Totals(_Model):
    estimated_monthly_cost: Money | None
    display: str | None
    resources: Count
    estimated: Count
    partial: Count
    no_direct_charge: Count
    unavailable: Count
    complete: bool
    label: Literal[TOTAL_LABEL]  # type: ignore[valid-type]


class UnmanagedCost(_Model):
    unmanaged_cost_version: Literal["1"]
    binding: Binding
    source: Source
    status: Literal["complete", "partial", "failed", "not_run"]
    failure: Literal[FAILURES] | None  # type: ignore[valid-type]
    resources: list[ResourceEstimate]
    totals: Totals
    limitations: list[Literal[LIMITATIONS]]  # type: ignore[valid-type]

    @model_validator(mode="after")
    def _invariants(self) -> UnmanagedCost:
        problems = cost_problems(self)
        if problems:
            raise ValueError("; ".join(problems))
        return self


def cost_problems(doc: UnmanagedCost) -> list[str]:
    problems: list[str] = []
    if list(doc.limitations) != list(LIMITATIONS):
        problems.append("limitations must be exactly the defined codes in order")
    refs = [r.ref for r in doc.resources]
    if refs != sorted(set(refs), key=lambda ref: int(ref[4:])):
        problems.append("resources must be sorted by ref, without repeats")
    statuses = [r.estimate_status for r in doc.resources]
    api_failed = [r for r in doc.resources if r.reason == "pricing_api_failed"]
    if doc.status == "not_run":
        if doc.failure != "inventory_not_complete" or doc.resources or doc.source.queried_at is not None:
            problems.append("not_run has failure inventory_not_complete, no resources and no query time")
    elif doc.status == "failed":
        if doc.failure not in API_FAILURES or not api_failed:
            problems.append("failed needs an API failure code and a resource whose query failed")
    else:
        if doc.failure is not None or api_failed:
            problems.append("only a failed status has a failure")
        expected = "complete" if all(s in ("estimated", "no_direct_charge") for s in statuses) else "partial"
        if doc.status != expected:
            problems.append(f"status must be {expected}")
    if doc.status != "not_run" and doc.source.queried_at is None:
        problems.append("a priced document has a query time")
    amounts = [Decimal(r.monthly_cost) for r in doc.resources if r.monthly_cost is not None]
    t = doc.totals
    expected_total = None if doc.status == "not_run" or (doc.resources and not amounts) else _sum(amounts)
    if (t.estimated_monthly_cost is None) != (expected_total is None) or (
            expected_total is not None and Decimal(t.estimated_monthly_cost) != expected_total):
        problems.append("estimated_monthly_cost must be the exact sum of the resource amounts")
    if t.display != (None if t.estimated_monthly_cost is None else format_usd(Decimal(t.estimated_monthly_cost))):
        problems.append("the total display does not match the total")
    counts = {s: statuses.count(s) for s in ESTIMATE_STATUSES}
    if (t.resources, t.estimated, t.partial, t.no_direct_charge, t.unavailable) != (
            len(statuses), counts["estimated"], counts["partial"], counts["no_direct_charge"], counts["unavailable"]):
        problems.append("total counts do not match the resources")
    if t.complete != (doc.status == "complete"):
        problems.append("complete is true exactly when the status is complete")
    findings = leak_findings(doc.model_dump(mode="json"))
    if findings:
        problems.append("identifier-like values: " + ", ".join(findings))
    return problems


def render_cost(doc: UnmanagedCost) -> str:
    return json.dumps(doc.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def load_cost(raw: Any) -> UnmanagedCost:
    """Validate a parsed unmanaged cost document (raises pydantic.ValidationError)."""
    return UnmanagedCost.model_validate_json(json.dumps(raw))


def check_cost_binding(cost: UnmanagedCost, inventory_raw: Any) -> bool:
    """The cost document prices exactly this inventory (canonical hash) of the same run."""
    binding = inventory_raw.get("binding") if isinstance(inventory_raw, Mapping) else None
    return (isinstance(binding, Mapping) and cost.binding.inventory_sha256 == canonical_sha256(inventory_raw)
            and cost.binding.drift_report_sha256 == binding.get("drift_report_sha256")
            and cost.binding.run_id == binding.get("run_id") and cost.binding.environment == binding.get("environment"))


# ---------------------------------------------------------------------------
# Exact decimals
# ---------------------------------------------------------------------------

def format_timestamp(moment: datetime) -> str:
    """UTC with microseconds (drift_engine.activity_logs' format, without loading that module: G14)."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _text(value: Decimal) -> str:
    return format(value.copy_abs() if value.is_zero() else value, "f")


def _sum(values: list[Decimal]) -> Decimal:
    total = Decimal(0)
    for value in values:
        total = _EXACT.add(total, value)
    return total


def format_usd(value: Decimal) -> str:
    """Display only, rounded half-up to cents: `$8.18/month`. The exact amount is published next to it."""
    cents = value.quantize(_CENT, rounding=ROUND_HALF_UP, context=Context(prec=200))
    return f"${format(cents.copy_abs(), 'f')}/month"


# ---------------------------------------------------------------------------
# Retail Prices API source
# ---------------------------------------------------------------------------

class PricingSourceError(Exception):
    """A Retail Prices API request failed; `code` is one of API_FAILURES."""

    def __init__(self, code: str) -> None:
        if code not in API_FAILURES:
            raise ValueError(f"unknown pricing failure code {code!r}")
        super().__init__(code)
        self.code = code


class RetailPriceSource(Protocol):
    def items(self, odata_filter: str) -> list[Any]:
        """Every item for the filter (all pages); raise PricingSourceError on failure."""
        ...


@dataclass(frozen=True)
class PriceSettings:
    retries: int = 3
    backoff_seconds: float = 1.0
    retry_after_max: float = 30.0
    timeout_seconds: float = 30.0
    max_pages: int = 10
    max_bytes: int = 10 * 1024 * 1024


def query_url(odata_filter: str) -> str:
    return PRICES_ENDPOINT + "?" + urllib.parse.urlencode({"api-version": PRICES_API_VERSION, "$filter": odata_filter})


def allowed_price_url(url: str) -> bool:
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return (parts.scheme == "https" and parts.hostname == PRICES_HOST and port in (None, 443)
            and parts.username is None and parts.password is None and parts.path == PRICES_PATH
            and not parts.fragment)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        raise PricingSourceError("blocked_request")


def _reject_constant(name: str) -> Any:
    raise ValueError(name)


class RetailPricesApi:
    """RetailPriceSource over HTTPS (standard library only; no credential is ever sent)."""

    def __init__(self, *, opener: Any = None, sleep: Callable[[float], None] = time.sleep,
                 settings: PriceSettings = PriceSettings()) -> None:
        self._opener = opener or urllib.request.build_opener(_NoRedirect())
        self._sleep = sleep
        self._settings = settings

    def _fetch(self, url: str) -> Any:
        if not allowed_price_url(url):
            raise PricingSourceError("blocked_request")
        settings = self._settings
        last = "connection_failed"
        for attempt in range(settings.retries + 1):
            if attempt:
                delay = settings.backoff_seconds * (2 ** (attempt - 1))
                self._sleep(min(delay, settings.retry_after_max))
            request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
            try:
                with self._opener.open(request, timeout=settings.timeout_seconds) as response:
                    data = response.read(settings.max_bytes + 1)
            except PricingSourceError:
                raise
            except urllib.error.HTTPError as exc:
                status = exc.code
                if status == 429 or 500 <= status <= 599:
                    last = "throttled" if status == 429 else "service_error"
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    if retry_after and retry_after.isdigit() and attempt < settings.retries:
                        self._sleep(min(float(retry_after), settings.retry_after_max))
                    continue
                raise PricingSourceError("http_error") from None
            except (TimeoutError, socket.timeout):
                last = "timeout"
                continue
            except (urllib.error.URLError, OSError):
                last = "connection_failed"
                continue
            if len(data) > settings.max_bytes:
                raise PricingSourceError("invalid_response")
            try:
                return json.loads(data.decode("utf-8"), parse_float=Decimal, parse_constant=_reject_constant)
            except (ValueError, RecursionError, UnicodeDecodeError):
                raise PricingSourceError("invalid_response") from None
        raise PricingSourceError(last)

    def items(self, odata_filter: str) -> list[Any]:
        url: str | None = query_url(odata_filter)
        collected: list[Any] = []
        for _ in range(self._settings.max_pages):
            document = self._fetch(url)
            page = document.get("Items") if isinstance(document, Mapping) else None
            next_link = document.get("NextPageLink") if isinstance(document, Mapping) else None
            if not isinstance(page, list) or (next_link is not None and not isinstance(next_link, str)):
                raise PricingSourceError("invalid_response")
            collected += page
            if not next_link:
                return collected
            url = next_link
        raise PricingSourceError("page_limit_exceeded")


# ---------------------------------------------------------------------------
# Matching (exactly one meter per resource)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Meter:
    product_name: str
    sku_name: str
    meter_name: str
    arm_sku_name: str
    arm_region_name: str
    unit_of_measure: str
    unit_price: Decimal
    effective_start_date: str


def _meter(item: Any) -> _Meter | None:
    """A valid USD Consumption meter at the base tier, or None (ignored)."""
    if not isinstance(item, Mapping):
        return None
    texts = {key: item.get(key) for key in ("productName", "skuName", "meterName", "armRegionName",
                                            "unitOfMeasure", "effectiveStartDate")}
    if not all(isinstance(v, str) and 0 < len(v) <= 200 for v in texts.values()):
        return None
    price, tier = item.get("retailPrice"), item.get("tierMinimumUnits", 0)
    if isinstance(price, bool) or not isinstance(price, (Decimal, int)) or isinstance(tier, bool) \
            or not isinstance(tier, (Decimal, int)):
        return None
    try:
        price = Decimal(price)
        if not price.is_finite() or price < 0 or Decimal(tier) != 0:
            return None
    except InvalidOperation:  # pragma: no cover - Decimal(int|Decimal) cannot fail
        return None
    if item.get("currencyCode") != "USD" or item.get("type") != "Consumption":
        return None
    arm_sku = item.get("armSkuName")
    return _Meter(texts["productName"], texts["skuName"], texts["meterName"],
                  arm_sku if isinstance(arm_sku, str) else "", texts["armRegionName"], texts["unitOfMeasure"], price,
                  texts["effectiveStartDate"])


def _pick(items: list[Any], rule: Callable[[_Meter], bool]) -> _Meter | str:
    matches = [m for m in (_meter(i) for i in items) if m is not None and rule(m)]
    unique = {(m.product_name, m.sku_name, m.meter_name, m.unit_price) for m in matches}  # a repeat is one meter
    if not matches:
        return "price_not_found"
    if len(unique) > 1:
        return "ambiguous_price"
    return matches[0]


def _component(meter: _Meter, quantity: str) -> dict[str, str]:
    return {"product_name": meter.product_name, "sku_name": meter.sku_name,
            "meter_name": meter.meter_name, "arm_region_name": meter.arm_region_name,
            "unit_of_measure": meter.unit_of_measure, "unit_price": _text(meter.unit_price),
            "effective_start_date": meter.effective_start_date, "quantity": quantity,
            "monthly_cost": _text(_EXACT.multiply(meter.unit_price, Decimal(quantity)))}


def disk_tier(letter: str, size_gb: int) -> str | None:
    """The billed tier of a disk size (the smallest tier at least as large), or None above 32767 GiB."""
    for limit, number in _TIER_SIZES:
        if letter == "S" and limit < 32:
            continue  # Standard HDD starts at S4
        if size_gb <= limit:
            return f"{letter}{number}"
    return None


@dataclass(frozen=True)
class _Plan:
    """What to query for one resource, or why it cannot be priced."""
    reason: str | None = None
    odata_filter: str | None = None
    rule: Callable[[_Meter], bool] | None = None
    quantity: str = HOURS_PER_MONTH
    partial: str | None = None
    assumptions: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    no_charge: bool = False


def _vm_plan(location: str, inputs: Mapping[str, Any]) -> _Plan:
    if inputs.get("priority") in ("Spot", "Low"):
        return _Plan("spot_or_low_priority")
    size, os_type = inputs.get("vm_size"), inputs.get("os_type")
    if not isinstance(size, str) or not _FILTER_VALUE.fullmatch(size) or os_type is None:
        return _Plan("missing_pricing_input")
    windows_rate = os_type == "Windows" and inputs.get("license_type") not in AHB_LICENSES
    assumptions = ["compute_only_disks_and_ips_priced_separately", "pay_as_you_go_list_price",
                   "runs_730_hours_per_month"]
    if os_type == "Windows":
        assumptions.append("windows_license_included" if windows_rate else "linux_rate_azure_hybrid_benefit")
    if inputs.get("power_state") in ("deallocated", "deallocating"):
        assumptions.append("observed_deallocated_priced_as_running")
    publisher = (inputs.get("image_publisher") or "").lower()
    partial = ("image_software_license_not_priced"
               if inputs.get("marketplace_plan") or publisher in PAID_IMAGE_PUBLISHERS else None)
    exclusions = ["data_transfer", "usage_based_charges"] + (["image_software_license"] if partial else [])

    def rule(m: _Meter) -> bool:
        name = m.meter_name.lower()
        return (m.unit_of_measure == "1 Hour" and m.arm_sku_name.lower() == size.lower()
                and m.arm_region_name == location and "spot" not in name and "low priority" not in name
                and m.product_name.startswith("Virtual Machines ")
                and m.product_name.endswith(" Windows") == windows_rate)

    return _Plan(odata_filter=(f"serviceName eq 'Virtual Machines' and armRegionName eq '{location}' and "
                               f"armSkuName eq '{size}' and priceType eq 'Consumption'"),
                 rule=rule, partial=partial, assumptions=tuple(assumptions), exclusions=tuple(exclusions))


def _disk_plan(location: str, inputs: Mapping[str, Any]) -> _Plan:
    sku, size = inputs.get("disk_sku"), inputs.get("disk_size_gb")
    if sku is None or size is None:
        return _Plan("missing_pricing_input")
    if sku not in DISK_SKUS:
        return _Plan("unsupported_sku")
    if (inputs.get("max_shares") or 1) > 1:
        return _Plan("shared_disk")
    product, letter, redundancy = DISK_SKUS[sku]
    tier = disk_tier(letter, size)
    if tier is None:
        return _Plan("unsupported_disk_size")
    if inputs.get("disk_tier") is not None and inputs["disk_tier"] != tier:
        return _Plan("performance_tier_differs")
    sku_name = f"{tier} {redundancy}"
    exclusions = ["snapshots_and_backups"] + (["disk_transactions"] if letter in ("E", "S") else [])

    def rule(m: _Meter) -> bool:
        return (m.unit_of_measure == "1/Month" and m.product_name == product and m.sku_name == sku_name
                and m.meter_name == f"{sku_name} Disk" and m.arm_region_name == location)

    return _Plan(odata_filter=(f"serviceName eq 'Storage' and armRegionName eq '{location}' and "
                               f"skuName eq '{sku_name}' and priceType eq 'Consumption'"),
                 rule=rule, quantity="1", assumptions=("disk_billed_at_tier_size", "pay_as_you_go_list_price"),
                 exclusions=tuple(sorted(exclusions)))


def _public_ip_plan(location: str, inputs: Mapping[str, Any]) -> _Plan:
    sku = inputs.get("ip_sku")
    if sku is None:
        return _Plan("missing_pricing_input")
    if sku != "Standard":
        return _Plan("unsupported_sku")  # Basic public IPs were retired by Azure (2025-09-30)
    if inputs.get("ip_tier", "Regional") not in (None, "Regional") \
            or inputs.get("ip_version", "IPv4") not in (None, "IPv4"):
        return _Plan("unsupported_ip_configuration")

    def rule(m: _Meter) -> bool:
        return (m.unit_of_measure == "1 Hour" and m.product_name == "IP Addresses"
                and m.meter_name == PUBLIC_IP_METER and m.arm_region_name == location)

    return _Plan(odata_filter=(f"serviceName eq 'Virtual Network' and armRegionName eq '{location}' and "
                               "productName eq 'IP Addresses' and priceType eq 'Consumption'"),
                 rule=rule, assumptions=("pay_as_you_go_list_price", "runs_730_hours_per_month"),
                 exclusions=("data_transfer",))


def pricing_plan(item_type: str, location: str | None, inputs: Mapping[str, Any]) -> _Plan:
    """How one unmanaged resource is priced (pure; no network)."""
    type_key = item_type.lower()
    if type_key in NO_DIRECT_CHARGE_TYPES:
        return _Plan(no_charge=True, exclusions=("usage_based_charges",))
    planner = {"microsoft.compute/virtualmachines": _vm_plan, "microsoft.compute/disks": _disk_plan,
               "microsoft.network/publicipaddresses": _public_ip_plan}.get(type_key)
    if planner is None:
        return _Plan("unsupported_resource_type")
    if location is None or not _LOCATION.fullmatch(location):
        return _Plan("location_unknown")
    return planner(location, inputs)


# ---------------------------------------------------------------------------
# Estimate
# ---------------------------------------------------------------------------

def _source_block(queried_at: str | None) -> dict[str, Any]:
    return {"name": "azure_retail_prices_api", "endpoint": f"{PRICES_HOST}{PRICES_PATH}",
            "api_version": PRICES_API_VERSION, "currency": "USD", "price_type": "Consumption",
            "hours_per_month": HOURS_PER_MONTH, "queried_at": queried_at}


def _totals(resources: list[dict[str, Any]], status: str) -> dict[str, Any]:
    amounts = [Decimal(r["monthly_cost"]) for r in resources if r["monthly_cost"] is not None]
    total = None if status == "not_run" or (resources and not amounts) else _sum(amounts)
    statuses = [r["estimate_status"] for r in resources]
    return {"estimated_monthly_cost": None if total is None else _text(total),
            "display": None if total is None else format_usd(total), "resources": len(resources),
            "estimated": statuses.count("estimated"), "partial": statuses.count("partial"),
            "no_direct_charge": statuses.count("no_direct_charge"), "unavailable": statuses.count("unavailable"),
            "complete": status == "complete", "label": TOTAL_LABEL}


def estimate_costs(inventory: Inventory, inventory_raw: Mapping[str, Any], source: RetailPriceSource, *,
                   now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> UnmanagedCost:
    """The `unmanaged_cost_version` 1 document for a validated inventory (`inventory_raw` is its parsed JSON,
    hashed for the binding). A failed Retail Prices API query is recorded (status `failed`), never raised."""
    binding = {"run_id": inventory.binding.run_id, "environment": inventory.binding.environment,
               "drift_report_sha256": inventory.binding.drift_report_sha256,
               "inventory_sha256": canonical_sha256(inventory_raw)}
    if inventory.outcome != "complete":
        doc = {"unmanaged_cost_version": UNMANAGED_COST_VERSION, "binding": binding, "source": _source_block(None),
               "status": "not_run", "failure": "inventory_not_complete", "resources": [],
               "totals": _totals([], "not_run"), "limitations": list(LIMITATIONS)}
        return UnmanagedCost.model_validate_json(json.dumps(doc))

    queried_at = format_timestamp(now())
    cache: dict[str, list[Any] | PricingSourceError] = {}
    failure = None
    resources = []
    for item in iter_unmanaged(inventory):
        plan = pricing_plan(item.type, item.location, item.pricing_inputs.model_dump(exclude_none=True))
        entry: dict[str, Any] = {"ref": item.ref, "type": item.type, "name": item.name, "location": item.location,
                                 "estimate_status": "unavailable", "reason": plan.reason, "monthly_cost": None,
                                 "display": None, "components": [], "assumptions": sorted(set(plan.assumptions)),
                                 "exclusions": sorted(set(plan.exclusions))}
        if plan.no_charge:
            entry.update(estimate_status="no_direct_charge", reason=None, monthly_cost="0",
                         display=format_usd(Decimal(0)))
        elif plan.reason is None:
            if plan.odata_filter not in cache:
                try:
                    cache[plan.odata_filter] = source.items(plan.odata_filter)
                except PricingSourceError as exc:
                    cache[plan.odata_filter] = exc
            result = cache[plan.odata_filter]
            if isinstance(result, PricingSourceError):
                entry["reason"] = "pricing_api_failed"
                failure = failure or result.code
            else:
                meter = _pick(result, plan.rule)
                if isinstance(meter, str):
                    entry["reason"] = meter
                else:
                    component = _component(meter, plan.quantity)
                    entry.update(estimate_status="partial" if plan.partial else "estimated", reason=plan.partial,
                                 monthly_cost=component["monthly_cost"],
                                 display=format_usd(Decimal(component["monthly_cost"])), components=[component])
        if entry["estimate_status"] == "unavailable":
            entry["assumptions"], entry["exclusions"] = [], []
        resources.append(entry)

    statuses = [r["estimate_status"] for r in resources]
    status = ("failed" if failure else
              "complete" if all(s in ("estimated", "no_direct_charge") for s in statuses) else "partial")
    doc = {"unmanaged_cost_version": UNMANAGED_COST_VERSION, "binding": binding,
           "source": _source_block(queried_at), "status": status, "failure": failure, "resources": resources,
           "totals": _totals(resources, status), "limitations": list(LIMITATIONS)}
    cost = UnmanagedCost.model_validate_json(json.dumps(doc))
    log_event(logger, logging.INFO, "unmanaged_cost_estimated", "unmanaged resources priced", status=status,
              resources=len(resources), queries=len(cache))
    return cost


# ---------------------------------------------------------------------------
# Document checks and the step-summary section (shared by the CLI and ai_engine)
# ---------------------------------------------------------------------------

INPUT_ERRORS = ("binding_mismatch", "contract", "invalid_json", "leak", "unreadable")
MAX_INPUT_BYTES = 10 * 1024 * 1024


class UnmanagedInputError(Exception):
    """An inventory / cost document pair cannot be used; `code` is one of INPUT_ERRORS (never a value)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def inventory_bound_to_report(inventory: Inventory, report_raw: Any) -> bool:
    run = report_raw.get("run") if isinstance(report_raw, Mapping) else None
    plan = report_raw.get("plan") if isinstance(report_raw, Mapping) else None
    b = inventory.binding
    return (isinstance(run, Mapping) and isinstance(plan, Mapping)
            and b.drift_report_sha256 == canonical_sha256(report_raw) and b.run_id == run.get("run_id")
            and b.environment == run.get("environment") and b.plan_timestamp == plan.get("timestamp"))


def check_documents(inventory_raw: Any, cost_raw: Any, report_raw: Any) -> tuple[Inventory, UnmanagedCost]:
    """Both documents valid (leak scan first, then the strict contracts), the inventory bound to this public drift
    report and the cost document to this inventory. Raises UnmanagedInputError."""
    from pydantic import ValidationError

    if leak_findings(inventory_raw) or leak_findings(cost_raw):
        raise UnmanagedInputError("leak")
    try:
        inventory, cost = load_inventory(inventory_raw), load_cost(cost_raw)
    except (ValidationError, ValueError, TypeError):
        raise UnmanagedInputError("contract") from None
    if not inventory_bound_to_report(inventory, report_raw) or not check_cost_binding(cost, inventory_raw):
        raise UnmanagedInputError("binding_mismatch")
    if cost.status != "not_run" and [r.ref for r in cost.resources] != [i.ref for i in iter_unmanaged(inventory)]:
        raise UnmanagedInputError("binding_mismatch")  # every unmanaged resource is priced exactly once
    return inventory, cost


INCOMPLETE_TOTAL = "At least {display} — incomplete estimate"


def total_text(totals: Any) -> str:
    """The total for people to read: the display when every resource has an estimate; "At least <display> —
    incomplete estimate" when some are unavailable or partial (the known part is a lower bound, never the complete
    cost); "not determinable" without any amount. `totals` is a Totals model or its JSON form."""
    get = totals.get if isinstance(totals, Mapping) else lambda key: getattr(totals, key)
    if get("display") is None:
        return "not determinable"
    return get("display") if get("complete") else INCOMPLETE_TOTAL.format(display=get("display"))


def _cell(value: Any) -> str:
    return "`" + str(value) + "`" if value is not None else "n/a"


def summary_markdown(inventory: Inventory, cost: UnmanagedCost) -> str:
    """The workflow step-summary section: counts, types, totals and one row per unmanaged resource (type, name,
    estimate, status). No resource ID, subscription, tag or IP address (none exists in the documents)."""
    c, t = inventory.counts, cost.totals
    lines = ["### Unmanaged Azure resources (outside Terraform)", "",
             "Not drift: these resources are not in Terraform state. Estimates are Azure Retail Prices API list "
             "prices (USD), not actual Azure billing, and separate from the Infracost Terraform plan estimate.", "",
             "| Field | Value |", "| --- | --- |",
             f"| Inventory | `{inventory.outcome}`" + (f" (`{inventory.failure}`)" if inventory.failure else "") + " |",
             f"| Resource groups | {', '.join(f'`{s.resource_group}` {s.status}' for s in inventory.scopes) or 'none'} |",
             f"| Listed | {c.listed} (managed by Terraform {c.managed}, unmanaged {c.unmanaged}, attached to a managed "
             f"resource {c.attached_to_managed}) |",
             "| Unmanaged by type | " + (", ".join(f"`{k}` {v}" for k, v in inventory.unmanaged_by_type.items())
                                       or "none") + " |",
             f"| Pricing | `{cost.status}`" + (f" (`{cost.failure}`)" if cost.failure else "") + " |",
             f"| Estimated monthly cost | {total_text(t)} ({t.estimated} estimated, {t.partial} "
             f"partial, {t.no_direct_charge} no direct charge, {t.unavailable} unavailable) |", ""]
    rows = [r for r in cost.resources]
    if rows:
        lines += ["| Ref | Type | Name | Estimate | Status |", "| --- | --- | --- | --- | --- |"]
        for r in rows:
            lines.append(f"| {r.ref} | {_cell(r.type)} | {_cell(r.name) if r.name else 'withheld'} | "
                         f"{r.display or 'unavailable'} | `{r.estimate_status}`"
                         + (f" (`{r.reason}`)" if r.reason else "") + " |")
        lines.append("")
    return "\n".join(lines) + "\n"
