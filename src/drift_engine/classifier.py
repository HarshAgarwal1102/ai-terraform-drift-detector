"""Deterministic drift classification (spec §6; Tasks 3.3-3.4).

Classifies a run manifest + plan.json into the drift report described by
schemas/drift_report.schema.json. Migrated unchanged from scripts/detect_drift.py
(Task 4.6), which now imports it, so the package CLI and the script produce the
same report from the same evidence.

Standard library only. No Terraform, Azure, network or LLM access; the same
evidence always yields the same report.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from drift_engine.comparator import (
    CONFIG_CHANGED,
    DRIFTED,
    DRIFTED_AND_CONFIG_CHANGED,
    DRIFTED_CONVERGED,
    UNKNOWN_UNTIL_APPLY,
    attribute_changes,
    classify_attributes,
)
from drift_engine.parser import (
    PLAN_STAGE,
    EvidenceError,
    ParsedPlan,
    ResourceEvidence,
    extract_plan,
    load_json,
    normalize_action,
    parse_plan,
    resource_evidence,
)

CLASSIFICATION_VERSION = "1"
OUTPUT_FILE = "drift_classification.json"
MANIFEST_FILE = "detection_run.json"
PLAN_FILE = "plan.json"

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


@dataclass(frozen=True)
class Evaluation:
    """A report plus the evidence behind it (None unless the outcome is succeeded)."""

    report: dict
    parsed: ParsedPlan | None
    plan: dict | None  # raw plan.json, e.g. for comparator.configured_attributes


def classify_bundle(artifact_dir: str) -> dict:
    """Build the classification result for an evidence bundle (pure, deterministic)."""
    return evaluate(
        os.path.join(artifact_dir, PLAN_FILE), os.path.join(artifact_dir, MANIFEST_FILE)
    ).report


def evaluate(plan_path: str, manifest_path: str | None = None) -> Evaluation:
    """Classify plan.json, with its run manifest when given.

    With a manifest the full integrity gate applies (spec §5.3), exactly as for an
    evidence bundle. Without one, `run` holds only nulls and the two checks that need
    the manifest (plan exit code consistency, Terraform version) are skipped; every
    other check still applies.
    """
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
        if manifest_path is None:
            result["run"] = {k: None for k in _RUN_FIELDS}
            result["run"]["detection_outcome"] = None
            plan_rc = tf_version = None
        else:
            manifest = load_json(manifest_path, "manifest")
            if not isinstance(manifest, dict):
                raise EvidenceError("manifest", f"{os.path.basename(manifest_path)} is not a JSON object")
            result["run"] = {k: manifest.get(k) for k in _RUN_FIELDS}
            result["run"]["detection_outcome"] = manifest.get("outcome")

            if manifest.get("outcome") != "succeeded":
                if manifest.get("outcome") == "failed":
                    result["failure"] = {
                        "source": "detection_run",
                        "stage": manifest.get("failure_stage"),
                        "reason": manifest.get("failure_reason"),
                    }
                    return Evaluation(result, None, None)
                raise EvidenceError("manifest", f"unrecognized outcome {manifest.get('outcome')!r}")

            plan_rc = manifest.get("plan_exit_code")
            if type(plan_rc) is not int or plan_rc not in (0, 2):
                raise EvidenceError("manifest", f"succeeded run with plan_exit_code {plan_rc!r}")
            tf_version = manifest.get("terraform_version")
            if not isinstance(tf_version, str) or not tf_version:
                raise EvidenceError("manifest", "terraform_version missing")

        plan = load_json(plan_path, PLAN_STAGE)
        parsed = parse_plan(plan, plan_rc, tf_version)
        result["plan"] = parsed.header
        result.update(classify_parsed(parsed))
        result["outcome"] = "succeeded"
        return Evaluation(result, parsed, plan)
    except EvidenceError as exc:
        result["failure"] = {"source": "classifier", "stage": exc.stage, "reason": exc.reason}
        return Evaluation(result, None, None)
