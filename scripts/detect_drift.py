#!/usr/bin/env python3
"""Deterministic drift classification (Task 3.3).

Classifies the evidence bundle produced by scripts/generate_plan_json.sh
according to docs/drift-detection-spec.md (§5.3 integrity gate, §6
classification, §8.2 engine rules). Standard library only; never calls
Terraform, Azure or an LLM. The same bundle always yields byte-identical
output.

Three views of each managed resource are compared (spec §6):
  S  recorded state   resource_drift[].change.before (else resource_changes[].change.before)
  R  refreshed/real   resource_drift[].change.after  (equals S without a drift entry)
  D  desired          resource_changes[].change.after

Usage:
  scripts/detect_drift.py ARTIFACT_DIR [--output PATH]

Writes ARTIFACT_DIR/drift_classification.json (or PATH).

Exit status (process outcome only - drift is a valid result, not an error):
  0   evidence valid and classified (has_drift true or false)
  1   evidence failed or rejected; has_drift is null (unknown)
  64  usage error (ARTIFACT_DIR missing)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

CLASSIFICATION_VERSION = "1"
OUTPUT_FILE = "drift_classification.json"
MANIFEST_FILE = "detection_run.json"
PLAN_FILE = "plan.json"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 64

# Resource classes (spec §6.1)
IN_SYNC = "in_sync"
EXTERNAL_DRIFT = "external_drift"
EXTERNAL_DELETION = "external_deletion"
CONVERGED_DRIFT = "converged_drift"
CONFIG_CHANGE = "config_change"
RESOURCE_ADDED = "resource_added"
RESOURCE_REMOVED = "resource_removed"
DRIFT_AND_CONFIG_CHANGE = "drift_and_config_change"
UNDETERMINED = "undetermined"

# Attribute classes (spec §6.2)
DRIFTED = "drifted"
DRIFTED_CONVERGED = "drifted_converged"
CONFIG_CHANGED = "config_changed"
DRIFTED_AND_CONFIG_CHANGED = "drifted_and_config_changed"
UNKNOWN_UNTIL_APPLY = "unknown_until_apply"

_MISSING = object()  # attribute absent from a view (distinct from JSON null)


class EvidenceError(Exception):
    """The evidence bundle cannot be trusted; drift status is unknown."""

    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(reason)
        self.stage = stage
        self.reason = reason


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

def _entries_ok(entries: Any) -> bool:
    return all(
        isinstance(e, dict)
        and isinstance(e.get("address"), str)
        and isinstance(e.get("change"), dict)
        and isinstance(e["change"].get("actions"), list)
        for e in entries
    )


def integrity_violations(plan: Any, plan_rc: int, expected_tf_version: str) -> list[str]:
    if not isinstance(plan, dict):
        return ["plan.json is not a JSON object"]

    violations: list[str] = []
    fmt = plan.get("format_version")
    if not isinstance(fmt, str):
        violations.append("format_version missing or not a string")
    elif fmt.split(".")[0] != "1":
        violations.append(f"unsupported format_version {fmt} (major must be 1)")
    if plan.get("terraform_version") != expected_tf_version:
        violations.append(
            f"terraform_version {plan.get('terraform_version')!r} != manifest {expected_tf_version!r}"
        )
    if plan.get("errored") is not False:
        violations.append(f"errored is {json.dumps(plan.get('errored'))} (must be false)")
    if plan.get("complete") is not True:
        violations.append(f"complete is {json.dumps(plan.get('complete'))} (must be true)")
    for key in ("resource_changes", "resource_drift"):
        if key in plan:
            if not isinstance(plan[key], list):
                violations.append(f"{key} is not an array")
            elif not _entries_ok(plan[key]):
                violations.append(f"{key} contains an entry without address/change.actions")
    if "output_changes" in plan:
        oc = plan["output_changes"]
        if not isinstance(oc, dict):
            violations.append("output_changes is not an object")
        elif not all(isinstance(v, dict) and isinstance(v.get("actions"), list) for v in oc.values()):
            violations.append("output_changes contains an entry without actions")
    if violations:
        return violations

    pending = sum(1 for e in plan.get("resource_changes", []) if is_pending(e))
    pending += sum(1 for v in plan.get("output_changes", {}).values() if v["actions"] != ["no-op"])
    if plan_rc == 0 and pending > 0:
        return [f"plan exit 0 but plan.json contains {pending} pending change(s)"]
    if plan_rc == 2 and pending == 0:
        return ["plan exit 2 but plan.json contains no pending change"]
    return []


# ---------------------------------------------------------------------------
# Attribute-level rule (spec §6.2, top-level attributes only)
# ---------------------------------------------------------------------------

def _contains_true(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, dict):
        return any(_contains_true(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_true(v) for v in value)
    return False


def classify_attributes(
    state: dict | None, real: dict | None, desired: dict | None, after_unknown: Any
) -> list[dict]:
    """Return changed top-level attributes with their §6.2 class.

    Only attribute names and classes are reported; values are Task 3.4 scope
    (and are withheld here so sensitive values cannot leak).
    """
    if not isinstance(state, dict) or not isinstance(real, dict) or not isinstance(desired, dict):
        return []  # object created or destroyed: no attribute-level comparison
    unknown = after_unknown if isinstance(after_unknown, dict) else {}

    result = []
    for name in sorted(set(state) | set(real) | set(desired) | set(unknown)):
        if _contains_true(unknown.get(name)):
            result.append({"name": name, "class": UNKNOWN_UNTIL_APPLY})
            continue
        s = state.get(name, _MISSING)
        r = real.get(name, _MISSING)
        d = desired.get(name, _MISSING)
        if s == r:
            if d == s:
                continue  # unchanged
            cls = CONFIG_CHANGED
        elif d == s:
            cls = DRIFTED
        elif d == r:
            cls = DRIFTED_CONVERGED
        else:
            cls = DRIFTED_AND_CONFIG_CHANGED
        result.append({"name": name, "class": cls})
    return result


# ---------------------------------------------------------------------------
# Resource-level classification (spec §6.1)
# ---------------------------------------------------------------------------

def classify_resource(drift: dict | None, change: dict | None) -> dict:
    if drift is None and change is None:
        raise ValueError("classify_resource needs a drift or change entry")
    entry = change if change is not None else drift
    c = change["change"] if change is not None else None
    d = drift["change"] if drift is not None else None

    action = normalize_action(c["actions"]) if c is not None else None
    drift_action = normalize_action(d["actions"]) if d is not None else None
    notes: list[str] = []

    state = d.get("before") if d is not None else c.get("before")
    real = d.get("after") if d is not None else c.get("before")
    desired = c.get("after") if c is not None else None
    attributes = classify_attributes(
        state, real, desired, c.get("after_unknown") if c is not None else None
    )
    kinds = {a["class"] for a in attributes}

    moved = change is not None and change.get("previous_address") is not None
    importing = c is not None and c.get("importing") is not None

    if d is None:
        # No refresh divergence: anything pending comes from the configuration side.
        if action in ("no-op", "read") and not (moved or importing):
            cls = IN_SYNC
        elif action == "create":
            cls = RESOURCE_ADDED
        elif action == "delete":
            cls = RESOURCE_REMOVED
        elif action in ("update", "replace", "no-op"):
            cls = CONFIG_CHANGE
        else:
            cls = UNDETERMINED
            notes.append(f"unrecognized actions {c['actions']}")
    elif drift_action == "delete":
        # Refresh found the object missing.
        if action == "create":
            cls = EXTERNAL_DELETION
        elif action in (None, "no-op"):
            cls = CONVERGED_DRIFT
            notes.append("object missing remotely and no longer declared in configuration")
        else:
            cls = UNDETERMINED
            notes.append(f"object missing remotely but planned action is {action}")
    elif action in (None, "no-op") and not (moved or importing):
        cls = CONVERGED_DRIFT
    elif action == "delete":
        cls = DRIFT_AND_CONFIG_CHANGE
        notes.append("remote object diverged from state and the configuration no longer declares it")
    else:
        drifted_kinds = {DRIFTED, DRIFTED_CONVERGED}
        if DRIFTED_AND_CONFIG_CHANGED in kinds or (kinds & drifted_kinds and CONFIG_CHANGED in kinds):
            cls = DRIFT_AND_CONFIG_CHANGE
        elif DRIFTED in kinds:
            cls = EXTERNAL_DRIFT
        else:
            cls = UNDETERMINED
            notes.append("drift present with a pending change, but no attribute explains the change")

    if action == "replace":
        notes.append(
            "planned action is replace (delete and create); desired values describe the new object, "
            "so optional attributes not set in configuration can appear as config_changed"
        )
    if moved:
        notes.append(f"moved from {change['previous_address']} (move-only exit behavior unverified, spec §5.3)")
    if importing:
        notes.append("import pending (import-only exit behavior unverified, spec §5.3)")
    if UNKNOWN_UNTIL_APPLY in kinds:
        notes.append("some attribute values are unknown until apply")

    ambiguous = cls == UNDETERMINED or DRIFTED_AND_CONFIG_CHANGED in kinds

    return {
        "address": entry["address"],
        "module_address": entry.get("module_address"),
        "mode": entry.get("mode"),
        "type": entry.get("type"),
        "name": entry.get("name"),
        "index": entry.get("index"),
        "provider_name": entry.get("provider_name"),
        "classification": cls,
        "action": action,
        "actions": c["actions"] if c is not None else None,
        "action_reason": change.get("action_reason") if change is not None else None,
        "drift_action": drift_action,
        "drift_actions": d["actions"] if d is not None else None,
        "previous_address": change.get("previous_address") if change is not None else None,
        "importing": importing,
        "attributes": attributes,
        "ambiguous": ambiguous,
        "notes": notes,
    }


def classify_plan(plan: dict) -> dict:
    """Classify a plan that has already passed the integrity gate."""
    drift = {e["address"]: e for e in plan.get("resource_drift", []) if e.get("mode") == "managed"}
    changes = {e["address"]: e for e in plan.get("resource_changes", []) if e.get("mode") == "managed"}

    resources = [
        classify_resource(drift.get(address), changes.get(address))
        for address in sorted(set(drift) | set(changes))
    ]
    output_changes = [
        {"name": name, "action": normalize_action(v["actions"]), "actions": v["actions"]}
        for name, v in sorted(plan.get("output_changes", {}).items())
    ]

    counts: dict[str, int] = {}
    for r in resources:
        counts[r["classification"]] = counts.get(r["classification"], 0) + 1
    resource_pending = any(r["classification"] != IN_SYNC for r in resources)
    output_pending = any(o["action"] != "no-op" for o in output_changes)

    return {
        "has_drift": bool(drift),
        "summary": {
            "resources_total": len(resources),
            "drifted_resources": len(drift),
            "classification_counts": dict(sorted(counts.items())),
            "ambiguous_resources": sum(1 for r in resources if r["ambiguous"]),
            "has_pending_resource_changes": resource_pending,
            "has_pending_output_changes": output_pending,
            "output_only_change": output_pending and not resource_pending and not drift,
        },
        "resources": resources,
        "output_changes": output_changes,
    }


# ---------------------------------------------------------------------------
# Evidence bundle
# ---------------------------------------------------------------------------

_RUN_FIELDS = (
    "run_id", "environment", "working_dir", "backend_key", "git_commit",
    "started_at", "finished_at", "terraform_version", "plan_exit_code", "show_exit_code",
)


def _load_json(path: str, stage: str) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)  # rejects trailing data / multiple documents
    except FileNotFoundError:
        raise EvidenceError(stage, f"{os.path.basename(path)} not found") from None
    except (OSError, ValueError) as exc:
        raise EvidenceError(stage, f"{os.path.basename(path)} is not valid JSON: {exc}") from None


def classify_bundle(artifact_dir: str) -> dict:
    """Build the classification result for an evidence bundle (pure, deterministic)."""
    result: dict[str, Any] = {
        "classification_version": CLASSIFICATION_VERSION,
        "outcome": "failed",
        "has_drift": None,
        "failure": None,
        "run": None,
        "plan": None,
        "summary": None,
        "resources": [],
        "output_changes": [],
    }
    try:
        manifest = _load_json(os.path.join(artifact_dir, MANIFEST_FILE), "manifest")
        if not isinstance(manifest, dict):
            raise EvidenceError("manifest", "detection_run.json is not a JSON object")
        result["run"] = {k: manifest.get(k) for k in _RUN_FIELDS}
        result["run"]["detection_outcome"] = manifest.get("outcome")

        if manifest.get("outcome") != "succeeded":
            if manifest.get("outcome") == "failed":
                result["failure"] = {
                    "source": "detection_run",
                    "stage": manifest.get("failure_stage"),
                    "reason": manifest.get("failure_reason"),
                }
                return result
            raise EvidenceError("manifest", f"unrecognized outcome {manifest.get('outcome')!r}")

        plan_rc = manifest.get("plan_exit_code")
        if type(plan_rc) is not int or plan_rc not in (0, 2):
            raise EvidenceError("manifest", f"succeeded run with plan_exit_code {plan_rc!r}")
        tf_version = manifest.get("terraform_version")
        if not isinstance(tf_version, str) or not tf_version:
            raise EvidenceError("manifest", "terraform_version missing")

        plan = _load_json(os.path.join(artifact_dir, PLAN_FILE), "integrity")
        violations = integrity_violations(plan, plan_rc, tf_version)
        if violations:
            raise EvidenceError("integrity", "; ".join(violations))

        result["plan"] = {
            k: plan.get(k)
            for k in ("format_version", "terraform_version", "timestamp", "applyable", "errored", "complete")
        }
        result.update(classify_plan(plan))
        result["outcome"] = "succeeded"
        return result
    except EvidenceError as exc:
        result["failure"] = {"source": "classifier", "stage": exc.stage, "reason": exc.reason}
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic drift classification (Task 3.3).")
    parser.add_argument("artifact_dir", help="evidence bundle written by scripts/generate_plan_json.sh")
    parser.add_argument("--output", help=f"output path (default: ARTIFACT_DIR/{OUTPUT_FILE})")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.artifact_dir):
        print(f"ERROR: artifact directory not found: {args.artifact_dir}", file=sys.stderr)
        return EXIT_USAGE

    result = classify_bundle(args.artifact_dir)
    output = args.output or os.path.join(args.artifact_dir, OUTPUT_FILE)
    with open(output, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, sort_keys=True)
        fh.write("\n")

    if result["outcome"] != "succeeded":
        failure = result["failure"]
        print(
            f"CLASSIFICATION FAILED [{failure['source']}/{failure['stage']}]: {failure['reason']}\n"
            "  Drift status is UNKNOWN - this must not be treated as 'no drift'.",
            file=sys.stderr,
        )
        return EXIT_FAILED

    counts = ", ".join(f"{k}={v}" for k, v in result["summary"]["classification_counts"].items())
    print(f"has_drift={str(result['has_drift']).lower()}  [{counts}]")
    print(f"Classification: {output}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
