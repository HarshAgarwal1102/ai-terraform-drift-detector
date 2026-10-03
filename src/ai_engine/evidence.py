"""The only path from deterministic evidence to an LLM prompt (Tasks 6.3-6.5).

`build_llm_evidence` turns `parsed_drift` plus the deterministic routing of
`classify_drift` (security) and `route_cost_config` (cost, configuration) into
the JSON object the single analysis prompt may contain. It is an explicit
allowlist: every field is copied by name into a new object, so nothing the
report gains later reaches a model by accident. Never included as fields: `run`
(run ids, working dir, backend key, git commit, timestamps), `plan` metadata,
`provider_name`, `module_address`, `previous_address`, `importing`, in-sync
resources, output changes, or the raw plan (which the AI engine never reads).
`notes` are drift_engine's own deterministic texts and are included as they
are; they can mention an address, e.g. "moved from <previous address>".

Sections (Tasks 6.4-6.5): each route names the analysis section it is for
(`security`, `cost`, `configuration`, `root_cause`, `risk`; default `security`). A change routed to
several sections is sent **once**, tagged with every section and its routing
reason (`sections`). A section is `applicable` only if at least one of its
changes was included; citations are later checked per section (`cited_keys`).

Origin facts (Task 6.5): with `origin_facts` (from the deterministic
`derive_origin_risk` node), each change also carries `origin` {category,
lifecycle, risk_factors} and each resource `risk_factors`, `moved`,
`importing` and `action_reason`. `moved` is a boolean: the previous address
itself is never sent.

Fail closed: a change whose views mix a redacted status with a plain value, or
that is flagged `redacted` but still carries a value, raises
`EvidenceIntegrityError` and nothing is sent. drift_engine redacts (spec §8.3);
this module only verifies that, it never redacts by rules of its own.

Limits are deterministic (`EvidenceLimits`): changes are ordered by section
(security, cost, configuration), then deterministic severity, address and path.
Per-section caps keep one section (e.g. many LOW tag changes) from crowding out
another; values longer than the value cap are cut; changes are dropped from the
end until the change, resource and character caps hold. Everything cut or
dropped is recorded in `truncation`, overall and per section.

`render_evidence` serializes the evidence for the prompt with `<` and `>`
escaped, so a Terraform or Azure value cannot close the evidence delimiters.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

SEVERITY_ORDER = ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL")  # ascending, as in the report contract
_RANK = {level: i for i, level in enumerate(SEVERITY_ORDER)}

SECTIONS = ("security", "cost", "configuration", "root_cause", "risk")  # also the priority order under limits
DEFAULT_SECTION = "security"

RESOURCE_FIELDS = ("address", "type", "classification", "action", "drift_action", "ambiguous", "notes")
CHANGE_FIELDS = ("path", "attribute", "class", "redacted")
VIEWS = ("state", "real", "desired")
EVIDENCE_TAG = "terraform_evidence"


class EvidenceIntegrityError(RuntimeError):
    """Evidence violates the redaction contract; it must not be sent to an LLM."""


@dataclass(frozen=True)
class EvidenceLimits:
    max_resources: int = 20
    max_changes: int = 60  # unique changes across all sections
    max_value_chars: int = 2000
    max_evidence_chars: int = 40000
    max_security_changes: int = 30
    max_cost_changes: int = 20
    max_configuration_changes: int = 30
    max_root_cause_changes: int = 30
    max_risk_changes: int = 30

    def section_cap(self, section: str) -> int:
        return getattr(self, f"max_{section}_changes")


def severity_rank(level: str) -> int:
    return _RANK[level]


def _check_redaction(address: str, change: Mapping[str, Any]) -> None:
    statuses = {change[view]["status"] for view in VIEWS}
    has_value = "value" in statuses
    if has_value and (change["redacted"] or "redacted" in statuses):
        # Name the location only: the offending value must not travel even in an error.
        raise EvidenceIntegrityError(f"redacted change {address} {'.'.join(change['path'])} carries a value; "
                                     "refusing to build LLM evidence")


def _view(view: Mapping[str, Any], limits: EvidenceLimits) -> tuple[dict[str, Any], bool]:
    if view["status"] != "value":
        return {"status": view["status"]}, False
    text = json.dumps(view["value"], sort_keys=True, ensure_ascii=False)
    if len(text) <= limits.max_value_chars:
        return {"status": "value", "value": view["value"]}, False
    return {"status": "value_truncated", "value_prefix": text[:limits.max_value_chars],
            "original_chars": len(text)}, True


def check_evidence_integrity(resources: Iterable[Mapping[str, Any]]) -> None:
    for resource in resources:
        for change in resource["attribute_changes"]:
            _check_redaction(resource["address"], change)


def build_llm_evidence(
    parsed_drift: Mapping[str, Any],
    routes: Iterable[Mapping[str, Any]],
    limits: EvidenceLimits = EvidenceLimits(),
    origin_facts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Allowlisted, deduplicated, size-bounded evidence for the routed changes.

    `routes` are routing entries {address, path, reason, section?} from
    `security_targets` / `cost_targets` / `config_targets`. The integrity check
    covers every resource of `parsed_drift`, not only the routed changes, so a
    defect anywhere stops the call.
    """
    resources = {r["address"]: r for r in parsed_drift["resources"]}
    check_evidence_integrity(resources.values())
    origins = {(c["address"], tuple(c["path"])): c for c in (origin_facts or {}).get("changes", [])}
    resource_facts = {r["address"]: r for r in (origin_facts or {}).get("resources", [])}

    merged: dict[tuple[str, tuple[str, ...]], dict[str, str]] = {}
    routed_per_section = {section: 0 for section in SECTIONS}
    for route in routes:
        section = route.get("section", DEFAULT_SECTION)
        sections = merged.setdefault((route["address"], tuple(route["path"])), {})
        if section not in sections:
            sections[section] = route["reason"]
            routed_per_section[section] += 1

    picked = []
    for (address, path), sections in merged.items():
        resource = resources[address]
        change = next(c for c in resource["attribute_changes"] if tuple(c["path"]) == path)
        picked.append((resource, change, sections))
    picked.sort(key=lambda item: (min(SECTIONS.index(s) for s in item[2]),
                                  -severity_rank(item[1]["severity"]["level"]),
                                  -severity_rank(item[0]["severity"]["level"]), item[0]["address"],
                                  list(item[1]["path"])))

    omitted: list[dict[str, Any]] = []
    values_cut: list[dict[str, Any]] = []
    kept: list[tuple[Mapping[str, Any], dict[str, Any]]] = []
    addresses: list[str] = []
    per_section = {section: 0 for section in SECTIONS}
    for resource, change, sections in picked:
        key = {"address": resource["address"], "path": list(change["path"])}
        fits = {s: r for s, r in sections.items() if per_section[s] < limits.section_cap(s)}
        new_resource = resource["address"] not in addresses
        if not fits or len(kept) >= limits.max_changes or (new_resource and len(addresses) >= limits.max_resources):
            omitted.append({**key, "sections": sorted(sections, key=SECTIONS.index)})
            continue
        if len(fits) < len(sections):  # included for some sections, capped for the others
            omitted.append({**key, "sections": sorted(set(sections) - set(fits), key=SECTIONS.index)})
        entry: dict[str, Any] = {field: change[field] for field in CHANGE_FIELDS}
        entry["path"] = list(change["path"])
        entry["severity"] = {"level": change["severity"]["level"], "rules": list(change["severity"]["rules"])}
        entry["assessment"] = change["assessment"]["category"]
        entry["sections"] = {s: fits[s] for s in sorted(fits, key=SECTIONS.index)}
        origin = origins.get((resource["address"], tuple(change["path"])))
        if origin is not None:
            entry["origin"] = {"category": origin["origin"], "lifecycle": origin["lifecycle"],
                               "risk_factors": list(origin["risk_factors"])}
        for view in VIEWS:
            entry[view], cut = _view(change[view], limits)
            if cut:
                values_cut.append({**key, "view": view})
        for section in fits:
            per_section[section] += 1
        kept.append((resource, entry))
        if new_resource:
            addresses.append(resource["address"])

    evidence = _assemble(kept, resources, omitted, values_cut, merged, routed_per_section, resource_facts)
    while kept and len(render_evidence(evidence)) > limits.max_evidence_chars:
        resource, entry = kept.pop()
        omitted.append({"address": resource["address"], "path": entry["path"], "sections": list(entry["sections"])})
        values_cut = [v for v in values_cut if (v["address"], v["path"]) != (resource["address"], entry["path"])]
        evidence = _assemble(kept, resources, omitted, values_cut, merged, routed_per_section, resource_facts)
    return evidence


def _assemble(kept, resources, omitted, values_cut, merged, routed_per_section, resource_facts) -> dict[str, Any]:
    addresses: list[str] = []
    for resource, _ in kept:
        if resource["address"] not in addresses:
            addresses.append(resource["address"])
    out_resources = []
    for address in addresses:
        resource = resources[address]
        item: dict[str, Any] = {field: resource[field] for field in RESOURCE_FIELDS}
        item["notes"] = list(resource["notes"])
        item["severity"] = {"level": resource["severity"]["level"], "reasons": list(resource["severity"]["reasons"])}
        facts = resource_facts.get(address)
        if facts is not None:
            item.update({"risk_factors": list(facts["risk_factors"]), "moved": facts["moved"],
                         "importing": facts["importing"], "action_reason": facts["action_reason"]})
        item["changes"] = [entry for r, entry in kept if r["address"] == address]
        out_resources.append(item)
    included = {section: sum(1 for _, e in kept if section in e["sections"]) for section in SECTIONS}
    record = {
        "changes_total": len(merged),
        "changes_included": len(kept),
        "changes_omitted": [dict(o) for o in omitted],
        "values_truncated": [dict(v) for v in values_cut],
        "per_section": {section: {"routed": routed_per_section[section], "included": included[section]}
                        for section in SECTIONS},
    }
    record["truncated"] = bool(record["changes_omitted"] or record["values_truncated"])
    sections = {section: {"applicable": included[section] > 0} for section in SECTIONS}
    return {"resources": out_resources, "sections": sections, "truncation": record}


def cited_keys(evidence: Mapping[str, Any], section: str | None = None) -> dict[tuple[str, tuple[str, ...]], str]:
    """(address, path) -> deterministic severity level, for every change in the evidence.

    With `section`, only changes sent for that section: a finding of one section
    cannot cite evidence that was given to the model for another.
    """
    return {(r["address"], tuple(c["path"])): c["severity"]["level"]
            for r in evidence["resources"] for c in r["changes"]
            if section is None or section in c["sections"]}


def evidence_lookup(evidence: Mapping[str, Any]) -> dict[tuple[str, tuple[str, ...]], tuple[dict, dict]]:
    """(address, path) -> (resource entry, change entry) of the evidence sent."""
    return {(r["address"], tuple(c["path"])): (r, c) for r in evidence["resources"] for c in r["changes"]}


def render_evidence(evidence: Mapping[str, Any]) -> str:
    """Deterministic JSON for the prompt; `<`/`>` escaped so values cannot spoof the delimiters."""
    payload = {"resources": evidence["resources"], "sections": evidence["sections"],
               "truncated": evidence["truncation"]["truncated"]}
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return text.replace("<", "\\u003c").replace(">", "\\u003e")
