"""Tests for deterministic Activity Log attribution (Task 7.2).

Run from the repository root:
    pytest tests/test_attribution.py

Requires the package (pip install -e ".[dev]"); skipped otherwise. No Azure, network
or credentials: every evidence file is produced by the Task 7.1 collector
(drift_engine.activity_logs) over a fake source, so it always satisfies the 7.1
contract, and every drift report by drift_engine's own classifier. IDs, callers and
addresses are synthetic.

Timeline used throughout (UTC): detection run 2026-10-03 10:00:00-10:05:00, so
T_start = 09:59:00 and T_end = 10:06:00 (60-second skew, rules version 2); evidence
queried at 12:00:00 (settled from 10:15:00 = finished + 10 min); lifecycle events on
2026-10-02.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import datetime as dt
import hashlib
import io
import json
import logging
import os
import random
import shutil
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

try:
    from pydantic import ValidationError

    from drift_engine import activity_logs as al
    from drift_engine import attribution as at
    from drift_engine import cli
    from drift_engine.classifier import evaluate
    from drift_engine.formatters import render_json
    from drift_engine.models import DriftReport
except ImportError:  # pydantic not installed
    at = None

from test_activity_logs import (  # noqa: E402  (shared 7.1 helpers; no test classes imported)
    ASSOC_ADDR, CALLER, DELETE, NSG_ADDR, NSG_ID, RG, RG_ADDR, RG_ID, RULE_ID, SUB, SUBNET_ADDR, SUBNET_ID,
    FakeSource, ev, nsg, page, raw_entry,
)

UTC = dt.timezone.utc
RUN_STARTED, RUN_FINISHED = "2026-10-03T10:00:00Z", "2026-10-03T10:05:00Z"
T_START = dt.datetime(2026, 10, 3, 9, 59, tzinfo=UTC)
T_END = dt.datetime(2026, 10, 3, 10, 6, tzinfo=UTC)
QUERIED = dt.datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
DAY = dt.datetime(2026, 10, 2, tzinfo=UTC)
GUID_CALLER = "11111111-2222-4333-8444-555555555555"
OTHER = "mallory@example.com"
SECOND_RG = "second-rg"
SECOND_RG_ID = f"/subscriptions/{SUB}/resourceGroups/{SECOND_RG}"

OPS = {
    NSG_ID: "Microsoft.Network/networkSecurityGroups",
    RG_ID: "Microsoft.Resources/subscriptions/resourceGroups",
    SECOND_RG_ID: "Microsoft.Resources/subscriptions/resourceGroups",
    SUBNET_ID: "Microsoft.Network/virtualNetworks/subnets",
    RULE_ID: "Microsoft.Network/networkSecurityGroups/securityRules",
}


def at_time(hour: int, minute: int = 0, second: int = 0, day: dt.datetime = DAY) -> dt.datetime:
    return day + dt.timedelta(hours=hour, minutes=minute, seconds=second)


def iso(moment: dt.datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class Log:
    """Builds REST-shaped Activity Log rows with unique ids, grouped as Azure logs them."""

    def __init__(self) -> None:
        self.n = 0
        self.groups = 0

    def group(self, kind: str, start: dt.datetime, *, statuses=("Started", "Accepted", "Succeeded"),
              caller: str | None = CALLER, callers=None, corr="auto", rid: str = NSG_ID, op: str | None = None,
              category: str = "Administrative", step: int = 2, sub_status: str | None = None) -> list[dict]:
        self.groups += 1
        correlation = f"corr-{self.groups:04d}" if corr == "auto" else corr
        rows = []
        for i, status in enumerate(statuses):
            self.n += 1
            rows.append(ev(
                self.n, ts=iso(start + dt.timedelta(seconds=step * i)), resourceId=rid,
                operationName={"value": op or f"{OPS[rid]}/{kind}"},
                status={"value": status} if status else DELETE,
                subStatus={"value": sub_status} if sub_status else DELETE,
                correlationId=correlation if correlation is not None else DELETE,
                caller=callers[i] if callers is not None else caller,
                category={"value": category},
            ))
        return rows

    def event(self, start: dt.datetime, **overrides) -> list[dict]:
        self.n += 1
        return [ev(self.n, ts=iso(start), **overrides)]


def ids(rows: list[dict]) -> list[str]:
    return sorted(r["eventDataId"] for r in rows)


def deleted(address: str = NSG_ADDR, rid=NSG_ID, rtype: str = "azurerm_network_security_group"):
    """A drift entry and planned change for an externally deleted resource."""
    return ([raw_entry(address, ["delete"], nsg(rid), None, rtype=rtype)],
            [raw_entry(address, ["create"], None, nsg(DELETE), {"id": True}, rtype=rtype)])


def updated(address: str = NSG_ADDR, rid=NSG_ID, drift_actions=("update",)):
    changed = nsg(rid, tags={"env": "changed"})
    return ([raw_entry(address, list(drift_actions), nsg(rid), changed)],
            [raw_entry(address, ["update"], changed, nsg(rid))])


MANIFEST = {"outcome": "succeeded", "terraform_version": "1.14.7", "run_id": "attr-run-1", "environment": "dev",
            "backend_key": "dev.tfstate", "started_at": RUN_STARTED, "finished_at": RUN_FINISHED}


class Scenario:
    """Plan, manifest, drift report and Activity Log evidence of one detection run."""

    def __init__(self, directory: str, drift, changes, script: dict, *, queried_at=QUERIED, manifest=None,
                 limits=None) -> None:
        os.makedirs(directory, exist_ok=True)
        pending = any(e["change"]["actions"] not in (["no-op"], ["read"]) for e in changes)
        plan = {"format_version": "1.2", "terraform_version": "1.14.7", "errored": False, "complete": True,
                "applyable": True, "timestamp": "2026-10-03T10:00:01Z",
                "resource_drift": list(drift), "resource_changes": list(changes)}
        doc = dict(MANIFEST, plan_exit_code=2 if pending else 0)
        for key, value in (manifest or {}).items():
            if value is DELETE:
                doc.pop(key, None)
            else:
                doc[key] = value
        self.plan = os.path.join(directory, "plan.json")
        self.manifest = os.path.join(directory, "detection_run.json")
        for path, content in ((self.plan, plan), (self.manifest, doc)):
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(content, fh)
        evaluation = evaluate(self.plan, self.manifest)
        report = DriftReport.model_validate(evaluation.report).model_dump(mode="json")
        self.report_bytes = render_json(report).encode()
        evidence = al.collect_evidence(self.plan, self.manifest, source=FakeSource(script), queried_at=queried_at,
                                       **({"limits": limits} if limits else {}))
        self.evidence_bytes = al.render_evidence(evidence).encode()
        self.report_path = os.path.join(directory, "drift_classification.json")
        self.evidence_path = os.path.join(directory, "activity_log_evidence.json")
        for path, data in ((self.report_path, self.report_bytes), (self.evidence_path, self.evidence_bytes)):
            with open(path, "wb") as fh:
                fh.write(data)

    def attribute(self):
        return at.attribute(self.report_bytes, self.evidence_bytes)


@unittest.skipIf(at is None, "drift_engine is not installed (pip install -e '.[dev]')")
class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="attribution-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.log = Log()

    def scenario(self, drift_changes=None, rows=(), *, script=None, **kwargs) -> Scenario:
        drift, changes = drift_changes or deleted()
        directory = os.path.join(self.tmp, f"s{len(os.listdir(self.tmp))}")
        return Scenario(directory, drift, changes, script if script is not None else {RG: [page(*rows)]}, **kwargs)

    def resource(self, document, address: str = NSG_ADDR):
        return next(r for r in document.resources if r.address == address)

    def scenario_result(self, scenario: Scenario, address: str = NSG_ADDR):
        document = scenario.attribute()
        self.assertEqual(at.verify_against_evidence(document, scenario.evidence_bytes), [])
        return self.resource(document, address).attribution

    def status(self, rows=(), **kwargs):
        attribution = self.check(rows, **kwargs)
        return attribution.status, attribution.reason

    def check(self, rows=(), address: str = NSG_ADDR, drift_changes=None, **kwargs):
        return self.scenario_result(self.scenario(drift_changes, rows, **kwargs), address)

    def W(self, hour, minute=0, second=0, **kwargs):  # noqa: N802 - write group
        return self.log.group("write", at_time(hour, minute, second), **kwargs)

    def D(self, hour, minute=0, second=0, **kwargs):  # noqa: N802 - delete group
        return self.log.group("delete", at_time(hour, minute, second), **kwargs)


# ---------------------------------------------------------------------------
# Existence-anchor sequences (rule external_deletion_v1)
# ---------------------------------------------------------------------------

class AnchorSequenceTests(_Base):
    def test_write_then_delete_is_confirmed(self):
        write, delete = self.W(8), self.D(9)
        attribution = self.check(write + delete)
        self.assertEqual(attribution.model_dump(), {
            "status": "confirmed", "reason": None, "rule": "external_deletion_v1",
            "claim": "recorded_successful_delete", "caller": CALLER,
            "anchor": {"kind": "write_event", "event_ids": ids(write), "run_id": None,
                       "time": "2026-10-02T08:00:04.000000Z"},
            "decisive_event_ids": ids(delete), "candidate_event_ids": [], "related_event_ids": [],
            "after_detection_event_ids": [],
        })

    def test_write_delete_delete_is_unknown_for_both_deletes(self):
        for second_caller in (CALLER, OTHER):
            with self.subTest(second_caller):
                rows = self.W(8) + self.D(9) + self.D(9, 30, caller=second_caller)
                self.assertEqual(self.status(rows), ("unknown", "multiple_successful_deletes"))

    def test_final_delete_uses_the_latest_write_as_anchor(self):
        first_write, first_delete = self.W(6), self.D(7, caller=OTHER)
        second_write, final_delete = self.W(8), self.D(9)
        attribution = self.check(first_write + first_delete + second_write + final_delete)
        self.assertEqual((attribution.status, attribution.caller), ("confirmed", CALLER))
        self.assertEqual(attribution.anchor.event_ids, ids(second_write))
        self.assertEqual(attribution.decisive_event_ids, ids(final_delete))
        self.assertEqual(attribution.candidate_event_ids, sorted(ids(first_write) + ids(first_delete)))

    def test_delete_without_anchor_is_unknown(self):
        for rows in (self.D(9), self.D(8) + self.D(9), self.D(9, caller=GUID_CALLER)):
            with self.subTest(len(rows)):
                self.assertEqual(self.status(rows), ("unknown", "no_existence_anchor"))

    def test_write_after_the_delete_is_unknown(self):
        self.assertEqual(self.status(self.W(8) + self.D(9) + self.W(9, 30)), ("unknown", "latest_operation_is_write"))

    def test_unresolved_delete_is_unknown(self):
        for statuses in (("Started",), ("Started", "Accepted"), ("Accepted", None)):
            with self.subTest(statuses):
                rows = self.W(8) + self.D(9, statuses=statuses)
                self.assertEqual(self.status(rows), ("unknown", "unresolved_operation"))

    def test_unresolved_operation_between_anchor_and_delete(self):
        for kind in ("write", "delete"):
            with self.subTest(kind):
                pending = self.log.group(kind, at_time(8, 30), statuses=("Started", "Accepted"))
                rows = self.W(8) + pending + self.D(9)
                self.assertEqual(self.status(rows), ("unknown", "unresolved_operation"))

    def test_unresolved_operation_before_the_anchor_does_not_matter(self):
        rows = self.D(7, statuses=("Started",)) + self.W(8) + self.D(9)
        self.assertEqual(self.status(rows), ("confirmed", None))

    def test_failed_delete_between_anchor_and_delete_is_ignored(self):
        failed = self.D(8, 30, statuses=("Started", "Failed"), caller=OTHER)
        canceled = self.D(8, 40, statuses=("Started", "Canceled"), caller=OTHER)
        attribution = self.check(self.W(8) + failed + canceled + self.D(9))
        self.assertEqual((attribution.status, attribution.caller), ("confirmed", CALLER))
        self.assertEqual(attribution.related_event_ids, sorted(ids(failed) + ids(canceled)))

    def test_mixed_outcome_group_counts_as_successful(self):
        mixed = self.D(9, statuses=("Started", "Failed", "Started", "Succeeded", "Succeeded"))
        attribution = self.check(self.W(8) + mixed)
        self.assertEqual((attribution.status, attribution.decisive_event_ids), ("confirmed", ids(mixed)))

    def test_mixed_outcome_group_followed_by_a_repeat_delete_is_unknown(self):
        # the observed disk case: the real removal had an earlier failed attempt, then a
        # second caller's delete (204) succeeded; treating the first group as failed would
        # wrongly confirm the second caller
        mixed = self.D(9, statuses=("Started", "Failed", "Started", "Succeeded", "Succeeded"),
                       callers=[CALLER, CALLER, GUID_CALLER, GUID_CALLER, CALLER])
        repeat = self.D(9, 1, statuses=("Started", "Succeeded"), caller=OTHER, sub_status="NoContent")
        self.assertEqual(self.status(self.W(8) + mixed + repeat), ("unknown", "multiple_successful_deletes"))

    def test_failed_or_unresolved_write_is_not_an_anchor(self):
        for statuses in (("Started", "Failed"), ("Started", "Accepted")):
            with self.subTest(statuses):
                rows = self.W(8, statuses=statuses) + self.D(9)
                self.assertEqual(self.status(rows), ("unknown", "no_existence_anchor"))

    def test_write_before_the_window_is_not_an_anchor(self):
        old_write = self.log.group("write", dt.datetime(2026, 9, 2, 8, tzinfo=UTC))
        self.assertEqual(self.status(old_write + self.D(9)), ("unknown", "no_existence_anchor"))

    def test_old_write_inside_the_window_is_a_valid_anchor_only(self):
        old_write = self.log.group("write", dt.datetime(2026, 9, 4, 8, tzinfo=UTC))
        scenario = self.scenario(None, old_write + self.D(9))
        document = scenario.attribute()
        resource = self.resource(document)
        self.assertEqual((resource.attribution.status, resource.attribution.anchor.time),
                         ("confirmed", "2026-09-04T08:00:04.000000Z"))
        self.assertEqual(at.render_claim(resource),
                         f"Azure recorded caller {CALLER} performing the successful delete of this exact "
                         "resource under the correlation rules.")

    def test_no_content_delete_is_a_successful_delete(self):
        delete = self.D(9, statuses=("Started", "Succeeded"), sub_status="NoContent")
        self.assertEqual(self.status(self.W(8) + delete), ("confirmed", None))

    def test_succeeded_only_delete_group_is_a_candidate(self):
        attribution = self.check(self.W(8) + self.D(9, statuses=("Succeeded",)))
        self.assertEqual(attribution.status, "confirmed")

    def test_deletion_events_missing(self):
        self.assertEqual(self.status([]), ("unknown", "no_deletion_event"))
        self.assertEqual(self.status(self.W(8)), ("unknown", "latest_operation_is_write"))


# ---------------------------------------------------------------------------
# Grouping and matching
# ---------------------------------------------------------------------------

class GroupingAndMatchingTests(_Base):
    def test_operation_name_casing(self):
        rg = deleted(RG_ADDR, RG_ID, "azurerm_resource_group")
        rows = (self.log.group("write", at_time(8), rid=RG_ID, op="Microsoft.Resources/subscriptions/resourcegroups/write")
                + self.log.group("delete", at_time(9), rid=RG_ID, op="MICROSOFT.RESOURCES/subscriptions/resourceGroups/DELETE"))
        self.assertEqual((self.check(rows, RG_ADDR, rg).status), "confirmed")

    def test_resource_id_casing(self):
        upper = NSG_ID.upper().replace("/SUBSCRIPTIONS/", "/subscriptions/")
        rows = self.W(8, rid=NSG_ID) + self.log.group("delete", at_time(9), rid=upper, op=f"{OPS[NSG_ID]}/delete")
        self.assertEqual(self.status(rows), ("confirmed", None))

    def test_one_correlation_across_a_cascade_is_split_per_resource(self):
        both = (deleted(RG_ADDR, RG_ID, "azurerm_resource_group")[0] + deleted()[0],
                deleted(RG_ADDR, RG_ID, "azurerm_resource_group")[1] + deleted()[1])
        rg_write = self.log.group("write", at_time(7), rid=RG_ID)
        nsg_write = self.W(8)
        rg_delete = self.log.group("delete", at_time(9), rid=RG_ID, corr="cascade-1")
        nsg_delete = self.log.group("delete", at_time(9, 0, 1), rid=NSG_ID, statuses=("Succeeded",), corr="cascade-1")
        rule_delete = self.log.group("delete", at_time(9, 0, 1), rid=RULE_ID, statuses=("Succeeded",), corr="cascade-1")
        scenario = self.scenario(both, rg_write + nsg_write + rg_delete + nsg_delete + rule_delete)
        rg = self.scenario_result(scenario, RG_ADDR)
        nsg_result = self.scenario_result(scenario, NSG_ADDR)
        self.assertEqual((rg.status, rg.decisive_event_ids), ("confirmed", ids(rg_delete)))
        self.assertEqual((nsg_result.status, nsg_result.decisive_event_ids), ("confirmed", ids(nsg_delete)))
        self.assertEqual(nsg_result.related_event_ids, ids(rule_delete))

    def test_differing_operation_ids_stay_one_group(self):
        delete = self.D(9)
        self.assertEqual(len({r["operationId"] for r in delete}), 3)
        self.assertEqual(self.check(self.W(8) + delete).decisive_event_ids, ids(delete))

    def test_events_without_correlation_id_are_groups_of_their_own(self):
        rows = self.W(8) + self.D(9, statuses=("Started", "Succeeded"), corr=None)
        self.assertEqual(self.status(rows), ("unknown", "unresolved_operation"))
        rows = self.W(8) + self.D(9, statuses=("Succeeded",), corr=None)
        self.assertEqual(self.status(rows), ("confirmed", None))

    def test_only_administrative_lifecycle_events_count(self):
        policy_write = self.W(8, category="Policy")
        self.assertEqual(self.status(policy_write + self.D(9)), ("unknown", "no_existence_anchor"))
        policy_delete = self.D(9, category="Policy")
        self.assertEqual(self.status(self.W(8) + policy_delete), ("unknown", "latest_operation_is_write"))

    def test_other_operations_on_the_resource_are_not_anchors(self):
        tags = self.log.group("write", at_time(8), op="Microsoft.Resources/tags/write")
        action = self.log.group("write", at_time(8, 30), op="Microsoft.Network/networkSecurityGroups/join/action")
        attribution = self.check(tags + action + self.D(9))
        self.assertEqual((attribution.status, attribution.reason), ("unknown", "no_existence_anchor"))
        self.assertEqual(attribution.related_event_ids, sorted(ids(tags) + ids(action)))

    def test_child_events_never_decide(self):
        child_delete = self.log.group("delete", at_time(9), rid=RULE_ID)
        attribution = self.check(self.W(8) + child_delete)
        self.assertEqual((attribution.status, attribution.reason), ("unknown", "latest_operation_is_write"))
        self.assertEqual(attribution.related_event_ids, ids(child_delete))

    def test_parent_operation_name_on_a_child_resource_never_decides(self):
        disguised = self.log.group("delete", at_time(9), rid=RULE_ID, op=f"{OPS[NSG_ID]}/delete")
        self.assertEqual(self.status(self.W(8) + disguised), ("unknown", "latest_operation_is_write"))

    def test_parent_delete_never_decides_for_a_child(self):
        both = (deleted(RG_ADDR, RG_ID, "azurerm_resource_group")[0] + deleted()[0],
                deleted(RG_ADDR, RG_ID, "azurerm_resource_group")[1] + deleted()[1])
        rows = (self.log.group("write", at_time(7), rid=RG_ID) + self.W(8)
                + self.log.group("delete", at_time(9), rid=RG_ID))
        scenario = self.scenario(both, rows)
        self.assertEqual(self.scenario_result(scenario, RG_ADDR).status, "confirmed")
        nsg_result = self.scenario_result(scenario, NSG_ADDR)
        self.assertEqual((nsg_result.status, nsg_result.reason), ("unknown", "latest_operation_is_write"))

    def test_shared_resource_id_decides_both_addresses(self):
        subnet = deleted(SUBNET_ADDR, SUBNET_ID, "azurerm_subnet")
        assoc = deleted(ASSOC_ADDR, SUBNET_ID, "azurerm_subnet_network_security_group_association")
        rows = self.log.group("write", at_time(8), rid=SUBNET_ID) + self.log.group("delete", at_time(9), rid=SUBNET_ID)
        scenario = self.scenario((subnet[0] + assoc[0], subnet[1] + assoc[1]), rows)
        first, second = self.scenario_result(scenario, SUBNET_ADDR), self.scenario_result(scenario, ASSOC_ADDR)
        self.assertEqual(first.model_dump(), second.model_dump())
        self.assertEqual(first.status, "confirmed")

    def test_association_removal_is_a_subnet_write(self):
        assoc = deleted(ASSOC_ADDR, SUBNET_ID, "azurerm_subnet_network_security_group_association")
        rows = self.log.group("write", at_time(8), rid=SUBNET_ID) + self.log.group("write", at_time(9), rid=SUBNET_ID)
        self.assertEqual(self.status(rows, address=ASSOC_ADDR, drift_changes=assoc),
                         ("unknown", "latest_operation_is_write"))

    def test_lifecycle_operation_names(self):
        cases = {
            RG_ID: "microsoft.resources/subscriptions/resourcegroups",
            NSG_ID: "microsoft.network/networksecuritygroups",
            SUBNET_ID: "microsoft.network/virtualnetworks/subnets",
            RULE_ID: "microsoft.network/networksecuritygroups/securityrules",
            f"{NSG_ID}/providers/Microsoft.Authorization/locks/l1": "microsoft.authorization/locks",
        }
        for rid, base in cases.items():
            with self.subTest(rid):
                self.assertEqual(at.lifecycle_operations(al.parse_resource_id(rid)), (f"{base}/write", f"{base}/delete"))


# ---------------------------------------------------------------------------
# Caller resolution
# ---------------------------------------------------------------------------

class CallerTests(_Base):
    def test_multiple_callers_in_the_candidate_group(self):
        for callers in ([GUID_CALLER, CALLER, CALLER], [CALLER, CALLER, "Alice@example.com"]):
            with self.subTest(callers):
                rows = self.W(8) + self.D(9, callers=callers)
                self.assertEqual(self.status(rows), ("unknown", "caller_inconsistent"))

    def test_missing_or_rejected_caller(self):
        for callers in ([CALLER, None, CALLER], [None, None, None], [CALLER, "bad\ncaller", CALLER],
                        [CALLER, "", CALLER]):
            with self.subTest(callers):
                rows = self.W(8) + self.D(9, callers=callers)
                self.assertEqual(self.status(rows), ("unknown", "caller_missing"))

    def test_guid_caller_is_kept_verbatim(self):
        attribution = self.check(self.W(8) + self.D(9, caller=GUID_CALLER))
        self.assertEqual((attribution.status, attribution.caller), ("confirmed", GUID_CALLER))

    def test_anchor_caller_does_not_matter(self):
        attribution = self.check(self.W(8, caller=OTHER) + self.D(9))
        self.assertEqual((attribution.status, attribution.caller), ("confirmed", CALLER))


# ---------------------------------------------------------------------------
# Ambiguity, concurrency, automation, detection window
# ---------------------------------------------------------------------------

class AmbiguityTests(_Base):
    def test_overlapping_or_touching_groups(self):
        write = lambda: self.W(8)  # [08:00:00, 08:00:04]
        for second, expected in ((3, ("unknown", "order_ambiguous")), (4, ("unknown", "order_ambiguous")),
                                 (5, ("confirmed", None))):
            with self.subTest(second):
                rows = write() + self.log.group("delete", at_time(8, 0, second), statuses=("Succeeded",))
                self.assertEqual(self.status(rows), expected)

    def test_concurrency_with_detection(self):
        day = dt.datetime(2026, 10, 3, tzinfo=UTC)
        for moment, expected in ((T_START - dt.timedelta(seconds=1), ("confirmed", None)),
                                 (T_START, ("unknown", "concurrent_with_detection")),
                                 (T_START + dt.timedelta(minutes=3), ("unknown", "concurrent_with_detection"))):
            with self.subTest(moment):
                rows = (self.log.group("write", at_time(8, day=day))
                        + self.log.group("delete", moment, statuses=("Succeeded",)))
                self.assertEqual(self.status(rows), expected)

    def test_automated_activity_overlap(self):
        delete = self.D(9)  # interval [09:00:00, 09:00:04]
        for offset, expected in ((dt.timedelta(minutes=5), ("unknown", "automated_activity_overlap")),
                                 (dt.timedelta(minutes=5, seconds=1), ("confirmed", None)),
                                 (-dt.timedelta(minutes=5), ("unknown", "automated_activity_overlap")),
                                 (-dt.timedelta(minutes=5, seconds=1), ("confirmed", None))):
            for category in ("Policy", "Autoscale"):
                with self.subTest(offset=offset, category=category):
                    edge = at_time(9, 0, 4) if offset > dt.timedelta(0) else at_time(9)
                    automated = self.log.event(edge + offset, resourceId=NSG_ID, category={"value": category},
                                               operationName={"value": "Microsoft.Authorization/policies/audit/action"})
                    attribution = self.check(self.W(8) + delete + automated)
                    self.assertEqual((attribution.status, attribution.reason), expected)
                    self.assertEqual(attribution.related_event_ids, ids(automated))

    def test_automated_activity_on_a_child_does_not_count(self):
        child = self.log.event(at_time(9, 0, 1), resourceId=RULE_ID, category={"value": "Policy"},
                               operationName={"value": "Microsoft.Authorization/policies/audit/action"})
        self.assertEqual(self.status(self.W(8) + self.D(9) + child), ("confirmed", None))

    def test_events_after_detection_are_listed_and_ignored(self):
        day = dt.datetime(2026, 10, 3, tzinfo=UTC)
        late = self.log.group("delete", T_END + dt.timedelta(seconds=1), caller=OTHER)
        attribution = self.check(self.W(8) + self.D(9) + late)
        self.assertEqual((attribution.status, attribution.after_detection_event_ids), ("confirmed", ids(late)))
        only_late = self.log.group("delete", at_time(10, 30, day=day))
        attribution = self.check(self.W(8) + only_late)
        self.assertEqual((attribution.reason, attribution.after_detection_event_ids),
                         ("latest_operation_is_write", ids(only_late)))

    def test_group_starting_at_the_end_of_detection_counts(self):
        at_end = self.log.group("write", T_END, statuses=("Started", "Succeeded"))
        self.assertEqual(self.status(self.W(8) + self.D(9) + at_end), ("unknown", "latest_operation_is_write"))


# ---------------------------------------------------------------------------
# Preconditions and document outcome
# ---------------------------------------------------------------------------

class PreconditionTests(_Base):
    def rows(self):
        return self.W(8) + self.D(9)

    def test_settled_boundary(self):
        settled = QUERIED.replace(hour=10, minute=15)  # finished 10:05:00 + M (10 min)
        self.assertEqual(self.status(self.rows(), queried_at=settled), ("confirmed", None))
        scenario = self.scenario(None, self.rows(), queried_at=settled - dt.timedelta(seconds=1))
        document = scenario.attribute()
        self.assertEqual((document.outcome, self.resource(document).attribution.reason),
                         ("incomplete", "evidence_not_settled"))
        self.assertEqual(self.resource(document).attribution.candidate_event_ids, [])

    def test_detection_time_unknown(self):
        for manifest in ({"started_at": DELETE}, {"finished_at": DELETE}, {"finished_at": "yesterday"},
                         {"started_at": RUN_FINISHED, "finished_at": RUN_STARTED}):
            with self.subTest(manifest):
                document = self.scenario(None, self.rows(), manifest=manifest).attribute()
                self.assertEqual((document.outcome, self.resource(document).attribution.reason),
                                 ("incomplete", "detection_time_unknown"))

    def test_incomplete_evidence(self):
        script = {RG: [page(*self.rows(), more=True), page()]}
        document = self.scenario(None, script=script, limits=al.Limits(max_pages_per_scope=1)).attribute()
        self.assertEqual((document.outcome, self.resource(document).attribution.reason),
                         ("incomplete", "evidence_incomplete"))

    def test_one_failed_scope(self):
        both = (deleted()[0] + deleted("azurerm_resource_group.second", SECOND_RG_ID, "azurerm_resource_group")[0],
                deleted()[1] + deleted("azurerm_resource_group.second", SECOND_RG_ID, "azurerm_resource_group")[1])
        script = {RG: [page(*self.rows())], SECOND_RG: [al.SourceError("authorization_failed", 403)]}
        document = self.scenario(both, script=script).attribute()
        self.assertEqual(document.outcome, "incomplete")
        self.assertEqual(self.resource(document, "azurerm_resource_group.second").attribution.reason,
                         "evidence_failed")
        self.assertEqual(self.resource(document, "azurerm_resource_group.second").resource_id, SECOND_RG_ID)
        self.assertEqual(self.resource(document).attribution.status, "confirmed")

    def test_failed_evidence(self):
        document = self.scenario(None, script={RG: [al.SourceError("throttled", 429)]}).attribute()
        self.assertEqual((document.outcome, document.failure.model_dump()),
                         ("failed", {"stage": "evidence", "reason": "evidence_failed"}))
        self.assertEqual([r.attribution.reason for r in document.resources], ["evidence_failed"])

    def test_non_queried_targets(self):
        sub_level = f"/subscriptions/{SUB}/providers/Microsoft.Authorization/roleAssignments/ra1"
        drift, changes = [], []
        for address, rid in (("azurerm_network_security_group.no_id", DELETE),
                             ("azurerm_network_security_group.bad_id", "not-an-arm-id"),
                             ("azurerm_role_assignment.sub", sub_level)):
            d, c = deleted(address, rid)
            drift += d
            changes += c
        document = self.scenario((drift, changes), script={}).attribute()
        self.assertEqual({r.address: (r.attribution.reason, r.resource_id) for r in document.resources}, {
            "azurerm_network_security_group.no_id": ("no_resource_id", None),
            "azurerm_network_security_group.bad_id": ("invalid_resource_id", None),
            "azurerm_role_assignment.sub": ("unsupported_scope", sub_level),
        })
        self.assertEqual(document.outcome, "incomplete")

    def test_update_create_and_replace_drift_stay_unknown(self):
        cases = {
            "update": updated(),
            "replace": updated(drift_actions=("delete", "create")),
            "create": ([raw_entry(NSG_ADDR, ["create"], None, nsg())], []),
        }
        for name, drift_changes in cases.items():
            with self.subTest(name):
                write = self.W(8)  # a single write by a single caller is still not attribution
                scenario = self.scenario(drift_changes, write)
                document = scenario.attribute()
                attribution = self.resource(document).attribution
                self.assertEqual((attribution.status, attribution.reason), ("unknown", "update_not_attributable"))
                self.assertEqual(attribution.candidate_event_ids, ids(write))
                self.assertEqual(self.resource(document).drift_action, name)
                self.assertEqual(document.outcome, "complete")

    def test_no_drift_is_complete_and_empty(self):
        changes = [raw_entry(NSG_ADDR, ["update"], nsg(), nsg(tags={"env": "new"}))]
        document = self.scenario(([], changes), script={}).attribute()
        self.assertEqual((document.outcome, document.resources), ("complete", []))

    def test_binding_mismatch(self):
        good = self.scenario(None, self.rows())
        other_run = self.scenario(None, self.rows(), manifest={"run_id": "attr-run-2"})
        other_plan = self.scenario(deleted(RG_ADDR, RG_ID, "azurerm_resource_group"), self.rows())
        extra = self.scenario((deleted()[0] + updated(RG_ADDR, RG_ID)[0], deleted()[1] + updated(RG_ADDR, RG_ID)[1]),
                              self.rows())
        for name, evidence in (("run_id", other_run), ("target_set", other_plan), ("extra_target", extra)):
            with self.subTest(name):
                document = at.attribute(good.report_bytes, evidence.evidence_bytes)
                self.assertEqual((document.outcome, document.failure.model_dump()),
                                 ("failed", {"stage": "binding", "reason": "evidence_mismatch"}))
                self.assertEqual([(r.attribution.reason, r.resource_id) for r in document.resources],
                                 [("evidence_mismatch", None)])
        timestamp = json.loads(good.evidence_bytes)
        timestamp["subject"]["plan_timestamp"] = "2026-10-03T09:00:00Z"
        document = at.attribute(good.report_bytes, json.dumps(timestamp).encode())
        self.assertEqual(document.failure.reason, "evidence_mismatch")
        no_run = json.loads(good.report_bytes)
        no_run["run"]["run_id"] = None
        self.assertEqual(at.attribute(json.dumps(no_run).encode(), good.evidence_bytes).failure.reason,
                         "evidence_mismatch")

    def test_input_failures(self):
        good = self.scenario(None, self.rows())
        failed_run = self.scenario(None, self.rows(), manifest={"outcome": "failed", "failure_stage": "plan",
                                                                "failure_reason": "x"})
        duplicate = good.evidence_bytes.replace(b'"evidence_version": "2"', b'"evidence_version": "2", "evidence_version": "2"')
        cases = [
            (None, good.evidence_bytes, "report_invalid"), (b"{", good.evidence_bytes, "report_invalid"),
            (b'{"outcome": "succeeded"}', good.evidence_bytes, "report_invalid"),
            (b"\xff\xfe", good.evidence_bytes, "report_invalid"),
            (good.report_bytes, None, "evidence_invalid"), (good.report_bytes, b"[]", "evidence_invalid"),
            (good.report_bytes, duplicate, "evidence_invalid"),
            (good.report_bytes, good.evidence_bytes.replace(b'"untrusted_external"', b'"trusted"'), "evidence_invalid"),
            (good.report_bytes, b'{"x": NaN}', "evidence_invalid"),
            (failed_run.report_bytes, good.evidence_bytes, "report_failed"),
        ]
        for report, evidence, reason in cases:
            with self.subTest(reason=reason, report=report[:20] if report else None):
                document = at.attribute(report, evidence)
                self.assertEqual((document.outcome, document.failure.model_dump(), document.resources),
                                 ("failed", {"stage": "input", "reason": reason}, []))


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class DeterminismTests(_Base):
    def test_byte_identical_under_event_shuffling(self):
        rows = (self.W(6) + self.D(7, caller=OTHER) + self.W(8) + self.D(8, 30, statuses=("Started", "Failed"))
                + self.D(9) + self.log.group("delete", at_time(9, 0, 1), rid=RULE_ID)
                + self.log.event(at_time(12), resourceId=NSG_ID, category={"value": "Policy"},
                                 operationName={"value": "Microsoft.Authorization/policies/audit/action"}))
        baseline = self.scenario(None, script={RG: [page(*rows[:4], more=True), page(*rows[4:])]})
        expected = at.render_attribution(baseline.attribute())
        self.assertIn('"status": "confirmed"', expected)

        def without_hash(text: str) -> dict:
            doc = json.loads(text)
            doc["binding"].pop("evidence_sha256")
            return doc

        rng = random.Random(72)
        for _ in range(15):
            shuffled = rows[:]
            rng.shuffle(shuffled)
            cut = rng.randrange(1, len(shuffled))
            # same page count: the evidence (it records `pages`) and the attribution are byte-identical
            scenario = self.scenario(None, script={RG: [page(*shuffled[:cut], more=True), page(*shuffled[cut:])]})
            self.assertEqual(scenario.evidence_bytes, baseline.evidence_bytes)
            self.assertEqual(at.render_attribution(scenario.attribute()), expected)
            # different paging changes only the evidence bytes, never the decisions
            single = self.scenario(None, shuffled)
            self.assertEqual(without_hash(at.render_attribution(single.attribute())), without_hash(expected))

    def test_decide_is_independent_of_event_order(self):
        sequences = {
            "confirmed": self.W(8) + self.D(9),
            "multiple": self.W(8) + self.D(9) + self.D(9, 30, caller=OTHER),
            "mixed": self.W(8) + self.D(9, statuses=("Started", "Failed", "Started", "Succeeded")),
            "anchor": self.W(6) + self.D(7) + self.W(8) + self.D(9),
        }
        for name, rows in sequences.items():
            with self.subTest(name):
                evidence = al.ActivityLogEvidence.model_validate_json(self.scenario(None, rows).evidence_bytes)
                arm = al.parse_resource_id(NSG_ID)
                started, finished = al.parse_timestamp(RUN_STARTED), al.parse_timestamp(RUN_FINISHED)
                baseline = at.decide("delete", arm, evidence.events, started, finished)
                rng = random.Random(name)
                for _ in range(20):
                    events = list(evidence.events)
                    rng.shuffle(events)
                    self.assertEqual(at.decide("delete", arm, events, started, finished), baseline)

    def test_identical_inputs_render_identically(self):
        scenario = self.scenario(None, self.W(8) + self.D(9))
        first = at.render_attribution(scenario.attribute())
        self.assertEqual(first, at.render_attribution(scenario.attribute()))
        self.assertTrue(first.endswith("}\n"))
        self.assertEqual(first, json.dumps(json.loads(first), indent=2, sort_keys=True) + "\n")
        self.assertEqual(at.DriftAttribution.model_validate_json(first), scenario.attribute())


# ---------------------------------------------------------------------------
# Output contract and re-check against the evidence
# ---------------------------------------------------------------------------

class ContractTests(_Base):
    def setUp(self):
        super().setUp()
        both = (deleted()[0] + updated(RG_ADDR, RG_ID)[0], deleted()[1] + updated(RG_ADDR, RG_ID)[1])
        self.write, self.delete = self.W(8), self.D(9)
        self.extra = self.log.group("delete", at_time(9, 0, 1), rid=RULE_ID)
        self.rg_write = self.log.group("write", at_time(7), rid=RG_ID)
        self.scen = self.scenario(both, self.write + self.delete + self.extra + self.rg_write)
        self.document = self.scen.attribute()
        self.doc = self.document.model_dump(mode="json")
        self.nsg = [r["address"] for r in self.doc["resources"]].index(NSG_ADDR)
        self.rg = [r["address"] for r in self.doc["resources"]].index(RG_ADDR)

    def invalid(self, mutate, message=None):
        doc = copy.deepcopy(self.doc)
        mutate(doc)
        with self.assertRaises(ValidationError) as ctx:
            at.DriftAttribution.model_validate(doc)
        if message:
            self.assertIn(message, str(ctx.exception))

    def a(self, doc, which="nsg"):
        return doc["resources"][getattr(self, which)]["attribution"]

    def test_valid(self):
        self.assertEqual(self.a(self.doc)["status"], "confirmed")
        self.assertEqual(self.a(self.doc, "rg")["reason"], "update_not_attributable")
        self.assertEqual(self.a(self.doc, "rg")["candidate_event_ids"], ids(self.rg_write))
        self.assertEqual(at.DriftAttribution.model_validate(self.doc).model_dump(mode="json"), self.doc)

    def test_unknown_fields_rejected(self):
        for path in ([], ["binding"], ["binding", "window"], ["resources", 0], ["resources", 0, "attribution"]):
            for name in ("extra", "actor", "confirmed", "caller_identity", "statement"):
                with self.subTest(path=path, name=name):
                    def mutate(doc, path=path, name=name):
                        node = doc
                        for key in path:
                            node = node[key]
                        node[name] = "x"
                    self.invalid(mutate)
        self.invalid(lambda d: self.a(d)["anchor"].update(extra=1))

    def test_constants(self):
        self.assertEqual((self.doc["attribution_version"], self.doc["rules_version"]), ("2", "2"))
        self.assertEqual({k: self.doc["binding"][k] for k in ("skew_seconds", "settle_margin_minutes",
                                                               "automated_overlap_minutes")},
                         {"skew_seconds": 60, "settle_margin_minutes": 10, "automated_overlap_minutes": 5})
        for version in ("1", "3"):
            self.invalid(lambda d, v=version: d.update(attribution_version=v))
            self.invalid(lambda d, v=version: d.update(rules_version=v))
        self.invalid(lambda d: d["binding"].update(skew_seconds=300))
        self.invalid(lambda d: d["binding"].update(settle_margin_minutes=20))
        self.invalid(lambda d: d["binding"].update(automated_overlap_minutes=1))
        self.invalid(lambda d: d["binding"]["window"].update(settled_until="2026-10-03T11:40:00.000000Z"))
        self.invalid(lambda d: self.a(d).update(rule="single_writer"))
        self.invalid(lambda d: self.a(d).update(claim="caused_the_drift"))
        self.invalid(lambda d: self.a(d)["anchor"].update(kind="prior_detection_run"))
        self.invalid(lambda d: self.a(d)["anchor"].update(run_id="prior-run"))
        self.invalid(lambda d: self.a(d).update(reason="made_up"))

    def test_confirmed_invariants(self):
        self.invalid(lambda d: self.a(d).update(caller=None), "needs rule, claim, caller and anchor")
        self.invalid(lambda d: self.a(d).update(anchor=None))
        self.invalid(lambda d: self.a(d).update(reason="caller_missing"))
        self.invalid(lambda d: self.a(d).update(decisive_event_ids=[]))
        self.invalid(lambda d: self.a(d).update(caller="bad‮caller"))
        self.invalid(lambda d: d["resources"][self.nsg].update(resource_id=None))

    def test_unknown_invariants(self):
        self.invalid(lambda d: self.a(d).update(status="unknown"))
        self.invalid(lambda d: self.a(d, "rg").update(caller=CALLER))
        self.invalid(lambda d: self.a(d, "rg").update(reason=None))
        self.invalid(lambda d: self.a(d, "rg").update(status="confirmed"))
        self.invalid(lambda d: self.a(d, "rg").update(reason="no_deletion_event"), "non-delete drift")
        self.invalid(lambda d: self.a(d, "rg").update(reason="evidence_not_settled"),
                     "failed a precondition lists no events")

    def test_event_lists(self):
        self.invalid(lambda d: self.a(d)["decisive_event_ids"].reverse(), "sorted")
        self.invalid(lambda d: self.a(d)["related_event_ids"].append(self.a(d)["decisive_event_ids"][0]),
                     "more than one list")
        self.invalid(lambda d: self.a(d)["candidate_event_ids"].append(self.a(d)["anchor"]["event_ids"][0]),
                     "more than one list")
        self.invalid(lambda d: self.a(d)["related_event_ids"].append("not a token"))

    def test_document_invariants(self):
        self.invalid(lambda d: d["resources"].reverse(), "sorted by address")
        self.invalid(lambda d: d.update(outcome="incomplete"), "outcome must be complete")
        self.invalid(lambda d: d.update(outcome="failed"))
        self.invalid(lambda d: d.update(failure={"stage": "input", "reason": "report_invalid"}))
        self.invalid(lambda d: d.update(outcome="failed", failure={"stage": "input", "reason": "report_invalid"}),
                     "input failure lists no resources")
        self.invalid(lambda d: d.update(outcome="failed", failure={"stage": "binding", "reason": "evidence_mismatch"}))
        self.invalid(lambda d: d.update(failure={"stage": "binding", "reason": "evidence_failed"}))
        self.invalid(lambda d: d["binding"].update(window=None))
        self.invalid(lambda d: d["binding"].update(evidence_sha256="0" * 63))

    def test_each_contract_rule_on_its_own(self):
        nsg_attr = self.a(self.doc)

        def as_unknown(reason):
            return {**nsg_attr, "status": "unknown", "reason": reason, "rule": None, "claim": None, "caller": None,
                    "anchor": None, "decisive_event_ids": [],
                    "candidate_event_ids": sorted(nsg_attr["decisive_event_ids"] + nsg_attr["anchor"]["event_ids"])}

        def emptied(reason):
            return {**as_unknown(reason), "candidate_event_ids": [], "related_event_ids": []}

        self.invalid(lambda d: self.a(d)["anchor"]["event_ids"].reverse(), "anchor event_ids must be sorted")
        self.invalid(lambda d: d["resources"][self.rg].update(attribution=copy.deepcopy(nsg_attr)),
                     "only a deletion can be confirmed")
        self.invalid(lambda d: d["resources"][self.nsg].update(attribution=as_unknown("update_not_attributable")),
                     "not a reason for a deletion")
        self.invalid(lambda d: d["resources"][self.rg].update(attribution=emptied("no_resource_id")),
                     "no_resource_id has no resource_id")
        self.invalid(lambda d: (d["resources"][self.rg].update(attribution=emptied("evidence_mismatch"),
                                                                resource_id=None)),
                     "evidence_mismatch is a document failure")
        self.invalid(lambda d: d["binding"].update(evidence_outcome="failed"), "evidence_outcome must be")
        self.invalid(lambda d: d.update(outcome="failed", failure={"stage": "evidence", "reason": "evidence_failed"}),
                     "evidence failure makes every resource evidence_failed")

        def binding_without_hash(d):
            for r in d["resources"]:
                r.update(attribution=emptied("evidence_mismatch"), resource_id=None, drift_action=r["drift_action"])
            d.update(outcome="failed", failure={"stage": "binding", "reason": "evidence_mismatch"})
            d["binding"].update(evidence_sha256=None)
        self.invalid(binding_without_hash, "evidence_sha256 is required")

    def test_oversized_input_is_invalid(self):
        with mock.patch.object(at, "MAX_INPUT_BYTES", 10):
            document, evidence = at.attribute_files(self.scen.report_path, self.scen.evidence_path)
        self.assertEqual((document.failure.reason, evidence), ("report_invalid", None))

    def test_recheck_accepts_the_real_result(self):
        self.assertEqual(at.verify_against_evidence(self.document, self.scen.evidence_bytes), [])

    def recheck(self, mutate, evidence=None):
        doc = copy.deepcopy(self.doc)
        mutate(doc)
        return at.verify_against_evidence(at.DriftAttribution.model_validate(doc), evidence or self.scen.evidence_bytes)

    def test_recheck_detects_tampering(self):
        write_ids, delete_ids, extra_ids = ids(self.write), ids(self.delete), ids(self.extra)
        foreign = self.log.n + 1000
        cases = {
            "hash": lambda d: d["binding"].update(evidence_sha256="0" * 64),
            "unknown event": lambda d: self.a(d).update(related_event_ids=sorted(
                self.a(d)["related_event_ids"] + [f"00000000-0000-4000-9000-{foreign:012d}"])),
            "caller": lambda d: self.a(d).update(caller=OTHER),
            "swapped": lambda d: (self.a(d).update(decisive_event_ids=write_ids),
                                  self.a(d)["anchor"].update(event_ids=delete_ids)),
            "anchor time": lambda d: self.a(d)["anchor"].update(time="2026-10-02T09:30:00.000000Z"),
            "anchor after delete": lambda d: self.a(d)["anchor"].update(time="2026-10-02T09:00:04.000000Z"),
            "child as decisive": lambda d: (self.a(d).update(decisive_event_ids=extra_ids,
                                                             related_event_ids=delete_ids)),
            "partial group": lambda d: (self.a(d).update(decisive_event_ids=delete_ids[:1],
                                                         candidate_event_ids=delete_ids[1:])),
            "not matched": lambda d: self.a(d, "rg").update(related_event_ids=sorted(
                self.a(d, "rg")["related_event_ids"] + [delete_ids[0]])),
            "subject": lambda d: d["binding"].update(run_id="other-run"),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                self.assertNotEqual(self.recheck(mutate), [])
        self.assertNotEqual(at.verify_against_evidence(self.document, b"{}"), [])
        self.assertNotEqual(at.verify_against_evidence(self.document, None), [])

    def test_recheck_specific_findings(self):
        write_ids, delete_ids, extra_ids = ids(self.write), ids(self.delete), ids(self.extra)
        two_groups = self.recheck(lambda d: self.a(d).update(decisive_event_ids=sorted(delete_ids + extra_ids),
                                                             related_event_ids=[]))
        self.assertTrue(any("not one operation group" in p for p in two_groups), two_groups)
        reversed_order = self.recheck(lambda d: (self.a(d).update(decisive_event_ids=write_ids),
                                                 self.a(d)["anchor"].update(event_ids=delete_ids,
                                                                            time="2026-10-02T09:00:04.000000Z")))
        self.assertTrue(any("does not precede" in p for p in reversed_order), reversed_order)
        doc = copy.deepcopy(self.doc)
        doc["binding"]["evidence_sha256"] = hashlib.sha256(b"{}").hexdigest()
        self.assertEqual(at.verify_against_evidence(at.DriftAttribution.model_validate(doc), b"{}"),
                         ["the evidence does not satisfy its contract"])


# ---------------------------------------------------------------------------
# Wording, boundaries and safety
# ---------------------------------------------------------------------------

class SafetyTests(_Base):
    SOURCE = os.path.join(ROOT, "src", "drift_engine", "attribution.py")

    def test_claim_wording(self):
        self.assertEqual(at.CLAIM_TEMPLATE.format(caller="X"),
                         "Azure recorded caller X performing the successful delete of this exact resource under the "
                         "correlation rules.")
        scenario = self.scenario(None, self.W(8) + self.D(9))
        document = scenario.attribute()
        rendered = at.render_attribution(document) + at.render_claim(self.resource(document))
        for phrase in ("caused", "cause", "out-of-band", "made the", "responsible", "guilty"):
            self.assertNotIn(phrase, rendered.lower())
        unknown = self.scenario(None, self.D(9)).attribute()
        self.assertIsNone(at.render_claim(self.resource(unknown)))

    def test_no_azure_network_or_clock_in_attribution(self):
        with open(self.SOURCE, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertEqual(imported - {"__future__", "hashlib", "json", "logging", "os", "collections", "dataclasses",
                                     "datetime", "typing", "pydantic", "drift_engine"}, set())
        called = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertFalse(called & {"now", "utcnow", "today", "monotonic", "perf_counter", "urlopen", "request"})
        drift_imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                         and (node.module or "").startswith("drift_engine")}
        self.assertEqual(drift_imports, {"drift_engine.activity_logs", "drift_engine.logs", "drift_engine.models"})

    def test_importing_and_running_never_loads_azure(self):
        scenario = self.scenario(None, self.W(8) + self.D(9))
        code = ("import json, sys; from drift_engine import cli; code = cli.main(sys.argv[1:]);"
                "print(json.dumps([code, sorted(m for m in sys.modules if m == 'azure' or m.startswith('azure.'))]))")
        out = os.path.join(self.tmp, "attr.json")
        result = subprocess.run([sys.executable, "-c", code, "attribute", "--report", scenario.report_path,
                                 "--evidence", scenario.evidence_path, "--output", out],
                                capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src")),
                                timeout=120)
        self.assertEqual(json.loads(result.stdout.strip().splitlines()[-1]), [0, []], result.stderr)

    def test_ai_layer_does_not_use_attribution(self):
        for directory, _, files in os.walk(os.path.join(ROOT, "src", "ai_engine")):
            for name in files:
                if name.endswith(".py"):
                    with open(os.path.join(directory, name), encoding="utf-8") as fh:
                        text = fh.read()
                    self.assertNotIn("drift_engine.attribution", text, name)
                    self.assertNotIn("import attribution", text, name)

    def test_inputs_are_never_modified(self):
        scenario = self.scenario(None, self.W(8) + self.D(9))
        before = [hashlib.sha256(open(p, "rb").read()).hexdigest()
                  for p in (scenario.report_path, scenario.evidence_path, scenario.plan, scenario.manifest)]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["attribute", "--report", scenario.report_path, "--evidence",
                                       scenario.evidence_path, "--output", os.path.join(self.tmp, "out.json")]), 0)
        after = [hashlib.sha256(open(p, "rb").read()).hexdigest()
                 for p in (scenario.report_path, scenario.evidence_path, scenario.plan, scenario.manifest)]
        self.assertEqual(before, after)
        self.assertEqual(json.loads(scenario.report_bytes), evaluate(scenario.plan, scenario.manifest).report)


# ---------------------------------------------------------------------------
# Safeguard mutants: each one must change at least one scenario's result
# ---------------------------------------------------------------------------

MUTANTS = {
    "anchor-not-required": ('    else:\n        return unknown("no_existence_anchor")\n',
                            '    else:\n        anchor_doc, anchor_ids, since_anchor = None, (), lifecycle\n'),
    "anchor-any-successful-group": ('if g.kind == "write" and g.outcome == "successful"]', 'if g.outcome == "successful"]'),
    "anchor-earliest-write": ("    anchor = lifecycle[writes[-1]] if writes else None",
                              "    anchor = lifecycle[writes[0]] if writes else None"),
    "multiple-deletes-allowed": ("    if len(deletes) > 1:", "    if False:"),
    "unresolved-ignored": ('    if any(g.outcome == "unresolved" for g in since_anchor):', "    if False:"),
    "unresolved-dropped-from-lifecycle": ('lifecycle = [g for g in groups if g.outcome != "failed" and g.start <= t_end]',
                                          'lifecycle = [g for g in groups if g.outcome == "successful" and g.start <= t_end]'),
    "after-detection-included": ('lifecycle = [g for g in groups if g.outcome != "failed" and g.start <= t_end]',
                                 'lifecycle = [g for g in groups if g.outcome != "failed"]'),
    "caller-missing-ignored": ("    if any(caller is None for caller in candidate.callers):", "    if False:"),
    "caller-inconsistency-ignored": ("    if len(set(candidate.callers)) != 1:", "    if False:"),
    "concurrency-ignored": ("    if not candidate.end < t_start:", "    if False:"),
    "concurrency-boundary": ("    if not candidate.end < t_start:", "    if not candidate.end <= t_start:"),
    "skew-dropped": ("    t_start, t_end = run_started - SKEW, run_finished + SKEW",
                     "    t_start, t_end = run_started, run_finished"),
    "mixed-outcome-as-failed": ("        if succeeded:\n            outcome = \"successful\"",
                                "        if succeeded and not any(e.status in TERMINAL_FAILURES for e in rows):\n"
                                "            outcome = \"successful\""),
    "order-touching-allowed": ("        if earlier.end >= later.start:", "        if earlier.end > later.start:"),
    "latest-write-ignored": ('    if lifecycle[-1].kind == "write":', "    if False:"),
    "update-drift-attributable": ('    if drift_action != "delete":', '    if drift_action not in ("delete", "update"):'),
    "automation-ignored": ("        if (event.category in AUTOMATED_CATEGORIES and _same_resource(event, arm)",
                           "        if (False and _same_resource(event, arm)"),
    "category-ignored": ("        if (event.category != LIFECYCLE_CATEGORY or operation not in (write_op, delete_op)",
                         "        if (operation not in (write_op, delete_op)"),
    "case-sensitive-operation": ("        operation = event.operation_name.lower()",
                                 "        operation = event.operation_name"),
    "descendants-decide": ("                or not _same_resource(event, arm)):\n            other.append(event)",
                           "                ):\n            other.append(event)"),
    "settle-check-removed": ("        elif not settled(queried_at, finished):", "        elif False:"),
    "settle-from-start": ("    return queried_at >= run_finished + SETTLE_MARGIN",
                          "    return queried_at >= run_finished - timedelta(minutes=5) + SETTLE_MARGIN"),
    "r7-tied-to-skew": ("    low, high = candidate.start - AUTOMATED_OVERLAP, candidate.end + AUTOMATED_OVERLAP",
                        "    low, high = candidate.start - SKEW, candidate.end + SKEW"),
    "unreadable-ignored": ("        elif scope_key(target.resource_id) in unreadable:", "        elif False:"),
    "binding-check-removed": ('            or subject.run_id != binding["run_id"] or subject.plan_timestamp != binding["plan_timestamp"]):',
                              "            ):"),
    "target-set-check-removed": ('    if set(targets) != {r["address"] for r in drifted}:', "    if False:"),
    "target-status-ignored": ('        elif target.status != "queried":', "        elif False:"),
    "correlation-ignored": ('        key = ("correlation", event.correlation_id) if event.correlation_id is not None else ("event", event.event_data_id)',
                            '        key = ("all", None)'),
}


class SafeguardMutationTests(_Base):
    """Each mutant removes one safeguard from a copy of attribution.py (loaded in-process;
    the repository file is never changed) and must change the result of at least one
    scenario below, i.e. every safeguard is exercised by a test."""

    def scenarios(self) -> dict[str, tuple[bytes, bytes]]:
        log = self.log
        day3 = dt.datetime(2026, 10, 3, tzinfo=UTC)
        both = (deleted(RG_ADDR, RG_ID, "azurerm_resource_group")[0] + deleted()[0],
                deleted(RG_ADDR, RG_ID, "azurerm_resource_group")[1] + deleted()[1])
        built = {
            "confirmed": self.scenario(None, self.W(8) + self.D(9)),
            "no-anchor": self.scenario(None, self.D(9)),
            "delete-before-anchor": self.scenario(None, self.D(6) + self.W(8) + self.D(9)),
            "re-anchor": self.scenario(None, self.W(6) + self.D(7) + self.W(8) + self.D(9)),
            "multiple": self.scenario(None, self.W(8) + self.D(9) + self.D(9, 30, caller=OTHER)),
            "unresolved": self.scenario(None, self.W(8) + self.D(8, 30, statuses=("Started",)) + self.D(9)),
            "unresolved-last": self.scenario(None, self.W(8) + self.D(9, statuses=("Started", "Accepted"))),
            "late-delete": self.scenario(None, self.W(8) + self.D(9)
                                         + log.group("delete", T_END + dt.timedelta(minutes=1), caller=OTHER)),
            "caller-missing": self.scenario(None, self.W(8) + self.D(9, callers=[CALLER, None, CALLER])),
            "caller-mixed": self.scenario(None, self.W(8) + self.D(9, callers=[GUID_CALLER, CALLER, CALLER])),
            "concurrent": self.scenario(None, log.group("write", at_time(8, day=day3))
                                        + log.group("delete", at_time(10, 1, day=day3), statuses=("Succeeded",))),
            "concurrent-boundary": self.scenario(None, log.group("write", at_time(8, day=day3))
                                                 + log.group("delete", at_time(9, 59, day=day3), statuses=("Succeeded",))),
            "concurrent-skew": self.scenario(None, log.group("write", at_time(8, day=day3))
                                             + log.group("delete", at_time(9, 59, 30, day=day3), statuses=("Succeeded",))),
            "disk-case": self.scenario(None, self.W(8) + self.D(9, statuses=("Started", "Failed", "Started", "Succeeded"))
                                       + self.D(9, 1, statuses=("Started", "Succeeded"), caller=OTHER)),
            "touching": self.scenario(None, self.W(8) + log.group("delete", at_time(8, 0, 4), statuses=("Succeeded",))),
            "rewrite": self.scenario(None, self.W(8) + self.D(9) + self.W(9, 30)),
            "update": self.scenario(updated(), self.W(8)),
            "automated": self.scenario(None, self.W(8) + self.D(9) + log.event(
                at_time(9, 2), resourceId=NSG_ID, category={"value": "Policy"},
                operationName={"value": "Microsoft.Authorization/policies/audit/action"})),
            "policy-anchor": self.scenario(None, self.W(8, category="Policy") + self.D(9)),
            "case-variant": self.scenario(None, self.W(8, op="microsoft.network/networksecuritygroups/write")
                                          + self.D(9, op="MICROSOFT.NETWORK/NETWORKSECURITYGROUPS/DELETE")),
            "disguised-child": self.scenario(None, self.W(8) + log.group("delete", at_time(9), rid=RULE_ID,
                                                                          op=f"{OPS[NSG_ID]}/delete")),
            "not-settled": self.scenario(None, self.W(8) + self.D(9), queried_at=QUERIED.replace(hour=10, minute=14)),
            "settled-just": self.scenario(None, self.W(8) + self.D(9), queried_at=QUERIED.replace(hour=10, minute=15)),
            "automated-4min": self.scenario(None, self.W(8) + self.D(9) + log.event(
                at_time(9, 4), resourceId=NSG_ID, category={"value": "Policy"},
                operationName={"value": "Microsoft.Authorization/policies/audit/action"})),
            "unreadable": self.scenario(None, self.W(8) + self.D(9) + [ev(9001, ts="2026-10-02T09:30:00Z",
                                                                         operationName={"value": "bad name"})]),
            "incomplete": self.scenario(None, script={RG: [page(*(self.W(8) + self.D(9)), more=True), page()]},
                                        limits=al.Limits(max_pages_per_scope=1)),
            "parent": self.scenario(both, log.group("write", at_time(7), rid=RG_ID) + self.W(8)
                                    + log.group("delete", at_time(9), rid=RG_ID)),
        }
        pairs = {name: (s.report_bytes, s.evidence_bytes) for name, s in built.items()}
        good = built["confirmed"]
        other_run = self.scenario(None, self.W(8) + self.D(9), manifest={"run_id": "attr-run-2"})
        other_plan = self.scenario(deleted(RG_ADDR, RG_ID, "azurerm_resource_group"), self.W(8))
        pairs["mismatch-run"] = (good.report_bytes, other_run.evidence_bytes)
        pairs["mismatch-targets"] = (good.report_bytes, other_plan.evidence_bytes)
        return pairs

    @staticmethod
    def load(name: str, source: str):
        module_name = f"drift_engine._attribution_mutant_{name.replace('-', '_')}"
        module = types.ModuleType(module_name)
        module.__file__ = f"<mutant {name}>"
        sys.modules[module_name] = module
        try:
            exec(compile(source, module.__file__, "exec"), module.__dict__)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
        return module

    @staticmethod
    def outcome(module, report: bytes, evidence: bytes) -> str:
        try:
            return module.render_attribution(module.attribute(report, evidence))
        except Exception as exc:  # a crash also shows that the safeguard was exercised
            return f"raised {type(exc).__name__}"

    def test_every_mutant_is_caught(self):
        with open(at.__file__, encoding="utf-8") as fh:
            source = fh.read()
        pairs = self.scenarios()
        expected = {name: self.outcome(at, *pair) for name, pair in pairs.items()}
        self.assertFalse(any(v.startswith("raised") for v in expected.values()), expected)
        survivors = []
        for name, (old, new) in MUTANTS.items():
            with self.subTest(name):
                self.assertEqual(source.count(old), 1, f"mutant {name} does not apply exactly once")
                module = self.load(name, source.replace(old, new))
                try:
                    if all(self.outcome(module, *pair) == expected[s] for s, pair in pairs.items()):
                        survivors.append(name)
                finally:
                    sys.modules.pop(module.__name__, None)
        self.assertEqual(survivors, [])

    def test_unmutated_copy_matches_the_module(self):
        with open(at.__file__, encoding="utf-8") as fh:
            module = self.load("identity", fh.read())
        try:
            for name, pair in self.scenarios().items():
                self.assertEqual(self.outcome(module, *pair), self.outcome(at, *pair), name)
        finally:
            sys.modules.pop(module.__name__, None)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class CliTests(_Base):
    def tearDown(self):
        logger = logging.getLogger("drift_engine")
        for handler in [h for h in logger.handlers if getattr(h, "_drift_engine_handler", False)]:
            logger.removeHandler(handler)
        logger.setLevel(logging.NOTSET)

    def run_cli(self, scenario, *extra, output=True):
        args = ["attribute", "--report", scenario.report_path, "--evidence", scenario.evidence_path, *extra]
        self.output = os.path.join(self.tmp, "drift_attribution.json")
        if output:
            args += ["--output", self.output]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(args)
        return code, out.getvalue(), err.getvalue()

    def test_complete(self):
        scenario = self.scenario(None, self.W(8) + self.D(9))
        code, out, err = self.run_cli(scenario)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("attribution_outcome=complete  resources=1 [confirmed=1, unknown=0]", out)
        self.assertIn(f"Attribution: {self.output}", out)
        self.assertNotIn(CALLER, out)
        self.assertEqual(stat.S_IMODE(os.stat(self.output).st_mode), 0o600)
        with open(self.output, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), at.render_attribution(scenario.attribute()))

    def test_existing_output_keeps_its_mode(self):
        scenario = self.scenario(None, self.W(8) + self.D(9))
        self.run_cli(scenario)
        os.chmod(self.output, 0o640)
        self.assertEqual(self.run_cli(scenario)[0], 0)
        self.assertEqual(stat.S_IMODE(os.stat(self.output).st_mode), 0o640)

    def test_standard_output(self):
        scenario = self.scenario(None, self.W(8) + self.D(9))
        code, out, _ = self.run_cli(scenario, output=False)
        self.assertEqual((code, out), (0, at.render_attribution(scenario.attribute())))

    def test_incomplete_and_failed(self):
        cases = [
            (self.scenario(None, self.W(8) + self.D(9), manifest={"started_at": DELETE}),
             "ATTRIBUTION INCOMPLETE [incomplete]"),
            (self.scenario(None, script={RG: [al.SourceError("throttled", 429)]}), "ATTRIBUTION FAILED [evidence_failed]"),
        ]
        for scenario, message in cases:
            with self.subTest(message):
                code, _, err = self.run_cli(scenario)
                self.assertEqual(code, 1)
                self.assertIn(message, err)
                self.assertIn("Drift detection results are unaffected.", err)
                self.assertTrue(os.path.exists(self.output))

    def test_missing_input_file(self):
        scenario = self.scenario(None, self.W(8) + self.D(9))
        os.remove(scenario.evidence_path)
        code, _, err = self.run_cli(scenario)
        self.assertEqual(code, 1)
        self.assertIn("ATTRIBUTION FAILED [evidence_invalid]", err)

    def test_usage_errors(self):
        for args in (["attribute"], ["attribute", "--report", "r.json"], ["attribute", "--evidence", "e.json"]):
            with self.subTest(args), self.assertRaises(SystemExit) as ctx, contextlib.redirect_stderr(io.StringIO()):
                cli.main(args)
            self.assertEqual(ctx.exception.code, 2)

    def test_unwritable_output(self):
        scenario = self.scenario(None, self.W(8) + self.D(9))
        code, _, err = self.run_cli(scenario, "--output", os.path.join(self.tmp, "missing", "a.json"), output=False)
        self.assertEqual(code, 73)
        self.assertIn("cannot write", err)

    def test_recheck_failure_writes_nothing(self):
        scenario = self.scenario(None, self.W(8) + self.D(9))
        with mock.patch.object(at, "verify_against_evidence", return_value=["tampered"]):
            code, _, err = self.run_cli(scenario)
        self.assertEqual(code, 70)
        self.assertIn("does not match the evidence", err)
        self.assertFalse(os.path.exists(self.output))

    def test_internal_error(self):
        scenario = self.scenario(None, self.W(8) + self.D(9))
        with mock.patch.object(at, "attribute_files", side_effect=RuntimeError("boom")):
            code, _, err = self.run_cli(scenario)
        self.assertEqual(code, 70)
        self.assertIn("No attribution was written; drift detection results are unaffected.", err)
        self.assertFalse(os.path.exists(self.output))

    def test_logs_hold_no_callers_or_ids(self):
        scenario = self.scenario(None, self.W(8) + self.D(9, caller=GUID_CALLER))
        code, _, err = self.run_cli(scenario, "--log-level", "debug", "--log-format", "json")
        self.assertEqual(code, 0)
        self.assertIn("attribution_finished", err)
        for secret in (CALLER, GUID_CALLER, SUB, NSG_ID, RG_ID):
            self.assertNotIn(secret, err)


if __name__ == "__main__":
    unittest.main()
