"""Tests for the Task 9.3 TruffleHog secret-scan integration.

No TruffleHog binary, no network. Static checks read `scripts/run_trufflehog.sh`,
`.github/workflows/security-scan.yml` and the README. The gate tests run the real
script inside a temporary Git repository with a fake `trufflehog` on PATH that writes
v3.97.9-shaped JSON whose raw fields hold a sentinel value, and records how it was
called. The real TruffleHog proofs (baseline, synthetic-secret detection) are separate,
recorded validation steps (PROJECT_PLAN.md, Task 9.3).
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "run_trufflehog.sh")
WORKFLOWS = os.path.join(ROOT, ".github", "workflows")
SECURITY_SCAN = os.path.join(WORKFLOWS, "security-scan.yml")
README = os.path.join(ROOT, "README.md")

# Locked pins (Task 9.3). One reviewed change updates them everywhere.
TRUFFLEHOG_VERSION = "3.97.9"
TRUFFLEHOG_LINUX_SHA256 = "40377e6572495412fb9ba0bc21c9401f73b72f1d2afd11b9931bc4a5ed622866"
# Built from two parts so the repository never contains the annotation itself.
IGNORE_ANNOTATION = "trufflehog" ":ignore"
SENTINEL = "SENTINEL-SECRET-VALUE-0123456789abcdef"

# Flags that would narrow the scan, hide results, verify against providers or print values.
FORBIDDEN = ("--exclude-paths", "--exclude-globs", "--exclude-detectors", "--include-paths",
             "--include-detectors", "--results", "--only-verified", "--filter-unverified", "--since-commit",
             "--max-depth", "--branch", "--github-actions", "--sarif", "--verifier", "--custom-verifiers-only",
             "--allow-verification-overlap", "trufflesecurity/trufflehog@", "ghcr.io/trufflesecurity",
             "install.sh", "continue-on-error", "|| true")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def code_lines(text: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


def finding(detector: str = "Github", file: str = "config.txt", line: int = 1, commit: str = "834bf2f5aa11") -> dict:
    """A v3.97.9-shaped result; every value-bearing field holds the sentinel."""
    return {
        "SourceMetadata": {"Data": {"Git": {"commit": commit, "file": file, "email": "probe <probe@example.invalid>",
                                            "repository": "file:///repo", "timestamp": "2026-10-04 10:00:00 +0000",
                                            "line": line}}},
        "SourceID": 1, "SourceType": 7, "SourceName": "trufflehog - git", "DetectorType": 8,
        "DetectorName": detector, "DetectorDescription": "synthetic", "DecoderName": "PLAIN", "Verified": False,
        "VerificationFromCache": False, "Raw": SENTINEL, "RawV2": SENTINEL, "Redacted": SENTINEL,
        "ExtraData": {"value": SENTINEL}, "StructuredData": None,
    }


FAKE_TRUFFLEHOG = r"""#!/usr/bin/env bash
# Fake trufflehog: records each call and replays the prepared output.
set -euo pipefail
for arg in "$@"; do
  if [ "${arg}" = "--version" ]; then
    echo "trufflehog ${FAKE_VERSION}" >&2
    exit 0
  fi
done
{
  printf '{"cwd":"%s","args":[' "$(pwd -P)"
  sep=""; for arg in "$@"; do printf '%s"%s"' "${sep}" "${arg}"; sep=","; done
  printf ']}\n'
} >> "${FAKE_DIR}/calls.jsonl"
cat "${FAKE_DIR}/stdout"
printf '{"level":"info-0","msg":"running source"}\n{"level":"info-0","msg":"finished scanning"}\n' >&2
exit "${FAKE_RC}"
"""


class GateHarness(unittest.TestCase):
    """Runs the real script in a temporary Git repository with a fake trufflehog."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trufflehog-gate-")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.repo, "scripts"))
        shutil.copy2(SCRIPT, os.path.join(self.repo, "scripts", "run_trufflehog.sh"))
        self.write("README.txt", "clean\n")
        self.git("init", "-q", "-b", "main")
        self.commit("initial")
        self.fake = os.path.join(self.tmp, "fake")
        os.makedirs(os.path.join(self.fake, "bin"))
        tool = os.path.join(self.fake, "bin", "trufflehog")
        with open(tool, "w", encoding="utf-8") as fh:
            fh.write(FAKE_TRUFFLEHOG)
        os.chmod(tool, os.stat(tool).st_mode | stat.S_IXUSR)
        self.work = os.path.join(self.tmp, "runner-temp")
        os.makedirs(self.work)
        self.set_output([], 0)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *args: str):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=self.repo,
                       check=True, capture_output=True)

    def write(self, name: str, text: str):
        with open(os.path.join(self.repo, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    def commit(self, message: str):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def set_output(self, results: list, rc: int, raw: str | None = None):
        with open(os.path.join(self.fake, "stdout"), "w", encoding="utf-8") as fh:
            fh.write(raw if raw is not None else "".join(json.dumps(r) + "\n" for r in results))
        self.rc = rc

    def run_gate(self, version: str = TRUFFLEHOG_VERSION, path: str | None = None, extra_env: dict | None = None):
        env = dict(os.environ)
        env.update({"FAKE_DIR": self.fake, "FAKE_VERSION": version, "FAKE_RC": str(self.rc),
                    "RUNNER_TEMP": self.work,
                    "PATH": path if path is not None else f"{self.fake}/bin:{os.environ['PATH']}"})
        env.update(extra_env or {})
        return subprocess.run(["/bin/bash", os.path.join(self.repo, "scripts", "run_trufflehog.sh")], env=env,
                              capture_output=True, text=True, timeout=60)

    def calls(self) -> list[dict]:
        path = os.path.join(self.fake, "calls.jsonl")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh]


class GateTests(GateHarness):
    def assert_no_sentinel(self, result):
        self.assertNotIn(SENTINEL, result.stdout)
        self.assertNotIn(SENTINEL, result.stderr)

    def test_clean_history_passes(self):
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("secret scan of the Git history (not drift detection)", result.stdout)
        self.assertIn(f"TruffleHog version: trufflehog {TRUFFLEHOG_VERSION}", result.stdout)
        self.assertIn("no secrets found", result.stdout)
        self.assertIn("trufflehog: info-0 finished scanning", result.stdout)
        self.assertEqual(os.listdir(self.work), [])  # private work directory removed

    def test_exact_invocation_from_repository_root(self):
        self.assertEqual(self.run_gate().returncode, 0)
        calls = self.calls()
        self.assertEqual(len(calls), 1)
        repo = os.path.realpath(self.repo)
        self.assertEqual(calls[0]["cwd"], repo)
        self.assertEqual(calls[0]["args"], ["git", f"file://{repo}", "--no-update", "--no-verification", "--json",
                                            "--fail"])

    def test_findings_fail_with_183_and_print_metadata_only(self):
        self.set_output([finding(), finding("PrivateKey", "keys/id_rsa", 7, "abcdef0123456789")], 183)
        result = self.run_gate()
        self.assertEqual(result.returncode, 183, result.stdout + result.stderr)
        self.assertIn("FINDING  detector=Github  verified=false  file=config.txt  line=1  commit=834bf2f5aa11",
                      result.stdout)
        self.assertIn("FINDING  detector=PrivateKey  verified=false  file=keys/id_rsa  line=7  commit=abcdef012345",
                      result.stdout)
        self.assertIn("2 secret finding(s)", result.stderr)
        self.assert_no_sentinel(result)
        self.assertNotIn("probe@example.invalid", result.stdout + result.stderr)  # no author email

    def test_scanner_error_is_not_a_finding(self):
        for rc in (1, 2):
            with self.subTest(rc=rc):
                self.set_output([], rc)
                result = self.run_gate()
                self.assertEqual(result.returncode, rc)
                self.assertIn("scanner error, not a finding", result.stderr)

    def test_inconsistent_exit_codes_fail(self):
        self.set_output([finding()], 0)
        result = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("exited 0 but reported 1 result", result.stderr)
        self.assert_no_sentinel(result)
        self.set_output([], 183)
        result = self.run_gate()
        self.assertEqual(result.returncode, 183)
        self.assertIn("no result could be read", result.stderr)

    def test_unreadable_output_fails(self):
        for raw in ("{not json", '"just a string"\n', '[1, 2]\n'):
            with self.subTest(raw=raw):
                self.set_output([], 0, raw=raw)
                result = self.run_gate()
                self.assertEqual(result.returncode, 1)
                self.assertIn("cannot be evaluated safely", result.stderr)

    def test_prerequisites(self):
        with self.subTest("wrong version"):
            result = self.run_gate(version="3.97.8")
            self.assertEqual(result.returncode, 1)
            self.assertIn("TruffleHog 3.97.9 is required (got 'trufflehog 3.97.8')", result.stderr)
            self.assertEqual(self.calls(), [])
        with self.subTest("no trufflehog"):
            result = self.run_gate(path="/usr/bin:/bin")
            self.assertEqual(result.returncode, 1)
            self.assertIn("trufflehog was not found", result.stderr)
        with self.subTest("no jq"):
            result = self.run_gate(path=f"{self.fake}/bin")  # jq check runs before any external command
            self.assertEqual(result.returncode, 1)
            self.assertIn("jq is required", result.stderr)
            self.assertEqual(self.calls(), [])

    def test_ignore_annotation_in_files_fails(self):
        self.write("config.txt", f"token = x  # {IGNORE_ANNOTATION}\n")
        self.commit("annotated")
        result = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("not allowed in the repository files", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_ignore_annotation_in_history_fails(self):
        self.write("config.txt", f"token = x  # {IGNORE_ANNOTATION}\n")
        self.commit("annotated")
        os.remove(os.path.join(self.repo, "config.txt"))
        self.commit("annotation removed again")
        result = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("anywhere in the Git history", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_work_dir_inside_repository_fails(self):
        result = self.run_gate(extra_env={"RUNNER_TEMP": self.repo})
        self.assertEqual(result.returncode, 1)
        self.assertIn("must be outside the repository", result.stderr)


class StaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script_code = code_lines(read(SCRIPT))
        cls.wf = yaml.safe_load(read(SECURITY_SCAN))
        cls.job = cls.wf["jobs"]["trufflehog"]
        cls.job_text = yaml.safe_dump(cls.job)

    def test_script_pins_and_flags(self):
        self.assertTrue(os.access(SCRIPT, os.X_OK))
        code = self.script_code
        self.assertIn("set -euo pipefail", code)
        self.assertIn(f'TRUFFLEHOG_VERSION="{TRUFFLEHOG_VERSION}"', code)
        self.assertIn('trufflehog --no-update --version', code)
        self.assertIn('trufflehog git "file://${ROOT_DIR}"', code)
        for flag in ("--no-update", "--no-verification", "--json", "--fail"):
            self.assertIn(f"  {flag} \\", code)
        self.assertIn('>"${results}" 2>"${scan_log}"', code)  # raw JSON never reaches the log
        self.assertLess(code.index("command -v jq"), code.index("trufflehog --no-update --version"))
        self.assertLess(code.index("git grep"), code.index('trufflehog git "file://'))
        for forbidden in FORBIDDEN:
            self.assertNotIn(forbidden, code, forbidden)

    def test_script_prints_no_secret_fields(self):
        printing = [ln for ln in self.script_code.splitlines() if "FINDING" in ln or "trufflehog: " in ln]
        self.assertTrue(printing)
        for field in ("Raw", "RawV2", "Redacted", "ExtraData", "StructuredData", "email"):
            for line in printing:
                self.assertNotIn(field, line, field)

    def test_trufflehog_job(self):
        job = self.job
        self.assertIn("not drift detection", job["name"])
        for key in ("permissions", "environment", "outputs", "continue-on-error", "if", "env", "needs", "services",
                    "container"):
            self.assertNotIn(key, job)
        steps = job["steps"]
        self.assertEqual([s.get("uses") for s in steps], ["actions/checkout@v4", None, None])
        self.assertEqual(steps[0]["with"], {"fetch-depth": 0, "persist-credentials": False})
        install = steps[1]
        self.assertEqual(install["env"], {"PINNED_TRUFFLEHOG_VERSION": TRUFFLEHOG_VERSION,
                                          "PINNED_TRUFFLEHOG_LINUX_SHA256": TRUFFLEHOG_LINUX_SHA256})
        run = install["run"]
        self.assertIn("set -euo pipefail", run)
        self.assertIn('archive="trufflehog_${PINNED_TRUFFLEHOG_VERSION}_linux_amd64.tar.gz"', run)
        self.assertIn("https://github.com/trufflesecurity/trufflehog/releases/download/"
                      "v${PINNED_TRUFFLEHOG_VERSION}/${archive}", run)
        self.assertLess(run.index("sha256sum -c -"), run.index("tar -xzf"))  # verified before unpacking
        self.assertEqual(steps[2]["run"].strip(), "./scripts/run_trufflehog.sh")
        self.assertNotIn("env", steps[2])
        for step in steps:
            for key in ("continue-on-error", "if"):
                self.assertNotIn(key, step)

    def test_job_is_credential_free_without_drift_semantics(self):
        for forbidden in ("id-token", "azure/login", "ARM_", "TF_VAR_", "AZURE_", "secrets.", "GITHUB_TOKEN",
                          "github.token", "drift_detected", "drift_status", "drift-report", "issues",
                          "upload-artifact", "actions/cache", "sarif", "security-events", "write", "docker") + FORBIDDEN:
            self.assertNotIn(forbidden, self.job_text, forbidden)
        self.assertEqual(self.wf["permissions"], {"contents": "read"})
        self.assertEqual(sorted(self.wf["jobs"]), ["tflint", "trivy-config", "trufflehog"])

    def test_no_ignore_annotation_in_repository(self):
        tracked = subprocess.run(["git", "grep", "-l", "-I", "-F", IGNORE_ANNOTATION], cwd=ROOT,
                                 capture_output=True, text=True)
        self.assertEqual(tracked.stdout, "", tracked.stdout)

    def test_existing_workflows_have_no_trufflehog(self):
        for name in ("drift-detection.yml", "terraform-auth-test.yml"):
            self.assertNotIn("trufflehog", read(os.path.join(WORKFLOWS, name)).lower(), name)

    def test_readme_documents_scanner(self):
        text = read(README)
        for needle in (TRUFFLEHOG_VERSION, TRUFFLEHOG_LINUX_SHA256, "./scripts/run_trufflehog.sh", "183",
                       "--no-update", "--no-verification", "fetch-depth: 0"):
            self.assertIn(needle, text, needle)


if __name__ == "__main__":
    unittest.main()
