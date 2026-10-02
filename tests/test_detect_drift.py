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
# Task 3.4: attribute detail and resource-type grouping
# ---------------------------------------------------------------------------

# Task 3.3 output fields; Task 3.4 may only add `attribute_changes` / `resource_types`.
TASK33_RESOURCE_KEYS = {
    "address", "module_address", "mode", "type", "name", "index", "provider_name",
    "classification", "action", "actions", "action_reason", "drift_action", "drift_actions",
    "previous_address", "importing", "attributes", "ambiguous", "notes",
}
TASK33_TOP_KEYS = {
    "classification_version", "outcome", "has_drift", "failure", "run", "plan",
    "summary", "resources", "output_changes",
}


def changes_by_path(resource: dict) -> dict:
    return {".".join(c["path"]): c for c in resource["attribute_changes"]}


def value(view: dict):
    assert view["status"] == "value", view
    return view["value"]


def res(address, rtype, actions, before, after, **change):
    """A managed resource_changes / resource_drift entry for synthetic plans."""
    body = {"actions": actions, "before": before, "after": after, "after_unknown": {},
            "before_sensitive": {}, "after_sensitive": {}}
    body.update(change)
    return {"address": address, "mode": "managed", "type": rtype, "name": address.split(".")[-1],
            "index": None, "module_address": None, "provider_name": "registry.terraform.io/hashicorp/x",
            "change": body}


class TestAttributeChangesRealEvidence(unittest.TestCase):
    def test_no_relevant_attribute_changes(self):  # 1
        r = classify("in_sync")
        main = by_index(r)["main"]
        self.assertEqual(main["classification"], dd.IN_SYNC)
        self.assertEqual(main["attribute_changes"], [])

    def test_map_key_change_external_drift(self):  # 4
        main = by_index(classify("external_drift"))["main"]
        self.assertEqual(main["classification"], dd.EXTERNAL_DRIFT)
        changes = changes_by_path(main)
        self.assertEqual(list(changes), ["tags.probe"], "only the changed tag key, not the whole map")
        probe = changes["tags.probe"]
        self.assertEqual(probe["path"], ["tags", "probe"])
        self.assertEqual(probe["attribute"], "tags")
        self.assertEqual(probe["class"], dd.DRIFTED)
        self.assertEqual(value(probe["state"]), "1")
        self.assertEqual(probe["real"], {"status": "absent"})
        self.assertEqual(value(probe["desired"]), "1")
        self.assertFalse(probe["redacted"])

    def test_map_key_change_config_and_ambiguous_and_converged(self):  # 4
        expected = {
            "config_change": (dd.CONFIG_CHANGE, dd.CONFIG_CHANGED, "absent", "absent", "1"),
            "drift_and_config_change": (dd.DRIFT_AND_CONFIG_CHANGE, dd.DRIFTED_AND_CONFIG_CHANGED, "1", "absent", "2"),
            "converged_drift": (dd.CONVERGED_DRIFT, dd.DRIFTED_CONVERGED, "1", "absent", "absent"),
        }
        for name, (rcls, acls, s, r_, d) in expected.items():
            with self.subTest(name):
                main = by_index(classify(name))["main"]
                self.assertEqual(main["classification"], rcls)
                probe = changes_by_path(main)["tags.probe"]
                self.assertEqual(probe["class"], acls)
                for view, exp in (("state", s), ("real", r_), ("desired", d)):
                    got = probe[view]
                    self.assertEqual(got["status"] if exp == "absent" else got.get("value"), exp, view)

    def test_scalar_change_multiple_attributes_unknown_and_null(self):  # 2, 5, 9, 10
        main = by_index(classify("replace"))["main"]
        self.assertEqual((main["classification"], main["action"]), (dd.CONFIG_CHANGE, "replace"))
        changes = changes_by_path(main)
        self.assertEqual(sorted(changes), ["id", "location", "managed_by"])
        loc = changes["location"]  # scalar
        self.assertEqual((loc["class"], value(loc["state"]), value(loc["real"]), value(loc["desired"])),
                         (dd.CONFIG_CHANGED, "centralindia", "centralindia", "westeurope"))
        rid = changes["id"]  # unknown until apply: no value invented
        self.assertEqual(rid["class"], dd.UNKNOWN_UNTIL_APPLY)
        self.assertEqual(rid["desired"], {"status": "unknown"})
        mb = changes["managed_by"]  # null is a value, distinct from absent
        self.assertEqual(mb["desired"], {"status": "value", "value": None})
        self.assertEqual(value(mb["state"]), "")

    def test_resource_added(self):  # 11
        r = classify("resource_added")
        extra = by_index(r)["extra"]
        self.assertEqual(extra["classification"], dd.RESOURCE_ADDED)
        changes = changes_by_path(extra)
        self.assertIn("tags.environment", changes)
        for c in changes.values():
            self.assertIsNone(c["class"], "§6.2 does not apply to object-level create")
            self.assertEqual(c["state"], {"status": "absent"})
            self.assertEqual(c["real"], {"status": "absent"})
        self.assertEqual(value(changes["name"]["desired"]), "aitdd-dev-extra-rg")
        self.assertEqual(changes["id"]["desired"], {"status": "unknown"})
        self.assertEqual(by_index(r)["main"]["attribute_changes"], [])

    def test_resource_removed(self):  # 12
        main = by_index(classify("resource_removed"))["main"]
        self.assertEqual(main["classification"], dd.RESOURCE_REMOVED)
        changes = changes_by_path(main)
        self.assertEqual(value(changes["name"]["state"]), "aitdd-dev-main-rg")
        for c in changes.values():
            self.assertIsNone(c["class"])
            self.assertEqual(c["desired"], {"status": "absent"})

    def test_external_deletion_values(self):
        ghost = by_index(classify("external_deletion"))["ghost"]
        self.assertEqual(ghost["classification"], dd.EXTERNAL_DELETION)
        name = changes_by_path(ghost)["name"]
        self.assertEqual((value(name["state"]), name["real"]["status"], value(name["desired"])),
                         ("aitdd-dev-ghost-rg", "absent", "aitdd-dev-ghost-rg"))

    def test_multiple_resources_same_type(self):  # 6
        r = classify("resource_removed")
        self.assertEqual(r["resource_types"], [{
            "type": "azurerm_resource_group",
            "resource_count": 2,
            "addresses": [
                'module.resource_group.azurerm_resource_group.this["main"]',
                'module.resource_group.azurerm_resource_group.this["other"]',
            ],
            "classification_counts": {dd.RESOURCE_ADDED: 1, dd.RESOURCE_REMOVED: 1},
        }])

    def test_output_only_change_has_no_attribute_changes(self):  # 16
        r = classify("output_only_change")
        self.assertIs(r["has_drift"], False)
        self.assertTrue(r["summary"]["output_only_change"])
        for x in r["resources"]:
            self.assertEqual(x["classification"], dd.IN_SYNC)
            self.assertEqual(x["attribute_changes"], [])
        self.assertEqual(r["resource_types"][0]["classification_counts"], {dd.IN_SYNC: 1})

    def test_failed_run_has_no_enrichment(self):  # 15
        r = classify("failed_run")
        self.assertEqual((r["outcome"], r["has_drift"]), ("failed", None))
        self.assertEqual((r["resources"], r["resource_types"]), ([], []))

    def test_task33_contract_preserved(self):  # 13
        for name in sorted(os.listdir(FIXTURES)):
            with self.subTest(name):
                r = classify(name)
                self.assertEqual(set(r), TASK33_TOP_KEYS | {"resource_types"})
                for x in r["resources"]:
                    # Task 3.4 added attribute_changes; Task 6.2A added severity.
                    self.assertEqual(set(x), TASK33_RESOURCE_KEYS | {"attribute_changes", "severity"})
                    for a in x["attributes"]:
                        self.assertEqual(set(a), {"name", "class"})

    def test_task33_and_task34_agree_on_changed_attributes(self):  # 13
        for name in sorted(os.listdir(FIXTURES)):
            for x in classify(name)["resources"]:
                if x["attributes"]:  # object present in all three views
                    with self.subTest(f"{name}:{x['index']}"):
                        self.assertEqual({a["name"] for a in x["attributes"]},
                                         {c["attribute"] for c in x["attribute_changes"]})


class TestAttributeChangesSynthetic(unittest.TestCase):
    def test_nested_object_change(self):  # 3
        before = {"site_config": {"always_on": False, "tls": "1.2"}, "name": "app"}
        after = {"site_config": {"always_on": True, "tls": "1.2"}, "name": "app"}
        out = dd.classify_resource(None, res("x.app", "azurerm_linux_web_app", ["update"], before, after))
        self.assertEqual(out["classification"], dd.CONFIG_CHANGE)
        changes = changes_by_path(out)
        self.assertEqual(list(changes), ["site_config.always_on"])
        c = changes["site_config.always_on"]
        self.assertEqual((c["class"], value(c["state"]), value(c["desired"])), (dd.CONFIG_CHANGED, False, True))

    def test_multiple_resource_types_grouped(self):  # 7
        rg_a = res("rg.a", "azurerm_resource_group", ["update"], {"tags": {"env": "dev"}}, {"tags": {"env": "prd"}})
        rg_b = res("rg.b", "azurerm_resource_group", ["no-op"], {"tags": {}}, {"tags": {}})
        vnet_before = {"address_space": ["10.0.0.0/16"]}
        vnet_drift = res("vnet.c", "azurerm_virtual_network", ["update"], vnet_before, {"address_space": ["10.1.0.0/16"]})
        vnet_change = res("vnet.c", "azurerm_virtual_network", ["update"], {"address_space": ["10.1.0.0/16"]}, vnet_before)
        out = dd.classify_plan({"resource_changes": [vnet_change, rg_b, rg_a], "resource_drift": [vnet_drift]})
        self.assertEqual({x["address"]: x["classification"] for x in out["resources"]},
                         {"rg.a": dd.CONFIG_CHANGE, "rg.b": dd.IN_SYNC, "vnet.c": dd.EXTERNAL_DRIFT})
        self.assertEqual([(t["type"], t["addresses"], t["classification_counts"]) for t in out["resource_types"]], [
            ("azurerm_resource_group", ["rg.a", "rg.b"], {dd.CONFIG_CHANGE: 1, dd.IN_SYNC: 1}),
            ("azurerm_virtual_network", ["vnet.c"], {dd.EXTERNAL_DRIFT: 1}),
        ])
        space = changes_by_path(by_address(out)["vnet.c"])["address_space"]  # lists compared whole
        self.assertEqual((space["class"], value(space["real"])), (dd.DRIFTED, ["10.1.0.0/16"]))

    def test_sensitive_values_redacted(self):  # 8
        secrets = ("old-secret-value", "new-secret-value", "tag-secret-1", "tag-secret-2", "conn-a", "conn-b")
        before = {"admin_password": secrets[0], "tags": {"secret": secrets[2], "env": "dev"},
                  "conn": {"a": secrets[4]}, "same_secret": "unchanged-secret"}
        after = {"admin_password": secrets[1], "tags": {"secret": secrets[3], "env": "prd"},
                 "conn": {"a": secrets[5]}, "same_secret": "unchanged-secret"}
        mask = {"admin_password": True, "tags": {"secret": True}, "conn": True, "same_secret": True}
        out = dd.classify_resource(None, res("x.db", "azurerm_example", ["update"], before, after,
                                             before_sensitive=mask, after_sensitive=mask))
        self.assertEqual(out["classification"], dd.CONFIG_CHANGE)
        changes = changes_by_path(out)
        self.assertEqual(sorted(changes), ["admin_password", "conn", "tags.env", "tags.secret"],
                         "sensitive subtree reported once, unchanged sensitive value omitted")
        for path in ("admin_password", "conn", "tags.secret"):
            c = changes[path]
            self.assertTrue(c["redacted"])
            self.assertEqual(c["class"], dd.CONFIG_CHANGED)
            for view in ("state", "real", "desired"):
                self.assertEqual(c[view], {"status": "redacted"})
        self.assertFalse(changes["tags.env"]["redacted"])
        self.assertEqual(value(changes["tags.env"]["desired"]), "prd")
        dumped = json.dumps(out)
        for s in secrets + ("unchanged-secret",):
            self.assertNotIn(s, dumped)

    def test_sensitive_in_drift_mask_only_redacts_every_view(self):  # 8
        drift = res("x.k", "t", ["update"], {"key": "s1"}, {"key": "s2"}, after_sensitive={"key": True})
        change = res("x.k", "t", ["update"], {"key": "s2"}, {"key": "s1"})
        out = dd.classify_resource(drift, change)
        self.assertEqual(out["classification"], dd.EXTERNAL_DRIFT)
        c = changes_by_path(out)["key"]
        self.assertEqual((c["class"], c["redacted"]), (dd.DRIFTED, True))
        self.assertNotIn("s1", json.dumps(out["attribute_changes"]))
        self.assertNotIn("s2", json.dumps(out["attribute_changes"]))

    def test_nested_unknown_and_null_versus_absent(self):  # 9, 10
        before = {"cfg": {"a": 1, "b": None}, "opt": None}
        after = {"cfg": {"a": 1}, "opt": None}
        out = dd.classify_resource(None, res("x.u", "t", ["update"], before, after,
                                             after_unknown={"cfg": {"c": True}}))
        changes = changes_by_path(out)
        self.assertEqual(sorted(changes), ["cfg.b", "cfg.c"])
        self.assertEqual((changes["cfg.b"]["state"], changes["cfg.b"]["desired"]),
                         ({"status": "value", "value": None}, {"status": "absent"}))
        self.assertEqual(changes["cfg.c"]["class"], dd.UNKNOWN_UNTIL_APPLY)
        self.assertEqual(changes["cfg.c"]["desired"], {"status": "unknown"})
        self.assertEqual(out["attributes"], [{"name": "cfg", "class": dd.UNKNOWN_UNTIL_APPLY}],
                         "Task 3.3 top-level result unchanged")

    def test_empty_map_versus_absent_is_reported(self):
        out = dd.classify_resource(None, res("x.e", "t", ["update"], {"name": "n"}, {"name": "n", "tags": {}}))
        self.assertEqual(changes_by_path(out)["tags"]["desired"], {"status": "value", "value": {}})

    def test_invalid_evidence_has_no_enrichment(self):  # 14
        d = os.path.join(tempfile.mkdtemp(prefix="detect-drift-34-"), "bundle")
        try:
            shutil.copytree(os.path.join(FIXTURES, "external_drift"), d)
            with open(os.path.join(d, "plan.json"), "w") as fh:
                fh.write('{"truncated": ')
            r = dd.classify_bundle(d)
            self.assertEqual((r["outcome"], r["has_drift"], r["resources"], r["resource_types"]),
                             ("failed", None, [], []))
        finally:
            shutil.rmtree(os.path.dirname(d), ignore_errors=True)

    def test_attribute_changes_deterministic(self):
        plan_path = os.path.join(FIXTURES, "resource_removed", "plan.json")
        with open(plan_path) as fh:
            plan = json.load(fh)
        first = json.dumps(dd.classify_plan(plan), sort_keys=True)
        plan["resource_changes"].reverse()
        self.assertEqual(first, json.dumps(dd.classify_plan(plan), sort_keys=True))


def by_address(result: dict) -> dict:
    return {r["address"]: r for r in result["resources"]}


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
