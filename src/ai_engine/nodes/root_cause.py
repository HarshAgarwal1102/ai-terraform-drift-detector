"""Origin facts, risk factors and the root-cause / risk section handlers (Task 6.5).

`derive_origin_risk` (deterministic, no LLM) writes the write-once
`AiState.origin_facts` from report fields only:

- per change: the **origin category**, i.e. which side of Terraform's three
  views changed, restated from the attribute class and resource classification:

      outside_terraform            remote differs from recorded state; declared = recorded
      outside_terraform_converged  remote changed and now equals the declaration
      configuration_side           declared differs from recorded (code, tfvars, module or
                                   provider default: not distinguishable)
      both_sides                   remote and declaration both changed
      value_unknown_until_apply    the planned value is not known yet
      undetermined                 the engine could not explain the change

  plus `lifecycle` (object created/deleted, no attribute class) and the
  deterministic **risk factors** of the change;
- per resource: moved, importing, action_reason, ambiguous and the union of
  its risk factors (`moved` is a boolean; the previous address is not copied);
- routes for the `root_cause` section (every non-noise change of a changed
  resource) and the `risk` section (changes with at least one risk factor).

Nothing is re-classified: every value is a lookup on fields drift_engine
already decided. Who made a change, when, and through which channel come only
from the deterministic public investigation (Task 9B.4,
`ai_engine.nodes.investigation_facts`): root-cause findings are hypotheses about
the kind of origin and carry no actor; the report's `who.actor_attribution` is
the only place attribution appears.

The LLM sections (`root_cause_analysis`, `risk_assessment`) are part of the
single `analyze_drift` call and validated here: section-scoped citations, the
deterministic free-text guards (cost, attribution, remediation), and evidence
consistency. A hypothesis that contradicts the cited changes' origin is
rejected (`hypothesis_contradicts_evidence`); a `risk_kind` must match a
deterministic factor of the cited changes (`risk_not_supported_by_evidence`;
`other` is kept and flagged). There is no AI risk level: deterministic
severity remains the only authoritative rating.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import Field

from ai_engine.evidence import cited_keys, evidence_lookup, evidence_refs, severity_rank
from ai_engine.nodes.common import CitedPath, EvidenceRefs, Strict, free_text_violation
from drift_engine.logs import log_event

logger = logging.getLogger(__name__)

NOISE = "noise"
REVERTIBLE_CLASSES = ("drifted", "drifted_and_config_changed")

ORIGIN_BY_CLASS = {
    "drifted": "outside_terraform",
    "drifted_converged": "outside_terraform_converged",
    "config_changed": "configuration_side",
    "drifted_and_config_changed": "both_sides",
    "unknown_until_apply": "value_unknown_until_apply",
}
# Object-level changes (create/delete: no attribute class) take their origin from the resource class.
ORIGIN_BY_RESOURCE_CLASS = {
    "external_drift": "outside_terraform",
    "external_deletion": "outside_terraform",
    "converged_drift": "outside_terraform_converged",
    "config_change": "configuration_side",
    "resource_added": "configuration_side",
    "resource_removed": "configuration_side",
    "drift_and_config_change": "both_sides",
    "undetermined": "undetermined",
}

RISK_FACTORS = ("apply_reverts_external_change", "apply_destroys_or_recreates", "ambiguous_intent",
                "unmanaged_setting", "value_unknown_until_apply", "redacted_unreadable", "moved_or_importing")


def origin_category(resource: Mapping[str, Any], change: Mapping[str, Any]) -> str:
    if resource["classification"] == "undetermined":
        return "undetermined"
    if change["class"] is not None:
        return ORIGIN_BY_CLASS[change["class"]]
    return ORIGIN_BY_RESOURCE_CLASS[resource["classification"]]


def change_risk_factors(resource: Mapping[str, Any], change: Mapping[str, Any]) -> list[str]:
    factors = []
    if resource["action"] == "update" and change["class"] in REVERTIBLE_CLASSES:
        factors.append("apply_reverts_external_change")
    if resource["action"] in ("replace", "delete") or resource["classification"] == "external_deletion":
        factors.append("apply_destroys_or_recreates")
    if change["class"] == "drifted_and_config_changed" or resource["ambiguous"]:
        factors.append("ambiguous_intent")
    if change["assessment"]["category"] == "unconfigured":
        factors.append("unmanaged_setting")
    if change["class"] == "unknown_until_apply" or change["desired"]["status"] == "unknown":
        factors.append("value_unknown_until_apply")
    if change["redacted"]:
        factors.append("redacted_unreadable")
    if resource["previous_address"] is not None or resource["importing"]:
        factors.append("moved_or_importing")
    return factors


def derive_origin_risk(state: Mapping[str, Any]) -> dict[str, Any]:
    """LangGraph node: deterministic origin categories, risk factors and root-cause / risk routing."""
    changes: list[dict[str, Any]] = []
    resources: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = []
    for resource in state["parsed_drift"]["resources"]:
        union: list[str] = []
        for change in resource["attribute_changes"]:
            if change["assessment"]["category"] == NOISE:
                continue  # provider-computed: no origin to analyze
            origin = origin_category(resource, change)
            factors = change_risk_factors(resource, change)
            union += [f for f in factors if f not in union]
            key = {"address": resource["address"], "path": list(change["path"])}
            changes.append({**key, "origin": origin, "lifecycle": change["class"] is None,
                            "attribute_class": change["class"], "assessment": change["assessment"]["category"],
                            "risk_factors": factors})
            severity = change["severity"]["level"]
            routes.append({**key, "severity": severity, "section": "root_cause", "reason": f"origin: {origin}"})
            if factors:
                routes.append({**key, "severity": severity, "section": "risk",
                               "reason": "risk factors: " + ", ".join(factors)})
        resources.append({"address": resource["address"], "classification": resource["classification"],
                          "action": resource["action"], "moved": resource["previous_address"] is not None,
                          "importing": resource["importing"], "action_reason": resource["action_reason"],
                          "ambiguous": resource["ambiguous"],
                          "risk_factors": [f for f in RISK_FACTORS if f in union]})
    facts = {"changes": changes, "resources": resources, "routes": routes}
    log_event(logger, logging.INFO, "origin_risk_derived", "origin categories and risk factors derived",
              changes=len(changes), root_cause_routes=sum(r["section"] == "root_cause" for r in routes),
              risk_routes=sum(r["section"] == "risk" for r in routes))
    return {"origin_facts": facts}


# --------------------------------------------------------------------------- section schemas

Explanation = Annotated[str, Field(min_length=1, max_length=600)]  # shorter: five sections share one reply
Hypothesis = Literal["out_of_band_change", "configuration_change", "provider_or_platform_behavior",
                     "azure_policy_or_automation", "lifecycle_change", "undetermined"]
Channel = Literal["portal", "cli_or_sdk", "other_iac_or_pipeline", "azure_policy", "platform_managed", "unknown"]
RiskKind = Literal["apply_reverts_external_change", "apply_destroys_or_recreates", "ambiguous_intent",
                   "unmanaged_setting", "value_unknown_until_apply", "evidence_incomplete", "other"]


class RootCauseFinding(Strict):
    address: Annotated[str, Field(min_length=1, max_length=512)]
    cited_paths: Annotated[list[CitedPath], Field(min_length=1, max_length=20)]
    hypothesis: Hypothesis
    possible_channels: Annotated[list[Channel], Field(min_length=1, max_length=6)]
    explanation: Explanation
    basis: Literal["inference"]


class RootCauseSection(Strict):
    findings: Annotated[list[RootCauseFinding], Field(max_length=20)]
    summary: Annotated[str, Field(max_length=1000)]


class RiskFinding(Strict):
    address: Annotated[str, Field(min_length=1, max_length=512)]
    cited_paths: Annotated[list[CitedPath], Field(min_length=1, max_length=20)]
    risk_kind: RiskKind
    explanation: Explanation
    basis: Literal["inference"]


class RiskSection(Strict):
    findings: Annotated[list[RiskFinding], Field(max_length=20)]
    summary: Annotated[str, Field(max_length=1000)]


# Which deterministic origins each hypothesis is consistent with.
HYPOTHESIS_ORIGINS = {
    "out_of_band_change": {"outside_terraform", "outside_terraform_converged", "both_sides"},
    "configuration_change": {"configuration_side", "both_sides"},
    "provider_or_platform_behavior": {"outside_terraform", "outside_terraform_converged", "configuration_side",
                                      "both_sides", "value_unknown_until_apply"},
    "azure_policy_or_automation": {"outside_terraform", "outside_terraform_converged", "both_sides"},
}


def hypothesis_consistent(hypothesis: str, origin: Mapping[str, Any]) -> bool:
    if hypothesis == "undetermined":
        return True
    if hypothesis == "lifecycle_change":
        return bool(origin["lifecycle"])
    return origin["category"] in HYPOTHESIS_ORIGINS[hypothesis]


def _risk_supported(kind: str, change: Mapping[str, Any], evidence: Mapping[str, Any]) -> bool:
    factors = change["origin"]["risk_factors"]
    if kind == "evidence_incomplete":
        return "redacted_unreadable" in factors or evidence["truncation"]["truncated"]
    return kind in factors


def _check(finding: Any, known: Mapping, index: int, rejected: list, refs: EvidenceRefs) -> list | None:
    keys = [(finding.address, tuple(path)) for path in finding.cited_paths]
    if not all(key in known for key in keys):
        rejected.append({"index": index, "reason": "unsupported_citation"})
        return None
    violation = free_text_violation(finding.explanation, refs)
    if violation:
        rejected.append({"index": index, "reason": violation})
        return None
    return keys


def _facts(lookup: Mapping, keys: list) -> list[dict[str, Any]]:
    return [{"path": list(key[1]), "origin": lookup[key][1]["origin"]["category"],
             "lifecycle": lookup[key][1]["origin"]["lifecycle"],
             "risk_factors": list(lookup[key][1]["origin"]["risk_factors"])} for key in keys]


def validate_root_cause_section(output: RootCauseSection, evidence: Mapping[str, Any]) -> tuple[list[dict], list[dict]]:
    known = cited_keys(evidence, "root_cause")
    lookup = evidence_lookup(evidence)
    refs = evidence_refs(evidence)
    accepted, rejected = [], []
    for index, finding in enumerate(output.findings):
        keys = _check(finding, known, index, rejected, refs)
        if keys is None:
            continue
        if not all(hypothesis_consistent(finding.hypothesis, lookup[key][1]["origin"]) for key in keys):
            rejected.append({"index": index, "reason": "hypothesis_contradicts_evidence"})
            continue
        accepted.append({
            "address": finding.address,
            "cited_paths": [list(path) for path in finding.cited_paths],
            "hypothesis": finding.hypothesis,  # inference, unconfirmed
            "possible_channels": list(dict.fromkeys(finding.possible_channels)),
            "origin_facts": _facts(lookup, keys),  # deterministic, authoritative
            "deterministic_severity": max((known[key] for key in keys), key=severity_rank),
            "explanation": finding.explanation,
            "basis": "inference",
        })
    return accepted, rejected


def validate_risk_section(output: RiskSection, evidence: Mapping[str, Any]) -> tuple[list[dict], list[dict]]:
    known = cited_keys(evidence, "risk")
    lookup = evidence_lookup(evidence)
    refs = evidence_refs(evidence)
    accepted, rejected = [], []
    for index, finding in enumerate(output.findings):
        keys = _check(finding, known, index, rejected, refs)
        if keys is None:
            continue
        if finding.risk_kind != "other" and not any(
                _risk_supported(finding.risk_kind, lookup[key][1], evidence) for key in keys):
            rejected.append({"index": index, "reason": "risk_not_supported_by_evidence"})
            continue
        accepted.append({
            "address": finding.address,
            "cited_paths": [list(path) for path in finding.cited_paths],
            "risk_kind": finding.risk_kind,  # inference: what the explanation is about
            "risk_kind_unverified": finding.risk_kind == "other",
            "risk_factors": sorted({f for key in keys for f in lookup[key][1]["origin"]["risk_factors"]},
                                   key=RISK_FACTORS.index),  # deterministic
            "deterministic_severity": max((known[key] for key in keys), key=severity_rank),  # the only rating
            "explanation": finding.explanation,
            "basis": "inference",
        })
    return accepted, rejected
