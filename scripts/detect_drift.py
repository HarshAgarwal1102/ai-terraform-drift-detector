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

The logic lives in the drift_engine package (src/drift_engine/): plan loading
and the integrity gate in parser.py (Task 4.2), the attribute diff in
comparator.py (Task 4.4) and the classification in classifier.py (Task 4.6).
This script is a thin wrapper around them and needs no installation step; the
installed `drift-engine analyze` command produces the same report.

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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

# Re-exported (see __all__) for callers and tests that use this script as a module.
from drift_engine.classifier import (  # noqa: E402
    CLASSIFICATION_VERSION,
    CONFIG_CHANGE,
    CONFIG_CHANGED,
    CONVERGED_DRIFT,
    DRIFT_AND_CONFIG_CHANGE,
    DRIFTED,
    DRIFTED_AND_CONFIG_CHANGED,
    DRIFTED_CONVERGED,
    EXTERNAL_DELETION,
    EXTERNAL_DRIFT,
    IN_SYNC,
    MANIFEST_FILE,
    OUTPUT_FILE,
    PLAN_FILE,
    RESOURCE_ADDED,
    RESOURCE_REMOVED,
    UNDETERMINED,
    UNKNOWN_UNTIL_APPLY,
    classify_attributes,
    classify_bundle,
    classify_parsed,
    classify_plan,
    classify_resource,
)
from drift_engine.parser import EvidenceError, normalize_action  # noqa: E402

__all__ = [  # re-exports kept for callers and tests that load this script as a module
    "CLASSIFICATION_VERSION", "CONFIG_CHANGE", "CONFIG_CHANGED", "CONVERGED_DRIFT", "DRIFT_AND_CONFIG_CHANGE",
    "DRIFTED", "DRIFTED_AND_CONFIG_CHANGED", "DRIFTED_CONVERGED", "EXTERNAL_DELETION", "EXTERNAL_DRIFT", "IN_SYNC",
    "MANIFEST_FILE", "OUTPUT_FILE", "PLAN_FILE", "RESOURCE_ADDED", "RESOURCE_REMOVED", "UNDETERMINED",
    "UNKNOWN_UNTIL_APPLY", "EvidenceError", "classify_attributes", "classify_bundle", "classify_parsed",
    "classify_plan", "classify_resource", "normalize_action", "main",
]

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 64


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
