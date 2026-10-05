"""Tests for the unknown/missing Activity Log fallback (Task 7.3).

Run from the repository root:
    pytest tests/test_attribution_fallback.py

`attribution.origin_statement` is the single display mapping: a drifted resource
shows the Task 7.2 claim only when confirmed, and "Change origin could not be
confirmed" in every other case. The machine-readable status/reason stay in
drift_attribution.json and `caller` stays null unless confirmed. The AI tests at the
end need the `[ai]` extra and are skipped without it.

Requires the package (pip install -e ".[dev]"); skipped otherwise. No Azure, network
or credentials: evidence comes from the Task 7.1 collector over a fake source and
attribution from the Task 7.2 engine (helpers shared with tests/test_attribution.py).
"""

from __future__ import annotations

import contextlib
import copy
import datetime as dt
import hashlib
import importlib.util
import inspect
import io
import json
import os
import re
import unittest
from unittest import mock

from test_activity_logs import (  # noqa: E402  (shared helpers; no test classes imported)
    CALLER, DELETE, FIXTURES, NSG_ADDR, NSG_ID, RG, RG_ADDR, SUB, FakeSource, ev, page,
)
from test_attribution import (  # noqa: E402
    GUID_CALLER, OTHER, QUERIED, ROOT, T_START, UTC, _Base, at_time, deleted, updated,
)

try:
    from drift_engine import activity_logs as al
    from drift_engine import attribution as at
    from drift_engine import cli
    from drift_engine.classifier import evaluate
except ImportError:  # pydantic not installed
    at = None

HAS_AI_EXTRA = at is not None and all(importlib.util.find_spec(m) for m in ("langgraph", "langchain_openai"))

FALLBACK = "Change origin could not be confirmed"
SECOND = "azurerm_resource_group.second"
SECOND_RG = "second-rg"
SECOND_RG_ID = f"/subscriptions/{SUB}/resourceGroups/{SECOND_RG}"


def _public(evaluation):
    """The public drift report (Task 9B.4A): every consumer reads it, never the internal report."""
    from drift_engine.report_public import public_document
    return public_document(evaluation.report, evaluation.plan or {})


class FallbackTests(_Base):
    def statements(self, document, addresses=(NSG_ADDR,)):
        return {a: at.origin_statement(document, a) for a in addresses}

    def assert_fallback(self, document, addresses=(NSG_ADDR,)):
        for address, statement in self.statements(document, addresses).items():
            self.assertEqual(statement, FALLBACK, address)
            for caller in (CALLER, OTHER, GUID_CALLER):
                self.assertNotIn(caller, statement)
        for resource in document.resources if document is not None else []:
            if resource.attribution.status != "confirmed":
                self.assertIsNone(resource.attribution.caller)

    def test_statement_constant(self):
        self.assertEqual(at.UNCONFIRMED_ORIGIN, FALLBACK)

    # --- the plan's validation: empty Activity Log response, end to end -----------

    def test_empty_log_response_end_to_end(self):
        for name, drift_changes, reason in (("deletion", deleted(), "no_deletion_event"),
                                            ("update", updated(), "update_not_attributable")):
            with self.subTest(name):
                scenario = self.scenario(drift_changes, script={RG: [page()]})
                evidence = json.loads(scenario.evidence_bytes)
                self.assertEqual((evidence["outcome"], evidence["events"], evidence["scopes"][0]["events_returned"]),
                                 ("complete", [], 0))
                document = scenario.attribute()
                attribution = self.resource(document).attribution
                self.assertEqual((document.outcome, attribution.status, attribution.reason, attribution.caller),
                                 ("complete", "unknown", reason, None))
                self.assert_fallback(document)

    def test_empty_log_response_through_the_cli_pipeline(self):
        scenario = self.scenario(deleted(), script={RG: [page()]})
        report = os.path.join(self.tmp, "report.json")
        evidence = os.path.join(self.tmp, "evidence.json")
        output = os.path.join(self.tmp, "attribution.json")
        class FixedClock(dt.datetime):  # the CLI's query time, pinned to the test timeline
            @classmethod
            def now(cls, tz=None):
                return QUERIED

        quiet = contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO())
        with quiet[0], quiet[1], mock.patch.object(cli, "datetime", FixedClock):
            self.assertEqual(cli.main(["analyze", "--plan", scenario.plan, "--manifest", scenario.manifest,
                                       "--output", report]), 0)
            with mock.patch.object(cli, "_activity_log_source", return_value=FakeSource({RG: [page()]})):
                self.assertEqual(cli.main(["activity-logs", "--plan", scenario.plan, "--manifest",
                                           scenario.manifest, "--output", evidence]), 0)
            before = hashlib.sha256(open(report, "rb").read()).hexdigest()
            self.assertEqual(cli.main(["attribute", "--report", report, "--evidence", evidence,
                                       "--output", output]), 0)
        self.assertEqual(hashlib.sha256(open(report, "rb").read()).hexdigest(), before)
        with open(output, encoding="utf-8") as fh:
            document = at.DriftAttribution.model_validate_json(fh.read())
        self.assertEqual(self.resource(document).attribution.reason, "no_deletion_event")
        self.assert_fallback(document)

    # --- missing, disabled, failed, invalid or mismatched evidence -------------------

    def test_collection_failures(self):
        for code in al.QUERY_FAILURE_CODES:
            with self.subTest(code):
                document = self.scenario(deleted(), script={RG: [al.SourceError(code)]}).attribute()
                self.assertEqual((document.outcome, document.failure.reason), ("failed", "evidence_failed"))
                self.assert_fallback(document)

    def test_one_failed_scope(self):
        both = (deleted()[0] + deleted(SECOND, SECOND_RG_ID, "azurerm_resource_group")[0],
                deleted()[1] + deleted(SECOND, SECOND_RG_ID, "azurerm_resource_group")[1])
        rows = self.W(8) + self.D(9)
        document = self.scenario(both, script={RG: [page(*rows)],
                                               SECOND_RG: [al.SourceError("authorization_failed", 403)]}).attribute()
        self.assertEqual(self.resource(document, SECOND).attribution.reason, "evidence_failed")
        self.assertEqual(at.origin_statement(document, SECOND), FALLBACK)
        self.assertNotEqual(at.origin_statement(document, NSG_ADDR), FALLBACK)  # the other resource is confirmed

    def test_missing_invalid_or_mismatched_inputs(self):
        good = self.scenario(deleted(), self.W(8) + self.D(9))
        other_run = self.scenario(deleted(), self.W(8) + self.D(9), manifest={"run_id": "attr-run-2"})
        cases = {
            "no evidence file": at.attribute_files(good.report_path, os.path.join(self.tmp, "missing.json"))[0],
            "invalid evidence": at.attribute(good.report_bytes, b"not json"),
            "invalid report": at.attribute(b"{", good.evidence_bytes),
            "no report": at.attribute(None, good.evidence_bytes),
            "mismatched evidence": at.attribute(good.report_bytes, other_run.evidence_bytes),
        }
        self.assertEqual(at.origin_statement(good.attribute(), NSG_ADDR),
                         at.CLAIM_TEMPLATE.format(caller=CALLER))  # the same events, correctly bound
        for name, document in cases.items():
            with self.subTest(name):
                self.assertEqual(document.outcome, "failed")
                self.assert_fallback(document)

    def test_no_attribution_document_or_unlisted_address(self):
        self.assertEqual(at.origin_statement(None, NSG_ADDR), FALLBACK)
        confirmed = self.scenario(deleted(), self.W(8) + self.D(9)).attribute()
        for address in (RG_ADDR, "", NSG_ADDR.upper(), "module.network.azurerm_network_security_group.this"):
            with self.subTest(address):
                self.assertEqual(at.origin_statement(confirmed, address), FALLBACK)

    def test_failed_document_never_shows_a_claim(self):
        # defense in depth: even an (unvalidated) failed document carrying a confirmed
        # entry must fall back; only a non-failed document can confirm
        confirmed = self.scenario(deleted(), self.W(8) + self.D(9)).attribute()
        inconsistent = at.DriftAttribution.model_construct(
            **{**dict(confirmed), "outcome": "failed",
               "failure": at.Failure(stage="evidence", reason="evidence_failed")})
        self.assertEqual(self.resource(inconsistent).attribution.status, "confirmed")
        self.assertEqual(at.origin_statement(inconsistent, NSG_ADDR), FALLBACK)

    def test_sdk_unavailable_without_the_azure_extra(self):
        document = self.scenario(deleted(), script={RG: [al.SourceError("azure_sdk_unavailable")]}).attribute()
        self.assert_fallback(document)

    # --- expired / out of window / not yet settled ----------------------------------

    def test_expired_or_out_of_window_events(self):
        rows = self.W(8) + self.D(9)  # 2026-10-02
        later = dt.datetime(2026, 12, 31, 12, tzinfo=UTC)  # a 30-day window no longer reaches 2026-10-02
        scenario = self.scenario(deleted(), rows, queried_at=later)
        evidence = json.loads(scenario.evidence_bytes)
        self.assertEqual((evidence["events"], evidence["scopes"][0]["dropped"]),
                         ([], {"timestamp_outside_window": len(rows)}))
        document = scenario.attribute()
        self.assertEqual(self.resource(document).attribution.reason, "no_deletion_event")
        self.assert_fallback(document)
        old_anchor = self.log.group("write", dt.datetime(2026, 9, 1, 8, tzinfo=UTC))
        document = self.scenario(deleted(), old_anchor + self.D(9)).attribute()
        self.assertEqual(self.resource(document).attribution.reason, "no_existence_anchor")
        self.assert_fallback(document)

    def test_not_settled(self):
        document = self.scenario(deleted(), self.W(8) + self.D(9),
                                 queried_at=QUERIED.replace(hour=10, minute=14)).attribute()
        self.assertEqual(self.resource(document).attribution.reason, "evidence_not_settled")
        self.assert_fallback(document)

    # --- every unknown reason --------------------------------------------------------

    def reason_scenarios(self) -> dict[str, tuple]:
        """One scenario per Task 7.2 reason code: (document, address)."""
        day3 = dt.datetime(2026, 10, 3, tzinfo=UTC)
        both = (deleted()[0] + deleted(SECOND, SECOND_RG_ID, "azurerm_resource_group")[0],
                deleted()[1] + deleted(SECOND, SECOND_RG_ID, "azurerm_resource_group")[1])
        sub_level = f"/subscriptions/{SUB}/providers/Microsoft.Authorization/roleAssignments/ra1"
        good = self.scenario(deleted(), self.W(8) + self.D(9))
        policy = self.log.event(at_time(9, 1), resourceId=NSG_ID, category={"value": "Policy"},
                                operationName={"value": "Microsoft.Authorization/policies/audit/action"})
        build = {
            "evidence_mismatch": lambda: (at.attribute(good.report_bytes, self.scenario(
                deleted(), self.W(8) + self.D(9), manifest={"run_id": "other"}).evidence_bytes), NSG_ADDR),
            "evidence_failed": lambda: (self.scenario(both, script={RG: [page()], SECOND_RG: [
                al.SourceError("throttled", 429)]}).attribute(), SECOND),
            "evidence_incomplete": lambda: (self.scenario(deleted(), script={RG: [page(more=True), page()]},
                                                          limits=al.Limits(max_pages_per_scope=1)).attribute(), NSG_ADDR),
            "evidence_not_settled": lambda: (self.scenario(deleted(), self.W(8) + self.D(9),
                                                           queried_at=QUERIED.replace(hour=10)).attribute(), NSG_ADDR),
            "unreadable_events_in_scope": lambda: (self.scenario(deleted(), self.W(8) + self.D(9) + [ev(
                9001, ts="2026-10-02T09:30:00Z", operationName={"value": "bad name"})]).attribute(), NSG_ADDR),
            "detection_time_unknown": lambda: (self.scenario(deleted(), self.W(8) + self.D(9),
                                                             manifest={"started_at": DELETE}).attribute(), NSG_ADDR),
            "no_resource_id": lambda: (self.scenario(deleted(NSG_ADDR, DELETE), script={}).attribute(), NSG_ADDR),
            "invalid_resource_id": lambda: (self.scenario(deleted(NSG_ADDR, "bad"), script={}).attribute(), NSG_ADDR),
            "unsupported_scope": lambda: (self.scenario(deleted(NSG_ADDR, sub_level), script={}).attribute(), NSG_ADDR),
            "update_not_attributable": lambda: (self.scenario(updated(), self.W(8)).attribute(), NSG_ADDR),
            "no_deletion_event": lambda: (self.scenario(deleted(), []).attribute(), NSG_ADDR),
            "order_ambiguous": lambda: (self.scenario(deleted(), self.W(8) + self.log.group(
                "delete", at_time(8, 0, 3), statuses=("Succeeded",))).attribute(), NSG_ADDR),
            "latest_operation_is_write": lambda: (self.scenario(deleted(), self.W(8)).attribute(), NSG_ADDR),
            "no_existence_anchor": lambda: (self.scenario(deleted(), self.D(9)).attribute(), NSG_ADDR),
            "multiple_successful_deletes": lambda: (self.scenario(deleted(), self.W(8) + self.D(9) + self.D(
                9, 30, caller=OTHER)).attribute(), NSG_ADDR),
            "unresolved_operation": lambda: (self.scenario(deleted(), self.W(8) + self.D(
                9, statuses=("Started", "Accepted"))).attribute(), NSG_ADDR),
            "caller_missing": lambda: (self.scenario(deleted(), self.W(8) + self.D(
                9, callers=[CALLER, None, CALLER])).attribute(), NSG_ADDR),
            "caller_inconsistent": lambda: (self.scenario(deleted(), self.W(8) + self.D(
                9, callers=[GUID_CALLER, CALLER, CALLER])).attribute(), NSG_ADDR),
            "concurrent_with_detection": lambda: (self.scenario(deleted(), self.log.group(
                "write", at_time(8, day=day3)) + self.log.group("delete", T_START, statuses=("Succeeded",))
            ).attribute(), NSG_ADDR),
            "automated_activity_overlap": lambda: (self.scenario(deleted(), self.W(8) + self.D(9) + policy
                                                                 ).attribute(), NSG_ADDR),
        }
        return {reason: make() for reason, make in build.items()}

    def test_every_unknown_reason_resolves_to_the_fallback(self):
        produced = self.reason_scenarios()
        self.assertEqual(set(produced), set(at.REASONS))
        for reason, (document, address) in produced.items():
            with self.subTest(reason):
                resource = self.resource(document, address)
                self.assertEqual((resource.attribution.status, resource.attribution.reason, resource.attribution.caller),
                                 ("unknown", reason, None))
                self.assertEqual(at.origin_statement(document, address), FALLBACK)
                self.assert_fallback(document, [address])

    # --- confirmed positive control ---------------------------------------------------

    def test_confirmed_keeps_the_claim_template(self):
        for caller in (CALLER, GUID_CALLER):
            with self.subTest(caller):
                document = self.scenario(deleted(), self.W(8) + self.D(9, caller=caller)).attribute()
                attribution = self.resource(document).attribution
                self.assertEqual((attribution.status, attribution.caller), ("confirmed", caller))
                self.assertEqual(at.origin_statement(document, NSG_ADDR),
                                 f"Azure recorded caller {caller} performing the successful delete of this exact "
                                 "resource under the correlation rules.")
                self.assertEqual(at.origin_statement(document, NSG_ADDR), at.render_claim(self.resource(document)))

    def test_fallback_is_not_stored_in_any_output(self):
        for reason, (document, _) in self.reason_scenarios().items():
            with self.subTest(reason):
                rendered = at.render_attribution(document)
                self.assertNotIn(FALLBACK, rendered)
                self.assertNotIn("caller_identity", rendered)

    def test_deterministic(self):
        rows = self.W(8) + self.D(9, statuses=("Started", "Accepted"))
        first = self.scenario(deleted(), rows).attribute()
        second = self.scenario(deleted(), rows).attribute()
        self.assertEqual(at.render_attribution(first), at.render_attribution(second))
        self.assertEqual(at.origin_statement(first, NSG_ADDR), at.origin_statement(second, NSG_ADDR))


# ---------------------------------------------------------------------------
# AI layer: cannot invent or assume caller identities without log data
# ---------------------------------------------------------------------------

class AiBoundaryTests(_Base):
    def test_ai_engine_never_reads_activity_log_data(self):
        for directory, _, files in os.walk(os.path.join(ROOT, "src", "ai_engine")):
            for name in files:
                if name.endswith(".py"):
                    with open(os.path.join(directory, name), encoding="utf-8") as fh:
                        text = fh.read()
                    # Task 9B.4: `activity_log_evidence` is now the report v2 basis label of the public
                    # investigation's operations; the restricted modules and documents stay out of reach.
                    for needle in ("drift_engine.activity_logs", "drift_engine.attribution", "import activity_logs",
                                   "import attribution", "origin_statement", "drift_attribution"):
                        self.assertNotIn(needle, text, f"{name}: {needle}")


@unittest.skipUnless(HAS_AI_EXTRA, "needs the 'ai' extra")
class AiAntiCallerTests(_Base):
    """A model that names a caller is rejected, the AI report keeps actor unknown, and
    nothing from the Activity Log can reach the model."""

    def setUp(self):
        super().setUp()
        from ai_engine import verify
        from ai_engine.evidence import EVIDENCE_TAG
        from ai_engine.graph import run_analysis
        self.verify, self.tag, self.run_analysis = verify, EVIDENCE_TAG, run_analysis

    def naming_model(self, caller: str):
        tag = self.tag

        class CallerNamingModel:
            def __init__(self):
                self.prompts = []

            def invoke(self, messages):
                self.prompts.append(messages)
                shown = json.loads(re.search(rf"<{tag}>\n(.*)\n</{tag}>", messages[-1].content, re.S).group(1))
                causes = [{"address": r["address"], "cited_paths": [c["path"]], "hypothesis": "out_of_band_change",
                           "possible_channels": ["portal"],
                           "explanation": f"{caller} changed this in the portal.", "basis": "inference"}
                          for r in shown["resources"] for c in r["changes"] if "root_cause" in c["sections"]]

                def section(findings, summary):
                    return {"findings": findings, "summary": summary}
                return json.dumps({"security_analysis": section([], ""), "cost_analysis": section([], ""),
                                   "configuration_analysis": section([], ""),
                                   "root_cause_analysis": section(causes, f"The change was made by {caller}."),
                                   "risk_assessment": section([], f"{caller} deleted it."),
                                   "investigation_analysis": section([], f"{caller} made the change.")})
        return CallerNamingModel()

    def check(self, drift_report: dict, caller: str):
        model = self.naming_model(caller)
        state = self.run_analysis(copy.deepcopy(drift_report), llm=model)
        report = state["report"]
        # report v2 (Task 9B.4): without a public investigation, WHO is not investigated and attribution is
        # not confirmed by available evidence, whatever the model says
        for resource in report["resources"]:
            if resource["investigation_scope"] == "drift":
                self.assertEqual(resource["who"]["recorded_caller"]["status"], "not_investigated")
                self.assertEqual(resource["who"]["actor_attribution"]["status"],
                                 "not_confirmed_by_available_evidence")
        self.assertEqual(report["investigation"]["status"], "not_available")
        self.assertNotIn(caller, json.dumps(report))
        self.assertEqual(self.verify.verify_report(report, drift_report), [])
        for messages in model.prompts:
            for message in messages:
                self.assertNotIn(caller, message.content)
                self.assertNotIn('"caller"', message.content)
        return report

    def test_caller_named_by_the_model_is_rejected(self):
        drift_report = _public(evaluate(os.path.join(FIXTURES, "plan_evidence", "external_drift", "plan.sanitized.json"),
                                os.path.join(FIXTURES, "plan_evidence", "external_drift", "detection_run.json")))
        report = self.check(drift_report, CALLER)
        rejections = report["analysis"]["root_cause"]["rejection_reasons"]
        self.assertEqual(rejections, {"summary_unsupported_attribution": 1, "unsupported_attribution": 1})

    def test_confirmed_attribution_never_reaches_the_ai(self):
        # Task 7.2 confirms the deletion; the AI still sees only the drift report
        scenario = self.scenario(deleted(), self.W(8) + self.D(9))
        self.assertEqual(self.resource(scenario.attribute()).attribution.status, "confirmed")
        from drift_engine.report_public import public_document
        with open(scenario.plan, encoding="utf-8") as fh:  # the AI engine reads only the public report (Task 9B.4A)
            drift_report = public_document(json.loads(scenario.report_bytes), json.load(fh))
        with_files = self.check(drift_report, CALLER)
        os.remove(scenario.evidence_path)
        without_files = self.run_analysis(copy.deepcopy(drift_report), config=None, llm=self.naming_model(CALLER))
        self.assertEqual(with_files, without_files["report"])

    def test_run_analysis_has_no_activity_log_input(self):
        parameters = inspect.signature(self.run_analysis).parameters
        for name in parameters:
            for word in ("evidence", "attribution", "activity", "caller", "log"):
                self.assertNotIn(word, name)


if __name__ == "__main__":
    unittest.main()
