"""Terraform plan cost delta, correlated with drift (Task 10.2).

`cost_delta(public_report, infracost, cost_run)` reads the sanitised Infracost
artifact of one drift-detection run (`infracost.json` and `cost_run.json`, Task 10.1
D8) together with that run's public drift report (Task 9B.4A), and returns the
`cost_delta_version` 1 document. Library only: no I/O, clock, network or Azure, and
the inputs and the drift result are never changed (Phase 10: cost is never drift).

Sign: `monthly_cost_delta` = -(Infracost diff `monthlyCost`) = list-price estimate of the
refreshed current configuration (`prior_state`) - list-price estimate of the declared
configuration (`planned_values`), Task 10.1 D3. Positive: the current configuration is
estimated to cost more than the declared one. Every amount is an Infracost list-price
estimate for Terraform-managed resources only, never actual Azure billing: resources
outside Terraform are invisible here (spec §6.3), and usage-based charges are not priced.

Rules (design locked 2026-10-11, PROJECT_PLAN.md Task 10.2):
- Binding fails closed: only the public drift report of the same run (run id,
  environment, canonical hash) and the pinned Infracost source are accepted.
- Money is a JSON decimal string, parsed with `Decimal` and computed exactly. A float,
  null or malformed amount fails; an absent optional amount stays `null`. A zero is
  never invented: `"0"` appears only when Infracost wrote it or as an exact sum.
- Infracost lines are matched to report resources by exact address only. Every
  diff line lands in exactly one group: confirmed drift, configuration, mixed,
  ambiguous or unmatched. Only confirmed drift is ever drift cost, and the combined
  Infracost plan total is never labelled as drift cost.
- `breakdown` / `pastBreakdown` values of a resource are shown only when they are
  comparable: the same name, once, in the same project as its diff line. They are
  never used to compute a delta.
- Resource lines are not required to sum to Infracost's totals (the input contract
  does not guarantee it); the difference is reported as a reconciliation residual.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Context, Decimal, Inexact
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from drift_engine.investigation_public import canonical_sha256
from drift_engine.report_public import validate_public

COST_DELTA_VERSION = "1"

# Task 10.1 constants (cost_run.json, D8); kept equal to scripts/sanitize_infracost.py by a test.
INFRACOST_VERSION = "v0.10.46"
MODE = "plan_json_breakdown"
PRICING = "list_prices_usd_no_usage_file"
COST_SIGN_CONVENTION = (
    "diffTotalMonthlyCost = totalMonthlyCost (desired, planned_values) - pastTotalMonthlyCost "
    "(actual, refreshed prior_state); drift cost = -diffTotalMonthlyCost"
)
SIGN_CONVENTION = (
    "monthly_cost_delta = -(Infracost diff monthlyCost) = list-price estimate of the refreshed current "
    "configuration (prior_state) - list-price estimate of the declared configuration (planned_values); "
    "Terraform-managed resources only, not actual Azure billing; positive: the current configuration "
    "is estimated to cost more than the declared one"
)
PLAN_DELTA_LABEL = ("Infracost plan total: drift and pending configuration changes combined; "
                    "not a drift cost")
# Fixed codes, always all published. The last two: amounts never cover resources outside
# Terraform (spec §6.3) and are list-price estimates, never actual Azure billing.
LIMITATIONS = ("list_prices_usd_no_usage_file", "exact_address_match", "absent_from_diff_is_not_zero",
               "subresources_not_attributed", "mixed_not_split", "terraform_managed_resources_only",
               "estimate_not_billing")

DRIFT_CLASSES = ("converged_drift", "external_deletion", "external_drift")
CONFIGURATION_CLASSES = ("config_change", "resource_added", "resource_removed")
MIXED_CLASSES = ("drift_and_config_change",)
GROUPS = ("confirmed_drift", "configuration", "mixed", "ambiguous", "unmatched")
ERROR_CODES = ("binding_mismatch", "currency_not_usd", "invalid_decimal", "invalid_structure",
               "not_public_report", "unsupported_source")

_DECIMAL = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")
_CENT = Decimal("0.01")


class CostDeltaError(Exception):
    """The inputs cannot be used (fail closed). `code` is one of ERROR_CODES; the
    message names a location, never a value."""

    def __init__(self, code: str, where: str) -> None:
        super().__init__(f"{code}: {where}")
        self.code = code
        self.where = where


# ---------------------------------------------------------------------------
# Output contract (cost_delta_version 1)
# ---------------------------------------------------------------------------

Money = Annotated[str, Field(pattern=_DECIMAL.pattern)]
Count = Annotated[int, Field(ge=0)]
Attribution = Literal["drift", "configuration", "mixed", "ambiguous"]
AttributionReason = Literal["undetermined_classification", "classifier_ambiguous", "inconsistent_drift_evidence",
                            "duplicate_cost_line"]
CostStatus = Literal["cost_line", "duplicate_cost_lines", "no_cost_change_listed", "no_price_resource_type",
                     "unsupported_resource_type", "not_in_cost_output"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Binding(_Model):
    run_id: str
    environment: str
    drift_report_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Source(_Model):
    infracost_version: Literal["v0.10.46"]
    mode: Literal["plan_json_breakdown"]
    pricing: Literal["list_prices_usd_no_usage_file"]
    currency: Literal["USD"]
    time_generated: str


class ResourceCost(_Model):
    address: str
    type: str
    classification: str
    drift_actions: list[str] | None
    attribution: Attribution
    attribution_reason: AttributionReason | None
    cost_status: CostStatus
    monthly_cost_delta: Money | None
    past_monthly_cost: Money | None
    desired_monthly_cost: Money | None
    display: str | None


class CostLine(_Model):
    name: str
    resource_type: str | None
    project: Count
    group: Literal["ambiguous", "unmatched"]
    reason: Literal["duplicate_name", "in_sync_in_report", "no_report_address"]
    monthly_cost_delta: Money | None
    display: str | None


class Subtotal(_Model):
    monthly_cost_delta: Money | None
    display: str | None
    with_cost: Count
    without_cost: Count
    complete: bool


class Amount(_Model):
    monthly_cost_delta: Money
    display: str


class PlanDelta(Amount):
    label: Literal[PLAN_DELTA_LABEL]  # type: ignore[valid-type]


class Totals(_Model):
    confirmed_drift: Subtotal
    configuration: Subtotal
    mixed: Subtotal
    ambiguous: Subtotal
    unmatched: Subtotal
    unreconciled: Amount
    infracost_plan_delta: PlanDelta
    past_monthly_cost: Money
    desired_monthly_cost: Money


class ProjectReconciliation(_Model):
    project: Count
    has_diff: bool
    lines: Count
    lines_without_amount: Count
    listed_diff_sum: Money | None
    reported_diff_total: Money | None
    residual: Money | None


class RootCheck(_Model):
    reported_diff_total: Money
    compared_to: Money
    residual: Money


class Reconciliation(_Model):
    status: Literal["reconciled", "residual"]
    projects: list[ProjectReconciliation]
    root_vs_projects: RootCheck
    root_vs_total_minus_past: RootCheck


class CostDelta(_Model):
    cost_delta_version: Literal["1"]
    binding: Binding
    source: Source
    sign_convention: Literal[SIGN_CONVENTION]  # type: ignore[valid-type]
    resources: list[ResourceCost]
    unmatched_cost_lines: list[CostLine]
    totals: Totals
    reconciliation: Reconciliation
    limitations: list[Literal[LIMITATIONS]]  # type: ignore[valid-type]

    @model_validator(mode="after")
    def _all_limitations(self) -> "CostDelta":
        # Exactly the seven codes: none missing, none repeated (unknown ones fail the Literal).
        if len(self.limitations) != len(LIMITATIONS) or set(self.limitations) != set(LIMITATIONS):
            raise ValueError("limitations must be exactly the defined codes, each once")
        return self


# ---------------------------------------------------------------------------
# Exact decimals
# ---------------------------------------------------------------------------

# Sums and negations are exact: amounts are at most MAX_DECIMAL_CHARS long, so even
# many of them never need more than this precision (a result needing rounding traps).
MAX_DECIMAL_CHARS = 40
_EXACT = Context(prec=200, traps=[Inexact])


def parse_money(value: Any, where: str) -> Decimal:
    """A JSON decimal string as an exact Decimal. Anything else (float, int, bool, null,
    exponent, malformed or over-long text) is `invalid_decimal`."""
    if not isinstance(value, str) or len(value) > MAX_DECIMAL_CHARS or not _DECIMAL.match(value):
        raise CostDeltaError("invalid_decimal", where)
    return Decimal(value)


def _optional_money(item: Mapping[str, Any], key: str, where: str) -> Decimal | None:
    """Absent -> None (not reported). Present -> must be a decimal string (null fails)."""
    if key not in item:
        return None
    return parse_money(item[key], f"{where}.{key}")


def _text(value: Decimal) -> str:
    """Plain decimal text as written (never an exponent), with a negative zero written as zero."""
    return format(value.copy_abs() if value.is_zero() else value, "f")


def _neg(value: Decimal) -> Decimal:
    return _EXACT.minus(value)


def _sum(values: list[Decimal]) -> Decimal:
    total = Decimal(0)
    for value in values:
        total = _EXACT.add(total, value)
    return total


def format_monthly_usd(value: Decimal) -> str:
    """Display only, rounded half-up to cents: `+$106.58/month`, `-$13.14/month`,
    `$0.00/month`. The exact value is always published next to it."""
    cents = value.quantize(_CENT, rounding=ROUND_HALF_UP, context=Context(prec=200))
    if cents.is_zero():
        return "$0.00/month"
    return f"{'+' if cents > 0 else '-'}${format(cents.copy_abs(), 'f')}/month"  # copy_abs: never rounds


# ---------------------------------------------------------------------------
# Input checks (fail closed)
# ---------------------------------------------------------------------------

def _mapping(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CostDeltaError("invalid_structure", where)
    return value


def _list(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise CostDeltaError("invalid_structure", where)
    return value


def _string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise CostDeltaError("invalid_structure", where)
    return value


def check_binding(public_report: Any, cost_run: Any) -> Binding:
    """The cost artifact must belong to this run's public drift report."""
    report = _mapping(public_report, "drift report")
    if report.get("public_version") != "1":
        raise CostDeltaError("not_public_report", "drift report")
    try:
        validate_public(report)
    except ValidationError:
        raise CostDeltaError("invalid_structure", "drift report") from None
    run = report["run"]
    manifest = _mapping(cost_run, "cost_run")
    expected_source = {"infracost_version": INFRACOST_VERSION, "mode": MODE, "pricing": PRICING,
                       "cost_sign_convention": COST_SIGN_CONVENTION}
    for key, value in expected_source.items():
        if manifest.get(key) != value:
            raise CostDeltaError("unsupported_source", f"cost_run.{key}")
    run_id = _string(manifest.get("run_id"), "cost_run.run_id")
    environment = _string(manifest.get("environment"), "cost_run.environment")
    if run_id != run.get("run_id"):
        raise CostDeltaError("binding_mismatch", "cost_run.run_id")
    if environment != run.get("environment"):
        raise CostDeltaError("binding_mismatch", "cost_run.environment")
    if manifest.get("drift_report_sha256") != canonical_sha256(report):
        raise CostDeltaError("binding_mismatch", "cost_run.drift_report_sha256")
    return Binding(run_id=run_id, environment=environment, drift_report_sha256=manifest["drift_report_sha256"])


class _Line:
    """One Infracost resource line of one breakdown."""

    def __init__(self, item: Any, project: int, where: str) -> None:
        item = _mapping(item, where)
        self.name = _string(item.get("name"), f"{where}.name")
        rtype = item.get("resourceType")
        self.resource_type = _string(rtype, f"{where}.resourceType") if "resourceType" in item else None
        self.monthly_cost = _optional_money(item, "monthlyCost", where)
        self.project = project


class _Project:
    def __init__(self, item: Any, index: int) -> None:
        where = f"infracost.projects[{index}]"
        item = _mapping(item, where)
        self.index = index
        self.lines: dict[str, list[_Line]] = {}
        self.totals: dict[str, Decimal] = {}
        for key in ("breakdown", "pastBreakdown", "diff"):
            if key not in item:
                if key == "breakdown":
                    raise CostDeltaError("invalid_structure", f"{where}.breakdown")
                continue
            breakdown = _mapping(item[key], f"{where}.{key}")
            self.totals[key] = parse_money(breakdown.get("totalMonthlyCost"), f"{where}.{key}.totalMonthlyCost")
            resources = _list(breakdown.get("resources"), f"{where}.{key}.resources")
            self.lines[key] = [_Line(r, index, f"{where}.{key}.resources[{i}]") for i, r in enumerate(resources)]

    def find(self, key: str, name: str) -> list[_Line]:
        return [line for line in self.lines.get(key, []) if line.name == name]


def _count_map(summary: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    counts = summary.get(key, {})
    return _mapping(counts, f"infracost.summary.{key}")


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------

def attribute(resource: Mapping[str, Any]) -> tuple[str, str | None]:
    """(attribution, reason) from the public report only: classification, drift_actions
    and the classifier's `ambiguous` flag. Only `drift` is ever counted as drift cost."""
    classification = resource.get("classification")
    has_drift = resource.get("drift_actions") is not None
    if classification == "undetermined":
        return "ambiguous", "undetermined_classification"
    if resource.get("ambiguous") is True:
        return "ambiguous", "classifier_ambiguous"
    if classification in DRIFT_CLASSES and has_drift:
        return "drift", None
    if classification in CONFIGURATION_CLASSES and not has_drift:
        return "configuration", None
    if classification in MIXED_CLASSES and has_drift:
        return "mixed", None
    return "ambiguous", "inconsistent_drift_evidence"


# ---------------------------------------------------------------------------
# Cost delta
# ---------------------------------------------------------------------------

def _subtotal(amounts: list[Decimal | None]) -> Subtotal:
    present = [a for a in amounts if a is not None]
    total = _sum(present) if present else None
    return Subtotal(monthly_cost_delta=None if total is None else _text(total),
                    display=None if total is None else format_monthly_usd(total),
                    with_cost=len(present), without_cost=len(amounts) - len(present),
                    complete=len(present) == len(amounts))


def _amount(value: Decimal) -> dict[str, str]:
    return {"monthly_cost_delta": _text(value), "display": format_monthly_usd(value)}


def cost_delta(public_report: Any, infracost: Any, cost_run: Any) -> dict[str, Any]:
    """The `cost_delta_version` 1 document (JSON-ready dict). Raises CostDeltaError."""
    binding = check_binding(public_report, cost_run)
    root = _mapping(infracost, "infracost")
    if root.get("currency") != "USD":
        raise CostDeltaError("currency_not_usd", "infracost.currency")
    time_generated = _string(root.get("timeGenerated"), "infracost.timeGenerated")
    plan_diff = parse_money(root.get("diffTotalMonthlyCost"), "infracost.diffTotalMonthlyCost")
    past_total = parse_money(root.get("pastTotalMonthlyCost"), "infracost.pastTotalMonthlyCost")
    desired_total = parse_money(root.get("totalMonthlyCost"), "infracost.totalMonthlyCost")
    summary = _mapping(root.get("summary"), "infracost.summary")
    no_price_types = _count_map(summary, "noPriceResourceCounts")
    unsupported_types = _count_map(summary, "unsupportedResourceCounts")
    projects_raw = _list(root.get("projects"), "infracost.projects")
    if not projects_raw:
        raise CostDeltaError("invalid_structure", "infracost.projects")
    projects = [_Project(p, i) for i, p in enumerate(projects_raw)]

    report_resources = _list(public_report.get("resources"), "drift report.resources")
    by_address: dict[str, Mapping[str, Any]] = {}
    for i, item in enumerate(report_resources):
        item = _mapping(item, f"drift report.resources[{i}]")
        by_address[_string(item.get("address"), f"drift report.resources[{i}].address")] = item

    # How often each name occurs, per project and list: a name is pairable only when it
    # occurs in one project at most and at most once in each of that project's lists.
    occurrences: dict[str, set[int]] = {}
    repeated: set[str] = set()
    for project in projects:
        for lines in project.lines.values():
            for name, count in Counter(line.name for line in lines).items():
                occurrences.setdefault(name, set()).add(project.index)
                if count > 1:
                    repeated.add(name)
    duplicates = {name for name, where in occurrences.items() if len(where) > 1} | repeated

    resources: list[dict[str, Any]] = []
    group_amounts: dict[str, list[Decimal | None]] = {group: [] for group in GROUPS}
    attributed_lines: set[int] = set()
    for item in report_resources:
        if item.get("classification") == "in_sync":
            continue
        address = item["address"]
        attribution, reason = attribute(item)
        delta = past = desired = None
        if address in duplicates:
            attribution, reason, status = "ambiguous", "duplicate_cost_line", "duplicate_cost_lines"
        else:
            project = next((p for p in projects if p.index in occurrences.get(address, set())), None)
            diff_line = project.find("diff", address) if project else []
            if project is not None:
                past_lines, desired_lines = project.find("pastBreakdown", address), project.find("breakdown", address)
                past = past_lines[0].monthly_cost if past_lines else None
                desired = desired_lines[0].monthly_cost if desired_lines else None
            if diff_line:
                status = "cost_line"
                attributed_lines.add(id(diff_line[0]))
                delta = None if diff_line[0].monthly_cost is None else _neg(diff_line[0].monthly_cost)
            elif project is not None:
                status = "no_cost_change_listed"
            elif item.get("type") in no_price_types and item.get("type") not in unsupported_types:
                status = "no_price_resource_type"
            elif item.get("type") in unsupported_types and item.get("type") not in no_price_types:
                status = "unsupported_resource_type"
            else:
                status = "not_in_cost_output"
            group_amounts["confirmed_drift" if attribution == "drift" else attribution].append(delta)
        if status == "duplicate_cost_lines":
            group_amounts["ambiguous"].append(None)
        resources.append({
            "address": address, "type": item.get("type"), "classification": item.get("classification"),
            "drift_actions": item.get("drift_actions"), "attribution": attribution, "attribution_reason": reason,
            "cost_status": status, "monthly_cost_delta": None if delta is None else _text(delta),
            "past_monthly_cost": None if past is None else _text(past),
            "desired_monthly_cost": None if desired is None else _text(desired),
            "display": None if delta is None else format_monthly_usd(delta),
        })

    # Diff lines not attributed above: never dropped, never attributed to drift.
    unmatched: list[dict[str, Any]] = []
    for project in projects:
        for line in project.lines.get("diff", []):
            if id(line) in attributed_lines:
                continue
            report_item = by_address.get(line.name)
            if line.name in duplicates:
                group, why = "ambiguous", "duplicate_name"
            elif report_item is not None and report_item.get("classification") == "in_sync":
                group, why = "unmatched", "in_sync_in_report"
            else:
                group, why = "unmatched", "no_report_address"
            delta = None if line.monthly_cost is None else _neg(line.monthly_cost)
            group_amounts[group].append(delta)
            unmatched.append({"name": line.name, "resource_type": line.resource_type, "project": project.index,
                              "group": group, "reason": why,
                              "monthly_cost_delta": None if delta is None else _text(delta),
                              "display": None if delta is None else format_monthly_usd(delta)})

    # Reconciliation (Infracost's own diff sign). Reported, never enforced.
    project_checks = []
    listed_all: list[Decimal] = []
    project_totals: list[Decimal] = []
    residual_found = False
    for project in projects:
        lines = project.lines.get("diff")
        if lines is None:
            project_checks.append({"project": project.index, "has_diff": False, "lines": 0, "lines_without_amount": 0,
                                   "listed_diff_sum": None, "reported_diff_total": None, "residual": None})
            continue
        listed = [line.monthly_cost for line in lines if line.monthly_cost is not None]
        listed_sum = _sum(listed)
        residual = _EXACT.subtract(project.totals["diff"], listed_sum)
        residual_found |= not residual.is_zero() or len(listed) != len(lines)
        listed_all += listed
        project_totals.append(project.totals["diff"])
        project_checks.append({"project": project.index, "has_diff": True, "lines": len(lines),
                               "lines_without_amount": len(lines) - len(listed), "listed_diff_sum": _text(listed_sum),
                               "reported_diff_total": _text(project.totals["diff"]), "residual": _text(residual)})
    vs_projects = _EXACT.subtract(plan_diff, _sum(project_totals))
    total_minus_past = _EXACT.subtract(desired_total, past_total)
    vs_total = _EXACT.subtract(plan_diff, total_minus_past)
    residual_found |= not vs_projects.is_zero() or not vs_total.is_zero()

    plan_delta = _neg(plan_diff)
    unreconciled = _EXACT.subtract(plan_delta, _neg(_sum(listed_all)))
    document = {
        "cost_delta_version": COST_DELTA_VERSION,
        "binding": binding.model_dump(),
        "source": {"infracost_version": INFRACOST_VERSION, "mode": MODE, "pricing": PRICING, "currency": "USD",
                   "time_generated": time_generated},
        "sign_convention": SIGN_CONVENTION,
        "resources": resources,
        "unmatched_cost_lines": unmatched,
        "totals": {
            **{group: _subtotal(group_amounts[group]).model_dump() for group in GROUPS},
            "unreconciled": _amount(unreconciled),
            "infracost_plan_delta": {**_amount(plan_delta), "label": PLAN_DELTA_LABEL},
            "past_monthly_cost": _text(past_total),
            "desired_monthly_cost": _text(desired_total),
        },
        "reconciliation": {
            "status": "residual" if residual_found else "reconciled",
            "projects": project_checks,
            "root_vs_projects": {"reported_diff_total": _text(plan_diff), "compared_to": _text(_sum(project_totals)),
                                 "residual": _text(vs_projects)},
            "root_vs_total_minus_past": {"reported_diff_total": _text(plan_diff),
                                         "compared_to": _text(total_minus_past), "residual": _text(vs_total)},
        },
        "limitations": list(LIMITATIONS),
    }
    return CostDelta.model_validate(document).model_dump(mode="json")
