#!/usr/bin/env python3
"""Deterministic drift classification (Task 3.3) with attribute detail (Task 3.4).

Classifies the evidence bundle produced by scripts/generate_plan_json.sh
according to docs/drift-detection-spec.md (§5.3 integrity gate, §6
classification, §8.2 engine rules). Standard library only; never calls
Terraform, Azure or an LLM. The same bundle always yields byte-identical
output.

Three views of each managed resource are compared (spec §6):
  S  recorded state   resource_drift[].change.before (else resource_changes[].change.before)
  R  refreshed/real   resource_drift[].change.after  (equals S without a drift entry)
  D  desired          resource_changes[].change.after

Plan loading, the integrity gate and S/R/D extraction live in
src/drift_engine/parser.py (Task 4.2), and the attribute diff (§6.2 rule and
Task 3.4 detail) in src/drift_engine/comparator.py (Task 4.4), both imported
below; this script needs no installation step.

Usage:
  scripts/detect_drift.py ARTIFACT_DIR [--output PATH]

Writes ARTIFACT_DIR/drift_classification.json (or PATH).

Task 3.4 adds, without changing any Task 3.3 field: per-resource
`attribute_changes` (nested paths with S/R/D values; sensitive values
redacted) and top-level `resource_types` (resources grouped by Terraform type).

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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from drift_engine.comparator import (  # noqa: E402
    CONFIG_CHANGED,
    DRIFTED,
    DRIFTED_AND_CONFIG_CHANGED,
    DRIFTED_CONVERGED,
    UNKNOWN_UNTIL_APPLY,
    attribute_changes,
    classify_attributes,
)
from drift_engine.parser import (  # noqa: E402
    EvidenceError,
    ParsedPlan,
    ResourceEvidence,
    extract_plan,
    load_json,
    normalize_action,
    parse_plan_file,
    resource_evidence,
)

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

# ---------------------------------------------------------------------------
# Resource-level classification (spec §6.1)
# ---------------------------------------------------------------------------

def classify_resource(drift: dict | None, change: dict | None) -> dict:
    if drift is None and change is None:
        raise ValueError("classify_resource needs a drift or change entry")
    return _classify_evidence(resource_evidence(drift, change))


def _classify_evidence(ev: ResourceEvidence) -> dict:
    action = normalize_action(ev.actions)
    drift_action = normalize_action(ev.drift_actions)
    notes: list[str] = []

    attributes = classify_attributes(ev.state, ev.real, ev.desired, ev.after_unknown)
    kinds = {a["class"] for a in attributes}
    details = attribute_changes(ev.state, ev.real, ev.desired, ev.after_unknown, list(ev.sensitive_masks))

    moved = ev.previous_address is not None
    importing = ev.importing

    if ev.drift_actions is None:
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
            notes.append(f"unrecognized actions {ev.actions}")
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
        notes.append(f"moved from {ev.previous_address} (move-only exit behavior unverified, spec §5.3)")
    if importing:
        notes.append("import pending (import-only exit behavior unverified, spec §5.3)")
    if UNKNOWN_UNTIL_APPLY in kinds:
        notes.append("some attribute values are unknown until apply")

    ambiguous = cls == UNDETERMINED or DRIFTED_AND_CONFIG_CHANGED in kinds

    return {
        "address": ev.address,
        "module_address": ev.module_address,
        "mode": ev.mode,
        "type": ev.type,
        "name": ev.name,
        "index": ev.index,
        "provider_name": ev.provider_name,
        "classification": cls,
        "action": action,
        "actions": ev.actions,
        "action_reason": ev.action_reason,
        "drift_action": drift_action,
        "drift_actions": ev.drift_actions,
        "previous_address": ev.previous_address,
        "importing": importing,
        "attributes": attributes,
        "attribute_changes": details,
        "ambiguous": ambiguous,
        "notes": notes,
    }


def classify_plan(plan: dict) -> dict:
    """Classify a plan that has already passed the integrity gate."""
    return classify_parsed(extract_plan(plan))


def classify_parsed(parsed: ParsedPlan) -> dict:
    resources = [_classify_evidence(ev) for ev in parsed.resources]
    output_changes = [
        {"name": name, "action": normalize_action(actions), "actions": actions}
        for name, actions in parsed.output_changes.items()
    ]

    counts: dict[str, int] = {}
    for r in resources:
        counts[r["classification"]] = counts.get(r["classification"], 0) + 1

    by_type: dict[str, list[dict]] = {}
    for r in resources:
        by_type.setdefault(str(r["type"]), []).append(r)
    resource_types = []
    for rtype in sorted(by_type):
        type_counts: dict[str, int] = {}
        for r in by_type[rtype]:
            type_counts[r["classification"]] = type_counts.get(r["classification"], 0) + 1
        resource_types.append({
            "type": rtype,
            "resource_count": len(by_type[rtype]),
            "addresses": [r["address"] for r in by_type[rtype]],
            "classification_counts": dict(sorted(type_counts.items())),
        })
    drift = sum(1 for ev in parsed.resources if ev.drift_actions is not None)
    resource_pending = any(r["classification"] != IN_SYNC for r in resources)
    output_pending = any(o["action"] != "no-op" for o in output_changes)

    return {
        "has_drift": drift > 0,
        "summary": {
            "resources_total": len(resources),
            "drifted_resources": drift,
            "classification_counts": dict(sorted(counts.items())),
            "ambiguous_resources": sum(1 for r in resources if r["ambiguous"]),
            "has_pending_resource_changes": resource_pending,
            "has_pending_output_changes": output_pending,
            "output_only_change": output_pending and not resource_pending and not drift,
        },
        "resources": resources,
        "resource_types": resource_types,
        "output_changes": output_changes,
    }


# ---------------------------------------------------------------------------
# Evidence bundle
# ---------------------------------------------------------------------------

_RUN_FIELDS = (
    "run_id", "environment", "working_dir", "backend_key", "git_commit",
    "started_at", "finished_at", "terraform_version", "plan_exit_code", "show_exit_code",
)


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
        "resource_types": [],
        "output_changes": [],
    }
    try:
        manifest = load_json(os.path.join(artifact_dir, MANIFEST_FILE), "manifest")
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

        parsed = parse_plan_file(os.path.join(artifact_dir, PLAN_FILE), plan_rc, tf_version)
        result["plan"] = parsed.header
        result.update(classify_parsed(parsed))
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
