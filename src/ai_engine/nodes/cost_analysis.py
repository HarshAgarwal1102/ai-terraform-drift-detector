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
`analyze_drift`. Cost is pricing-free in Phase 6: the evidence holds no prices,
so a finding has only a qualitative `direction` and the constant
`monetary_impact = "not_determinable_from_evidence"`. `contains_cost_claim` is
the deterministic guard against invented amounts, prices, rates or savings.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from fnmatch import fnmatchcase
from typing import Annotated, Any, Literal

from pydantic import Field

from ai_engine.evidence import cited_keys, evidence_lookup, severity_rank
from ai_engine.nodes.common import CitedPath, Strict, contains_cost_claim
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
    accepted, rejected = [], []
    for index, finding in enumerate(output.findings):
        keys = [(finding.address, tuple(path)) for path in finding.cited_paths]
        if not all(key in known for key in keys):
            rejected.append({"index": index, "reason": "unsupported_citation"})
            continue
        if contains_cost_claim(finding.explanation):
            rejected.append({"index": index, "reason": "unsupported_cost_claim"})
            continue
        resource = lookup[keys[0]][0]
        accepted.append({
            "address": finding.address,
            "cited_paths": [list(path) for path in finding.cited_paths],
            "cost_driver": finding.cost_driver,
            "direction": finding.direction,  # inference, qualitative only
            "monetary_impact": NOT_DETERMINABLE,
            "pricing_source": None,  # Phase 10 (Infracost) supplies real figures
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
    accepted, rejected = [], []
    for index, finding in enumerate(output.findings):
        keys = [(finding.address, tuple(path)) for path in finding.cited_paths]
        if not all(key in known for key in keys):
            rejected.append({"index": index, "reason": "unsupported_citation"})
            continue
        if contains_cost_claim(finding.explanation):
            rejected.append({"index": index, "reason": "unsupported_cost_claim"})
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
