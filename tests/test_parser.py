"""Tests for src/drift_engine/parser.py (Task 4.2).

Run from the repository root:
    pytest tests/test_parser.py
    python3 -m unittest tests.test_parser    (no installation needed)

Real plans come from tests/fixtures/plan_evidence/ (see tests/test_detect_drift.py
for their provenance). The parser must never raise anything but EvidenceError for
bad input; every invalid case below asserts exactly that.
"""

from __future__ import annotations

import copy
import json
import os
import random
import shutil
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from drift_engine import parser as p  # noqa: E402

FIXTURE_SOURCE = os.path.join(ROOT, "tests", "fixtures", "plan_evidence")
MAIN = 'module.resource_group.azurerm_resource_group.this["main"]'


def fixture_plan(name: str) -> dict:
    with open(os.path.join(FIXTURE_SOURCE, name, "plan.sanitized.json"), encoding="utf-8") as fh:
        return json.load(fh)


def fixture_manifest(name: str) -> dict:
    with open(os.path.join(FIXTURE_SOURCE, name, "detection_run.json"), encoding="utf-8") as fh:
        return json.load(fh)


def fixture_names() -> list[str]:
    return sorted(
        n for n in os.listdir(FIXTURE_SOURCE)
        if os.path.exists(os.path.join(FIXTURE_SOURCE, n, "plan.sanitized.json"))
    )


def by_index(parsed: p.ParsedPlan) -> dict:
    return {r.index: r for r in parsed.resources}


def minimal_plan(**extra) -> dict:
    plan = {"format_version": "1.2", "terraform_version": "1.14.7", "errored": False, "complete": True}
    plan.update(extra)
    return plan


def entry(address: str = "a.b", actions=("update",), **change) -> dict:
    """A resource entry with only the fields Terraform always writes."""
    rtype, name = address.split(".")[-2:]
    mode = "data" if address.startswith("data.") else "managed"
    return {"address": address, "mode": mode, "type": rtype, "name": name,
            "change": {"actions": list(actions), **change}}


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drift-parser-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def write(self, name: str, data: bytes | str) -> str:
        path = os.path.join(self.tmp, name)
        mode = "wb" if isinstance(data, bytes) else "w"
        with open(path, mode, **({} if isinstance(data, bytes) else {"encoding": "utf-8"})) as fh:
            fh.write(data)
        return path

    def assertEvidenceError(self, fn, *args, contains: str = "", **kwargs) -> p.EvidenceError:
        with self.assertRaises(p.EvidenceError) as ctx:
            fn(*args, **kwargs)
        self.assertIn(contains, ctx.exception.reason)
        return ctx.exception


# ---------------------------------------------------------------------------
# Real plans
# ---------------------------------------------------------------------------

class TestRealPlans(unittest.TestCase):
    def test_every_fixture_parses_with_its_manifest(self):
        for name in fixture_names():
            with self.subTest(name):
                m = fixture_manifest(name)
                parsed = p.parse_plan_file(
                    os.path.join(FIXTURE_SOURCE, name, "plan.sanitized.json"),
                    m["plan_exit_code"], m["terraform_version"],
                )
                self.assertEqual(parsed.header["format_version"], "1.2")
                self.assertEqual(parsed.header["terraform_version"], "1.14.7")
                self.assertIs(parsed.header["errored"], False)
                self.assertIs(parsed.header["complete"], True)
                self.assertEqual(set(parsed.header), set(p.PLAN_HEADER_FIELDS))
                addresses = [r.address for r in parsed.resources]
                self.assertEqual(addresses, sorted(addresses))
                self.assertEqual(list(parsed.output_changes), ["resource_groups"])

    def test_every_fixture_parses_without_manifest(self):
        for name in fixture_names():
            with self.subTest(name):
                self.assertIsInstance(p.parse_plan(fixture_plan(name)), p.ParsedPlan)

    def test_external_drift_views(self):
        main = by_index(p.parse_plan(fixture_plan("external_drift"), 2, "1.14.7"))["main"]
        self.assertEqual(main.address, MAIN)
        self.assertEqual(main.type, "azurerm_resource_group")
        self.assertEqual(main.mode, "managed")
        self.assertEqual(main.module_address, "module.resource_group")
        self.assertEqual(main.actions, ["update"])
        self.assertEqual(main.drift_actions, ["update"])
        self.assertEqual(main.state["tags"]["probe"], "1")  # recorded state
        self.assertNotIn("probe", main.real["tags"])  # removed outside Terraform
        self.assertEqual(main.desired["tags"]["probe"], "1")  # configuration restores it
        self.assertFalse(main.importing)
        self.assertIsNone(main.previous_address)
        self.assertEqual(len(main.sensitive_masks), 4)  # drift before/after + change before/after

    def test_without_drift_entry_real_equals_recorded_state(self):
        main = by_index(p.parse_plan(fixture_plan("config_change")))["main"]
        self.assertIsNone(main.drift_actions)
        self.assertIs(main.real, main.state)
        self.assertEqual(len(main.sensitive_masks), 2)

    def test_create_has_null_state_and_unknown_values(self):
        extra = by_index(p.parse_plan(fixture_plan("resource_added")))["extra"]
        self.assertEqual(extra.actions, ["create"])
        self.assertIsNone(extra.state)
        self.assertIsNone(extra.real)
        self.assertIsInstance(extra.desired, dict)
        self.assertIs(extra.after_unknown["id"], True)
        self.assertNotIn("id", extra.desired)  # unknown value is not invented

    def test_delete_has_null_desired(self):
        main = by_index(p.parse_plan(fixture_plan("resource_removed")))["main"]
        self.assertEqual(main.actions, ["delete"])
        self.assertIsNone(main.desired)
        self.assertIsInstance(main.state, dict)

    def test_external_deletion_has_null_real(self):
        ghost = by_index(p.parse_plan(fixture_plan("external_deletion")))["ghost"]
        self.assertEqual(ghost.drift_actions, ["delete"])
        self.assertIsNone(ghost.real)
        self.assertIsInstance(ghost.state, dict)

    def test_parsing_is_deterministic(self):
        plan = fixture_plan("external_deletion")
        self.assertEqual(p.parse_plan(plan), p.parse_plan(copy.deepcopy(plan)))


# ---------------------------------------------------------------------------
# Missing fields, null states, unknown values
# ---------------------------------------------------------------------------

class TestMissingAndNullFields(unittest.TestCase):
    def test_missing_arrays_default_to_empty_after_gate(self):
        parsed = p.parse_plan(minimal_plan())
        self.assertEqual(parsed.resources, ())
        self.assertEqual(parsed.output_changes, {})

    def test_missing_optional_header_fields_read_as_none(self):
        parsed = p.parse_plan(minimal_plan())
        self.assertIsNone(parsed.header["timestamp"])
        self.assertIsNone(parsed.header["applyable"])

    def test_entry_with_only_required_fields(self):
        r = p.parse_plan(minimal_plan(resource_changes=[entry()])).resources[0]
        self.assertEqual((r.address, r.mode, r.type, r.name), ("a.b", "managed", "a", "b"))
        for field in ("module_address", "index", "provider_name",
                      "action_reason", "previous_address", "state", "real", "desired", "after_unknown"):
            self.assertIsNone(getattr(r, field), field)
        self.assertEqual(r.sensitive_masks, (None, None))
        self.assertFalse(r.importing)

    def test_explicit_nulls(self):
        e = entry(before=None, after=None, after_unknown=None, before_sensitive=None,
                  after_sensitive=None, importing=None)
        e.update(module_address=None, index=None, previous_address=None, action_reason=None)
        r = p.parse_plan(minimal_plan(resource_changes=[e])).resources[0]
        self.assertIsNone(r.state)
        self.assertIsNone(r.desired)
        self.assertFalse(r.importing)

    def test_drift_only_resource(self):
        d = entry(actions=("update",), before={"x": 1}, after={"x": 2})
        r = p.parse_plan(minimal_plan(resource_drift=[d])).resources[0]
        self.assertIsNone(r.actions)
        self.assertEqual((r.state, r.real, r.desired), ({"x": 1}, {"x": 2}, None))

    def test_unknown_values_passed_through(self):
        e = entry(before={"a": 1}, after={"a": 1}, after_unknown={"b": True, "c": {"d": True}})
        r = p.parse_plan(minimal_plan(resource_changes=[e])).resources[0]
        self.assertEqual(r.after_unknown, {"b": True, "c": {"d": True}})
        self.assertNotIn("b", r.desired)

    def test_whole_object_unknown(self):
        e = entry(actions=("create",), before=None, after=None, after_unknown=True)
        r = p.parse_plan(minimal_plan(resource_changes=[e])).resources[0]
        self.assertIs(r.after_unknown, True)

    def test_importing_and_move_recorded(self):
        e = entry(actions=("no-op",), importing={"id": "x"})
        e["previous_address"] = "a.old"
        r = p.parse_plan(minimal_plan(resource_changes=[e])).resources[0]
        self.assertTrue(r.importing)
        self.assertEqual(r.previous_address, "a.old")

    def test_data_sources_are_excluded(self):
        data = entry("data.x.y", actions=("read",))
        data["mode"] = "data"
        parsed = p.parse_plan(minimal_plan(resource_changes=[data, entry()]))
        self.assertEqual([r.address for r in parsed.resources], ["a.b"])

    def test_non_object_views_are_kept_not_rejected(self):
        e = entry(before="text", after=[1, 2], after_unknown="odd")
        r = p.parse_plan(minimal_plan(resource_changes=[e])).resources[0]
        self.assertEqual((r.state, r.desired, r.after_unknown), ("text", [1, 2], "odd"))

    def test_optional_manifest_checks(self):
        plan = minimal_plan(resource_changes=[entry()])
        p.parse_plan(plan)  # no manifest: version and exit-code checks skipped
        self.assertEvidenceError(plan, 0, None, "plan exit 0")
        self.assertEvidenceError(plan, None, "1.0.0", "terraform_version")

    def assertEvidenceError(self, plan, rc, version, contains):
        with self.assertRaises(p.EvidenceError) as ctx:
            p.parse_plan(plan, rc, version)
        self.assertEqual(ctx.exception.stage, p.PLAN_STAGE)
        self.assertIn(contains, ctx.exception.reason)


# ---------------------------------------------------------------------------
# Invalid plans: always EvidenceError, never another exception
# ---------------------------------------------------------------------------

def _nested(depth: int) -> dict:
    v: object = "x"
    for _ in range(depth):
        v = {"k": v}
    return v  # type: ignore[return-value]


INVALID_PLANS = {
    "not an object": ([], "not a JSON object"),
    "null": (None, "not a JSON object"),
    "no format_version": ({"errored": False, "complete": True}, "format_version missing"),
    "format_version number": (minimal_plan(format_version=1.2), "format_version missing"),
    "format major 2": (minimal_plan(format_version="2.0"), "major must be 1"),
    "errored": (minimal_plan(errored=True), "errored is true"),
    "errored missing": ({"format_version": "1.2", "complete": True}, "errored is null"),
    "incomplete": (minimal_plan(complete=False), "complete is false"),
    "resource_changes object": (minimal_plan(resource_changes={}), "resource_changes is not an array"),
    "resource_drift null": (minimal_plan(resource_drift=None), "resource_drift is not an array"),
    "entry not object": (minimal_plan(resource_changes=[5]), "without address/change.actions"),
    "entry no address": (minimal_plan(resource_changes=[{"change": {"actions": []}}]), "without address"),
    "address not string": (minimal_plan(resource_changes=[{"address": 1, "change": {"actions": []}}]), "without address"),
    "change missing": (minimal_plan(resource_changes=[{"address": "a"}]), "without address/change.actions"),
    "change null": (minimal_plan(resource_changes=[{"address": "a", "change": None}]), "without address"),
    "actions missing": (minimal_plan(resource_drift=[{"address": "a", "change": {}}]), "change.actions"),
    "actions string": (minimal_plan(resource_changes=[{"address": "a", "change": {"actions": "update"}}]), "change.actions"),
    "actions not strings": (minimal_plan(resource_changes=[entry(actions=("create", None))]), "not all strings"),
    "actions nested": (minimal_plan(resource_changes=[entry(actions=(["update"],))]), "not all strings"),
    "duplicate address": (minimal_plan(resource_changes=[entry(), entry(actions=("no-op",))]), "duplicate address"),
    "deep value": (minimal_plan(resource_changes=[entry(after=_nested(2000))]), "nested deeper than"),
    "output_changes array": (minimal_plan(output_changes=[]), "output_changes is not an object"),
    "output no actions": (minimal_plan(output_changes={"o": {}}), "output_changes contains an entry without"),
    "output actions not strings": (minimal_plan(output_changes={"o": {"actions": [1]}}), "not all strings"),
}


class TestInvalidPlans(TempDirTestCase):
    def test_invalid_structures(self):
        for name, (plan, message) in INVALID_PLANS.items():
            with self.subTest(name):
                err = self.assertEvidenceError(p.parse_plan, plan, contains=message)
                self.assertEqual(err.stage, p.PLAN_STAGE)

    def test_depth_limit_boundary(self):
        # Containers are counted from the entry (level 1): entry -> change -> after -> ...
        # so `after` may hold MAX_VALUE_DEPTH - 2 nested objects and no more.
        ok = minimal_plan(resource_changes=[entry(after=_nested(p.MAX_VALUE_DEPTH - 2))])
        p.parse_plan(ok)
        deep = minimal_plan(resource_changes=[entry(after=_nested(p.MAX_VALUE_DEPTH - 1))])
        self.assertEvidenceError(p.parse_plan, deep, contains="nested deeper")

    def test_several_violations_reported_together(self):
        err = self.assertEvidenceError(p.parse_plan, {"format_version": "3"})
        self.assertEqual(err.reason.count(";"), 2)

    def test_invalid_files(self):
        valid = json.dumps(fixture_plan("in_sync"))
        cases = {
            "empty": (b"", "not valid JSON"),
            "truncated": (valid[:500], "not valid JSON"),
            "two documents": (valid + valid, "not valid JSON"),
            "trailing garbage": (valid + "x", "not valid JSON"),
            "utf-8 bom": ("﻿" + valid, "not valid JSON"),
            "not utf-8": (b"\xff\xfe{}", "not valid JSON"),
            "text": ("plan output, not json", "not valid JSON"),
            "deeply nested json": ("[" * 200_000 + "]" * 200_000, ""),
        }
        for name, (data, message) in cases.items():
            with self.subTest(name):
                path = self.write("plan.json", data)
                self.assertEvidenceError(p.parse_plan_file, path, contains=message)

    def test_missing_file(self):
        self.assertEvidenceError(p.parse_plan_file, os.path.join(self.tmp, "plan.json"), contains="plan.json not found")

    def test_directory_instead_of_file(self):
        path = os.path.join(self.tmp, "plan.json")
        os.mkdir(path)
        self.assertEvidenceError(p.parse_plan_file, path, contains="not valid JSON")

    def test_load_json_keeps_caller_stage(self):
        err = self.assertEvidenceError(p.load_json, os.path.join(self.tmp, "detection_run.json"), "manifest")
        self.assertEqual(err.stage, "manifest")


def _with(field: str, value, array: str = "resource_changes") -> dict:
    e = entry()
    if value is _DROP:
        e.pop(field, None)  # absent from the entry
    else:
        e[field] = value
    return minimal_plan(**{array: [e]})


_DROP = object()

# (field, bad value, expected message fragment)
IDENTITY_CASES = (
    ("address", "", "an empty address"),
    ("mode", _DROP, "a mode other than managed or data"),
    ("mode", "unmanaged", "a mode other than managed or data"),
    ("mode", None, "a mode other than managed or data"),
    ("type", _DROP, "a missing or non-string type"),
    ("type", None, "a missing or non-string type"),
    ("type", 7, "a missing or non-string type"),
    ("name", _DROP, "a missing or non-string name"),
    ("name", ["b"], "a missing or non-string name"),
    ("index", True, "an index that is not a string or integer"),
    ("index", 1.0, "an index that is not a string or integer"),
    ("index", ["main"], "an index that is not a string or integer"),
    ("index", {"k": 1}, "an index that is not a string or integer"),
    ("module_address", 3, "a non-string module_address"),
    ("provider_name", [], "a non-string provider_name"),
    ("action_reason", False, "a non-string action_reason"),
    ("previous_address", {}, "a non-string previous_address"),
)


class TestIdentityFields(unittest.TestCase):
    """Gap found in Task 4.6: identity fields reached the report unchecked."""

    def test_malformed_identity_fields_rejected_in_both_arrays(self):
        for array in ("resource_changes", "resource_drift"):
            for field, value, message in IDENTITY_CASES:
                with self.subTest(array=array, field=field, value=repr(value)):
                    with self.assertRaises(p.EvidenceError) as ctx:
                        p.parse_plan(_with(field, value, array))
                    self.assertEqual(ctx.exception.stage, p.PLAN_STAGE)
                    self.assertIn(f"{array} contains an entry with {message}", ctx.exception.reason)

    def test_empty_actions_rejected(self):
        for array in ("resource_changes", "resource_drift"):
            with self.subTest(array):
                with self.assertRaises(p.EvidenceError) as ctx:
                    p.parse_plan(minimal_plan(**{array: [entry(actions=())]}))
                self.assertIn(f"{array} contains an entry with empty actions", ctx.exception.reason)
        with self.assertRaises(p.EvidenceError) as ctx:
            p.parse_plan(minimal_plan(output_changes={"o": {"actions": []}}))
        self.assertIn("output_changes contains an entry with empty actions", ctx.exception.reason)

    def test_data_source_entries_are_checked_too(self):
        data = entry("data.azurerm_client_config.current", actions=("read",))
        data["name"] = None
        with self.assertRaises(p.EvidenceError):
            p.parse_plan(minimal_plan(resource_changes=[data]))

    def test_several_problems_reported_once_each_in_fixed_order(self):
        bad = [entry("a.x"), entry("a.y"), entry("a.z")]
        bad[0]["type"] = None
        bad[1]["type"] = 1
        bad[2]["index"] = True
        with self.assertRaises(p.EvidenceError) as ctx:
            p.parse_plan(minimal_plan(resource_changes=bad))
        self.assertEqual(ctx.exception.reason,
                         "resource_changes contains an entry with a missing or non-string type; "
                         "resource_changes contains an entry with an index that is not a string or integer")

    def test_every_valid_terraform_shape_accepted(self):
        valid = (
            ("index", _DROP), ("index", None), ("index", 0), ("index", 12), ("index", "main"), ("index", ""),
            ("module_address", _DROP), ("module_address", None), ("module_address", 'module.a["x"]'),
            ("provider_name", _DROP), ("provider_name", "registry.terraform.io/hashicorp/azurerm"),
            ("action_reason", None), ("action_reason", "replace_because_cannot_update"),
            ("previous_address", None), ("previous_address", "a.old"),
            ("mode", "data"), ("name", ""),
        )
        for field, value in valid:
            with self.subTest(field=field, value=repr(value)):
                self.assertIsInstance(p.parse_plan(_with(field, value)), p.ParsedPlan)

    def test_real_fixtures_unaffected(self):
        source = os.path.join(ROOT, "tests", "fixtures", "plan_evidence")
        for name in sorted(os.listdir(source)):
            path = os.path.join(source, name, "plan.sanitized.json")
            if os.path.exists(path):
                with self.subTest(name):
                    self.assertIsInstance(p.parse_plan_file(path), p.ParsedPlan)

    def test_classifier_reports_rejected_identity_as_failed_evidence(self):
        # The stdlib path used by scripts/detect_drift.py: a failed report, never a
        # report whose resources break the schema.
        from drift_engine import classifier

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "plan.json")
            for field, value, message in IDENTITY_CASES:
                with self.subTest(field=field, value=repr(value)):
                    with open(path, "w", encoding="utf-8") as fh:
                        json.dump(_with(field, value), fh)
                    report = classifier.evaluate(path).report
                    self.assertEqual((report["outcome"], report["has_drift"], report["resources"]),
                                     ("failed", None, []))
                    self.assertEqual(report["failure"]["stage"], "integrity")
                    self.assertIn(message, report["failure"]["reason"])


class TestFuzzedPlans(unittest.TestCase):
    """Random structural damage to real plans: success or EvidenceError, nothing else."""

    REPLACEMENTS = (None, True, 0, -1, 1.5, "", "x", [], {}, [None], {"actions": None}, ["no-op"])

    def _paths(self, node, path=()):
        yield path
        if isinstance(node, dict):
            for k, v in node.items():
                yield from self._paths(v, path + (k,))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from self._paths(v, path + (i,))

    def test_random_mutations(self):
        rng = random.Random(4242)
        plans = [fixture_plan(n) for n in fixture_names()]
        outcomes = {"parsed": 0, "rejected": 0}
        for _ in range(1500):
            plan = copy.deepcopy(rng.choice(plans))
            for _ in range(rng.randint(1, 3)):
                path = rng.choice(list(self._paths(plan))[1:])
                parent = plan
                for key in path[:-1]:
                    parent = parent[key]
                if isinstance(parent, dict) and rng.random() < 0.3:
                    del parent[path[-1]]
                else:
                    parent[path[-1]] = copy.deepcopy(rng.choice(self.REPLACEMENTS))
            try:
                p.parse_plan(plan, rng.choice((None, 0, 2)), rng.choice((None, "1.14.7")))
                outcomes["parsed"] += 1
            except p.EvidenceError:
                outcomes["rejected"] += 1
        self.assertGreater(outcomes["parsed"], 0)
        self.assertGreater(outcomes["rejected"], 0)


# ---------------------------------------------------------------------------
# Size limit (50 MB)
# ---------------------------------------------------------------------------

class TestSizeLimit(TempDirTestCase):
    def test_limit_is_50_mib(self):
        self.assertEqual(p.MAX_PLAN_BYTES, 50 * 1024 * 1024)

    def test_file_at_limit_is_read_and_one_byte_over_is_rejected(self):
        data = json.dumps(fixture_plan("in_sync"))
        path = self.write("plan.json", data)
        size = os.path.getsize(path)
        self.assertIsInstance(p.parse_plan_file(path, max_bytes=size), p.ParsedPlan)
        self.assertEvidenceError(p.parse_plan_file, path, max_bytes=size - 1, contains="limit")

    def test_file_over_50_mib_is_rejected_without_reading(self):
        path = os.path.join(self.tmp, "plan.json")
        with open(path, "wb") as fh:
            fh.truncate(p.MAX_PLAN_BYTES + 1)  # sparse: nothing is written or read
        self.assertEvidenceError(p.parse_plan_file, path, contains=f"limit {p.MAX_PLAN_BYTES}")

    def test_plan_just_under_50_mib_parses(self):
        template = fixture_plan("resource_added")
        base_change = next(e for e in template["resource_changes"] if e["index"] == "main")
        resource = copy.deepcopy(base_change)
        resource["change"]["before"]["tags"]["padding"] = "p" * 2000
        resource["change"]["after"]["tags"]["padding"] = "p" * 2000
        one = len(json.dumps(resource)) + 2
        count = (p.MAX_PLAN_BYTES - 200_000) // one
        prefix = base_change["address"].rsplit("[", 1)[0]
        changes = []
        for i in range(count):
            r = copy.deepcopy(resource)
            r["address"] = f'{prefix}["r{i:06d}"]'
            r["index"] = f"r{i:06d}"
            changes.append(r)
        plan = minimal_plan(resource_changes=changes, timestamp="2026-10-02T00:00:00Z")
        path = self.write("plan.json", json.dumps(plan))
        size = os.path.getsize(path)
        self.assertGreater(size, 45 * 1024 * 1024)
        self.assertLessEqual(size, p.MAX_PLAN_BYTES)

        start = time.monotonic()
        parsed = p.parse_plan_file(path, 0, "1.14.7")
        elapsed = time.monotonic() - start
        self.assertEqual(len(parsed.resources), count)
        self.assertLess(elapsed, 30, f"parsing {size} bytes took {elapsed:.1f}s")


if __name__ == "__main__":
    unittest.main()
