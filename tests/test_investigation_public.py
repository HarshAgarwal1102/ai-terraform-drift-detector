"""Tests for the public drift investigation, the privacy profile and the restricted-data
CLI hardening (Task 9B.3).

Run from the repository root:
    pytest tests/test_investigation_public.py

No Azure, network or credentials. Public documents are projected from investigations
over a fake Activity Log source; IDs, callers and addresses are synthetic.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import datetime as dt
import hashlib
import io
import json
import os
import subprocess
import sys
import types
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS)

from test_activity_logs import (  # noqa: E402  (shared helpers; no test classes imported)
    CALLER, NSG_ADDR, NSG_ID, RG, ROOT, SUB, FakeSource, NoCallSource, al, ev, page,
)
from test_investigation import (  # noqa: E402
    REPO, UTC, FakeClock, _Base, at_time, in_sync, nsg_and_rg, nsg_drift, report_bytes,
)

try:
    from pydantic import ValidationError

    from drift_engine import attribution as at
    from drift_engine import cli
    from drift_engine import investigation as inv
    from drift_engine import investigation_public as pub
    from drift_engine import who
except ImportError:  # pydantic not installed
    pub = None

NO_CI = {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"}
SAMPLES = {  # forbidden values planted by the leak mutants
    "upn": "alice@example.com",
    "object_id": "11111111-2222-4333-8444-555555555555",
    "subscription": f"/subscriptions/{SUB}",
    "arm_id": NSG_ID,
    "event_id": "00000000-0000-4000-9000-000000000042",
    "ipv4": "203.0.113.9",
    "ipv6": "2001:db8::9",
    "url": "https://example.com/x",
}


def leaves(value, path=()):
    """(path, kind) for every string leaf and every dict key of a JSON value."""
    if isinstance(value, str):
        yield path, "value"
    elif isinstance(value, dict):
        for key, item in value.items():
            yield path + (key,), "key"
            yield from leaves(item, path + (key,))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from leaves(item, path + (index,))


def plant(document, path, kind, sample):
    node = document
    for part in path[:-1]:
        node = node[part]
    if kind == "key":
        node[sample] = node.pop(path[-1])
    else:
        node[path[-1]] = sample


@unittest.skipIf(pub is None, "drift_engine is not installed (pip install -e '.[dev]')")
class _PubBase(_Base):
    def rich(self):
        """An investigation with every public section populated: an anchored NSG with a
        capable tags write and an attached Policy event, descendant and automated events,
        a resource group without an anchor, rejected anchor candidates."""
        anchors = self.dir("anchors")
        self.anchor(anchors, "run-400-1")
        self.anchor(anchors, "run-399-1", run=399, head_branch="feature")
        with open(os.path.join(anchors, "notes.txt"), "w") as fh:
            fh.write("x")
        tags = self.log.tags(at_time(8))
        rows = (tags + self.log.policy(at_time(8, 0, 1), corr=tags[0]["correlationId"])
                + self.log.rows(at_time(8, 30), rid=f"{NSG_ID}/securityRules/r1",
                                op="Microsoft.Network/networkSecurityGroups/securityRules/write")
                + self.log.policy(at_time(10, 7, day=dt.datetime(2026, 10, 3, tzinfo=UTC)))
                + self.log.tags(at_time(9), rid=f"/subscriptions/{SUB}/resourceGroups/{RG}"))
        return self.inv_run(nsg_and_rg(), rows, anchors=anchors)

    def delete(self):
        return self.inv_run(nsg_drift("delete"), self.log.write(at_time(8)) + self.log.delete(at_time(9)),
                            anchors=None)

    def public(self, result) -> dict:
        text, problems = inv.publish(result.document)
        self.assertEqual(problems, [])
        return json.loads(text)


class ProjectionTests(_PubBase):
    def scenarios(self):
        failed_input = self.inv_run(paths=self.plan(nsg_drift()), report=b"{}", source=NoCallSource(), rows=None)
        evidence_failed = self.inv_run(rows=None, source=FakeSource({RG: [al.SourceError("throttled", 429)]}))
        unreadable = self.inv_run(rows=[ev(9999, ts="2026-10-02T07:30:00Z", operationName={"value": "bad name"})])
        no_drift = self.inv_run(paths=self.plan(in_sync()), source=NoCallSource())
        return {"rich": self.rich(), "delete": self.delete(), "failed_input": failed_input,
                "evidence_failed": evidence_failed, "unreadable": unreadable, "no_drift": no_drift}

    def test_every_scenario_projects_cleanly(self):
        for name, result in self.scenarios().items():
            with self.subTest(name):
                text, problems = inv.publish(result.document)
                self.assertEqual(problems, [])
                self.assertEqual(text, inv.publish(result.document)[0])  # byte-identical
                document = pub.load_public(text.encode())
                self.assertEqual(pub.render_public(document), text)
                self.assertEqual(inv.verify_projection(document, result.document), [])
                self.assertEqual(pub.leak_findings(json.loads(text)), [])

    def test_no_restricted_value_crosses(self):
        for name, result in self.scenarios().items():
            with self.subTest(name):
                text, _ = inv.publish(result.document)
                restricted = result.document
                secrets = {restricted.binding.evidence_sha256, hashlib.sha256(
                    inv.render_investigation(restricted).encode()).hexdigest()}
                secrets |= {c.candidate for c in restricted.anchor_candidates.accepted}
                secrets |= {c.candidate for c in restricted.anchor_candidates.rejected}
                for r in restricted.resources:
                    secrets |= {r.resource_id, r.actor_attribution.caller}
                    for op in r.operations:
                        secrets |= {op.caller, op.correlation_id, *op.event_ids, *op.attached_event_ids}
                    secrets |= {a.event_id for a in r.automated_events}
                    if r.deletion_rule is not None:
                        secrets |= {r.deletion_rule.caller, *r.deletion_rule.decisive_event_ids,
                                    *r.deletion_rule.candidate_event_ids}
                for secret in secrets - {None}:
                    self.assertNotIn(secret, text)
                for word in ("caller\"", "resource_id", "event_id\"", "correlation_id\"", "evidence_sha256",
                             "candidate\""):
                    self.assertNotIn(f'"{word}', text.replace('"caller_identity"', "").replace(
                        '"resource_id": "withheld"', "").replace('"event_id": "withheld"', "").replace(
                        '"correlation_id": "withheld"', ""))

    def test_exact_schema(self):
        document = self.public(self.rich())
        delete = self.public(self.delete())
        self.assertEqual(set(document), {"public_version", "exposure", "rules", "outcome", "failure", "binding",
                                         "completeness", "anchors", "resources"})
        self.assertEqual(document["exposure"], {"caller_identity": "withheld", "resource_id": "withheld",
                                                "event_id": "withheld", "correlation_id": "withheld",
                                                "who_path": "local_only"})
        self.assertEqual(set(document["binding"]), {"run_id", "plan_timestamp", "drift_report_sha256",
                                                    "evidence_outcome", "observation"})
        self.assertEqual(document["anchors"], {"examined": 2, "accepted": 1,
                                               "rejected": {"not_a_candidate": 1, "wrong_branch": 1}})
        nsg = next(r for r in document["resources"] if r["address"] == NSG_ADDR)
        self.assertEqual(set(nsg), {"address", "drift_action", "relevant_areas", "window", "verdict", "reason",
                                    "decisive_operation", "property_link", "property_link_reason", "deletion_rule",
                                    "actor_attribution", "unreadable_events_in_scope", "operations",
                                    "automated_events", "descendant_events", "descendant_operations"})
        self.assertEqual(nsg["window"]["anchor"]["run_id"], "github-400-1")
        self.assertEqual(set(nsg["window"]["anchor"]), {"run_id", "plan_timestamp", "started_at", "finished_at",
                                                        "report_sha256"})
        self.assertEqual(set(nsg["operations"][0]), {
            "op_id", "operation_name", "outcome", "relations", "start", "end", "available_at", "timing",
            "in_window", "role", "capable_areas", "caller_status", "caller_type", "client_app",
            "pipeline_identity", "attached_events"})
        self.assertEqual(nsg["operations"][0]["attached_events"], 1)
        self.assertEqual(nsg["automated_events"][0]["ref"], "auto-1")
        self.assertEqual(set(nsg["automated_events"][0]), {"ref", "operation_name", "category", "event_timestamp",
                                                           "timing", "in_window", "signal"})
        self.assertEqual(set(nsg["actor_attribution"]), {"status", "rule", "claim"})
        rule = delete["resources"][0]["deletion_rule"]
        self.assertEqual(set(rule), {"status", "reason", "rule", "claim", "anchor_kind", "anchor_time",
                                     "anchor_run_id", "decisive_events", "candidate_events", "related_events",
                                     "after_detection_events"})
        self.assertEqual((rule["status"], rule["decisive_events"]), ("confirmed", 2))
        self.assertEqual(delete["resources"][0]["actor_attribution"],
                         {"status": "confirmed", "rule": "external_deletion_v1", "claim": "recorded_successful_delete"})

    def test_unknown_fields_are_rejected(self):
        document = self.public(self.rich())
        for path in ([], ["exposure"], ["binding"], ["anchors"], ["resources", 0], ["resources", 0, "operations", 0],
                     ["resources", 0, "actor_attribution"]):
            for name in ("caller", "resource_id", "event_ids", "evidence_sha256", "extra"):
                with self.subTest(path=path, name=name):
                    changed = copy.deepcopy(document)
                    node = changed
                    for key in path:
                        node = node[key]
                    node[name] = "x"
                    with self.assertRaises(ValidationError):
                        pub.PublicInvestigation.model_validate(changed)


class LeakScanTests(_PubBase):
    def test_kinds(self):
        for sample, kind in ((SAMPLES["upn"], "at_sign"), (SAMPLES["object_id"], "guid"),
                             (SAMPLES["subscription"], "subscriptions_path"), (SAMPLES["arm_id"], "providers_path"),
                             (SAMPLES["ipv4"], "ip_address"), (SAMPLES["ipv6"], "ip_address"),
                             ("fe80::1%eth0 x", "ip_address"), (SAMPLES["url"], "url"), ("www.example.com", "url"),
                             ("see [10.0.0.1]", "ip_address")):
            with self.subTest(sample):
                self.assertIn(kind, " ".join(pub.leak_findings({"a": sample})))

    def test_no_false_positives_on_allowed_content(self):
        allowed = ["2026-10-04T11:04:56.093597Z", "Microsoft.Resources/tags/write",
                   'module.resource_group.azurerm_resource_group.this["main"]', "a" * 64, "github-37197574080-1",
                   "local-20261001T171607Z-23099", "1.14.7", "10:00:00", "2026-10-04T11:06:49Z", "op-12",
                   "microsoft.network/networksecuritygroups/securityrules/write", "unreadable_events_in_scope"]
        self.assertEqual(pub.leak_findings(allowed), [])

    def test_findings_never_echo_the_value(self):
        findings = pub.leak_findings({"descendant_operations": {SAMPLES["upn"]: 1}, "x": SAMPLES["ipv4"]})
        self.assertTrue(findings)
        for finding in findings:
            for sample in SAMPLES.values():
                self.assertNotIn(sample, finding)

    def test_a_planted_value_in_every_public_string_is_caught(self):
        document = self.public(self.rich())
        sites = list(leaves(document))
        self.assertGreater(len(sites), 100)
        for path, kind in sites:
            for name, sample in SAMPLES.items():
                with self.subTest(path=path, kind=kind, sample=name):
                    changed = copy.deepcopy(document)
                    plant(changed, path, kind, sample)
                    self.assertTrue(pub.leak_findings(changed))
                    with self.assertRaises(pub.PublicInvestigationError) as ctx:
                        pub.load_public(json.dumps(changed).encode())
                    self.assertEqual(ctx.exception.code, "leak")


class ConsistencyTests(_PubBase):
    def test_tampering_is_caught(self):
        result = self.rich()
        document = self.public(result)
        nsg = next(i for i, r in enumerate(document["resources"]) if r["address"] == NSG_ADDR)
        cases = {
            "verdict": lambda d: d["resources"][nsg].update(verdict="ambiguous", reason="unclassified_operation",
                                                            decisive_operation=None),
            "caller type": lambda d: d["resources"][nsg]["operations"][0].update(caller_type="service_principal"),
            "client": lambda d: d["resources"][nsg]["operations"][0].update(client_app="azure_cli"),
            "start": lambda d: d["resources"][nsg]["operations"][0].update(start="2026-10-02T07:00:00.000000Z"),
            "attached": lambda d: d["resources"][nsg]["operations"][0].update(attached_events=0),
            "automated timing": lambda d: d["resources"][nsg]["automated_events"][0].update(
                timing="before_observation", signal=True),
            "rejected counts": lambda d: d["anchors"]["rejected"].update(wrong_branch=2),
            "binding": lambda d: d["binding"].update(drift_report_sha256="0" * 64),
            "anchor run": lambda d: d["resources"][nsg]["window"]["anchor"].update(run_id="github-1-1"),
            "polls": lambda d: d["completeness"].update(polls=9),
            "descendants": lambda d: d["resources"][nsg].update(descendant_events=0, descendant_operations={}),
            "resources": lambda d: d["resources"].pop(),
            "pipeline": lambda d: d["resources"][nsg]["operations"][0].update(pipeline_identity=True),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                changed = copy.deepcopy(document)
                mutate(changed)
                self.assertTrue(inv.verify_projection(pub.PublicInvestigation.model_validate(changed),
                                                      result.document))

    def test_publish_refuses_leaks_contract_and_mismatch(self):
        result = self.rich()
        real = inv.project

        def with_change(change):
            def patched(document):
                projected = real(document)
                change(projected)
                return projected
            return patched

        cases = {
            "leak": lambda p: p["binding"].update(run_id="alice@example.com"),
            "contract": lambda p: p.update(caller="x"),
            "mismatch": lambda p: p["completeness"].update(polls=7),
        }
        for name, change in cases.items():
            with self.subTest(name), mock.patch.object(inv, "project", with_change(change)):
                text, problems = inv.publish(result.document)
                self.assertIsNone(text)
                self.assertTrue(problems)
                for problem in problems:
                    self.assertNotIn("alice", problem)


class PublicContractTests(_PubBase):
    """The public model's own invariants (relied on by consumers such as Task 9B.4)."""

    def test_invariants(self):
        document = self.public(self.rich())
        delete = self.public(self.delete())
        nsg = next(i for i, r in enumerate(document["resources"]) if r["address"] == NSG_ADDR)
        cases = {
            "op numbering": (document, lambda d: d["resources"][nsg]["operations"][0].update(op_id="op-5")),
            "auto numbering": (document, lambda d: d["resources"][nsg]["automated_events"][0].update(ref="auto-3")),
            "decisive missing": (document, lambda d: d["resources"][nsg].update(decisive_operation="op-9")),
            "decisive without verdict": (document, lambda d: d["resources"][nsg].update(
                verdict="ambiguous", reason="unclassified_operation")),
            "update confirmed": (document, lambda d: d["resources"][nsg].update(property_link="confirmed")),
            "actor mismatch": (delete, lambda d: d["resources"][0]["actor_attribution"].update(
                status="not_confirmed", rule=None, claim=None)),
            "unreadable sole": (document, lambda d: d["resources"][nsg].update(unreadable_events_in_scope=True)),
            "descendant sum": (document, lambda d: d["resources"][nsg].update(descendant_events=9)),
            "addresses": (document, lambda d: d["resources"].reverse()),
            "failure": (document, lambda d: d.update(outcome="failed")),
            "stage reason": (document, lambda d: d.update(outcome="failed", failure={"stage": "input",
                                                                                      "reason": "evidence_failed"})),
            "rejected order": (document, lambda d: d["anchors"].update(rejected={"wrong_branch": 1,
                                                                                 "not_a_candidate": 1})),
            "window anchor": (document, lambda d: d["resources"][nsg]["window"].update(anchor=None)),
            "anchor run id": (document, lambda d: d["resources"][nsg]["window"]["anchor"].update(run_id="local-1")),
        }
        for name, (base, mutate) in cases.items():
            with self.subTest(name):
                changed = copy.deepcopy(base)
                mutate(changed)
                with self.assertRaises(ValidationError):
                    pub.PublicInvestigation.model_validate(changed)

    def test_loader_errors(self):
        self.assertEqual(self._code(b'{"a": NaN}'), "invalid_json")
        self.assertEqual(self._code(b'{"a": 1, "a": 1}'), "invalid_json")
        self.assertEqual(self._code(b"\xff"), "invalid_json")
        with mock.patch.object(pub, "MAX_INPUT_BYTES", 5):
            self.assertEqual(self._code(b"{" + b" " * 10 + b"}"), "too_large")
        with self.assertRaises(ValueError):
            pub.PublicInvestigationError("made_up")
        document = pub.PublicInvestigation.model_validate(self.public(self.rich()))
        for report in (b"{", b"[]"):
            with self.subTest(report), self.assertRaises(pub.PublicInvestigationError):
                pub.check_binding(document, report)

    def _code(self, data: bytes) -> str:
        with self.assertRaises(pub.PublicInvestigationError) as ctx:
            pub.load_public(data)
        return ctx.exception.code

    def test_verify_projection_structure(self):
        result = self.rich()
        document = self.public(result)
        nsg = next(i for i, r in enumerate(document["resources"]) if r["address"] == NSG_ADDR)
        for name, mutate in {
            "window": lambda d: d["resources"][nsg].update(window=None),
            "operations": lambda d: d["resources"][nsg]["operations"].append(dict(
                d["resources"][nsg]["operations"][-1], op_id=f"op-{len(d['resources'][nsg]['operations']) + 1}",
                start="2026-10-03T09:00:00.000000Z", end="2026-10-03T09:00:00.000000Z")),
            "automated": lambda d: d["resources"][nsg]["automated_events"].clear(),
        }.items():
            with self.subTest(name):
                changed = copy.deepcopy(document)
                mutate(changed)
                self.assertTrue(inv.verify_projection(pub.PublicInvestigation.model_validate(changed),
                                                      result.document))


class LeakyRestrictedTests(_PubBase):
    def test_a_consistent_but_leaky_document_is_refused(self):
        restricted = self.rich().document
        for sample in SAMPLES.values():
            with self.subTest(sample):
                leaky = inv.DriftInvestigation.model_validate(dict(
                    restricted.model_dump(mode="json"),
                    binding=dict(restricted.binding.model_dump(mode="json"), run_id=sample)))
                text, problems = inv.publish(leaky)
                self.assertIsNone(text)
                self.assertTrue(problems and all(p.startswith("leak ") for p in problems))
                self.assertEqual(inv.verify_projection(pub.PublicInvestigation.model_validate(inv.project(leaky)),
                                                       leaky), [])


class CliTests(_PubBase):
    def main(self, args, source=None, env=None):
        out, err = io.StringIO(), io.StringIO()
        clock = FakeClock()
        with mock.patch.object(cli, "_activity_log_source", return_value=source or FakeSource()), \
                mock.patch.object(cli, "_now", clock), mock.patch.object(cli, "_sleep", clock.sleep), \
                mock.patch.dict(os.environ, env if env is not None else NO_CI, clear=True), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(args)
        return code, out.getvalue(), err.getvalue()

    def investigate_args(self, paths, *extra):
        directory = self.dir("cli")
        self.report = os.path.join(directory, "drift_report.json")
        with open(self.report, "wb") as fh:
            fh.write(report_bytes(paths))
        self.restricted = os.path.join(directory, "restricted.json")
        self.evidence = os.path.join(directory, "evidence.json")
        self.public_file = os.path.join(directory, "drift_investigation.json")
        return ["investigate", "--plan", paths[0], "--manifest", paths[1], "--report", self.report,
                "--output", self.restricted, "--evidence-output", self.evidence, "--public-output", self.public_file,
                *extra]

    def test_public_output_and_check(self):
        paths = self.plan(nsg_drift())
        code, out, err = self.main(self.investigate_args(paths), FakeSource({RG: [page(*self.log.tags(at_time(8)))]}))
        self.assertEqual(code, 0, err)
        self.assertIn("Public investigation:", out)
        public = open(self.public_file, "rb").read()
        pub.check_binding(pub.load_public(public), open(self.report, "rb").read())
        self.assertNotIn(CALLER, public.decode())
        code, out, _ = self.main(["investigation-check", "--public", self.public_file, "--report", self.report])
        self.assertEqual((code, "public_investigation=valid" in out), (0, True))

    def test_public_failure_writes_nothing(self):
        paths = self.plan(nsg_drift())
        with mock.patch.object(inv, "publish", return_value=(None, ["leak $.x: at_sign"])):
            code, _, err = self.main(self.investigate_args(paths), FakeSource({RG: [page(*self.log.tags(at_time(8)))]}))
        self.assertEqual(code, 70)
        for path in (self.public_file, self.restricted, self.evidence):
            self.assertFalse(os.path.exists(path))

    def test_check_rejections(self):
        paths = self.plan(nsg_drift())
        self.main(self.investigate_args(paths), FakeSource({RG: [page(*self.log.tags(at_time(8)))]}))
        good = open(self.public_file, "rb").read()
        directory = self.dir("check")
        cases = {
            "leak": good.replace(b'"github-500-1"', b'"alice@example.com"'),
            "invalid_json": b"{",
            "contract": json.dumps({k: v for k, v in json.loads(good).items() if k != "rules"}).encode(),
        }
        for code_name, data in cases.items():
            with self.subTest(code_name):
                path = os.path.join(directory, f"{code_name}.json")
                with open(path, "wb") as fh:
                    fh.write(data)
                code, out, err = self.main(["investigation-check", "--public", path])
                self.assertEqual(code, 1)
                self.assertIn(f"PUBLIC INVESTIGATION REJECTED [{code_name}]", err)
                self.assertNotIn("alice", err + out)
        other = os.path.join(directory, "other_report.json")
        with open(other, "wb") as fh:
            fh.write(report_bytes(self.plan(nsg_drift("other"))))
        code, _, err = self.main(["investigation-check", "--public", self.public_file, "--report", other])
        self.assertEqual((code, "[binding_mismatch]" in err), (1, True))
        code, _, err = self.main(["investigation-check", "--public", self.public_file, "--report",
                                  os.path.join(directory, "missing")])
        self.assertEqual((code, "[binding_mismatch]" in err), (1, True))
        code, _, err = self.main(["investigation-check", "--public", os.path.join(directory, "missing")])
        self.assertEqual((code, "[invalid_json]" in err), (1, True))


class HardeningTests(_PubBase):
    main = CliTests.main

    def test_restricted_stdout_is_refused_in_github_actions(self):
        paths = self.plan(nsg_drift())
        report = os.path.join(self.dir("r"), "drift_report.json")
        with open(report, "wb") as fh:
            fh.write(report_bytes(paths))
        evidence = os.path.join(self.dir("e"), "evidence.json")
        with open(evidence, "w") as fh:
            fh.write(al.render_evidence(al.collect_evidence(*paths, source=FakeSource(),
                                                            queried_at=dt.datetime(2026, 10, 3, 10, 15, tzinfo=UTC))))
        commands = {
            "activity-logs": ["activity-logs", "--plan", paths[0], "--manifest", paths[1]],
            "attribute": ["attribute", "--report", report, "--evidence", evidence],
            "investigate": ["investigate", "--plan", paths[0], "--manifest", paths[1], "--report", report],
        }
        for name, args in commands.items():
            with self.subTest(name):
                code, out, err = self.main(args, NoCallSource(), env={"GITHUB_ACTIONS": "true"})
                self.assertEqual((code, out), (2, ""))
                self.assertIn("needs --output", err)
                # locally standard output still works
                code, out, _ = self.main(args, FakeSource())
                self.assertNotEqual(code, 2)
                self.assertTrue(out)

    def test_errors_never_print_restricted_values(self):
        paths = self.plan(nsg_drift())
        planted = ValueError(f"input_value={{'caller': '{CALLER}', 'resource_id': '{NSG_ID}'}}")
        directory = self.dir("x")
        args = {
            "activity-logs": (al, "collect_evidence", ["activity-logs", "--plan", paths[0], "--manifest", paths[1],
                                                       "--output", os.path.join(directory, "a.json")]),
            "attribute": (at, "attribute_files", ["attribute", "--report", paths[0], "--evidence", paths[0],
                                                  "--output", os.path.join(directory, "b.json")]),
            "investigate": (inv, "investigate", ["investigate", "--plan", paths[0], "--manifest", paths[1], "--report",
                                                 paths[0], "--output", os.path.join(directory, "c.json")]),
            "who": (who, "run_who", ["who", "--public", paths[0], "--terraform", paths[0], "--output-dir", directory]),
        }
        for name, (module, function, argv) in args.items():
            with self.subTest(name), mock.patch.object(module, function, side_effect=planted):
                code, out, err = self.main(argv + ["--log-level", "debug"])
                self.assertEqual(code, 70)
                self.assertIn("INTERNAL ERROR: unexpected ValueError.", err)
                self.assertNotIn(CALLER, out + err)
                self.assertNotIn(NSG_ID, out + err)
        # analyze keeps its detailed message (no restricted data)
        with mock.patch.object(cli, "evaluate", side_effect=RuntimeError("boom")):
            code, _, err = self.main(["analyze", "--plan", paths[0], "--manifest", paths[1]])
        self.assertIn("RuntimeError: boom", err)


class BoundaryTests(unittest.TestCase):
    FORBIDDEN = ("drift_engine.activity_logs", "drift_engine.attribution", "drift_engine.investigation",
                 "drift_engine.who")

    @unittest.skipIf(pub is None, "drift_engine is not installed")
    def test_importing_the_public_module_loads_no_restricted_module(self):
        code = ("import json, sys; import drift_engine.investigation_public; "
                "print(json.dumps(sorted(m for m in sys.modules if m == 'azure' or m.startswith('azure.') "
                f"or m in {list(self.FORBIDDEN)!r})))")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                             env=dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src")))
        self.assertEqual(json.loads(out.stdout), [])

    def test_ai_engine_never_imports_restricted_modules(self):
        names = {"activity_logs", "attribution", "investigation", "who"}
        offenders = []
        for directory, _, files in os.walk(os.path.join(ROOT, "src", "ai_engine")):
            for file in files:
                if not file.endswith(".py"):
                    continue
                path = os.path.join(directory, file)
                tree = ast.parse(open(path, encoding="utf-8").read(), path)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        bad = [a.name for a in node.names if a.name in self.FORBIDDEN]
                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        bad = [module] if module in self.FORBIDDEN else [
                            f"{module}.{a.name}" for a in node.names if module == "drift_engine" and a.name in names]
                    else:
                        continue
                    offenders += [f"{os.path.relpath(path, ROOT)}: {b}" for b in bad]
        self.assertEqual(offenders, [])

    @unittest.skipIf(pub is None, "drift_engine is not installed")
    def test_constants_match_the_restricted_modules(self):
        self.assertEqual(pub.AREAS, inv.AREAS)
        self.assertEqual(pub.VERDICTS, inv.VERDICTS)
        self.assertEqual(pub.DECISIVE_VERDICTS, inv.DECISIVE_VERDICTS)
        self.assertEqual(pub.AMBIGUOUS_REASONS, inv.AMBIGUOUS_REASONS)
        self.assertEqual(pub.PRECONDITION_REASONS, inv.PRECONDITION_REASONS)
        self.assertEqual(pub.PROPERTY_LINK_REASONS, inv.PROPERTY_LINK_REASONS)
        self.assertEqual(pub.ANCHOR_REJECTIONS, inv.ANCHOR_REJECTIONS)
        self.assertEqual(pub.FAILURE_REASONS, inv.FAILURE_REASONS)
        self.assertEqual(set(pub.DELETION_REASONS), set(at.REASONS))
        self.assertEqual(pub.CALLER_TYPES, al.CALLER_TYPES)
        self.assertEqual(pub.CLIENT_APPS, al.CLIENT_APP_VALUES)
        self.assertIs(inv.canonical_sha256, pub.canonical_sha256)


# ---------------------------------------------------------------------------
# Safeguard mutants: projection, leak scan, who matching, CLI guards
# ---------------------------------------------------------------------------

MUTANTS = {
    "investigation_public": {
        "leak-at-sign-dropped": ('    if "@" in text:', '    if False:'),
        "leak-guid-dropped": ('    if _GUID.search(text):', '    if False:'),
        "leak-ip-dropped": ('    if _ip_like(text):', '    if False:'),
        "leak-providers-dropped": ('    if "/providers/" in lowered:', '    if False:'),
        "leak-subscriptions-dropped": ('    if "/subscriptions/" in lowered:', '    if False:'),
        "leak-url-dropped": ('    if _URL.search(text):', '    if False:'),
        "leak-keys-not-scanned": ('            findings += [f"{path}.{segment}<key>: {kind}" for kind in _string_findings(str(key))]',
                                  '            pass'),
        "load-skips-leak-scan": ('    findings = leak_findings(raw)\n    if findings:', '    findings = []\n    if findings:'),
        "extra-fields-allowed": ('    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)',
                                 '    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)'),
        "binding-hash-unchecked": ('    if (binding.drift_report_sha256 != canonical_sha256(report) or binding.run_id != run.get("run_id")',
                                   '    if (binding.run_id != run.get("run_id")'),
    },
    "investigation": {
        "attached-count-zero": ('"pipeline_identity": op.pipeline_identity, "attached_events": len(op.attached_event_ids),',
                                '"pipeline_identity": op.pipeline_identity, "attached_events": 0,'),
        "publish-skips-leak-scan": ('    problems += [f"leak {finding}" for finding in pub.leak_findings(public.model_dump(mode="json"))]',
                                    '    pass'),
        "publish-skips-consistency": ('    problems = verify_projection(public, document)\n', '    problems = []\n'),
        "verify-ignores-operations": ('''        for pop, rop in zip(p.operations, r.operations):''',
                                      '''        for pop, rop in []:'''),
    },
    "who": {
        "start-not-compared": ('and al.format_timestamp(g.start) == op.start and al.format_timestamp(g.end) == op.end',
                               'and al.format_timestamp(g.end) == op.end'),
        "client-not-compared": ('and g.caller_type == op.caller_type and g.client_app == op.client_app]',
                                'and g.caller_type == op.caller_type]'),
        "multiple-accepted": ('    if len(matches) > 1:\n        return dict(result, status="multiple_matches")',
                              '    if False:\n        pass'),
        "retention-ignored": ('    if start < now - RETENTION:', '    if False:'),
        "ci-refusal-removed": ('    if environ.get("GITHUB_ACTIONS") == "true":', '    if False:'),
        "address-check-removed": ('        if rid is None:\n            return _failed(public, "address_unknown", now)',
                                  '        if rid is None:\n            continue'),
    },
    "cli": {
        "stdout-refusal-removed": ('    if os.environ.get("GITHUB_ACTIONS") == "true" and args.output is None:',
                                   '    if False:'),
        "restricted-errors-verbose": ('        if command in _RESTRICTED_COMMANDS:\n            # restricted data',
                                      '        if False:\n            # restricted data'),
        "public-check-skipped": ('        public_text, public_problems = investigation.publish(document)',
                                 '        public_text, public_problems = investigation.publish(document)[0], []'),
    },
}


@unittest.skipIf(pub is None, "drift_engine is not installed (pip install -e '.[dev]')")
class SafeguardMutationTests(_PubBase):
    """Each mutant removes one safeguard from an in-process copy of a module (the
    repository files are never changed) and must change at least one probe's result."""

    def load(self, name: str, source: str, real):
        module = types.ModuleType(f"{real.__name__}_mutant_{name.replace('-', '_')}")
        module.__file__ = f"<mutant {name}>"
        sys.modules[module.__name__] = module
        exec(compile(source, module.__file__, "exec"), module.__dict__)
        return module

    def probes(self, modules: dict) -> dict:
        p, i, w, c = modules["investigation_public"], modules["investigation"], modules["who"], modules["cli"]
        self.log = __import__("test_investigation").Log()
        results = {}
        rich = self.rich()
        restricted = rich.document

        def attempt(fn):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001  (a mutant may break something)
                return type(exc).__name__

        public_text, problems = i.publish(restricted)
        results["publish"] = (public_text, tuple(problems))
        document = json.loads(inv.publish(restricted)[0])
        for name, sample in SAMPLES.items():
            results[f"scan-{name}"] = tuple(p.leak_findings({"a": sample}))
        results["scan-key"] = tuple(p.leak_findings({"k": {SAMPLES["upn"]: 1}}))
        leaky = copy.deepcopy(document)
        leaky["binding"]["run_id"] = SAMPLES["upn"]
        results["load-leak"] = attempt(lambda: p.load_public(json.dumps(leaky).encode()))
        extra = copy.deepcopy(document)
        extra["caller"] = "x"
        results["load-extra"] = attempt(lambda: p.load_public(json.dumps(extra).encode()))
        other = report_bytes(self.plan(nsg_and_rg(), plan_ts="2026-10-03T10:02:00Z"))
        results["binding"] = attempt(lambda: p.check_binding(p.PublicInvestigation.model_validate(
            dict(document, binding=dict(document["binding"], drift_report_sha256="0" * 64))), other))
        tampered = copy.deepcopy(document)
        tampered["resources"][0]["operations"][0]["client_app"] = "azure_cli"
        results["verify"] = tuple(i.verify_projection(pub.PublicInvestigation.model_validate(tampered), restricted))
        # a projection leak and a projection mismatch must be refused by publish
        with mock.patch.object(i, "project", lambda d, real=i.project: dict(
                real(d), binding=dict(real(d)["binding"], run_id=SAMPLES["upn"]))):
            results["publish-leak"] = attempt(lambda: i.publish(restricted)[0])
        with mock.patch.object(i, "project", lambda d, real=i.project: dict(
                real(d), completeness=dict(real(d)["completeness"], polls=9))):
            results["publish-mismatch"] = attempt(lambda: i.publish(restricted)[0])
        # consistent but leaky: the restricted document's own run id (free-form) carries a UPN
        leaky_restricted = inv.DriftInvestigation.model_validate(dict(
            restricted.model_dump(mode="json"), binding=dict(restricted.binding.model_dump(mode="json"),
                                                             run_id=SAMPLES["upn"])))
        results["publish-restricted-leak"] = attempt(lambda: i.publish(leaky_restricted)[0])
        # who
        rows = self.log.tags(at_time(8))
        public = inv.publish(self.inv_run(nsg_drift(), rows).document)[0].encode()
        state = __import__("test_who").state_json({NSG_ADDR: NSG_ID})
        now = dt.datetime(2026, 10, 4, 9, tzinfo=UTC)

        def run(source_rows, when=now, environ=NO_CI, terraform=state):
            return attempt(lambda: w.run_who(public, terraform, source=FakeSource({RG: [page(*source_rows)]}),
                                             now=when, environ=environ).document)

        shifted = __import__("test_who").shift(rows, milliseconds=500)
        moved = [dict(r, eventTimestamp=s["eventTimestamp"]) if i_ == 0 else r
                 for i_, (r, s) in enumerate(zip(rows, shifted))]
        twin = [dict(r, eventDataId=r["eventDataId"].replace("9000", "9100"), correlationId="corr-twin") for r in rows]
        results["who-start"] = run(moved)
        results["who-client"] = run([dict(r, claims={"appid": "c44b4083-3bb0-49c1-b47d-974e53cbdf3c"}) for r in rows])
        results["who-multiple"] = run(rows + twin)
        results["who-retention"] = run(rows, when=at_time(8) + dt.timedelta(days=91))
        results["who-ci"] = run(rows, environ={"GITHUB_ACTIONS": "true"})
        results["who-address"] = run(rows, terraform=__import__("test_who").state_json({}))
        # cli guards
        paths = self.plan(nsg_drift())
        report = os.path.join(self.dir("m"), "drift_report.json")
        with open(report, "wb") as fh:
            fh.write(report_bytes(paths))

        def cli_run(argv, env, patches=None):
            out, err = io.StringIO(), io.StringIO()
            clock = FakeClock()
            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(c, "_activity_log_source", return_value=FakeSource(
                    {RG: [page(*self.log.tags(at_time(8)))]})))
                stack.enter_context(mock.patch.object(c, "_now", clock))
                stack.enter_context(mock.patch.object(c, "_sleep", clock.sleep))
                stack.enter_context(mock.patch.dict(os.environ, env, clear=True))
                for (module, name), value in (patches or {}).items():
                    stack.enter_context(mock.patch.object(module, name, value))
                stack.enter_context(contextlib.redirect_stdout(out))
                stack.enter_context(contextlib.redirect_stderr(err))
                code = c.main(argv)
            return code, CALLER in out.getvalue() + err.getvalue()

        results["cli-stdout"] = cli_run(["investigate", "--plan", paths[0], "--manifest", paths[1], "--report", report],
                                        {"GITHUB_ACTIONS": "true"})
        planted = mock.Mock(side_effect=ValueError(f"input_value={CALLER}"))
        results["cli-error"] = cli_run(["investigate", "--plan", paths[0], "--manifest", paths[1], "--report", report,
                                        "--output", os.path.join(self.tmp, "o.json")], NO_CI,
                                       {(c.investigation, "investigate"): planted})
        public_out = os.path.join(self.dir("pubout"), "p.json")
        bad_publish = mock.Mock(return_value=(None, ["leak"]))
        results["cli-public"] = (cli_run(["investigate", "--plan", paths[0], "--manifest", paths[1], "--report", report,
                                          "--output", os.path.join(self.tmp, "q.json"), "--public-output", public_out],
                                         NO_CI, {(c.investigation, "publish"): bad_publish}),
                                 os.path.exists(public_out))
        return results

    def test_every_mutant_is_caught(self):
        reals = {"investigation_public": pub, "investigation": inv, "who": who, "cli": cli}
        sources = {name: open(module.__file__, encoding="utf-8").read() for name, module in reals.items()}
        baseline = self.probes(reals)
        survivors = []
        for target, mutants in MUTANTS.items():
            for name, (old, new) in mutants.items():
                with self.subTest(f"{target}:{name}"):
                    self.assertEqual(sources[target].count(old), 1, f"mutant {name} no longer matches")
                    modules = dict(reals)
                    modules[target] = self.load(name, sources[target].replace(old, new), reals[target])
                    if self.probes(modules) == baseline:
                        survivors.append(f"{target}:{name}")
        self.assertEqual(survivors, [])


if __name__ == "__main__":
    unittest.main()
