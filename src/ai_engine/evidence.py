"""The only path from deterministic evidence to an LLM prompt (Task 6.3).

`build_llm_evidence` turns `parsed_drift` plus the deterministic routing of
`classify_drift` into the JSON object a prompt may contain. It is an explicit
allowlist: every field is copied by name into a new object, so nothing the
report gains later reaches a model by accident. Never included as fields: `run`
(run ids, working dir, backend key, git commit, timestamps), `plan` metadata,
`provider_name`, `module_address`, `previous_address`, `importing`, in-sync
resources, output changes, or the raw plan (which the AI engine never reads).
`notes` are drift_engine's own deterministic texts and are included as they
are; they can mention an address, e.g. "moved from <previous address>".

Fail closed: a change whose views mix a redacted status with a plain value, or
that is flagged `redacted` but still carries a value, raises
`EvidenceIntegrityError` and nothing is sent. drift_engine redacts (spec §8.3);
this module only verifies that, it never redacts by rules of its own.

Limits are deterministic (`EvidenceLimits`): changes are ordered by
deterministic severity, then address and path; values longer than the value cap
are cut, and changes are dropped from the end until the change, resource and
character caps hold. Everything cut or dropped is recorded in `truncation`.

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

RESOURCE_FIELDS = ("address", "type", "classification", "action", "drift_action", "ambiguous", "notes")
CHANGE_FIELDS = ("path", "attribute", "class", "redacted")
VIEWS = ("state", "real", "desired")
EVIDENCE_TAG = "terraform_evidence"


class EvidenceIntegrityError(RuntimeError):
    """Evidence violates the redaction contract; it must not be sent to an LLM."""


@dataclass(frozen=True)
class EvidenceLimits:
    max_resources: int = 20
    max_changes: int = 60
    max_value_chars: int = 2000
    max_evidence_chars: int = 40000


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
) -> dict[str, Any]:
    """Allowlisted, size-bounded evidence for the routed (address, path) changes.

    `routes` are `security_targets["changes"]` entries: {address, path, reason}.
    The integrity check covers every resource of `parsed_drift`, not only the
    routed changes, so a defect anywhere stops the call.
    """
    resources = {r["address"]: r for r in parsed_drift["resources"]}
    check_evidence_integrity(resources.values())

    picked = []
    for route in routes:
        resource = resources[route["address"]]
        change = next(c for c in resource["attribute_changes"] if list(c["path"]) == list(route["path"]))
        picked.append((resource, change, route["reason"]))
    picked.sort(key=lambda item: (-severity_rank(item[1]["severity"]["level"]),
                                  -severity_rank(item[0]["severity"]["level"]), item[0]["address"],
                                  list(item[1]["path"])))

    truncation: dict[str, Any] = {"changes_total": len(picked), "changes_omitted": [], "values_truncated": []}
    kept: list[tuple[Mapping[str, Any], dict[str, Any]]] = []
    addresses: list[str] = []
    for resource, change, reason in picked:
        key = {"address": resource["address"], "path": list(change["path"])}
        new_resource = resource["address"] not in addresses
        if len(kept) >= limits.max_changes or (new_resource and len(addresses) >= limits.max_resources):
            truncation["changes_omitted"].append(key)
            continue
        entry: dict[str, Any] = {field: change[field] for field in CHANGE_FIELDS}
        entry["path"] = list(change["path"])
        entry["severity"] = {"level": change["severity"]["level"], "rules": list(change["severity"]["rules"])}
        entry["assessment"] = change["assessment"]["category"]
        entry["routing_reason"] = reason
        for view in VIEWS:
            entry[view], cut = _view(change[view], limits)
            if cut:
                truncation["values_truncated"].append({**key, "view": view})
        kept.append((resource, entry))
        if new_resource:
            addresses.append(resource["address"])

    evidence = _assemble(kept, addresses, resources, truncation)
    while kept and len(render_evidence(evidence)) > limits.max_evidence_chars:
        resource, entry = kept.pop()
        truncation["changes_omitted"].append({"address": resource["address"], "path": entry["path"]})
        truncation["values_truncated"] = [t for t in truncation["values_truncated"]
                                          if (t["address"], t["path"]) != (resource["address"], entry["path"])]
        evidence = _assemble(kept, [a for a in addresses if any(r["address"] == a for r, _ in kept)],
                             resources, truncation)
    return evidence


def _assemble(kept, addresses, resources, truncation) -> dict[str, Any]:
    out_resources = []
    for address in addresses:
        resource = resources[address]
        item: dict[str, Any] = {field: resource[field] for field in RESOURCE_FIELDS}
        item["notes"] = list(resource["notes"])
        item["severity"] = {"level": resource["severity"]["level"], "reasons": list(resource["severity"]["reasons"])}
        item["changes"] = [entry for r, entry in kept if r["address"] == address]
        out_resources.append(item)
    record = {
        "changes_total": truncation["changes_total"],
        "changes_included": len(kept),
        "changes_omitted": list(truncation["changes_omitted"]),
        "values_truncated": list(truncation["values_truncated"]),
    }
    record["truncated"] = bool(record["changes_omitted"] or record["values_truncated"])
    return {"resources": out_resources, "truncation": record}


def cited_keys(evidence: Mapping[str, Any]) -> dict[tuple[str, tuple[str, ...]], str]:
    """(address, path) of every change in the evidence -> its deterministic severity level."""
    return {(r["address"], tuple(c["path"])): c["severity"]["level"]
            for r in evidence["resources"] for c in r["changes"]}


def render_evidence(evidence: Mapping[str, Any]) -> str:
    """Deterministic JSON for the prompt; `<`/`>` escaped so values cannot spoof the delimiters."""
    payload = {"resources": evidence["resources"], "truncated": evidence["truncation"]["truncated"]}
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return text.replace("<", "\\u003c").replace(">", "\\u003e")
