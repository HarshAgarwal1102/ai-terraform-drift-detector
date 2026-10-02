"""Tests for src/drift_engine/severity.py (Task 4.5).

Run from the repository root:
    pytest tests/test_severity.py
    python3 -m unittest tests.test_severity    (no installation needed)

Real plans come from tests/fixtures/plan_evidence/ (resource group only). Key Vault,
NSG and storage cases are synthetic plans shaped like `terraform show -json` output.
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
from drift_engine import severity as sv  # noqa: E402

FIXTURE_SOURCE = os.path.join(ROOT, "tests", "fixtures", "plan_evidence")

_spec = importlib.util.spec_from_file_location("detect_drift", os.path.join(ROOT, "scripts", "detect_drift.py"))
dd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dd)


def fixture_names() -> list[str]:
    return sorted(
        n for n in os.listdir(FIXTURE_SOURCE)
        if os.path.exists(os.path.join(FIXTURE_SOURCE, n, "plan.sanitized.json"))
    )


def rate_plan(plan: dict, rules=sv.SEVERITY_RULES) -> dict[str, sv.ResourceSeverity]:
    """Parse, compare, classify and rate, the way a caller combines Tasks 4.2-4.5."""
    parsed = parser.parse_plan(plan)
    comparisons = c.compare_plan(parsed, c.configured_attributes(plan))
    classes = {r["address"]: r["classification"] for r in dd.classify_plan(plan)["resources"]}
    return {r.address: r for r in sv.plan_severity(parsed, comparisons, classes, rules)}


def rate_fixture(name: str) -> dict[str, sv.ResourceSeverity]:
    with open(os.path.join(FIXTURE_SOURCE, name, "plan.sanitized.json"), encoding="utf-8") as fh:
        plan = json.load(fh)
    return {a.rsplit("[", 1)[1].strip('"]'): r for a, r in rate_plan(plan).items()}


def azure_plan(rtype: str, state, real, desired, configured=None, actions=("update",),
               sensitive=None, after_unknown=None) -> dict:
    """One managed resource; drift S -> R when they differ, planned change R -> D."""
    entry = {"address": f"{rtype}.this", "mode": "managed", "type": rtype, "name": "this"}
    mask = sensitive or {}
    plan = {
        "format_version": "1.2", "terraform_version": "1.14.7", "errored": False, "complete": True,
        "resource_changes": [dict(entry, change={
            "actions": list(actions), "before": real, "after": desired, "after_unknown": after_unknown or {},
            "before_sensitive": mask, "after_sensitive": mask})],
        "configuration": {"root_module": {"resources": [{
            "address": f"{rtype}.this", "mode": "managed", "type": rtype, "name": "this",
            "expressions": {k: {} for k in (configured if configured is not None else [])}}]}},
    }
    if state != real:
        plan["resource_drift"] = [dict(entry, change={
            "actions": ["delete"] if real is None else ["update"], "before": state, "after": real,
            "before_sensitive": mask, "after_sensitive": mask})]
    return plan


def rate_one(*args, **kwargs) -> sv.ResourceSeverity:
    (result,) = rate_plan(azure_plan(*args, **kwargs)).values()
    return result


def drift(rtype: str, state: dict, **real_changes) -> sv.ResourceSeverity:
    """External change to `real_changes`; configuration declares every attribute of `state`."""
    real = dict(state, **real_changes)
    return rate_one(rtype, state, real, state, configured=list(state))


def by_path(result: sv.ResourceSeverity) -> dict[str, sv.ChangeSeverity]:
    return {".".join(ch.path): ch for ch in result.changes}


KV = {"id": "/kv", "name": "kv", "tenant_id": "t",
      "access_policy": [{"object_id": "o1", "secret_permissions": ["Get"]}],
      "network_acls": [{"default_action": "Deny", "bypass": "AzureServices", "ip_rules": []}],
      "public_network_access_enabled": False, "purge_protection_enabled": True,
      "tags": {"env": "dev"}}
RULE = {"name": "ssh", "priority": 100, "direction": "Inbound", "access": "Allow", "protocol": "Tcp",
        "source_address_prefix": "10.0.0.0/8", "destination_port_range": "22"}
NSG = {"id": "/nsg", "name": "nsg", "security_rule": [RULE], "tags": {}}
SA = {"id": "/sa", "name": "sa", "public_network_access_enabled": False, "allow_nested_items_to_be_public": False,
      "network_rules": [{"default_action": "Deny", "ip_rules": ["203.0.113.10"]}], "min_tls_version": "TLS1_2",
      "tags": {"env": "dev"}, "description": None}


# ---------------------------------------------------------------------------
# Acceptance 1: security-sensitive changes are CRITICAL / HIGH
# ---------------------------------------------------------------------------

class TestKeyVault(unittest.TestCase):
    def test_access_policy_drift_is_critical(self):
        r = drift("azurerm_key_vault", KV, access_policy=[{"object_id": "o2", "secret_permissions": ["Get", "List"]}])
        self.assertEqual(r.severity, sv.CRITICAL)
        self.assertEqual(by_path(r)["access_policy"].rules, ("key-vault-access-policy",))

    def test_standalone_access_policy_is_critical(self):
        state = {"id": "/p", "key_vault_id": "/kv", "object_id": "o1", "secret_permissions": ["Get"]}
        self.assertEqual(drift("azurerm_key_vault_access_policy", state, secret_permissions=["Get", "Set"]).severity,
                         sv.CRITICAL)

    def test_public_access(self):
        self.assertEqual(drift("azurerm_key_vault", KV, public_network_access_enabled=True).severity, sv.CRITICAL)
        disabled = dict(KV, public_network_access_enabled=True)
        # Turned off outside Terraform, but the configuration wants it on: still CRITICAL (desired value)
        self.assertEqual(drift("azurerm_key_vault", disabled, public_network_access_enabled=False).severity,
                         sv.CRITICAL)

    def test_network_acls(self):
        self.assertEqual(drift("azurerm_key_vault", KV, network_acls=[dict(KV["network_acls"][0], ip_rules=["1.2.3.4"])])
                         .severity, sv.HIGH)
        self.assertEqual(drift("azurerm_key_vault", KV, network_acls=[dict(KV["network_acls"][0], default_action="Allow")])
                         .severity, sv.CRITICAL)

    def test_purge_protection(self):
        self.assertEqual(drift("azurerm_key_vault", KV, purge_protection_enabled=False).severity, sv.HIGH)


class TestNetworkSecurityGroup(unittest.TestCase):
    def nsg(self, **rule_changes) -> sv.ResourceSeverity:
        return drift("azurerm_network_security_group", NSG, security_rule=[dict(RULE, **rule_changes)])

    def test_inbound_rule_change_is_high(self):
        self.assertEqual(self.nsg(destination_port_range="22-23").severity, sv.HIGH)

    def test_inbound_allow_from_any_source_is_critical(self):
        for source in ("*", "Internet", "0.0.0.0/0", "Any", " internet "):
            with self.subTest(source=source):
                r = self.nsg(source_address_prefix=source)
                self.assertEqual(r.severity, sv.CRITICAL)
                self.assertEqual(by_path(r)["security_rule"].rules, ("nsg-security-rule",))

    def test_source_prefixes_list(self):
        self.assertEqual(self.nsg(source_address_prefix=None, source_address_prefixes=["10.0.0.1", "*"]).severity,
                         sv.CRITICAL)

    def test_open_but_not_inbound_allow_is_high(self):
        self.assertEqual(self.nsg(source_address_prefix="*", access="Deny").severity, sv.HIGH)
        self.assertEqual(self.nsg(source_address_prefix="*", direction="Outbound").severity, sv.HIGH)

    def test_standalone_rule(self):
        state = dict(RULE, id="/r", network_security_group_name="nsg")
        self.assertEqual(drift("azurerm_network_security_rule", state, destination_port_range="3389").severity, sv.HIGH)
        self.assertEqual(drift("azurerm_network_security_rule", state, source_address_prefix="*").severity,
                         sv.CRITICAL)
        outbound = dict(state, direction="Outbound")
        self.assertEqual(drift("azurerm_network_security_rule", outbound, source_address_prefix="*").severity,
                         sv.HIGH)


class TestStorage(unittest.TestCase):
    def test_public_network_access(self):
        self.assertEqual(drift("azurerm_storage_account", SA, public_network_access_enabled=True).severity, sv.CRITICAL)

    def test_public_blob_access(self):
        self.assertEqual(drift("azurerm_storage_account", SA, allow_nested_items_to_be_public=True).severity,
                         sv.CRITICAL)

    def test_ip_allow_list(self):
        rules = [dict(SA["network_rules"][0], ip_rules=["203.0.113.10", "198.51.100.0/24"])]
        self.assertEqual(drift("azurerm_storage_account", SA, network_rules=rules).severity, sv.HIGH)
        opened = [dict(SA["network_rules"][0], default_action="Allow")]
        self.assertEqual(drift("azurerm_storage_account", SA, network_rules=opened).severity, sv.CRITICAL)

    def test_tls(self):
        self.assertEqual(drift("azurerm_storage_account", SA, min_tls_version="TLS1_0").severity, sv.HIGH)

    def test_container_access(self):
        state = {"id": "/c", "name": "c", "container_access_type": "private"}
        self.assertEqual(drift("azurerm_storage_container", state, container_access_type="blob").severity, sv.CRITICAL)
        state = dict(state, container_access_type="blob")
        # Made private outside Terraform; configuration still says blob -> desired is public
        self.assertEqual(drift("azurerm_storage_container", state, container_access_type="private").severity,
                         sv.CRITICAL)

    def test_standalone_network_rules(self):
        state = {"id": "/n", "storage_account_id": "/sa", "default_action": "Deny", "ip_rules": []}
        self.assertEqual(drift("azurerm_storage_account_network_rules", state, ip_rules=["1.2.3.4"]).severity, sv.HIGH)
        self.assertEqual(drift("azurerm_storage_account_network_rules", state, default_action="Allow").severity,
                         sv.CRITICAL)


class TestSecurityNotDowngraded(unittest.TestCase):
    def test_unconfigured_security_setting_keeps_rating(self):
        # public access left at the provider default, then enabled in Azure
        r = rate_one("azurerm_storage_account", SA, dict(SA, public_network_access_enabled=True), SA, configured=["name"])
        change = by_path(r)["public_network_access_enabled"]
        self.assertEqual(change.assessment.category, c.UNCONFIGURED)
        self.assertEqual(change.severity, sv.CRITICAL)

    def test_without_configuration_evidence(self):
        plan = azure_plan("azurerm_key_vault", KV, dict(KV, access_policy=[]), KV, configured=list(KV))
        del plan["configuration"]
        (r,) = rate_plan(plan).values()
        self.assertEqual(by_path(r)["access_policy"].assessment.category, c.UNDETERMINED)
        self.assertEqual(r.severity, sv.CRITICAL)

    def test_external_deletion_of_security_resource_is_critical(self):
        r = rate_one("azurerm_network_security_group", NSG, None, NSG, configured=list(NSG), actions=("create",))
        self.assertEqual(r.classification, "external_deletion")
        self.assertEqual(r.severity, sv.CRITICAL)
        self.assertIn("security-sensitive resource deleted outside Terraform", r.reasons)

    def test_planned_open_inbound_rule_is_critical(self):
        r = rate_one("azurerm_network_security_group", None, None, dict(NSG, security_rule=[dict(RULE, source_address_prefix="*")]),
                     configured=list(NSG), actions=("create",))
        self.assertEqual(r.classification, "resource_added")
        self.assertEqual(r.severity, sv.CRITICAL)
        self.assertFalse(by_path(r)["security_rule"].is_drift)


# ---------------------------------------------------------------------------
# Acceptance 2: tag / description changes are LOW / INFO
# ---------------------------------------------------------------------------

class TestLowAndInfo(unittest.TestCase):
    def test_real_tag_changes_are_low(self):
        for name in ("external_drift", "converged_drift", "drift_and_config_change", "config_change"):
            with self.subTest(name):
                main = rate_fixture(name)["main"]
                self.assertEqual(main.severity, sv.LOW)
                self.assertEqual([ch.rules for ch in main.changes], [("tags",)])

    def test_tags_on_security_resource_are_low(self):
        r = drift("azurerm_key_vault", KV, tags={"env": "prod"})
        self.assertEqual(r.severity, sv.LOW)

    def test_tags_and_access_policy_together(self):
        r = drift("azurerm_key_vault", KV, tags={"env": "prod"}, access_policy=[])
        self.assertEqual(r.severity, sv.CRITICAL)
        paths = by_path(r)
        self.assertEqual((paths["tags.env"].severity, paths["access_policy"].severity), (sv.LOW, sv.CRITICAL))
        self.assertEqual(r.reasons, ("access_policy: key-vault-access-policy",))

    def test_description_is_low(self):
        self.assertEqual(drift("azurerm_storage_account", SA, description="changed").severity, sv.LOW)

    def test_noise_is_info(self):
        state = dict(SA, etag="0x1")
        r = drift("azurerm_storage_account", state, etag="0x2")
        r2 = rate_one("azurerm_storage_account", state, dict(state, etag="0x2", id="/sa2"), state, configured=["name"])
        self.assertEqual(r.severity, sv.MEDIUM)  # etag declared in configuration: not noise, no rule -> default
        self.assertEqual(r2.severity, sv.INFO)
        self.assertEqual({ch.severity for ch in r2.changes}, {sv.INFO})
        self.assertEqual(r2.reasons, ())

    def test_in_sync_is_info(self):
        for name in ("in_sync", "output_only_change"):
            with self.subTest(name):
                main = rate_fixture(name)["main"]
                self.assertEqual((main.severity, main.changes, main.reasons), (sv.INFO, (), ()))


# ---------------------------------------------------------------------------
# Defaults, floors and edge cases
# ---------------------------------------------------------------------------

class TestDefaultsAndFloors(unittest.TestCase):
    def test_unmatched_change_defaults_to_medium(self):
        r = drift("azurerm_storage_account", SA, account_tier="Premium")
        self.assertEqual(r.severity, sv.MEDIUM)
        self.assertEqual(r.reasons, ("account_tier: no rule matched (default MEDIUM)",))

    def test_real_replace_is_high(self):
        main = rate_fixture("replace")["main"]
        self.assertEqual(main.severity, sv.HIGH)
        self.assertIn("planned replace destroys and recreates the object", main.reasons)
        paths = by_path(main)
        self.assertEqual((paths["id"].severity, paths["managed_by"].severity), (sv.INFO, sv.INFO))  # noise
        self.assertEqual(paths["location"].severity, sv.MEDIUM)

    def test_real_external_deletion_is_high(self):
        result = rate_fixture("external_deletion")
        self.assertEqual(result["ghost"].severity, sv.HIGH)
        self.assertIn("resource deleted outside Terraform", result["ghost"].reasons)
        self.assertEqual(result["main"].severity, sv.INFO)

    def test_real_create_and_delete(self):
        for name, key in (("resource_added", "extra"), ("resource_removed", "main")):
            with self.subTest(name):
                r = rate_fixture(name)[key]
                self.assertEqual(r.severity, sv.MEDIUM)
                self.assertEqual(by_path(r)["id"].severity, sv.INFO)
                self.assertEqual(by_path(r)["tags.project"].severity, sv.LOW)

    def test_undetermined_floor(self):
        comparison = c.ResourceComparison("a.b", "azurerm_x", "update", ())
        self.assertEqual(sv.resource_severity(comparison, classification="undetermined").severity, sv.MEDIUM)
        self.assertEqual(sv.resource_severity(comparison).severity, sv.INFO)  # no classification, no floor

    def test_resource_type_of_any_shape(self):
        # ResourceEvidence.type is passed through from plan.json unchecked (Task 4.2 contract)
        for rtype in (None, 5, ["azurerm_key_vault"], {"t": 1}):
            with self.subTest(rtype=rtype):
                self.assertEqual(sv.resource_floor("external_deletion", None, rtype)[0], sv.HIGH)
                comparison = c.ResourceComparison("a.b", rtype, "update", ())
                self.assertEqual(sv.resource_severity(comparison, classification="external_deletion").severity, sv.HIGH)

    def test_redacted_security_value(self):
        r = rate_one("azurerm_storage_account", SA, dict(SA, public_network_access_enabled=True), SA, configured=list(SA),
                     sensitive={"public_network_access_enabled": True})
        change = by_path(r)["public_network_access_enabled"]
        self.assertTrue(change.assessment.change["redacted"])
        # Value hidden: no CRITICAL escalation from it, but sensitive and storage rules both say HIGH
        self.assertEqual(change.severity, sv.HIGH)
        self.assertEqual(change.rules, ("storage-public-network-access", "sensitive-value"))

    def test_redacted_unknown_attribute_is_high(self):
        state = {"id": "/x", "admin_password": "a"}
        r = rate_one("azurerm_linux_virtual_machine", state, dict(state, admin_password="b"), state,
                     configured=list(state), sensitive={"admin_password": True})
        self.assertEqual(r.severity, sv.HIGH)
        self.assertNotIn('"b"', json.dumps([ch.assessment.change for ch in r.changes]))

    def test_unknown_desired_value_does_not_escalate(self):
        desired = {k: v for k, v in SA.items() if k != "public_network_access_enabled"}
        r = rate_one("azurerm_storage_account", SA, SA, desired, configured=list(SA),
                     after_unknown={"public_network_access_enabled": True})
        change = by_path(r)["public_network_access_enabled"]
        self.assertEqual(change.assessment.change["desired"], {"status": "unknown"})
        self.assertEqual(change.severity, sv.HIGH)

    def test_odd_value_shapes_do_not_crash(self):
        for value in (None, "*", 5, [None, "x", 3], {"direction": "Inbound"}, [{"access": None}], [[RULE]]):
            with self.subTest(value=value):
                r = drift("azurerm_network_security_group", NSG, security_rule=value)
                self.assertIn(r.severity, (sv.HIGH, sv.CRITICAL))

    def test_rule_order_does_not_matter(self):
        state = dict(KV, description="x")
        args = ("azurerm_key_vault", state, dict(state, access_policy=[], tags={}, description="y"), state)
        forward = rate_plan(azure_plan(*args, configured=list(state)))
        backward = rate_plan(azure_plan(*args, configured=list(state)), rules=tuple(reversed(sv.SEVERITY_RULES)))
        for address in forward:
            self.assertEqual(forward[address].severity, backward[address].severity)
            self.assertEqual([c.severity for c in forward[address].changes],
                             [c.severity for c in backward[address].changes])
            self.assertEqual([set(c.rules) for c in forward[address].changes],
                             [set(c.rules) for c in backward[address].changes])

    def test_custom_rules(self):
        rule = sv.SeverityRule("rg-location", sv.CRITICAL, "test", (("location",),), ("azurerm_resource_group",))
        with open(os.path.join(FIXTURE_SOURCE, "replace", "plan.sanitized.json"), encoding="utf-8") as fh:
            plan = json.load(fh)
        (r,) = rate_plan(plan, rules=(rule,)).values()
        self.assertEqual(r.severity, sv.CRITICAL)
        (r,) = rate_plan(plan, rules=()).values()
        self.assertEqual(r.severity, sv.HIGH)  # replace floor


# ---------------------------------------------------------------------------
# API contract
# ---------------------------------------------------------------------------

class TestApi(unittest.TestCase):
    def test_severity_order(self):
        self.assertEqual(sv.SEVERITIES, ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"))
        self.assertEqual(sv.highest(["LOW", "CRITICAL", "MEDIUM"]), "CRITICAL")
        self.assertEqual(sv.highest([]), "INFO")
        self.assertLess(sv.rank(sv.HIGH), sv.rank(sv.CRITICAL))

    def test_rule_validation(self):
        with self.assertRaises(ValueError):
            sv.SeverityRule("x", "SEVERE", "bad", sv.ANY_PATH)
        with self.assertRaises(ValueError):
            sv.SeverityRule("x", sv.LOW, "half escalation", sv.ANY_PATH, escalate_to=sv.HIGH)
        with self.assertRaises(ValueError):
            sv.SeverityRule("x", sv.LOW, "half escalation", sv.ANY_PATH, escalate_when=sv.value_is_true)

    def test_default_rule_ids_unique(self):
        ids = [r.id for r in sv.SEVERITY_RULES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_mismatched_inputs_rejected(self):
        with open(os.path.join(FIXTURE_SOURCE, "external_deletion", "plan.sanitized.json"), encoding="utf-8") as fh:
            plan = json.load(fh)
        parsed = parser.parse_plan(plan)
        comparisons = c.compare_plan(parsed, c.configured_attributes(plan))
        with self.assertRaises(ValueError):
            sv.plan_severity(parsed, comparisons[:1])
        with self.assertRaises(ValueError):
            sv.resource_severity(comparisons[0], parsed.resources[1])

    def test_every_change_rated_and_unmodified(self):
        for name in fixture_names():
            with self.subTest(name):
                with open(os.path.join(FIXTURE_SOURCE, name, "plan.sanitized.json"), encoding="utf-8") as fh:
                    plan = json.load(fh)
                parsed = parser.parse_plan(plan)
                comparisons = c.compare_plan(parsed, c.configured_attributes(plan))
                snapshot = copy.deepcopy(comparisons)
                rated = sv.plan_severity(parsed, comparisons)
                self.assertEqual(comparisons, snapshot)
                self.assertEqual([r.address for r in rated], [e.address for e in parsed.resources])
                for r, comp in zip(rated, comparisons):
                    self.assertEqual(tuple(ch.assessment for ch in r.changes), comp.changes)
                    self.assertIn(r.severity, sv.SEVERITIES)

    def test_classifier_output_unchanged(self):
        for name in fixture_names():
            with self.subTest(name):
                with open(os.path.join(FIXTURE_SOURCE, name, "plan.sanitized.json"), encoding="utf-8") as fh:
                    plan = json.load(fh)
                before = json.dumps(dd.classify_plan(plan), sort_keys=True)
                rate_plan(plan)
                self.assertEqual(json.dumps(dd.classify_plan(plan), sort_keys=True), before)

    def test_deterministic(self):
        for name in fixture_names():
            with self.subTest(name):
                self.assertEqual(rate_fixture(name), rate_fixture(name))


if __name__ == "__main__":
    unittest.main()
