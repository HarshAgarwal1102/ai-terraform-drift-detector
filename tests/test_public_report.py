"""Tests for the public drift report projection (Task 9B.4A).

Run from the repository root:
    pytest tests/test_public_report.py

The internal drift report is the unchanged Phase 3/4 document; the public report is its
deterministic projection with identifiers withheld (PROJECT_PLAN.md Phase 9B, P1-P4). No
Azure, network, credentials or real identifiers: every ID, GUID and address is synthetic.
"""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS)

from test_activity_logs import NSG_ADDR, NSG_ID, OTHER_ID, RG_ADDR, RG_ID, nsg, raw_entry, write_raw_plan  # noqa: E402

try:
    import jsonschema
except ImportError:  # dev extra not installed
    jsonschema = None

from drift_engine import cli  # noqa: E402
from drift_engine import report_public as rp  # noqa: E402
from drift_engine.classifier import evaluate  # noqa: E402
from drift_engine.investigation_public import canonical_sha256  # noqa: E402
from drift_engine.models import DriftReport  # noqa: E402

ROOT = Path(TESTS).parent
FIXTURES = Path(TESTS) / "fixtures"
GROUPS = ("plan_evidence", "security_plans", "cost_config_plans", "root_cause_plans", "report_plans")
G1 = "11111111-2222-4333-8444-555555555555"
G2 = "66666666-7777-4888-9999-000000000000"
SAMPLES = {"arm": OTHER_ID, "subscription_path": "/subscriptions/abc/resourceGroups/rg",
           "provider_path": "x/providers/Microsoft.Network/thing", "guid": G1, "upn": "carol@example.com"}
HAS_AI_EXTRA = all(importlib.util.find_spec(m) for m in ("langgraph", "langchain_openai"))


def fixture_paths():
    for group in GROUPS:
        for directory in sorted((FIXTURES / group).iterdir()):
            plan = next((directory / f for f in ("plan.synthetic.json", "plan.sanitized.json", "plan.json")
                         if (directory / f).exists()), None)
            if directory.is_dir() and plan is not None and (directory / "detection_run.json").exists():
                yield f"{group}/{directory.name}", (str(plan), str(directory / "detection_run.json"))


def internal_of(evaluation) -> dict:
    return DriftReport.model_validate(evaluation.report).model_dump(mode="json")


class _Base(unittest.TestCase):
    def setUp(self):
        import shutil
        self.tmp = tempfile.mkdtemp(prefix="public-report-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.count = 0

    def dir(self) -> str:
        self.count += 1
        return os.path.join(self.tmp, f"d{self.count}")

    def ids_plan(self, extra_real=None):
        """An NSG drifted in identifier-valued attributes, plus an in-sync RG (whose ARM ID the plan maps)."""
        state = nsg(tags={"env": "dev"}, association=RG_ID, owner="alice@example.com", principal=G1,
                    cidr="10.0.0.0/16", url="https://example.org/x", ids=[OTHER_ID], plain="a",
                    rules=[{"web": "allow"}])
        real = nsg(tags={"env": "dev", G2: "x"}, association=OTHER_ID, owner="bob@example.com", principal=G2,
                   cidr="0.0.0.0/0", url="https://example.org/y", ids=[RG_ID], plain="a",
                   rules=[{G1: "allow"}], **(extra_real or {}))
        rg = {"id": RG_ID, "name": "rg"}
        return write_raw_plan(self.dir(), drift=[raw_entry(NSG_ADDR, ["update"], state, real)],
                              changes=[raw_entry(NSG_ADDR, ["update"], real, state),
                                       raw_entry(RG_ADDR, ["no-op"], rg, rg, rtype="azurerm_resource_group")])

    def tags_key_plan(self):
        """Only a tag whose key is a GUID drifted, so the resource severity reason names that path."""
        state, real = nsg(tags={"env": "dev"}), nsg(tags={"env": "dev", G2: "x"})
        return write_raw_plan(self.dir(), drift=[raw_entry(NSG_ADDR, ["update"], state, real)],
                              changes=[raw_entry(NSG_ADDR, ["update"], real, state)])

    def project(self, paths):
        evaluation = evaluate(*paths)
        internal = internal_of(evaluation)
        index = rp.build_index(evaluation.plan or {})
        return internal, rp.project(internal, index), index

    @staticmethod
    def change(document, path, address=NSG_ADDR):
        resource = next(r for r in document["resources"] if r["address"] == address)
        return next(c for c in resource["attribute_changes"] if c["path"][0] == path)


# ---------------------------------------------------------------------------
# The internal report is unchanged; every fixture projects
# ---------------------------------------------------------------------------

class InternalUnchangedTests(_Base):
    def run_analyze(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["analyze", *args])
        return code, out.getvalue(), err.getvalue()

    def test_internal_output_is_byte_identical_with_and_without_public_output(self):
        for name, (plan, manifest) in fixture_paths():
            with self.subTest(name):
                a, b, public = (os.path.join(self.tmp, f"{name.replace('/', '-')}-{x}.json") for x in "abp")
                code_a, _, _ = self.run_analyze("--plan", plan, "--manifest", manifest, "--output", a)
                code_b, _, _ = self.run_analyze("--plan", plan, "--manifest", manifest, "--output", b,
                                                "--public-output", public)
                self.assertEqual(code_a, code_b)
                self.assertEqual(Path(a).read_bytes(), Path(b).read_bytes())
                self.assertEqual(json.loads(Path(a).read_text()), internal_of(evaluate(plan, manifest)))
                document = json.loads(Path(public).read_text())
                self.assertEqual(document["public_version"], "1")
                self.assertEqual(rp.identifier_findings(document), [])


class ProjectionTests(_Base):
    def test_every_fixture_projects_deterministically_and_cleanly(self):
        for name, paths in fixture_paths():
            with self.subTest(name):
                evaluation = evaluate(*paths)
                internal = internal_of(evaluation)
                text = rp.publish_report(internal, evaluation.plan or {})
                self.assertEqual(text, rp.publish_report(copy.deepcopy(internal), evaluation.plan or {}))
                document = json.loads(text)
                self.assertEqual(rp.verify_public_report(document, internal, rp.build_index(evaluation.plan or {})),
                                 [])
                self.assertEqual(rp.identifier_findings(document), [])
                # only views and public_version differ from the internal report
                strip = lambda d: {k: v for k, v in d.items() if k not in ("resources", "public_version")}
                self.assertEqual(strip(document), strip(internal))
                for pub_r, raw_r in zip(document["resources"], internal["resources"]):
                    self.assertEqual({k: v for k, v in pub_r.items() if k != "attribute_changes"},
                                     {k: v for k, v in raw_r.items() if k != "attribute_changes"})

    def test_deletion_ids_name_their_terraform_address(self):
        for name in ("plan_evidence/external_deletion", "plan_evidence/resource_removed", "plan_evidence/replace",
                     "cost_config_plans/storage_deleted_externally", "report_plans/multi_resource"):
            with self.subTest(name):
                paths = dict(fixture_paths())[name]
                evaluation = evaluate(*paths)
                internal = internal_of(evaluation)
                index = rp.build_index(evaluation.plan or {})
                document = rp.public_document(internal, evaluation.plan or {})
                ids = [(pc, rc) for pr, rr in zip(document["resources"], internal["resources"])
                       for pc, rc in zip(pr["attribute_changes"], rr["attribute_changes"]) if pc["path"] == ["id"]]
                self.assertTrue(ids)
                for pc, rc in ids:
                    for view in ("state", "real", "desired"):
                        if rc[view]["status"] != "value":
                            continue
                        self.assertIn("arm_resource_id", pc[view]["kinds"])
                        # a plan resource's address; a ref when no single resource owns that ID (ambiguous)
                        owner = index.get(rc[view]["value"].casefold())
                        self.assertEqual((pc[view]["resource"], pc[view]["ref"] is None), (owner, owner is not None))
                self.assertEqual(rp.identifier_findings(document), [])

    def test_withheld_classes_and_kept_configuration_evidence(self):
        internal, public, _ = self.project(self.ids_plan())
        association = self.change(public, "association")
        self.assertEqual(association["state"], {"status": "withheld", "kinds": ["arm_resource_id", "guid"],
                                                "resource": RG_ADDR, "ref": None})  # an ARM ID of a plan resource
        self.assertEqual(association["real"], {"status": "withheld", "kinds": ["arm_resource_id", "guid"],
                                               "resource": None, "ref": "id-1"})  # not in this plan
        self.assertEqual(association["desired"], association["state"])
        owner, principal = self.change(public, "owner"), self.change(public, "principal")
        self.assertEqual((owner["state"]["kinds"], owner["state"]["ref"], owner["real"]["ref"],
                          owner["desired"]["ref"]), (["identity"], "id-2", "id-3", "id-2"))  # same value, same ref
        self.assertEqual((principal["state"]["kinds"], principal["state"]["ref"], principal["real"]["ref"]),
                         (["guid"], "id-4", "id-5"))
        ids = self.change(public, "ids")
        self.assertEqual(ids["state"], {"status": "withheld", "kinds": ["arm_resource_id", "guid"], "resource": None,
                                        "ref": None})  # a container is withheld whole
        for path, expected in (("cidr", ("10.0.0.0/16", "0.0.0.0/0")), ("url", ("https://example.org/x",
                                                                                 "https://example.org/y"))):
            change = self.change(public, path)
            self.assertEqual((change["state"]["value"], change["real"]["value"]), expected)  # Terraform evidence
            self.assertEqual(change, self.change(internal, path))
        self.assertEqual(rp.identifier_findings(public), [])

    def test_identifier_key_becomes_a_stable_placeholder(self):
        internal, public, _ = self.project(self.tags_key_plan())
        [change] = [c for c in public["resources"][0]["attribute_changes"] if c["path"][0] == "tags"]
        self.assertEqual((change["path"], change["attribute"]), (["tags", "withheld-key-1"], "tags"))
        self.assertEqual({change[v]["status"] for v in ("state", "real", "desired")}, {"withheld"})
        self.assertEqual(change["state"]["kinds"], ["guid"])  # absent state view, withheld for its key
        raw_reasons = internal["resources"][0]["severity"]["reasons"]
        self.assertTrue(any(r.startswith(f"tags.{G2}: ") for r in raw_reasons))
        self.assertTrue(any(r.startswith("tags.withheld-key-1: ") for r in public["resources"][0]["severity"]["reasons"]))
        self.assertEqual(rp.identifier_findings(public), [])

    def test_value_less_views_and_redaction_are_copied(self):
        internal, public, _ = self.project(self.ids_plan())
        for pub_r, raw_r in zip(public["resources"], internal["resources"]):
            for pc, rc in zip(pub_r["attribute_changes"], raw_r["attribute_changes"]):
                self.assertEqual((pc["redacted"], pc["class"], pc["severity"], pc["assessment"]),
                                 (rc["redacted"], rc["class"], rc["severity"], rc["assessment"]))
                for view in ("state", "real", "desired"):
                    if rc[view]["status"] != "value" and "withheld-key" not in ".".join(pc["path"]):
                        self.assertEqual(pc[view], rc[view])

    def test_identifiers_in_structure_fail_closed(self):
        internal, _, index = self.project(self.ids_plan())
        positions = {
            "address": lambda r: r["resources"][0].update(address=f'azurerm_x.this["{G1}"]'),
            "notes": lambda r: r["resources"][0]["notes"].append("owned by dave@example.com"),
            "working_dir": lambda r: r["run"].update(working_dir="/subscriptions/x/dir"),
            "resource_types": lambda r: r["resource_types"][0]["addresses"].append(G1),
            "plan": lambda r: r["plan"].update(timestamp=G1),
            "index": lambda r: r["resources"][0].update(index=G1),
            "previous_address": lambda r: r["resources"][0].update(previous_address=OTHER_ID),
        }
        for name, plant in positions.items():
            with self.subTest(name):
                planted = copy.deepcopy(internal)
                plant(planted)
                with self.assertRaises(rp.PublicReportError) as ctx:
                    rp.project(planted, index)
                self.assertEqual(ctx.exception.code, "identifier_in_structure")
                self.assertNotIn(G1, str(ctx.exception))

    def test_index(self):
        plan = {"prior_state": {"values": {"root_module": {
                    "resources": [{"address": "a.one", "mode": "managed", "values": {"id": RG_ID}}],
                    "child_modules": [{"resources": [{"address": "module.m.b.two", "mode": "managed",
                                                      "values": {"id": NSG_ID}},
                                                     {"address": "data.x", "mode": "data", "values": {"id": OTHER_ID}}]}]}}},
                "resource_changes": [{"address": "c.three", "mode": "managed",
                                      "change": {"before": {"id": NSG_ID.upper()}, "after": None}}]}
        index = rp.build_index(plan)
        self.assertEqual(index[RG_ID.casefold()], "a.one")
        self.assertIsNone(index[NSG_ID.casefold()])  # two addresses share it: no address, a ref
        self.assertNotIn(OTHER_ID.casefold(), index)  # data sources are not managed resources
        with self.assertRaises(rp.PublicReportError) as ctx:
            rp.build_index(["not", "a", "plan"])
        self.assertEqual(ctx.exception.code, "index_invalid")


# ---------------------------------------------------------------------------
# Independent verification, scan, model and schema
# ---------------------------------------------------------------------------

class VerificationTests(_Base):
    def test_tampering_is_detected(self):
        internal, public, index = self.project(self.ids_plan())
        self.assertEqual(rp.verify_public_report(public, internal, index), [])

        def ch(doc, path):
            return self.change(doc, path)
        tampers = {
            "classification": lambda d: d["resources"][0].update(classification="in_sync"),
            "summary": lambda d: d["summary"].update(highest_severity="INFO"),
            "version": lambda d: d.update(public_version="2"),
            "value restored": lambda d: ch(d, "owner").update(state={"status": "value", "value": "x"}),
            "kept value changed": lambda d: ch(d, "cidr")["real"].update(value="10.9.9.9/32"),
            "ref renumbered": lambda d: ch(d, "owner")["real"].update(ref="id-9"),
            "ref unstable": lambda d: ch(d, "owner")["desired"].update(ref="id-3"),
            "resource swapped": lambda d: ch(d, "association")["state"].update(resource=NSG_ADDR),
            "resource dropped": lambda d: ch(d, "association")["state"].update(resource=None, ref="id-1"),
            "kinds": lambda d: ch(d, "principal")["state"].update(kinds=["identity"]),
            "container ref": lambda d: ch(d, "ids")["state"].update(ref="id-1"),
            "path": lambda d: ch(d, "cidr").update(path=["cidrs"], attribute="cidrs"),
            "severity": lambda d: ch(d, "cidr")["severity"].update(level="LOW"),
            "reasons": lambda d: d["resources"][0]["severity"]["reasons"].reverse(),
            "change dropped": lambda d: d["resources"][0]["attribute_changes"].pop(),
            "leak": lambda d: ch(d, "cidr")["real"].update(value=SAMPLES["upn"]),
            "contract": lambda d: d.update(extra=1),
        }
        for name, tamper in tampers.items():
            with self.subTest(name):
                broken = copy.deepcopy(public)
                tamper(broken)
                problems = rp.verify_public_report(broken, internal, index)
                self.assertNotEqual(problems, [], name)
                self.assertNotIn(SAMPLES["upn"], " ".join(problems))

    def test_structural_tampering_is_detected(self):
        internal, public, index = self.project(self.ids_plan())
        r0 = lambda d: d["resources"][0]
        first = lambda d: r0(d)["attribute_changes"][0]
        tampers = {
            "resource severity": lambda d: r0(d)["severity"].update(level="INFO"),
            "resource count": lambda d: d["resources"].append(copy.deepcopy(r0(d))),
            "path length": lambda d: first(d).update(path=first(d)["path"] + ["x"]),
            "attribute": lambda d: first(d).update(attribute="other"),
            "attributes class": lambda d: r0(d)["attributes"][0].update({"class": "config_changed"}),
            "attributes name": lambda d: r0(d)["attributes"][0].update(name="renamed"),
            "attributes count": lambda d: r0(d)["attributes"].pop(),
            "value-less view": lambda d: next(c for c in r0(d)["attribute_changes"]
                                              if c["state"]["status"] == "absent" or c["real"]["status"] == "absent"
                                              or True)["desired"].update(status="unknown"),
            "scalar without ref": lambda d: self.change(d, "principal")["state"].update(ref=None),
        }
        for name, tamper in tampers.items():
            with self.subTest(name):
                broken = copy.deepcopy(public)
                tamper(broken)
                self.assertNotEqual(rp.verify_public_report(broken, internal, index), [], name)

    def test_identifier_attribute_name_uses_the_key_placeholder(self):
        internal, _, index = self.project(self.tags_key_plan())
        internal["resources"][0]["attributes"].append({"name": G1, "class": "drifted"})
        change = copy.deepcopy(internal["resources"][0]["attribute_changes"][0])
        internal["resources"][0]["attribute_changes"].append(dict(change, path=[G1], attribute=G1))
        public = rp.project(internal, index)
        self.assertEqual(public["resources"][0]["attributes"][-1]["name"], "withheld-key-2")
        self.assertEqual(rp.verify_public_report(public, internal, index), [])
        for tamper in (lambda d: d["resources"][0]["attributes"][-1].update(name="withheld-key-1"),
                       lambda d: d["resources"][0]["attribute_changes"][-1]["state"].update(ref="id-1", kinds=["guid"]),
                       lambda d: d["resources"][0]["attribute_changes"][-1]["real"].update(kinds=["identity"]),
                       lambda d: d["resources"][0]["attribute_changes"][-1]["desired"].update(
                           status="unknown", kinds=None, resource=None, ref=None)):
            broken = copy.deepcopy(public)
            tamper(broken)
            if broken["resources"][0]["attribute_changes"][-1]["desired"].get("kinds", 1) is None:
                for key in ("kinds", "resource", "ref"):
                    broken["resources"][0]["attribute_changes"][-1]["desired"].pop(key)
            self.assertNotEqual(rp.verify_public_report(broken, internal, index), [])
        with self.assertRaises(ValueError):
            rp.PublicReportError("not_a_code")

    def test_key_tampering_is_detected(self):
        internal, public, index = self.project(self.tags_key_plan())
        for tamper in (lambda d: d["resources"][0]["attribute_changes"][0]["path"].__setitem__(1, "withheld-key-2"),
                       lambda d: d["resources"][0]["severity"]["reasons"].__setitem__(
                           0, d["resources"][0]["severity"]["reasons"][0].replace("withheld-key-1", "x"))):
            broken = copy.deepcopy(public)
            tamper(broken)
            self.assertNotEqual(rp.verify_public_report(broken, internal, index), [])

    def test_publish_fails_closed_on_verification_or_scan(self):
        internal, _, _ = self.project(self.ids_plan())
        plan = evaluate(*self.ids_plan()).plan
        with mock.patch.object(rp, "verify_public_report", return_value=["x"]):
            with self.assertRaises(rp.PublicReportError) as ctx:
                rp.publish_report(internal, plan)
        self.assertEqual(ctx.exception.code, "verification_failed")
        with self.assertRaises(rp.PublicReportError) as ctx:
            rp.publish_report(internal, plan, manifest={"run_id": SAMPLES["upn"]})
        self.assertEqual(ctx.exception.code, "scan_failed")


class ScanTests(_Base):
    def test_every_string_and_key_position_is_scanned(self):
        _, public, _ = self.project(self.ids_plan())
        positions = []

        def walk(value, path=()):
            if isinstance(value, str):
                positions.append((path, "value"))
            elif isinstance(value, dict):
                for key, item in value.items():
                    positions.append((path + (key,), "key"))
                    walk(item, path + (key,))
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    walk(item, path + (i,))
        walk(public)
        self.assertGreater(len(positions), 150)
        for path, kind in positions:
            for sample in SAMPLES.values():
                planted = copy.deepcopy(public)
                node = planted
                for part in path[:-1]:
                    node = node[part]
                if kind == "key":
                    node[sample] = node.pop(path[-1])
                else:
                    node[path[-1]] = sample
                findings = rp.identifier_findings(planted)
                self.assertTrue(findings, (path, kind))
                self.assertNotIn(sample, " ".join(findings))

    def test_configuration_evidence_is_not_flagged(self):
        for text in ("10.0.0.0/16", "0.0.0.0/0", "2001:db8::/32", "https://example.org/a?b=c", "@daily",
                     "Standard_B1s", "rg-aitdd/main"):
            self.assertEqual(rp.identifier_findings({"v": text}), [], text)


class ModelAndSchemaTests(_Base):
    def test_contracts_exclude_each_other(self):
        internal, public, _ = self.project(self.ids_plan())
        rp.validate_public(public)
        with self.assertRaises(Exception):
            rp.validate_public(internal)  # no public_version
        with self.assertRaises(Exception):
            DriftReport.model_validate(public)  # the internal contract rejects public_version and withheld
        for bad in ({"kinds": ["guid", "arm_resource_id"]}, {"kinds": []}, {"kinds": ["ip"]},
                    {"resource": "a", "ref": "id-1"}, {"ref": "x-1"}):
            with self.subTest(bad):
                broken = copy.deepcopy(public)
                self.change(broken, "owner")["state"].update(bad)
                with self.assertRaises(Exception):
                    rp.validate_public(broken)

    @unittest.skipIf(jsonschema is None, "needs jsonschema (dev extra)")
    def test_public_schema_agrees(self):
        schema = json.loads((ROOT / "schemas" / "drift_report.public.schema.json").read_text())
        internal_schema = json.loads((ROOT / "schemas" / "drift_report.schema.json").read_text())
        validator = jsonschema.Draft202012Validator(schema)
        for name, paths in list(fixture_paths()) + [("ids", self.ids_plan()), ("key", self.tags_key_plan())]:
            with self.subTest(name):
                evaluation = evaluate(*paths)
                internal = internal_of(evaluation)
                validator.validate(rp.public_document(internal, evaluation.plan or {}))
                self.assertFalse(validator.is_valid(internal))
        # identical to the internal schema apart from the documented differences
        for key in ("$schema", "type", "additionalProperties", "allOf"):
            self.assertEqual(schema[key], internal_schema[key], key)
        self.assertEqual(schema["required"], internal_schema["required"] + ["public_version"])
        self.assertEqual({k: v for k, v in schema["$defs"].items() if k != "view_value"},
                         {k: v for k, v in internal_schema["$defs"].items() if k != "view_value"})
        self.assertEqual(schema["$defs"]["view_value"]["oneOf"][:2], internal_schema["$defs"]["view_value"]["oneOf"])

    def test_hash_contract(self):
        evaluation = evaluate(*self.ids_plan())
        internal = internal_of(evaluation)
        document = rp.public_document(internal, evaluation.plan)
        self.assertEqual(rp.public_sha256(document), canonical_sha256(document))
        self.assertNotEqual(rp.public_sha256(document), canonical_sha256(internal))

    def test_module_imports_nothing_restricted(self):
        import ast
        tree = ast.parse(Path(rp.__file__).read_text())
        imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {
            a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        self.assertEqual({m for m in imported if m and m.startswith("drift_engine")},
                         {"drift_engine.investigation_public", "drift_engine.models"})


# ---------------------------------------------------------------------------
# CLI: analyze --public-output
# ---------------------------------------------------------------------------

class CliTests(_Base):
    def main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["analyze", *args])
        return code, out.getvalue(), err.getvalue()

    def outputs(self):
        directory = self.dir()
        os.makedirs(directory)
        return os.path.join(directory, "drift_report.json"), os.path.join(directory, "drift_report.public.json")

    def test_writes_both(self):
        plan, manifest = self.ids_plan()
        internal_path, public_path = self.outputs()
        code, out, _ = self.main("--plan", plan, "--manifest", manifest, "--output", internal_path,
                                 "--public-output", public_path)
        self.assertEqual(code, 0)
        self.assertIn("alice@example.com", Path(internal_path).read_text())  # internal: unchanged values
        public = Path(public_path).read_text()
        self.assertNotIn("alice@example.com", public)
        self.assertNotIn("/subscriptions/", public)
        self.assertEqual(rp.identifier_findings(json.loads(public)), [])

    def test_every_failure_writes_nothing_and_echoes_no_value(self):
        plan, manifest = self.ids_plan()
        cases = {
            "identifier_in_structure": lambda: mock.patch.object(
                rp, "project", side_effect=rp.PublicReportError("identifier_in_structure")),
            "verification_failed": lambda: mock.patch.object(rp, "verify_public_report", return_value=["x"]),
            "scan_failed": lambda: mock.patch.object(cli, "_published_manifest", return_value={"note": G1}),
            "unexpected": lambda: mock.patch.object(rp, "project", side_effect=KeyError(G1)),
        }
        for name, patcher in cases.items():
            with self.subTest(name):
                internal_path, public_path = self.outputs()
                with patcher():
                    code, _, err = self.main("--plan", plan, "--manifest", manifest, "--output", internal_path,
                                             "--public-output", public_path)
                self.assertEqual(code, 70)
                self.assertFalse(os.path.exists(internal_path) or os.path.exists(public_path))
                expected = "verification_failed" if name == "unexpected" else name
                self.assertIn(f"public_projection_failed:{expected}", err)
                self.assertIn("UNKNOWN", err)
                self.assertNotIn(G1, err)

    def test_identifier_in_a_real_structural_field(self):
        plan, manifest = self.ids_plan()
        with open(manifest, encoding="utf-8") as fh:
            doc = json.load(fh)
        doc["backend_key"] = "state-of-erin@example.com"  # copied into report.run: never rewritten
        with open(manifest, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        internal_path, public_path = self.outputs()
        code, _, err = self.main("--plan", plan, "--manifest", manifest, "--output", internal_path,
                                 "--public-output", public_path)
        self.assertEqual(code, 70)
        self.assertIn("public_projection_failed:identifier_in_structure", err)
        self.assertNotIn("erin@example.com", err)
        self.assertFalse(os.path.exists(public_path) or os.path.exists(internal_path))

    def test_write_failures_leave_nothing(self):
        plan, manifest = self.ids_plan()
        internal_path, _ = self.outputs()
        code, _, err = self.main("--plan", plan, "--manifest", manifest, "--output", internal_path,
                                 "--public-output", os.path.join(self.tmp, "missing-dir", "p.json"))
        self.assertEqual(code, 70)
        self.assertIn("public_projection_failed:write_failed", err)
        self.assertFalse(os.path.exists(internal_path))
        _, public_path = self.outputs()
        code, _, _ = self.main("--plan", plan, "--manifest", manifest,
                               "--output", os.path.join(self.tmp, "missing-dir", "i.json"), "--public-output", public_path)
        self.assertEqual(code, 73)
        self.assertFalse(os.path.exists(public_path))  # never a public report without its internal source

    def test_without_the_flag_nothing_changes(self):
        plan, manifest = self.ids_plan()
        internal_path, public_path = self.outputs()
        code, _, _ = self.main("--plan", plan, "--manifest", manifest, "--output", internal_path)
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(public_path))

    def test_failed_detection_still_projects(self):
        directory = self.dir()
        os.makedirs(directory)
        manifest = os.path.join(directory, "detection_run.json")
        with open(FIXTURES / "plan_evidence" / "failed_run" / "detection_run.json") as src, open(manifest, "w") as dst:
            dst.write(src.read())
        internal_path, public_path = self.outputs()
        code, _, _ = self.main("--plan", os.path.join(directory, "absent.json"), "--manifest", manifest,
                               "--output", internal_path, "--public-output", public_path)
        self.assertEqual(code, 1)  # unchanged Phase 5 semantics: failed evidence
        document = json.loads(Path(public_path).read_text())
        self.assertEqual((document["outcome"], document["has_drift"], document["resources"]), ("failed", None, []))


# ---------------------------------------------------------------------------
# Consumers
# ---------------------------------------------------------------------------

def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"_{name}_under_test", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ConsumerTests(_Base):
    def public_ids(self):
        evaluation = evaluate(*self.ids_plan())
        return internal_of(evaluation), rp.public_document(internal_of(evaluation), evaluation.plan)

    def test_issues_accept_only_the_public_report_and_render_withheld(self):
        ga = _load_script("github_automation")
        internal, public = self.public_ids()
        with self.assertRaises(ga.AutomationError):
            ga.load_report(json.dumps(internal).encode())
        report = ga.load_report(json.dumps(public).encode())
        body = ga.render_canonical("dev", next(r for r in report.resources if r.address == NSG_ADDR))
        self.assertIn("withheld", body)
        for secret in ("alice@example.com", "/subscriptions/", G1):
            self.assertNotIn(secret, body)

    def test_cost_binding_refuses_the_internal_report(self):
        san = _load_script("sanitize_infracost")
        internal, public = self.public_ids()
        for report in (dict(internal, run=dict(internal["run"], run_id="github-1-1")),):
            with self.assertRaises(san.SanitizeError):
                san.report_binding(report, "github-1-1")
        public = dict(public, run=dict(public["run"], run_id="github-1-1", environment="dev"))
        self.assertEqual(san.report_binding(public, "github-1-1"), ("dev", rp.public_sha256(public)))

    @unittest.skipUnless(HAS_AI_EXTRA, "needs the 'ai' extra")
    def test_ai_report_from_identifier_drift_is_leak_free(self):
        from ai_engine.config import load_config
        from ai_engine.graph import run_analysis
        from ai_engine.nodes.report_generator import render_markdown
        from ai_engine.verify import verify_report
        internal, public = self.public_ids()
        with self.assertRaises(Exception):
            run_analysis(copy.deepcopy(internal), config=load_config({}))  # the internal report never reaches it
        report = json.loads(json.dumps(run_analysis(copy.deepcopy(public), config=load_config({}))["report"]))
        self.assertEqual(verify_report(report, public), [])
        self.assertEqual(report["provenance"]["drift_report_sha256"], rp.public_sha256(public))
        resource = next(r for r in report["resources"] if r["address"] == NSG_ADDR)
        association = next(c for c in resource["what"]["changes"] if c["path"] == ["association"])
        self.assertEqual(association["state"]["resource"], RG_ADDR)
        gaps = {tuple(g["path"]): g["reason"] for o in report["remediation"]["options"] for g in o["fragment_gaps"]}
        self.assertEqual(gaps[("owner",)], "withheld")
        markdown = render_markdown(report)
        self.assertIn("withheld", markdown)
        self.assertEqual(rp.identifier_findings(report), [])
        self.assertEqual(rp.identifier_findings(markdown.replace("​", "")), [])


# ---------------------------------------------------------------------------
# Safeguard mutants (an in-process copy of report_public.py; the file is never changed)
# ---------------------------------------------------------------------------

MUTANTS = {
    "no-arm-kind": ('    if _ARM_PATH.search(text):\n        kinds.add("arm_resource_id")', '    if False:\n        kinds.add("arm_resource_id")'),
    "no-guid-kind": ('    if _GUID.search(text):\n        kinds.add("guid")', '    if False:\n        kinds.add("guid")'),
    "no-identity-kind": ('    if _IDENTITY.search(text):\n        kinds.add("identity")', '    if False:\n        kinds.add("identity")'),
    "keys-not-scanned": ("            out |= identifier_kinds(str(key)) | _value_kinds(item)", "            out |= _value_kinds(item)"),
    "no-address-mapping": ("    address = index.get(value.casefold()) if \"arm_resource_id\" in kinds else None\n    return",
                           "    address = None\n    return"),
    "container-ref": ("    if forced or not isinstance(value, str):\n        return _withheld(kinds | forced)",
                      "    if forced:\n        return _withheld(kinds | forced)"),
    "key-not-forced": ("                projected[name] = _project_view(change[name], key_kinds, index, refs)",
                       "                projected[name] = _project_view(change[name], set(), index, refs)"),
    "key-kept": ("            path = [keys(s) if identifier_kinds(s) else s for s in change[\"path\"]]",
                 "            path = list(change[\"path\"])"),
    "reason-not-renamed": ("                    reason = new + reason[len(old):]", "                    pass"),
    "structure-unchecked": ("    if identifier_findings(_structure(public)):\n        raise", "    if False:\n        raise"),
    "verify-skipped": ("    if verify_public_report(public, internal, index):\n        raise PublicReportError(\"verification_failed\")",
                       "    if False:\n        raise PublicReportError(\"verification_failed\")"),
    "scan-skipped": ("    if identifier_findings(public) or (manifest is not None and identifier_findings(manifest)):",
                     "    if False:"),
    "manifest-unscanned": ("    if identifier_findings(public) or (manifest is not None and identifier_findings(manifest)):",
                           "    if identifier_findings(public):"),
    "index-ambiguity-ignored": ("    return {rid: (next(iter(addresses)) if len(addresses) == 1 else None)",
                                "    return {rid: sorted(addresses)[0]"),
    "verify-kinds-unchecked": ("    if sorted(kinds) != list(pub.get(\"kinds\", [])):\n        add(", "    if False:\n        add("),
    "verify-refs-unchecked": ("        placeholder(value, pub[\"ref\"], ref_map, \"id-\", where)", "        pass"),
    "verify-copy-unchecked": ("        if dict(pub) != {\"status\": \"value\", \"value\": value}:\n            add(",
                              "        if False:\n            add("),
    "verify-scan-skipped": ("    findings = identifier_findings(public)\n    if findings:", "    findings = []\n    if findings:"),
}


class SafeguardMutationTests(_Base):
    def outcomes(self, module) -> tuple:
        ids, key = self.ids_plan(), self.tags_key_plan()
        results = []
        for paths, manifest in ((ids, None), (key, None), (ids, {"run_id": SAMPLES["upn"]})):
            evaluation = evaluate(*paths)
            internal = internal_of(evaluation)
            try:
                results.append(module.publish_report(internal, evaluation.plan, manifest))
            except Exception as exc:
                results.append(f"{type(exc).__name__}:{getattr(exc, 'code', '')}")
            planted = copy.deepcopy(internal)
            planted["resources"][0]["notes"].append(G1)
            try:
                results.append(module.project(planted, module.build_index(evaluation.plan)))
            except Exception as exc:
                results.append(f"{type(exc).__name__}:{getattr(exc, 'code', '')}")
        # verification of tampered documents (by the module under test)
        internal, public, index = self.project(ids)
        for tamper in (lambda d: self.change(d, "owner").update(state={"status": "value", "value": "x"}),
                       lambda d: self.change(d, "principal")["state"].update(kinds=["identity"]),
                       lambda d: self.change(d, "owner")["real"].update(ref="id-9"),
                       lambda d: self.change(d, "cidr")["real"].update(value="10.9.9.9/32"),
                       lambda d: self.change(d, "cidr")["real"].update(value=G1)):
            broken = copy.deepcopy(public)
            tamper(broken)
            results.append(bool(module.verify_public_report(broken, internal, index)))
        # a wrong projection must be caught by publish's own verification
        original_project = module.project
        module.project = lambda i, idx: dict(original_project(i, idx), summary=None)
        try:
            evaluation = evaluate(*ids)
            module.publish_report(internal_of(evaluation), evaluation.plan)
            results.append("published")
        except Exception as exc:
            results.append(f"{type(exc).__name__}:{getattr(exc, 'code', '')}")
        finally:
            module.project = original_project
        # an identifier present in both documents is caught only by verification's own scan
        both_internal, both_public = copy.deepcopy(internal), copy.deepcopy(public)
        for doc in (both_internal, both_public):
            doc["resources"][0]["notes"].append(G1)
        results.append(bool(module.verify_public_report(both_public, both_internal, index)))
        results.append(module.build_index({"resource_changes": [
            {"address": a, "mode": "managed", "change": {"before": {"id": RG_ID}}} for a in ("x.a", "x.b")]}))
        return tuple(json.dumps(r, sort_keys=True, default=str) for r in results)

    @staticmethod
    def load(name: str, source: str):
        module_name = f"drift_engine._report_public_mutant_{name.replace('-', '_')}"
        module = types.ModuleType(module_name)
        module.__file__ = f"<mutant {name}>"
        sys.modules[module_name] = module
        exec(compile(source, module.__file__, "exec"), module.__dict__)
        return module

    def test_every_mutant_is_caught(self):
        original = Path(rp.__file__).read_text(encoding="utf-8")
        baseline = self.outcomes(self.load("baseline", original))
        self.assertEqual(baseline, self.outcomes(rp))
        survivors = []
        for name, (old, new) in MUTANTS.items():
            with self.subTest(name):
                self.assertEqual(original.count(old), 1, f"mutant {name} no longer matches the source")
                if self.outcomes(self.load(name, original.replace(old, new))) == baseline:
                    survivors.append(name)
        self.assertEqual(survivors, [])


if __name__ == "__main__":
    unittest.main()
