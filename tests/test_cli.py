"""Tests for the drift-engine CLI and formatters (Task 4.6).

Run from the repository root:
    pytest tests/test_cli.py

Requires the package with its dependencies (pip install -e ".[dev]"); skipped
otherwise, so the stdlib-only `python3 -m unittest discover -s tests` still runs.
Inputs are the committed real-evidence fixtures plus synthetic variants.
"""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import logging
import os
import runpy
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from importlib.metadata import PackageNotFoundError, entry_points, version
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

try:
    import yaml

    from drift_engine import cli, comparator, formatters, severity
    from drift_engine.classifier import evaluate
    from drift_engine.models import DriftReport
except ImportError:  # pydantic / PyYAML not installed
    cli = None
try:
    import jsonschema
except ImportError:
    jsonschema = None

FIXTURES = os.path.join(ROOT, "tests", "fixtures", "plan_evidence")
SCHEMA = os.path.join(ROOT, "schemas", "drift_report.schema.json")
ANSI = "\033["

_spec = importlib.util.spec_from_file_location("detect_drift", os.path.join(ROOT, "scripts", "detect_drift.py"))
dd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dd)


def fixture_names(with_plan: bool = True) -> list[str]:
    return sorted(
        n for n in os.listdir(FIXTURES)
        if not with_plan or os.path.exists(os.path.join(FIXTURES, n, "plan.sanitized.json"))
    )


def plan_path(name: str) -> str:
    return os.path.join(FIXTURES, name, "plan.sanitized.json")


def manifest_path(name: str) -> str:
    return os.path.join(FIXTURES, name, "detection_run.json")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


@unittest.skipIf(cli is None, "pydantic/PyYAML not installed (pip install -e '.[dev]')")
class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drift-cli-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(self._reset_logging)

    @staticmethod
    def _reset_logging():
        """--log-level configures the global drift_engine logger; undo it after each test."""
        engine = logging.getLogger("drift_engine")
        for h in [h for h in engine.handlers if getattr(h, "_drift_engine_handler", False)]:
            engine.removeHandler(h)
        engine.setLevel(logging.NOTSET)

    def run_cli(self, *args: str, env: dict | None = None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.dict(os.environ, env or {}):
            try:
                code = cli.main(list(args))
            except SystemExit as exc:  # argparse
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def write_plan(self, name: str, plan: dict) -> str:
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(plan, fh)
        return path

    def load_fixture_plan(self, name: str) -> dict:
        with open(plan_path(name), encoding="utf-8") as fh:
            return json.load(fh)


# ---------------------------------------------------------------------------
# Acceptance: drift-engine analyze --plan plan.json --output report.json
# ---------------------------------------------------------------------------

class TestAnalyzeToFile(CliTestCase):
    def test_every_fixture_produces_a_valid_report(self):
        for name in fixture_names():
            with self.subTest(name):
                out = os.path.join(self.tmp, f"{name}.json")
                code, stdout, stderr = self.run_cli("analyze", "--plan", plan_path(name), "--output", out)
                self.assertEqual(code, 0, stderr)
                with open(out, encoding="utf-8") as fh:
                    text = fh.read()
                report = DriftReport.model_validate_json(text)
                self.assertEqual(report.outcome, "succeeded")
                self.assertEqual(text, json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n")
                self.assertIn(f"Report: {out}", stdout)
                self.assertIn("has_drift=", stdout)
                self.assertIn("WARNING: no --manifest", stderr)

    def test_summary_line(self):
        out = os.path.join(self.tmp, "r.json")
        _, stdout, _ = self.run_cli("analyze", "--plan", plan_path("external_drift"),
                                    "--manifest", manifest_path("external_drift"), "--output", out)
        self.assertEqual(stdout.splitlines()[0], "has_drift=true  [external_drift=1]  severity=LOW")

    def test_with_manifest_matches_the_classifier_script_byte_for_byte(self):
        for name in fixture_names(with_plan=False):
            with self.subTest(name):
                bundle = os.path.join(self.tmp, f"bundle-{name}")
                os.makedirs(bundle)
                shutil.copy(manifest_path(name), bundle)
                plan = os.path.join(bundle, "plan.json")
                if os.path.exists(plan_path(name)):
                    shutil.copy(plan_path(name), plan)
                out = os.path.join(self.tmp, f"{name}.json")
                code, _, _ = self.run_cli("analyze", "--plan", plan, "--manifest",
                                          os.path.join(bundle, "detection_run.json"), "--output", out)
                script_out = os.path.join(self.tmp, f"{name}.script.json")
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    script_code = dd.main([bundle, "--output", script_out])
                self.assertEqual(code, script_code)
                with open(out, "rb") as a, open(script_out, "rb") as b:
                    self.assertEqual(a.read(), b.read())

    @unittest.skipIf(jsonschema is None, "jsonschema not installed")
    def test_reports_validate_against_the_schema(self):
        with open(SCHEMA, encoding="utf-8") as fh:
            validator = jsonschema.Draft202012Validator(json.load(fh))
        for name in fixture_names(with_plan=False):
            for manifest in (None, manifest_path(name)):
                with self.subTest(name=name, manifest=bool(manifest)):
                    args = ["analyze", "--plan", plan_path(name)] + (["--manifest", manifest] if manifest else [])
                    _, stdout, _ = self.run_cli(*args)
                    validator.validate(json.loads(stdout))

    def test_report_contract_unchanged(self):
        _, stdout, _ = self.run_cli("analyze", "--plan", plan_path("external_drift"))
        report = json.loads(stdout)
        self.assertEqual(set(report), {
            "classification_version", "outcome", "has_drift", "failure", "run", "plan", "summary",
            "resources", "resource_types", "output_changes"})
        # classification_version 2 (Task 6.2A): deterministic severity is part of the report.
        self.assertEqual(report["classification_version"], "2")
        self.assertEqual(report["resources"][0]["severity"], {"level": "LOW", "reasons": ["tags.probe: tags"]})
        self.assertEqual(report["summary"]["highest_severity"], "LOW")

    def test_console_ratings_match_report_severity(self):
        # The console view rates the plan itself (same function, same evidence); it must
        # agree with the severity the report carries.
        for name in fixture_names():
            with self.subTest(name):
                evaluation = evaluate(plan_path(name), manifest_path(name))
                comparisons = comparator.compare_plan(evaluation.parsed,
                                                      comparator.configured_attributes(evaluation.plan))
                classes = {r["address"]: r["classification"] for r in evaluation.report["resources"]}
                rated = severity.plan_severity(evaluation.parsed, comparisons, classes)
                for resource, rating in zip(evaluation.report["resources"], rated, strict=True):
                    self.assertEqual(resource["severity"], {"level": rating.severity, "reasons": list(rating.reasons)})
                    self.assertEqual([ch["severity"]["level"] for ch in resource["attribute_changes"]],
                                     [ch.severity for ch in rating.changes])


class TestPlanOnlyMode(CliTestCase):
    def test_run_is_all_null_and_warned(self):
        code, stdout, stderr = self.run_cli("analyze", "--plan", plan_path("in_sync"))
        self.assertEqual(code, 0)
        self.assertEqual(set(json.loads(stdout)["run"].values()), {None})
        self.assertIn("exit-code and Terraform-version checks are skipped", stderr)

    def test_other_integrity_checks_still_apply(self):
        plan = self.load_fixture_plan("external_drift")
        plan["errored"] = True
        code, stdout, stderr = self.run_cli("analyze", "--plan", self.write_plan("plan.json", plan))
        report = json.loads(stdout)
        self.assertEqual((code, report["outcome"], report["has_drift"]), (1, "failed", None))
        self.assertIn("errored is true", report["failure"]["reason"])
        self.assertIn("Drift status is UNKNOWN", stderr)

    def test_manifest_checks_apply_when_given(self):
        manifest = json.loads(read(manifest_path("external_drift")))
        manifest["plan_exit_code"] = 0  # contradicts the pending change in the plan
        path = os.path.join(self.tmp, "detection_run.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh)
        code, stdout, _ = self.run_cli("analyze", "--plan", plan_path("external_drift"), "--manifest", path)
        self.assertEqual(code, 1)
        self.assertIn("plan exit 0 but plan.json contains", json.loads(stdout)["failure"]["reason"])


# ---------------------------------------------------------------------------
# Failure handling: drift status unknown, never "no drift"
# ---------------------------------------------------------------------------

class TestFailures(CliTestCase):
    def test_failed_run_manifest(self):
        out = os.path.join(self.tmp, "r.json")
        code, stdout, stderr = self.run_cli("analyze", "--plan", os.path.join(self.tmp, "absent.json"),
                                            "--manifest", manifest_path("failed_run"), "--output", out)
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")  # no success summary
        report = json.loads(read(out))
        self.assertEqual((report["outcome"], report["has_drift"]), ("failed", None))
        self.assertEqual(report["failure"]["source"], "detection_run")
        self.assertIn("CLASSIFICATION FAILED [detection_run/plan]", stderr)

    def test_missing_and_invalid_plan(self):
        bad = os.path.join(self.tmp, "bad.json")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        for path, reason in ((os.path.join(self.tmp, "missing.json"), "missing.json not found"),
                             (bad, "bad.json is not valid JSON")):
            for fmt in formatters.FORMATS:
                with self.subTest(path=path, fmt=fmt):
                    code, stdout, _ = self.run_cli("analyze", "--plan", path, "--format", fmt)
                    self.assertEqual(code, 1)
                    self.assertIn(reason, stdout)
                    if fmt == "console":
                        self.assertIn("FAILED: drift status UNKNOWN", stdout)
                        self.assertNotIn("none detected", stdout)
                    else:
                        loaded = json.loads(stdout) if fmt == "json" else yaml.safe_load(stdout)
                        self.assertIsNone(loaded["has_drift"])

    def test_unwritable_output(self):
        code, _, stderr = self.run_cli("analyze", "--plan", plan_path("in_sync"),
                                       "--output", os.path.join(self.tmp, "no", "such", "dir", "r.json"))
        self.assertEqual(code, cli.EXIT_CANT_WRITE)
        self.assertIn("cannot write", stderr)

    def test_contract_violation_writes_nothing(self):
        from drift_engine.classifier import Evaluation
        broken = Evaluation({"outcome": "succeeded"}, None, None)
        with mock.patch.object(cli, "evaluate", return_value=broken):
            code, stdout, stderr = self.run_cli("analyze", "--plan", plan_path("in_sync"))
        self.assertEqual((code, stdout), (cli.EXIT_CONTRACT_VIOLATION, ""))
        self.assertIn("does not satisfy the report contract", stderr)

    def test_malformed_identity_fields_fail_the_integrity_gate(self):
        # Before the gate checked identity fields, these reached the classifier and broke
        # the report contract (exit 70). Now they are rejected evidence: a failed report.
        cases = (("name", None, "non-string name"), ("type", 0, "non-string type"),
                 ("provider_name", [], "non-string provider_name"), ("index", True, "index that is not"),
                 ("address", "", "empty address"), ("mode", "unmanaged", "mode other than"))
        for field, value, reason in cases:
            with self.subTest(field=field):
                plan = self.load_fixture_plan("external_drift")
                for e in plan["resource_drift"] + plan["resource_changes"]:
                    e[field] = value
                out = os.path.join(self.tmp, f"{field}.json")
                code, stdout, stderr = self.run_cli("analyze", "--plan", self.write_plan("plan.json", plan),
                                                    "--output", out)
                self.assertEqual(code, cli.EXIT_FAILED)
                self.assertEqual(stdout, "")
                report = json.loads(read(out))
                self.assertEqual((report["outcome"], report["has_drift"]), ("failed", None))
                self.assertEqual(report["failure"]["stage"], "integrity")
                self.assertIn(reason, report["failure"]["reason"])
                self.assertIn("Drift status is UNKNOWN", stderr)

    def test_usage_errors(self):
        for args in ([], ["analyze"], ["analyze", "--plan", "p", "--format", "xml"],
                     ["analyze", "--plan", "p", "--color", "rainbow"], ["unknown"]):
            with self.subTest(args=args):
                code, _, stderr = self.run_cli(*args)
                self.assertEqual(code, cli.EXIT_USAGE)
                self.assertIn("error:", stderr)


# ---------------------------------------------------------------------------
# Formats
# ---------------------------------------------------------------------------

class TestFormats(CliTestCase):
    def test_json_is_default_and_goes_to_stdout(self):
        code, stdout, _ = self.run_cli("analyze", "--plan", plan_path("external_drift"))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout)["has_drift"], True)

    def test_yaml_equals_json(self):
        for name in fixture_names():
            with self.subTest(name):
                args = ["analyze", "--plan", plan_path(name), "--manifest", manifest_path(name)]
                _, as_json, _ = self.run_cli(*args)
                _, as_yaml, _ = self.run_cli(*args, "--format", "yaml")
                self.assertEqual(yaml.safe_load(as_yaml), json.loads(as_json))

    def test_yaml_quotes_ambiguous_strings(self):
        report = {"a": "yes", "b": "1", "c": "null", "d": "on", "e": "2026-10-01", "f": "x: y", "g": ""}
        self.assertEqual(yaml.safe_load(formatters.render_yaml(report)), report)

    def test_output_is_deterministic(self):
        for fmt in formatters.FORMATS:
            with self.subTest(fmt):
                args = ["analyze", "--plan", plan_path("external_deletion"), "--format", fmt]
                self.assertEqual(self.run_cli(*args)[1], self.run_cli(*args)[1])

    def test_format_to_file(self):
        for fmt in formatters.FORMATS:
            with self.subTest(fmt):
                out = os.path.join(self.tmp, f"r.{fmt}")
                _, stdout_text, _ = self.run_cli("analyze", "--plan", plan_path("replace"), "--format", fmt)
                code, _, _ = self.run_cli("analyze", "--plan", plan_path("replace"), "--format", fmt, "--output", out)
                self.assertEqual(code, 0)
                with open(out, encoding="utf-8") as fh:
                    self.assertEqual(fh.read(), stdout_text)

    def test_unknown_format_in_render(self):
        with self.assertRaises(ValueError):
            formatters.render("xml", {})


# ---------------------------------------------------------------------------
# Console view
# ---------------------------------------------------------------------------

class TestConsole(CliTestCase):
    def console(self, name: str, *extra: str) -> str:
        code, stdout, _ = self.run_cli("analyze", "--plan", plan_path(name), "--manifest", manifest_path(name),
                                       "--format", "console", *extra)
        self.assertIn(code, (0, 1))
        return stdout

    def test_external_drift(self):
        text = self.console("external_drift")
        for expected in ("Outcome     succeeded", "Drift       DETECTED: 1 of 1 resources drifted",
                         "Severity    LOW", "external_drift  update",
                         'module.resource_group.azurerm_resource_group.this["main"]',
                         "tags.probe  drifted  configured  LOW  (tags)",
                         'state: "1"   real: (absent)   desired: "1"', "Run         environment dev"):
            self.assertIn(expected, text)

    def test_in_sync(self):
        text = self.console("in_sync")
        self.assertIn("Drift       none detected", text)
        self.assertIn("Severity    INFO", text)
        self.assertNotIn("Resources with changes", text)
        self.assertIn("In sync     1 resource(s) without changes", text)

    def test_noise_listed_not_hidden_and_floor_explained(self):
        text = self.console("replace")
        self.assertIn("Severity    HIGH", text)
        self.assertIn("noise (INFO): id [computed-id], managed_by [replace-unset-optional]", text)
        self.assertIn("severity: planned replace destroys and recreates the object", text)
        self.assertIn("location  config_changed  configured  MEDIUM", text)
        self.assertIn("Outputs     resource_groups: update", text)

    def test_external_deletion(self):
        text = self.console("external_deletion")
        self.assertIn("HIGH      external_deletion  create", text)
        self.assertIn("severity: resource deleted outside Terraform", text)

    def test_console_severity_matches_severity_module(self):
        for name in fixture_names():
            with self.subTest(name):
                text = self.console(name)
                from drift_engine import classifier, comparator
                ev = classifier.evaluate(plan_path(name), manifest_path(name))
                classes = {r["address"]: r["classification"] for r in ev.report["resources"]}
                rated = severity.plan_severity(ev.parsed, comparator.compare_plan(
                    ev.parsed, comparator.configured_attributes(ev.plan)), classes)
                top = severity.highest(r.severity for r in rated)
                self.assertIn(f"Severity    {top} (highest", text)

    def test_resources_sorted_by_severity(self):
        # external deletion (HIGH) at an address that sorts after a LOW tag drift
        plan = self.load_fixture_plan("external_deletion")
        for e in plan["resource_drift"] + plan["resource_changes"]:
            if e["index"] == "ghost":
                e["address"], e["index"] = e["address"].replace('"ghost"', '"zzz"'), "zzz"
        main = next(e for e in plan["resource_changes"] if e["index"] == "main")
        drift = copy.deepcopy(main)
        drift["change"]["actions"] = ["update"]
        drift["change"]["before"] = copy.deepcopy(main["change"]["before"])
        drift["change"]["before"]["tags"]["probe"] = "1"
        plan["resource_drift"].append(drift)
        _, text, _ = self.run_cli("analyze", "--plan", self.write_plan("plan.json", plan), "--format", "console")
        rows = [line for line in text.splitlines() if "azurerm_resource_group.this[" in line]
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0].startswith("HIGH") and 'this["zzz"]' in rows[0], rows)
        self.assertTrue(rows[1].startswith("LOW") and 'this["main"]' in rows[1], rows)

    def test_failed_console(self):
        text = self.console("failed_run")
        self.assertIn('FAILED: drift status UNKNOWN (must not be treated as "no drift")', text)
        self.assertNotIn("Severity", text)
        self.assertNotIn("In sync", text)

    def test_plan_only_run_line(self):
        _, text, _ = self.run_cli("analyze", "--plan", plan_path("in_sync"), "--format", "console")
        self.assertIn("Run         no run manifest: plan exit-code and Terraform-version checks were skipped", text)

    def test_sensitive_values_never_printed(self):
        plan = self.load_fixture_plan("external_drift")
        for e in plan["resource_drift"] + plan["resource_changes"]:
            for view in ("before", "after"):
                if isinstance(e["change"].get(view), dict):
                    e["change"][view]["tags"]["probe"] = "s3cr3t-token-value"
            e["change"]["after_sensitive"] = {"tags": {"probe": True}}
        e = plan["resource_drift"][0]
        e["change"]["after"]["tags"].pop("probe")
        path = self.write_plan("plan.json", plan)
        for fmt in formatters.FORMATS:
            with self.subTest(fmt):
                code, stdout, stderr = self.run_cli("analyze", "--plan", path, "--format", fmt)
                self.assertEqual(code, 0, stderr)
                self.assertNotIn("s3cr3t", stdout + stderr)
                if fmt == "console":
                    self.assertIn("(sensitive)", stdout)
                    self.assertIn("HIGH", stdout)  # sensitive-value rule

    def test_unknown_value_shown(self):
        plan = self.load_fixture_plan("external_drift")
        change = plan["resource_changes"][0]["change"]
        change["after"]["tags"].pop("probe")
        change["after_unknown"] = {"tags": {"probe": True}}
        _, text, _ = self.run_cli("analyze", "--plan", self.write_plan("plan.json", plan), "--format", "console")
        self.assertIn("desired: (known after apply)", text)

    def test_long_values_truncated(self):
        plan = self.load_fixture_plan("external_drift")
        plan["resource_drift"][0]["change"]["after"]["tags"]["probe"] = "x" * 500
        _, text, _ = self.run_cli("analyze", "--plan", self.write_plan("plan.json", plan), "--format", "console")
        self.assertIn("…", text)
        self.assertNotIn("x" * 100, text)

    def test_color(self):
        self.assertNotIn(ANSI, self.console("external_drift"))  # auto, not a terminal
        self.assertNotIn(ANSI, self.console("external_drift", "--color", "never"))
        colored = self.console("external_drift", "--color", "always")
        self.assertIn(ANSI, colored)
        self.assertIn("\033[36mLOW", colored)

    def test_auto_color_rules(self):
        with mock.patch.object(sys.stdout, "isatty", return_value=True, create=True), \
                mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NO_COLOR", None)
            self.assertTrue(cli._use_color("auto", to_terminal=True))
            self.assertFalse(cli._use_color("auto", to_terminal=False))
            with mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
                self.assertFalse(cli._use_color("auto", to_terminal=True))
            self.assertTrue(cli._use_color("always", to_terminal=False))
            self.assertFalse(cli._use_color("never", to_terminal=True))


# ---------------------------------------------------------------------------
# Real process invocation
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Logging (Task 4.7)
# ---------------------------------------------------------------------------

class TestCliLogging(CliTestCase):
    ARGS = ("analyze", "--plan", plan_path("external_drift"), "--manifest", manifest_path("external_drift"))

    def test_no_log_lines_by_default(self):
        code, _, stderr = self.run_cli(*self.ARGS)
        self.assertEqual((code, stderr), (0, ""))

    def test_text_logs_on_stderr_and_report_unchanged(self):
        _, plain, _ = self.run_cli(*self.ARGS)
        code, logged, stderr = self.run_cli(*self.ARGS, "--log-level", "info")
        self.assertEqual(code, 0)
        self.assertEqual(logged, plain)
        self.assertIn("INFO drift_engine.classifier classification_finished: evidence classified", stderr)
        self.assertNotIn("DEBUG", stderr)

    def test_json_logs_are_one_object_per_line(self):
        code, _, stderr = self.run_cli("analyze", "--plan", plan_path("replace"), "--log-level", "debug",
                                       "--log-format", "json")
        self.assertEqual(code, 0)
        records = [json.loads(line) for line in stderr.splitlines() if line.startswith("{")]
        # The classifier rates the plan for the report (Task 6.2A); the console view rates it again.
        self.assertEqual([r["event"] for r in records], ["manifest_not_given", "evidence_loaded", "plan_parsed",
                                                         "comparison_finished", "severity_rated",
                                                         "classification_finished", "comparison_finished",
                                                         "severity_rated"])
        self.assertEqual(records[-1]["fields"]["highest"], "HIGH")
        for line in stderr.splitlines():
            self.assertTrue(line.startswith("{") or line.startswith("WARNING: no --manifest"), line)

    def test_report_written_event(self):
        out = os.path.join(self.tmp, "r.yaml")
        _, _, stderr = self.run_cli(*self.ARGS, "--output", out, "--format", "yaml", "--log-level", "info",
                                    "--log-format", "json")
        written = [json.loads(line) for line in stderr.splitlines() if '"report_written"' in line]
        self.assertEqual(written[0]["fields"], {"output": out, "format": "yaml", "outcome": "succeeded"})

    def test_failure_events(self):
        _, _, stderr = self.run_cli("analyze", "--plan", os.path.join(self.tmp, "missing.json"),
                                    "--log-level", "warning", "--log-format", "json")
        failed = [json.loads(line) for line in stderr.splitlines() if '"classification_failed"' in line]
        self.assertEqual(failed[0]["fields"]["reason"], "missing.json not found")
        code, _, stderr = self.run_cli(*self.ARGS, "--output", os.path.join(self.tmp, "no", "dir", "r.json"),
                                       "--log-level", "error")
        self.assertEqual(code, cli.EXIT_CANT_WRITE)
        self.assertIn("ERROR drift_engine.cli output_write_failed", stderr)

    def test_invalid_log_options(self):
        for args in (("--log-level", "verbose"), ("--log-level", "info", "--log-format", "xml")):
            with self.subTest(args=args):
                self.assertEqual(self.run_cli(*self.ARGS, *args)[0], cli.EXIT_USAGE)


# ---------------------------------------------------------------------------
# Error handling (Task 4.7)
# ---------------------------------------------------------------------------

class TestErrorHandling(CliTestCase):
    ARGS = ("analyze", "--plan", plan_path("external_drift"), "--manifest", manifest_path("external_drift"))

    def test_unexpected_exception_is_contained(self):
        with mock.patch.object(cli, "evaluate", side_effect=RuntimeError("boom")):
            code, stdout, stderr = self.run_cli(*self.ARGS)
        self.assertEqual((code, stdout), (cli.EXIT_INTERNAL_ERROR, ""))
        self.assertIn("INTERNAL ERROR: unexpected RuntimeError: boom", stderr)
        self.assertIn("Drift status is UNKNOWN", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_unexpected_exception_is_logged_with_traceback_at_debug(self):
        with mock.patch.object(cli, "evaluate", side_effect=RuntimeError("boom")):
            _, _, error_only = self.run_cli(*self.ARGS, "--log-level", "error")
            _, _, debug = self.run_cli(*self.ARGS, "--log-level", "debug")
        self.assertIn("unexpected_error: unexpected internal error error_type=\"RuntimeError\"", error_only)
        self.assertNotIn("Traceback", error_only)
        self.assertIn("Traceback", debug)

    def run_interruptible(self, *args):
        try:
            return self.run_cli(*args)
        except KeyboardInterrupt:  # would otherwise abort the whole test session
            self.fail("KeyboardInterrupt escaped the CLI")

    def test_keyboard_interrupt(self):
        with mock.patch.object(cli, "evaluate", side_effect=KeyboardInterrupt):
            code, _, stderr = self.run_interruptible(*self.ARGS)
        self.assertEqual((code, stderr), (cli.EXIT_INTERRUPTED, "Interrupted.\n"))

    def test_broken_pipe_in_process(self):
        broken = mock.Mock()
        broken.write.side_effect = BrokenPipeError
        broken.fileno.side_effect = io.UnsupportedOperation  # like StringIO: no file descriptor
        with mock.patch.object(sys, "stdout", broken):
            code = cli.main(list(self.ARGS))
        self.assertEqual(code, cli.EXIT_BROKEN_PIPE)

    def test_broken_pipe_real_process(self):
        env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
        proc = subprocess.Popen([sys.executable, "-m", "drift_engine.cli", *self.ARGS, "--format", "console"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        proc.stdout.close()  # reader goes away before the report is written
        stderr = proc.stderr.read().decode()
        proc.stderr.close()
        self.assertEqual(proc.wait(timeout=60), cli.EXIT_BROKEN_PIPE, stderr)
        self.assertNotIn("Traceback", stderr)
        self.assertNotIn("Exception ignored", stderr)


ROOT_USER = hasattr(os, "geteuid") and os.geteuid() == 0  # root bypasses file permissions


class TestAtomicOutput(CliTestCase):
    """--output: atomic replacement that never weakens an existing report (Task 4.7)."""

    ARGS = ("analyze", "--plan", plan_path("external_drift"))

    def leftovers(self, directory: str | None = None) -> list[str]:
        return [f for f in os.listdir(directory or self.tmp) if f.startswith(".drift-engine-")]

    def existing(self, name: str, mode: int, content: str = "previous report") -> str:
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(path, mode)
        return path

    def mode(self, path: str) -> int:
        return os.lstat(path).st_mode & 0o7777

    def write_report(self, out: str, umask: int = 0o022) -> int:
        old = os.umask(umask)
        try:
            return self.run_cli(*self.ARGS, "--output", out)[0]
        finally:
            os.umask(old)

    # -- permissions ---------------------------------------------------------

    def test_new_file_respects_the_umask(self):
        for umask, expected in ((0o022, 0o644), (0o077, 0o600), (0o002, 0o664)):
            with self.subTest(umask=oct(umask)):
                out = os.path.join(self.tmp, f"new-{umask:o}.json")
                self.assertEqual(self.write_report(out, umask), 0)
                self.assertEqual(self.mode(out), expected)
        self.assertEqual(self.leftovers(), [])

    def test_existing_0600_report_stays_0600(self):
        out = self.existing("r.json", 0o600)
        self.assertEqual(self.write_report(out, umask=0o022), 0)  # a loose umask must not widen it
        self.assertEqual(self.mode(out), 0o600)
        self.assertTrue(DriftReport.model_validate_json(read(out)).has_drift)

    def test_existing_permissions_are_kept_exactly(self):
        for mode in (0o640, 0o664, 0o604, 0o666):
            with self.subTest(mode=oct(mode)):
                out = self.existing(f"r-{mode:o}.json", mode)
                self.assertEqual(self.write_report(out, umask=0o077), 0)  # a tight umask must not narrow it
                self.assertEqual(self.mode(out), mode)

    def test_special_bits_are_not_carried_over(self):
        out = self.existing("r.json", 0o640)
        os.chmod(out, 0o2640)  # setgid
        if self.mode(out) != 0o2640:
            self.skipTest("filesystem does not keep setgid on a regular file")
        self.assertEqual(self.write_report(out), 0)
        self.assertEqual(self.mode(out), 0o640)

    @unittest.skipIf(ROOT_USER, "root can write any file")
    def test_read_only_existing_report_is_refused(self):
        out = self.existing("r.json", 0o444)
        code, _, stderr = self.run_cli(*self.ARGS, "--output", out)
        self.assertEqual(code, cli.EXIT_CANT_WRITE)
        self.assertIn("not writable", stderr)
        self.assertEqual((read(out), self.mode(out)), ("previous report", 0o444))
        self.assertEqual(self.leftovers(), [])

    # -- failures keep the existing report ------------------------------------

    def test_failed_write_keeps_the_previous_report(self):
        out = self.existing("r.json", 0o600)
        with mock.patch.object(cli.os, "replace", side_effect=OSError("disk full")):
            code, _, stderr = self.run_cli(*self.ARGS, "--output", out)
        self.assertEqual(code, cli.EXIT_CANT_WRITE)
        self.assertIn("disk full", stderr)
        self.assertEqual((read(out), self.mode(out)), ("previous report", 0o600))
        self.assertEqual(self.leftovers(), [])

    def test_interrupted_write_keeps_the_previous_report(self):
        out = self.existing("r.json", 0o600)
        with mock.patch.object(cli.os, "fsync", side_effect=KeyboardInterrupt):
            try:
                code, _, _ = self.run_cli(*self.ARGS, "--output", out)
            except KeyboardInterrupt:  # would otherwise abort the whole test session
                self.fail("KeyboardInterrupt escaped the CLI")
        self.assertEqual(code, cli.EXIT_INTERRUPTED)
        self.assertEqual((read(out), self.mode(out)), ("previous report", 0o600))
        self.assertEqual(self.leftovers(), [])

    def test_interrupted_write_leaves_no_new_file(self):
        out = os.path.join(self.tmp, "r.json")
        with mock.patch.object(cli.os, "fsync", side_effect=KeyboardInterrupt):
            try:
                code, _, _ = self.run_cli(*self.ARGS, "--output", out)
            except KeyboardInterrupt:
                self.fail("KeyboardInterrupt escaped the CLI")
        self.assertEqual(code, cli.EXIT_INTERRUPTED)
        self.assertFalse(os.path.exists(out))
        self.assertEqual(self.leftovers(), [])

    def test_output_path_is_a_directory(self):
        target = os.path.join(self.tmp, "adir")
        os.mkdir(target)
        code, _, _ = self.run_cli(*self.ARGS, "--output", target)
        self.assertEqual(code, cli.EXIT_CANT_WRITE)
        self.assertTrue(os.path.isdir(target))
        self.assertEqual(self.leftovers(), [])

    @unittest.skipIf(ROOT_USER, "root can write into any directory")
    def test_read_only_directory_is_refused_without_fallback(self):
        directory = os.path.join(self.tmp, "ro")
        os.mkdir(directory)
        out = os.path.join(directory, "r.json")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("previous report")
        os.chmod(out, 0o644)
        os.chmod(directory, 0o555)
        self.addCleanup(os.chmod, directory, 0o755)
        code, _, _ = self.run_cli(*self.ARGS, "--output", out)
        self.assertEqual(code, cli.EXIT_CANT_WRITE)  # no non-atomic in-place write
        self.assertEqual(read(out), "previous report")
        self.assertEqual(self.leftovers(directory), [])

    # -- links: atomic replacement semantics -----------------------------------

    def test_hard_link_gets_a_new_file_other_names_keep_old_content(self):
        out = self.existing("r.json", 0o600)
        other = os.path.join(self.tmp, "other-name.json")
        os.link(out, other)
        self.assertEqual(self.write_report(out), 0)
        self.assertTrue(DriftReport.model_validate_json(read(out)).has_drift)
        self.assertEqual(self.mode(out), 0o600)  # permissions of the replaced file kept
        self.assertEqual(read(other), "previous report")  # documented: the link is not updated
        self.assertNotEqual(os.stat(out).st_ino, os.stat(other).st_ino)

    def test_symlink_is_replaced_never_written_through(self):
        target = self.existing("protected.json", 0o600, "must not be overwritten")
        link = os.path.join(self.tmp, "r.json")
        os.symlink(target, link)
        self.assertEqual(self.write_report(link, umask=0o022), 0)
        self.assertFalse(os.path.islink(link))  # the link itself was replaced...
        self.assertTrue(DriftReport.model_validate_json(read(link)).has_drift)
        self.assertEqual(self.mode(link), 0o644)  # ...by a new file with umask permissions
        self.assertEqual((read(target), self.mode(target)), ("must not be overwritten", 0o600))

    def test_dangling_symlink_is_replaced(self):
        link = os.path.join(self.tmp, "r.json")
        os.symlink(os.path.join(self.tmp, "does-not-exist"), link)
        self.assertEqual(self.write_report(link), 0)
        self.assertFalse(os.path.islink(link))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "does-not-exist")))

    def test_replaces_an_existing_report(self):
        out = self.existing("r.json", 0o644, "old")
        self.assertEqual(self.run_cli(*self.ARGS, "--output", out)[0], 0)
        self.assertTrue(DriftReport.model_validate_json(read(out)).has_drift)
        self.assertEqual(self.leftovers(), [])


class TestConsoleWithoutRatings(CliTestCase):
    """render_console used directly, without severities (library callers)."""

    def test_succeeded_report_without_ratings(self):
        from drift_engine import classifier
        report = classifier.evaluate(plan_path("replace"), manifest_path("replace")).report
        text = formatters.render_console(report)
        self.assertIn("Severity    INFO (highest across resources)", text)
        self.assertIn("location  config_changed\n", text)  # no category/severity without ratings
        self.assertNotIn("noise (INFO)", text)

    def test_failed_report_without_run(self):
        from drift_engine import classifier
        report = classifier.evaluate(plan_path("in_sync"), os.path.join(self.tmp, "missing.json")).report
        self.assertIsNone(report["run"])
        text = formatters.render_console(report)
        self.assertIn("FAILED: drift status UNKNOWN", text)
        self.assertNotIn("Run ", text)


class TestModuleEntryPoint(CliTestCase):
    def test_run_as_main(self):
        out = os.path.join(self.tmp, "r.json")
        argv = ["drift-engine", "analyze", "--plan", plan_path("in_sync"), "--output", out]
        modules = {k: v for k, v in sys.modules.items() if k != "drift_engine.cli"}
        with mock.patch.object(sys, "argv", argv), mock.patch.dict(sys.modules, modules, clear=True), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                runpy.run_module("drift_engine.cli", run_name="__main__")
        self.assertEqual(ctx.exception.code, 0)
        self.assertTrue(os.path.exists(out))


class TestProcess(CliTestCase):
    def test_python_module_invocation(self):
        out = os.path.join(self.tmp, "report.json")
        env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
        proc = subprocess.run([sys.executable, "-m", "drift_engine.cli", "analyze", "--plan",
                               plan_path("external_drift"), "--output", out],
                              capture_output=True, text=True, env=env, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        DriftReport.model_validate_json(read(out))

    def test_installed_console_script(self):
        try:
            version("drift-engine")
        except PackageNotFoundError:
            self.skipTest("drift-engine not installed")
        (ep,) = [e for e in entry_points(group="console_scripts") if e.name == "drift-engine"]
        self.assertEqual(ep.value, "drift_engine.cli:main")
        exe = shutil.which("drift-engine", path=sysconfig.get_path("scripts"))
        if exe is None:
            self.skipTest("drift-engine executable not on this interpreter's scripts path")
        out = os.path.join(self.tmp, "report.json")
        proc = subprocess.run([exe, "analyze", "--plan", plan_path("external_drift"), "--output", out],
                              capture_output=True, text=True, cwd=self.tmp, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(DriftReport.model_validate_json(read(out)).has_drift)
        proc = subprocess.run([exe, "--version"], capture_output=True, text=True, check=False)
        self.assertEqual(proc.stdout.strip(), f"drift-engine {version('drift-engine')}")


if __name__ == "__main__":
    unittest.main()
