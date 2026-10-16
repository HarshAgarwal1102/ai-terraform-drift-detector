"""Task 12.1A (P5, P5b, C8): scripts/generate_plan_json.sh never puts plan values or jq error
text into a failure reason.

A failure reason reaches the public job log three times: the script's stderr, the
`::error::` line of Generate Plan Evidence, and the Analyze Drift failure line (the engine
copies the manifest's failure_reason into the report). These tests run the REAL script
with a fake `terraform` (tests/test_auth_test_workflow.py) that prints a random sentinel
in every output, and plans whose values carry the sentinel. Nothing reaches Azure.

Plans used: the committed real plan tests/fixtures/plan_evidence/external_drift (real
Terraform 1.14.7 output) and copies of it with deliberately broken header fields.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
sys.path.insert(0, str(TESTS))

from test_auth_test_workflow import FAKE_TERRAFORM, JQ_SHIM, _exe  # noqa: E402
from test_investigation_workflow import _analyze  # noqa: E402

pytestmark = pytest.mark.integration

SCRIPT = ROOT / "scripts" / "generate_plan_json.sh"
BASH = shutil.which("bash") or "/bin/bash"
JQ = shutil.which("jq")
REAL_PLAN = TESTS / "fixtures" / "plan_evidence" / "external_drift" / "plan.sanitized.json"
VALUE_FREE_HEADER_REASON = ("unsupported format_version (major must be 1);"
                            "terraform_version does not match the pinned version;"
                            "errored is not false;complete is not true")


@pytest.fixture
def sentinel() -> str:
    return f"E6-SENTINEL-{secrets.token_hex(8)}"


@pytest.fixture
def engine_shim(tmp_path) -> Path:
    shim = tmp_path / "engine-shim"
    shim.mkdir()
    _exe(shim / "drift-engine", f'#!/bin/sh\nexec "{sys.executable}" -m drift_engine.cli "$@"\n')
    return shim


def run_script(tmp_path: Path, sentinel: str, plan, *, plan_rc=2, jq_fail_on=None):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _exe(bindir / "terraform", FAKE_TERRAFORM)
    path = [str(bindir)]
    if jq_fail_on:
        shim = tmp_path / "jqshim"
        shim.mkdir()
        _exe(shim / "jq", JQ_SHIM)
        path.append(str(shim))
    path += [str(Path(JQ).parent), "/usr/bin", "/bin"]
    tf_dir = tmp_path / "tf"
    tf_dir.mkdir()
    (tf_dir / "dev.tfvars").write_text('environment = "dev"\n')
    show = tmp_path / "show.json"
    show.write_text(json.dumps(plan) if isinstance(plan, dict) else Path(plan).read_text())
    art = tmp_path / "evidence"  # absolute, new, outside the repository
    env = {"PATH": os.pathsep.join(path), "HOME": str(tmp_path), "SENTINEL": sentinel,
           "FAKE_CALLS": str(tmp_path / "calls.log"), "FAKE_PLAN_RC": str(plan_rc), "FAKE_SHOW_FILE": str(show),
           "REAL_JQ": JQ, "JQ_FAIL_ON": jq_fail_on or "", "ARTIFACT_DIR": str(art), "TF_DIR": str(tf_dir),
           "TERRAFORM_VERSION": "1.14.7"}
    proc = subprocess.run([BASH, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)
    manifest = json.loads((art / "detection_run.json").read_text())
    return proc, manifest, art


def broken_header(sentinel: str) -> dict:
    plan = json.loads(REAL_PLAN.read_text())
    plan.update({"format_version": f"9.{sentinel}", "terraform_version": sentinel, "errored": sentinel,
                 "complete": {"nested": sentinel}})
    return plan


def assert_public_text_clean(proc, manifest, sentinel):
    assert sentinel not in proc.stdout, proc.stdout
    assert sentinel not in proc.stderr, proc.stderr
    assert sentinel not in json.dumps(manifest)


def test_real_plan_succeeds_and_plan_output_stays_in_plan_log(tmp_path, sentinel):
    proc, manifest, art = run_script(tmp_path, sentinel, REAL_PLAN, plan_rc=2)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert manifest["outcome"] == "succeeded" and manifest["plan_exit_code"] == 2
    assert_public_text_clean(proc, manifest, sentinel)
    assert sentinel in (art / "plan.log").read_text()


def test_jq_gate_failure_has_a_fixed_reason(tmp_path, sentinel):
    # P5: the gate call is the only jq call with --argjson; the shim fails it quoting the sentinel.
    proc, manifest, art = run_script(tmp_path, sentinel, REAL_PLAN, plan_rc=2, jq_fail_on="--argjson")
    assert proc.returncode == 1
    assert manifest["outcome"] == "failed" and manifest["failure_stage"] == "integrity"
    assert manifest["failure_reason"] == "integrity gate could not evaluate plan.json"
    assert_public_text_clean(proc, manifest, sentinel)
    assert sentinel in (art / "plan.log").read_text()  # jq's stderr: runner-local only


def test_integrity_violation_messages_are_value_free(tmp_path, sentinel):
    # P5b: header fields carrying the sentinel produce fixed messages; details only in plan.log.
    proc, manifest, art = run_script(tmp_path, sentinel, broken_header(sentinel), plan_rc=2)
    assert proc.returncode == 1
    assert manifest["failure_stage"] == "integrity"
    assert manifest["failure_reason"] == VALUE_FREE_HEADER_REASON
    assert_public_text_clean(proc, manifest, sentinel)
    assert sentinel in (art / "plan.log").read_text()


def test_pending_mismatch_reason_carries_a_count_only(tmp_path, sentinel):
    proc, manifest, _ = run_script(tmp_path, sentinel, REAL_PLAN, plan_rc=0)
    assert proc.returncode == 1
    assert manifest["failure_reason"] == "plan exit 0 but plan.json contains 1 pending change(s)"
    assert_public_text_clean(proc, manifest, sentinel)


@pytest.mark.parametrize("plan_rc, reason", [
    (1, "terraform plan exited 1 (error); any plan file written is not valid evidence"),
    (3, "terraform plan exited unexpectedly with 3"),
])
def test_plan_failure_reasons_are_fixed(tmp_path, sentinel, plan_rc, reason):
    proc, manifest, _ = run_script(tmp_path, sentinel, REAL_PLAN, plan_rc=plan_rc)
    assert proc.returncode == 1
    assert manifest["failure_stage"] == "plan" and manifest["failure_reason"] == reason
    assert_public_text_clean(proc, manifest, sentinel)


@pytest.mark.parametrize("case", ["jq_gate_failure", "broken_header"])
def test_analyze_drift_failure_line_stays_clean(tmp_path, sentinel, engine_shim, case):
    # C8: the second print path. Analyze Drift runs after a failed evidence step whenever a
    # manifest exists and prints the report's failure reason, copied from the manifest.
    if case == "jq_gate_failure":
        proc, manifest, art = run_script(tmp_path, sentinel, REAL_PLAN, plan_rc=2, jq_fail_on="--argjson")
        expected = "integrity gate could not evaluate plan.json"
    else:
        proc, manifest, art = run_script(tmp_path, sentinel, broken_header(sentinel), plan_rc=2)
        expected = VALUE_FREE_HEADER_REASON
    assert proc.returncode == 1 and (art / "plan.json").exists()
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "drift-detection.yml").read_text())
    proc, outputs, _ = _analyze(wf, tmp_path, engine_shim, art / "plan.json", art / "detection_run.json",
                                evidence="failure")
    assert proc.returncode != 0 and outputs["drift_detected"] == "unknown"
    assert expected in proc.stdout
    assert sentinel not in proc.stdout + proc.stderr + json.dumps(outputs)
