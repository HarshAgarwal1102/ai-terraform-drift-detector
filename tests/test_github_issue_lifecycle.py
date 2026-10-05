"""Tests for the Task 8.3 drift issue lifecycle in scripts/github_automation.py.

Reuses the Task 8.1 fakes (in-memory GitHub API behind the client's opener hook,
reports from the real classifier with the run bound to github-123-1). No network:
tests/conftest.py blocks real connections. The safeguard mutants for 8.3 live in
the shared harness in tests/test_github_automation.py.
"""

from __future__ import annotations

import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import yaml

from test_github_automation import (
    BOT, ENV, FIXTURES, REPO, RG_ADDR, WORKFLOW, FakeGitHub, FakeResponse, _Base, _public, args_for, evaluate, evidence,
    fixture_dirs, fixture_report, ga, lowest_report, resolved_report,
)

OLD = "2026-10-02T00:00:00Z"        # marker of an issue created by an earlier drifted run
NOW = "2026-10-03T10:00:00Z"        # plan.timestamp of the run under test
LATER = "2026-10-04T00:00:00Z"
CLOSE = {"state": "closed", "state_reason": "completed"}


def address(i: int) -> str:
    return f'module.resource_group.azurerm_resource_group.this["s{i:02d}"]'


def marker(addr: str, plan: str = OLD, *, environment: str = "dev", content: str = "a" * 64,
           run: str = "github-100-1") -> str:
    return ga.marker_line(ga.fingerprint(environment, addr), content, run, plan)


def issue_body(addr: str, plan: str = OLD, **kwargs) -> str:
    return marker(addr, plan, **kwargs) + "\n## Terraform drift detected\n\nhuman-visible text\n"


def with_in_sync(report: dict, *addresses: str) -> dict:
    """Add present, non-drifted resources to a report (partial resolution in a 'true' run)."""
    base = copy.deepcopy(fixture_report("in_sync")["resources"][0])
    for addr in addresses:
        item = copy.deepcopy(base)
        item["address"] = addr
        report["resources"].append(item)
    report["summary"]["resources_total"] = len(report["resources"])
    return report


class _Lifecycle(_Base):
    def run_false(self, fake: FakeGitHub, report: dict | None = None, env: dict | None = None):
        return self.run_with(fake, report or resolved_report(), "false", env)

    def run_with(self, fake: FakeGitHub, report: dict, drift: str, env: dict | None = None):
        path = self.write_report(report)
        return ga.run(args_for(path, drift=drift), dict(ENV if env is None else env), self.client_factory(fake))

    def writes(self, fake: FakeGitHub) -> list[tuple[str, str, object]]:
        return [(m, u.replace(f"{ga.API_URL}/repos/{REPO}", ""), p) for m, u, p in fake.requests if m != "GET"]


# --------------------------------------------------------------------------- gating

class LifecycleGatingTests(_Lifecycle):
    def test_false_run_closes_and_never_creates_or_updates(self):
        fake = FakeGitHub()
        fake.add_issue(issue_body(RG_ADDR))
        result = self.run_false(fake)
        self.assertEqual((result.outcome, result.closed, result.created, result.updated), ("ok", [1], [], []))
        self.assertEqual(self.writes(fake), [("PATCH", "/issues/1", CLOSE)])
        self.assertEqual(fake.count("POST"), 0)

    def test_gating_matrix(self):
        failed = _public(evaluate(os.path.join(self.tmp, "absent-plan.json"),
                                  os.path.join(FIXTURES, "plan_evidence", "failed_run", "detection_run.json")))
        cases = [
            ("false", resolved_report(), None),
            ("false", lowest_report(), "report_inconsistent"),           # has_drift true but 'false'
            ("false", failed, "report_failed"),
            ("false", {"not": "a report"}, "report_invalid"),
            ("true", resolved_report(), "report_inconsistent"),          # has_drift false but 'true'
            ("true", lowest_report(), None),
            ("unknown", resolved_report(), "not_drift_detected"),
            ("unknown", lowest_report(), "not_drift_detected"),
            ("", resolved_report(), "not_drift_detected"),
        ]
        for drift, report, code_ in cases:
            with self.subTest(drift=drift, code=code_):
                fake = FakeGitHub()
                fake.add_issue(issue_body(RG_ADDR))
                result = self.run_with(fake, report, drift)
                self.assertEqual(result.codes, [code_] if code_ else [])
                if code_:
                    self.assertEqual(fake.requests, [])  # run-level failures happen before any request
                    self.assertEqual(fake.issues[1]["state"], "open")

    def test_false_run_report_consistency(self):
        cases = {}
        r = resolved_report(); r["summary"]["drifted_resources"] = 1; cases["drift-count"] = r
        r = resolved_report(); r["resources"][0]["drift_action"] = "update"; cases["drift-action"] = r
        r = resolved_report(2); r["resources"][1]["address"] = RG_ADDR; cases["duplicate-address"] = r
        r = resolved_report(); r["plan"]["timestamp"] = None; cases["no-timestamp"] = r
        r = resolved_report(); r["run"]["environment"] = "prod"; cases["environment"] = r
        r = resolved_report(); r["run"]["run_id"] = "local-1"; cases["local-run"] = r
        expected = {"environment": "environment_mismatch", "local-run": "run_mismatch"}
        for name, report in cases.items():
            with self.subTest(name):
                fake = FakeGitHub()
                fake.add_issue(issue_body(RG_ADDR))
                result = self.run_false(fake, report)
                self.assertEqual(result.codes, [expected.get(name, "report_inconsistent")])
                self.assertEqual(fake.requests, [])

    def test_true_run_rejects_duplicate_addresses_anywhere_in_the_report(self):
        report = with_in_sync(lowest_report(), address(1), address(1))
        fake = FakeGitHub()
        self.assertEqual(self.run_with(fake, report, "true").codes, ["report_inconsistent"])
        self.assertEqual(fake.requests, [])

    def test_binding_applies_to_false_runs(self):
        for name, changes, code_ in (("attempt", {"GITHUB_RUN_ATTEMPT": "2"}, "attempt_mismatch"),
                                     ("run", {"GITHUB_RUN_ID": "999"}, "run_mismatch"),
                                     ("outside-actions", {"GITHUB_ACTIONS": "false"}, "publish_outside_actions"),
                                     ("token", {"GITHUB_TOKEN": ""}, "token_missing")):
            with self.subTest(name):
                fake = FakeGitHub()
                fake.add_issue(issue_body(RG_ADDR))
                result = self.run_false(fake, env=dict(ENV, **changes))
                self.assertEqual(result.codes, [code_])
                self.assertEqual(fake.requests, [])

    def test_run_level_api_failures_happen_before_any_write(self):
        for kind, failure, code_ in (("label", 401, "auth_failed"), ("list", 500, "server_error")):
            with self.subTest(kind):
                fake = FakeGitHub()
                fake.add_issue(issue_body(RG_ADDR))
                fake.fail(kind, *([failure] * ga.MAX_ATTEMPTS))
                self.assertEqual(self.run_false(fake).codes, [code_])
                self.assertEqual(self.writes(fake), [])
        fake = FakeGitHub(labels=())
        fake.add_issue(issue_body(RG_ADDR))
        self.assertEqual(self.run_false(fake).codes, ["label_missing"])
        self.assertEqual(self.writes(fake), [])
        fake = FakeGitHub(page_size=1)
        for i in range(ga.MAX_PAGES + 1):
            fake.add_issue(issue_body(RG_ADDR))
        self.assertEqual(self.run_false(fake).codes, ["pagination_limit"])
        self.assertEqual(self.writes(fake), [])

    def test_dry_run_for_a_false_run_has_no_network_and_no_creates(self):
        out = os.path.join(self.tmp, "preview")
        result = ga.run(args_for(self.write_report(resolved_report()), publish=False, drift="false", out_dir=out),
                        {}, None)
        self.assertEqual((result.outcome, result.planned, result.closed), ("ok", 0, []))
        with open(os.path.join(out, "requests.json")) as fh:
            self.assertEqual(json.load(fh), [])


# --------------------------------------------------------------------------- resolvable set

class ResolvableSetTests(_Lifecycle):
    def test_resolvable_set_on_every_fixture(self):
        checked = 0
        for d in fixture_dirs():
            name = os.path.basename(os.path.normpath(d))
            report = fixture_report(name)
            if report["outcome"] != "succeeded":
                continue
            with self.subTest(name):
                ev = evidence(report) if report["has_drift"] else ga.evidence_from_report(
                    ga.load_report(json.dumps(report).encode()), "dev", False)
                present = {r["address"] for r in report["resources"]}
                drifted = {r["address"] for r in report["resources"] if r["drift_action"] is not None}
                self.assertEqual(set(ev.resolved), present - drifted)
                self.assertEqual({r.address for r in ev.resources}, drifted)
                self.assertEqual(list(ev.resolved), sorted(ev.resolved))
                checked += 1
        self.assertGreaterEqual(checked, 35)

    def test_other_environment_and_unknown_addresses_are_never_closed(self):
        fake = FakeGitHub()
        fake.add_issue(issue_body(RG_ADDR, environment="prod"))  # same address, other environment
        fake.add_issue(issue_body(address(7)))                   # removed / moved resource
        before = copy.deepcopy(fake.issues)
        result = self.run_false(fake)
        self.assertEqual((result.codes, result.outcome, result.closed), (["resource_not_in_report"], "ok", []))
        self.assertEqual(fake.issues, before)
        self.assertEqual(self.writes(fake), [])

    def test_issues_without_a_marker_fingerprint_are_ignored(self):
        fake = FakeGitHub()
        fake.add_issue("no marker at all")
        fake.add_issue("<!-- drift-issue v=1 no fingerprint -->")
        result = self.run_false(fake)
        self.assertEqual((result.codes, self.writes(fake)), ([], []))


# --------------------------------------------------------------------------- transitions

class TransitionTests(_Lifecycle):
    def test_timestamp_ordering(self):
        for plan, expected_code, closed in ((OLD, None, [1]), (NOW, "conflicting_evidence", []),
                                            (LATER, "stale_evidence", [])):
            with self.subTest(plan=plan):
                fake = FakeGitHub()
                fake.add_issue(issue_body(RG_ADDR, plan))
                result = self.run_false(fake)
                self.assertEqual(result.closed, closed)
                self.assertEqual(result.codes, [expected_code] if expected_code else [])
                self.assertEqual(result.outcome, "failed" if expected_code else "ok")
                self.assertEqual(fake.issues[1]["state"], "closed" if closed else "open")

    def test_invalid_and_unsupported_markers_are_not_closed(self):
        fp = ga.fingerprint("dev", RG_ADDR)
        for body, code_ in ((f"<!-- drift-issue v=1 fp={fp} broken -->", "marker_invalid"),
                            (f"<!-- drift-issue v=2 fp={fp} content={'a' * 64} run=github-1-1 plan={OLD} -->",
                             "marker_version_unsupported")):
            with self.subTest(code=code_):
                fake = FakeGitHub()
                fake.add_issue(body)
                result = self.run_false(fake)
                self.assertEqual((result.codes, result.outcome, result.closed), ([code_], "failed", []))
                self.assertEqual(self.writes(fake), [])

    def test_every_valid_duplicate_is_closed(self):
        fake = FakeGitHub()
        for n in (6, 2, 4):
            fake.add_issue(issue_body(RG_ADDR), number=n)
        result = self.run_false(fake)
        self.assertEqual((result.closed, result.codes, result.outcome), ([2, 4, 6], ["duplicate_issues"], "ok"))

    def test_duplicate_with_one_bad_marker_closes_only_the_valid_ones(self):
        fake = FakeGitHub()
        fake.add_issue(issue_body(RG_ADDR), number=2)
        fake.add_issue(f"<!-- drift-issue v=1 fp={ga.fingerprint('dev', RG_ADDR)} broken -->", number=3)
        result = self.run_false(fake)
        self.assertEqual((result.closed, sorted(result.codes)), ([2], ["duplicate_issues", "marker_invalid"]))

    def test_partial_resolution_in_a_true_run(self):
        report = with_in_sync(lowest_report(plan_ts=NOW), address(1), address(2))
        fake = FakeGitHub()
        drifted_issue = fake.add_issue(issue_body(RG_ADDR))      # drifted again: 8.1 update (content differs)
        resolved_issue = fake.add_issue(issue_body(address(1)))  # resolved: closed
        result = self.run_with(fake, report, "true")
        self.assertEqual((result.updated, result.closed, result.created, result.codes), ([drifted_issue], [resolved_issue], [], []))
        report2 = with_in_sync(lowest_report(plan_ts=NOW), address(1))
        report2["resources"][0]["address"] = address(3)          # a new drifted resource: created
        fake2 = FakeGitHub()
        n_resolved = fake2.add_issue(issue_body(address(1)))
        result2 = self.run_with(fake2, report2, "true")
        self.assertEqual((len(result2.created), result2.closed), (1, [n_resolved]))
        order = [m for m, _, _ in self.writes(fake2)]
        self.assertEqual(order, ["POST", "PATCH"])               # 8.1 writes first, then closures

    def test_drifted_issue_is_never_closed(self):
        fake = FakeGitHub()
        fake.add_issue(issue_body(RG_ADDR))
        result = self.run_with(fake, lowest_report(plan_ts=NOW), "true")
        self.assertEqual((result.closed, fake.issues[1]["state"]), ([], "open"))


class RecurrenceAndHumanTests(_Lifecycle):
    def test_recurrence_creates_a_new_issue_and_never_reopens(self):
        fake = FakeGitHub()
        fake.add_issue(issue_body(RG_ADDR))
        self.assertEqual(self.run_false(fake).closed, [1])
        drift_again = lowest_report(plan_ts=LATER)
        result = self.run_with(fake, drift_again, "true")
        self.assertEqual((result.created, fake.issues[1]["state"]), ([2], "closed"))
        self.assertEqual([sorted(p) for m, _, p in fake.requests if m == "POST"], [["body", "labels", "title"]])
        resolved_again = resolved_report(plan_ts="2026-10-05T00:00:00Z")
        result = self.run_false(fake, resolved_again)
        self.assertEqual((result.closed, fake.issues[1]["state"], fake.issues[2]["state"]), ([2], "closed", "closed"))
        self.assertFalse(any(p and p.get("state") == "open" for _, _, p in fake.requests))

    def test_human_closed_issue_with_persisting_drift_gets_a_new_issue(self):
        fake = FakeGitHub()
        fake.add_issue(issue_body(RG_ADDR), state="closed")
        result = self.run_with(fake, lowest_report(plan_ts=NOW), "true")
        self.assertEqual((result.created, fake.issues[1]["state"]), ([2], "closed"))

    def test_human_reopened_resolved_issue_is_closed_again(self):
        fake = FakeGitHub()
        fake.add_issue(issue_body(RG_ADDR))
        self.run_false(fake)
        fake.issues[1]["state"] = "open"                   # a human reopens it; drift still resolved
        result = self.run_false(fake, resolved_report(plan_ts=LATER))
        self.assertEqual((result.closed, fake.issues[1]["state"]), ([1], "closed"))

    def test_label_removed_opts_out(self):
        fake = FakeGitHub()
        fake.add_issue(issue_body(RG_ADDR), labels=())
        result = self.run_false(fake)
        self.assertEqual((result.closed, result.codes, self.writes(fake)), ([], [], []))

    def test_human_edits(self):
        fake = FakeGitHub()
        edited = issue_body(RG_ADDR) + "\nA human added this note.\n"
        fake.add_issue(edited, title="Renamed by a human")
        result = self.run_false(fake)
        self.assertEqual(result.closed, [1])
        self.assertEqual((fake.issues[1]["body"], fake.issues[1]["title"]), (edited, "Renamed by a human"))
        broken = FakeGitHub()
        broken.add_issue("Human rewrote everything\n" + marker(RG_ADDR))  # marker no longer first line
        self.assertEqual((self.run_false(broken).closed, self.writes(broken)), ([], []))

    def test_human_edit_race_between_listing_and_close_is_preserved(self):
        fake = FakeGitHub()
        fake.add_issue(issue_body(RG_ADDR))
        raced = issue_body(RG_ADDR) + "\nEdited after the listing, before the close.\n"

        def human_edit(api, number):
            api.issues[number]["body"] = raced
            api.issues[number]["title"] = "Edited title"

        fake.before_patch = human_edit
        result = self.run_false(fake)
        self.assertEqual(result.closed, [1])
        self.assertEqual((fake.issues[1]["body"], fake.issues[1]["title"], fake.issues[1]["state"]),
                         (raced, "Edited title", "closed"))


# --------------------------------------------------------------------------- close request and failure scope

class CloseRequestTests(_Lifecycle):
    def test_close_payload_is_exactly_state_and_state_reason(self):
        fake = FakeGitHub()
        fake.add_issue(issue_body(RG_ADDR))
        self.run_false(fake)
        (method, path, payload), = self.writes(fake)
        self.assertEqual((method, path), ("PATCH", "/issues/1"))
        self.assertEqual(payload, CLOSE)
        self.assertEqual(sorted(payload), ["state", "state_reason"])
        for forbidden in ("body", "title", "labels", "assignees", "milestone"):
            self.assertNotIn(forbidden, payload)
        self.assertFalse(any(m == "POST" for m, _, _ in fake.requests))  # no comment

    def test_close_is_retried_like_any_patch(self):
        fake = FakeGitHub()
        fake.add_issue(issue_body(RG_ADDR))
        fake.fail("update", 502, (429, {"Retry-After": "120"}))
        result = self.run_false(fake)
        self.assertEqual((result.closed, fake.count("PATCH"), self.sleeps), ([1], 3, [1.0, ga.RETRY_AFTER_CAP]))
        fake = FakeGitHub()
        fake.add_issue(issue_body(RG_ADDR))
        fake.fail("update", 500, 500, 500)
        result = self.run_false(fake)
        self.assertEqual((result.codes, fake.count("PATCH"), fake.issues[1]["state"]), (["server_error"], 3, "open"))
        fake = FakeGitHub()
        fake.add_issue(issue_body(RG_ADDR))
        fake.fail("update", (403, {"X-RateLimit-Remaining": "0"}))
        self.assertEqual((self.run_false(fake).codes, fake.count("PATCH")), (["rate_limited"], 1))

    def test_api_failure_on_first_close_stops_all_writes(self):
        report = resolved_report(3)
        fake = FakeGitHub()
        for addr in (RG_ADDR, address(1), address(2)):
            fake.add_issue(issue_body(addr))
        fake.fail("update", 422)
        result = self.run_false(fake, report)
        self.assertEqual((result.codes, result.outcome, result.closed), (["validation_failed"], "failed", []))
        self.assertEqual(fake.count("PATCH"), 1)
        self.assertTrue(all(i["state"] == "open" for i in fake.issues.values()))

    def test_mixed_run_continues_deterministically(self):
        report = with_in_sync(lowest_report(plan_ts=NOW), address(1), address(2), address(3), address(4))
        fake = FakeGitHub()
        fake.add_issue(f"<!-- drift-issue v=1 fp={ga.fingerprint('dev', address(1))} broken -->")  # 1 marker_invalid
        fake.add_issue(issue_body(address(2), LATER))                                          # 2 stale_evidence
        fake.add_issue(issue_body(address(3), NOW))                                            # 3 conflicting_evidence
        fake.add_issue(issue_body(address(9)))                                                 # 4 resource_not_in_report
        fake.add_issue(issue_body(address(4)))                                                 # 5 valid closure
        fake.add_issue(issue_body(RG_ADDR))                                                    # 6 valid 8.1 update
        result = self.run_with(fake, report, "true")
        self.assertEqual(self.writes(fake)[0][:2], ("PATCH", "/issues/6"))
        self.assertEqual(sorted(self.writes(fake)[0][2]), ["body", "title"])
        self.assertEqual(self.writes(fake)[1], ("PATCH", "/issues/5", CLOSE))
        self.assertEqual(len(self.writes(fake)), 2)
        self.assertEqual((result.updated, result.closed, result.outcome), ([6], [5], "failed"))
        self.assertEqual(sorted(result.codes), ["conflicting_evidence", "marker_invalid", "resource_not_in_report",
                                                "stale_evidence"])
        for n in (1, 2, 3, 4):
            self.assertEqual(fake.issues[n]["state"], "open")

    def test_warnings_only_run_exits_zero(self):
        report = self.write_report(resolved_report())
        fake = FakeGitHub()
        fake.add_issue(issue_body(RG_ADDR), number=1)
        fake.add_issue(issue_body(RG_ADDR), number=2)                  # duplicate_issues
        fake.add_issue(issue_body(address(5)), number=3)               # resource_not_in_report
        original = ga.GitHubClient
        ga.GitHubClient = lambda token, repo: original(token, repo, opener=fake)
        try:
            with redirect_stdout(io.StringIO()):
                rc = ga.main(["--report", report, "--environment", "dev", "--drift-detected", "false", "--publish"],
                             dict(ENV, GITHUB_STEP_SUMMARY=os.path.join(self.tmp, "summary.md")))
        finally:
            ga.GitHubClient = original
        self.assertEqual(rc, 0)
        with open(os.path.join(self.tmp, "summary.md")) as fh:
            summary = fh.read()
        self.assertIn("closed: 2", summary)
        self.assertIn("Closed issues: #1, #2", summary)
        self.assertIn("`duplicate_issues`", summary)
        self.assertIn("`resource_not_in_report`", summary)

    def test_per_issue_anomaly_exits_one_through_main(self):
        report = self.write_report(resolved_report())
        fake = FakeGitHub()
        fake.add_issue(issue_body(RG_ADDR, LATER))
        original = ga.GitHubClient
        ga.GitHubClient = lambda token, repo: original(token, repo, opener=fake)
        try:
            with redirect_stdout(io.StringIO()):
                rc = ga.main(["--report", report, "--environment", "dev", "--drift-detected", "false", "--publish"],
                             dict(ENV))
        finally:
            ga.GitHubClient = original
        self.assertEqual(rc, 1)

    def test_cap_is_shared_by_creates_updates_and_closes(self):
        count = ga.MAX_WRITES_PER_RUN + 2
        report = resolved_report(count)
        fake = FakeGitHub()
        addrs = [RG_ADDR] + [address(i) for i in range(1, count)]
        for addr in addrs:
            fake.add_issue(issue_body(addr))
        result = self.run_false(fake, report)
        self.assertEqual((len(result.closed), result.not_processed, result.codes),
                         (ga.MAX_WRITES_PER_RUN, 2, ["cap_exceeded"]))
        self.assertEqual(result.closed, list(range(1, ga.MAX_WRITES_PER_RUN + 1)))  # issue number order
        # creates count first: 9 creates leave room for exactly one close
        true_report = lowest_report(plan_ts=NOW)
        base = true_report["resources"][0]
        true_report["resources"] = []
        for i in range(ga.MAX_WRITES_PER_RUN - 1):
            item = copy.deepcopy(base)
            item["address"] = f'module.x.azurerm_resource_group.this["d{i}"]'
            true_report["resources"].append(item)
        true_report["summary"]["drifted_resources"] = ga.MAX_WRITES_PER_RUN - 1
        true_report = with_in_sync(true_report, address(1), address(2))
        fake = FakeGitHub()
        fake.add_issue(issue_body(address(1)))
        fake.add_issue(issue_body(address(2)))
        result = self.run_with(fake, true_report, "true")
        self.assertEqual((len(result.created), result.closed, result.not_processed, result.codes),
                         (ga.MAX_WRITES_PER_RUN - 1, [1], 1, ["cap_exceeded"]))

    def test_no_leakage_and_phase7_inputs_ignored(self):
        caller = "alice.caller@example.com"
        report = resolved_report()
        path = self.write_report(report)
        with open(os.path.join(self.tmp, "drift_attribution.json"), "w") as fh:
            json.dump({"resources": [{"address": RG_ADDR, "attribution": {"status": "confirmed", "caller": caller}}]}, fh)
        with open(os.path.join(self.tmp, "activity_log_evidence.json"), "w") as fh:
            json.dump({"events": [{"caller": caller}]}, fh)
        with_files = FakeGitHub()
        with_files.add_issue(issue_body(RG_ADDR))
        ga.run(args_for(path, drift="false"), dict(ENV), self.client_factory(with_files))
        other = tempfile.mkdtemp(prefix="gh-lifecycle-clean-")
        self.addCleanup(lambda: __import__("shutil").rmtree(other, ignore_errors=True))
        clean = os.path.join(other, "drift_report.json")
        with open(clean, "w") as fh:
            json.dump(report, fh)
        without = FakeGitHub()
        without.add_issue(issue_body(RG_ADDR))
        ga.run(args_for(clean, drift="false"), dict(ENV), self.client_factory(without))
        self.assertEqual(with_files.requests, without.requests)
        written = json.dumps(self.writes(with_files))
        for forbidden in (caller, "alice", "/subscriptions/", "task-3.6"):
            self.assertNotIn(forbidden, written)
        self.assertIsNone(ga._GUID_RE.search(written))


# --------------------------------------------------------------------------- workflow

class LifecycleWorkflowTests(unittest.TestCase):
    def test_issues_job_runs_for_true_and_false_only(self):
        with open(WORKFLOW, encoding="utf-8") as fh:
            wf = yaml.safe_load(fh)
        job = wf["jobs"]["issues"]
        condition = job["if"]
        self.assertEqual(condition, "${{ needs.plan-and-analyze.outputs.drift_detected == 'true' || "
                                    "needs.plan-and-analyze.outputs.drift_detected == 'false' }}")
        self.assertNotIn("unknown", condition)
        self.assertNotIn("always()", condition)
        self.assertNotIn("!cancelled()", condition)
        self.assertEqual(job["permissions"], {"contents": "read", "issues": "write"})
        self.assertEqual(job["needs"], ["preflight", "plan-and-analyze"])
        self.assertEqual(job["steps"][-1]["name"], "Manage Drift Issues")
        self.assertEqual(sorted(wf.get("on", wf.get(True))), ["schedule", "workflow_dispatch"])
        self.assertEqual(wf["concurrency"]["cancel-in-progress"], False)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
