"""Tests for the Task 9.2 Trivy config integration.

No Trivy binary, no network. Static checks read `scripts/run_trivy_config.sh`,
`security/trivy-risk-acceptance.json` and `.github/workflows/security-scan.yml`. The
gate tests run the real script inside a temporary copy of the repository layout with a
fake `trivy` on PATH that writes synthetic Trivy JSON (shaped like real v0.75.0 output)
and records how it was called. The real Trivy run (baseline, mutation checks) is a
separate, recorded validation step (PROJECT_PLAN.md, Task 9.2).
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "run_trivy_config.sh")
ACCEPTANCE = os.path.join(ROOT, "security", "trivy-risk-acceptance.json")
WORKFLOWS = os.path.join(ROOT, ".github", "workflows")
SECURITY_SCAN = os.path.join(WORKFLOWS, "security-scan.yml")
README = os.path.join(ROOT, "README.md")

# Locked pins (Task 9.2). One reviewed change updates them everywhere.
TRIVY_VERSION = "0.75.0"
TRIVY_LINUX_SHA256 = "c6e65abddb348e25f10549df887045629cf28cc72453cd1c63acb717316b3f3f"
DEV = "terraform/environments/dev"
BOOTSTRAP = "terraform/bootstrap"
ACCEPTED = {"id": "AZU-0012", "resource": "azurerm_storage_account.tfstate", "file": "terraform/bootstrap/main.tf",
            "expires": "2027-03-31"}

# Anything that would let Trivy hide or skip findings, or scan more than Terraform misconfigurations.
FORBIDDEN_TRIVY = ("--ignorefile", "--ignore-policy", "--skip-dirs", "--skip-files", "--severity", "--exit-code",
                   "--scanners", "--include-non-failures", "--config-check", "--checks-bundle-repository",
                   "trivy-action", "setup-trivy", "aquasec/trivy:", "continue-on-error", "|| true")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def code_lines(text: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


# --------------------------------------------------------------------------- synthetic Trivy JSON

def misconfig(rule: str, severity: str, resource: str, title: str = "synthetic") -> dict:
    return {"Type": "Terraform Security Check", "ID": rule, "Title": title, "Severity": severity, "Status": "FAIL",
            "CauseMetadata": {"Resource": resource, "Provider": "Azure", "Service": "storage",
                              "StartLine": 17, "EndLine": 50}}


def report(artifact: str, results: list[tuple[str, list[dict]]]) -> dict:
    return {"SchemaVersion": 2, "ArtifactName": artifact, "ArtifactType": "filesystem",
            "Results": [{"Target": target, "Class": "config", "Type": "terraform",
                         **({"Misconfigurations": items} if items else {})} for target, items in results]}


def baseline() -> dict[str, dict]:
    """Shape and content of the first real v0.75.0 run (PROJECT_PLAN.md, Task 9.2)."""
    sa = "azurerm_storage_account.tfstate"
    return {
        DEV: report(DEV, [(".", [])]),
        BOOTSTRAP: report(BOOTSTRAP, [(".", []), ("main.tf", [
            misconfig("AZU-0012", "CRITICAL", sa), misconfig("AZU-0057", "MEDIUM", sa),
            misconfig("AZU-0058", "LOW", sa), misconfig("AZU-0060", "MEDIUM", sa),
            misconfig("AZU-0061", "MEDIUM", sa)])]),
    }


FAKE_TRIVY = r"""#!/usr/bin/env bash
# Fake trivy: records each call and writes the prepared JSON for the scanned root.
set -euo pipefail
log="${FAKE_DIR}/calls.jsonl"
if [ "${1:-}" = "--version" ]; then
  printf '{"Version":"%s"}\n' "${FAKE_VERSION}"
  exit 0
fi
out=""; cache=""; prev=""
for arg in "$@"; do
  [ "${prev}" = "--output" ] && out="${arg}"
  [ "${prev}" = "--cache-dir" ] && cache="${arg}"
  prev="${arg}"
done
root="${*: -1}"
cache_entries="$(ls -A "${cache}" | wc -l | tr -d ' ')"
env_trivy="$(env | grep -c '^TRIVY_' || true)"
{
  printf '{"cwd":"%s","cache_entries":%s,"env_trivy":%s,"args":[' "$(pwd -P)" "${cache_entries}" "${env_trivy}"
  sep=""; for arg in "$@"; do printf '%s"%s"' "${sep}" "${arg}"; sep=","; done
  printf ']}\n'
} >> "${log}"
echo "INFO fake scan" >&2
echo "ERROR [misconfig] Falling back to embedded checks" >&2
[ -n "${FAKE_FAIL_ROOT:-}" ] && [ "${FAKE_FAIL_ROOT}" = "${root}" ] && exit 1
cp "${FAKE_DIR}/${root//\//_}.json" "${out}"
"""


class GateHarness(unittest.TestCase):
    """Runs the real script in a temporary repository copy with a fake trivy."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trivy-gate-")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.repo, "scripts"))
        os.makedirs(os.path.join(self.repo, "security"))
        for root in (DEV, BOOTSTRAP):
            os.makedirs(os.path.join(self.repo, root))
        shutil.copy2(SCRIPT, os.path.join(self.repo, "scripts", "run_trivy_config.sh"))
        shutil.copy2(ACCEPTANCE, os.path.join(self.repo, "security", "trivy-risk-acceptance.json"))
        self.fake = os.path.join(self.tmp, "fake")
        os.makedirs(os.path.join(self.fake, "bin"))
        trivy = os.path.join(self.fake, "bin", "trivy")
        with open(trivy, "w", encoding="utf-8") as fh:
            fh.write(FAKE_TRIVY)
        os.chmod(trivy, os.stat(trivy).st_mode | stat.S_IXUSR)
        self.work = os.path.join(self.tmp, "runner-temp")
        os.makedirs(self.work)
        self.set_reports(baseline())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def set_reports(self, reports: dict[str, dict]):
        for root, data in reports.items():
            with open(os.path.join(self.fake, root.replace("/", "_") + ".json"), "w", encoding="utf-8") as fh:
                fh.write(data if isinstance(data, str) else json.dumps(data))

    def set_record(self, record):
        with open(os.path.join(self.repo, "security", "trivy-risk-acceptance.json"), "w", encoding="utf-8") as fh:
            fh.write(record if isinstance(record, str) else json.dumps(record))

    def record(self) -> dict:
        return json.loads(read(ACCEPTANCE))

    def run_gate(self, version: str = TRIVY_VERSION, path: str | None = None, extra_env: dict | None = None):
        env = {k: v for k, v in os.environ.items() if not k.startswith("TRIVY_")}
        env.update({"FAKE_DIR": self.fake, "FAKE_VERSION": version, "RUNNER_TEMP": self.work,
                    "PATH": path if path is not None else f"{self.fake}/bin:{os.environ['PATH']}"})
        env.update(extra_env or {})
        return subprocess.run(["/bin/bash", os.path.join(self.repo, "scripts", "run_trivy_config.sh")],
                              env=env, capture_output=True, text=True, timeout=60)

    def calls(self) -> list[dict]:
        path = os.path.join(self.fake, "calls.jsonl")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh]


class GateTests(GateHarness):
    def assert_fails(self, result, message: str):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(message, result.stderr)

    def test_baseline_passes_and_prints_everything(self):
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        out = result.stdout
        self.assertIn("static security scan (not drift detection)", out)
        self.assertIn("Trivy version: 0.75.0", out)
        self.assertIn("ACCEPTED RISK  CRITICAL  AZU-0012  azurerm_storage_account.tfstate  terraform/bootstrap/main.tf",
                      out)
        self.assertIn("expires: 2027-03-31", out)
        self.assertIn("justification: ", out)
        for rule, sev in (("AZU-0057", "MEDIUM"), ("AZU-0058", "LOW"), ("AZU-0060", "MEDIUM"), ("AZU-0061", "MEDIUM")):
            self.assertIn(f"REPORTED (non-blocking)  {sev}  {rule}", out)
        self.assertNotIn("BLOCKING ", out)
        self.assertIn("Falling back to embedded checks", result.stderr)  # expected ERROR-level log, not a failure

    def test_invocations_root_flags_and_fresh_caches(self):
        self.assertEqual(self.run_gate().returncode, 0)
        calls = self.calls()
        self.assertEqual(len(calls), 2)
        repo = os.path.realpath(self.repo)
        caches = []
        for call, root, extra in ((calls[0], DEV, ["--tf-vars", f"{DEV}/dev.tfvars"]), (calls[1], BOOTSTRAP, [])):
            self.assertEqual(call["cwd"], repo)  # from the repository root
            args = call["args"]
            cache = args[args.index("--cache-dir") + 1]
            output = args[args.index("--output") + 1]
            caches.append(cache)
            self.assertEqual(args, ["config", "--skip-check-update", "--disable-telemetry", "--skip-version-check",
                                    "--misconfig-scanners", "terraform", "--cache-dir", cache, "--format", "json",
                                    "--output", output, *extra, root])
            self.assertEqual(call["cache_entries"], 0)  # fresh, empty cache
            self.assertFalse(os.path.realpath(cache).startswith(repo + os.sep))
            self.assertTrue(os.path.realpath(cache).startswith(os.path.realpath(self.work) + os.sep))
            self.assertEqual(call["env_trivy"], 0)
        self.assertNotEqual(caches[0], caches[1])
        self.assertEqual(os.listdir(self.work), [])  # work directory removed

    def test_trivy_environment_is_cleared(self):
        result = self.run_gate(extra_env={"TRIVY_SEVERITY": "LOW", "TRIVY_IGNOREFILE": "/tmp/x", "TRIVY_SKIP_DIRS": "x"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c["env_trivy"] for c in self.calls()], [0, 0])

    def test_unexpected_high_and_critical_fail(self):
        for sev, resource in (("HIGH", "azurerm_storage_account.tfstate"), ("CRITICAL", 'module.network["main"]')):
            with self.subTest(sev=sev):
                reports = baseline()
                reports[DEV] = report(DEV, [(".", []), ("../../modules/network/main.tf",
                                                        [misconfig("AZU-0047", sev, resource)])])
                self.set_reports(reports)
                result = self.run_gate()
                self.assert_fails(result, "HIGH/CRITICAL finding(s) not covered by the risk acceptance")
                self.assertIn(f"BLOCKING  {sev}  AZU-0047", result.stdout)
                self.assertIn("ACCEPTED RISK  CRITICAL  AZU-0012", result.stdout)

    def test_near_misses_of_the_accepted_finding_fail(self):
        cases = {
            "other rule": misconfig("AZU-0008", "HIGH", "azurerm_storage_account.tfstate"),
            "other resource": misconfig("AZU-0012", "CRITICAL", "azurerm_storage_account.other"),
        }
        for name, extra in cases.items():
            with self.subTest(name=name):
                reports = baseline()
                reports[BOOTSTRAP]["Results"][1]["Misconfigurations"].append(extra)
                self.set_reports(reports)
                self.assert_fails(self.run_gate(), "not covered by the risk acceptance")
        with self.subTest(name="other file"):  # same rule and resource in another file
            reports = baseline()
            reports[BOOTSTRAP]["Results"].append(
                {"Target": "other.tf", "Misconfigurations": [misconfig("AZU-0012", "CRITICAL",
                                                                       "azurerm_storage_account.tfstate")]})
            self.set_reports(reports)
            self.assert_fails(self.run_gate(), "not covered by the risk acceptance")
        with self.subTest(name="same file under another root"):
            reports = baseline()
            reports[DEV] = report(DEV, [("main.tf", [misconfig("AZU-0012", "CRITICAL",
                                                                "azurerm_storage_account.tfstate")])])
            self.set_reports(reports)
            self.assert_fails(self.run_gate(), "not covered by the risk acceptance")

    def test_medium_and_low_never_block(self):
        reports = baseline()
        reports[DEV] = report(DEV, [(".", [misconfig("AZU-0099", "MEDIUM", "x.y"), misconfig("AZU-0098", "LOW", "x.z"),
                                          misconfig("AZU-0097", "UNKNOWN", "x.w")])])
        self.set_reports(reports)
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("REPORTED (non-blocking)  MEDIUM  AZU-0099", result.stdout)

    def test_stale_acceptance_fails(self):
        reports = baseline()
        reports[BOOTSTRAP]["Results"][1]["Misconfigurations"].pop(0)  # AZU-0012 gone
        self.set_reports(reports)
        self.assert_fails(self.run_gate(), "stale risk acceptance")

    def test_multiple_matches_fail(self):
        reports = baseline()
        reports[BOOTSTRAP]["Results"][1]["Misconfigurations"].append(
            misconfig("AZU-0012", "CRITICAL", "azurerm_storage_account.tfstate"))
        self.set_reports(reports)
        self.assert_fails(self.run_gate(), "matches 2 findings")

    def test_expired_acceptance_fails(self):
        record = self.record()
        record["acceptances"][0]["expires"] = "2020-01-01"
        self.set_record(record)
        self.assert_fails(self.run_gate(), "expired on 2020-01-01")
        self.assertEqual(self.calls(), [])  # before any scan

    def test_malformed_records_fail(self):
        base = self.record()
        variants = {"not json": "{", "missing": None}
        two = copy.deepcopy(base)
        two["acceptances"].append(copy.deepcopy(base["acceptances"][0]))
        variants["two entries"] = two
        variants["no entries"] = {"acceptances": []}
        for field in ("id", "resource", "file", "expires", "justification", "scope", "reference"):
            missing = copy.deepcopy(base)
            del missing["acceptances"][0][field]
            variants[f"missing {field}"] = missing
        extra = copy.deepcopy(base)
        extra["acceptances"][0]["severity"] = "CRITICAL"
        variants["extra field"] = extra
        extra_top = copy.deepcopy(base)
        extra_top["note"] = "x"
        variants["extra top-level key"] = extra_top
        for bad_date in ("2027-3-31", "2027-02-30", "31-03-2027", ""):
            dated = copy.deepcopy(base)
            dated["acceptances"][0]["expires"] = bad_date
            variants[f"date {bad_date!r}"] = dated
        wildcard = copy.deepcopy(base)
        wildcard["acceptances"][0]["resource"] = 7
        variants["non-string field"] = wildcard
        for name, record in variants.items():
            with self.subTest(name=name):
                path = os.path.join(self.repo, "security", "trivy-risk-acceptance.json")
                if record is None:
                    os.remove(path)
                    message = "risk-acceptance record not found"
                else:
                    self.set_record(record)
                    message = "malformed risk-acceptance record"
                self.assert_fails(self.run_gate(), message)
                shutil.copy2(ACCEPTANCE, path)

    def test_wildcard_record_does_not_widen(self):
        record = self.record()
        record["acceptances"][0]["resource"] = "azurerm_storage_account.*"
        self.set_record(record)
        result = self.run_gate()
        self.assert_fails(result, "stale risk acceptance")
        self.assertIn("BLOCKING  CRITICAL  AZU-0012", result.stdout)

    def test_unsafe_or_failed_scans_fail(self):
        cases = {
            "invalid json": "{not json",
            "wrong artifact": report("terraform", [(".", [])]),
            "schema version": {**report(BOOTSTRAP, [(".", [])]), "SchemaVersion": 3},
            "no results array": {"SchemaVersion": 2, "ArtifactName": BOOTSTRAP},
            "missing ID": report(BOOTSTRAP, [("main.tf", [{**misconfig("AZU-0012", "CRITICAL", "r.n"), "ID": ""}])]),
            "missing resource": report(BOOTSTRAP, [("main.tf", [{**misconfig("AZU-0012", "CRITICAL", "r.n"),
                                                                 "CauseMetadata": {}}])]),
            "unknown severity": report(BOOTSTRAP, [("main.tf", [misconfig("AZU-0012", "SEVERE", "r.n")])]),
            "missing target": {"SchemaVersion": 2, "ArtifactName": BOOTSTRAP, "Results": [{"Class": "config"}]},
        }
        for name, data in cases.items():
            with self.subTest(name=name):
                self.set_reports({**baseline(), BOOTSTRAP: data})
                self.assert_fails(self.run_gate(), "unexpected Trivy JSON")
        with self.subTest(name="trivy exits non-zero"):
            self.set_reports(baseline())
            result = self.run_gate(extra_env={"FAKE_FAIL_ROOT": DEV})
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("passed", result.stdout)

    def test_prerequisites(self):
        with self.subTest("wrong version"):
            self.assert_fails(self.run_gate(version="0.74.0"), "Trivy 0.75.0 is required (got '0.74.0')")
        with self.subTest("no trivy"):
            self.assert_fails(self.run_gate(path="/usr/bin:/bin"), "trivy 0.75.0 was not found")
        with self.subTest("no jq"):
            # Only the fake trivy on PATH: the jq check runs before any external command.
            result = self.run_gate(path=f"{self.fake}/bin")
            self.assert_fails(result, "jq is required")
            self.assertEqual(self.calls(), [])

    def test_ignore_and_config_files_fail(self):
        for name in (".trivyignore", ".trivyignore.yaml", "trivy.yaml"):
            with self.subTest(name=name):
                path = os.path.join(self.repo, name)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("AZU-0012\n")
                self.assert_fails(self.run_gate(), f"{name} is not allowed")
                os.remove(path)
        tf = os.path.join(self.repo, BOOTSTRAP, "main.tf")
        with open(tf, "w", encoding="utf-8") as fh:
            fh.write('#trivy:ignore:AZU-0012\nresource "x" "y" {}\n')
        self.assert_fails(self.run_gate(), "inline trivy:ignore annotations are not allowed")

    def test_work_dir_inside_repository_fails(self):
        result = self.run_gate(extra_env={"RUNNER_TEMP": self.repo})
        self.assert_fails(result, "must be outside the repository")


class StaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = read(SCRIPT)
        cls.script_code = code_lines(cls.script)
        cls.wf_text = read(SECURITY_SCAN)
        cls.wf = yaml.safe_load(cls.wf_text)
        cls.job = cls.wf["jobs"]["trivy-config"]
        cls.job_text = yaml.safe_dump(cls.job)

    def test_acceptance_record(self):
        data = json.loads(read(ACCEPTANCE))
        self.assertEqual(list(data), ["acceptances"])
        self.assertEqual(len(data["acceptances"]), 1)
        entry = data["acceptances"][0]
        self.assertEqual(sorted(entry), ["expires", "file", "id", "justification", "reference", "resource", "scope"])
        self.assertEqual({k: entry[k] for k in ACCEPTED}, ACCEPTED)
        self.assertIn("AVD-AZU-0012", entry["reference"])  # documentation alias only
        for key in ("justification", "scope"):
            self.assertGreater(len(entry[key]), 40)

    def test_no_ignore_or_config_files_in_repository(self):
        tracked = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True,
                                 text=True, check=True).stdout.split()
        for path in tracked:
            self.assertNotIn(os.path.basename(path), (".trivyignore", ".trivyignore.yaml", "trivy.yaml"), path)
            if path.endswith((".tf", ".tfvars")):
                self.assertNotIn("trivy:ignore", read(os.path.join(ROOT, path)).lower(), path)

    def test_script_flags_and_scope(self):
        self.assertTrue(os.access(SCRIPT, os.X_OK))
        code = self.script_code
        self.assertIn("set -euo pipefail", code)
        self.assertIn(f'TRIVY_VERSION="{TRIVY_VERSION}"', code)
        for flag in ("--skip-check-update", "--disable-telemetry", "--skip-version-check",
                     "--misconfig-scanners terraform", "--format json", '--cache-dir "${cache_dir}"'):
            self.assertIn(flag, code)
        self.assertIn(f"scan {DEV} --tf-vars {DEV}/dev.tfvars", code)
        self.assertIn(f"scan {BOOTSTRAP}\n", code)
        self.assertEqual(len(re.findall(r"^scan ", code, re.MULTILINE)), 2)
        self.assertIn('cd "${ROOT_DIR}"', code)
        self.assertIn('($artifact + "/" + $target)', code)  # locked path derivation
        self.assertIn(".id == $rec.id and .resource == $rec.resource and .file == $rec.file", code)
        self.assertLess(code.index("command -v jq"), code.index("trivy --version"))
        for forbidden in FORBIDDEN_TRIVY:
            self.assertNotIn(forbidden, code, forbidden)

    def test_trivy_config_job(self):
        job = self.job
        self.assertIn("not drift detection", job["name"])
        for key in ("permissions", "environment", "outputs", "continue-on-error", "if", "env", "needs", "services",
                    "container"):
            self.assertNotIn(key, job)
        steps = job["steps"]
        self.assertEqual([s.get("uses") for s in steps], ["actions/checkout@v4", None, None])
        self.assertEqual(steps[0]["with"], {"persist-credentials": False})
        install = steps[1]
        self.assertEqual(install["env"], {"PINNED_TRIVY_VERSION": TRIVY_VERSION,
                                          "PINNED_TRIVY_LINUX_SHA256": TRIVY_LINUX_SHA256})
        run = install["run"]
        self.assertIn("set -euo pipefail", run)
        self.assertIn('archive="trivy_${PINNED_TRIVY_VERSION}_Linux-64bit.tar.gz"', run)
        self.assertIn("https://github.com/aquasecurity/trivy/releases/download/v${PINNED_TRIVY_VERSION}/${archive}", run)
        self.assertLess(run.index("sha256sum -c -"), run.index("tar -xzf"))  # verified before unpacking
        self.assertEqual(steps[2]["run"].strip(), "./scripts/run_trivy_config.sh")
        self.assertNotIn("env", steps[2])
        for step in steps:
            for key in ("continue-on-error", "if"):
                self.assertNotIn(key, step)

    def test_job_is_credential_free_without_drift_semantics(self):
        for forbidden in ("id-token", "azure/login", "ARM_", "TF_VAR_", "AZURE_", "secrets.", "GITHUB_TOKEN",
                          "github.token", "terraform init", "terraform plan", "drift_detected", "drift_status",
                          "drift-report", "issues", "upload-artifact", "actions/cache", "sarif", "security-events",
                          "write", "docker", "ghcr.io") + FORBIDDEN_TRIVY:
            self.assertNotIn(forbidden, self.job_text, forbidden)
        self.assertEqual(self.wf["permissions"], {"contents": "read"})

    def test_existing_workflows_have_no_trivy(self):
        for name in ("drift-detection.yml", "terraform-auth-test.yml"):
            self.assertNotIn("trivy", read(os.path.join(WORKFLOWS, name)).lower(), name)

    def test_readme_documents_scanner(self):
        text = read(README)
        for needle in (TRIVY_VERSION, TRIVY_LINUX_SHA256, "./scripts/run_trivy_config.sh", "AZU-0012", "2027-03-31",
                       "security/trivy-risk-acceptance.json", "HIGH", "CRITICAL", "MEDIUM", "LOW"):
            self.assertIn(needle, text, needle)


if __name__ == "__main__":
    unittest.main()
