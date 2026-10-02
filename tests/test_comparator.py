"""Tests for src/drift_engine/comparator.py (Task 4.4).

Run from the repository root:
    pytest tests/test_comparator.py
    python3 -m unittest tests.test_comparator    (no installation needed)

Real plans come from tests/fixtures/plan_evidence/. The MVP only manages a resource
group, so the network, NSG and Key Vault cases are synthetic plans shaped like
`terraform show -json` output (resource_drift + resource_changes + configuration).
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from drift_engine import comparator as c  # noqa: E402
from drift_engine import parser  # noqa: E402

FIXTURE_SOURCE = os.path.join(ROOT, "tests", "fixtures", "plan_evidence")
RG_CONFIG = "module.resource_group.azurerm_resource_group.this"

_spec = importlib.util.spec_from_file_location("detect_drift", os.path.join(ROOT, "scripts", "detect_drift.py"))
dd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dd)


def fixture_plan(name: str) -> dict:
    with open(os.path.join(FIXTURE_SOURCE, name, "plan.sanitized.json"), encoding="utf-8") as fh:
        return json.load(fh)


def fixture_names() -> list[str]:
    return sorted(
        n for n in os.listdir(FIXTURE_SOURCE)
        if os.path.exists(os.path.join(FIXTURE_SOURCE, n, "plan.sanitized.json"))
    )


def compare_fixture(name: str) -> dict[str, c.ResourceComparison]:
    plan = fixture_plan(name)
    result = c.compare_plan(parser.parse_plan(plan), c.configured_attributes(plan))
    return {r.address.rsplit("[", 1)[1].strip('"]'): r for r in result}


def by_path(comparison: c.ResourceComparison) -> dict[str, c.ChangeAssessment]:
    return {".".join(a.change["path"]): a for a in comparison.changes}


# ---------------------------------------------------------------------------
# Synthetic Azure plans
# ---------------------------------------------------------------------------

def azure_plan(rtype: str, state: dict, real: dict, desired: dict, configured: list[str],
               actions=("update",), name: str = "this", module: str | None = None) -> dict:
    """One managed resource with drift (S -> R) and a planned change (R -> D)."""
    local = f"{rtype}.{name}"
    address = f"module.{module}.{local}" if module else local
    entry = {"address": address, "mode": "managed", "type": rtype, "name": name,
             "provider_name": "registry.terraform.io/hashicorp/azurerm"}
    drift = dict(entry, change={"actions": ["update"], "before": state, "after": real,
                                "before_sensitive": {}, "after_sensitive": {}})
    change = dict(entry, change={"actions": list(actions), "before": real, "after": desired,
                                 "after_unknown": {}, "before_sensitive": {}, "after_sensitive": {}})
    resources = [{"address": local, "mode": "managed", "type": rtype, "name": name,
                  "expressions": {k: {"constant_value": None} for k in configured}}]
    root = {"resources": resources}
    if module:
        root = {"module_calls": {module: {"module": {"resources": resources}}}}
    plan = {"format_version": "1.2", "terraform_version": "1.14.7", "errored": False, "complete": True,
            "resource_changes": [change], "configuration": {"root_module": root}}
    if state != real:
        plan["resource_drift"] = [drift]
    return plan


def compare_one(plan: dict) -> c.ResourceComparison:
    (result,) = c.compare_plan(parser.parse_plan(plan), c.configured_attributes(plan))
    return result


STORAGE_STATE = {
    "id": "/subscriptions/<AZURE_SUBSCRIPTION_ID>/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/sa",
    "name": "sa",
    "network_rules": [{"default_action": "Deny", "ip_rules": ["203.0.113.10"], "bypass": ["AzureServices"]}],
    "public_network_access_enabled": False,
    "tags": {"environment": "dev"},
    "timeouts": None,
}


# ---------------------------------------------------------------------------
# Migrated diff: identical to what the classifier reports
# ---------------------------------------------------------------------------

class TestMigratedDiff(unittest.TestCase):
    def test_classifier_uses_the_comparator(self):
        self.assertIs(dd.attribute_changes, c.attribute_changes)
        self.assertIs(dd.classify_attributes, c.classify_attributes)
        self.assertEqual(dd.DRIFTED, c.DRIFTED)

    def test_changes_match_classifier_output_for_every_fixture(self):
        for name in fixture_names():
            with self.subTest(name):
                plan = fixture_plan(name)
                report = {r["address"]: r for r in dd.classify_plan(plan)["resources"]}
                for comparison in c.compare_plan(parser.parse_plan(plan), c.configured_attributes(plan)):
                    self.assertEqual(
                        [a.change for a in comparison.changes],
                        report[comparison.address]["attribute_changes"],
                    )

    def test_nested_map_key_drift(self):
        out = c.attribute_changes({"tags": {"a": "1"}}, {"tags": {"a": "1", "b": "2"}}, {"tags": {"a": "1"}}, {}, [])
        self.assertEqual([x["path"] for x in out], [["tags", "b"]])
        self.assertEqual(out[0]["class"], c.DRIFTED)

    def test_lists_compared_whole(self):
        out = c.attribute_changes({"l": [1, 2]}, {"l": [2, 1]}, {"l": [1, 2]}, {}, [])
        self.assertEqual([x["path"] for x in out], [["l"]])

    def test_null_versus_absent(self):
        out = c.attribute_changes({"a": None}, {}, {"a": None}, {}, [])
        self.assertEqual(out[0]["real"], {"status": "absent"})
        self.assertEqual(out[0]["state"], {"status": "value", "value": None})

    def test_unknown_desired(self):
        out = c.attribute_changes({"a": 1}, {"a": 1}, {}, {"a": True}, [])
        self.assertEqual((out[0]["class"], out[0]["desired"]), (c.UNKNOWN_UNTIL_APPLY, {"status": "unknown"}))

    def test_sensitive_redacted(self):
        out = c.attribute_changes({"k": "old"}, {"k": "new"}, {"k": "old"}, {}, [{"k": True}])
        self.assertTrue(out[0]["redacted"])
        self.assertNotIn("old", json.dumps(out))
        self.assertNotIn("new", json.dumps(out))

    def test_create_has_no_attribute_class(self):
        out = c.attribute_changes(None, None, {"a": 1}, {}, [])
        self.assertEqual(out[0]["class"], None)


# ---------------------------------------------------------------------------
# Configuration evidence
# ---------------------------------------------------------------------------

class TestConfiguredAttributes(unittest.TestCase):
    def test_real_plan(self):
        self.assertEqual(
            c.configured_attributes(fixture_plan("external_drift")),
            {RG_CONFIG: frozenset({"location", "name", "tags"})},
        )

    def test_nested_modules_and_root_resources(self):
        plan = {"configuration": {"root_module": {
            "resources": [{"address": "azurerm_x.a", "expressions": {"p": {}}}],
            "module_calls": {"outer": {"module": {
                "resources": [{"address": "azurerm_y.b", "expressions": {"q": {}}}],
                "module_calls": {"inner": {"module": {"resources": [{"address": "azurerm_z.c"}]}}},
            }}},
        }}}
        self.assertEqual(c.configured_attributes(plan), {
            "azurerm_x.a": frozenset({"p"}),
            "module.outer.azurerm_y.b": frozenset({"q"}),
            "module.outer.module.inner.azurerm_z.c": frozenset(),
        })

    def test_missing_or_malformed_configuration(self):
        for plan in ({}, {"configuration": None}, {"configuration": {"root_module": []}},
                     {"configuration": {"root_module": {"resources": [5, {"address": 1}, None]}}},
                     {"configuration": {"root_module": {"resources": True}}},
                     {"configuration": {"root_module": {"resources": 1.5, "module_calls": []}}},
                     {"configuration": {"root_module": {"module_calls": {"m": None, "n": {"module": 3}}}}},
                     [], None):
            with self.subTest(plan=plan):
                self.assertEqual(c.configured_attributes(plan), {})

    def test_config_address(self):
        cases = {
            'module.resource_group.azurerm_resource_group.this["main"]': RG_CONFIG,
            "azurerm_x.y[0]": "azurerm_x.y",
            'module.a["k"].module.b[2].azurerm_x.y["v"]': "module.a.module.b.azurerm_x.y",
            'azurerm_x.y["a.b[c]"]': "azurerm_x.y",
            'azurerm_x.y["quote\\"]x"]': "azurerm_x.y",
            "data.azurerm_client_config.current": "data.azurerm_client_config.current",
            "azurerm_x.y": "azurerm_x.y",
        }
        for address, expected in cases.items():
            with self.subTest(address):
                self.assertEqual(c.config_address(address), expected)


# ---------------------------------------------------------------------------
# Acceptance: user-configured drift isolated
# ---------------------------------------------------------------------------

class TestUserConfiguredDrift(unittest.TestCase):
    def test_real_tag_drift(self):
        main = compare_fixture("external_drift")["main"]
        (change,) = main.configured_drift
        self.assertEqual(change.change["path"], ["tags", "probe"])
        self.assertEqual(change.category, c.CONFIGURED)
        self.assertEqual(main.noise, ())

    def test_ip_allow_list_drift(self):
        real = copy.deepcopy(STORAGE_STATE)
        real["network_rules"][0]["ip_rules"] = ["203.0.113.10", "198.51.100.7"]
        r = compare_one(azure_plan("azurerm_storage_account", STORAGE_STATE, real, STORAGE_STATE,
                                   ["name", "network_rules", "public_network_access_enabled", "tags"]))
        (change,) = r.configured_drift
        self.assertEqual(change.change["path"], ["network_rules"])  # list of blocks: compared whole
        self.assertEqual(change.change["class"], c.DRIFTED)

    def test_nsg_inbound_rule_drift(self):
        rule = {"name": "ssh", "direction": "Inbound", "access": "Deny", "source_address_prefix": "10.0.0.0/8"}
        state = {"id": "/x/nsg", "name": "nsg", "security_rule": [rule]}
        real = {"id": "/x/nsg", "name": "nsg", "security_rule": [dict(rule, access="Allow", source_address_prefix="*")]}
        r = compare_one(azure_plan("azurerm_network_security_group", state, real, state, ["name", "security_rule"]))
        self.assertEqual([a.change["path"] for a in r.configured_drift], [["security_rule"]])

    def test_security_setting_drift(self):
        real = dict(STORAGE_STATE, public_network_access_enabled=True)
        r = compare_one(azure_plan("azurerm_storage_account", STORAGE_STATE, real, STORAGE_STATE,
                                   ["name", "public_network_access_enabled"]))
        self.assertEqual([a.change["path"] for a in r.configured_drift], [["public_network_access_enabled"]])

    def test_unconfigured_security_setting_is_kept_significant(self):
        # Left at the provider default, changed in Azure: real drift Terraform will revert.
        state = {"id": "/x/kv", "name": "kv", "public_network_access_enabled": False}
        real = dict(state, public_network_access_enabled=True)
        r = compare_one(azure_plan("azurerm_key_vault", state, real, state, ["name"]))
        (change,) = r.changes
        self.assertEqual(change.category, c.UNCONFIGURED)
        self.assertTrue(change.significant)
        self.assertTrue(change.is_drift)
        self.assertEqual(r.configured_drift, ())

    def test_configured_drift_excludes_config_changes(self):
        main = compare_fixture("config_change")["main"]
        self.assertEqual(main.configured_drift, ())
        self.assertEqual(len(main.significant), 1)  # still reported, as a configuration change

    def test_converged_and_ambiguous_drift_count_as_drift(self):
        for name in ("converged_drift", "drift_and_config_change"):
            with self.subTest(name):
                self.assertEqual(len(compare_fixture(name)["main"].configured_drift), 1)


# ---------------------------------------------------------------------------
# Acceptance: noise filtered
# ---------------------------------------------------------------------------

class TestNoise(unittest.TestCase):
    def test_noise_mixed_with_real_drift(self):
        state = dict(STORAGE_STATE, etag="0x1", creation_time="2026-01-01T00:00:00Z",
                     last_modified_time="2026-01-01T00:00:00Z", provisioning_state="Succeeded")
        real = dict(state, id=state["id"] + "2", etag="0x2", last_modified_time="2026-10-02T00:00:00Z",
                    provisioning_state="Updating", tags={"environment": "prod"})
        r = compare_one(azure_plan("azurerm_storage_account", state, real, state, ["name", "tags"]))
        paths = by_path(r)
        self.assertEqual({p for p, a in paths.items() if a.category == c.NOISE},
                         {"id", "etag", "last_modified_time", "provisioning_state"})
        self.assertEqual(paths["id"].rule, "computed-id")
        self.assertEqual(paths["etag"].rule, "read-only-metadata")
        self.assertEqual(paths["last_modified_time"].rule, "timestamps")
        self.assertEqual([a.change["path"] for a in r.significant], [["tags", "environment"]])
        self.assertEqual([a.change["path"] for a in r.configured_drift], [["tags", "environment"]])

    def test_real_replace_quirk_is_noise(self):
        paths = by_path(compare_fixture("replace")["main"])
        self.assertEqual(paths["managed_by"].category, c.NOISE)
        self.assertEqual(paths["managed_by"].rule, "replace-unset-optional")
        self.assertEqual(paths["id"].rule, "computed-id")  # unknown until apply on the new object
        self.assertEqual(paths["location"].category, c.CONFIGURED)
        self.assertEqual([".".join(a.change["path"]) for a in compare_fixture("replace")["main"].significant],
                         ["location"])

    def test_real_create_noise(self):
        extra = by_path(compare_fixture("resource_added")["extra"])
        self.assertEqual(extra["id"].category, c.NOISE)
        self.assertEqual(extra["timeouts"].rule, "timeouts")
        self.assertEqual(extra["managed_by"].category, c.UNCONFIGURED)  # not a replace: kept
        self.assertEqual(extra["tags.project"].category, c.CONFIGURED)

    def test_replace_rule_needs_replace_and_unset_desired(self):
        state = {"id": "/x", "managed_by": "team"}
        update = compare_one(azure_plan("azurerm_resource_group", state, state, dict(state, managed_by=None), []))
        self.assertEqual(by_path(update)["managed_by"].category, c.UNCONFIGURED)
        replace_set = compare_one(azure_plan("azurerm_resource_group", state, state, dict(state, managed_by="x"),
                                             [], actions=("delete", "create")))
        self.assertEqual(by_path(replace_set)["managed_by"].category, c.UNCONFIGURED)

    def test_configuration_wins_over_noise_rule(self):
        state = {"id": "/x", "timeouts": {"create": "30m"}}
        real = {"id": "/x", "timeouts": {"create": "60m"}}
        r = compare_one(azure_plan("azurerm_x", state, real, state, ["timeouts"]))
        (change,) = r.changes
        self.assertEqual(change.category, c.CONFIGURED)
        self.assertEqual(change.rule, "timeouts")  # recorded, not applied
        self.assertTrue(change.significant)

    def test_no_configuration_evidence_is_undetermined(self):
        plan = azure_plan("azurerm_x", {"id": "/a", "p": 1}, {"id": "/b", "p": 2}, {"id": "/a", "p": 1}, ["p"])
        del plan["configuration"]
        r = compare_one(plan)
        self.assertEqual({a.category for a in r.changes}, {c.UNDETERMINED})
        self.assertEqual(by_path(r)["id"].rule, "computed-id")
        self.assertEqual(len(r.significant), 2)  # nothing hidden without proof

    def test_resource_missing_from_configuration(self):
        plan = azure_plan("azurerm_x", {"id": "/a", "p": 1}, {"id": "/a", "p": 2}, {"id": "/a", "p": 1}, ["p"])
        plan["configuration"]["root_module"]["resources"][0]["address"] = "azurerm_x.other"
        self.assertEqual({a.category for a in compare_one(plan).changes}, {c.UNDETERMINED})

    def test_resource_removed_from_configuration(self):
        state = {"id": "/a", "p": 1}
        plan = azure_plan("azurerm_x", state, state, None, [], actions=("delete",))
        plan["configuration"]["root_module"]["resources"][0]["address"] = "azurerm_x.other"
        cats = by_path(compare_one(plan))
        self.assertEqual((cats["id"].category, cats["p"].category), (c.NOISE, c.UNCONFIGURED))

    def test_custom_rules(self):
        rule = c.NoiseRule("sku-casing", "test", (("sku", "*"),), resource_types=("azurerm_storage_*",))
        state = {"sku": {"tier": "Standard"}}
        real = {"sku": {"tier": "standard"}}
        plan = azure_plan("azurerm_storage_account", state, real, state, [])
        parsed, cfg = parser.parse_plan(plan), c.configured_attributes(plan)
        (r,) = c.compare_plan(parsed, cfg, rules=(rule,))
        self.assertEqual(r.changes[0].rule, "sku-casing")
        (other,) = c.compare_plan(parser.parse_plan(azure_plan("azurerm_key_vault", state, real, state, [])), cfg,
                                  rules=(rule,))
        self.assertIsNone(other.changes[0].rule)
        (none,) = c.compare_plan(parsed, cfg, rules=())
        self.assertEqual(none.changes[0].category, c.UNCONFIGURED)

    def test_rule_path_is_a_prefix_match(self):
        rule = c.NoiseRule("t", "test", (("a", "b"),))
        def change(path):
            return {"path": path, "desired": {"status": "absent"}}
        self.assertTrue(rule.matches("x", "update", change(["a", "b"])))
        self.assertTrue(rule.matches("x", "update", change(["a", "b", "c"])))
        self.assertFalse(rule.matches("x", "update", change(["a"])))
        self.assertFalse(rule.matches("x", "update", change(["a", "bb"])))

    def test_tags_never_noise(self):
        for path in (["tags"], ["tags", "created_at"], ["tags", "etag"]):
            ch = {"path": path, "attribute": "tags", "class": c.DRIFTED, "desired": {"status": "absent"}}
            with self.subTest(path=path):
                self.assertIsNone(next((r.id for r in c.NOISE_RULES if r.matches("azurerm_x", "update", ch)), None))


# ---------------------------------------------------------------------------
# Nothing hidden, nothing altered
# ---------------------------------------------------------------------------

class TestAnnotationOnly(unittest.TestCase):
    def test_every_change_kept_and_partitioned(self):
        for name in fixture_names():
            for r in compare_fixture(name).values():
                with self.subTest(name=name, address=r.address):
                    self.assertEqual(len(r.significant) + len(r.noise), len(r.changes))
                    self.assertEqual(set(map(id, r.significant)) | set(map(id, r.noise)), set(map(id, r.changes)))

    def test_every_resource_kept(self):
        for name in fixture_names():
            with self.subTest(name):
                plan = fixture_plan(name)
                parsed = parser.parse_plan(plan)
                result = c.compare_plan(parsed, c.configured_attributes(plan))
                self.assertEqual([r.address for r in result], [e.address for e in parsed.resources])

    def test_classification_unchanged_by_comparison(self):
        for name in fixture_names():
            with self.subTest(name):
                plan = fixture_plan(name)
                before = json.dumps(dd.classify_plan(plan), sort_keys=True)
                c.compare_plan(parser.parse_plan(plan), c.configured_attributes(plan))
                self.assertEqual(json.dumps(dd.classify_plan(plan), sort_keys=True), before)

    def test_redacted_change_stays_redacted(self):
        plan = fixture_plan("external_drift")
        for e in plan["resource_drift"] + plan["resource_changes"]:
            e["change"]["after_sensitive"] = {"tags": {"probe": True}}
        (r,) = c.compare_plan(parser.parse_plan(plan), c.configured_attributes(plan))
        (change,) = r.changes
        self.assertTrue(change.change["redacted"])
        self.assertEqual(change.category, c.CONFIGURED)

    def test_deterministic(self):
        plan = fixture_plan("external_deletion")
        first = c.compare_plan(parser.parse_plan(plan), c.configured_attributes(plan))
        second = c.compare_plan(parser.parse_plan(copy.deepcopy(plan)), c.configured_attributes(copy.deepcopy(plan)))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
