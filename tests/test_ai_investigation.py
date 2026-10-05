"""Task 9B.4: AI report v2 from the public drift investigation.

Public investigations are produced by the real pipeline: drift_engine.investigation
(Task 9B.2) over a fake Activity Log source, projected by `publish` (Task 9B.3). The
AI engine reads only that public document. Covered:

- report v2 on every scenario: the verified portal tag edit (sole), no anchor
  (latest), ambiguous (several candidates / one candidate), none,
  not-investigated (unreadable scope), deletion-confirmed, bindable failed
  investigations (evidence failure, input failure without resources), no drift,
  a non-drift resource next to a drifted one (D2), and no investigation at all;
- D1 caller statuses, D3 failure handling, `gap_seconds`, the fixed statements and
  the "not confirmed by available evidence" wording;
- recommendation policy v1 over every option fixture;
- loading and binding (leak, contract, binding, scope, observation) and the CLI
  (exit 1 for every rejected investigation, exit 70 when verification fails, D4);
- verify_report v2 against investigation tampering;
- fake-model tests: a valid interpretation accepted; actor naming, identity strings,
  causal / proof upgrades, invented times / operations / references and consistency
  upgrades rejected; deterministic state identical with and without the LLM; the
  restricted WHO data never reaches the prompt.

No Azure, network or real LLM (tests/conftest.py blocks non-loopback connections).
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import sys
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS)

from test_activity_logs import RG, RG_ADDR, FakeSource, NoCallSource, al, ev, raw_entry  # noqa: E402
from test_investigation import (  # noqa: E402
    RealShapeTests, at_time, in_sync, nsg_drift, public_report_bytes,
)
from test_investigation_public import _PubBase, inv, pub  # noqa: E402

HAS_AI_EXTRA = all(importlib.util.find_spec(m) for m in ("langgraph", "langchain_openai"))
if HAS_AI_EXTRA:
    from ai_engine import cli as ai_cli
    from ai_engine import verify
    from ai_engine.config import load_config
    from ai_engine.evidence import EVIDENCE_TAG, EvidenceIntegrityError, EvidenceLimits, build_investigation_evidence
    from ai_engine.graph import run_analysis
    from ai_engine.nodes.investigation_facts import NOT_CONFIRMED, InvestigationInputError, load_investigation
    from ai_engine.nodes.remediation import ACCEPT_REMOTE_NOTE
    from ai_engine.nodes.report_generator import render_markdown, write_report

TAGS_WRITE = "Microsoft.Resources/tags/write"
REAL_CALLER = "user@example.invalid"  # the sanitized fixture's recorded caller (restricted data)
VNET_ADDR = "module.network.azurerm_virtual_network.this"
EMPTY = {"findings": [], "summary": ""}
SECTION_KEYS = ("security_analysis", "cost_analysis", "configuration_analysis", "root_cause_analysis",
                "risk_assessment", "investigation_analysis")


def envelope(**sections) -> str:
    return json.dumps({key: sections.get(key, EMPTY) for key in SECTION_KEYS})


def finding(address, ops=("op-1",), consistency="consistent_with_drift",
            explanation="The recorded tags write is consistent with the drifted tags area.") -> dict:
    return {"address": address, "cited_operations": list(ops), "consistency": consistency,
            "explanation": explanation, "basis": "inference"}


class ScriptedLLM:
    def __init__(self, reply: str):
        self.reply, self.prompts = reply, []

    def invoke(self, messages):
        self.prompts.append(messages)
        return self.reply


def shown(messages) -> dict:
    return json.loads(re.search(rf"<{EVIDENCE_TAG}>\n(.*)\n</{EVIDENCE_TAG}>", messages[-1].content, re.S).group(1))


@unittest.skipUnless(HAS_AI_EXTRA and pub is not None, "needs the 'ai' extra and drift_engine")
class _AiBase(_PubBase, RealShapeTests):
    """Runs the real investigation, keeps the drift report it was bound to, and the AI engine over both."""

    def runTest(self):  # RealShapeTests' tests are not re-run here
        pass

    def inv_run(self, entries=None, rows=(), *, paths=None, report=None, **kwargs):
        paths = paths or self.plan(entries if entries is not None else nsg_drift())
        self.drift = json.loads(public_report_bytes(paths))  # what the AI engine reads (Task 9B.4A)
        return super().inv_run(entries, rows, paths=paths, report=report, **kwargs)

    def public(self, result) -> dict:
        text, problems = inv.publish(result.document)
        self.assertEqual(problems, [])
        return json.loads(text)

    def ai(self, result=None, *, llm=None, public=None):
        """(report, public) for the last investigation; verify_report must accept the report."""
        public = public if public is not None else (self.public(result) if result is not None else None)
        kwargs = {"llm": llm} if llm is not None else {"config": load_config({"AI_LLM_PROVIDER": "none"})}
        state = run_analysis(copy.deepcopy(self.drift), investigation=copy.deepcopy(public) if public else None,
                             **kwargs)
        report = json.loads(json.dumps(state["report"]))  # a plain copy: state containers are frozen
        self.assertEqual(verify.verify_report(report, self.drift, public), [])
        self.state = state
        return report, public

    @staticmethod
    def resource(report, address):
        return next(r for r in report["resources"] if r["address"] == address)

    def assert_no_restricted(self, report):
        """No recorded caller anywhere; the whole report (JSON and Markdown) is free of the withheld identifier
        classes (Task 9B.4A: WHAT comes from the public drift report); the investigation-derived parts also pass
        the full public leak scan."""
        from drift_engine.report_public import identifier_findings
        text = json.dumps(report) + render_markdown(report)
        for secret in (REAL_CALLER, "alice@example.com", "/subscriptions/", "/providers/"):
            self.assertNotIn(secret, text)
        self.assertEqual(identifier_findings(report), [])
        self.assertEqual(identifier_findings(render_markdown(report).replace("\u200b", "")), [])
        derived = [report["investigation"]] + [{k: r[k] for k in ("operations", "automated_events", "when", "who",
                                                                    "correlation")} for r in report["resources"]]
        self.assertEqual(pub.leak_findings(derived), [])


# --------------------------------------------------------------------------- report v2 on every scenario


class ScenarioTests(_AiBase):
    def test_verified_portal_tag_edit_meets_the_phase_acceptance(self):
        report, public = self.ai(self.real())
        self.assertEqual((report["report_version"], report["investigation"]["status"]), ("2", "complete"))
        self.assertEqual(report["provenance"]["investigation_sha256"], pub.canonical_sha256(public))
        r = self.resource(report, RG_ADDR)
        # WHAT (Terraform evidence)
        self.assertEqual((r["investigation_scope"], r["what"]["basis"], r["what"]["classification"]),
                         ("drift", "terraform_evidence", "external_drift"))
        self.assertEqual([c["path"] for c in r["what"]["changes"]], [["tags", "probe"]])
        # recorded operation (Activity Log evidence): one group, exact + extension, Succeeded
        [op] = r["operations"]
        self.assertEqual((op["op_id"], op["operation_name"], op["outcome"], op["relations"], op["timing"],
                          op["caller_identity"], op["basis"]),
                         ("op-1", TAGS_WRITE, "successful", ["exact", "extension"], "before_observation",
                          "withheld", "activity_log_evidence"))
        # WHEN: event time and detection time apart; gap = observation start - operation end
        when = r["when"]
        self.assertEqual((when["status"], when["event_start"], when["event_end"], when["available_at"]),
                         ("decisive_operation", "2026-10-04T11:04:56.093597Z", "2026-10-04T11:04:58.187357Z",
                          "2026-10-04T11:06:24.000000Z"))
        self.assertEqual(when["observation"], {"started_at": "2026-10-04T11:06:39.000000Z",
                                               "finished_at": "2026-10-04T11:06:57.000000Z"})
        self.assertEqual((when["plan_timestamp"], when["gap_seconds"]), ("2026-10-04T11:06:49Z", 100.812643))
        self.assertEqual(when["last_in_sync"]["run_id"], "github-37178020110-1")
        # WHO: recorded caller type and client, identity withheld; attribution not confirmed
        self.assertEqual(r["who"]["recorded_caller"], {
            "status": "recorded", "reason": None, "operation": "op-1", "candidate_operations": 1,
            "caller_type": "user", "client_app": "azure_portal", "pipeline_identity": None, "identity": "withheld"})
        self.assertEqual(r["who"]["actor_attribution"]["status"], "not_confirmed_by_available_evidence")
        # correlation
        corr = r["correlation"]
        self.assertEqual((corr["verdict"], corr["property_link"], corr["property_link_reason"]),
                         ("sole_capable_operation", "inferred_not_provable", "no_property_values_in_activity_log"))
        self.assertTrue(report["investigation"]["completeness"]["settled"])
        # recommendation R4 with the accept-remote note; approval required, nothing executed
        rec = r["remediation"]["recommendation"]
        self.assertEqual((rec["decision"], rec["policy_rule"], rec["kind"], rec["notes"]),
                         ("recommended", "R4", "restore_declared", [ACCEPT_REMOTE_NOTE]))
        self.assertEqual((rec["approval_required"], rec["execution_allowed"], rec["automatic_apply"]),
                         (True, False, False))
        # deterministic narrative without an LLM, with the fixed wording
        texts = [s["text"] for s in r["analysis"]["narrative"]]
        self.assertIn("Verdict sole_capable_operation: since the last in-sync observation, exactly one recorded "
                      f"operation (op-1, {TAGS_WRITE}) can explain every drifted property area (tags).", texts)
        self.assertIn("The operation ended 100.812643 s before the observation started.", texts)
        self.assertTrue(any(NOT_CONFIRMED in t and "Property link inferred_not_provable" in t for t in texts))
        self.assertTrue(any(t.startswith("Actor attribution: " + NOT_CONFIRMED) for t in texts))
        self.assertEqual(report["llm"]["attempted"], False)
        self.assert_no_restricted(report)

    def test_without_an_anchor_the_latest_operation_is_decisive(self):
        report, _ = self.ai(self.real(with_anchor=False))
        r = self.resource(report, RG_ADDR)
        self.assertEqual((r["correlation"]["verdict"], r["when"]["decisive_operation"], r["when"]["window"]["kind"],
                          r["when"]["last_in_sync"]), ("latest_capable_operation", "op-3", "lookback", None))
        self.assertEqual(r["who"]["recorded_caller"]["candidate_operations"], 3)
        ids = [s["id"] for s in r["analysis"]["narrative"]]
        self.assertIn("when.lookback.v1", ids)
        self.assertIn("who.azure_cli.v1", ids)  # azure_cli covers local Terraform with CLI auth
        self.assertIn("2 earlier candidate operation(s)", " ".join(s["text"] for s in r["analysis"]["narrative"]))

    def test_ambiguous_with_several_candidates_is_multiple_operations(self):
        report, _ = self.ai(self.inv_run(rows=self.log.tags(at_time(8)) + self.log.tags(at_time(9))))
        r = report["resources"][0]
        self.assertEqual((r["correlation"]["verdict"], r["correlation"]["reason"]),
                         ("ambiguous", "multiple_capable_operations"))
        caller = r["who"]["recorded_caller"]
        self.assertEqual((caller["status"], caller["candidate_operations"], caller["caller_type"]),
                         ("multiple_operations", 2, None))
        self.assertEqual((r["when"]["status"], r["when"]["event_start"], r["when"]["gap_seconds"]),
                         ("not_confirmed", None, None))
        self.assertEqual(r["when"]["statements"][0]["text"], f"Event time of the change: {NOT_CONFIRMED}.")
        self.assertEqual(len(r["operations"]), 2)  # each operation's caller data stays with the operation

    def test_ambiguous_with_one_candidate_has_no_decisive_operation(self):
        report, _ = self.ai(self.inv_run(rows=self.log.tags(at_time(8)) + self.log.policy(at_time(9))))
        r = report["resources"][0]
        self.assertEqual((r["correlation"]["verdict"], r["correlation"]["reason"]), ("ambiguous", "automated_activity"))
        self.assertEqual((r["who"]["recorded_caller"]["status"], r["who"]["recorded_caller"]["candidate_operations"]),
                         ("no_decisive_operation", 1))
        self.assertEqual(r["correlation"]["counts"]["automated_signals"], 1)
        self.assertEqual(r["automated_events"][0]["ref"], "auto-1")

    def test_no_capable_operation_found(self):
        report, _ = self.ai(self.inv_run(rows=()))
        r = report["resources"][0]
        self.assertEqual((r["correlation"]["verdict"], r["correlation"]["property_link"]),
                         ("no_capable_operation_found", "none"))
        self.assertEqual(r["who"]["recorded_caller"]["status"], "no_decisive_operation")
        text = " ".join(s["text"] for s in r["correlation"]["statements"])
        self.assertIn("This does not mean that no change happened.", text)
        self.assertIn(report["investigation"]["completeness"]["queried_at"], text)

    def test_unreadable_scope_is_not_investigated(self):
        bad = ev(9999, ts="2026-10-02T07:30:00Z", operationName={"value": "bad name"})
        report, _ = self.ai(self.inv_run(rows=[bad]))
        r = report["resources"][0]
        self.assertEqual(report["investigation"]["status"], "incomplete")
        self.assertEqual((r["correlation"]["status"], r["correlation"]["verdict"], r["correlation"]["reason"]),
                         ("not_investigated", "not_investigated", "unreadable_events_in_scope"))
        self.assertEqual(r["who"]["recorded_caller"]["status"], "not_investigated")
        self.assertIn(NOT_CONFIRMED, r["who"]["statements"][0]["text"])

    def test_confirmed_deletion(self):
        report, _ = self.ai(self.delete())
        r = report["resources"][0]
        corr, who = r["correlation"], r["who"]
        self.assertEqual((corr["verdict"], corr["property_link"], corr["deletion_rule"]["status"]),
                         ("latest_capable_operation", "confirmed", "confirmed"))
        self.assertEqual(who["actor_attribution"], {"status": "confirmed", "rule": "external_deletion_v1",
                                                    "claim": "recorded_successful_delete"})
        self.assertEqual(who["recorded_caller"]["identity"], "withheld")
        self.assertEqual(who["statements"][-1]["id"], "who.actor_confirmed.v1")
        # the investigation never changes the recommendation: recreating does not restore data (R2)
        rec = r["remediation"]["recommendation"]
        self.assertEqual((rec["decision"], rec["policy_rule"]), ("human_decision_required", "R2"))
        self.assert_no_restricted(report)

    def test_decisive_operation_without_a_single_recorded_caller(self):  # D1 not_recorded
        rows = self.log.tags(at_time(8))
        rows[1]["caller"] = "bob@example.com"
        for rows, reason in ((self.log.tags(at_time(8), caller=None), "caller_missing"),
                             (rows, "caller_inconsistent")):
            report, _ = self.ai(self.inv_run(rows=rows))
            r = report["resources"][0]
            self.assertEqual(r["correlation"]["verdict"], "sole_capable_operation")
            self.assertEqual(r["who"]["recorded_caller"], {
                "status": "not_recorded", "reason": reason, "operation": "op-1", "candidate_operations": 1,
                "caller_type": None, "client_app": None, "pipeline_identity": None, "identity": "withheld"})
            self.assertEqual(r["who"]["statements"][0]["text"],
                             f"Recorded caller of op-1: {NOT_CONFIRMED} ({reason}).")
            self.assert_no_restricted(report)
            self.assertNotIn("bob@example.com", json.dumps(report))

    def test_deletion_not_confirmed_by_the_rule(self):
        report, _ = self.ai(self.inv_run(nsg_drift("delete"), self.log.delete(at_time(9)), anchors=None))
        corr = report["resources"][0]["correlation"]
        self.assertEqual((corr["verdict"], corr["property_link"], corr["property_link_reason"]),
                         ("latest_capable_operation", "inferred_not_provable", "deletion_rule_not_confirmed"))
        ids = [s["id"] for s in corr["statements"]]
        self.assertIn("link.deletion_not_confirmed.v1", ids)
        self.assertEqual(report["resources"][0]["who"]["actor_attribution"]["status"],
                         "not_confirmed_by_available_evidence")

    def test_rule_confirmed_deletion_under_an_ambiguous_verdict_stays_inferred(self):  # Option A
        rows = (self.log.write(at_time(8)) + self.log.delete(at_time(9))
                + self.log.rows(at_time(9, 30), op="Microsoft.Network/networkSecurityGroups/foo/action"))
        report, public = self.ai(self.inv_run(nsg_drift("delete"), rows, anchors=None))
        self.assertEqual(public["resources"][0]["deletion_rule"]["status"], "confirmed")
        r = report["resources"][0]
        self.assertEqual((r["correlation"]["verdict"], r["correlation"]["property_link"],
                          r["correlation"]["property_link_reason"], r["who"]["actor_attribution"]["status"]),
                         ("ambiguous", "inferred_not_provable", "verdict_not_decisive",
                          "not_confirmed_by_available_evidence"))
        self.assertIn("link.not_decisive.v1", [s["id"] for s in r["correlation"]["statements"]])

    def test_update_drift_is_never_property_confirmed(self):
        for scenario in (self.real, lambda: self.real(with_anchor=False), self.rich):
            report, _ = self.ai(scenario())
            for r in report["resources"]:
                if r["investigation_scope"] == "drift" and r["what"]["action"] == "update":
                    self.assertNotEqual(r["correlation"]["property_link"], "confirmed")
                    self.assertNotEqual(r["who"]["actor_attribution"]["status"], "confirmed")

    def test_bindable_failed_investigation_marks_drift_not_investigated(self):  # D3
        result = self.inv_run(rows=None, source=FakeSource({RG: [al.SourceError("throttled", 429)]}))
        report, public = self.ai(result)
        self.assertEqual((public["outcome"], report["investigation"]["status"]), ("failed", "failed"))
        self.assertEqual(report["investigation"]["failure"], {"stage": "evidence", "reason": "evidence_failed"})
        for r in report["resources"]:
            self.assertEqual((r["correlation"]["verdict"], r["correlation"]["reason"]),
                             ("not_investigated", "investigation_failed"))
        self.assertTrue(any("investigation failed" in item for item in report["limitations"]))

    def test_input_failure_without_resources_is_still_bindable(self):  # D3
        result = self.inv_run(anchors=os.path.join(self.tmp, "missing-anchors"), rows=self.log.tags(at_time(8)))
        public = self.public(result)
        self.assertEqual((public["outcome"], public["failure"]["reason"], public["resources"]),
                         ("failed", "anchor_directory_unreadable", []))
        report, _ = self.ai(result)
        [r] = report["resources"]
        self.assertEqual(r["correlation"]["reason"], "investigation_failed")

    def test_unbindable_failed_investigation_is_rejected(self):  # D3
        result = self.inv_run(report=b"{}", source=NoCallSource(), rows=None)
        public = self.public(result)
        self.assertEqual((public["failure"]["reason"], public["binding"]["drift_report_sha256"]),
                         ("report_invalid", None))
        with self.assertRaises(InvestigationInputError) as ctx:
            load_investigation(public, self.drift)
        self.assertEqual(ctx.exception.code, "binding_mismatch")

    def test_no_drift_has_no_investigation_claims(self):
        report, _ = self.ai(self.inv_run(paths=self.plan(in_sync()), source=NoCallSource()))
        self.assertEqual((report["investigation"]["status"], report["resources"]), ("complete", []))
        self.assertIn("No changed resources: there are no investigation claims.", render_markdown(report))

    def test_non_drift_resource_is_not_applicable(self):  # D2
        drift, changes = nsg_drift()
        vnet_before = {"id": "vnet-id-placeholder", "name": "vnet", "address_space": ["10.0.0.0/16"]}
        vnet_after = dict(vnet_before, address_space=["10.1.0.0/16"])
        changes = changes + [raw_entry(VNET_ADDR, ["update"], vnet_before, vnet_after,
                                       rtype="azurerm_virtual_network")]
        report, _ = self.ai(self.inv_run((drift, changes), rows=self.log.tags(at_time(8))))
        vnet = self.resource(report, VNET_ADDR)
        self.assertEqual((vnet["what"]["classification"], vnet["investigation_scope"]), ("config_change", "not_drift"))
        self.assertEqual((vnet["when"]["status"], vnet["who"]["recorded_caller"]["status"],
                          vnet["who"]["actor_attribution"]["status"], vnet["correlation"]["status"],
                          vnet["correlation"]["verdict"], vnet["operations"]),
                         ("not_applicable",) * 4 + (None, []))
        self.assertEqual([o.rsplit("#", 1)[1] for o in vnet["remediation"]["option_ids"]], ["1", "2"])
        self.assertEqual(vnet["remediation"]["recommendation"]["kind"], "apply_pending_change")
        nsg_entry = next(r for r in report["resources"] if r["address"] != VNET_ADDR)
        self.assertEqual(nsg_entry["correlation"]["verdict"], "sole_capable_operation")

    def test_without_investigation_every_drifted_resource_is_not_investigated(self):
        self.real()
        report, _ = self.ai()
        self.assertEqual((report["investigation"]["status"], report["provenance"]["investigation_sha256"]),
                         ("not_available", None))
        r = self.resource(report, RG_ADDR)
        self.assertEqual((r["correlation"]["verdict"], r["correlation"]["reason"]),
                         ("not_investigated", "investigation_not_provided"))
        md = render_markdown(report)
        for line in ("Event time of the change:", "Recorded caller:", "Actor attribution:"):
            self.assertIn(line, md.replace("​", ""))
        self.assertGreaterEqual(md.count(NOT_CONFIRMED), 6)
        self.assertIn(f"- Gap between the operation end and the observation start: {NOT_CONFIRMED}", md)
        self.assertIn(f"- Last in-sync observation: {NOT_CONFIRMED}", md)
        # without an investigation the detection time is still known (Terraform evidence)
        self.assertEqual(r["when"]["observation"]["started_at"], "2026-10-04T11:06:39.000000Z")

    def test_markdown_order_and_determinism(self):
        result = self.rich()
        report, public = self.ai(result)
        md = render_markdown(report)
        headings = [line for line in md.splitlines() if line.startswith("## ")]
        self.assertEqual(headings, ["## Summary", "## What changed", "## Recorded Azure operations", "## When",
                                    "## Who", "## Correlation", "## Analysis", "## Recommendation & options",
                                    "## Limitations", "## Provenance"])
        a, _ = self.ai(public=public)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(report, sort_keys=True))
        paths = write_report(self.state, os.path.join(self.tmp, "out"))
        self.assertEqual(paths["markdown"].read_text(encoding="utf-8"), md)
        self.assertEqual(verify.verify_markdown(md, report), [])


# --------------------------------------------------------------------------- recommendation policy v1


POLICY_TABLE = {  # (group, fixture, address) -> (rule, recommended kind, accept-remote note)
    ("plan_evidence", "config_change", RG_ADDR): ("R4", "apply_pending_change", False),
    ("plan_evidence", "converged_drift", RG_ADDR): ("R3", "refresh_state_only", False),
    ("plan_evidence", "drift_and_config_change", RG_ADDR): ("R1", None, False),
    ("plan_evidence", "external_deletion", 'module.resource_group.azurerm_resource_group.this["ghost"]'):
        ("R2", None, False),
    ("plan_evidence", "external_drift", RG_ADDR): ("R4", "restore_declared", True),
    ("plan_evidence", "replace", RG_ADDR): ("R2", None, False),
    ("plan_evidence", "resource_added", 'module.resource_group.azurerm_resource_group.this["extra"]'):
        ("R4", "create_declared_object", False),
    ("plan_evidence", "resource_removed", RG_ADDR): ("R2", None, False),
    ("plan_evidence", "resource_removed", 'module.resource_group.azurerm_resource_group.this["other"]'):
        ("R4", "create_declared_object", False),
    ("cost_config_plans", "storage_added", "azurerm_storage_account.this"): ("R4", "create_declared_object", False),
    ("cost_config_plans", "storage_config_mix", "azurerm_storage_account.this"): ("R1", None, False),
    ("cost_config_plans", "storage_deleted_externally", "azurerm_storage_account.this"): ("R2", None, False),
    ("cost_config_plans", "vm_size_planned_change", "azurerm_linux_virtual_machine.this"):
        ("R4", "apply_pending_change", False),
    ("root_cause_plans", "importing_resource", "azurerm_storage_account.this"): ("R4", "apply_pending_change", False),
    ("root_cause_plans", "moved_resource", "azurerm_storage_account.this"): ("R4", "apply_pending_change", False),
    ("root_cause_plans", "noise_only_drift", "azurerm_storage_account.this"): ("R3", "refresh_state_only", False),
    ("root_cause_plans", "replace_cannot_update", "azurerm_storage_account.this"): ("R2", None, False),
    ("root_cause_plans", "undetermined_change", "azurerm_storage_account.this"): ("R1", None, False),
    ("report_plans", "multi_resource", "azurerm_resource_group.old"): ("R2", None, False),
    ("report_plans", "multi_resource", "azurerm_storage_account.logs"): ("R2", None, False),
    ("report_plans", "multi_resource", "azurerm_storage_account.this"): ("R4", "restore_declared", True),
}


@unittest.skipUnless(HAS_AI_EXTRA, "needs the 'ai' extra")
class PolicyTests(unittest.TestCase):
    def setUp(self):
        from test_ai_engine import ALL_FIXTURES, fixture_report, prepared
        self.fixtures, self.fixture_report, self.prepared = ALL_FIXTURES, fixture_report, prepared

    def test_policy_over_every_option_fixture(self):
        seen = set()
        for group, name in self.fixtures:
            state = self.prepared(self.fixture_report(group, name))
            if state["parsed_drift"]["outcome"] != "succeeded":
                self.assertEqual(state["remediation_plan"]["recommendations"], [])
                continue
            options = state["remediation_plan"]["options"]
            for rec in state["remediation_plan"]["recommendations"]:
                with self.subTest(group=group, name=name, address=rec["address"]):
                    key = (group, name, rec["address"])
                    rule, kind, note = POLICY_TABLE.get(key, ("R4", "restore_declared", True))
                    self.assertEqual((rec["policy_rule"], rec["kind"], bool(rec["notes"])), (rule, kind, note))
                    self.assertEqual(rec["decision"], {"R0": "no_options", "R1": "human_decision_required",
                                                       "R2": "human_decision_required"}.get(rule, "recommended"))
                    self.assertEqual((rec["approval_required"], rec["execution_allowed"], rec["automatic_apply"]),
                                     (True, False, False))
                    if rec["option_id"] is not None:
                        chosen = next(o for o in options if o["option_id"] == rec["option_id"])
                        self.assertEqual((chosen["address"], chosen["kind"]), (rec["address"], kind))
                        self.assertFalse(chosen["destructive"] or chosen["data_not_restored"])
                    seen.add(key)
        self.assertEqual(set(POLICY_TABLE) - seen, set())

    def test_r0_no_options(self):
        from ai_engine.nodes.remediation import recommend
        rec = recommend({"address": "a", "classification": "external_drift"}, [])
        self.assertEqual((rec["decision"], rec["policy_rule"], rec["rationale"], rec["option_id"]),
                         ("no_options", "R0", "no_options", None))

    def test_investigation_never_changes_the_recommendation(self):
        state = self.prepared(self.fixture_report("plan_evidence", "external_drift"))
        recs = state["remediation_plan"]["recommendations"]
        state["investigation_facts"] = {"status": "complete"}  # never read by plan_remediation
        from ai_engine.nodes.remediation import plan_remediation
        self.assertEqual(plan_remediation(state)["remediation_plan"]["recommendations"], recs)


# --------------------------------------------------------------------------- loading, binding, CLI


class LoadAndCliTests(_AiBase):
    def setUp(self):
        super().setUp()
        self.result = self.real()
        self.good = self.public(self.result)

    def rejected(self, document, drift=None) -> str:
        with self.assertRaises(InvestigationInputError) as ctx:
            load_investigation(document, drift if drift is not None else self.drift)
        return ctx.exception.code

    def test_rejections(self):
        planted = copy.deepcopy(self.good)
        planted["resources"][0]["address"] = REAL_CALLER
        self.assertEqual(self.rejected(planted), "leak")
        extra = copy.deepcopy(self.good)
        extra["resources"][0]["operations"][0]["caller"] = "x"
        self.assertEqual(self.rejected(extra), "contract")
        upgraded = copy.deepcopy(self.good)
        upgraded["resources"][0]["property_link"] = "confirmed"  # the public invariants refuse it
        self.assertEqual(self.rejected(upgraded), "contract")
        other_run = copy.deepcopy(self.drift)
        other_run["run"]["run_id"] = "github-1-1"
        self.assertEqual(self.rejected(self.good, other_run), "binding_mismatch")
        other_content = copy.deepcopy(self.drift)  # same run id and plan timestamp, other content
        other_content["summary"]["highest_severity"] = "INFO"
        self.assertEqual(self.rejected(self.good, other_content), "binding_mismatch")
        other_window = copy.deepcopy(self.drift)
        other_window["run"]["started_at"] = "2026-10-04T11:06:40Z"
        self.assertEqual(self.rejected(self.good, other_window), "binding_mismatch")
        missing = copy.deepcopy(self.good)
        missing["resources"] = []
        self.assertEqual(self.rejected(missing), "scope_mismatch")
        areas = copy.deepcopy(self.good)
        areas["resources"][0]["relevant_areas"] = ["other"]
        self.assertEqual(self.rejected(areas), "scope_mismatch")
        self.assertEqual(load_investigation(self.good, self.drift), self.good)

    def cli(self, investigation_text: str | None, out="out"):
        report_path = os.path.join(self.tmp, "drift_report.json")
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(self.drift, fh)
        args = ["--report", report_path, "--output-dir", os.path.join(self.tmp, out)]
        if investigation_text is not None:
            path = os.path.join(self.tmp, f"{out}-investigation.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(investigation_text)
            args += ["--investigation", path]
        with mock.patch.dict(os.environ, {"AI_LLM_PROVIDER": "none"}, clear=False), \
                mock.patch("sys.stderr") as err, mock.patch("sys.stdout"):
            code = ai_cli.main(args)
        written = sorted(os.listdir(os.path.join(self.tmp, out))) if os.path.isdir(os.path.join(self.tmp, out)) \
            else []
        return code, written, "".join(str(c.args[0]) for c in err.write.call_args_list)

    def test_cli_writes_report_v2_with_the_investigation(self):
        code, written, _ = self.cli(json.dumps(self.good))
        self.assertEqual((code, written), (0, ["ai_analysis_report.json", "ai_analysis_report.md"]))
        with open(os.path.join(self.tmp, "out", "ai_analysis_report.json"), encoding="utf-8") as fh:
            report = json.load(fh)
        self.assertEqual(report["investigation"]["status"], "complete")
        self.assertEqual(verify.verify_report(report, self.drift, self.good), [])

    def test_cli_rejects_every_bad_investigation_and_writes_nothing(self):
        planted = copy.deepcopy(self.good)
        planted["resources"][0]["address"] = REAL_CALLER
        unbindable = self.public(self.inv_run(report=b"{}", source=NoCallSource(), rows=None))
        self.drift = json.loads(public_report_bytes(self.plan(nsg_drift())))  # keep a valid drift report as input
        cases = {"invalid_json": "{", "duplicate": '{"a": 1, "a": 1}', "leak": json.dumps(planted),
                 "contract": json.dumps({"public_version": "1"}), "binding": json.dumps(self.good),
                 "unbindable": json.dumps(unbindable)}
        for n, (name, text) in enumerate(cases.items()):
            with self.subTest(name):
                code, written, err = self.cli(text, out=f"out-{n}")
                self.assertEqual((code, written), (1, []))
                self.assertIn("the investigation is rejected", err)
                self.assertNotIn(REAL_CALLER, err)

    def test_cli_exits_70_when_verification_fails(self):  # D4
        with mock.patch.object(verify, "verify_report", return_value=["planted problem"]):
            code, written, err = self.cli(json.dumps(self.good))
        self.assertEqual((code, written), (70, []))
        self.assertIn("failed verification (1 problem(s))", err)
        self.assertNotIn("planted problem", err)

    def test_cli_unreadable_investigation(self):
        report_path = os.path.join(self.tmp, "r.json")
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(self.drift, fh)
        with mock.patch.dict(os.environ, {"AI_LLM_PROVIDER": "none"}), mock.patch("sys.stderr"), \
                mock.patch("sys.stdout"):
            code = ai_cli.main(["--report", report_path, "--output-dir", os.path.join(self.tmp, "o"),
                                "--investigation", os.path.join(self.tmp, "nope.json")])
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "o")))

    def test_run_analysis_rechecks_the_investigation(self):
        planted = copy.deepcopy(self.good)
        planted["resources"][0]["address"] = REAL_CALLER
        with self.assertRaises(InvestigationInputError):
            run_analysis(copy.deepcopy(self.drift), config=load_config({}), investigation=planted)
        with self.assertRaises(ValueError):
            run_analysis(copy.deepcopy(self.drift), config=load_config({}), investigation={})


# --------------------------------------------------------------------------- verify_report v2: tampering


def _r0(report):
    return report["resources"][0]


TAMPERS = {
    "verdict upgraded": lambda r, p: _r0(r)["correlation"].update(verdict="latest_capable_operation"),
    "reason invented": lambda r, p: _r0(r)["correlation"].update(reason="evidence_failed"),
    "property link confirmed": lambda r, p: _r0(r)["correlation"].update(property_link="confirmed",
                                                                         property_link_reason=None),
    "relevant areas": lambda r, p: _r0(r)["correlation"].update(relevant_areas=["other"]),
    "counts": lambda r, p: _r0(r)["correlation"]["counts"].update(candidates=2),
    "operation time": lambda r, p: _r0(r)["operations"][0].update(start="2026-10-04T11:00:00.000000Z"),
    "operation dropped": lambda r, p: _r0(r).update(operations=[]),
    "operation name": lambda r, p: _r0(r)["operations"][0].update(operation_name="Microsoft.Resources/x/write"),
    "event time": lambda r, p: _r0(r)["when"].update(event_end="2026-10-04T11:05:00.000000Z"),
    "gap": lambda r, p: _r0(r)["when"].update(gap_seconds=1.0),
    "observation": lambda r, p: _r0(r)["when"]["observation"].update(started_at="2026-10-04T11:00:00.000000Z"),
    "last in sync": lambda r, p: _r0(r)["when"].update(last_in_sync=None),
    "caller type": lambda r, p: _r0(r)["who"]["recorded_caller"].update(caller_type="service_principal"),
    "client app": lambda r, p: _r0(r)["who"]["recorded_caller"].update(client_app="azure_cli"),
    "caller status": lambda r, p: _r0(r)["who"]["recorded_caller"].update(
        status="no_decisive_operation", operation=None, caller_type=None, client_app=None),
    "actor confirmed": lambda r, p: _r0(r)["who"]["actor_attribution"].update(
        status="confirmed", rule="external_deletion_v1", claim="recorded_successful_delete"),
    "statement text": lambda r, p: [s.update(text="This operation caused the drift.") for s in
                                    (_r0(r)["correlation"]["statements"][-2], next(
                                        n for n in _r0(r)["analysis"]["narrative"]
                                        if n == _r0(r)["correlation"]["statements"][-2]))],
    "statement id swapped": lambda r, p: _r0(r)["when"]["statements"][0].update(id="when.not_confirmed.v1"),
    "narrative order": lambda r, p: _r0(r)["analysis"]["narrative"].reverse(),
    "investigation sha": lambda r, p: r["provenance"].update(investigation_sha256="0" * 64),
    "version": lambda r, p: r["provenance"]["versions"].update(capable_operations_table=None),
    "status": lambda r, p: r["investigation"].update(status="incomplete"),
    "completeness": lambda r, p: r["investigation"]["completeness"].update(polls=5),
    "scope flipped": lambda r, p: _r0(r).update(investigation_scope="not_drift"),
    "investigation file swapped": lambda r, p: p["resources"][0]["operations"][0].update(
        end="2026-10-04T11:04:59.000000Z"),
    "investigation_sent invented": lambda r, p: r["llm"]["investigation_sent"].append(
        {"address": RG_ADDR, "operations": ["op-1"], "automated_events": []}),
}


class VerifyTamperTests(_AiBase):
    def test_every_tamper_is_detected(self):
        report, public = self.ai(self.real())
        for name, tamper in TAMPERS.items():
            with self.subTest(name):
                broken, inv_copy = copy.deepcopy(report), copy.deepcopy(public)
                tamper(broken, inv_copy)
                self.assertNotEqual(verify.verify_report(broken, self.drift, inv_copy), [], name)

    def test_ai_investigation_findings_are_reverified(self):
        public = self.public(self.real())
        llm = ScriptedLLM(envelope(investigation_analysis={"findings": [finding(RG_ADDR)], "summary": ""}))
        report, _ = self.ai(llm=llm, public=public)
        self.assertEqual(len(report["analysis"]["investigation"]["findings"]), 1)

        def first(r):
            return r["analysis"]["investigation"]["findings"][0]
        tampers = {
            "verdict": lambda r: first(r).update(verdict="latest_capable_operation"),
            "attribution": lambda r: first(r).update(actor_attribution="confirmed"),
            "unsent operation": lambda r: first(r).update(cited_operations=["op-2"]),
            "unsent resource": lambda r: first(r).update(address="azurerm_key_vault.prod"),
            "consistency": lambda r: first(r).update(consistency="not_consistent_with_drift"),
            "consistency upgrade": lambda r: first(r).update(cited_operations=[]),
            "guard": lambda r: first(r).update(explanation="op-1 caused the drift."),
            "sent unknown resource": lambda r: r["llm"]["investigation_sent"].append(
                {"address": "azurerm_key_vault.prod", "operations": [], "automated_events": []}),
            "sent unknown operation": lambda r: r["llm"]["investigation_sent"][0].update(operations=["op-7"]),
        }
        for name, tamper in tampers.items():
            with self.subTest(name):
                broken = copy.deepcopy(report)
                tamper(broken)
                self.assertNotEqual(verify.verify_report(broken, self.drift, public), [], name)

    def test_investigation_file_itself_is_checked(self):
        report, public = self.ai(self.real())
        cases = {
            "contract": lambda p: p.pop("exposure"),
            "leak": lambda p: p["resources"][0].update(address=REAL_CALLER),
            "binding": lambda p: p["binding"].update(run_id="github-1-1"),
            "observation": lambda p: p["binding"]["observation"].update(started_at="2026-10-04T11:00:00.000000Z"),
            "scope": lambda p: p.update(resources=[]),
        }
        for name, tamper in cases.items():
            with self.subTest(name):
                broken = copy.deepcopy(public)
                tamper(broken)
                problems = verify.verify_report(report, self.drift, broken)
                self.assertTrue(any(p.startswith("investigation") for p in problems), (name, problems))

    def test_report_checked_against_the_wrong_investigation(self):
        report, public = self.ai(self.real())
        self.assertNotEqual(verify.verify_report(report, self.drift, None), [])
        _, other = self.ai(self.real(with_anchor=False))  # another investigation of the same drift report
        self.assertNotEqual(verify.verify_report(report, self.drift, other), [])


# --------------------------------------------------------------------------- the LLM: evidence, guards, authority


class LlmTests(_AiBase):
    def setUp(self):
        super().setUp()
        self.result = self.real()
        self.good = self.public(self.result)

    def run_llm(self, *findings, summary=""):
        llm = ScriptedLLM(envelope(investigation_analysis={"findings": list(findings), "summary": summary}))
        report, _ = self.ai(llm=llm, public=self.good)
        return report, llm, self.state["inferences"]["analyze_investigation"]

    def test_valid_interpretation_is_accepted_and_labelled(self):
        text = ("The recorded tags write op-1 ended at 2026-10-04T11:04:58Z, before the observation, and is "
                "consistent with the drifted tags area; impact is limited to tag metadata.")
        report, llm, result = self.run_llm(finding(RG_ADDR, explanation=text),
                                           summary="One recorded operation is consistent with the tag drift.")
        self.assertEqual(len(llm.prompts), 1)  # still one logical call
        self.assertEqual((result["status"], result["rejected_findings"]), ("ok", []))
        [kept] = report["analysis"]["investigation"]["findings"]
        self.assertEqual((kept["consistency"], kept["verdict"], kept["property_link"], kept["actor_attribution"],
                          kept["basis"]), ("consistent_with_drift", "sole_capable_operation",
                                           "inferred_not_provable", "not_confirmed_by_available_evidence",
                                           "inference"))
        md = render_markdown(report)
        self.assertIn("AI inference: The recorded tags write op\\-1", md)

    def test_unsafe_interpretations_are_rejected(self):
        cases = {
            "unsupported_attribution": "A user changed the tags in the portal.",
            "identity_like_string": "The call came from 198.51.100.7 on the portal.",
            "verdict_upgrade": "op-1 caused the drift.",
            "verdict_upgrade ": "This confirms that the tag write explains the drift.",
            "unsupported_timestamp": "The tags write ended at 11:05:30 UTC.",
            "unsupported_operation": "Microsoft.Resources/deployments/write also ran.",
            "unsupported_operation ": "op-2 ran after op-1.",
        }
        findings = [finding(RG_ADDR, explanation=text) for text in cases.values()]
        findings += [finding(RG_ADDR, ops=("op-9",)), finding("azurerm_key_vault.prod"),
                     finding(RG_ADDR, consistency="not_consistent_with_drift")]
        report, _, result = self.run_llm(*findings, summary=f"The caller was {REAL_CALLER}.")
        reasons = [r["reason"] for r in result["rejected_findings"]]
        self.assertEqual(reasons, [k.strip() for k in cases] + ["unsupported_citation", "unsupported_citation",
                                                               "consistency_contradicts_evidence",
                                                               "summary_unsupported_attribution"])
        self.assertEqual(report["analysis"]["investigation"]["findings"], [])
        self.assertNotIn(REAL_CALLER, json.dumps(report))

    def test_consistency_cannot_exceed_the_verdict(self):
        self.result = self.inv_run(rows=())  # no capable operation at all
        self.good = self.public(self.result)
        address = self.good["resources"][0]["address"]
        _, _, result = self.run_llm(finding(address, ops=()), finding(address, ops=(), consistency="undetermined",
                                                                      explanation="Nothing recorded explains it."))
        self.assertEqual([r["reason"] for r in result["rejected_findings"]], ["consistency_exceeds_evidence"])
        self.assertEqual(len(result["findings"]), 1)

    def test_deterministic_report_identical_with_and_without_llm(self):
        without, _ = self.ai(public=self.good)
        with_llm, _, _ = self.run_llm(finding(RG_ADDR), summary="op-1 caused it.")
        for key in ("report_version", "provenance", "summary", "investigation", "resources", "remediation", "cost"):
            self.assertEqual(json.dumps(with_llm[key], sort_keys=True), json.dumps(without[key], sort_keys=True),
                             key)

    def test_prompt_carries_only_the_allowlisted_public_investigation(self):
        _, llm, _ = self.run_llm()
        prompt = "".join(m.content for m in llm.prompts[0])
        evidence_text = json.dumps(shown(llm.prompts[0]))
        investigation = shown(llm.prompts[0])["investigation"]
        [resource] = investigation["resources"]
        self.assertEqual(set(resource), {"address", "drift_action", "relevant_areas", "verdict", "reason",
                                         "property_link", "property_link_reason", "unreadable_events_in_scope",
                                         "descendant_events", "actor_attribution", "decisive_operation", "window",
                                         "operations", "automated_events"})
        self.assertEqual(set(resource["operations"][0]), {
            "op_id", "operation_name", "outcome", "relations", "start", "end", "available_at", "timing",
            "in_window", "role", "capable_areas", "caller_type", "client_app", "pipeline_identity"})
        self.assertEqual(set(investigation["run"]), {"observation", "completeness"})
        for secret in (REAL_CALLER, "/subscriptions/", "37178020110", self.good["binding"]["drift_report_sha256"]):
            self.assertNotIn(secret, prompt)
        for field in ("caller_status", "withheld", "correlation", "event_id", "exposure", "binding",
                      self.good["resources"][0]["window"]["anchor"]["report_sha256"]):
            self.assertNotIn(field, evidence_text)
        self.assertEqual(resource["window"], {"kind": "anchor", "start": self.good["resources"][0]["window"]["start"]})
        self.assertEqual(self.state["report"]["llm"]["investigation_sent"],
                         [{"address": RG_ADDR, "operations": ["op-1"], "automated_events": []}])

    def test_leaky_investigation_evidence_fails_closed(self):
        facts = copy.deepcopy(self.state_facts())
        facts["resources"][0]["address"] = REAL_CALLER
        with self.assertRaises(EvidenceIntegrityError):
            build_investigation_evidence(facts)

    def state_facts(self):
        self.ai(public=self.good)
        return json.loads(json.dumps(self.state["investigation_facts"]))

    def test_investigation_evidence_limits(self):
        facts = self.state_facts()
        evidence = build_investigation_evidence(facts, EvidenceLimits(max_investigation_operations=0))
        self.assertEqual((evidence["resources"][0]["operations"], evidence["operations_omitted"], evidence["truncated"]),
                         ([], {RG_ADDR: 1}, True))
        evidence = build_investigation_evidence(facts, EvidenceLimits(max_investigation_resources=0))
        self.assertEqual((evidence["resources"], evidence["omitted"], evidence["run"]), ([], [RG_ADDR], None))
        evidence = build_investigation_evidence(facts, EvidenceLimits(max_investigation_chars=10))
        self.assertEqual((evidence["resources"], evidence["truncated"]), ([], True))

    def test_not_investigated_resources_are_never_sent(self):
        for result in (self.inv_run(rows=[ev(9999, ts="2026-10-02T07:30:00Z", operationName={"value": "bad name"})]),
                       self.inv_run(rows=None, source=FakeSource({RG: [al.SourceError("throttled", 429)]}))):
            llm = ScriptedLLM(envelope())
            self.ai(llm=llm, public=self.public(result))
            self.assertEqual(len(llm.prompts), 1)  # the Terraform sections still go to the model
            evidence = shown(llm.prompts[0])
            self.assertNotIn("investigation", evidence)  # no investigation block, only the applicability flag
            self.assertEqual(evidence["sections"]["investigation"], {"applicable": False})
            self.assertEqual(self.state["llm_call"]["investigation_sent"], [])
            self.assertEqual(self.state["inferences"]["analyze_investigation"]["reason"],
                             "no investigated drifted resources")


class GuardUnitTests(unittest.TestCase):
    @unittest.skipUnless(HAS_AI_EXTRA, "needs the 'ai' extra")
    def test_timestamp_forms_and_references(self):
        from ai_engine.nodes.common import EvidenceRefs, reference_violation, timestamp_forms
        forms = timestamp_forms("2026-10-04T11:04:56.093597Z")
        for accepted in ("2026-10-04", "11:04", "11:04:56", "11:04:56.09", "2026-10-04T11:04:56.093597"):
            self.assertIn(accepted, forms)
        refs = EvidenceRefs(frozenset(forms), frozenset({TAGS_WRITE.casefold()}), frozenset({"op-1"}))
        self.assertIsNone(reference_violation("op-1 (Microsoft.Resources/TAGS/write) at 2026-10-04 11:04:56 UTC.",
                                              refs))
        self.assertEqual(reference_violation("op-1 at 11:04:57.", refs), "unsupported_timestamp")
        self.assertEqual(reference_violation("auto-1 fired.", refs), "unsupported_operation")

    @unittest.skipUnless(HAS_AI_EXTRA, "needs the 'ai' extra")
    def test_ip_and_url_allowed_only_when_quoted_from_the_evidence(self):
        from ai_engine.nodes.common import EvidenceRefs, free_text_violation
        refs = EvidenceRefs(evidence_text='{"source": "0.0.0.0/0", "endpoint": "https://example.org/a"}')
        self.assertIsNone(free_text_violation("Inbound is open to 0.0.0.0/0.", refs))
        self.assertIsNone(free_text_violation("The endpoint is now https://example.org/a.", refs))
        self.assertEqual(free_text_violation("Inbound is open from 192.0.2.4.", refs), "identity_like_string")
        self.assertEqual(free_text_violation("Inbound is open to 0.0.0.0/0."), "identity_like_string")


if __name__ == "__main__":
    unittest.main()
