"""Static tests for the Task 9.1 TFLint integration.

No TFLint binary, no network: these tests read `.tflint.hcl`, `scripts/run_tflint.sh`,
`.github/workflows/security-scan.yml` and the Terraform baseline fixes as text. The
real TFLint run (plugin download, baseline, mutation checks) is a separate, recorded
validation step (PROJECT_PLAN.md, Task 9.1).
"""

from __future__ import annotations

import glob
import os
import re
import subprocess
import tempfile
import unittest

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, ".tflint.hcl")
SCRIPT = os.path.join(ROOT, "scripts", "run_tflint.sh")
WORKFLOWS = os.path.join(ROOT, ".github", "workflows")
SECURITY_SCAN = os.path.join(WORKFLOWS, "security-scan.yml")
README = os.path.join(ROOT, "README.md")
TERRAFORM = os.path.join(ROOT, "terraform")

# Locked versions (Task 9.1). One reviewed change updates them everywhere.
TFLINT_VERSION = "0.64.0"
AZURERM_RULESET_VERSION = "0.32.0"
AZURERM_SOURCE = "github.com/terraform-linters/tflint-ruleset-azurerm"

# Flags/attributes that would hide findings or weaken the gate.
FORBIDDEN_FLAGS = ("--minimum-failure-severity", "--force", "--fix", "--disable-rule", "--only",
                   "continue-on-error", "|| true", "tflint-ignore", "TFLINT_LOG")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def strip_hcl_comments(text: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith(("#", "//")))


def hcl_block(text: str, header: str) -> str | None:
    """Body of the first top-level block whose header matches `header` (regex), or None."""
    match = re.search(rf"^{header}\s*\{{", text, re.MULTILINE)
    if not match:
        return None
    depth, start = 0, match.end() - 1
    for i in range(start, len(text)):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return text[start + 1:i]
    return None


def attr(body: str | None, name: str) -> str | None:
    if body is None:
        return None
    match = re.search(rf"^\s*{name}\s*=\s*(.+?)\s*$", body, re.MULTILINE)
    return match.group(1) if match else None


def pin_errors(config_text: str) -> list[str]:
    """Version-pin violations of a TFLint config (empty list = exactly pinned)."""
    text = strip_hcl_comments(config_text)
    errors = []
    if not re.fullmatch(r'"= \d+\.\d+\.\d+"', attr(hcl_block(text, r"tflint"), "required_version") or ""):
        errors.append("tflint.required_version is not an exact '= X.Y.Z' pin")
    azurerm = hcl_block(text, r'plugin\s+"azurerm"')
    if azurerm is None:
        errors.append("azurerm plugin missing")
    else:
        if not re.fullmatch(r'"\d+\.\d+\.\d+"', attr(azurerm, "version") or ""):
            errors.append("azurerm plugin version is not an exact X.Y.Z pin")
        if attr(azurerm, "source") != f'"{AZURERM_SOURCE}"':
            errors.append("azurerm plugin source is not the terraform-linters ruleset")
    return errors


class TflintConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = read(CONFIG)
        cls.text = strip_hcl_comments(cls.raw)

    def test_exact_pins(self):
        self.assertEqual(pin_errors(self.raw), [])
        self.assertEqual(attr(hcl_block(self.text, r"tflint"), "required_version"), f'"= {TFLINT_VERSION}"')
        azurerm = hcl_block(self.text, r'plugin\s+"azurerm"')
        self.assertEqual(attr(azurerm, "version"), f'"{AZURERM_RULESET_VERSION}"')
        self.assertEqual(attr(azurerm, "enabled"), "true")

    def test_unpinned_configs_are_rejected(self):
        loose_tflint = self.raw.replace(f'"= {TFLINT_VERSION}"', '">= 0.50"')
        no_tflint_block = re.sub(r"tflint\s*\{[^}]*\}", "", self.raw)
        no_azurerm_version = re.sub(r'\n\s*version\s*=\s*"[^"]*"', "", self.raw)
        loose_azurerm = self.raw.replace(f'version = "{AZURERM_RULESET_VERSION}"', 'version = "~> 0.32"')
        for variant in (loose_tflint, no_tflint_block, no_azurerm_version, loose_azurerm):
            self.assertNotEqual(variant, self.raw)
            self.assertNotEqual(pin_errors(variant), [])

    def test_settings(self):
        self.assertEqual(attr(hcl_block(self.text, r"config"), "call_module_type"), '"local"')
        terraform = hcl_block(self.text, r'plugin\s+"terraform"')
        self.assertEqual(attr(terraform, "enabled"), "true")
        self.assertEqual(attr(terraform, "preset"), '"recommended"')
        self.assertEqual(re.findall(r'^plugin\s+"([^"]+)"', self.text, re.MULTILINE), ["terraform", "azurerm"])

    def test_no_weakening_attributes(self):
        for forbidden in ("varfile", "signature", "plugin_dir", "exclude", "disabled_by_default",
                          "force", "minimum_failure_severity", "ignore_module", "enabled = false"):
            self.assertNotIn(forbidden, self.text)
        self.assertNotRegex(self.text, r"^rule\s", "no rule blocks (no global rule disables)")


class RunTflintScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(SCRIPT)
        cls.code = "\n".join(ln for ln in cls.text.splitlines() if not ln.lstrip().startswith("#"))

    def test_scans_terraform_only_with_absolute_config(self):
        self.assertTrue(os.access(SCRIPT, os.X_OK))
        self.assertIn("set -euo pipefail", self.code)
        self.assertIn('ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd -P)"', self.code)
        self.assertIn('CONFIG="${ROOT_DIR}/.tflint.hcl"', self.code)
        self.assertIn('cd "${ROOT_DIR}/terraform"', self.code)
        self.assertIn('tflint --recursive --config "${CONFIG}"', self.code)
        self.assertEqual(len(re.findall(r"^\s*tflint ", self.code, re.MULTILINE)), 2)  # --init and the lint run
        self.assertNotIn("--chdir", self.code)

    def test_token_only_for_init_and_ruleset_check(self):
        init = self.code.index('tflint --init --config "${CONFIG}"')
        unset = self.code.index("unset GITHUB_TOKEN")
        version = self.code.index('tflint --version --config "${CONFIG}"')
        lint = self.code.index('tflint --recursive')
        self.assertLess(init, unset)
        self.assertLess(unset, version)
        self.assertLess(version, lint)
        self.assertIn(f'EXPECTED_AZURERM_RULESET="ruleset.azurerm ({AZURERM_RULESET_VERSION})"', self.code)

    def test_no_failure_hiding(self):
        for forbidden in FORBIDDEN_FLAGS:
            self.assertNotIn(forbidden, self.code)
        self.assertNotRegex(self.code, r"exit 0\b")
        self.assertNotRegex(self.code, r"\$\?")  # no exit-code capture or remapping

    def _run(self, plugin_dir: str | None) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k not in ("TFLINT_PLUGIN_DIR", "GITHUB_TOKEN")}
        if plugin_dir is not None:
            env["TFLINT_PLUGIN_DIR"] = plugin_dir
        # Fails before any tflint invocation; an empty PATH entry proves no tool is needed.
        env["PATH"] = "/usr/bin:/bin"
        return subprocess.run(["bash", SCRIPT], env=env, capture_output=True, text=True, timeout=30)

    def test_plugin_dir_must_be_outside_the_repository(self):
        for plugin_dir, message in ((None, "must be set"), (os.path.join(ROOT, "terraform"), "outside the repository"),
                                    (ROOT, "outside the repository"),
                                    (os.path.join(ROOT, "no-such-dir"), "not an existing directory")):
            result = self._run(plugin_dir)
            self.assertEqual(result.returncode, 1, plugin_dir)
            self.assertIn(message, result.stderr)
            self.assertNotIn("Installing", result.stdout)

    def test_plugin_dir_outside_repository_passes_the_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(tmp)
        # The guard passes; without a tflint binary on PATH the next step fails (127).
        self.assertIn("static Terraform lint (not drift detection)", result.stdout)
        self.assertNotEqual(result.returncode, 0)


class SecurityScanWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(SECURITY_SCAN)
        cls.wf = yaml.safe_load(cls.text)
        cls.code = "\n".join(ln for ln in cls.text.splitlines() if not ln.lstrip().startswith("#"))

    def test_triggers_permissions_concurrency(self):
        triggers = self.wf.get("on", self.wf.get(True))
        self.assertEqual(triggers, {"push": {"branches": ["main"]}, "pull_request": {"branches": ["main"]},
                                    "workflow_dispatch": None})
        self.assertEqual(self.wf["permissions"], {"contents": "read"})
        self.assertEqual(self.wf["concurrency"], {
            "group": "security-scan-${{ github.ref }}",
            "cancel-in-progress": "${{ github.event_name == 'pull_request' }}"})

    def test_tflint_job(self):
        self.assertEqual(sorted(self.wf["jobs"]), ["tflint"])
        job = self.wf["jobs"]["tflint"]
        for key in ("permissions", "environment", "outputs", "continue-on-error", "if", "env"):
            self.assertNotIn(key, job)
        self.assertIn("not drift detection", job["name"])
        steps = job["steps"]
        self.assertEqual([s.get("uses") for s in steps],
                         ["actions/checkout@v4", "terraform-linters/setup-tflint@v6", None])
        self.assertEqual(steps[0]["with"], {"persist-credentials": False})
        self.assertEqual(steps[1]["with"], {"tflint_version": f"v{TFLINT_VERSION}"})  # no cache, default token input
        self.assertEqual(steps[2]["run"].strip(), "./scripts/run_tflint.sh")
        self.assertEqual(steps[2]["env"], {"TFLINT_PLUGIN_DIR": "${{ runner.temp }}",
                                           "GITHUB_TOKEN": "${{ github.token }}"})
        for step in steps:
            for key in ("continue-on-error", "if"):
                self.assertNotIn(key, step)
            if step is not steps[2]:
                self.assertNotIn("env", step)
        self.assertEqual(self.code.count("GITHUB_TOKEN"), 1)

    def test_no_azure_no_drift_semantics_no_extras(self):
        for forbidden in ("id-token", "azure/login", "ARM_", "TF_VAR_", "AZURE_", "secrets.", "terraform init",
                          "terraform plan", "drift_detected", "drift_status", "drift-report", "issues:",
                          "upload-artifact", "sarif", "security-events", "cache", "paths:", "paths-ignore",
                          "pull_request_target", "write") + FORBIDDEN_FLAGS:
            self.assertNotIn(forbidden, self.code, forbidden)


class ExistingWorkflowsTests(unittest.TestCase):
    def test_no_tflint_or_security_scan_integration(self):
        for name in ("drift-detection.yml", "terraform-auth-test.yml"):
            text = read(os.path.join(WORKFLOWS, name)).lower()
            for marker in ("tflint", "security-scan", "run_tflint"):
                self.assertNotIn(marker, text, f"{name}: {marker}")


class TerraformBaselineTests(unittest.TestCase):
    def test_no_tflint_ignore_annotations(self):
        for path in glob.glob(os.path.join(TERRAFORM, "**", "*.tf"), recursive=True):
            if "/.terraform/" not in path:
                self.assertNotIn("tflint-ignore", read(path), path)

    def test_state_storage_is_protected(self):
        text = read(os.path.join(TERRAFORM, "bootstrap", "main.tf"))
        for header in (r'resource\s+"azurerm_storage_account"\s+"tfstate"', r'resource\s+"azurerm_storage_container"\s+"tfstate"'):
            lifecycle = hcl_block(hcl_block(text, header).replace("\n  ", "\n"), r"lifecycle")
            self.assertEqual(attr(lifecycle, "prevent_destroy"), "true", header)

    def test_module_version_constraints_match_roots(self):
        for module in ("network", "resource-group"):
            text = strip_hcl_comments(read(os.path.join(TERRAFORM, "modules", module, "versions.tf")))
            self.assertIn('required_version = ">= 1.6.0"', text)
            self.assertRegex(text, r'source\s*=\s*"hashicorp/azurerm"')
            self.assertRegex(text, r'version\s*=\s*"~> 5\.0"')


class DocumentationTests(unittest.TestCase):
    def test_readme_records_pins_and_usage(self):
        text = read(README)
        for needle in (TFLINT_VERSION, AZURERM_RULESET_VERSION, "TFLINT_PLUGIN_DIR=", "./scripts/run_tflint.sh",
                       "prevent_destroy", "security-scan.yml", "4.65.0"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
