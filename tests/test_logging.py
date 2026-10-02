"""Tests for structured logging (Task 4.7): src/drift_engine/logs.py and the events
emitted by parser, classifier, comparator and severity.

Run from the repository root:
    pytest tests/test_logging.py
    python3 -m unittest tests.test_logging    (no installation needed)
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from drift_engine import classifier, comparator, logs, parser, severity  # noqa: E402

FIXTURES = os.path.join(ROOT, "tests", "fixtures", "plan_evidence")
SECRET = "s3cr3t-value-never-logged"
PLAIN = "plain-attribute-value-never-logged"


def plan_path(name: str) -> str:
    return os.path.join(FIXTURES, name, "plan.sanitized.json")


def manifest_path(name: str) -> str:
    return os.path.join(FIXTURES, name, "detection_run.json")


def events(records) -> list[str]:
    return [getattr(r, "event", None) for r in records]


def by_event(records, event: str) -> logging.LogRecord:
    (record,) = [r for r in records if getattr(r, "event", None) == event]
    return record


class LoggingTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drift-logs-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(self._reset_logging)

    @staticmethod
    def _reset_logging():
        engine = logging.getLogger(logs.LOGGER_NAME)
        for h in [h for h in engine.handlers if getattr(h, logs._HANDLER_MARK, False)]:
            engine.removeHandler(h)
        engine.setLevel(logging.NOTSET)

    def write(self, name: str, data: dict) -> str:
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return path

    def fixture(self, name: str) -> dict:
        with open(plan_path(name), encoding="utf-8") as fh:
            return json.load(fh)


# ---------------------------------------------------------------------------
# Silent by default
# ---------------------------------------------------------------------------

class TestSilentByDefault(LoggingTestCase):
    def test_package_logger_has_a_null_handler(self):
        handlers = logging.getLogger(logs.LOGGER_NAME).handlers
        self.assertEqual(sum(isinstance(h, logging.NullHandler) for h in handlers), 1)

    def test_nothing_reaches_stderr_without_configuration(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            classifier.evaluate(plan_path("external_drift"))  # also emits a WARNING event
            classifier.evaluate(os.path.join(self.tmp, "missing.json"))
        self.assertEqual(err.getvalue(), "")

    def test_classifier_script_output_unchanged(self):
        bundle = os.path.join(self.tmp, "bundle")
        os.makedirs(bundle)
        shutil.copy(manifest_path("external_drift"), bundle)
        shutil.copy(plan_path("external_drift"), os.path.join(bundle, "plan.json"))
        proc = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "detect_drift.py"), bundle],
                              capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, "")
        self.assertEqual(proc.stdout.splitlines()[0], "has_drift=true  [external_drift=1]")

    def test_logging_does_not_change_the_report(self):
        quiet = classifier.evaluate(plan_path("replace"), manifest_path("replace")).report
        logs.configure_logging("debug", "json", io.StringIO())
        loud = classifier.evaluate(plan_path("replace"), manifest_path("replace")).report
        self.assertEqual(json.dumps(quiet, sort_keys=True), json.dumps(loud, sort_keys=True))


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class TestEvents(LoggingTestCase):
    def test_successful_classification(self):
        with self.assertLogs(logs.LOGGER_NAME, logging.DEBUG) as cm:
            classifier.evaluate(plan_path("external_drift"), manifest_path("external_drift"))
        self.assertEqual(events(cm.records), ["evidence_loaded", "evidence_loaded", "plan_parsed",
                                              "comparison_finished", "severity_rated", "classification_finished"])
        done = by_event(cm.records, "classification_finished")
        self.assertEqual(done.levelno, logging.INFO)
        self.assertEqual(done.name, "drift_engine.classifier")
        self.assertEqual(done.fields, {
            "outcome": "succeeded", "has_drift": True, "resources": 1, "drifted_resources": 1,
            "classification_counts": {"external_drift": 1}, "ambiguous_resources": 0,
            "highest_severity": "LOW", "manifest": True})
        loaded = [r.fields for r in cm.records if r.event == "evidence_loaded"]
        self.assertEqual([f["stage"] for f in loaded], ["manifest", "integrity"])
        self.assertEqual(by_event(cm.records, "plan_parsed").fields["manifest_checks"], True)

    def test_failed_classification(self):
        with self.assertLogs(logs.LOGGER_NAME, logging.DEBUG) as cm:
            classifier.evaluate(os.path.join(self.tmp, "missing.json"), manifest_path("in_sync"))
        failed = by_event(cm.records, "classification_failed")
        self.assertEqual(failed.levelno, logging.WARNING)
        self.assertEqual((failed.fields["source"], failed.fields["stage"], failed.fields["reason"]),
                         ("classifier", "integrity", "missing.json not found"))

    def test_failed_run_manifest(self):
        with self.assertLogs(logs.LOGGER_NAME, logging.WARNING) as cm:
            classifier.evaluate(os.path.join(self.tmp, "absent.json"), manifest_path("failed_run"))
        self.assertEqual(by_event(cm.records, "classification_failed").fields["source"], "detection_run")

    def test_integrity_gate_failure(self):
        plan = self.fixture("external_drift")
        plan["errored"] = True
        with self.assertLogs(logs.LOGGER_NAME, logging.DEBUG) as cm:
            classifier.evaluate(self.write("plan.json", plan))
        self.assertEqual(by_event(cm.records, "integrity_gate_failed").fields, {"violations": 1})
        self.assertIn("errored is true", by_event(cm.records, "classification_failed").fields["reason"])

    def test_missing_manifest_is_a_warning(self):
        with self.assertLogs(logs.LOGGER_NAME, logging.INFO) as cm:
            classifier.evaluate(plan_path("in_sync"))
        warning = by_event(cm.records, "manifest_not_given")
        self.assertEqual((warning.levelno, warning.fields), (logging.WARNING, {"plan": "plan.sanitized.json"}))
        self.assertFalse(by_event(cm.records, "classification_finished").fields["manifest"])

    def test_comparison_and_severity(self):
        plan = self.fixture("replace")
        parsed = parser.parse_plan(plan)
        with self.assertLogs(logs.LOGGER_NAME, logging.DEBUG) as cm:
            comparisons = comparator.compare_plan(parsed, comparator.configured_attributes(plan))
            severity.plan_severity(parsed, comparisons, {parsed.resources[0].address: "config_change"})
        self.assertEqual(by_event(cm.records, "comparison_finished").fields, {
            "resources": 1, "changes": 3, "categories": {"configured": 1, "noise": 2},
            "configuration_evidence": True})
        self.assertEqual(by_event(cm.records, "severity_rated").fields, {
            "resources": 1, "highest": "HIGH", "severities": {"HIGH": 1}, "classification_floors": True})

    def test_records_point_at_the_emitting_module(self):
        with self.assertLogs(logs.LOGGER_NAME, logging.DEBUG) as cm:
            classifier.evaluate(plan_path("in_sync"), manifest_path("in_sync"))
        for record in cm.records:
            self.assertNotEqual(os.path.basename(record.pathname), "logs.py")
        loaded = by_event(cm.records, "classification_finished")
        self.assertEqual((os.path.basename(loaded.pathname), loaded.funcName), ("classifier.py", "evaluate"))
        self.assertEqual(os.path.basename(cm.records[0].pathname), "parser.py")

    def test_every_event_field_is_json_serializable(self):
        with self.assertLogs(logs.LOGGER_NAME, logging.DEBUG) as cm:
            for name in sorted(os.listdir(FIXTURES)):
                ev = classifier.evaluate(plan_path(name), manifest_path(name))
                if ev.parsed is not None:
                    comps = comparator.compare_plan(ev.parsed, comparator.configured_attributes(ev.plan))
                    severity.plan_severity(ev.parsed, comps)
        self.assertTrue(cm.records)
        for record in cm.records:
            self.assertIsInstance(record.event, str)
            json.dumps(record.fields)

    def test_events_are_aggregate_not_per_resource(self):
        with self.assertLogs(logs.LOGGER_NAME, logging.DEBUG) as cm:
            ev = classifier.evaluate(plan_path("external_deletion"), manifest_path("external_deletion"))
            comparator.compare_plan(ev.parsed, comparator.configured_attributes(ev.plan))
        # 2 loads, parsed, compared + rated (for the report), finished, compared again - for 2 resources
        self.assertEqual(len(cm.records), 7)


# ---------------------------------------------------------------------------
# No attribute values in logs
# ---------------------------------------------------------------------------

class TestNoValuesInLogs(LoggingTestCase):
    def test_sensitive_and_plain_values_never_logged(self):
        plan = self.fixture("external_drift")
        for e in plan["resource_drift"] + plan["resource_changes"]:
            for view in ("before", "after"):
                if isinstance(e["change"].get(view), dict):
                    e["change"][view]["tags"]["probe"] = SECRET
                    e["change"][view]["tags"]["owner"] = PLAIN
            e["change"]["after_sensitive"] = {"tags": {"probe": True}}
        plan["resource_drift"][0]["change"]["after"]["tags"].pop("probe")
        plan["resource_drift"][0]["change"]["after"]["tags"]["owner"] = PLAIN + "-changed"
        path = self.write("plan.json", plan)
        for fmt in logs.LOG_FORMATS:
            with self.subTest(fmt):
                stream = io.StringIO()
                logs.configure_logging("debug", fmt, stream)
                ev = classifier.evaluate(path)
                self.assertEqual(ev.report["outcome"], "succeeded")
                comps = comparator.compare_plan(ev.parsed, comparator.configured_attributes(ev.plan))
                severity.plan_severity(ev.parsed, comps)
                text = stream.getvalue()
                self.assertIn("classification_finished", text)
                self.assertNotIn(SECRET, text)
                self.assertNotIn(PLAIN, text)


# ---------------------------------------------------------------------------
# logs.py
# ---------------------------------------------------------------------------

class TestFormatters(LoggingTestCase):
    def record(self, **extra) -> logging.LogRecord:
        record = logging.LogRecord("drift_engine.test", logging.WARNING, __file__, 1, "msg %s", ("arg",), None)
        for k, v in extra.items():
            setattr(record, k, v)
        return record

    def test_json_formatter(self):
        line = logs.JsonFormatter().format(self.record(event="e", fields={"b": 2, "a": [1]}))
        data = json.loads(line)
        self.assertEqual({k: data[k] for k in ("level", "logger", "event", "message", "fields")},
                         {"level": "WARNING", "logger": "drift_engine.test", "event": "e",
                          "message": "msg arg", "fields": {"a": [1], "b": 2}})
        self.assertRegex(data["time"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}\+00:00$")
        self.assertNotIn("\n", line)

    def test_text_formatter(self):
        line = logs.TextFormatter().format(self.record(event="e", fields={"b": "x y", "a": None}))
        self.assertRegex(line, r"^\S+ WARNING drift_engine\.test e: msg arg a=null b=\"x y\"$")

    def test_plain_records_without_event(self):
        record = self.record()
        self.assertEqual(json.loads(logs.JsonFormatter().format(record))["event"], None)
        self.assertRegex(logs.TextFormatter().format(record), r" WARNING drift_engine\.test: msg arg$")

    def test_non_json_values_are_stringified(self):
        line = logs.JsonFormatter().format(self.record(event="e", fields={"obj": object.__name__, "set": {1}}))
        self.assertIn('"set": "{1}"', line)

    def test_exceptions_are_included(self):
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            exc_info = sys.exc_info()
        record = self.record(event="e", fields={})
        record.exc_info = exc_info
        self.assertIn("RuntimeError: boom", json.loads(logs.JsonFormatter().format(record))["exception"])
        self.assertIn("RuntimeError: boom", logs.TextFormatter().format(record))


class TestConfigure(LoggingTestCase):
    def test_level_and_stream(self):
        stream = io.StringIO()
        logs.configure_logging("info", "text", stream)
        log = logging.getLogger("drift_engine.test")
        logs.log_event(log, logging.DEBUG, "hidden", "not shown")
        logs.log_event(log, logging.INFO, "shown", "shown", n=1)
        self.assertNotIn("hidden", stream.getvalue())
        self.assertIn("shown: shown n=1", stream.getvalue())

    def test_reconfiguring_replaces_the_handler(self):
        first, second = io.StringIO(), io.StringIO()
        logs.configure_logging("info", "text", first)
        handler = logs.configure_logging("info", "json", second)
        engine = logging.getLogger(logs.LOGGER_NAME)
        self.assertEqual([h for h in engine.handlers if getattr(h, logs._HANDLER_MARK, False)], [handler])
        logs.log_event(logging.getLogger("drift_engine.x"), logging.INFO, "e", "m")
        self.assertEqual(first.getvalue(), "")
        json.loads(second.getvalue())

    def test_default_stream_is_stderr(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            logs.configure_logging("warning")
            logs.log_event(logging.getLogger("drift_engine.x"), logging.WARNING, "e", "to stderr")
        self.assertIn("to stderr", err.getvalue())

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            logs.configure_logging("verbose")
        with self.assertRaises(ValueError):
            logs.configure_logging("info", "xml")

    def test_disabled_level_builds_no_record(self):
        log = logging.getLogger("drift_engine.quiet")
        log.setLevel(logging.ERROR)
        self.addCleanup(log.setLevel, logging.NOTSET)
        with unittest.mock.patch.object(log, "log") as emit:
            logs.log_event(log, logging.INFO, "e", "m", n=1)
            logs.log_event(log, logging.ERROR, "e", "m", n=1)
        self.assertEqual(emit.call_count, 1)
        self.assertEqual(emit.call_args.kwargs["extra"], {"event": "e", "fields": {"n": 1}})


if __name__ == "__main__":
    unittest.main()
