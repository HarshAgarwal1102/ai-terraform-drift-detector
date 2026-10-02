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
import os
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

    from drift_engine import cli, formatters, severity
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
        self.assertEqual(set(json.loads(stdout)), {
            "classification_version", "outcome", "has_drift", "failure", "run", "plan", "summary",
            "resources", "resource_types", "output_changes"})
        self.assertNotIn("severity", stdout)


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
