"""Terraform plan JSON parser (Task 4.2).

Reads `terraform show -json` output (docs/drift-detection-spec.md §5), applies the
integrity gate (§5.3) and extracts, per managed resource, the three views the
classifier compares (§6):

  S  recorded state   resource_drift[].change.before (else resource_changes[].change.before)
  R  refreshed/real   resource_drift[].change.after  (equals S without a drift entry)
  D  desired          resource_changes[].change.after

Migrated from scripts/detect_drift.py, which now imports it; behavior for valid
evidence is unchanged. Every problem with the input is reported as EvidenceError
(stage + reason), never as another exception, so a caller can always record the
run as failed instead of crashing. Missing optional fields read as None; missing
arrays default to empty only after the gate has passed (§5.2).

Standard library only. No Terraform, Azure, network or LLM access.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

PLAN_STAGE = "integrity"

# Largest plan.json accepted, in bytes. Larger files are rejected before reading.
MAX_PLAN_BYTES = 50 * 1024 * 1024

# Deepest nesting accepted inside a resource entry. Terraform values are far
# shallower; the limit keeps the recursive attribute comparison well inside
# Python's recursion limit.
MAX_VALUE_DEPTH = 100

PLAN_HEADER_FIELDS = ("format_version", "terraform_version", "timestamp", "applyable", "errored", "complete")


class EvidenceError(Exception):
    """The evidence bundle cannot be trusted; drift status is unknown."""

    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(reason)
        self.stage = stage
        self.reason = reason


@dataclass(frozen=True)
class ResourceEvidence:
    """One managed resource: its identity, planned actions and S/R/D views.

    A view is None when the object does not exist in it (create/delete). Values are
    the parsed JSON, unmodified; `after_unknown` and the sensitivity masks are
    passed through as Terraform wrote them.
    """

    address: str
    module_address: Any
    mode: Any
    type: Any
    name: Any
    index: Any
    provider_name: Any
    actions: list[str] | None  # resource_changes entry; None without one
    drift_actions: list[str] | None  # resource_drift entry; None without one
    action_reason: Any
    previous_address: Any
    importing: bool
    state: Any
    real: Any
    desired: Any
    after_unknown: Any
    sensitive_masks: tuple  # before/after_sensitive of the drift entry, then the change entry


@dataclass(frozen=True)
class ParsedPlan:
    header: dict  # PLAN_HEADER_FIELDS, as recorded in the plan
    resources: tuple[ResourceEvidence, ...]  # managed resources, sorted by address
    output_changes: dict[str, list[str]]  # output name -> actions, sorted by name


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_json(path: str, stage: str, max_bytes: int = MAX_PLAN_BYTES) -> Any:
    """Load one JSON document, or raise EvidenceError."""
    name = os.path.basename(path)
    try:
        size = os.path.getsize(path)
        if size > max_bytes:
            raise EvidenceError(stage, f"{name} is {size} bytes (limit {max_bytes})")
        with open(path, "rb") as fh:
            data = fh.read(max_bytes + 1)  # the file may grow after the size check
        if len(data) > max_bytes:
            raise EvidenceError(stage, f"{name} exceeds the {max_bytes} byte limit")
        return json.loads(data.decode("utf-8"))  # rejects trailing data / multiple documents
    except FileNotFoundError:
        raise EvidenceError(stage, f"{name} not found") from None
    except RecursionError:
        raise EvidenceError(stage, f"{name} is nested too deeply to parse") from None
    except (OSError, ValueError) as exc:
        raise EvidenceError(stage, f"{name} is not valid JSON: {exc}") from None


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def normalize_action(actions: list[str] | None) -> str | None:
    """Map Terraform's action list to a single verb."""
    if actions is None:
        return None
    if actions == ["no-op"]:
        return "no-op"
    if actions == ["read"]:
        return "read"
    if actions == ["create"]:
        return "create"
    if actions == ["update"]:
        return "update"
    if actions == ["delete"]:
        return "delete"
    if sorted(actions) == ["create", "delete"]:
        return "replace"
    return "unrecognized"


def is_pending(entry: dict) -> bool:
    """Pending change as defined by spec §5.3."""
    change = entry["change"]
    return (
        change["actions"] not in (["no-op"], ["read"])
        or entry.get("previous_address") is not None
        or change.get("importing") is not None
    )


# ---------------------------------------------------------------------------
# Integrity gate (spec §5.3) - re-applied here, never trusted from upstream
# ---------------------------------------------------------------------------

def _is_actions(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(a, str) for a in value)


def _entries_ok(entries: Any) -> bool:
    return all(
        isinstance(e, dict)
        and isinstance(e.get("address"), str)
        and isinstance(e.get("change"), dict)
        and isinstance(e["change"].get("actions"), list)
        for e in entries
    )


def _depth_exceeds(value: Any, limit: int) -> bool:
    """True when containers nest deeper than `limit` (iterative, so it cannot recurse)."""
    stack = [(value, 0)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, dict):
            children = node.values()
        elif isinstance(node, list):
            children = node
        else:
            continue
        if depth >= limit:
            return True
        stack.extend((child, depth + 1) for child in children)
    return False


def integrity_violations(
    plan: Any, plan_rc: int | None = None, expected_tf_version: str | None = None
) -> list[str]:
    """Spec §5.3 violations; empty when the plan is usable.

    `plan_rc` and `expected_tf_version` come from the run manifest. When either is
    None (a plan read without its manifest), that check is skipped.
    """
    if not isinstance(plan, dict):
        return ["plan.json is not a JSON object"]

    violations: list[str] = []
    fmt = plan.get("format_version")
    if not isinstance(fmt, str):
        violations.append("format_version missing or not a string")
    elif fmt.split(".")[0] != "1":
        violations.append(f"unsupported format_version {fmt} (major must be 1)")
    if expected_tf_version is not None and plan.get("terraform_version") != expected_tf_version:
        violations.append(
            f"terraform_version {plan.get('terraform_version')!r} != manifest {expected_tf_version!r}"
        )
    if plan.get("errored") is not False:
        violations.append(f"errored is {json.dumps(plan.get('errored'))} (must be false)")
    if plan.get("complete") is not True:
        violations.append(f"complete is {json.dumps(plan.get('complete'))} (must be true)")
    for key in ("resource_changes", "resource_drift"):
        if key in plan:
            entries = plan[key]
            if not isinstance(entries, list):
                violations.append(f"{key} is not an array")
            elif not _entries_ok(entries):
                violations.append(f"{key} contains an entry without address/change.actions")
            else:
                if not all(_is_actions(e["change"]["actions"]) for e in entries):
                    violations.append(f"{key} contains actions that are not all strings")
                addresses = [e["address"] for e in entries]
                if len(set(addresses)) != len(addresses):
                    violations.append(f"{key} contains a duplicate address")
                if any(_depth_exceeds(e, MAX_VALUE_DEPTH) for e in entries):
                    violations.append(f"{key} contains values nested deeper than {MAX_VALUE_DEPTH} levels")
    if "output_changes" in plan:
        oc = plan["output_changes"]
        if not isinstance(oc, dict):
            violations.append("output_changes is not an object")
        elif not all(isinstance(v, dict) and isinstance(v.get("actions"), list) for v in oc.values()):
            violations.append("output_changes contains an entry without actions")
        elif not all(_is_actions(v["actions"]) for v in oc.values()):
            violations.append("output_changes contains actions that are not all strings")
    if violations:
        return violations

    if plan_rc is None:
        return []
    pending = sum(1 for e in plan.get("resource_changes", []) if is_pending(e))
    pending += sum(1 for v in plan.get("output_changes", {}).values() if v["actions"] != ["no-op"])
    if plan_rc == 0 and pending > 0:
        return [f"plan exit 0 but plan.json contains {pending} pending change(s)"]
    if plan_rc == 2 and pending == 0:
        return ["plan exit 2 but plan.json contains no pending change"]
    return []


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def resource_evidence(drift: dict | None, change: dict | None) -> ResourceEvidence:
    """Combine one address's resource_drift and resource_changes entries."""
    if drift is None and change is None:
        raise ValueError("resource_evidence needs a drift or change entry")
    entry = change if change is not None else drift
    c = change["change"] if change is not None else None
    d = drift["change"] if drift is not None else None

    return ResourceEvidence(
        address=entry["address"],
        module_address=entry.get("module_address"),
        mode=entry.get("mode"),
        type=entry.get("type"),
        name=entry.get("name"),
        index=entry.get("index"),
        provider_name=entry.get("provider_name"),
        actions=c["actions"] if c is not None else None,
        drift_actions=d["actions"] if d is not None else None,
        action_reason=change.get("action_reason") if change is not None else None,
        previous_address=change.get("previous_address") if change is not None else None,
        importing=c is not None and c.get("importing") is not None,
        state=d.get("before") if d is not None else c.get("before"),
        real=d.get("after") if d is not None else c.get("before"),
        desired=c.get("after") if c is not None else None,
        after_unknown=c.get("after_unknown") if c is not None else None,
        sensitive_masks=tuple(
            part.get(key)
            for part in (d, c) if part is not None
            for key in ("before_sensitive", "after_sensitive")
        ),
    )


def parse_plan(
    plan: Any, plan_rc: int | None = None, expected_tf_version: str | None = None
) -> ParsedPlan:
    """Gate and extract an already-loaded plan, or raise EvidenceError."""
    violations = integrity_violations(plan, plan_rc, expected_tf_version)
    if violations:
        raise EvidenceError(PLAN_STAGE, "; ".join(violations))
    return extract_plan(plan)


def extract_plan(plan: dict) -> ParsedPlan:
    """Extract a plan that has already passed the integrity gate (use parse_plan otherwise)."""
    # Data sources (mode "data") are not drift evidence.
    drift = {e["address"]: e for e in plan.get("resource_drift", []) if e.get("mode") == "managed"}
    changes = {e["address"]: e for e in plan.get("resource_changes", []) if e.get("mode") == "managed"}
    return ParsedPlan(
        header={k: plan.get(k) for k in PLAN_HEADER_FIELDS},
        resources=tuple(
            resource_evidence(drift.get(address), changes.get(address))
            for address in sorted(set(drift) | set(changes))
        ),
        output_changes={name: v["actions"] for name, v in sorted(plan.get("output_changes", {}).items())},
    )


def parse_plan_file(
    path: str,
    plan_rc: int | None = None,
    expected_tf_version: str | None = None,
    max_bytes: int = MAX_PLAN_BYTES,
) -> ParsedPlan:
    """Load, gate and extract a plan.json file, or raise EvidenceError."""
    return parse_plan(load_json(path, PLAN_STAGE, max_bytes), plan_rc, expected_tf_version)
