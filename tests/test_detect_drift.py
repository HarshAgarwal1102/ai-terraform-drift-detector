"""Tests for scripts/detect_drift.py (Task 3.3).

Run from the repository root:
    python3 -m unittest discover -s tests -v

Fixtures in tests/fixtures/plan_evidence/ are real evidence bundles produced by
scripts/generate_plan_json.sh (Terraform 1.14.7, azurerm ~> 5.0) against a scratch
copy of terraform/environments/dev with a local backend seeded from a read-only
state pull. Each scenario altered only the scratch state copy and/or tfvars; live
Azure was only read and nothing was applied. Identifiers were sanitized
(subscription ID -> <AZURE_SUBSCRIPTION_ID>, scratch paths -> repo-relative), and
backend_key is null because the scratch copy used a local backend.

Plan files are stored as plan.sanitized.json because .gitignore deliberately ignores
every plan.json (real plan artifacts must never be committed). setUpModule copies the
fixtures into a temporary directory as proper bundles (plan.json) before any test runs.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "detect_drift.py")
FIXTURE_SOURCE = os.path.join(ROOT, "tests", "fixtures", "plan_evidence")
FIXTURES = ""  # materialized bundle directory, set by setUpModule
MAIN = 'module.resource_group.azurerm_resource_group.this["main"]'

_spec = importlib.util.spec_from_file_location("detect_drift", SCRIPT)
dd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dd)


def setUpModule():
    global FIXTURES
    FIXTURES = tempfile.mkdtemp(prefix="detect-drift-fixtures-")
    for name in os.listdir(FIXTURE_SOURCE):
        src = os.path.join(FIXTURE_SOURCE, name)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(FIXTURES, name)
        os.makedirs(dst)
        shutil.copy(os.path.join(src, "detection_run.json"), dst)
        sanitized = os.path.join(src, "plan.sanitized.json")
        if os.path.exists(sanitized):
            shutil.copy(sanitized, os.path.join(dst, "plan.json"))


def tearDownModule():
    shutil.rmtree(FIXTURES, ignore_errors=True)


def classify(name: str) -> dict:
    return dd.classify_bundle(os.path.join(FIXTURES, name))


def by_index(result: dict) -> dict:
    return {r["index"]: r for r in result["resources"]}


def attrs(resource: dict) -> dict:
    return {a["name"]: a["class"] for a in resource["attributes"]}


# ---------------------------------------------------------------------------
# Real evidence scenarios
# ---------------------------------------------------------------------------

class TestRealEvidenceScenarios(unittest.TestCase):
    def test_in_sync(self):
        r = classify("in_sync")
        self.assertEqual(r["outcome"], "succeeded")
        self.assertIs(r["has_drift"], False)
        self.assertEqual(r["run"]["plan_exit_code"], 0)
        main = by_index(r)["main"]
        self.assertEqual(main["classification"], dd.IN_SYNC)
        self.assertEqual(main["attributes"], [])
        self.assertFalse(r["summary"]["output_only_change"])

    def test_config_change_is_not_drift(self):  # scenario A
        r = classify("config_change")
        self.assertEqual(r["run"]["plan_exit_code"], 2)
        self.assertIs(r["has_drift"], False)
        main = by_index(r)["main"]
        self.assertEqual(main["classification"], dd.CONFIG_CHANGE)
        self.assertEqual(main["action"], "update")
        self.assertIsNone(main["drift_action"])
        self.assertEqual(attrs(main), {"tags": dd.CONFIG_CHANGED})

    def test_external_drift(self):  # scenario B
        r = classify("external_drift")
        self.assertEqual(r["run"]["plan_exit_code"], 2)
        self.assertIs(r["has_drift"], True)
        main = by_index(r)["main"]
        self.assertEqual(main["classification"], dd.EXTERNAL_DRIFT)
        self.assertEqual(main["drift_action"], "update")
        self.assertEqual(attrs(main), {"tags": dd.DRIFTED})
        self.assertFalse(main["ambiguous"])

    def test_drift_and_config_change_is_ambiguous(self):  # scenario C
        r = classify("drift_and_config_change")
        self.assertIs(r["has_drift"], True)
        main = by_index(r)["main"]
        self.assertEqual(main["classification"], dd.DRIFT_AND_CONFIG_CHANGE)
        self.assertEqual(attrs(main), {"tags": dd.DRIFTED_AND_CONFIG_CHANGED})
        self.assertTrue(main["ambiguous"])
        self.assertEqual(r["summary"]["ambiguous_resources"], 1)

    def test_converged_drift_with_exit_0(self):  # scenario D
        r = classify("converged_drift")
        self.assertEqual(r["run"]["plan_exit_code"], 0)
        self.assertIs(r["has_drift"], True, "exit 0 must not hide converged drift")
        main = by_index(r)["main"]
        self.assertEqual(main["classification"], dd.CONVERGED_DRIFT)
        self.assertEqual(main["action"], "no-op")
        self.assertEqual(attrs(main), {"tags": dd.DRIFTED_CONVERGED})

    def test_resource_added(self):  # scenario F
        r = classify("resource_added")
        self.assertIs(r["has_drift"], False)
        res = by_index(r)
        self.assertEqual(res["extra"]["classification"], dd.RESOURCE_ADDED)
        self.assertEqual(res["extra"]["action"], "create")
        self.assertEqual(res["main"]["classification"], dd.IN_SYNC)

    def test_resource_removed(self):  # scenario F
        r = classify("resource_removed")
        self.assertIs(r["has_drift"], False)
        res = by_index(r)
        self.assertEqual(res["main"]["classification"], dd.RESOURCE_REMOVED)
        self.assertEqual(res["main"]["action"], "delete")
        self.assertEqual(res["main"]["action_reason"], "delete_because_each_key")
        self.assertEqual(res["other"]["classification"], dd.RESOURCE_ADDED)

    def test_external_deletion_distinct_from_removal(self):  # scenario F
        r = classify("external_deletion")
        self.assertIs(r["has_drift"], True)
        res = by_index(r)
        self.assertEqual(res["ghost"]["classification"], dd.EXTERNAL_DELETION)
        self.assertEqual(res["ghost"]["drift_action"], "delete")
        self.assertEqual(res["ghost"]["action"], "create")
        self.assertEqual(res["main"]["classification"], dd.IN_SYNC)

    def test_replace(self):
        r = classify("replace")
        self.assertIs(r["has_drift"], False)
        main = by_index(r)["main"]
        self.assertEqual(main["classification"], dd.CONFIG_CHANGE)
        self.assertEqual(main["action"], "replace")
        self.assertEqual(main["action_reason"], "replace_because_cannot_update")
        a = attrs(main)
        self.assertEqual(a["location"], dd.CONFIG_CHANGED)
        self.assertEqual(a["id"], dd.UNKNOWN_UNTIL_APPLY)

    def test_output_only_change_is_not_resource_drift(self):
        r = classify("output_only_change")
        self.assertEqual(r["run"]["plan_exit_code"], 2)
        self.assertIs(r["has_drift"], False)
        self.assertTrue(r["summary"]["output_only_change"])
        self.assertFalse(r["summary"]["has_pending_resource_changes"])
        self.assertEqual({x["classification"] for x in r["resources"]}, {dd.IN_SYNC})
        self.assertEqual(r["output_changes"][0]["action"], "delete")

    def test_failed_run_is_unknown(self):
        r = classify("failed_run")
        self.assertEqual(r["outcome"], "failed")
        self.assertIsNone(r["has_drift"])
        self.assertEqual(r["failure"]["source"], "detection_run")
        self.assertEqual(r["failure"]["stage"], "plan")
        self.assertEqual(r["resources"], [])

    def test_exit_code_alone_does_not_decide_drift(self):
        cases = {name: classify(name) for name in ("config_change", "external_drift", "converged_drift", "in_sync")}
        self.assertEqual(cases["config_change"]["run"]["plan_exit_code"], cases["external_drift"]["run"]["plan_exit_code"])
        self.assertNotEqual(cases["config_change"]["has_drift"], cases["external_drift"]["has_drift"])
        self.assertEqual(cases["converged_drift"]["run"]["plan_exit_code"], cases["in_sync"]["run"]["plan_exit_code"])
        self.assertNotEqual(cases["converged_drift"]["has_drift"], cases["in_sync"]["has_drift"])

    def test_no_attribute_values_in_output(self):
        for name in os.listdir(FIXTURES):
            for res in classify(name)["resources"]:
                for a in res["attributes"]:
                    self.assertEqual(set(a), {"name", "class"})
                self.assertNotIn("before", res)
                self.assertNotIn("after", res)


# ---------------------------------------------------------------------------
# Invalid evidence must never become "no drift"
# ---------------------------------------------------------------------------

class TestInvalidEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="detect-drift-test-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def bundle(self, source: str, manifest=None, plan=None, raw_plan: str | None = None, drop=()) -> str:
        d = os.path.join(self.tmp, "bundle")
        shutil.copytree(os.path.join(FIXTURES, source), d)
        mpath, ppath = os.path.join(d, "detection_run.json"), os.path.join(d, "plan.json")
        for path, mutate in ((mpath, manifest), (ppath, plan)):
            if mutate:
                with open(path) as fh:
                    data = json.load(fh)
                mutate(data)
                with open(path, "w") as fh:
                    json.dump(data, fh)
        if raw_plan is not None:
            with open(ppath, "w") as fh:
                fh.write(raw_plan)
        for f in drop:
            os.remove(os.path.join(d, f))
        return d

    def assertRejected(self, d: str, stage: str, contains: str = ""):
        r = dd.classify_bundle(d)
        self.assertEqual(r["outcome"], "failed")
        self.assertIsNone(r["has_drift"], "rejected evidence must never yield has_drift=false")
        self.assertEqual(r["failure"]["source"], "classifier")
        self.assertEqual(r["failure"]["stage"], stage)
        self.assertIn(contains, r["failure"]["reason"])
        self.assertEqual(r["resources"], [])

    def test_missing_manifest(self):
        self.assertRejected(self.bundle("in_sync", drop=("detection_run.json",)), "manifest", "not found")

    def test_missing_plan_json_for_succeeded_run(self):
        self.assertRejected(self.bundle("in_sync", drop=("plan.json",)), "integrity", "not found")

    def test_truncated_plan_json(self):
        self.assertRejected(self.bundle("in_sync", raw_plan='{"format_version": "1.2", '), "integrity", "not valid JSON")

    def test_multiple_json_documents(self):
        self.assertRejected(self.bundle("in_sync", raw_plan="{}{}"), "integrity", "not valid JSON")

    def test_plan_not_object(self):
        self.assertRejected(self.bundle("in_sync", raw_plan="[]"), "integrity", "not a JSON object")

    def test_errored_plan_with_succeeded_manifest(self):
        def p(plan):
            plan["errored"] = True
            plan["complete"] = False
            plan.pop("resource_changes", None)
        self.assertRejected(self.bundle("in_sync", plan=p), "integrity", "errored is true")

    def test_missing_complete(self):
        self.assertRejected(self.bundle("in_sync", plan=lambda p: p.pop("complete")), "integrity", "complete is null")

    def test_unsupported_format_version(self):
        self.assertRejected(self.bundle("in_sync", plan=lambda p: p.update(format_version="2.0")), "integrity", "format_version")

    def test_terraform_version_mismatch(self):
        self.assertRejected(self.bundle("in_sync", plan=lambda p: p.update(terraform_version="1.7.0")), "integrity", "terraform_version")

    def test_resource_changes_not_array(self):
        self.assertRejected(self.bundle("in_sync", plan=lambda p: p.update(resource_changes={})), "integrity", "not an array")

    def test_entry_without_actions(self):
        self.assertRejected(
            self.bundle("external_drift", plan=lambda p: p["resource_changes"][0]["change"].pop("actions")),
            "integrity", "without address/change.actions",
        )

    def test_exit_2_but_no_pending_change(self):
        self.assertRejected(
            self.bundle("in_sync", manifest=lambda m: m.update(plan_exit_code=2)), "integrity", "no pending change"
        )

    def test_exit_0_but_pending_change(self):
        self.assertRejected(
            self.bundle("external_drift", manifest=lambda m: m.update(plan_exit_code=0)), "integrity", "pending change"
        )

    def test_succeeded_manifest_with_error_exit_code(self):
        self.assertRejected(
            self.bundle("in_sync", manifest=lambda m: m.update(plan_exit_code=1)), "manifest", "plan_exit_code 1"
        )

    def test_unrecognized_manifest_outcome(self):
        self.assertRejected(self.bundle("in_sync", manifest=lambda m: m.update(outcome="ok")), "manifest", "unrecognized outcome")

    def test_errored_plan_alongside_failed_manifest_is_ignored(self):
        # A failed run stays failed even if a plan.json is present.
        d = self.bundle("in_sync", manifest=lambda m: m.update(outcome="failed", failure_stage="plan", failure_reason="x"))
        r = dd.classify_bundle(d)
        self.assertEqual((r["outcome"], r["has_drift"], r["failure"]["source"]), ("failed", None, "detection_run"))


# ---------------------------------------------------------------------------
# Rule-level unit tests (synthetic)
# ---------------------------------------------------------------------------

class TestAttributeRule(unittest.TestCase):
    def test_all_attribute_classes(self):
        state = {"a": 1, "b": 1, "c": 1, "d": 1, "e": 1, "u": 1}
        real = {"a": 2, "b": 2, "c": 1, "d": 2, "e": 1, "u": 1}
        desired = {"a": 1, "b": 2, "c": 9, "d": 9, "e": 1}
        out = {x["name"]: x["class"] for x in dd.classify_attributes(state, real, desired, {"u": True})}
        self.assertEqual(out, {
            "a": dd.DRIFTED,
            "b": dd.DRIFTED_CONVERGED,
            "c": dd.CONFIG_CHANGED,
            "d": dd.DRIFTED_AND_CONFIG_CHANGED,
            "u": dd.UNKNOWN_UNTIL_APPLY,
        })  # "e" unchanged is omitted

    def test_missing_differs_from_null(self):
        out = dd.classify_attributes({"x": None}, {"x": None}, {}, {})
        self.assertEqual(out, [{"name": "x", "class": dd.CONFIG_CHANGED}])

    def test_nested_unknown(self):
        out = dd.classify_attributes({"t": {"k": 1}}, {"t": {"k": 1}}, {"t": {}}, {"t": {"k": True}})
        self.assertEqual(out, [{"name": "t", "class": dd.UNKNOWN_UNTIL_APPLY}])

    def test_object_level_changes_have_no_attributes(self):
        self.assertEqual(dd.classify_attributes(None, None, {"a": 1}, {}), [])
        self.assertEqual(dd.classify_attributes({"a": 1}, None, {"a": 1}, {}), [])


def entry(address, actions, before=None, after=None, **extra):
    change = {"actions": actions, "before": before, "after": after, "after_unknown": {}}
    change.update(extra.pop("change", {}))
    return dict({"address": address, "mode": "managed", "type": "t", "name": "n", "change": change}, **extra)


class TestResourceRule(unittest.TestCase):
    def test_drift_with_unexplained_pending_change_is_undetermined(self):
        drift = entry("r", ["update"], {"a": 1}, {"a": 2})
        change = entry("r", ["update"], {"a": 2}, {"a": 2}, change={"after_unknown": {"z": True}})
        r = dd.classify_resource(drift, change)
        self.assertEqual(r["classification"], dd.UNDETERMINED)
        self.assertTrue(r["ambiguous"])

    def test_drift_plus_config_on_different_attributes(self):
        drift = entry("r", ["update"], {"a": 1, "b": 1}, {"a": 2, "b": 1})
        change = entry("r", ["update"], {"a": 2, "b": 1}, {"a": 1, "b": 5})
        r = dd.classify_resource(drift, change)
        self.assertEqual(r["classification"], dd.DRIFT_AND_CONFIG_CHANGE)
        self.assertFalse(r["ambiguous"], "both causes are attributable per attribute")

    def test_drift_and_removed_from_config(self):
        drift = entry("r", ["update"], {"a": 1}, {"a": 2})
        change = entry("r", ["delete"], {"a": 2}, None)
        self.assertEqual(dd.classify_resource(drift, change)["classification"], dd.DRIFT_AND_CONFIG_CHANGE)

    def test_deleted_remotely_and_no_longer_declared(self):
        drift = entry("r", ["delete"], {"a": 1}, None)
        self.assertEqual(dd.classify_resource(drift, None)["classification"], dd.CONVERGED_DRIFT)

    def test_move_only_is_config_change(self):
        change = entry("r", ["no-op"], {"a": 1}, {"a": 1}, previous_address="old")
        r = dd.classify_resource(None, change)
        self.assertEqual(r["classification"], dd.CONFIG_CHANGE)
        self.assertEqual(r["previous_address"], "old")

    def test_import_is_config_change(self):
        change = entry("r", ["no-op"], {"a": 1}, {"a": 1}, change={"importing": {"id": "x"}})
        r = dd.classify_resource(None, change)
        self.assertEqual(r["classification"], dd.CONFIG_CHANGE)
        self.assertTrue(r["importing"])

    def test_data_sources_are_ignored(self):
        plan = {"resource_changes": [dict(entry("data.x", ["read"]), mode="data")], "output_changes": {}}
        out = dd.classify_plan(plan)
        self.assertEqual(out["resources"], [])
        self.assertIs(out["has_drift"], False)

    def test_normalize_action(self):
        self.assertEqual(dd.normalize_action(["create", "delete"]), "replace")
        self.assertEqual(dd.normalize_action(["delete", "create"]), "replace")
        self.assertEqual(dd.normalize_action(["forget"]), "unrecognized")


# ---------------------------------------------------------------------------
# CLI and determinism
# ---------------------------------------------------------------------------

class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="detect-drift-cli-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)

    def test_exit_codes_and_default_output(self):
        for name, expected in (("in_sync", 0), ("external_drift", 0), ("failed_run", 1)):
            d = os.path.join(self.tmp, name)
            shutil.copytree(os.path.join(FIXTURES, name), d)
            proc = self.run_cli(d)
            self.assertEqual(proc.returncode, expected, proc.stderr)
            with open(os.path.join(d, dd.OUTPUT_FILE)) as fh:
                out = json.load(fh)
            self.assertEqual(out["outcome"], "succeeded" if expected == 0 else "failed")
        self.assertEqual(self.run_cli(os.path.join(self.tmp, "absent")).returncode, 64)

    def test_output_is_byte_deterministic(self):
        paths = []
        for i in range(2):
            p = os.path.join(self.tmp, f"out{i}.json")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                dd.main([os.path.join(FIXTURES, "resource_removed"), "--output", p])
            with open(p, "rb") as fh:
                paths.append(fh.read())
        self.assertEqual(paths[0], paths[1])


if __name__ == "__main__":
    unittest.main()
