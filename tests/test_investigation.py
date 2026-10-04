"""Tests for the drift investigation: correlation v2 and the last-in-sync anchor (Task 9B.2).

Run from the repository root:
    pytest tests/test_investigation.py

Requires the package (pip install -e ".[dev]"); skipped otherwise. No Azure, network,
credentials or real clock: evidence is collected by the real Task 9B.1 collector over
a fake source, time is a fake clock whose `sleep` advances it, and drift reports come
from drift_engine's own classifier. IDs, callers and addresses are synthetic; the
real-shape scenario uses the sanitized fixture tests/fixtures/activity_log/.

Synthetic timeline (UTC): detection run 2026-10-03 10:00:00-10:05:00, so
before_observation ends before 09:59:00 and after_observation starts after 10:06:00
(60 s skew); the first query is at 10:15:00 (finished + 10 min) and re-queries stop at
10:25:00 (finished + 20 min). The trusted anchor run saw the resources in sync on
2026-10-02 06:00:00-06:01:00, so anchored windows start at 05:59:00 that day.
"""

from __future__ import annotations

import contextlib
import copy
import datetime as dt
import io
import json
import os
import random
import stat
import sys
import types
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS)

from test_activity_logs import (  # noqa: E402  (shared helpers; no test classes imported)
    CALLER, DELETE, FIXTURES, NSG_ADDR, NSG_ID, RG, RG_ADDR, RG_ID, ROOT, RULE_ID, SUB, FakeSource, NoCallSource,
    al, ev, nsg, page, raw_entry,
)

try:
    from pydantic import ValidationError

    from drift_engine import attribution as at
    from drift_engine import cli
    from drift_engine import investigation as inv
    from drift_engine.classifier import evaluate
    from drift_engine.models import DriftReport
except ImportError:  # pydantic not installed
    inv = None

UTC = dt.timezone.utc
STARTED, FINISHED = "2026-10-03T10:00:00Z", "2026-10-03T10:05:00Z"
PLAN_TS = "2026-10-03T10:02:00Z"
T_FINISHED = dt.datetime(2026, 10, 3, 10, 5, tzinfo=UTC)
NOT_BEFORE = T_FINISHED + dt.timedelta(minutes=10)
POLL_END = T_FINISHED + dt.timedelta(minutes=20)
DAY = dt.datetime(2026, 10, 2, tzinfo=UTC)
CURRENT_RUN = "github-500-1"
REPO = "owner/repo"
OTHER_CALLER = "mallory@example.com"
TAGS_OP = "Microsoft.Resources/tags/write"
NSG_OPS = "Microsoft.Network/networkSecurityGroups"
NSG_TAGS_EXT = f"{NSG_ID}/providers/Microsoft.Resources/tags/default"
VNET_ID = f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Network/virtualNetworks/aitdd-dev-main-vnet"
STATE = {"location": "centralindia"}


def at_time(hour: int, minute: int = 0, second: int = 0, day: dt.datetime = DAY) -> dt.datetime:
    return day + dt.timedelta(hours=hour, minutes=minute, seconds=second)


def iso(moment: dt.datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class Log:
    """REST-shaped Activity Log rows with unique ids, grouped the way Azure logs them."""

    def __init__(self) -> None:
        self.n = 0
        self.c = 0

    def rows(self, start: dt.datetime, *, statuses=("Started", "Succeeded"), rid=NSG_ID, op=f"{NSG_OPS}/write",
             category="Administrative", caller=CALLER, corr="auto", step=2, rids=None) -> list[dict]:
        self.c += 1
        correlation = f"corr-{self.c:04d}" if corr == "auto" else corr
        out = []
        for i, status in enumerate(statuses):
            self.n += 1
            out.append(ev(self.n, ts=iso(start + dt.timedelta(seconds=step * i)),
                          resourceId=(rids[i] if rids else rid), operationName={"value": op},
                          status={"value": status} if status else DELETE, category={"value": category},
                          correlationId=correlation if correlation is not None else DELETE,
                          caller=caller if caller is not None else DELETE, subStatus=DELETE))
        return out

    def write(self, start, **kw):
        return self.rows(start, **kw)

    def delete(self, start, **kw):
        return self.rows(start, op=f"{NSG_OPS}/delete", **kw)

    def tags(self, start, rid=NSG_ID, **kw):
        """The verified shape: Started on <id>/providers/Microsoft.Resources/tags/default,
        Succeeded on <id>, one correlationId."""
        ext = f"{rid}/providers/Microsoft.Resources/tags/default"
        return self.rows(start, op=TAGS_OP, rids=[ext, rid], **kw)

    def policy(self, start, corr="auto", rid=NSG_ID, category="Policy"):
        return self.rows(start, statuses=("Succeeded",), rid=rid, op="Microsoft.Authorization/policies/audit/action",
                         category=category, corr=corr)


def corr_of(rows: list[dict]) -> str:
    return rows[0]["correlationId"]


def nsg_drift(kind: str = "tags"):
    """(drift, changes) for an NSG drifted in `kind`: tags, other, both or delete."""
    state = nsg(**STATE)
    real = {"tags": nsg(**STATE, tags={"env": "changed"}), "other": nsg(location="westeurope"),
            "both": nsg(location="westeurope", tags={"env": "changed"})}.get(kind)
    if kind == "delete":
        return ([raw_entry(NSG_ADDR, ["delete"], state, None)],
                [raw_entry(NSG_ADDR, ["create"], None, nsg(DELETE, **STATE), {"id": True})])
    return [raw_entry(NSG_ADDR, ["update"], state, real)], [raw_entry(NSG_ADDR, ["update"], real, state)]


def in_sync(address=NSG_ADDR, rid=NSG_ID, rtype="azurerm_network_security_group"):
    view = nsg(rid, **STATE) if rtype == "azurerm_network_security_group" else {"id": rid, "name": RG}
    return [], [raw_entry(address, ["no-op"], view, view, rtype=rtype)]


def rg_drift():
    old, new = {"id": RG_ID, "name": RG, "tags": {"a": "1"}}, {"id": RG_ID, "name": RG, "tags": {"a": "2"}}
    return ([raw_entry(RG_ADDR, ["update"], old, new, rtype="azurerm_resource_group")],
            [raw_entry(RG_ADDR, ["update"], new, old, rtype="azurerm_resource_group")])


def nsg_and_rg(kind: str = "tags"):
    """NSG drift (anchored by the default anchor) plus RG drift (no anchor for it), so
    the run-level window is the lookback and the NSG's own window is narrower (G9)."""
    nsg_entries, rg_entries = nsg_drift(kind), rg_drift()
    return nsg_entries[0] + rg_entries[0], nsg_entries[1] + rg_entries[1]


class FakeClock:
    def __init__(self, start: dt.datetime = dt.datetime(2026, 10, 3, 10, 6, tzinfo=UTC)) -> None:
        self.now = start
        self.slept: list[float] = []

    def __call__(self) -> dt.datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += dt.timedelta(seconds=seconds)


class PollingSource:
    """Returns `script[i]` (resource group -> pages) for the i-th collection; the last repeats."""

    def __init__(self, scripts: list[dict]) -> None:
        self.scripts = scripts
        self.calls = 0

    def pages(self, subscription_id, query_filter):
        script = self.scripts[min(self.calls, len(self.scripts) - 1)]
        self.calls += 1
        return FakeSource(script).pages(subscription_id, query_filter)


def report_of(paths) -> dict:
    return DriftReport.model_validate(evaluate(*paths).report).model_dump(mode="json")


def report_bytes(paths) -> bytes:
    return (json.dumps(report_of(paths), indent=2, sort_keys=True) + "\n").encode("utf-8")


@unittest.skipIf(inv is None, "drift_engine is not installed (pip install -e '.[dev]')")
class _Base(unittest.TestCase):
    def setUp(self) -> None:
        import shutil
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="investigation-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.log = Log()
        self.count = 0

    def dir(self, name: str) -> str:
        self.count += 1
        path = os.path.join(self.tmp, f"{name}-{self.count}")
        os.makedirs(path)
        return path

    def plan(self, entries, *, run_id=CURRENT_RUN, started=STARTED, finished=FINISHED, plan_ts=PLAN_TS,
             environment="dev", outcome="succeeded") -> tuple[str, str]:
        drift, changes = entries
        directory = self.dir("plan")
        plan = {"format_version": "1.2", "terraform_version": "1.14.7", "errored": False, "complete": True,
                "applyable": True, "timestamp": plan_ts, "resource_drift": drift, "resource_changes": changes}
        pending = any(e["change"]["actions"] not in (["no-op"], ["read"]) for e in changes)
        manifest = {"outcome": outcome, "plan_exit_code": 2 if pending else 0, "terraform_version": "1.14.7",
                    "run_id": run_id, "environment": environment, "started_at": started, "finished_at": finished}
        for key in [k for k, v in manifest.items() if v is DELETE]:
            del manifest[key]
        paths = os.path.join(directory, "plan.json"), os.path.join(directory, "detection_run.json")
        for path, doc in zip(paths, (plan, manifest)):
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
        return paths

    def anchor(self, anchors: str, name: str, entries=None, *, run=400, attempt=1, started="2026-10-02T06:00:00Z",
               finished="2026-10-02T06:01:00Z", plan_ts="2026-10-02T06:00:30Z", environment="dev",
               report: bytes | None = None, **metadata) -> str:
        directory = os.path.join(anchors, name)
        os.makedirs(directory)
        meta = {"id": run, "run_attempt": attempt, "repository": REPO, "workflow_path": inv.WORKFLOW_PATH,
                "head_branch": "main", "event": "schedule", **metadata}
        meta = {k: v for k, v in meta.items() if v is not DELETE}
        with open(os.path.join(directory, "run.json"), "w", encoding="utf-8") as fh:
            json.dump(meta, fh)
        if report is None:
            report = report_bytes(self.plan(entries if entries is not None else in_sync(),
                                            run_id=f"github-{run}-{attempt}", started=started, finished=finished,
                                            plan_ts=plan_ts, environment=environment))
        with open(os.path.join(directory, "drift_report.json"), "wb") as fh:
            fh.write(report)
        return directory

    def anchors(self, **kwargs) -> str:
        directory = self.dir("anchors")
        self.anchor(directory, "run-400-1", **kwargs)
        return directory

    def inv_run(self, entries=None, rows=(), *, anchors="default", paths=None, source=None, clock=None,
            report: bytes | None = None, **kwargs) -> "inv.Result":
        paths = paths or self.plan(entries if entries is not None else nsg_drift())
        if anchors == "default":
            anchors = self.anchors()
        self.clock = clock or FakeClock()
        source = source if source is not None else FakeSource({RG: [page(*rows)]})
        kwargs.setdefault("repository", REPO if anchors else None)
        result = inv.investigate(paths[0], paths[1], report if report is not None else report_bytes(paths),
                                 source=source, clock=self.clock, sleep=self.clock.sleep, anchors_dir=anchors,
                                 **kwargs)
        self.assertEqual(inv.verify_against_evidence(result.document, result.evidence_bytes), [])
        return result

    def one(self, result) -> "inv.ResourceInvestigation":
        self.assertEqual(len(result.document.resources), 1)
        return result.document.resources[0]

    def verdict(self, *args, **kwargs) -> tuple:
        resource = self.one(self.inv_run(*args, **kwargs))
        return resource.verdict, resource.reason


# ---------------------------------------------------------------------------
# The real Azure shape (2026-10-04 manual portal tag edit)
# ---------------------------------------------------------------------------

class RealShapeTests(_Base):
    def real(self, with_anchor=True):
        src = os.path.join(FIXTURES, "plan_evidence", "external_drift")
        with open(os.path.join(src, "plan.sanitized.json"), encoding="utf-8") as fh:
            plan = json.loads(fh.read().replace("<AZURE_SUBSCRIPTION_ID>", SUB))
        plan["timestamp"] = "2026-10-04T11:06:49Z"
        with open(os.path.join(src, "detection_run.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)
        manifest.update(run_id="github-37197574080-1", started_at="2026-10-04T11:06:39Z",
                        finished_at="2026-10-04T11:06:57Z")
        directory = self.dir("real")
        paths = os.path.join(directory, "plan.json"), os.path.join(directory, "detection_run.json")
        for path, doc in zip(paths, (plan, manifest)):
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
        anchors = None
        if with_anchor:
            anchors = self.dir("anchors")
            self.anchor(anchors, "run-37178020110-1", in_sync(RG_ADDR, RG_ID, "azurerm_resource_group"),
                        run=37178020110, started="2026-10-04T04:47:39Z", finished="2026-10-04T04:49:01Z",
                        plan_ts="2026-10-04T04:48:30Z", event="workflow_dispatch")
        with open(os.path.join(FIXTURES, "activity_log", "rg_tag_writes.json"), encoding="utf-8") as fh:
            events = json.load(fh)
        clock = FakeClock(dt.datetime(2026, 10, 4, 11, 7, 5, tzinfo=UTC))
        return self.inv_run(paths=paths, anchors=anchors, source=FakeSource({RG: [page(*events)]}), clock=clock)

    def test_portal_tag_edit_is_the_sole_capable_operation(self):
        result = self.real()
        resource = self.one(result)
        self.assertEqual((resource.address, resource.relevant_areas), (RG_ADDR, ["tags"]))
        self.assertEqual((resource.verdict, resource.reason, resource.decisive_operation),
                         ("sole_capable_operation", None, "op-1"))
        self.assertEqual((resource.property_link, resource.property_link_reason),
                         ("inferred_not_provable", "no_property_values_in_activity_log"))
        self.assertEqual(resource.actor_attribution.status, "not_confirmed")
        self.assertEqual(resource.window.model_dump(), {"kind": "anchor", "start": "2026-10-04T04:46:39.000000Z",
                                                        "anchor": "run-37178020110-1"})
        (op,) = resource.operations
        self.assertEqual((op.operation_name, op.outcome, op.relations, op.timing, op.role, op.capable_areas),
                         (TAGS_OP, "successful", ["exact", "extension"], "before_observation", "capable", ["tags"]))
        self.assertEqual((op.start, op.end, op.available_at),
                         ("2026-10-04T11:04:56.093597Z", "2026-10-04T11:04:58.187357Z", "2026-10-04T11:06:24.000000Z"))
        self.assertEqual((op.caller, op.caller_status, op.caller_type, op.client_app, op.pipeline_identity),
                         ("user@example.invalid", "recorded", "user", "azure_portal", None))
        completeness = result.document.completeness
        self.assertEqual((completeness.not_before, completeness.queried_at, completeness.polls, completeness.settled),
                         ("2026-10-04T11:16:57.000000Z", "2026-10-04T11:16:57.000000Z", 1, True))
        self.assertEqual(self.clock.slept, [592.0])
        self.assertEqual(result.document.outcome, "complete")

    def test_without_an_anchor_the_portal_write_is_the_latest(self):
        resource = self.one(self.real(with_anchor=False))
        self.assertEqual((resource.verdict, resource.window.kind), ("latest_capable_operation", "lookback"))
        self.assertEqual([op.client_app for op in resource.operations], ["azure_cli", "azure_cli", "azure_portal"])
        self.assertEqual(resource.decisive_operation, "op-3")
        self.assertEqual(resource.property_link, "inferred_not_provable")


# ---------------------------------------------------------------------------
# Verdict matrix (G4)
# ---------------------------------------------------------------------------

class VerdictTests(_Base):
    def test_sole_and_latest(self):
        rows = self.log.tags(at_time(8))
        self.assertEqual(self.verdict(rows=rows), ("sole_capable_operation", None))
        self.assertEqual(self.verdict(rows=rows, anchors=None), ("latest_capable_operation", None))

    def test_two_capable_operations_are_ambiguous_with_an_anchor(self):
        rows = self.log.tags(at_time(8)) + self.log.tags(at_time(9), caller=OTHER_CALLER)
        self.assertEqual(self.verdict(rows=rows), ("ambiguous", "multiple_capable_operations"))
        resource = self.one(self.inv_run(rows=rows))
        self.assertEqual((resource.decisive_operation, resource.property_link),
                         (None, "inferred_not_provable"))
        # without an anchor the latest of two non-overlapping writes is reported
        self.assertEqual(self.verdict(rows=rows, anchors=None), ("latest_capable_operation", None))

    def test_capable_operation_during_observation(self):
        during = self.log.tags(at_time(10, 0, 30, day=dt.datetime(2026, 10, 3, tzinfo=UTC)))
        self.assertEqual(self.verdict(rows=self.log.tags(at_time(8)) + during), ("ambiguous", "during_observation"))

    def test_unclassified_operation(self):
        action = self.log.rows(at_time(7), op=f"{NSG_OPS}/someAction/action", statuses=("Succeeded",))
        rows = self.log.tags(at_time(8)) + action
        self.assertEqual(self.verdict(rows=rows), ("ambiguous", "unclassified_operation"))
        self.assertEqual(self.verdict(rows=action), ("ambiguous", "unclassified_operation"))
        # an earlier unclassified operation does not prevent "latest" without an anchor
        self.assertEqual(self.verdict(rows=rows, anchors=None), ("latest_capable_operation", None))

    def test_other_resources_and_children_never_decide(self):
        child = self.log.rows(at_time(8, 30), rid=RULE_ID, op=f"{NSG_OPS}/securityRules/write")
        child_tags = self.log.rows(at_time(8, 40), rid=f"{RULE_ID}/providers/Microsoft.Resources/tags/default",
                                   op=TAGS_OP, statuses=("Succeeded",))
        resource = self.one(self.inv_run(rows=self.log.tags(at_time(8)) + child + child_tags))
        self.assertEqual(resource.verdict, "sole_capable_operation")
        self.assertEqual((resource.descendant_events, resource.descendant_operations),
                         (3, {f"{NSG_OPS}/securityRules/write".lower(): 2, TAGS_OP.lower(): 1}))
        self.assertEqual(len(resource.operations), 1)

    def test_resource_group_contents_never_decide(self):
        entries = ([raw_entry(RG_ADDR, ["update"], {"id": RG_ID, "name": RG, "tags": {"a": "1"}},
                              {"id": RG_ID, "name": RG, "tags": {"a": "2"}}, rtype="azurerm_resource_group")],
                   [raw_entry(RG_ADDR, ["update"], {"id": RG_ID, "name": RG, "tags": {"a": "2"}},
                              {"id": RG_ID, "name": RG, "tags": {"a": "1"}}, rtype="azurerm_resource_group")])
        anchors = self.dir("anchors")
        self.anchor(anchors, "run-400-1", in_sync(RG_ADDR, RG_ID, "azurerm_resource_group"))
        deployment = self.log.rows(at_time(8, 30), rid=f"{RG_ID}/providers/Microsoft.Resources/deployments/d1",
                                   op="Microsoft.Resources/deployments/write")
        vnet = self.log.rows(at_time(8, 40), rid=VNET_ID, op="Microsoft.Network/virtualNetworks/write")
        resource = self.one(self.inv_run(entries, self.log.tags(at_time(8), rid=RG_ID) + deployment + vnet,
                                     anchors=anchors))
        self.assertEqual((resource.verdict, resource.descendant_events), ("sole_capable_operation", 4))

    def test_after_observation_is_listed_only(self):
        later = self.log.tags(at_time(10, 7, day=dt.datetime(2026, 10, 3, tzinfo=UTC)))
        resource = self.one(self.inv_run(rows=self.log.tags(at_time(8)) + later))
        self.assertEqual(resource.verdict, "sole_capable_operation")
        self.assertEqual([op.timing for op in resource.operations], ["before_observation", "after_observation"])
        self.assertEqual(self.verdict(rows=later), ("no_capable_operation_found", None))

    def test_failed_groups_are_listed_only(self):
        failed = self.log.tags(at_time(7), statuses=("Started", "Failed"))
        resource = self.one(self.inv_run(rows=failed + self.log.tags(at_time(8))))
        self.assertEqual(resource.verdict, "sole_capable_operation")
        self.assertEqual([op.outcome for op in resource.operations], ["failed", "successful"])
        self.assertEqual(self.verdict(rows=failed), ("no_capable_operation_found", None))

    def test_unresolved_group(self):
        unresolved = self.log.tags(at_time(7), statuses=("Started", "Accepted"))
        self.assertEqual(self.verdict(rows=unresolved + self.log.tags(at_time(8))), ("ambiguous", "unresolved_operation"))

    def test_none_found_is_never_no_change(self):
        resource = self.one(self.inv_run(rows=[]))
        self.assertEqual((resource.verdict, resource.property_link, resource.decisive_operation),
                         ("no_capable_operation_found", "none", None))
        self.assertEqual(resource.actor_attribution.status, "not_confirmed")

    def test_irrelevant_table_operation(self):
        # only "other" drifted: a tags write cannot explain it
        resource = self.one(self.inv_run(nsg_drift("other"), self.log.tags(at_time(8))))
        self.assertEqual((resource.verdict, resource.property_link), ("no_capable_operation_found", "none"))
        self.assertEqual(resource.operations[0].role, "irrelevant")


class PropertyAreaTests(_Base):
    def test_areas(self):
        self.assertEqual(self.one(self.inv_run(nsg_drift("tags"))).relevant_areas, ["tags"])
        self.assertEqual(self.one(self.inv_run(nsg_drift("other"))).relevant_areas, ["other"])
        self.assertEqual(self.one(self.inv_run(nsg_drift("both"))).relevant_areas, ["other", "tags"])
        self.assertEqual(self.one(self.inv_run(nsg_drift("delete"))).relevant_areas, ["existence_delete"])
        item = {"drift_action": "replace"}
        self.assertEqual(inv.relevant_areas(item), ["existence_create", "existence_delete"])
        self.assertEqual(inv.relevant_areas({"drift_action": "create"}), ["existence_create"])
        noise_only = {"drift_action": "update", "attribute_changes": [
            {"path": ["tags", "x"], "class": "drifted", "assessment": {"category": "noise"}},
            {"path": ["etag"], "class": "config_changed", "assessment": {"category": "configured"}}]}
        self.assertEqual(inv.relevant_areas(noise_only), ["other"])

    def test_partial_capability(self):
        both = nsg_drift("both")
        self.assertEqual(self.verdict(both, self.log.tags(at_time(8))), ("ambiguous", "partial_capability"))
        self.assertEqual(self.verdict(both, self.log.tags(at_time(8)), anchors=None), ("ambiguous", "partial_capability"))
        # one lifecycle write explains both areas
        self.assertEqual(self.verdict(both, self.log.write(at_time(8))), ("sole_capable_operation", None))
        # a tags write and a lifecycle write: two capable operations
        rows = self.log.tags(at_time(8)) + self.log.write(at_time(9))
        self.assertEqual(self.verdict(both, rows), ("ambiguous", "multiple_capable_operations"))
        # without an anchor, the latest explains both
        self.assertEqual(self.verdict(both, rows, anchors=None), ("latest_capable_operation", None))
        reversed_rows = self.log.write(at_time(8)) + self.log.tags(at_time(9))
        self.assertEqual(self.verdict(both, reversed_rows, anchors=None), ("ambiguous", "partial_capability"))

    def test_capability_table(self):
        arm = al.parse_resource_id(NSG_ID)
        self.assertEqual(inv.capable_areas(f"{NSG_OPS}/write".lower(), {"exact"}, arm),
                         ["existence_create", "other", "tags"])
        self.assertEqual(inv.capable_areas(f"{NSG_OPS}/delete".lower(), {"exact"}, arm), ["existence_delete"])
        self.assertEqual(inv.capable_areas(TAGS_OP.lower(), {"exact", "extension"}, arm), ["tags"])
        self.assertEqual(inv.capable_areas(f"{NSG_OPS}/write".lower(), {"extension"}, arm), [])
        self.assertEqual(inv.capable_areas("microsoft.authorization/locks/write", {"exact"}, arm), [])


class UnreadableEventTests(_Base):
    BAD = {"operationName": {"value": "not a valid name"}}

    def bad_row(self):
        return [ev(9999, ts="2026-10-02T07:30:00Z", **self.BAD)]

    def test_every_verdict(self):
        rows = self.log.tags(at_time(8))
        self.assertEqual(self.verdict(rows=rows + self.bad_row()), ("ambiguous", "unreadable_events_in_scope"))
        self.assertEqual(self.verdict(rows=rows + self.bad_row(), anchors=None),
                         ("ambiguous", "unreadable_events_in_scope"))
        resource = self.one(self.inv_run(rows=self.bad_row()))
        self.assertEqual((resource.verdict, resource.reason, resource.unreadable_events_in_scope, resource.window.kind),
                         ("not_investigated", "unreadable_events_in_scope", True, "anchor"))
        # an already ambiguous result keeps its own reason
        two = rows + self.log.tags(at_time(9))
        self.assertEqual(self.verdict(rows=two + self.bad_row()), ("ambiguous", "multiple_capable_operations"))

    def test_each_unreadable_drop_reason_counts_and_harmless_ones_do_not(self):
        cases = {
            "invalid_operation_name": self.BAD,
            "invalid_timestamp": {"eventTimestamp": "yesterday"},
            "invalid_resource_id": {"resourceId": "/not/an/arm/id"},
            "invalid_event_data_id": {"eventDataId": "bad id!"},
        }
        rows = self.log.tags(at_time(8))
        for reason, overrides in cases.items():
            with self.subTest(reason):
                bad = [ev(9000 + len(reason), ts="2026-10-02T07:30:00Z", **overrides)]
                result = self.inv_run(rows=rows + bad)
                self.assertIn(reason, json.loads(result.evidence_bytes)["scopes"][0]["dropped"])
                self.assertEqual(self.one(result).reason, "unreadable_events_in_scope")
        harmless = [ev(9100, ts="2026-10-02T07:30:00Z", category={"value": "ServiceHealth"}),
                    ev(9101, ts="2026-10-02T07:30:00Z", resourceId=f"/subscriptions/{SUB}/resourceGroups/{RG}/"
                                                                    "providers/Microsoft.Web/sites/elsewhere")]
        self.assertEqual(self.verdict(rows=rows + harmless + [rows[0]]), ("sole_capable_operation", None))
        conflicting = [dict(rows[0], caller=OTHER_CALLER)]
        self.assertEqual(self.one(self.inv_run(rows=rows + conflicting)).reason, "unreadable_events_in_scope")

    def test_deletion_is_blocked(self):
        resource = self.one(self.inv_run(nsg_drift("delete"), self.log.write(at_time(8)) + self.log.delete(at_time(9))
                                     + self.bad_row(), anchors=None))
        self.assertEqual((resource.verdict, resource.reason), ("ambiguous", "unreadable_events_in_scope"))
        self.assertEqual((resource.deletion_rule.status, resource.deletion_rule.reason),
                         ("unknown", "unreadable_events_in_scope"))
        self.assertEqual(resource.property_link, "inferred_not_provable")


class AutomatedActivityTests(_Base):
    def test_policy_with_the_same_correlation_is_attached(self):
        rows = self.log.tags(at_time(8))
        policy = self.log.policy(at_time(8, 0, 1), corr=corr_of(rows))
        resource = self.one(self.inv_run(rows=rows + policy))
        self.assertEqual(resource.verdict, "sole_capable_operation")
        self.assertEqual(resource.operations[0].attached_event_ids, [policy[0]["eventDataId"]])
        self.assertEqual(resource.automated_events, [])

    def test_separate_policy_or_autoscale_activity_is_a_signal(self):
        for category in ("Policy", "Autoscale"):
            with self.subTest(category):
                rows = self.log.tags(at_time(8)) + self.log.policy(at_time(7), category=category)
                self.assertEqual(self.verdict(rows=rows), ("ambiguous", "automated_activity"))
                self.assertEqual(self.verdict(rows=self.log.policy(at_time(7), category=category)),
                                 ("ambiguous", "automated_activity"))

    def test_policy_events_are_never_capable(self):
        policy_tags = self.log.rows(at_time(8), op=TAGS_OP, category="Policy", statuses=("Succeeded",))
        resource = self.one(self.inv_run(rows=policy_tags))
        self.assertEqual((resource.verdict, resource.reason, resource.operations),
                         ("ambiguous", "automated_activity", []))

    def test_outside_window_or_after_observation_is_no_signal(self):
        rows = self.log.tags(at_time(8))
        before_window = self.log.policy(at_time(5))  # the NSG's anchored window starts at 05:59
        after = self.log.policy(at_time(10, 7, day=dt.datetime(2026, 10, 3, tzinfo=UTC)))
        result = self.inv_run(nsg_and_rg(), rows + before_window + after)
        resource = next(r for r in result.document.resources if r.address == NSG_ADDR)
        self.assertEqual(resource.verdict, "sole_capable_operation")
        self.assertEqual([(a.in_window, a.timing, a.signal) for a in resource.automated_events],
                         [(False, "before_observation", False), (True, "after_observation", False)])


class TimingTests(_Base):
    def test_after_observation_boundary(self):
        day3 = dt.datetime(2026, 10, 3, tzinfo=UTC)
        for second, timing in ((0, "during_observation"), (1, "after_observation")):
            with self.subTest(second):
                rows = self.log.rows(at_time(10, 6, second, day=day3), op=TAGS_OP, statuses=("Succeeded",))
                self.assertEqual(self.one(self.inv_run(rows=rows)).operations[0].timing, timing)

    def test_exact_skew_edge(self):
        day3 = dt.datetime(2026, 10, 3, tzinfo=UTC)
        edge = self.log.rows(at_time(9, 59, day=day3), op=TAGS_OP, statuses=("Succeeded",))
        self.assertEqual(self.one(self.inv_run(rows=edge)).operations[0].timing, "during_observation")
        just = self.log.rows(at_time(9, 58, 59, day=day3), op=TAGS_OP, statuses=("Succeeded",))
        self.assertEqual(self.one(self.inv_run(rows=just)).operations[0].timing, "before_observation")

    def nsg_result(self, rows):
        result = self.inv_run(nsg_and_rg(), rows)
        return next(r for r in result.document.resources if r.address == NSG_ADDR)

    def test_window_membership_includes_straddling_operations(self):
        # the NSG's anchored window starts 2026-10-02 05:59:00; the run-level window is the lookback
        straddling = self.log.tags(at_time(5, 58, 50), step=20)  # [05:58:50, 05:59:10]
        before = self.log.tags(at_time(5, 50))  # ends 05:50:02
        resource = self.nsg_result(before + straddling + self.log.tags(at_time(8)))
        self.assertEqual([op.in_window for op in resource.operations], [False, True, True])
        self.assertEqual((resource.verdict, resource.reason), ("ambiguous", "multiple_capable_operations"))
        resource = self.nsg_result(before + self.log.tags(at_time(8)))
        self.assertEqual(resource.verdict, "sole_capable_operation")  # an operation before the window is no candidate
        exactly = self.log.rows(at_time(5, 59), op=TAGS_OP, statuses=("Succeeded",))
        self.assertTrue(self.nsg_result(exactly).operations[0].in_window)
        just_before = self.log.rows(at_time(5, 58, 59), op=TAGS_OP, statuses=("Succeeded",))
        self.assertFalse(self.nsg_result(just_before).operations[0].in_window)

    def test_collection_starts_at_the_run_level_window(self):
        # one anchored resource: nothing before its window is even collected
        early = self.log.tags(at_time(5, 50))
        result = self.inv_run(rows=early + self.log.tags(at_time(8)))
        self.assertEqual(len(self.one(result).operations), 1)
        self.assertEqual(json.loads(result.evidence_bytes)["scopes"][0]["dropped"], {"timestamp_outside_window": 2})

    def test_overlapping_latest_is_ambiguous(self):
        first = self.log.tags(at_time(8), step=10)  # [08:00:00, 08:00:10]
        second = self.log.tags(at_time(8, 0, 10), step=2)  # starts at the first's end
        self.assertEqual(self.verdict(rows=first + second, anchors=None), ("ambiguous", "multiple_capable_operations"))
        third = self.log.tags(at_time(8, 0, 11), step=2)
        self.assertEqual(self.verdict(rows=first + third, anchors=None), ("latest_capable_operation", None))
        # an overlapping unclassified operation inside the latest capable one
        action = self.log.rows(at_time(8, 0, 5), op=f"{NSG_OPS}/someAction/action", statuses=("Succeeded",))
        self.assertEqual(self.verdict(rows=first + action, anchors=None), ("ambiguous", "unclassified_operation"))
        self.assertEqual(self.verdict(rows=action + self.log.tags(at_time(8, 0, 5)), anchors=None),
                         ("ambiguous", "unclassified_operation"))


class SettlingTests(_Base):
    def test_first_query_at_finished_plus_m(self):
        self.inv_run(rows=self.log.tags(at_time(8)))
        self.assertEqual(self.clock.slept, [(NOT_BEFORE - dt.datetime(2026, 10, 3, 10, 6, tzinfo=UTC)).total_seconds()])
        late = FakeClock(NOT_BEFORE + dt.timedelta(minutes=3))
        result = self.inv_run(rows=self.log.tags(at_time(8)), clock=late)
        self.assertEqual(late.slept, [])
        self.assertEqual(result.document.completeness.not_before, iso(NOT_BEFORE))

    def test_settling_is_measured_from_finished_at(self):
        # a long observation: started 10:00, finished 10:30 -> first query at 10:40, not 10:10
        paths = self.plan(nsg_drift(), finished="2026-10-03T10:30:00Z")
        result = self.inv_run(paths=paths, rows=self.log.tags(at_time(8)))
        self.assertEqual(result.document.completeness.queried_at, "2026-10-03T10:40:00.000000Z")

    def test_polls_until_a_capable_operation_appears(self):
        rows = self.log.tags(at_time(8))
        source = PollingSource([{RG: [page()]}, {RG: [page()]}, {RG: [page(*rows)]}])
        result = self.inv_run(rows=None, source=source)
        self.assertEqual((source.calls, result.document.completeness.polls), (3, 3))
        self.assertEqual(result.document.completeness.queried_at, iso(NOT_BEFORE + dt.timedelta(minutes=4)))
        self.assertEqual(self.one(result).verdict, "sole_capable_operation")

    def test_polls_stop_at_the_cap(self):
        source = PollingSource([{RG: [page()]}])
        result = self.inv_run(rows=None, source=source)
        self.assertEqual(source.calls, 6)  # 10:15, :17, :19, :21, :23, :25
        self.assertEqual(result.document.completeness.queried_at, iso(POLL_END))
        self.assertEqual(self.one(result).verdict, "no_capable_operation_found")
        late = FakeClock(POLL_END - dt.timedelta(minutes=1, seconds=59))
        source = PollingSource([{RG: [page()]}])
        self.inv_run(rows=None, source=source, clock=late)
        self.assertEqual(source.calls, 1)

    def test_not_settled_evidence_is_not_investigated(self):
        paths = self.plan(nsg_drift())
        report = report_of(paths)
        evidence = al.collect_evidence(*paths, source=FakeSource({RG: [page(*self.log.tags(at_time(8)))]}),
                                       queried_at=NOT_BEFORE - dt.timedelta(seconds=1))
        failure, resources = inv.correlate(report, evidence, inv.AnchorSelection(), 30)
        self.assertEqual((failure, resources[0]["verdict"], resources[0]["reason"]),
                         (None, "not_investigated", "evidence_not_settled"))
        evidence = al.collect_evidence(*paths, source=FakeSource({RG: [page(*self.log.tags(at_time(8)))]}),
                                       queried_at=NOT_BEFORE)
        self.assertEqual(inv.correlate(report, evidence, inv.AnchorSelection(), 30)[1][0]["verdict"],
                         "latest_capable_operation")

    def test_no_wait_without_a_queryable_target(self):
        no_drift = self.plan(in_sync())
        result = self.inv_run(paths=no_drift, source=NoCallSource())
        self.assertEqual((self.clock.slept, result.document.resources, result.document.completeness.not_before),
                         ([], [], None))
        no_id = self.plan(([raw_entry(NSG_ADDR, ["update"], nsg(DELETE), nsg(DELETE, tags={"e": "x"}))],
                           [raw_entry(NSG_ADDR, ["update"], nsg(DELETE, tags={"e": "x"}), nsg(DELETE))]))
        result = self.inv_run(paths=no_id, source=NoCallSource())
        self.assertEqual(self.clock.slept, [])
        self.assertEqual((self.one(result).verdict, self.one(result).reason), ("not_investigated", "no_resource_id"))
        self.assertIsNone(result.document.completeness.not_before)

    def test_unknown_detection_time_queries_nothing(self):
        paths = self.plan(nsg_drift(), started=DELETE)
        result = self.inv_run(paths=paths, source=NoCallSource())
        self.assertEqual((self.one(result).reason, result.evidence_bytes, result.document.completeness),
                         ("detection_time_unknown", None, None))
        self.assertEqual(self.clock.slept, [])


class NotInvestigatedTests(_Base):
    def test_collection_failure(self):
        result = self.inv_run(rows=None, source=FakeSource({RG: [al.SourceError("authorization_failed", 403)]}))
        self.assertEqual((result.document.outcome, result.document.failure.reason), ("failed", "evidence_failed"))
        self.assertEqual(self.one(result).reason, "evidence_failed")

    def test_incomplete_scope(self):
        source = FakeSource({RG: [page(more=True), page()]})
        result = self.inv_run(rows=None, source=source, limits=al.Limits(max_pages_per_scope=1))
        self.assertEqual((self.one(result).verdict, self.one(result).reason), ("not_investigated", "evidence_incomplete"))
        self.assertEqual(result.document.outcome, "incomplete")

    def test_binding_mismatch(self):
        paths = self.plan(nsg_drift())
        other = self.plan(nsg_drift(), run_id="github-501-1")
        evidence = al.collect_evidence(*other, source=FakeSource(), queried_at=NOT_BEFORE)
        failure, resources = inv.correlate(report_of(paths), evidence, inv.AnchorSelection(), 30)
        self.assertEqual((failure, resources[0]["reason"]),
                         ({"stage": "binding", "reason": "evidence_mismatch"}, "evidence_mismatch"))

    def test_window_not_covered_by_the_evidence(self):
        paths = self.plan(nsg_drift())
        evidence = al.collect_evidence(*paths, source=FakeSource(), queried_at=NOT_BEFORE, lookback_days=1)
        anchors = self.anchors()
        selection = inv.select_anchor_runs(anchors, report_of(paths), REPO)
        self.assertEqual(inv.correlate(report_of(paths), evidence, selection, 1)[1][0]["reason"],
                         "evidence_incomplete")


# ---------------------------------------------------------------------------
# Deletion, property link and actor attribution (G5, Option A)
# ---------------------------------------------------------------------------

class DeletionTests(_Base):
    def test_anchor_a_confirmation_under_latest(self):
        rows = self.log.write(at_time(8)) + self.log.delete(at_time(9))
        resource = self.one(self.inv_run(nsg_drift("delete"), rows, anchors=None))
        self.assertEqual((resource.verdict, resource.property_link, resource.property_link_reason),
                         ("latest_capable_operation", "confirmed", None))
        self.assertEqual(resource.actor_attribution.model_dump(),
                         {"status": "confirmed", "rule": "external_deletion_v1",
                          "claim": "recorded_successful_delete", "caller": CALLER})
        self.assertEqual(resource.deletion_rule.anchor.kind, "write_event")
        self.assertEqual(resource.operations[0].role, "irrelevant")  # a write cannot explain a deletion

    def test_anchor_b_confirmation_under_sole(self):
        resource = self.one(self.inv_run(nsg_drift("delete"), self.log.delete(at_time(9))))
        self.assertEqual((resource.verdict, resource.property_link), ("sole_capable_operation", "confirmed"))
        self.assertEqual(resource.deletion_rule.anchor.model_dump(),
                         {"kind": "prior_detection_run", "event_ids": [], "run_id": "github-400-1",
                          "time": "2026-10-02T06:01:00.000000Z"})
        # without anchor B there is no existence proof
        resource = self.one(self.inv_run(nsg_drift("delete"), self.log.delete(at_time(9)), anchors=None))
        self.assertEqual((resource.verdict, resource.deletion_rule.reason, resource.property_link,
                          resource.property_link_reason),
                         ("latest_capable_operation", "no_existence_anchor", "inferred_not_provable",
                          "deletion_rule_not_confirmed"))

    def test_later_anchor_wins_and_overlap_is_order_ambiguous(self):
        # anchor A (write at 08:00) is later than anchor B (06:01): A is used
        rows = self.log.write(at_time(8)) + self.log.delete(at_time(9))
        resource = self.one(self.inv_run(nsg_drift("delete"), rows))
        self.assertEqual(resource.deletion_rule.anchor.kind, "write_event")
        # a lifecycle operation overlapping anchor B's observation (06:00-06:01 +/- 60 s)
        rows = self.log.delete(at_time(6, 1, 30)) + self.log.delete(at_time(9))
        resource = self.one(self.inv_run(nsg_drift("delete"), rows))
        self.assertEqual(resource.deletion_rule.reason, "order_ambiguous")
        self.assertNotEqual(resource.property_link, "confirmed")
        # just after the overlap window (06:02:01) it counts as after the anchor
        rows = self.log.delete(at_time(6, 2, 1), statuses=("Succeeded",)) + self.log.delete(at_time(9))
        self.assertEqual(self.one(self.inv_run(nsg_drift("delete"), rows)).deletion_rule.reason,
                         "multiple_successful_deletes")

    def test_option_a_no_confirmation_under_an_ambiguous_verdict(self):
        # an unclassified operation after the delete: the latest candidate is not the delete
        action = self.log.rows(at_time(9, 30), op=f"{NSG_OPS}/someAction/action", statuses=("Succeeded",))
        rows = self.log.write(at_time(8)) + self.log.delete(at_time(9)) + action
        resource = self.one(self.inv_run(nsg_drift("delete"), rows, anchors=None))
        self.assertEqual(resource.deletion_rule.status, "confirmed")  # the rule alone would confirm
        self.assertEqual((resource.verdict, resource.property_link, resource.property_link_reason),
                         ("ambiguous", "inferred_not_provable", "verdict_not_decisive"))
        self.assertEqual(resource.actor_attribution.status, "not_confirmed")
        # a Policy event 30 minutes away: outside R7's 5 minutes, but a G4 signal
        rows = self.log.write(at_time(8)) + self.log.delete(at_time(9)) + self.log.policy(at_time(9, 30))
        resource = self.one(self.inv_run(nsg_drift("delete"), rows, anchors=None))
        self.assertEqual((resource.deletion_rule.status, resource.verdict, resource.property_link_reason),
                         ("confirmed", "ambiguous", "verdict_not_decisive"))

    def test_r7_window_is_independent_of_the_skew(self):
        for minutes, expected in ((4, "automated_activity_overlap"), (6, None)):
            with self.subTest(minutes):
                rows = (self.log.write(at_time(8)) + self.log.delete(at_time(9))
                        + self.log.policy(at_time(9, minutes), corr=None))
                resource = self.one(self.inv_run(nsg_drift("delete"), rows, anchors=None))
                self.assertEqual(resource.deletion_rule.reason, expected)

    def test_update_drift_is_never_confirmed(self):
        for entries, rows in ((nsg_drift("tags"), self.log.tags(at_time(8))),
                              (nsg_drift("other"), self.log.write(at_time(8))),
                              (nsg_drift("both"), self.log.write(at_time(8)))):
            with self.subTest(relevant=entries[0][0]["change"]["after"]):
                resource = self.one(self.inv_run(entries, rows))
                self.assertEqual((resource.verdict, resource.property_link, resource.deletion_rule),
                                 ("sole_capable_operation", "inferred_not_provable", None))
                self.assertEqual(resource.actor_attribution.status, "not_confirmed")


# ---------------------------------------------------------------------------
# Anchor candidates (G9)
# ---------------------------------------------------------------------------

class AnchorTests(_Base):
    def select(self, anchors, paths=None):
        paths = paths or self.plan(nsg_drift())
        return inv.select_anchor_runs(anchors, report_of(paths), REPO)

    def rejection(self, **kwargs):
        anchors = self.dir("anchors")
        self.anchor(anchors, "run-1", **kwargs)
        selection = self.select(anchors)
        self.assertEqual(selection.accepted, [])
        return selection.rejected[0][1]

    def test_accepted(self):
        selection = self.select(self.anchors())
        (run,) = selection.accepted
        self.assertEqual((run.run_id, NSG_ADDR in run.in_sync, selection.examined), ("github-400-1", True, 1))

    def test_every_trust_check(self):
        good_report = None
        cases = {
            "wrong_repository": {"repository": "someone/else"},
            "wrong_workflow": {"workflow_path": ".github/workflows/other.yml"},
            "wrong_branch": {"head_branch": "feature"},
            "wrong_event": {"event": "push"},
            "same_run": {"run": 500},
            "environment_mismatch": {"environment": "prod"},
            "not_earlier": {"started": "2026-10-03T09:00:00Z", "finished": "2026-10-03T10:00:00Z"},
            "plan_not_earlier": {"plan_ts": "2026-10-03T10:02:00Z"},
            "outside_retention": {"started": "2026-07-01T06:00:00Z", "finished": "2026-07-01T06:01:00Z",
                                  "plan_ts": "2026-07-01T06:00:30Z"},
            "observation_unknown": {"started": "2026-10-02T06:02:00Z", "finished": "2026-10-02T06:01:00Z"},
        }
        for reason, kwargs in cases.items():
            with self.subTest(reason):
                self.assertEqual(self.rejection(**kwargs), reason)
        self.assertEqual(self.rejection(run=500, attempt=2), "same_run")  # another attempt of the current run
        for meta in ({"id": DELETE}, {"id": "400"}, {"id": True}, {"extra": 1}, {"run_attempt": 0}):
            with self.subTest(meta=meta):
                self.assertEqual(self.rejection(**meta), "metadata_invalid")
        self.assertEqual(self.rejection(report=b"not json"), "report_invalid")
        self.assertEqual(self.rejection(report=b'{"a": 1, "a": 2}'), "report_invalid")
        failed = report_bytes(self.plan(nsg_drift(), run_id="github-400-1", outcome="failed"))
        self.assertEqual(self.rejection(report=failed), "report_failed")
        other_binding = report_bytes(self.plan(in_sync(), run_id="github-401-1", plan_ts="2026-10-02T06:00:30Z",
                                               started="2026-10-02T06:00:00Z", finished="2026-10-02T06:01:00Z"))
        self.assertEqual(self.rejection(report=other_binding), "run_binding_mismatch")
        del good_report

    def test_the_current_report_can_never_be_an_anchor(self):
        paths = self.plan(nsg_drift())
        current = report_bytes(paths)
        anchors = self.dir("anchors")
        self.anchor(anchors, "a-same-id", run=500, report=current)
        self.anchor(anchors, "b-other-id", run=501, report=current)
        self.anchor(anchors, "c-bound", run=500, attempt=1, report=current, event="workflow_dispatch")
        selection = self.select(anchors, paths)
        self.assertEqual(selection.accepted, [])
        self.assertEqual(dict(selection.rejected), {"a-same-id": "same_run", "b-other-id": "run_binding_mismatch",
                                                    "c-bound": "same_run"})

    def test_non_candidates_ordering_and_limit(self):
        anchors = self.dir("anchors")
        with open(os.path.join(anchors, "a-file.json"), "w") as fh:
            fh.write("{}")
        os.makedirs(os.path.join(anchors, "b-no-run-json"))
        link_target = self.anchor(self.dir("elsewhere"), "linked")
        os.symlink(link_target, os.path.join(anchors, "c-symlink"))
        for n in range(55):
            self.anchor(anchors, f"run-{n:03d}", run=1000 + n,
                        started=f"2026-10-02T06:{n:02d}:00Z", finished=f"2026-10-02T06:{n:02d}:30Z",
                        plan_ts=f"2026-10-02T06:{n:02d}:10Z")
        selection = self.select(anchors)
        rejected = dict(selection.rejected)
        self.assertEqual({k: v for k, v in rejected.items() if not k.startswith("run-")},
                         {"a-file.json": "not_a_candidate", "b-no-run-json": "not_a_candidate",
                          "c-symlink": "not_a_candidate"})
        self.assertEqual(selection.examined, 50)
        self.assertEqual(sorted(k for k, v in rejected.items() if v == "candidate_limit"),
                         [f"run-{n:03d}" for n in range(50, 55)])
        self.assertEqual(len(selection.accepted), 50)
        self.assertEqual(selection.for_address(NSG_ADDR).candidate, "run-049")  # latest examined
        inv.AnchorCandidates.model_validate(selection.doc())

    def test_address_not_in_sync_is_no_anchor(self):
        anchors = self.dir("anchors")
        self.anchor(anchors, "run-400-1", nsg_drift())  # the NSG had drifted then too
        resource = self.one(self.inv_run(rows=self.log.tags(at_time(8)), anchors=anchors))
        self.assertEqual((resource.window.kind, resource.verdict), ("lookback", "latest_capable_operation"))

    def test_latest_in_sync_run_is_chosen(self):
        anchors = self.dir("anchors")
        self.anchor(anchors, "run-old", run=398, started="2026-10-01T06:00:00Z", finished="2026-10-01T06:01:00Z",
                    plan_ts="2026-10-01T06:00:30Z")
        self.anchor(anchors, "run-new", run=399)
        between = self.log.tags(at_time(12, day=dt.datetime(2026, 10, 1, tzinfo=UTC)))  # between the two anchors
        result = self.inv_run(nsg_and_rg(), between + self.log.tags(at_time(8)), anchors=anchors)
        resource = next(r for r in result.document.resources if r.address == NSG_ADDR)
        self.assertEqual((resource.window.anchor, resource.verdict), ("run-new", "sole_capable_operation"))
        self.assertEqual([op.in_window for op in resource.operations], [False, True])

    def test_unreadable_anchor_directory(self):
        result = self.inv_run(rows=None, anchors=os.path.join(self.tmp, "missing"), source=NoCallSource())
        self.assertEqual((result.document.outcome, result.document.failure.reason),
                         ("failed", "anchor_directory_unreadable"))

    def test_run_level_window_start(self):
        source = FakeSource()
        self.inv_run(rows=None, source=source)
        self.assertIn("eventTimestamp ge '2026-10-02T05:59:00Z'", source.calls[0][1])
        source = FakeSource()
        self.inv_run(rows=None, source=source, anchors=None)
        self.assertIn("eventTimestamp ge '2026-09-03T10:15:00Z'", source.calls[0][1])


# ---------------------------------------------------------------------------
# Report binding, contract, re-check, determinism
# ---------------------------------------------------------------------------

class ReportBindingTests(_Base):
    def test_report_must_match_plan_and_manifest(self):
        paths = self.plan(nsg_drift())
        good = json.loads(report_bytes(paths))
        tampered = copy.deepcopy(good)
        tampered["resources"][0]["severity"]["level"] = "CRITICAL"
        for data, reason in ((json.dumps(tampered).encode(), "report_mismatch"), (b"{", "report_invalid"),
                             (b'{"outcome": "succeeded"}', "report_invalid"),
                             (report_bytes(self.plan(nsg_drift("other"))), "report_mismatch")):
            with self.subTest(reason):
                result = self.inv_run(paths=paths, report=data, source=NoCallSource(), rows=None)
                self.assertEqual((result.document.failure.reason, result.document.resources, self.clock.slept),
                                 (reason, [], []))
        # key order and whitespace do not matter (canonical hash)
        compact = json.dumps(good, separators=(",", ":")).encode()
        self.assertEqual(self.inv_run(paths=paths, report=compact, rows=self.log.tags(at_time(8))).document.outcome,
                         "complete")

    def test_failed_run_report(self):
        paths = self.plan(nsg_drift(), outcome="failed")
        result = self.inv_run(paths=paths, source=NoCallSource(), rows=None)
        self.assertEqual(result.document.failure.reason, "report_failed")

    def test_hash_matches_ai_engine(self):
        try:
            from ai_engine.nodes.report_generator import drift_report_sha256
        except ImportError:
            self.skipTest("needs the ai extra")
        paths = self.plan(nsg_drift())
        result = self.inv_run(paths=paths, rows=self.log.tags(at_time(8)))
        self.assertEqual(result.document.binding.drift_report_sha256, drift_report_sha256(json.loads(report_bytes(paths))))


class ContractTests(_Base):
    def setUp(self):
        super().setUp()
        delete_rows = self.log.write(at_time(8)) + self.log.delete(at_time(9))
        self.delete_doc = self.inv_run(nsg_drift("delete"), delete_rows, anchors=None).document.model_dump(mode="json")
        self.update_doc = self.inv_run(rows=self.log.tags(at_time(8))).document.model_dump(mode="json")

    def invalid(self, doc, mutate, message=None):
        doc = copy.deepcopy(doc)
        mutate(doc["resources"][0] if doc["resources"] else doc)
        with self.assertRaises(ValidationError) as ctx:
            inv.DriftInvestigation.model_validate(doc)
        if message:
            self.assertIn(message, str(ctx.exception))

    def test_valid(self):
        for doc in (self.delete_doc, self.update_doc):
            self.assertEqual(inv.DriftInvestigation.model_validate(doc).model_dump(mode="json"), doc)

    def test_update_drift_can_never_be_confirmed(self):
        def confirm(r):
            r.update(property_link="confirmed", property_link_reason=None)
            r["actor_attribution"].update(status="confirmed", rule="external_deletion_v1",
                                          claim="recorded_successful_delete", caller=CALLER)
        self.invalid(self.update_doc, confirm, "only a deletion can be property-confirmed")

    def test_option_a(self):
        self.invalid(self.delete_doc, lambda r: r.update(verdict="ambiguous", reason="unclassified_operation",
                                                         decisive_operation=None), "Option A")
        self.invalid(self.delete_doc, lambda r: r["actor_attribution"].update(
            status="not_confirmed", rule=None, claim=None, caller=None), "actor attribution")
        self.invalid(self.delete_doc, lambda r: r["deletion_rule"].update(
            status="unknown", reason="no_existence_anchor", rule=None, claim=None, caller=None, anchor=None,
            decisive_event_ids=[]), "confirmed deletion rule")

    def test_verdict_invariants(self):
        doc = self.update_doc
        self.invalid(doc, lambda r: r.update(decisive_operation=None), "decisive operation")
        self.invalid(doc, lambda r: r.update(reason="partial_capability"), "has no reason")
        self.invalid(doc, lambda r: r.update(window={"kind": "lookback", "start": r["window"]["start"],
                                                     "anchor": None}), "anchor window")
        self.invalid(doc, lambda r: r.update(unreadable_events_in_scope=True), "unreadable")
        self.invalid(doc, lambda r: r.update(relevant_areas=["other", "tags"]), "every relevant area")
        self.invalid(doc, lambda r: r.update(verdict="no_capable_operation_found", decisive_operation=None),
                     "no_capable_operation_found lists no successful capable operation")
        self.invalid(doc, lambda r: r["operations"][0].update(role="unclassified"))
        self.invalid(doc, lambda r: r.update(property_link="none", property_link_reason=None))
        self.invalid(doc, lambda r: r.update(reason="made_up"))
        self.invalid(doc, lambda r: r.update(extra=1))
        self.invalid(doc, lambda r: r.update(trust="public"))

    def test_constants(self):
        for path, key, value in ((["rules"], "skew_seconds", 300), (["rules"], "settle_margin_minutes", 20),
                                 (["rules"], "automated_overlap_minutes", 1), (["rules"], "deletion_rules_version", "1"),
                                 ([], "investigation_version", "2"), ([], "trust", "public")):
            with self.subTest(key):
                doc = copy.deepcopy(self.update_doc)
                node = doc
                for part in path:
                    node = node[part]
                node[key] = value
                with self.assertRaises(ValidationError):
                    inv.DriftInvestigation.model_validate(doc)


class RecheckTests(_Base):
    def test_tampering_is_found(self):
        result = self.inv_run(rows=self.log.tags(at_time(8)))
        doc = result.document.model_dump(mode="json")

        def problems(mutate):
            changed = copy.deepcopy(doc)
            mutate(changed["resources"][0]["operations"][0])
            return inv.verify_against_evidence(inv.DriftInvestigation.model_validate(changed), result.evidence_bytes)

        self.assertTrue(problems(lambda op: op.update(caller=OTHER_CALLER)))
        self.assertTrue(problems(lambda op: op.update(start="2026-10-02T07:00:00.000000Z")))
        self.assertTrue(problems(lambda op: op.update(event_ids=sorted(op["event_ids"] + ["00000000-0000-4000-9000-999999999999"]))))
        self.assertTrue(problems(lambda op: op.update(relations=["exact"])))
        self.assertTrue(inv.verify_against_evidence(result.document, result.evidence_bytes + b" "))
        self.assertTrue(inv.verify_against_evidence(result.document, None))


class DeterminismTests(_Base):
    def test_byte_identical_under_shuffling(self):
        rows = (self.log.tags(at_time(8)) + self.log.rows(at_time(8, 30), rid=RULE_ID, op=f"{NSG_OPS}/securityRules/write")
                + self.log.policy(at_time(8, 0, 1)))
        paths = self.plan(nsg_drift())
        anchors = self.anchors()
        baseline = None
        rng = random.Random(7)
        for _ in range(5):
            shuffled = rows[:]
            rng.shuffle(shuffled)
            result = self.inv_run(paths=paths, anchors=anchors, source=FakeSource({RG: [page(*shuffled)]}))
            text = inv.render_investigation(result.document)
            baseline = baseline or text
            self.assertEqual(text, baseline)

    def test_paging_changes_only_the_evidence_hash(self):
        rows = self.log.tags(at_time(8)) + self.log.tags(at_time(9)) + self.log.policy(at_time(8, 0, 1))
        paths = self.plan(nsg_drift())
        anchors = self.anchors()
        one = self.inv_run(paths=paths, anchors=anchors, source=FakeSource({RG: [page(*rows)]})).document
        split = self.inv_run(paths=paths, anchors=anchors,
                             source=FakeSource({RG: [page(*rows[:3], more=True), page(*rows[3:])]})).document
        self.assertNotEqual(one.binding.evidence_sha256, split.binding.evidence_sha256)  # scope page counts differ
        self.assertEqual(one.resources, split.resources)
        self.assertEqual((one.completeness, one.anchor_candidates), (split.completeness, split.anchor_candidates))


class CliTests(_Base):
    def main(self, args, source=None, clock=None):
        clock = clock or FakeClock()
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cli, "_activity_log_source", return_value=source or FakeSource()), \
                mock.patch.object(cli, "_now", clock), mock.patch.object(cli, "_sleep", clock.sleep), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(args)
        return code, out.getvalue(), err.getvalue()

    def args(self, paths, *extra, report=None):
        report_path = os.path.join(self.dir("report"), "drift_report.json")
        with open(report_path, "wb") as fh:
            fh.write(report if report is not None else report_bytes(paths))
        self.output = os.path.join(self.tmp, "investigation.json")
        self.evidence = os.path.join(self.tmp, "evidence.json")
        return ["investigate", "--plan", paths[0], "--manifest", paths[1], "--report", report_path,
                "--output", self.output, "--evidence-output", self.evidence, *extra]

    def test_complete(self):
        paths = self.plan(nsg_drift())
        code, out, err = self.main(self.args(paths, "--anchors", self.anchors(), "--repository", REPO),
                                   FakeSource({RG: [page(*self.log.tags(at_time(8)))]}))
        self.assertEqual(code, 0, err)
        self.assertIn("sole_capable_operation=1", out)
        for path in (self.output, self.evidence):
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        document = inv.DriftInvestigation.model_validate(json.load(open(self.output)))
        self.assertEqual(inv.verify_against_evidence(document, open(self.evidence, "rb").read()), [])
        for text in (out, err):
            for secret in (CALLER, SUB, NSG_ID):
                self.assertNotIn(secret, text)

    def test_anchors_need_a_repository(self):
        paths = self.plan(nsg_drift())
        code, _, err = self.main(self.args(paths, "--anchors", self.anchors()))
        self.assertEqual(code, 2)
        self.assertIn("--repository", err)

    def test_incomplete_and_failed(self):
        paths = self.plan(nsg_drift())
        code, _, err = self.main(self.args(paths), FakeSource({RG: [al.SourceError("throttled", 429)]}))
        self.assertEqual(code, 1)
        self.assertIn("INVESTIGATION FAILED [evidence_failed]", err)
        code, _, err = self.main(self.args(paths, report=b"{}"), NoCallSource())
        self.assertEqual(code, 1)
        self.assertIn("[report_invalid]", err)

    def test_recheck_failure_writes_nothing(self):
        paths = self.plan(nsg_drift())
        with mock.patch.object(inv, "verify_against_evidence", return_value=["boom"]):
            code, _, err = self.main(self.args(paths), FakeSource({RG: [page(*self.log.tags(at_time(8)))]}))
        self.assertEqual(code, 70)
        self.assertFalse(os.path.exists(self.output))

    def test_pipeline_principal_from_environment(self):
        paths = self.plan(nsg_drift())
        principal = "00000000-0000-4000-8000-0000000000cc"
        rows = self.log.rows(at_time(8), op=TAGS_OP, statuses=("Succeeded",))
        rows[0]["claims"] = {"idtyp": "app", "appid": principal}
        with mock.patch.dict(os.environ, {al.PIPELINE_PRINCIPAL_ENV: principal}):
            code, out, err = self.main(self.args(paths), FakeSource({RG: [page(*rows)]}))
        self.assertEqual(code, 0, err)
        op = json.load(open(self.output))["resources"][0]["operations"][0]
        self.assertEqual((op["caller_type"], op["pipeline_identity"]), ("service_principal", True))
        self.assertNotIn(principal, open(self.output).read() + out + err)


class CoverageOfInvariantsTests(_Base):
    """Every contract invariant rejects a tampered document; error paths are exercised."""

    def setUp(self):
        super().setUp()
        self.doc = self.inv_run(nsg_and_rg(), self.log.tags(at_time(5, 50)) + self.log.tags(at_time(8))
                                + self.log.policy(at_time(10, 7, day=dt.datetime(2026, 10, 3, tzinfo=UTC)))
                                ).document.model_dump(mode="json")
        self.nsg = next(i for i, r in enumerate(self.doc["resources"]) if r["address"] == NSG_ADDR)

    def rejects(self, mutate):
        doc = copy.deepcopy(self.doc)
        mutate(doc, doc["resources"][self.nsg])
        with self.assertRaises(ValidationError):
            inv.DriftInvestigation.model_validate(doc)

    def test_tampered_documents_are_rejected(self):
        cases = {
            "op ids unsorted": lambda d, r: r["operations"][0].update(event_ids=list(reversed(
                r["operations"][0]["event_ids"]))),
            "attached is a row": lambda d, r: r["operations"][1].update(
                attached_event_ids=[r["operations"][1]["event_ids"][0]]),
            "start after end": lambda d, r: r["operations"][1].update(start="2026-10-02T09:00:00.000000Z"),
            "caller without recorded": lambda d, r: r["operations"][1].update(caller_status="missing"),
            "signal mismatch": lambda d, r: r["automated_events"][0].update(signal=True),
            "actor half confirmed": lambda d, r: r["actor_attribution"].update(rule="external_deletion_v1"),
            "areas unsorted": lambda d, r: r.update(relevant_areas=["tags", "other"]),
            "descendant ops unsorted": lambda d, r: r.update(descendant_operations={"b": 1, "a": 1},
                                                             descendant_events=2),
            "descendant count": lambda d, r: r.update(descendant_events=5),
            "op numbering": lambda d, r: r["operations"][0].update(op_id="op-7"),
            "op order": lambda d, r: r["operations"].reverse(),
            "duplicate event": lambda d, r: r["operations"][0].update(attached_event_ids=[
                r["automated_events"][0]["event_id"]]),
            "ambiguous without reason": lambda d, r: r.update(verdict="ambiguous", reason=None,
                                                              decisive_operation=None),
            "not investigated reason": lambda d, r: r.update(verdict="not_investigated", reason="partial_capability",
                                                             decisive_operation=None),
            "precondition with window": lambda d, r: r.update(verdict="not_investigated", reason="no_resource_id",
                                                              decisive_operation=None),
            "investigated without window": lambda d, r: r.update(window=None),
            "latest with anchor": lambda d, r: r.update(verdict="latest_capable_operation"),
            "decisive missing": lambda d, r: r.update(decisive_operation="op-9"),
            "decisive not capable": lambda d, r: r.update(decisive_operation="op-1"),
            "link reason": lambda d, r: r.update(property_link_reason=None),
            "deletion rule on update": lambda d, r: r.update(deletion_rule={
                "status": "unknown", "reason": "update_not_attributable", "rule": None, "claim": None,
                "caller": None, "anchor": None, "decisive_event_ids": [], "candidate_event_ids": [],
                "related_event_ids": [], "after_detection_event_ids": []}),
            "addresses unsorted": lambda d, r: d["resources"].reverse(),
            "failed without failure": lambda d, r: d.update(outcome="failed"),
            "outcome": lambda d, r: d.update(outcome="incomplete"),
            "input failure with resources": lambda d, r: d.update(outcome="failed", failure={
                "stage": "input", "reason": "report_invalid"}),
            "binding failure": lambda d, r: d.update(outcome="failed", failure={"stage": "binding",
                                                                                 "reason": "evidence_mismatch"}),
            "evidence failure": lambda d, r: d.update(outcome="failed", failure={"stage": "evidence",
                                                                                  "reason": "evidence_failed"}),
            "stage reason": lambda d, r: d.update(outcome="failed", failure={"stage": "input",
                                                                              "reason": "evidence_failed"}),
            "mismatch not failed": lambda d, r: r.update(verdict="not_investigated", reason="evidence_mismatch",
                                                         window=None, operations=[], automated_events=[],
                                                         descendant_events=0, descendant_operations={},
                                                         decisive_operation=None, property_link="none",
                                                         property_link_reason=None),
            "unbound": lambda d, r: d["binding"].update(drift_report_sha256=None),
            "completeness unbound": lambda d, r: d["binding"].update(evidence_sha256=None),
            "anchor duplicate": lambda d, r: d["anchor_candidates"]["rejected"].append(
                {"candidate": d["anchor_candidates"]["accepted"][0]["candidate"], "reason": "wrong_event"}),
            "anchor examined": lambda d, r: d["anchor_candidates"].update(examined=3),
            "window anchor": lambda d, r: r["window"].update(anchor=None),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                self.rejects(mutate)

    def test_anchor_candidate_ordering(self):
        doc = AnchorTests.select(self, self.anchors()).doc()
        doc["accepted"].append(dict(doc["accepted"][0], candidate="a-first"))
        doc["examined"] = 2
        with self.assertRaises(ValidationError):
            inv.AnchorCandidates.model_validate(doc)
        rejected = {"examined": 2, "accepted": [], "rejected": [{"candidate": "b", "reason": "wrong_event"},
                                                                {"candidate": "a", "reason": "wrong_event"}]}
        with self.assertRaises(ValidationError):
            inv.AnchorCandidates.model_validate(rejected)

    def test_api_errors_and_direct_correlation_paths(self):
        paths = self.plan(nsg_drift())
        with self.assertRaises(ValueError):
            inv.investigate(*paths, report_bytes(paths), source=FakeSource(), clock=FakeClock(),
                            sleep=lambda s: None, lookback_days=90)
        with self.assertRaises(ValueError):
            inv.investigate(*paths, report_bytes(paths), source=FakeSource(), clock=FakeClock(),
                            sleep=lambda s: None, anchors_dir=self.tmp)
        # evidence of the same run id and plan timestamp but other drifted resources
        other = self.plan(nsg_and_rg())
        evidence = al.collect_evidence(*other, source=FakeSource(), queried_at=NOT_BEFORE)
        failure, resources = inv.correlate(report_of(paths), evidence, inv.AnchorSelection(), 30)
        self.assertEqual((failure["reason"], resources[0]["reason"]), ("evidence_mismatch", "evidence_mismatch"))
        # detection time unknown in the report, evidence present
        unknown = self.plan(nsg_drift(), started=DELETE)
        evidence = al.collect_evidence(*unknown, source=FakeSource(), queried_at=NOT_BEFORE)
        self.assertEqual(inv.correlate(report_of(unknown), evidence, inv.AnchorSelection(), 30)[1][0]["reason"],
                         "detection_time_unknown")

    def test_oversized_or_unreadable_inputs(self):
        anchors = self.dir("anchors")
        self.anchor(anchors, "run-400-1")
        with mock.patch.object(inv, "MAX_INPUT_BYTES", 10):
            selection = inv.select_anchor_runs(anchors, report_of(self.plan(nsg_drift())), REPO)
        self.assertEqual(selection.rejected, [("run-400-1", "metadata_invalid")])
        self.assertIsNone(inv._read(os.path.join(self.tmp, "missing")))
        self.assertIsNone(inv._load_report_json(b"[1, 2]"))

    def test_verify_paths(self):
        result = self.inv_run(nsg_drift("delete"), self.log.write(at_time(8)) + self.log.delete(at_time(9)),
                              anchors=None)
        doc = result.document.model_dump(mode="json")
        evidence = json.loads(result.evidence_bytes)

        def problems(mutate_evidence):
            changed = copy.deepcopy(evidence)
            mutate_evidence(changed["events"])
            data = (json.dumps(changed, indent=2, sort_keys=True) + "\n").encode()
            bound = copy.deepcopy(doc)
            bound["binding"]["evidence_sha256"] = __import__("hashlib").sha256(data).hexdigest()
            return inv.verify_against_evidence(inv.DriftInvestigation.model_validate(bound), data)

        self.assertTrue(problems(lambda e: e[3].update(caller=OTHER_CALLER)))  # decisive delete caller
        self.assertTrue(problems(lambda e: e[0].update(category="Policy")))
        self.assertTrue(problems(lambda e: e[0].update(correlation_id="other-corr")))
        self.assertTrue(problems(lambda e: e[1].update(status="Failed")))
        self.assertTrue(problems(lambda e: e[1].update(operation_name="Microsoft.Network/networkSecurityGroups/other")))
        bound = copy.deepcopy(doc)
        bound["binding"]["run_id"] = "github-999-1"
        self.assertTrue(inv.verify_against_evidence(inv.DriftInvestigation.model_validate(bound),
                                                    result.evidence_bytes))
        self.assertEqual(inv.verify_against_evidence(result.document, b"not json"),
                         ["evidence_sha256 does not match the evidence"])
        # no evidence bound, but correlated resources claimed
        none_doc = self.inv_run(paths=self.plan(nsg_drift(), started=DELETE), source=NoCallSource()).document
        self.assertEqual(inv.verify_against_evidence(none_doc, None), [])
        # observation timing and attached/automated checks
        update = self.inv_run(rows=self.log.tags(at_time(8)) + self.log.policy(at_time(8, 0, 1), corr="auto"))
        update_doc = update.document.model_dump(mode="json")
        changed = copy.deepcopy(update_doc)
        changed["binding"]["observation"]["started_at"] = "2026-10-02T07:00:00.000000Z"
        self.assertTrue(inv.verify_against_evidence(inv.DriftInvestigation.model_validate(changed),
                                                    update.evidence_bytes))
        changed = copy.deepcopy(update_doc)
        changed["resources"][0]["automated_events"][0]["category"] = "Autoscale"
        self.assertTrue(inv.verify_against_evidence(inv.DriftInvestigation.model_validate(changed),
                                                    update.evidence_bytes))

    def test_anchor_b_with_every_delete_before_the_anchor(self):
        # a delete before the anchor run saw the resource in sync, then nothing: no deletion event after it
        rows = self.log.delete(at_time(5, 0, day=dt.datetime(2026, 10, 1, tzinfo=UTC)))
        arm = al.parse_resource_id(NSG_ID)
        paths = self.plan(nsg_drift("delete"))
        evidence = al.collect_evidence(*paths, source=FakeSource({RG: [page(*rows)]}), queried_at=NOT_BEFORE)
        prior = at.PriorAnchor("github-400-1", dt.datetime(2026, 10, 2, 6, tzinfo=UTC),
                               dt.datetime(2026, 10, 2, 6, 1, tzinfo=UTC))
        decision = at.decide("delete", arm, evidence.events, dt.datetime(2026, 10, 3, 10, tzinfo=UTC), T_FINISHED,
                             prior)
        self.assertEqual(decision["reason"], "no_deletion_event")

    def test_attribution_verifier_accepts_a_prior_detection_anchor(self):
        from test_attribution import Scenario  # noqa: F401  (the 7.2 harness is not needed here)
        paths = self.plan(nsg_drift("delete"))
        rows = self.log.write(at_time(8)) + self.log.delete(at_time(9))
        evidence = al.collect_evidence(*paths, source=FakeSource({RG: [page(*rows)]}), queried_at=NOT_BEFORE)
        data = al.render_evidence(evidence).encode()
        document = at.attribute(report_bytes(paths), data)
        doc = document.model_dump(mode="json")
        attribution = doc["resources"][0]["attribution"]
        attribution["candidate_event_ids"] = sorted(attribution["candidate_event_ids"]
                                                    + attribution["anchor"]["event_ids"])
        for time, ok in (("2026-10-02T06:01:00.000000Z", True), ("2026-10-02T09:30:00.000000Z", False)):
            attribution["anchor"] = {"kind": "prior_detection_run", "event_ids": [], "run_id": "github-400-1",
                                     "time": time}
            problems = at.verify_against_evidence(at.DriftAttribution.model_validate(doc), data)
            self.assertEqual(problems == [], ok, problems)


class CliErrorTests(CliTests):
    test_complete = test_anchors_need_a_repository = test_incomplete_and_failed = None
    test_recheck_failure_writes_nothing = test_pipeline_principal_from_environment = None

    def test_report_unreadable_or_oversized(self):
        paths = self.plan(nsg_drift())
        args = self.args(paths)
        args[args.index("--report") + 1] = os.path.join(self.tmp, "missing.json")
        code, _, err = self.main(args, NoCallSource())
        self.assertEqual((code, "[report_invalid]" in err), (1, True))
        with mock.patch.object(inv, "MAX_INPUT_BYTES", 10):
            code, _, err = self.main(self.args(paths), NoCallSource())
        self.assertEqual((code, "[report_invalid]" in err), (1, True))

    def test_stdout_and_write_error(self):
        paths = self.plan(nsg_drift())
        args = self.args(paths)
        stdout_args = args[:args.index("--output")]
        code, out, _ = self.main(stdout_args, FakeSource({RG: [page(*self.log.tags(at_time(8)))]}))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["investigation_version"], "1")
        args[args.index("--output") + 1] = os.path.join(self.tmp, "no-such-dir", "out.json")
        code, _, err = self.main(args, FakeSource({RG: [page(*self.log.tags(at_time(8)))]}))
        self.assertEqual(code, 73)
        self.assertIn("cannot write", err)

    def test_real_clock_and_sleep(self):
        self.assertIsNotNone(cli._now().utcoffset())
        cli._sleep(0)

    def test_internal_error_message(self):
        paths = self.plan(nsg_drift())
        with mock.patch.object(inv, "investigate", side_effect=RuntimeError("boom")):
            code, _, err = self.main(self.args(paths))
        self.assertEqual(code, 70)
        self.assertIn("No investigation was written", err)


# ---------------------------------------------------------------------------
# Safeguard mutants: each must change at least one scenario's result
# ---------------------------------------------------------------------------

MUTANTS = {
    "verdict-upgrade-ambiguous-to-sole": ('        if len(capable) > 1:\n            return "ambiguous", "multiple_capable_operations", None',
                                          '        if False:\n            pass'),
    "unclassified-ignored": ('        if any(c["role"] == "unclassified" for c in candidates):\n            return "ambiguous", "unclassified_operation", None',
                             '        if False:\n            pass'),
    "during-observation-ignored": ('    if any(c["timing"] == "during_observation" for c in candidates):',
                                   '    if False:'),
    "unresolved-ignored": ('    if any(c["outcome"] == "unresolved" for c in candidates):', '    if False:'),
    "skew-ignored": ('    if end < started - SKEW:', '    if end < started:'),
    "anchor-trust-branch-removed": ('    if metadata.head_branch != ANCHOR_BRANCH:', '    if False:'),
    "anchor-same-run-removed": ('    if metadata.id == _current_workflow_run_id(run.get("run_id")):', '    if False:'),
    "anchor-plan-order-removed": ('    if al.parse_timestamp(plan_ts) is None or current_plan is None or not al.parse_timestamp(plan_ts) < current_plan:',
                                  '    if al.parse_timestamp(plan_ts) is None:'),
    "anchor-limit-removed": ('    for name in candidates[MAX_ANCHOR_CANDIDATES:]:', '    for name in []:'),
    "update-drift-confirmed": ('            link, link_reason = "inferred_not_provable", "no_property_values_in_activity_log"',
                               '            link, link_reason = ("confirmed", None) if verdict in DECISIVE_VERDICTS else ("inferred_not_provable", "no_property_values_in_activity_log")'),
    "unreadable-ignored": ('        unreadable = at.scope_key(target.resource_id) in unreadable_scopes',
                           '        unreadable = False'),
    "partial-capability-ignored": ('    if not needed <= set(decisive["capable_areas"]):', '    if False:'),
    "policy-counted-as-capable": ('        elif event.category == at.LIFECYCLE_CATEGORY:', '        elif True:'),
    "automated-signal-ignored": ('    if any(a["signal"] for a in automated):', '    if False:'),
    "settling-from-started": ('    not_before = finished + SETTLE_MARGIN if queryable else None',
                              '    not_before = started + SETTLE_MARGIN if queryable else None'),
    "option-a-removed": ('                    if verdict not in DECISIVE_VERDICTS:\n                        link_reason = "verdict_not_decisive"\n                    elif',
                         '                    if False:\n                        pass\n                    elif'),
    "window-membership-start": ('                "in_window": end >= window_start,', '                "in_window": start >= window_start,'),
    "latest-overlap-ignored": ('        if overlapping:', '        if False:'),
}


class SafeguardMutationTests(_Base):
    """Each mutant removes one safeguard from an in-process copy of investigation.py (the
    repository file is never changed) and must change the result of a scenario."""

    def scenarios(self, module) -> dict:
        self.log = log = Log()  # identical event ids for every module
        anchors = self.anchors()

        def run(entries, rows, *, anchored=True, clock=None, paths=None, anchor_dir=None):
            paths = paths or self.plan(entries)
            clock = clock or FakeClock()
            try:
                result = module.investigate(paths[0], paths[1], report_bytes(paths),
                                            source=FakeSource({RG: [page(*rows)]}), clock=clock, sleep=clock.sleep,
                                            anchors_dir=(anchor_dir or anchors) if anchored else None,
                                            repository=REPO if anchored else None)
                return (module.render_investigation(result.document), tuple(clock.slept))
            except Exception as exc:  # a mutant may break an invariant
                return f"{type(exc).__name__}"

        day3 = dt.datetime(2026, 10, 3, tzinfo=UTC)
        action = lambda t: log.rows(t, op=f"{NSG_OPS}/someAction/action", statuses=("Succeeded",))
        branch_dir = self.dir("anchors")
        self.anchor(branch_dir, "run-400-1", head_branch="feature")
        same_dir = self.dir("anchors")
        self.anchor(same_dir, "run-400-1", run=500)
        plan_dir = self.dir("anchors")
        self.anchor(plan_dir, "run-400-1", plan_ts="2026-10-03T10:03:00Z")
        many = self.dir("anchors")
        for n in range(51):
            self.anchor(many, f"run-{n:03d}", run=1000 + n, started=f"2026-10-02T06:{n:02d}:00Z",
                        finished=f"2026-10-02T06:{n:02d}:30Z", plan_ts=f"2026-10-02T06:{n:02d}:10Z")
        long_obs = self.plan(nsg_drift(), finished="2026-10-03T10:30:00Z")
        return {
            "two": run(nsg_drift(), log.tags(at_time(8)) + log.tags(at_time(9))),
            "unclassified": run(nsg_drift(), log.tags(at_time(8)) + action(at_time(7))),
            "during": run(nsg_drift(), log.tags(at_time(8)) + log.tags(at_time(10, 0, 30, day=day3))),
            "unresolved": run(nsg_drift(), log.tags(at_time(7), statuses=("Started",)) + log.tags(at_time(8))),
            "skew": run(nsg_drift(), log.rows(at_time(9, 59, 30, day=day3), op=TAGS_OP, statuses=("Succeeded",))),
            "branch": run(nsg_drift(), log.tags(at_time(8)), anchor_dir=branch_dir),
            "same-run": run(nsg_drift(), log.tags(at_time(8)), anchor_dir=same_dir),
            "plan-order": run(nsg_drift(), log.tags(at_time(8)), anchor_dir=plan_dir),
            "limit": run(nsg_drift(), log.tags(at_time(8)), anchor_dir=many),
            "update": run(nsg_drift(), log.tags(at_time(8))),
            "unreadable": run(nsg_drift(), log.tags(at_time(8)) + [ev(9999, ts="2026-10-02T07:30:00Z",
                                                                    operationName={"value": "bad name"})]),
            "partial": run(nsg_drift("both"), log.tags(at_time(8))),
            "policy-tags": run(nsg_drift(), log.rows(at_time(8), op=TAGS_OP, category="Policy", statuses=("Succeeded",))),
            "policy-signal": run(nsg_drift(), log.tags(at_time(8)) + log.policy(at_time(7))),
            "long-observation": run(None, log.tags(at_time(8)), paths=long_obs),
            "option-a": run(nsg_drift("delete"), log.write(at_time(8)) + log.delete(at_time(9)) + action(at_time(9, 30)),
                            anchored=False),
            "straddling": run(nsg_and_rg(), log.tags(at_time(5, 58, 50), step=20) + log.tags(at_time(8))),
            "overlap": run(nsg_drift(), log.tags(at_time(8), step=10) + log.tags(at_time(8, 0, 10)), anchored=False),
        }

    @staticmethod
    def load(name: str, source: str):
        module_name = f"drift_engine._investigation_mutant_{name.replace('-', '_')}"
        module = types.ModuleType(module_name)
        module.__file__ = f"<mutant {name}>"
        sys.modules[module_name] = module
        try:
            exec(compile(source, module.__file__, "exec"), module.__dict__)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
        return module

    def test_every_mutant_is_caught(self):
        with open(inv.__file__, encoding="utf-8") as fh:
            original = fh.read()
        baseline = self.scenarios(self.load("baseline", original))
        self.assertEqual(baseline, self.scenarios(inv))  # the in-process copy behaves like the module
        survivors = []
        for name, (old, new) in MUTANTS.items():
            with self.subTest(name):
                self.assertEqual(original.count(old), 1, f"mutant {name} no longer matches the source")
                mutated = self.scenarios(self.load(name, original.replace(old, new)))
                if mutated == baseline:
                    survivors.append(name)
        self.assertEqual(survivors, [])


if __name__ == "__main__":
    unittest.main()
