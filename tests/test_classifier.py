"""Tests for src/drift_engine/classifier.py (moved from the script in Task 4.6;
dedicated tests added in Task 4.7).

Run from the repository root:
    pytest tests/test_classifier.py
    python3 -m unittest tests.test_classifier    (no installation needed)

The classification rules themselves are exercised end to end by
tests/test_detect_drift.py; this file covers evaluate() and the branches that
suite does not reach.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from drift_engine import classifier as c  # noqa: E402
from drift_engine.parser import ParsedPlan  # noqa: E402

FIXTURES = os.path.join(ROOT, "tests", "fixtures", "plan_evidence")
RUN_FIELDS = {"run_id", "environment", "working_dir", "backend_key", "git_commit", "started_at", "finished_at",
              "terraform_version", "plan_exit_code", "show_exit_code", "detection_outcome"}


def plan_path(name: str) -> str:
    return os.path.join(FIXTURES, name, "plan.sanitized.json")


def manifest_path(name: str) -> str:
    return os.path.join(FIXTURES, name, "detection_run.json")


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def entry(address="azurerm_x.this", actions=("update",), before=None, after=None) -> dict:
    return {"address": address, "mode": "managed", "type": "azurerm_x", "name": "this",
            "change": {"actions": list(actions), "before": before, "after": after}}


class TempDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drift-classifier-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def write(self, name: str, data) -> str:
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return path


class TestEvaluate(TempDir):
    def test_success_returns_the_evidence(self):
        ev = c.evaluate(plan_path("external_drift"), manifest_path("external_drift"))
        self.assertEqual(ev.report["outcome"], "succeeded")
        self.assertIsInstance(ev.parsed, ParsedPlan)
        self.assertEqual(ev.plan, load(plan_path("external_drift")))
        self.assertEqual(ev.report["run"]["detection_outcome"], "succeeded")

    def test_failure_returns_no_evidence(self):
        ev = c.evaluate(os.path.join(self.tmp, "missing.json"), manifest_path("in_sync"))
        self.assertEqual((ev.report["outcome"], ev.parsed, ev.plan), ("failed", None, None))

    def test_classify_bundle_is_evaluate_on_the_bundle(self):
        for name in sorted(os.listdir(FIXTURES)):
            with self.subTest(name):
                bundle = os.path.join(self.tmp, name)
                os.makedirs(bundle)
                shutil.copy(manifest_path(name), bundle)
                if os.path.exists(plan_path(name)):
                    shutil.copy(plan_path(name), os.path.join(bundle, c.PLAN_FILE))
                self.assertEqual(c.classify_bundle(bundle),
                                 c.evaluate(os.path.join(bundle, c.PLAN_FILE),
                                            os.path.join(bundle, c.MANIFEST_FILE)).report)

    def test_plan_only_run_is_all_null(self):
        report = c.evaluate(plan_path("in_sync")).report
        self.assertEqual(report["outcome"], "succeeded")
        self.assertEqual(set(report["run"]), RUN_FIELDS)
        self.assertEqual(set(report["run"].values()), {None})

    def test_plan_only_skips_only_the_manifest_checks(self):
        plan = load(plan_path("external_drift"))
        plan["terraform_version"] = "0.0.1"  # would contradict any manifest
        self.assertEqual(c.evaluate(self.write("plan.json", plan)).report["outcome"], "succeeded")
        plan["complete"] = False
        report = c.evaluate(self.write("plan.json", plan)).report
        self.assertEqual(report["failure"]["stage"], "integrity")

    def test_report_keys_identical_in_both_modes(self):
        a = c.evaluate(plan_path("replace")).report
        b = c.evaluate(plan_path("replace"), manifest_path("replace")).report
        self.assertEqual(set(a), set(b))
        self.assertEqual({k: v for k, v in a.items() if k != "run"}, {k: v for k, v in b.items() if k != "run"})


class TestManifestFailures(TempDir):
    def manifest(self, **changes) -> str:
        data = load(manifest_path("external_drift"))
        data.update(changes)
        return self.write("custom_manifest.json", data)

    def check(self, manifest: str, reason: str):
        report = c.evaluate(plan_path("external_drift"), manifest).report
        self.assertEqual((report["outcome"], report["has_drift"]), ("failed", None))
        self.assertEqual((report["failure"]["source"], report["failure"]["stage"]), ("classifier", "manifest"))
        self.assertEqual(report["failure"]["reason"], reason)
        return report

    def test_manifest_not_an_object_names_the_given_file(self):
        self.check(self.write("custom_manifest.json", [1, 2]), "custom_manifest.json is not a JSON object")

    def test_terraform_version_missing(self):
        self.check(self.manifest(terraform_version=""), "terraform_version missing")
        self.check(self.manifest(terraform_version=None), "terraform_version missing")

    def test_bad_plan_exit_code(self):
        for rc in (1, "2", None, True):
            with self.subTest(rc=rc):
                self.check(self.manifest(plan_exit_code=rc), f"succeeded run with plan_exit_code {rc!r}")

    def test_unrecognized_outcome_keeps_the_run(self):
        report = self.check(self.manifest(outcome="partial"), "unrecognized outcome 'partial'")
        self.assertEqual(report["run"]["detection_outcome"], "partial")

    def test_missing_manifest_file(self):
        self.check(os.path.join(self.tmp, "nope.json"), "nope.json not found")


class TestClassificationBranches(unittest.TestCase):
    def test_classify_resource_needs_an_entry(self):
        with self.assertRaises(ValueError):
            c.classify_resource(None, None)

    def test_unrecognized_actions_are_undetermined(self):
        r = c.classify_resource(None, entry(actions=("update", "delete")))
        self.assertEqual((r["classification"], r["action"]), (c.UNDETERMINED, "unrecognized"))
        self.assertTrue(r["ambiguous"])
        self.assertIn("unrecognized actions ['update', 'delete']", r["notes"])

    def test_missing_remotely_but_update_planned_is_undetermined(self):
        drift = entry(actions=("delete",), before={"a": 1}, after=None)
        change = entry(actions=("update",), before=None, after={"a": 1})
        r = c.classify_resource(drift, change)
        self.assertEqual(r["classification"], c.UNDETERMINED)
        self.assertIn("object missing remotely but planned action is update", r["notes"])

    def test_classification_is_deterministic_and_input_is_not_mutated(self):
        plan = load(plan_path("external_deletion"))
        snapshot = copy.deepcopy(plan)
        first = json.dumps(c.classify_plan(plan), sort_keys=True)
        self.assertEqual(json.dumps(c.classify_plan(plan), sort_keys=True), first)
        self.assertEqual(plan, snapshot)


class TestSeverityInReport(unittest.TestCase):
    """Task 6.2A: deterministic severity is attached to the report, never mis-attributed."""

    def test_every_change_and_resource_is_rated(self):
        report = c.classify_plan(load(plan_path("external_deletion")))
        for resource in report["resources"]:
            self.assertEqual(set(resource["severity"]), {"level", "reasons"})
            for change in resource["attribute_changes"]:
                self.assertEqual(set(change["severity"]), {"level", "rules"})
                self.assertEqual(set(change["assessment"]), {"category", "noise_rule"})
        self.assertEqual(report["summary"]["highest_severity"], "HIGH")

    def test_without_configuration_evidence_nothing_is_noise(self):
        plan = load(plan_path("replace"))
        parsed = c.extract_plan(plan)
        unconfigured = c.classify_parsed(parsed)  # no configuration: every change undetermined
        categories = {ch["assessment"]["category"] for r in unconfigured["resources"] for ch in r["attribute_changes"]}
        self.assertEqual(categories, {"undetermined"})
        levels = {ch["severity"]["level"] for r in unconfigured["resources"] for ch in r["attribute_changes"]}
        self.assertNotIn("INFO", levels)  # unproven noise is never rated down

    def test_mismatched_comparison_is_refused(self):
        from unittest import mock

        from drift_engine import comparator

        def shuffled(parsed, configured):
            result = comparator.compare_plan(parsed, configured)
            return tuple(comparator.ResourceComparison(r.address, r.type, r.action, r.changes[::-1])
                         for r in result)

        plan = load(plan_path("external_deletion"))  # 8 changes, so reversing reorders them
        with mock.patch.object(c, "compare_plan", shuffled):
            with self.assertRaisesRegex(RuntimeError, "do not match the report"):
                c.classify_plan(plan)


if __name__ == "__main__":
    unittest.main()
