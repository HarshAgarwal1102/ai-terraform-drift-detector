"""Cost and configuration routing and section handlers (Task 6.4).

`route_cost_config` (deterministic, no LLM) writes two write-once fields:

- `cost_targets`: changes relevant to cost. Two routes, both read from the
  report only:
    lifecycle  the resource is added, removed or deleted outside Terraform, or
               planned for replace: every non-noise change of that resource;
    attribute  the change's top-level attribute (or a nested map key) matches
               COST_ATTRIBUTE_PATTERNS: SKU, tier, size, capacity, counts, ...
  This list is routing data only. It rates nothing and classifies nothing.
- `config_targets`: every non-noise change of a non-in-sync resource (tag drift
  is configuration drift too), plus a deterministic per-resource summary: counts
  by attribute class and assessment, paths Terraform reverts on apply, pending
  configuration changes, ambiguous and unknown-until-apply paths. The summary
  only regroups the report; nothing is re-classified.

The LLM sections are validated here (`validate_cost_section`,
`validate_configuration_section`) and called from the single LLM node
`analyze_drift`. The LLM never receives or states amounts: a finding has only a
qualitative `direction`, and `contains_cost_claim` is the deterministic guard
against invented amounts, prices, rates or savings.

Cost impact (Task 10.3, report v3) is deterministic. `load_cost_input` reads the
sanitised `infracost-report` (Task 10.1) and calls `drift_engine.cost.cost_delta`
(Task 10.2), the only source of every amount, giving status `complete`,
`not_available` (no input) or `rejected` (a fixed code). `derive_cost_impact`
turns that into fixed `cost.*.v1` statements and, per resource, the
authoritative `estimate_direction`. The LLM may receive only that direction
(never an amount); a finding whose direction contradicts it is rejected
(`direction_conflicts_with_estimate`), and the cost section's free-text summary
is withheld when cost is `complete`.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from decimal import Decimal
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, ValidationError

from ai_engine.evidence import cited_keys, evidence_lookup, evidence_refs, severity_rank
from ai_engine.nodes.common import CitedPath, Strict, free_text_violation
from drift_engine import cost as cost_engine
from drift_engine.investigation_public import canonical_sha256, strict_json
from drift_engine.logs import log_event

logger = logging.getLogger(__name__)

LIFECYCLE_CLASSES = ("resource_added", "resource_removed", "external_deletion")
NOISE = "noise"
DRIFT_CLASSES = ("drifted", "drifted_converged", "drifted_and_config_changed")
NOT_DETERMINABLE = "not_determinable_from_evidence"

# Routing-only: attribute names whose change plausibly changes what Azure bills.
COST_ATTRIBUTE_PATTERNS = (
    "sku", "sku_*", "*_sku", "*_sku_*", "tier", "*_tier", "*_replication_type", "replication_type",
    "size", "vm_size", "*_vm_size", "capacity", "*_capacity", "instances", "instance_count", "*_count",
    "*_mb", "*_gb", "throughput", "*_throughput", "zone_redundant", "zone_redundancy_enabled", "zones",
    "autoscale*", "*_autoscale*",
)
NOT_COST_ATTRIBUTES = ("tags", "description")


def _cost_attribute(path: list[str]) -> str | None:
    if path[0] in NOT_COST_ATTRIBUTES:
        return None
    for name in dict.fromkeys((path[0], path[-1])):
        if any(fnmatchcase(name, pattern) for pattern in COST_ATTRIBUTE_PATTERNS):
            return name
    return None


def _cost_reason(resource: Mapping[str, Any], change: Mapping[str, Any]) -> str | None:
    if change["assessment"]["category"] == NOISE:
        return None
    if resource["classification"] in LIFECYCLE_CLASSES:
        return f"lifecycle: {resource['classification']}"
    if resource["action"] == "replace":
        return "lifecycle: planned replace"
    attribute = _cost_attribute(list(change["path"]))
    return f"cost attribute: {attribute}" if attribute else None


def _config_reason(change: Mapping[str, Any]) -> str | None:
    category = change["assessment"]["category"]
    if category == NOISE:
        return None
    return f"configuration: {change['class'] or 'object created or deleted'} ({category})"


def _config_summary(resource: Mapping[str, Any]) -> dict[str, Any]:
    changes = [c for c in resource["attribute_changes"] if c["assessment"]["category"] != NOISE]
    by_class: dict[str, int] = {}
    by_assessment: dict[str, int] = {}
    for change in changes:
        key = change["class"] or "object_level"
        by_class[key] = by_class.get(key, 0) + 1
        by_assessment[change["assessment"]["category"]] = by_assessment.get(change["assessment"]["category"], 0) + 1

    def paths(predicate) -> list[list[str]]:
        return [list(c["path"]) for c in changes if predicate(c)]

    update = resource["action"] == "update"
    return {
        "address": resource["address"],
        "classification": resource["classification"],
        "action": resource["action"],
        "changes_by_class": dict(sorted(by_class.items())),
        "changes_by_assessment": dict(sorted(by_assessment.items())),
        "reverted_on_apply": paths(lambda c: update and c["class"] in DRIFT_CLASSES),
        "pending_config_changes": paths(lambda c: c["class"] == "config_changed"),
        "ambiguous": paths(lambda c: c["class"] == "drifted_and_config_changed"),
        "unknown_until_apply": paths(lambda c: c["class"] == "unknown_until_apply"),
        "unconfigured_reverted": paths(lambda c: update and c["class"] in DRIFT_CLASSES
                                       and c["assessment"]["category"] == "unconfigured"),
        "noise_excluded": len(resource["attribute_changes"]) - len(changes),
    }


def route_cost_config(state: Mapping[str, Any]) -> dict[str, Any]:
    """LangGraph node: deterministic cost and configuration routing."""
    cost: list[dict[str, Any]] = []
    config: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    for resource in state["parsed_drift"]["resources"]:
        for change in resource["attribute_changes"]:
            key = {"address": resource["address"], "path": list(change["path"]),
                   "severity": change["severity"]["level"]}
            reason = _cost_reason(resource, change)
            if reason:
                cost.append({**key, "section": "cost", "reason": reason})
            reason = _config_reason(change)
            if reason:
                config.append({**key, "section": "configuration", "reason": reason})
        summary.append(_config_summary(resource))
    update = {
        "cost_targets": {"changes": cost, "addresses": sorted({c["address"] for c in cost})},
        "config_targets": {"changes": config, "addresses": sorted({c["address"] for c in config}),
                           "summary": summary},
    }
    log_event(logger, logging.INFO, "cost_config_routed", "cost and configuration changes routed",
              cost=len(cost), configuration=len(config))
    return update


# --------------------------------------------------------------------------- cost impact (Task 10.3)

COST_FILES = ("cost_run.json", "infracost.json")
MAX_COST_FILE_BYTES = 10 * 1024 * 1024
NOT_PROVIDED = "cost_input_not_provided"
INPUT_REJECTIONS = ("cost_input_unreadable", "cost_input_incomplete")
REJECTION_CODES = tuple(sorted(cost_engine.ERROR_CODES + INPUT_REJECTIONS))
DIRECTIONS = ("increase", "decrease", "no_change", "not_determinable")
SUMMARY_WITHHELD = "summary withheld: the deterministic cost estimate is authoritative"
PRICING_SOURCE = "infracost_list_prices_usd_no_usage_file"
# LLM direction -> the deterministic estimate directions it contradicts ("undetermined" never conflicts).
CONFLICTS = {"likely_increase": ("decrease", "no_change"), "likely_decrease": ("increase", "no_change"),
             "likely_neutral": ("increase", "decrease"), "undetermined": ()}
GROUP_LABELS = {  # every group except confirmed_drift is explicitly not drift cost
    "confirmed_drift": "Confirmed drift (the only drift cost)",
    "configuration": "Pending configuration changes (not drift cost)",
    "mixed": "Mixed drift and configuration changes (not split; not drift cost)",
    "ambiguous": "Ambiguous attribution (not drift cost)",
    "unmatched": "Unmatched Infracost lines (not attributed)",
}
_ESTIMATE_NOTE = "Infracost list-price estimate, not actual Azure billing"
COST_TEMPLATES: dict[str, str] = {
    "cost.status_complete.v1": "Cost figures are Infracost list-price estimates (USD, no usage file) of the refreshed "
                               "current configuration versus the declared configuration, for Terraform-managed "
                               "resources only; they are not actual Azure billing, and resources outside Terraform "
                               "are not covered.",
    "cost.status_not_available.v1": "No cost estimate was provided: monetary impact is not determinable from "
                                    "available evidence.",
    "cost.status_rejected.v1": "The cost estimate was rejected ({code}): monetary impact is not determinable from "
                               "available evidence.",
    "cost.resource.v1": "Estimated monthly cost impact on {address}: {display} ({delta} USD per month; current "
                        "configuration {past}, declared configuration {desired}); attribution {attribution}; "
                        + _ESTIMATE_NOTE + ".",
    "cost.resource_unpriced.v1": "Monthly cost impact on {address}: not determinable from available evidence "
                                 "({cost_status}); attribution {attribution}.",
    "cost.group.v1": "{label}: {amount} from {with_cost} priced line(s){incomplete}.",
    "cost.no_drift_cost.v1": "Confirmed drift has no cost line: no drift-attributable cost impact is reported.",
    "cost.plan_delta.v1": "Infracost plan total: {display} ({delta} USD per month); drift and pending configuration "
                          "changes combined; not a drift cost.",
    "cost.reconciliation.v1": "Infracost's totals do not reconcile with its resource lines ({checks} check(s) differ, "
                              "{missing} line(s) without an amount); {display} ({delta} USD per month) of the plan "
                              "total is unattributed and reported as unreconciled.",
}


def cost_statement(template_id: str, **slots: Any) -> dict[str, str]:
    return {"id": template_id, "text": COST_TEMPLATES[template_id].format(**slots)}


def _money(value: str | None) -> str:
    return "not reported" if value is None else f"{value} USD per month"


def estimate_direction(monthly_cost_delta: str | None) -> str:
    """Authoritative direction of a resource's estimate: the sign of `monthly_cost_delta` (exact decimal text)."""
    if monthly_cost_delta is None:
        return "not_determinable"
    sign = Decimal(monthly_cost_delta).compare(Decimal(0))
    return "increase" if sign > 0 else "decrease" if sign < 0 else "no_change"


def direction_conflicts(llm_direction: str, estimate: str) -> bool:
    return estimate in CONFLICTS[llm_direction]


def _not_complete(status: str, reason: str, input_sha256: Mapping[str, str] | None = None) -> dict[str, Any]:
    return {"status": status, "reason": reason, "cost_delta": None,
            "input_sha256": dict(input_sha256) if input_sha256 else None}


NOT_AVAILABLE = _not_complete("not_available", NOT_PROVIDED)


def cost_input(drift_report: Mapping[str, Any], infracost: Any, cost_run: Any) -> dict[str, Any]:
    """The cost input of a run from parsed `infracost.json` / `cost_run.json`: `complete` with the validated
    `cost_delta` v1 document, or `rejected` with the `cost_delta` error code. Hashes use the Task 10.2
    canonicalization of the parsed documents."""
    hashes = {"infracost": canonical_sha256(infracost), "cost_run": canonical_sha256(cost_run)}
    try:
        document = cost_engine.cost_delta(drift_report, infracost, cost_run)
    except cost_engine.CostDeltaError as exc:
        return _not_complete("rejected", exc.code, hashes)
    return {"status": "complete", "reason": None, "cost_delta": document, "input_sha256": hashes}


def rejected_cost(code: str) -> dict[str, Any]:
    """A `rejected` cost input that never parsed (no hashes)."""
    return _not_complete("rejected", code)


def read_cost_documents(directory: str | os.PathLike) -> dict[str, Any] | str:
    """{"infracost": ..., "cost_run": ...} parsed (strict JSON) from an `infracost-report` directory holding exactly
    `infracost.json` and `cost_run.json`, or the rejection code (`cost_input_unreadable` / `cost_input_incomplete`).
    Never raises for a bad directory and never returns file content in a code."""
    path = Path(directory)
    try:
        names = sorted(entry.name for entry in path.iterdir())
    except OSError:
        return "cost_input_unreadable"
    if tuple(names) != COST_FILES or not all((path / name).is_file() for name in names):
        return "cost_input_incomplete"
    documents = {}
    for name in COST_FILES:
        try:
            with open(path / name, "rb") as fh:
                data = fh.read(MAX_COST_FILE_BYTES + 1)
            if len(data) > MAX_COST_FILE_BYTES:
                return "cost_input_unreadable"
            documents[name] = strict_json(data)
        except (OSError, ValueError, RecursionError, UnicodeDecodeError):
            return "cost_input_unreadable"
    return {"infracost": documents["infracost.json"], "cost_run": documents["cost_run.json"]}


def load_cost_input(directory: str | os.PathLike, drift_report: Mapping[str, Any]) -> dict[str, Any]:
    """`cost_input` from an `infracost-report` directory; a directory that cannot be used is `rejected`."""
    documents = read_cost_documents(directory)
    if isinstance(documents, str):
        return rejected_cost(documents)
    return cost_input(drift_report, documents["infracost"], documents["cost_run"])


def _resource_statement(entry: Mapping[str, Any]) -> dict[str, str]:
    if entry["monthly_cost_delta"] is None:
        return cost_statement("cost.resource_unpriced.v1", address=entry["address"],
                              cost_status=entry["cost_status"], attribution=entry["attribution"])
    return cost_statement("cost.resource.v1", address=entry["address"], display=entry["display"],
                          delta=entry["monthly_cost_delta"], past=_money(entry["past_monthly_cost"]),
                          desired=_money(entry["desired_monthly_cost"]), attribution=entry["attribution"])


def _group_statement(group: str, subtotal: Mapping[str, Any]) -> dict[str, str]:
    amount = ("not determinable from available evidence" if subtotal["monthly_cost_delta"] is None
              else f"{subtotal['display']} ({subtotal['monthly_cost_delta']} USD per month)")
    incomplete = "" if subtotal["complete"] else f"; incomplete: {subtotal['without_cost']} without a price"
    return cost_statement("cost.group.v1", label=GROUP_LABELS[group], amount=amount,
                          with_cost=subtotal["with_cost"], incomplete=incomplete)


def _differing_checks(reconciliation: Mapping[str, Any]) -> int:
    residuals = [p["residual"] for p in reconciliation["projects"] if p["has_diff"]]
    residuals += [reconciliation[key]["residual"] for key in ("root_vs_projects", "root_vs_total_minus_past")]
    return sum(1 for value in residuals if Decimal(value) != 0)


def cost_statements(cost: Mapping[str, Any]) -> list[dict[str, str]]:
    """The run-level cost statements of a cost input: exactly one status statement unless `complete`."""
    if cost["status"] == "not_available":
        return [cost_statement("cost.status_not_available.v1")]
    if cost["status"] == "rejected":
        return [cost_statement("cost.status_rejected.v1", code=cost["reason"])]
    document = cost["cost_delta"]
    totals = document["totals"]
    out = [cost_statement("cost.status_complete.v1")]
    for group in cost_engine.GROUPS:
        subtotal = totals[group]
        if subtotal["with_cost"] + subtotal["without_cost"]:
            out.append(_group_statement(group, subtotal))
        elif group == "confirmed_drift":
            out.append(cost_statement("cost.no_drift_cost.v1"))
    plan = totals["infracost_plan_delta"]
    out.append(cost_statement("cost.plan_delta.v1", display=plan["display"], delta=plan["monthly_cost_delta"]))
    reconciliation = document["reconciliation"]
    if reconciliation["status"] == "residual":
        residual = totals["unreconciled"]
        out.append(cost_statement("cost.reconciliation.v1", checks=_differing_checks(reconciliation),
                                  missing=sum(p["lines_without_amount"] for p in reconciliation["projects"]),
                                  display=residual["display"], delta=residual["monthly_cost_delta"]))
    return out


def derive_cost_impact(state: Mapping[str, Any]) -> dict[str, Any]:
    """LangGraph node: deterministic cost impact (Task 10.3). Re-checks a `complete` input against the v1
    contract and this drift report (an inconsistent input is an internal error, never a silent result)."""
    cost = state.get("cost") or NOT_AVAILABLE  # an unset channel reads as LangGraph's empty seed
    status = cost["status"]
    if status not in ("complete", "not_available", "rejected"):
        raise ValueError("cost input status is invalid")
    impact: dict[str, Any] = {"status": status, "reason": cost["reason"], "cost_delta": None,
                              "input_sha256": cost.get("input_sha256"), "resources": {}, "directions": {}}
    if status == "complete":
        try:
            plain = json.loads(json.dumps(cost["cost_delta"]))  # frozen state -> plain JSON for the strict model
            document = cost_engine.CostDelta.model_validate(plain).model_dump(mode="json")
        except ValidationError:
            raise ValueError("cost input is not a valid cost_delta v1 document") from None
        if document["binding"]["drift_report_sha256"] != canonical_sha256(state["drift_report"]):
            raise ValueError("cost input is bound to another drift report")
        impact["cost_delta"] = document
        for entry in document["resources"]:
            impact["resources"][entry["address"]] = {**entry, "statements": [_resource_statement(entry)]}
            impact["directions"][entry["address"]] = estimate_direction(entry["monthly_cost_delta"])
    elif cost["cost_delta"] is not None or (status == "rejected" and cost["reason"] not in REJECTION_CODES) \
            or (status == "not_available" and cost["reason"] != NOT_PROVIDED):
        raise ValueError("cost input reason is inconsistent with its status")
    impact["statements"] = cost_statements({**cost, "cost_delta": impact["cost_delta"]})
    log_event(logger, logging.INFO, "cost_impact_derived", "cost impact derived", status=status,
              resources=len(impact["resources"]))
    return {"cost_impact": impact}


# --------------------------------------------------------------------------- section schemas


class CostFinding(Strict):
    address: Annotated[str, Field(min_length=1, max_length=512)]
    cited_paths: Annotated[list[CitedPath], Field(min_length=1, max_length=20)]
    cost_driver: Literal["sku_or_tier", "capacity_or_count", "resource_lifecycle", "other"]
    direction: Literal["likely_increase", "likely_decrease", "likely_neutral", "undetermined"]
    monetary_impact: Literal["not_determinable_from_evidence"]
    explanation: Annotated[str, Field(min_length=1, max_length=1500)]
    basis: Literal["inference"]


class CostSection(Strict):
    findings: Annotated[list[CostFinding], Field(max_length=50)]
    summary: Annotated[str, Field(max_length=2000)]


ConfigTopic = Literal["declared_value_overridden", "unmanaged_setting", "pending_config_change", "ambiguous_change",
                      "value_unknown_until_apply", "other"]


class ConfigurationFinding(Strict):
    address: Annotated[str, Field(min_length=1, max_length=512)]
    cited_paths: Annotated[list[CitedPath], Field(min_length=1, max_length=20)]
    topic: ConfigTopic
    explanation: Annotated[str, Field(min_length=1, max_length=1500)]
    basis: Literal["inference"]


class ConfigurationSection(Strict):
    findings: Annotated[list[ConfigurationFinding], Field(max_length=50)]
    summary: Annotated[str, Field(max_length=2000)]


def _deterministic_severity(known: Mapping, keys: list) -> str:
    return max((known[key] for key in keys), key=severity_rank)


def validate_cost_section(output: CostSection, evidence: Mapping[str, Any]) -> tuple[list[dict], list[dict]]:
    known = cited_keys(evidence, "cost")
    lookup = evidence_lookup(evidence)
    refs = evidence_refs(evidence)
    accepted, rejected = [], []
    for index, finding in enumerate(output.findings):
        keys = [(finding.address, tuple(path)) for path in finding.cited_paths]
        if not all(key in known for key in keys):
            rejected.append({"index": index, "reason": "unsupported_citation"})
            continue
        violation = free_text_violation(finding.explanation, refs)  # all free-text guards
        if violation:
            rejected.append({"index": index, "reason": violation})
            continue
        resource = lookup[keys[0]][0]
        # Task 10.3: the deterministic direction sent with the evidence is authoritative; a contradicting finding
        # (and its explanation) is never published.
        estimate = resource.get("cost_estimate_direction") or "not_determinable"
        if direction_conflicts(finding.direction, estimate):
            rejected.append({"index": index, "reason": "direction_conflicts_with_estimate"})
            continue
        accepted.append({
            "address": finding.address,
            "cited_paths": [list(path) for path in finding.cited_paths],
            "cost_driver": finding.cost_driver,
            "direction": finding.direction,  # inference, qualitative only
            "estimate_direction": estimate,  # deterministic (Task 10.3); amounts are attached by the report only
            "deterministic_severity": _deterministic_severity(known, keys),
            "classification": resource["classification"],
            "action": resource["action"],
            "explanation": finding.explanation,
            "basis": "inference",
        })
    return accepted, rejected


# Which deterministic facts make a topic consistent with the cited evidence.
def _topic_supported(topic: str, resource: Mapping[str, Any], change: Mapping[str, Any]) -> bool:
    cls, assessment = change["class"], change["assessment"]
    if topic == "declared_value_overridden":
        return cls in DRIFT_CLASSES
    if topic == "unmanaged_setting":
        return assessment in ("unconfigured", "undetermined")
    if topic == "pending_config_change":
        return cls in ("config_changed", "drifted_and_config_changed") or (
            cls is None and resource["action"] in ("create", "delete", "replace"))
    if topic == "ambiguous_change":
        return cls == "drifted_and_config_changed" or bool(resource["ambiguous"])
    if topic == "value_unknown_until_apply":
        return cls == "unknown_until_apply" or change["desired"]["status"] == "unknown"
    return True  # "other" makes no claim about the class


def validate_configuration_section(output: ConfigurationSection,
                                   evidence: Mapping[str, Any]) -> tuple[list[dict], list[dict]]:
    known = cited_keys(evidence, "configuration")
    lookup = evidence_lookup(evidence)
    refs = evidence_refs(evidence)
    accepted, rejected = [], []
    for index, finding in enumerate(output.findings):
        keys = [(finding.address, tuple(path)) for path in finding.cited_paths]
        if not all(key in known for key in keys):
            rejected.append({"index": index, "reason": "unsupported_citation"})
            continue
        violation = free_text_violation(finding.explanation, refs)  # all free-text guards
        if violation:
            rejected.append({"index": index, "reason": violation})
            continue
        facts = [{"path": list(path), "class": lookup[key][1]["class"], "assessment": lookup[key][1]["assessment"]}
                 for path, key in zip(finding.cited_paths, keys)]
        accepted.append({
            "address": finding.address,
            "cited_paths": [list(path) for path in finding.cited_paths],
            "topic": finding.topic,  # inference: what the explanation is about
            "evidence_facts": facts,  # deterministic attribute class / assessment, authoritative
            "topic_conflicts_with_evidence": not any(_topic_supported(finding.topic, *lookup[key]) for key in keys),
            "deterministic_severity": _deterministic_severity(known, keys),
            "explanation": finding.explanation,
            "basis": "inference",
        })
    return accepted, rejected
