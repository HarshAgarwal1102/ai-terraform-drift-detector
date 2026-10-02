"""Tests for src/drift_engine/models.py (Task 4.3).

Run from the repository root:
    pytest tests/test_models.py

Requires pydantic (pip install -e ".[dev]"); the tests skip without it, so the
stdlib-only `python3 -m unittest discover -s tests` still runs. Reports under test
are produced by the real classifier (scripts/detect_drift.py) from the committed
fixtures, plus the Task 3.5 sample. The models must accept exactly what
schemas/drift_report.schema.json accepts; the agreement tests check that with
jsonschema (a dev dependency).
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import random
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

try:
    from pydantic import ValidationError

    from drift_engine import models as m
except ImportError:  # pydantic not installed
    m = None
try:
    import jsonschema
except ImportError:
    jsonschema = None

FIXTURE_SOURCE = os.path.join(ROOT, "tests", "fixtures", "plan_evidence")
SCHEMA = os.path.join(ROOT, "schemas", "drift_report.schema.json")
SAMPLE = os.path.join(ROOT, "schemas", "examples", "drift_report.json")

_spec = importlib.util.spec_from_file_location("detect_drift", os.path.join(ROOT, "scripts", "detect_drift.py"))
dd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dd)

REPORTS: dict[str, dict] = {}  # name -> classifier output, built by setUpModule


def as_written(report: dict) -> str:
    """Serialize exactly like scripts/detect_drift.py writes the report."""
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def _bundle(root: str, name: str, manifest: dict, plan: dict | str | None) -> str:
    path = os.path.join(root, name)
    os.makedirs(path)
    with open(os.path.join(path, "detection_run.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh)
    if plan is not None:
        with open(os.path.join(path, "plan.json"), "w", encoding="utf-8") as fh:
            fh.write(plan if isinstance(plan, str) else json.dumps(plan))
    return path


def setUpModule():
    tmp = tempfile.mkdtemp(prefix="drift-models-")
    try:
        for name in sorted(os.listdir(FIXTURE_SOURCE)):
            src = os.path.join(FIXTURE_SOURCE, name)
            with open(os.path.join(src, "detection_run.json"), encoding="utf-8") as fh:
                manifest = json.load(fh)
            plan_path = os.path.join(src, "plan.sanitized.json")
            plan = None
            if os.path.exists(plan_path):
                with open(plan_path, encoding="utf-8") as fh:
                    plan = json.load(fh)
            REPORTS[name] = dd.classify_bundle(_bundle(tmp, name, manifest, plan))

        with open(os.path.join(FIXTURE_SOURCE, "external_drift", "detection_run.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)
        with open(os.path.join(FIXTURE_SOURCE, "external_drift", "plan.sanitized.json"), encoding="utf-8") as fh:
            base = json.load(fh)

        sensitive = copy.deepcopy(base)
        for e in sensitive["resource_drift"] + sensitive["resource_changes"]:
            e["change"]["after_sensitive"] = {"tags": {"probe": True}}
        # A nested block (a list in plan JSON) with one sensitive field that changed outside Terraform.
        sensitive_block = copy.deepcopy(base)
        for e in sensitive_block["resource_drift"] + sensitive_block["resource_changes"]:
            for view in ("before", "after"):
                e["change"][view]["site_config"] = [{"name": "cfg", "password": "S3CRET-STATE"}]
            e["change"]["before_sensitive"] = e["change"]["after_sensitive"] = {"site_config": [{"password": True}]}
        sensitive_block["resource_drift"][0]["change"]["after"]["site_config"][0]["password"] = "S3CRET-REAL"
        unknown = copy.deepcopy(base)
        unknown["resource_changes"][0]["change"]["after_unknown"] = {"tags": True}
        null_value = copy.deepcopy(base)
        null_value["resource_drift"][0]["change"]["after"]["tags"]["probe"] = None

        variants = {
            "sensitive": (manifest, sensitive),
            "sensitive_block": (manifest, sensitive_block),
            "unknown_value": (manifest, unknown),
            "null_value": (manifest, null_value),
            "missing_plan": (manifest, None),
            "truncated_plan": (manifest, json.dumps(base)[:300]),
            "exit_code_mismatch": (dict(manifest, plan_exit_code=0), base),
            "rejected_manifest": (dict(manifest, outcome="unexpected"), base),
        }
        for name, (man, plan) in variants.items():
            REPORTS[name] = dd.classify_bundle(_bundle(tmp, name, man, plan))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    with open(SAMPLE, encoding="utf-8") as fh:
        REPORTS["schema_sample"] = json.load(fh)


def report(name: str) -> dict:
    return copy.deepcopy(REPORTS[name])


def drift_item(name: str = "external_drift") -> dict:
    return report(name)["resources"][0]


@unittest.skipIf(m is None, "pydantic is not installed (pip install -e '.[dev]')")
class ModelTestCase(unittest.TestCase):
    def assertRejected(self, model, data):
        with self.assertRaises(ValidationError):
            model.model_validate(data)


# ---------------------------------------------------------------------------
# Real reports: load and round-trip
# ---------------------------------------------------------------------------

class TestRealReports(ModelTestCase):
    def test_reports_cover_both_outcomes(self):
        outcomes = {r["outcome"] for r in REPORTS.values()}
        self.assertEqual(outcomes, {"succeeded", "failed"})

    def test_every_report_validates_from_python(self):
        for name in REPORTS:
            with self.subTest(name):
                self.assertIsInstance(m.DriftReport.model_validate(report(name)), m.DriftReport)

    def test_json_round_trip_is_byte_identical(self):
        for name in REPORTS:
            with self.subTest(name):
                text = as_written(REPORTS[name])
                model = m.DriftReport.model_validate_json(text)
                self.assertEqual(as_written(model.model_dump(mode="json")), text)

    def test_sample_file_round_trip(self):
        with open(SAMPLE, encoding="utf-8") as fh:
            text = fh.read()
        model = m.DriftReport.model_validate_json(text)
        self.assertEqual(as_written(model.model_dump(mode="json")), text)

    def test_model_dump_json_round_trip(self):
        for name in REPORTS:
            with self.subTest(name):
                model = m.DriftReport.model_validate(report(name))
                again = m.DriftReport.model_validate_json(model.model_dump_json())
                self.assertEqual(again, model)
                self.assertEqual(json.loads(model.model_dump_json()), REPORTS[name])

    def test_redacted_block_report(self):
        self.assertNotIn("S3CRET", json.dumps(REPORTS["sensitive_block"]))
        r = m.DriftReport.model_validate(report("sensitive_block"))
        [change] = [c for c in r.resources[0].attribute_changes if c.attribute == "site_config"]
        self.assertTrue(change.redacted)
        self.assertEqual({change.state.status, change.real.status, change.desired.status}, {"redacted"})
        # A redacted change keeps its deterministic rating: it cannot be read, so it is HIGH.
        self.assertEqual((change.severity.level, change.severity.rules), ("HIGH", ["sensitive-value"]))

    def test_severity_typed_access(self):
        r = m.DriftReport.model_validate(report("external_deletion"))
        self.assertEqual(r.summary.highest_severity, "HIGH")
        self.assertEqual(r.summary.severity_counts, {"HIGH": 1, "INFO": 1})
        deleted = next(x for x in r.resources if x.classification == "external_deletion")
        self.assertEqual(deleted.severity.level, "HIGH")
        self.assertTrue(all(c.assessment.category in ("configured", "unconfigured", "noise", "undetermined")
                            for c in deleted.attribute_changes))

    def test_typed_access(self):
        r = m.DriftReport.model_validate(report("external_drift"))
        self.assertIs(r.has_drift, True)
        self.assertEqual(r.summary.classification_counts, {"external_drift": 1})
        item = r.resources[0]
        self.assertIsInstance(item, m.DriftItem)
        self.assertEqual(item.classification, "external_drift")
        change = item.attribute_changes[0]
        self.assertIsInstance(change, m.AttributeChange)
        self.assertEqual(change.path, ["tags", "probe"])
        self.assertEqual(change.class_, "drifted")
        self.assertEqual(change.state, m.ValueView(status="value", value="1"))
        self.assertEqual(change.real, m.StatusView(status="absent"))

    def test_failed_report_keeps_drift_unknown(self):
        for name in ("failed_run", "missing_plan", "truncated_plan", "exit_code_mismatch", "rejected_manifest"):
            with self.subTest(name):
                r = m.DriftReport.model_validate(report(name))
                self.assertEqual(r.outcome, "failed")
                self.assertIsNone(r.has_drift)
                self.assertIsNotNone(r.failure)
                self.assertIsNone(r.summary)


# ---------------------------------------------------------------------------
# View values: value / null / absent / unknown / redacted
# ---------------------------------------------------------------------------

class TestViewValues(ModelTestCase):
    def _change(self, name: str) -> m.AttributeChange:
        return m.DriftReport.model_validate(report(name)).resources[0].attribute_changes[0]

    def test_null_is_a_value_not_absence(self):
        change = self._change("null_value")
        self.assertEqual(change.real, m.ValueView(status="value", value=None))
        self.assertEqual(change.model_dump(mode="json")["real"], {"status": "value", "value": None})

    def test_unknown_value(self):
        change = m.DriftReport.model_validate(report("unknown_value")).resources[0].attribute_changes
        self.assertTrue(any(c.desired == m.StatusView(status="unknown") for c in change))

    def test_redacted_value_is_never_emitted(self):
        r = m.DriftReport.model_validate(report("sensitive"))
        change = r.resources[0].attribute_changes[0]
        self.assertTrue(change.redacted)
        for view in (change.state, change.real, change.desired):
            self.assertIn(view.status, ("redacted", "absent"))
        self.assertNotIn('"1"', r.model_dump_json().split('"attribute_changes"')[1].split('"attributes"')[0])

    def test_status_view_has_no_value_key(self):
        self.assertEqual(m.StatusView(status="absent").model_dump(), {"status": "absent"})

    def test_value_view_requires_value(self):
        self.assertRejected(m.ValueView, {"status": "value"})

    def test_status_view_rejects_value(self):
        for status in ("absent", "unknown", "redacted"):
            with self.subTest(status):
                self.assertRejected(m.StatusView, {"status": status, "value": "secret"})

    def test_json_values_of_every_type(self):
        for value in ("s", 1, 1.5, True, None, [1, "a"], {"k": {"n": [None]}}):
            with self.subTest(value=value):
                v = m.ValueView.model_validate({"status": "value", "value": value})
                self.assertEqual(v.model_dump(mode="json"), {"status": "value", "value": value})


# ---------------------------------------------------------------------------
# Strict typing
# ---------------------------------------------------------------------------

def _set(obj: dict, path: tuple, value) -> dict:
    target = obj
    for key in path[:-1]:
        target = target[key]
    if value is _DELETE:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return obj


_DELETE = object()
R0 = ("resources", 0)
AC0 = R0 + ("attribute_changes", 0)

# (base report, path, replacement): every one must be rejected by the models and the schema.
INVALID = {
    "has_drift string": ("external_drift", ("has_drift",), "true"),
    "has_drift int": ("external_drift", ("has_drift",), 1),
    "version 1 (pre-severity)": ("external_drift", ("classification_version",), "1"),
    "version 3": ("external_drift", ("classification_version",), "3"),
    "version int": ("external_drift", ("classification_version",), 1),
    "unknown outcome": ("external_drift", ("outcome",), "partial"),
    "extra top-level field": ("external_drift", ("header",), {}),
    "missing summary field": ("external_drift", ("summary", "resources_total"), _DELETE),
    "count as string": ("external_drift", ("summary", "resources_total"), "1"),
    "count as bool": ("external_drift", ("summary", "drifted_resources"), True),
    "count as float": ("external_drift", ("summary", "drifted_resources"), 1.5),
    "negative count": ("external_drift", ("summary", "ambiguous_resources"), -1),
    "unknown class in counts": ("external_drift", ("summary", "classification_counts", "drifty"), 1),
    "summary flag as int": ("external_drift", ("summary", "output_only_change"), 0),
    "plan errored": ("external_drift", ("plan", "errored"), True),
    "plan incomplete": ("external_drift", ("plan", "complete"), False),
    "plan errored as 0": ("external_drift", ("plan", "errored"), 0),
    "plan exit code string": ("external_drift", ("run", "plan_exit_code"), "2"),
    "plan exit code bool": ("external_drift", ("run", "plan_exit_code"), True),
    "run extra field": ("external_drift", ("run", "subscription_id"), "x"),
    "missing address": ("external_drift", R0 + ("address",), _DELETE),
    "empty address": ("external_drift", R0 + ("address",), ""),
    "missing type": ("external_drift", R0 + ("type",), _DELETE),
    "null type": ("external_drift", R0 + ("type",), None),
    "missing action": ("external_drift", R0 + ("action",), _DELETE),
    "unknown action": ("external_drift", R0 + ("action",), "patch"),
    "unknown classification": ("external_drift", R0 + ("classification",), "drifted"),
    "data mode": ("external_drift", R0 + ("mode",), "data"),
    "empty actions": ("external_drift", R0 + ("actions",), []),
    "actions not strings": ("external_drift", R0 + ("actions",), [1]),
    "index bool": ("external_drift", R0 + ("index",), True),
    "index float": ("external_drift", R0 + ("index",), 1.5),
    "importing null": ("external_drift", R0 + ("importing",), None),
    "notes not strings": ("external_drift", R0 + ("notes",), [None]),
    "missing attribute_changes": ("external_drift", R0 + ("attribute_changes",), _DELETE),
    "attribute class unknown": ("external_drift", R0 + ("attributes", 0, "class"), "changed"),
    "attribute class null": ("external_drift", R0 + ("attributes", 0, "class"), None),
    "empty path": ("external_drift", AC0 + ("path",), []),
    "path not strings": ("external_drift", AC0 + ("path",), ["tags", 0]),
    "change class unknown": ("external_drift", AC0 + ("class",), "resource_added"),
    "change class key renamed": ("external_drift", AC0 + ("class_",), "drifted"),
    "redacted as string": ("external_drift", AC0 + ("redacted",), "false"),
    "value view without value": ("external_drift", AC0 + ("state",), {"status": "value"}),
    "absent view with value": ("external_drift", AC0 + ("real",), {"status": "absent", "value": "1"}),
    "redacted view with value": ("external_drift", AC0 + ("real",), {"status": "redacted", "value": "s"}),
    "unknown view status": ("external_drift", AC0 + ("real",), {"status": "hidden"}),
    "view not object": ("external_drift", AC0 + ("real",), "absent"),
    "resource type count zero": ("external_drift", ("resource_types", 0, "resource_count"), 0),
    "resource type no addresses": ("external_drift", ("resource_types", 0, "addresses"), []),
    "output actions empty": ("external_drift", ("output_changes", 0, "actions"), []),
    "succeeded without summary": ("external_drift", ("summary",), None),
    "succeeded without plan": ("external_drift", ("plan",), None),
    "succeeded without run": ("external_drift", ("run",), None),
    "succeeded with unknown drift": ("external_drift", ("has_drift",), None),
    "succeeded with failure": ("external_drift", ("failure",), {"source": "classifier", "stage": None, "reason": None}),
    "failed reported as no drift": ("failed_run", ("has_drift",), False),
    "failed without failure": ("failed_run", ("failure",), None),
    "failure source unknown": ("failed_run", ("failure", "source"), "terraform"),
    # Deterministic severity (classification_version 2, Task 6.2A)
    "resource severity missing": ("external_drift", R0 + ("severity",), _DELETE),
    "resource severity unknown level": ("external_drift", R0 + ("severity", "level"), "SEVERE"),
    "resource severity lowercase": ("external_drift", R0 + ("severity", "level"), "low"),
    "resource severity extra field": ("external_drift", R0 + ("severity", "score"), 3),
    "severity reasons not strings": ("external_drift", R0 + ("severity", "reasons"), [1]),
    "change severity missing": ("external_drift", AC0 + ("severity",), _DELETE),
    "change severity null": ("external_drift", AC0 + ("severity",), None),
    "change severity rules not list": ("external_drift", AC0 + ("severity", "rules"), "tags"),
    "assessment missing": ("external_drift", AC0 + ("assessment",), _DELETE),
    "assessment unknown category": ("external_drift", AC0 + ("assessment", "category"), "ignored"),
    "assessment noise rule int": ("external_drift", AC0 + ("assessment", "noise_rule"), 1),
    "highest severity missing": ("external_drift", ("summary", "highest_severity"), _DELETE),
    "highest severity unknown": ("external_drift", ("summary", "highest_severity"), "NONE"),
    "severity count unknown level": ("external_drift", ("summary", "severity_counts", "SEVERE"), 1),
    "severity count negative": ("external_drift", ("summary", "severity_counts", "LOW"), -1),
    "severity count as string": ("external_drift", ("summary", "severity_counts", "LOW"), "1"),
}


class TestStrictTypes(ModelTestCase):
    def test_invalid_reports_rejected(self):
        for name, (base, path, value) in INVALID.items():
            with self.subTest(name):
                self.assertRejected(m.DriftReport, _set(report(base), path, value))

    def test_failed_report_with_results_rejected(self):
        for field in ("resources", "resource_types", "output_changes"):
            with self.subTest(field):
                bad = report("failed_run")
                bad[field] = copy.deepcopy(REPORTS["external_drift"][field])
                self.assertRejected(m.DriftReport, bad)

    def test_failed_report_with_summary_rejected(self):
        bad = report("failed_run")
        bad["summary"] = copy.deepcopy(REPORTS["external_drift"]["summary"])
        self.assertRejected(m.DriftReport, bad)

    def test_no_coercion_from_json_either(self):
        text = as_written(_set(report("external_drift"), ("summary", "resources_total"), "1"))
        with self.assertRaises(ValidationError):
            m.DriftReport.model_validate_json(text)

    def test_drift_item_requires_core_fields(self):
        for field in ("address", "type", "action", "attribute_changes", "classification"):
            with self.subTest(field):
                item = drift_item()
                del item[field]
                self.assertRejected(m.DriftItem, item)

    def test_models_are_immutable(self):
        r = m.DriftReport.model_validate(report("external_drift"))
        with self.assertRaises(ValidationError):
            r.has_drift = False
        with self.assertRaises(ValidationError):
            r.resources[0].classification = "in_sync"

    def test_build_by_field_name_and_serialize_as_class(self):
        change = m.AttributeChange(
            path=["tags", "owner"], attribute="tags", class_="drifted",
            state={"status": "absent"}, real={"status": "value", "value": "a"},
            desired={"status": "absent"}, redacted=False,
            severity={"level": "LOW", "rules": ["tags"]},
            assessment={"category": "configured", "noise_rule": None},
        )
        dumped = change.model_dump()
        self.assertEqual(dumped["class"], "drifted")
        self.assertNotIn("class_", dumped)
        self.assertEqual(m.AttributeChange.model_validate(dumped), change)

    def test_summary_model(self):
        s = m.DriftSummary.model_validate(report("external_deletion")["summary"])
        self.assertEqual(s.classification_counts, {"external_deletion": 1, "in_sync": 1})
        self.assertEqual(s.drifted_resources, 1)


# ---------------------------------------------------------------------------
# Agreement with schemas/drift_report.schema.json
# ---------------------------------------------------------------------------

@unittest.skipIf(jsonschema is None, "jsonschema is not installed (pip install -e '.[dev]')")
class TestSchemaAgreement(ModelTestCase):
    @classmethod
    def setUpClass(cls):
        with open(SCHEMA, encoding="utf-8") as fh:
            cls.validator = jsonschema.Draft202012Validator(json.load(fh))

    def verdicts(self, data) -> tuple[bool, bool]:
        try:
            m.DriftReport.model_validate(data)
            model_ok = True
        except ValidationError:
            model_ok = False
        return model_ok, self.validator.is_valid(data)

    def test_valid_reports_valid_for_both(self):
        for name in REPORTS:
            with self.subTest(name):
                self.assertEqual(self.verdicts(report(name)), (True, True))

    def test_invalid_reports_invalid_for_both(self):
        for name, (base, path, value) in INVALID.items():
            with self.subTest(name):
                self.assertEqual(self.verdicts(_set(report(base), path, value)), (False, False))

    def test_random_mutations_agree(self):
        # Floats with no fraction (1.0) are left out: JSON Schema counts them as integers,
        # the strict models do not. That is the one deliberate difference.
        replacements = (None, True, False, 0, 1, -1, 1.5, "", "x", "1", "drifted", "update",
                        [], ["x"], [1], {}, {"status": "absent"}, {"status": "value"})
        rng = random.Random(4303)
        names = sorted(REPORTS)
        disagreements = []
        tally = {True: 0, False: 0}
        for _ in range(3000):
            data = report(rng.choice(names))
            paths = list(_paths(data))
            for _ in range(rng.randint(1, 2)):
                path = rng.choice(paths)
                try:
                    if rng.random() < 0.2 and isinstance(_get(data, path[:-1]), dict):
                        _set(data, path, _DELETE)
                    else:
                        _set(data, path, copy.deepcopy(rng.choice(replacements)))
                except (KeyError, IndexError, TypeError):
                    continue  # path removed by an earlier mutation
            model_ok, schema_ok = self.verdicts(data)
            tally[model_ok] += 1
            if model_ok != schema_ok:
                disagreements.append(data)
        self.assertEqual(disagreements[:1], [])
        self.assertGreater(tally[True], 0)
        self.assertGreater(tally[False], 0)


def _get(obj, path):
    for key in path:
        obj = obj[key]
    return obj


def _paths(node, path=()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield path + (k,)
            yield from _paths(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield path + (i,)
            yield from _paths(v, path + (i,))


if __name__ == "__main__":
    unittest.main()
