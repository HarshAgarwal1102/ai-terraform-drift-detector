"""Task 9B.5: drift investigation in CI (drift-detection.yml, scripts/investigation_analysis.sh,
scripts/fetch_prior_drift_reports.py, ci/azure-constraints.txt).

Runner-realistic: workflow run: blocks and the scripts are executed with fake tools on PATH
(venv, pip, timeout, a fake GitHub API on loopback). The real `drift-engine investigate` runs
where no Azure call is needed (no drift) or where the Azure credential is unavailable (no `az`
on PATH, an unroutable proxy): it can never reach Azure or the network. Every identifier is
synthetic.
"""

from __future__ import annotations

import http.server
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import zipfile
from pathlib import Path

import pytest
import yaml

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
sys.path.insert(0, str(TESTS))

from test_activity_logs import RG, FakeSource, page  # noqa: E402
from test_investigation import REPO, at_time, in_sync, nsg_drift, public_report_bytes, report_bytes  # noqa: E402
from test_investigation_public import _PubBase, inv  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "drift-detection.yml"
SCRIPT = ROOT / "scripts" / "investigation_analysis.sh"
FETCH = ROOT / "scripts" / "fetch_prior_drift_reports.py"
AZURE_CONSTRAINTS = ROOT / "ci" / "azure-constraints.txt"
PYPROJECT = ROOT / "pyproject.toml"
BASH = shutil.which("bash") or "/bin/bash"
TOKEN = "ghs_synthetic_token_for_tests_only"
OWNER_REPO = "o/r"
CURRENT_RUN = 500
OUTPUT_LINE = re.compile(r"^investigation_status=(succeeded|incomplete|failed) investigation_failure=[a-z_]+ "
                         r"investigation_publishable=(true|false) investigation_detail=[a-z_=,0-9]+( outcome=.*)?$")
STATUS_KEYS = {"investigation_status", "investigation_failure", "investigation_detail", "investigation_publishable"}


@pytest.fixture(scope="module")
def wf() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def steps_by_name(job: dict) -> dict:
    return {s["name"]: s for s in job["steps"]}


def _exe(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def _outputs(path: Path) -> dict:
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)


# --------------------------------------------------------------------------- workflow structure (G10)


def test_plan_and_analyze_settings_and_outputs(wf):
    job = wf["jobs"]["plan-and-analyze"]
    assert job["timeout-minutes"] == 45
    assert job["permissions"] == {"id-token": "write", "contents": "read", "actions": "read"}
    outputs = job["outputs"]
    for key in STATUS_KEYS:
        assert outputs[key] == f"${{{{ steps.investigation.outputs.{key} }}}}"
    assert outputs["investigation_upload_outcome"] == "${{ steps.investigation_upload.outcome }}"
    names = [s["name"] for s in job["steps"]]
    assert names[names.index("Analyze Drift"):] == ["Analyze Drift", "Upload Drift Report", "Drift Investigation",
                                                    "Upload Drift Investigation", "Infracost Cost Estimate",
                                                    "Upload Infracost Report"]


def test_analyze_writes_internal_runner_only_and_public_in_place(wf):
    steps = steps_by_name(wf["jobs"]["plan-and-analyze"])
    run = steps["Analyze Drift"]["run"]
    assert 'internal_dir="${RUNNER_TEMP}/drift-internal"' in run and 'mkdir -m 0700 "${internal_dir}"' in run
    assert '--output "${internal_dir}/drift_report.json"' in run and '--public-output "${report}"' in run
    assert 'report="${ARTIFACT_DIR}/drift_report.json"' in run
    upload = steps["Upload Drift Report"]
    assert "if" not in upload  # default success(): a failed Analyze Drift step (UNKNOWN) uploads nothing
    assert [p.strip() for p in upload["with"]["path"].splitlines() if p.strip()] == [
        "${{ runner.temp }}/drift/drift_report.json",
                                              "${{ runner.temp }}/drift/detection_run.json"]
    text = WORKFLOW.read_text(encoding="utf-8")
    uploads = [s["with"]["path"] for job in wf["jobs"].values() for s in job.get("steps", [])
               if s.get("uses") == "actions/upload-artifact@v4"]
    for forbidden in ("drift-internal", "restricted", "anchors", "investigation-venv", "plan.json", "tfplan"):
        assert not any(forbidden in path for path in uploads), forbidden
    assert text.count("drift-internal") == 3  # the comment, the directory, and the investigation step's input


def test_investigation_step(wf):
    step = steps_by_name(wf["jobs"]["plan-and-analyze"])["Drift Investigation"]
    assert step["id"] == "investigation"
    assert step["if"] == ("${{ steps.upload.outcome == 'success' && (steps.analyze.outputs.drift_detected == 'true' "
                          "|| steps.analyze.outputs.drift_detected == 'false') }}")
    assert "timeout-minutes" not in step and "continue-on-error" not in step  # never fails plan-and-analyze
    assert step["env"] == {
        "GH_TOKEN": "${{ github.token }}",
        "DRIFT_ENGINE_PIPELINE_PRINCIPAL": "${{ secrets.AZURE_CLIENT_ID }}",
        "DRIFT_DETECTED": "${{ steps.analyze.outputs.drift_detected }}",
        "PLAN_JSON": "${{ runner.temp }}/drift/plan.json",
        "MANIFEST": "${{ runner.temp }}/drift/detection_run.json",
        "INTERNAL_REPORT": "${{ runner.temp }}/drift-internal/drift_report.json",
        "PUBLIC_REPORT": "${{ runner.temp }}/drift/drift_report.json",
        "REPOSITORY": "${{ github.repository }}",
        "CURRENT_RUN_ID": "${{ github.run_id }}",
    }
    run = step["run"]
    assert "./scripts/investigation_analysis.sh || script_rc=$?" in run and run.rstrip().endswith("exit 0")
    assert "set -x" not in run


def test_investigation_upload(wf):
    upload = steps_by_name(wf["jobs"]["plan-and-analyze"])["Upload Drift Investigation"]
    assert upload["id"] == "investigation_upload" and upload["continue-on-error"] is True
    assert upload["if"] == "${{ steps.investigation.outputs.investigation_publishable == 'true' }}"
    assert upload["with"] == {"name": "drift-investigation-${{ github.run_id }}",
                              "path": "${{ runner.temp }}/investigation/public/drift_investigation.json",
                              "retention-days": 30, "if-no-files-found": "error", "overwrite": True}


def test_exactly_two_always_exit_zero_steps(wf):
    always = [s["name"] for job in wf["jobs"].values() for s in job.get("steps", [])
              if s.get("run", "").rstrip().endswith("exit 0")]
    assert always == ["Drift Investigation", "Infracost Cost Estimate"]


def test_investigation_job(wf):
    job = wf["jobs"]["investigation"]
    assert job["needs"] == ["preflight", "plan-and-analyze"]
    assert job["if"] == ("${{ !cancelled() && (needs.plan-and-analyze.outputs.drift_detected == 'true' || "
                         "needs.plan-and-analyze.outputs.drift_detected == 'false') }}")
    assert job["permissions"] == {"contents": "read"} and job["timeout-minutes"] == 10
    assert [s["name"] for s in job["steps"]] == [
        "Checkout Code", "Setup Python", "Install drift-engine", "Download Drift Report",
        "Download Drift Investigation", "Verify Drift Investigation", "Investigation Summary",
        "Require Investigation Success"]
    steps = steps_by_name(job)
    assert steps["Download Drift Report"]["with"]["name"] == "drift-report-${{ github.run_id }}"
    assert steps["Download Drift Investigation"]["with"]["name"] == "drift-investigation-${{ github.run_id }}"
    verify = steps["Verify Drift Investigation"]["run"]
    assert '--report "${RUNNER_TEMP}/drift-report/drift_report.json"' in verify  # the downloaded PUBLIC report
    assert steps["Require Investigation Success"]["if"] == "${{ !cancelled() }}"
    assert steps["Investigation Summary"]["if"] == "${{ !cancelled() }}"
    text = json.dumps(job)
    for forbidden in ("secrets.", "id-token", "azure/login", "ARM_", "github-token", "GH_TOKEN", "continue-on-error"):
        assert forbidden not in text, forbidden
    # isolation: no other job reads the investigation; report keeps its needs
    for name in ("issues", "cost", "report", "preflight"):
        assert "investigation" not in json.dumps(wf["jobs"][name]), name
    assert wf["jobs"]["report"]["needs"] == ["preflight", "plan-and-analyze"]


# --------------------------------------------------------------------------- Analyze Drift, executed


@pytest.fixture
def engine_shim(tmp_path) -> Path:
    shim = tmp_path / "engine-shim"
    shim.mkdir()
    _exe(shim / "drift-engine", f'#!/bin/sh\nexec "{sys.executable}" -m drift_engine.cli "$@"\n')
    return shim


def _analyze(wf, tmp_path: Path, shim: Path, plan: Path, manifest: Path, evidence: str = "success"):
    runner = tmp_path / f"runner{len(list(tmp_path.glob('runner*')))}"
    (runner / "drift").mkdir(parents=True)
    shutil.copy(plan, runner / "drift" / "plan.json")
    shutil.copy(manifest, runner / "drift" / "detection_run.json")
    gh = runner / "gh_output"
    gh.write_text("")
    env = {"PATH": f"{shim}:/usr/bin:/bin", "RUNNER_TEMP": str(runner), "ARTIFACT_DIR": str(runner / "drift"),
           "EVIDENCE_OUTCOME": evidence, "GITHUB_OUTPUT": str(gh), "DRIFT_ENVIRONMENT": "dev", "HOME": str(tmp_path)}
    script = runner / "step.sh"
    script.write_text(steps_by_name(wf["jobs"]["plan-and-analyze"])["Analyze Drift"]["run"])
    proc = subprocess.run([BASH, "-e", str(script)], env=env, capture_output=True, text=True, timeout=120)
    return proc, _outputs(gh), runner


def _fixture(name: str) -> tuple[Path, Path]:
    base = TESTS / "fixtures" / "plan_evidence" / name
    return base / "plan.sanitized.json", base / "detection_run.json"


@pytest.mark.parametrize("name, drift", [("external_drift", "true"), ("in_sync", "false"),
                                         ("external_deletion", "true")])
def test_analyze_step_layout(wf, tmp_path, engine_shim, name, drift):
    proc, outputs, runner = _analyze(wf, tmp_path, engine_shim, *_fixture(name))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert outputs["drift_detected"] == drift
    public = json.loads((runner / "drift" / "drift_report.json").read_text())
    internal_path = runner / "drift-internal" / "drift_report.json"
    assert public["public_version"] == "1" and "public_version" not in json.loads(internal_path.read_text())
    assert stat.S_IMODE((runner / "drift-internal").stat().st_mode) == 0o700
    assert sorted(p.name for p in (runner / "drift").iterdir()) == ["detection_run.json", "drift_report.json",
                                                                     "plan.json"]  # the internal one is never here
    assert "/subscriptions/" not in (runner / "drift" / "drift_report.json").read_text()


def test_analyze_projection_failure_is_unknown_and_uploads_nothing(wf, tmp_path, engine_shim):
    plan, manifest = _fixture("external_drift")
    doc = json.loads(manifest.read_text())
    doc["backend_key"] = "state-of-erin@example.com"  # copied into report.run: fails the projection (P3)
    bad = tmp_path / "manifest.json"
    bad.write_text(json.dumps(doc))
    proc, outputs, runner = _analyze(wf, tmp_path, engine_shim, plan, bad)
    assert proc.returncode != 0  # the step fails, so Upload Drift Report (default success()) is skipped
    assert outputs["drift_detected"] == "unknown" and outputs["engine_exit_code"] == "70"
    assert not (runner / "drift" / "drift_report.json").exists()
    assert not (runner / "drift-internal" / "drift_report.json").exists()
    assert "erin@example.com" not in proc.stdout + proc.stderr


def test_analyze_failed_evidence_is_unknown(wf, tmp_path, engine_shim):
    proc, outputs, _ = _analyze(wf, tmp_path, engine_shim, *_fixture("external_drift"), evidence="failure")
    assert proc.returncode != 0 and outputs["drift_detected"] == "unknown"


# --------------------------------------------------------------------------- investigation_analysis.sh, executed


class _Gen(_PubBase):
    """Real investigations (Task 9B.2 / 9B.3 pipeline over fake Activity Log sources)."""

    def runTest(self):
        pass

    def inv_run(self, entries=None, rows=(), *, paths=None, **kwargs):
        paths = paths or self.plan(entries if entries is not None else nsg_drift())
        self.paths = paths
        return super().inv_run(entries, rows, paths=paths, **kwargs)


@pytest.fixture(scope="module")
def scenarios():
    """name -> (plan, manifest, internal report bytes, public report bytes, public investigation text)."""
    gen = _Gen()
    gen.setUp()
    out = {}

    def keep(name, result):
        text, problems = inv.publish(result.document)
        assert problems == []
        plan, manifest = gen.paths
        out[name] = (plan, manifest, report_bytes(gen.paths), public_report_bytes(gen.paths), text)
    keep("complete", gen.inv_run(rows=gen.log.tags(at_time(8))))
    keep("incomplete", gen.inv_run(rows=[__import__("test_activity_logs").ev(
        9999, ts="2026-10-02T07:30:00Z", operationName={"value": "bad name"})]))
    keep("evidence_failed", gen.inv_run(rows=None, source=FakeSource({RG: [__import__("test_activity_logs").al.SourceError(
        "throttled", 429)]})))
    keep("input_failed", gen.inv_run(anchors=os.path.join(gen.tmp, "missing-anchors"), rows=gen.log.tags(at_time(8))))
    keep("unbindable", gen.inv_run(report=b"{}", source=__import__("test_activity_logs").NoCallSource(), rows=None))
    binding = json.loads(out["evidence_failed"][4])
    binding["failure"] = {"stage": "binding", "reason": "evidence_mismatch"}
    for resource in binding["resources"]:
        resource["reason"] = "evidence_mismatch"
    out["binding_failed"] = out["evidence_failed"][:4] + (json.dumps(binding, indent=2, sort_keys=True) + "\n",)
    leaky = json.loads(out["complete"][4])
    leaky["resources"][0]["address"] = "carol@example.com"
    out["leaky"] = out["complete"][:4] + (json.dumps(leaky),)
    no_drift = gen.inv_run(paths=gen.plan(in_sync()), source=__import__("test_activity_logs").NoCallSource())
    keep("no_drift", no_drift)
    yield out
    gen.doCleanups()


class Harness:
    """scripts/investigation_analysis.sh with a fake venv/pip/timeout and a real or scripted drift-engine."""

    def __init__(self, tmp: Path) -> None:
        self.tmp, self.n = tmp, 0
        self.ctrl = tmp / "ctrl"
        self.ctrl.mkdir()
        self.shim = tmp / "shim"
        self.shim.mkdir()
        self.site = tmp / "fake-site"
        self.site.mkdir()
        real = sys.executable
        # venv creator: writes bin/python (pip controlled; everything else = real python -S, stdlib only +
        # fake dist-infos for the pin check) and bin/drift-engine (the scripted or real engine)
        _exe(self.shim / "python3", f'''#!{real}
import os, sys
ctrl = {str(self.ctrl)!r}
if sys.argv[1:3] != ["-m", "venv"]:
    os.execv({real!r}, [{real!r}] + sys.argv[1:])
if os.path.exists(os.path.join(ctrl, "venv_fail")):
    sys.exit(1)
b = os.path.join(sys.argv[3], "bin")
os.makedirs(b)
with open(os.path.join(b, "python"), "w") as fh:
    fh.write('#!/bin/sh\\nif [ "$1" = "-m" ] && [ "$2" = "pip" ]; then echo "$@" >> {self.ctrl}/pip_calls; '
             'exit $(cat {self.ctrl}/pip_rc 2>/dev/null || echo 0); fi\\n'
             'PYTHONPATH={self.site} exec {real} -S "$@"\\n')
with open(os.path.join(b, "drift-engine"), "w") as fh:
    fh.write('#!/bin/sh\\nexec {real} {self.tmp}/engine.py "$@"\\n')
for name in ("python", "drift-engine"):
    os.chmod(os.path.join(b, name), 0o755)
''')
        _exe(self.shim / "timeout", f'''#!{real}
import os, sys
with open({str(self.ctrl / "timeout_calls")!r}, "a") as fh:
    fh.write(sys.argv[1] + "\\n")
if os.path.exists({str(self.ctrl / "timeout_hit")!r}):
    sys.exit(124)
os.execvp(sys.argv[2], sys.argv[2:])
''')
        (tmp / "engine.py").write_text(f'''
import json, os, sys
ctrl = {str(self.ctrl)!r}
with open(os.path.join(ctrl, "engine_calls"), "a") as fh:
    fh.write(json.dumps({{"argv": sys.argv[1:], "gh_token": "GH_TOKEN" in os.environ or "GITHUB_TOKEN" in os.environ}}) + "\\n")
mode = open(os.path.join(ctrl, "mode")).read().strip() if os.path.exists(os.path.join(ctrl, "mode")) else "real"
if sys.argv[1] == "investigation-check" or mode == "real":
    from drift_engine.cli import main
    sys.exit(main(sys.argv[1:]))
spec = json.load(open(os.path.join(ctrl, "mode")))
args = sys.argv[1:]
def value(flag):
    return args[args.index(flag) + 1]
if spec.get("public") is not None:
    open(value("--public-output"), "w").write(spec["public"])
if spec.get("evidence") is not None:
    open(value("--evidence-output"), "w").write(spec["evidence"])
sys.exit(spec["rc"])
''')

    def run(self, scenario, *, drift="true", mode="real", pip_rc=0, venv_fail=False, timeout_hit=False,
            token=TOKEN, drop=None, api="http://127.0.0.1:9", extra_site=None):
        self.n += 1
        runner = self.tmp / f"runner{self.n}"
        runner.mkdir()
        for name in ("mode", "pip_rc", "venv_fail", "timeout_hit", "engine_calls", "timeout_calls", "pip_calls"):
            (self.ctrl / name).unlink(missing_ok=True)
        if mode != "real":
            (self.ctrl / "mode").write_text(json.dumps(mode))
        (self.ctrl / "pip_rc").write_text(str(pip_rc))
        if venv_fail:
            (self.ctrl / "venv_fail").write_text("")
        if timeout_hit:
            (self.ctrl / "timeout_hit").write_text("")
        for item in self.site.iterdir():
            shutil.rmtree(item)
        if extra_site:
            meta = self.site / f"{extra_site[0]}-{extra_site[1]}.dist-info"
            meta.mkdir()
            (meta / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {extra_site[0]}\nVersion: {extra_site[1]}\n")
        plan, manifest, internal, public_report, _ = scenario
        files = {"INTERNAL_REPORT": runner / "internal.json", "PUBLIC_REPORT": runner / "public_report.json"}
        files["INTERNAL_REPORT"].write_bytes(internal)
        files["PUBLIC_REPORT"].write_bytes(public_report)
        gh = runner / "gh_output"
        gh.write_text("")
        env = {"PATH": f"{self.shim}:/usr/bin:/bin", "HOME": str(self.tmp), "RUNNER_TEMP": str(runner),
               "GITHUB_OUTPUT": str(gh), "PLAN_JSON": str(plan), "MANIFEST": str(manifest),
               "INTERNAL_REPORT": str(files["INTERNAL_REPORT"]), "PUBLIC_REPORT": str(files["PUBLIC_REPORT"]),
               "DRIFT_DETECTED": drift, "REPOSITORY": OWNER_REPO, "CURRENT_RUN_ID": str(CURRENT_RUN),
               "GITHUB_API_URL": api, "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "127.0.0.1,localhost",
               "PYTHON": str(self.shim / "python3")}
        if token:
            env["GH_TOKEN"] = token
        for name in drop or ():
            env.pop(name)
        proc = subprocess.run([BASH, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=300)
        calls = [json.loads(line) for line in (self.ctrl / "engine_calls").read_text().splitlines()] \
            if (self.ctrl / "engine_calls").exists() else []
        return proc, _outputs(gh), runner, calls


@pytest.fixture
def harness(tmp_path):
    return Harness(tmp_path)


def _assert_clean(proc, outputs, runner, publishable: bool):
    assert proc.returncode == 0, proc.stdout + proc.stderr  # always exits 0
    assert set(outputs) == STATUS_KEYS
    lines = [line for line in proc.stdout.splitlines() if line.startswith("investigation_status=")]
    assert len(lines) == 1 and OUTPUT_LINE.match(lines[0]), proc.stdout
    text = proc.stdout + proc.stderr + json.dumps(outputs)
    for secret in (TOKEN, "alice@example.com", "carol@example.com", "/subscriptions/"):
        assert secret not in text
    public = runner / "investigation" / "public" / "drift_investigation.json"
    assert public.exists() is publishable  # never left behind unless publishable
    restricted = runner / "investigation" / "restricted"
    if restricted.exists():
        assert stat.S_IMODE(restricted.stat().st_mode) == 0o700


SCRIPTED = {
    # (scenario, mode spec) -> (status, failure, publishable)
    "succeeded": ("complete", {"rc": 0, "public": "complete"}, ("succeeded", "none", "true")),
    "incomplete": ("incomplete", {"rc": 1, "public": "incomplete"}, ("incomplete", "incomplete", "true")),
    "evidence_failed": ("evidence_failed", {"rc": 1, "public": "evidence_failed"}, ("failed", "evidence_failed", "true")),
    "binding_failed": ("binding_failed", {"rc": 1, "public": "binding_failed"},
                       ("failed", "evidence_binding_failed", "true")),
    "input_failed": ("input_failed", {"rc": 1, "public": "input_failed"}, ("failed", "input_failed", "true")),
    "unbindable": ("unbindable", {"rc": 1, "public": "unbindable"}, ("failed", "public_check_failed", "false")),
    "leak": ("leaky", {"rc": 0, "public": "leaky"}, ("failed", "public_check_failed", "false")),
    "usage": ("complete", {"rc": 2}, ("failed", "investigate_usage", "false")),
    "internal": ("complete", {"rc": 70}, ("failed", "investigate_internal_error", "false")),
    "write": ("complete", {"rc": 73}, ("failed", "write_failed", "false")),
    "other": ("complete", {"rc": 9}, ("failed", "investigate_internal_error", "false")),
    "rc1_without_public": ("complete", {"rc": 1}, ("failed", "investigate_internal_error", "false")),
    "rc0_but_incomplete": ("incomplete", {"rc": 0, "public": "incomplete"}, ("failed", "investigate_internal_error",
                                                                              "false")),
}


@pytest.mark.parametrize("name", list(SCRIPTED))
def test_outcome_mapping(harness, scenarios, name, api_server):
    key, spec, expected = SCRIPTED[name]
    spec = dict(spec)
    if "public" in spec:
        spec["public"] = scenarios[spec["public"]][4]
    proc, outputs, runner, calls = harness.run(scenarios[key], drift="false", mode=spec)
    assert (outputs["investigation_status"], outputs["investigation_failure"],
            outputs["investigation_publishable"]) == expected, proc.stdout + proc.stderr
    _assert_clean(proc, outputs, runner, expected[2] == "true")
    assert not any(c["gh_token"] for c in calls)  # the token reaches only the anchor fetch


def test_detail_codes_come_from_the_runner_only_evidence(harness, scenarios):
    evidence = json.dumps({"scopes": [{"error": {"code": "throttled"}}, {"error": {"code": "throttled"}},
                                      {"error": {"code": "authorization_failed"}}, {"error": None},
                                      {"error": {"code": "Not A Code!"}}],
                           "failure": {"stage": "query", "reason": "all_queries_failed"}})
    proc, outputs, runner, _ = harness.run(scenarios["evidence_failed"], drift="false",
                                           mode={"rc": 1, "public": scenarios["evidence_failed"][4],
                                                 "evidence": evidence})
    assert outputs["investigation_detail"] == "all_queries_failed=1,authorization_failed=1,throttled=2"
    _assert_clean(proc, outputs, runner, True)


def test_detail_codes_count_the_auth_reason(harness, scenarios):
    # Task 9B.5: the fixed auth_reason of authentication_failed scopes; anything else is ignored
    evidence = json.dumps({"scopes": [{"error": {"code": "authentication_failed", "http_status": None,
                                                 "auth_reason": "assertion_expired"}},
                                      {"error": {"code": "authentication_failed", "http_status": 401,
                                                 "auth_reason": "arm_rejected"}},
                                      {"error": {"code": "authentication_failed",
                                                 "auth_reason": "AADSTS700024 user@example.invalid"}},
                                      {"error": {"code": "authentication_failed", "auth_reason": "none"}}],
                           "failure": {"stage": "query", "reason": "all_queries_failed"}})
    proc, outputs, runner, _ = harness.run(scenarios["evidence_failed"], drift="false",
                                           mode={"rc": 1, "public": scenarios["evidence_failed"][4],
                                                 "evidence": evidence})
    assert outputs["investigation_detail"] == ("all_queries_failed=1,auth_arm_rejected=1,auth_assertion_expired=1,"
                                               "authentication_failed=4")  # unlisted reasons are ignored (review L3)
    assert OUTPUT_LINE.fullmatch(proc.stdout.strip().splitlines()[-1])
    for secret in ("AADSTS", "700024", "user@example.invalid"):
        assert secret not in proc.stdout + proc.stderr + json.dumps(outputs)
    _assert_clean(proc, outputs, runner, True)


def test_script_auth_reason_allowlist_matches_the_engine():
    from drift_engine.activity_logs import AUTH_REASONS
    listed = re.search(r'if reason in \(([^)]*)\):', SCRIPT.read_text(encoding="utf-8")).group(1)
    assert tuple(re.findall(r'"([a-z_]+)"', listed)) == AUTH_REASONS


def test_timeout_is_bounded_in_the_script(harness, scenarios):
    proc, outputs, runner, _ = harness.run(scenarios["complete"], drift="false", mode={"rc": 0}, timeout_hit=True)
    assert (outputs["investigation_status"], outputs["investigation_failure"]) == ("failed", "timeout")
    assert (harness.ctrl / "timeout_calls").read_text().split() == ["1500"]
    _assert_clean(proc, outputs, runner, False)


@pytest.mark.parametrize("kwargs, failure", [
    ({"venv_fail": True}, "install_failed"),
    ({"pip_rc": 1}, "install_failed"),
    ({"extra_site": ("azure-core", "0.0.1")}, "pin_mismatch"),
    ({"drop": ["INTERNAL_REPORT"]}, "inputs_missing"),
])
def test_setup_failures_run_nothing(harness, scenarios, kwargs, failure):
    proc, outputs, runner, calls = harness.run(scenarios["complete"], drift="false", mode={"rc": 0}, **kwargs)
    assert (outputs["investigation_status"], outputs["investigation_failure"]) == ("failed", failure)
    assert calls == []  # investigate never ran
    _assert_clean(proc, outputs, runner, False)


def test_pinned_install_command(harness, scenarios):
    harness.run(scenarios["complete"], drift="false", mode={"rc": 0, "public": scenarios["complete"][4]})
    pip = (harness.ctrl / "pip_calls").read_text().split()
    assert pip[:6] == ["-m", "pip", "install", "--disable-pip-version-check", "--no-input", "-c"]
    assert pip[6] == str(AZURE_CONSTRAINTS) and pip[7] == f"{ROOT}[azure]"


def test_stale_directories_are_refused(harness, scenarios):
    runner = harness.tmp / "runner1"
    (runner / "investigation").mkdir(parents=True)
    harness.n = 0  # run() reuses runner1
    (runner / "investigation" / "public").mkdir()
    shutil.rmtree(runner)
    runner.mkdir()
    (runner / "investigation-venv").mkdir()
    proc = subprocess.run([BASH, str(SCRIPT)], env={"PATH": "/usr/bin:/bin", "RUNNER_TEMP": str(runner),
                                                     "GITHUB_OUTPUT": str(runner / "o"), "PLAN_JSON": str(SCRIPT),
                                                     "MANIFEST": str(SCRIPT), "INTERNAL_REPORT": str(SCRIPT),
                                                     "PUBLIC_REPORT": str(SCRIPT), "DRIFT_DETECTED": "false",
                                                     "REPOSITORY": OWNER_REPO, "CURRENT_RUN_ID": "1"},
                          capture_output=True, text=True)
    assert proc.returncode == 0 and _outputs(runner / "o")["investigation_failure"] == "inputs_missing"


# --------------------------------------------------------------------------- real investigate runs


def test_no_drift_runs_the_real_investigation_without_azure_or_fetch(harness, scenarios, api_server):
    proc, outputs, runner, calls = harness.run(scenarios["no_drift"], drift="false", api=api_server.url)
    assert (outputs["investigation_status"], outputs["investigation_failure"],
            outputs["investigation_publishable"], outputs["investigation_detail"]) == (
        "succeeded", "none", "true", "none"), proc.stdout + proc.stderr
    _assert_clean(proc, outputs, runner, True)
    assert api_server.requests == []  # no anchor fetch for a run without drift
    assert [c["argv"][0] for c in calls] == ["investigate", "investigation-check"]
    assert "--anchors" not in calls[0]["argv"] and calls[0]["argv"][calls[0]["argv"].index("--report") + 1].endswith(
        "internal.json")
    assert calls[1]["argv"][calls[1]["argv"].index("--report") + 1].endswith("public_report.json")
    public = json.loads((runner / "investigation" / "public" / "drift_investigation.json").read_text())
    assert (public["outcome"], public["resources"]) == ("complete", [])
    restricted = runner / "investigation" / "restricted" / "drift_investigation.restricted.json"
    assert stat.S_IMODE(restricted.stat().st_mode) == 0o600
    assert "outcome=complete resources=0" in proc.stdout


def test_drifted_run_fetches_anchors_and_fails_bindably_without_azure(harness, scenarios, api_server, tmp_path):
    """Real investigate with three fetched candidates; no `az` on PATH -> credential_unavailable -> a failed but
    bindable investigation that is uploaded (decision 1)."""
    api_server.add_run(401, report=_public_anchor_report(tmp_path))  # a valid in-sync public report
    api_server.add_run(402, report=report_bytes(_anchor_plan(tmp_path, 402)))  # internal format: report_invalid
    api_server.add_run(403, expired=True)  # run.json without a report: report_invalid
    proc, outputs, runner, calls = harness.run(scenarios["complete"], api=api_server.url)
    assert (outputs["investigation_status"], outputs["investigation_failure"], outputs["investigation_publishable"],
            outputs["investigation_detail"]) == ("failed", "evidence_failed", "true", "all_queries_failed=1,credential_unavailable=1"), \
        proc.stdout + proc.stderr
    _assert_clean(proc, outputs, runner, True)
    public = json.loads((runner / "investigation" / "public" / "drift_investigation.json").read_text())
    assert public["anchors"] == {"examined": 3, "accepted": 1, "rejected": {"report_invalid": 2}}
    assert calls[0]["argv"][calls[0]["argv"].index("--anchors") + 1].endswith("investigation/anchors")
    assert "anchor_fetch=ok candidates=3" in proc.stdout and "reports=2" in proc.stdout
    assert not api_server.storage_authorized  # the token never reached the storage redirect target


def test_anchor_fetch_failure_fails_closed(harness, scenarios, api_server):
    api_server.fail_listing = True
    proc, outputs, runner, calls = harness.run(scenarios["complete"], api=api_server.url)
    assert (outputs["investigation_status"], outputs["investigation_failure"]) == ("failed", "anchor_fetch_failed")
    assert calls == []  # decision 2: investigate does not run without the required fetch
    _assert_clean(proc, outputs, runner, False)
    proc, outputs, runner, calls = harness.run(scenarios["complete"], api=api_server.url, token="")
    assert outputs["investigation_failure"] == "anchor_fetch_failed" and calls == []


# --------------------------------------------------------------------------- fake GitHub API


def _zip(report: bytes | None, *, extra: dict | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        if report is not None:
            zf.writestr("drift_report.json", report)
        zf.writestr("detection_run.json", b"{}")
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return buffer.getvalue()


class FakeGitHub:
    def __init__(self) -> None:
        self.runs, self.artifacts, self.archives = [], {}, {}
        self.requests, self.storage_authorized, self.fail_listing, self.flaky = [], False, False, 0
        api = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, code, body=b"", headers=None):
                self.send_response(code)
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                path = self.path.split("?")[0]
                api.requests.append((path, self.headers.get("Authorization")))
                if path.startswith("/storage/"):
                    api.storage_authorized |= self.headers.get("Authorization") is not None
                    return self._send(200, api.archives[path.rsplit("/", 1)[1]])
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    return self._send(401)
                if path == f"/repos/{OWNER_REPO}/actions/workflows/drift-detection.yml/runs":
                    if api.fail_listing:
                        return self._send(500)
                    if api.flaky:
                        api.flaky -= 1
                        return self._send(503)
                    return self._send(200, json.dumps({"workflow_runs": api.runs}).encode())
                match = re.fullmatch(rf"/repos/{OWNER_REPO}/actions/runs/(\d+)/artifacts", path)
                if match:
                    return self._send(200, json.dumps({"artifacts": api.artifacts.get(int(match.group(1)), [])}).encode())
                match = re.fullmatch(rf"/repos/{OWNER_REPO}/actions/artifacts/(\d+)/zip", path)
                if match:
                    return self._send(302, headers={"Location": f"{api.url}/storage/{match.group(1)}"})
                return self._send(404)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def add_run(self, run_id, *, report=None, expired=False, created="2026-10-02T06:00:00Z", event="schedule",
                branch="main", path=".github/workflows/drift-detection.yml", archive=None, size=None, attempt=1,
                name=None):
        self.runs.append({"id": run_id, "run_attempt": attempt, "event": event, "head_branch": branch, "path": path,
                          "created_at": created})
        body = archive if archive is not None else _zip(report)
        self.archives[str(run_id)] = body
        self.artifacts[run_id] = [{"name": name or f"drift-report-{run_id}", "expired": expired,
                                   "size_in_bytes": size if size is not None else len(body),
                                   "archive_download_url": f"{self.url}/repos/{OWNER_REPO}/actions/artifacts/"
                                                           f"{run_id}/zip"}]


@pytest.fixture
def api_server():
    server = FakeGitHub()
    yield server
    server.server.shutdown()


def _anchor_plan(tmp: Path, run: int) -> tuple[str, str]:
    gen = _Gen()
    gen.setUp()
    gen.tmp = str(tmp / f"anchor-plan-{run}")
    os.makedirs(gen.tmp, exist_ok=True)
    return gen.plan(in_sync(), run_id=f"github-{run}-1", started="2026-10-02T06:00:00Z",
                    finished="2026-10-02T06:01:00Z", plan_ts="2026-10-02T06:00:30Z")


def _public_anchor_report(tmp: Path) -> bytes:
    return public_report_bytes(_anchor_plan(tmp, 401))


# --------------------------------------------------------------------------- fetch_prior_drift_reports.py


def _load_fetch():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_fetch_under_test", FETCH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fetch_cli(api_server, out: Path, token=TOKEN, *args):
    env = {"PATH": "/usr/bin:/bin", "GITHUB_API_URL": api_server.url, "NO_PROXY": "127.0.0.1"}
    if token:
        env["GH_TOKEN"] = token
    return subprocess.run([sys.executable, str(FETCH), "--repository", OWNER_REPO, "--current-run-id",
                           str(CURRENT_RUN), "--output-dir", str(out), "--now", "2026-10-05T00:00:00Z", *args],
                          env=env, capture_output=True, text=True, timeout=120)


def test_run_selection_filters_and_limit():
    fetch = _load_fetch()
    now = fetch._parse_time("2026-10-05T00:00:00Z")
    base = {"run_attempt": 1, "event": "schedule", "head_branch": "main", "path": ".github/workflows/drift-detection.yml"}
    runs = [dict(base, id=i, created_at=f"2026-10-0{1 + i % 3}T00:{i % 60:02d}:00Z") for i in range(1, 61)]
    runs += [dict(base, id=900, event="push", created_at="2026-10-04T00:00:00Z"),
             dict(base, id=901, head_branch="feature", created_at="2026-10-04T00:00:00Z"),
             dict(base, id=902, path=".github/workflows/other.yml", created_at="2026-10-04T00:00:00Z"),
             dict(base, id=CURRENT_RUN, created_at="2026-10-04T00:00:00Z"),
             dict(base, id=903, created_at="2026-09-01T00:00:00Z"),  # outside 30 days
             dict(base, id=904, created_at="2026-10-06T00:00:00Z"),  # in the future
             dict(base, id=905, event="workflow_dispatch", created_at="2026-10-04T12:00:00Z")]
    selected = fetch.select_runs({"workflow_runs": runs}, CURRENT_RUN, now)
    assert len(selected) == 50 and selected[0]["id"] == 905
    assert not {900, 901, 902, CURRENT_RUN, 903, 904} & {r["id"] for r in selected}
    keys = [(fetch._parse_time(r["created_at"]), r["id"]) for r in selected]
    assert keys == sorted(keys, reverse=True)
    with pytest.raises(fetch.ListingError):
        fetch.select_runs({"workflow_runs": "x"}, CURRENT_RUN, now)


def test_archive_extraction_rules():
    fetch = _load_fetch()
    assert fetch.extract_report(_zip(b'{"a": 1}')) == b'{"a": 1}'
    bad = {"missing": _zip(None), "nested": _zip(None, extra={"x/drift_report.json": b"{}"}), "not_zip": b"PK-no"}
    for name, archive in bad.items():
        with pytest.raises(fetch.CandidateError) as info:
            fetch.extract_report(archive)
        assert info.value.reason == "archive_invalid", name
    big = _zip(b"0" * (fetch.MAX_REPORT_BYTES + 1))
    with pytest.raises(fetch.CandidateError) as info:
        fetch.extract_report(big)
    assert info.value.reason == "artifact_too_large"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        link = zipfile.ZipInfo("drift_report.json")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(link, "/etc/passwd")
    with pytest.raises(fetch.CandidateError):
        fetch.extract_report(buffer.getvalue())


def test_fetch_writes_candidates_and_skips_bad_artifacts(api_server, tmp_path):
    good = b'{"x": 1}'
    api_server.add_run(10, report=good, created="2026-10-04T00:00:00Z")
    api_server.add_run(11, report=good, expired=True)
    api_server.add_run(12, report=good, size=fetch_max() + 1)
    api_server.add_run(13, archive=b"not a zip")
    api_server.add_run(14, report=good, name="drift-report-999")  # no artifact named for this run
    api_server.add_run(15, report=good, attempt=2, event="workflow_dispatch")
    out = tmp_path / "anchors"
    proc = _fetch_cli(api_server, out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.strip() == ("anchor_fetch=ok candidates=6 listed=6 reports=2 skipped_archive_invalid=1 "
                                   "skipped_artifact_expired=1 skipped_artifact_missing=1 skipped_artifact_too_large=1")
    assert sorted(p.name for p in out.iterdir()) == [f"run-{i}-{1 if i != 15 else 2}" for i in range(10, 16)]
    assert (out / "run-10-1" / "drift_report.json").read_bytes() == good
    assert not (out / "run-11-1" / "drift_report.json").exists()
    meta = json.loads((out / "run-15-2" / "run.json").read_text())
    assert meta == {"id": 15, "run_attempt": 2, "repository": OWNER_REPO, "head_branch": "main",
                    "event": "workflow_dispatch", "workflow_path": ".github/workflows/drift-detection.yml"}
    assert stat.S_IMODE(out.stat().st_mode) == 0o700
    assert not api_server.storage_authorized
    assert TOKEN not in proc.stdout + proc.stderr and "127.0.0.1" not in proc.stdout


def fetch_max() -> int:
    return _load_fetch().MAX_ZIP_BYTES


def test_fetch_retries_then_fails_closed(api_server, tmp_path, monkeypatch):
    fetch = _load_fetch()
    api_server.flaky = 2
    github = fetch.GitHub(api_server.url, TOKEN, sleep=lambda s: None)
    out = tmp_path / "a"
    out.mkdir()
    counts = fetch.fetch(github, OWNER_REPO, CURRENT_RUN, str(out), fetch._parse_time("2026-10-05T00:00:00Z"))
    assert counts["candidates"] == 0 and api_server.flaky == 0  # two 503s retried
    api_server.fail_listing = True
    with pytest.raises(fetch.ListingError):
        fetch.fetch(github, OWNER_REPO, CURRENT_RUN, str(out), fetch._parse_time("2026-10-05T00:00:00Z"))
    proc = _fetch_cli(api_server, tmp_path / "b")
    assert proc.returncode == 1 and proc.stdout.strip() == "anchor_fetch=failed reason=listing_failed"


@pytest.mark.parametrize("token, args, setup", [("", (), None), (TOKEN, ("--now", "garbage"), None),
                                                 (TOKEN, (), "nonempty")])
def test_fetch_usage_errors(api_server, tmp_path, token, args, setup):
    out = tmp_path / "anchors"
    if setup == "nonempty":
        out.mkdir()
        (out / "stale").write_text("x")
    proc = _fetch_cli(api_server, out, token, *args)
    assert proc.returncode == 2 and api_server.requests == []


def test_fetched_candidates_feed_the_anchor_trust_checks(api_server, tmp_path):
    """The fetch output is exactly what `investigate` reads (G9): a valid public in-sync report is accepted, an
    internal-format report and a missing report are report_invalid."""
    api_server.add_run(401, report=_public_anchor_report(tmp_path))
    api_server.add_run(402, report=report_bytes(_anchor_plan(tmp_path, 402)))
    api_server.add_run(403, expired=True)
    out = tmp_path / "anchors"
    assert _fetch_cli(api_server, out).returncode == 0
    gen = _Gen()
    gen.setUp()
    current = json.loads(report_bytes(gen.plan(nsg_drift())))
    selection = inv.select_anchor_runs(str(out), current, OWNER_REPO)
    assert [a.run_id for a in selection.accepted] == ["github-401-1"]
    assert dict(selection.rejected) == {"run-402-1": "report_invalid", "run-403-1": "report_invalid"}
    gen.doCleanups()


# --------------------------------------------------------------------------- investigation job steps, executed


def _job_step(wf, name, tmp_path, env):
    gh_summary = tmp_path / "summary"
    gh_summary.write_text("")
    full = {"PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin", "RUNNER_TEMP": str(tmp_path),
            "GITHUB_STEP_SUMMARY": str(gh_summary), "GITHUB_RUN_ID": str(CURRENT_RUN), **env}
    step = steps_by_name(wf["jobs"]["investigation"])[name]
    script = tmp_path / "step.sh"
    script.write_text(step["run"])
    proc = subprocess.run([BASH, "-e", str(script)], env=full, capture_output=True, text=True, timeout=60)
    return proc, gh_summary.read_text()


def _require(wf, tmp_path, drift, status, upload, verify):
    return _job_step(wf, "Require Investigation Success", tmp_path, {
        "DRIFT_DETECTED": drift, "INVESTIGATION_STATUS": status, "INVESTIGATION_FAILURE": "x",
        "INVESTIGATION_UPLOAD_OUTCOME": upload, "VERIFY_OUTCOME": verify})


# G18 (PROJECT_PLAN.md Phase 9B, amends decision 1): the four status cases, on drifted and no-drift runs.
@pytest.mark.parametrize("drift, status, upload, verify, ok", [
    # succeeded
    ("true", "succeeded", "success", "success", True),
    ("false", "succeeded", "success", "success", True),
    ("true", "succeeded", "failure", "skipped", False),
    ("true", "succeeded", "success", "failure", False),
    # incomplete: a finding, passes with a warning, but only when uploaded and verified
    ("true", "incomplete", "success", "success", True),
    ("true", "incomplete", "failure", "skipped", False),
    ("true", "incomplete", "success", "failure", False),
    # failed: always fails, including decision 1's uploaded failed-but-bindable document
    ("true", "failed", "success", "success", False),
    ("false", "failed", "success", "success", False),
    ("true", "failed", "skipped", "skipped", False),
    ("false", "failed", "skipped", "skipped", False),
    # never ran: required for a drifted run; not required (intentional skip) for a no-drift run
    ("true", "", "skipped", "skipped", False),
    ("false", "", "skipped", "skipped", True),
    ("false", "", "", "", True),
    ("unknown", "", "", "", False),  # unreachable (the job needs true/false); fails closed
    ("", "", "", "", False),
])
def test_require_investigation_success(wf, tmp_path, drift, status, upload, verify, ok):
    proc, summary = _require(wf, tmp_path, drift, status, upload, verify)
    assert (proc.returncode == 0) is ok, proc.stdout
    assert ("::warning::" in proc.stdout) is (ok and status == "incomplete")
    assert ("not required: no drift" in summary) is (ok and status == "")
    if not ok:
        assert "::error::" in proc.stdout and "Drift result unaffected." in proc.stdout


@pytest.mark.parametrize("status, upload, verify", [
    ("succeeded", "success", "success"), ("succeeded", "failure", "skipped"), ("succeeded", "success", "failure"),
    ("incomplete", "success", "success"), ("incomplete", "failure", "skipped"), ("incomplete", "success", "failure"),
    ("failed", "success", "success"), ("failed", "skipped", "skipped"),
])
def test_require_investigation_success_never_depends_on_drift_once_run(wf, tmp_path, status, upload, verify):
    # G18: drift_detected decides only whether a missing investigation was required.
    drifted, _ = _require(wf, tmp_path, "true", status, upload, verify)
    clean, _ = _require(wf, tmp_path, "false", status, upload, verify)
    assert drifted.returncode == clean.returncode


def test_summary_is_counts_only(wf, tmp_path, scenarios):
    (tmp_path / "drift-investigation").mkdir()
    (tmp_path / "drift-investigation" / "drift_investigation.json").write_text(scenarios["complete"][4])
    proc, summary = _job_step(wf, "Investigation Summary", tmp_path, {
        "INVESTIGATION_STATUS": "succeeded", "INVESTIGATION_FAILURE": "none", "INVESTIGATION_DETAIL": "none",
        "INVESTIGATION_UPLOAD_OUTCOME": "success", "VERIFY_OUTCOME": "success"})
    assert proc.returncode == 0, proc.stderr
    assert "| Verdicts | `sole_capable_operation=1` |" in summary and "| Resources | 1 |" in summary
    from drift_engine.investigation_public import leak_findings
    assert leak_findings(summary.replace(f"drift-investigation-{CURRENT_RUN}", "")) == []
    for secret in ("alice@example.com", "Microsoft.", "module."):
        assert secret not in summary  # no operation names or addresses either
    proc, summary = _job_step(wf, "Investigation Summary", tmp_path, {
        "INVESTIGATION_STATUS": "x; rm -rf /", "VERIFY_OUTCOME": "skipped"})
    assert "| Status | `invalid` |" in summary


def test_investigation_step_block_maps_a_script_crash(wf, tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    _exe(repo / "scripts" / "investigation_analysis.sh", "#!/bin/sh\nexit 3\n")
    runner = tmp_path / "runner"
    (runner / "investigation" / "public").mkdir(parents=True)
    (runner / "investigation" / "public" / "drift_investigation.json").write_text("{}")
    gh = tmp_path / "gh"
    gh.write_text("")
    script = tmp_path / "step.sh"
    script.write_text(steps_by_name(wf["jobs"]["plan-and-analyze"])["Drift Investigation"]["run"])
    proc = subprocess.run([BASH, "-e", str(script)], cwd=repo, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "RUNNER_TEMP": str(runner), "GITHUB_OUTPUT": str(gh)})
    assert proc.returncode == 0
    assert _outputs(gh) == {"investigation_status": "failed", "investigation_failure": "script_error",
                            "investigation_detail": "none", "investigation_publishable": "false"}
    assert not (runner / "investigation" / "public" / "drift_investigation.json").exists()


# --------------------------------------------------------------------------- G18 CI result policy

LOCK = "terraform/environments/dev/.terraform.lock.hcl"
FAKE_PLAN_SCRIPT = """#!/bin/sh
# Stands in for scripts/generate_plan_json.sh: writes the given evidence, then exits SCRIPT_RC.
[ -z "${FIXTURE_PLAN:-}" ] || cp "${FIXTURE_PLAN}" "${ARTIFACT_DIR}/plan.json"
[ -z "${FIXTURE_MANIFEST:-}" ] || cp "${FIXTURE_MANIFEST}" "${ARTIFACT_DIR}/detection_run.json"
[ -z "${TOUCH_LOCK:-}" ] || echo "# changed" >> "${TF_DIR}/.terraform.lock.hcl"
exit "${SCRIPT_RC}"
"""


def _git_repo(path: Path) -> Path:
    (path / "scripts").mkdir(parents=True)
    (path / LOCK).parent.mkdir(parents=True)
    (path / LOCK).write_text("# lock\n")
    _exe(path / "scripts" / "generate_plan_json.sh", FAKE_PLAN_SCRIPT)
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]
    env = {"PATH": os.environ["PATH"], "HOME": str(path), "GIT_CONFIG_NOSYSTEM": "1"}
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "fixture"]):
        subprocess.run(git + args, cwd=path, env=env, check=True, capture_output=True)
    return path


def _evidence(wf, tmp_path, *, rc=0, plan=None, manifest=None, touch_lock=False, var_file="dev.tfvars",
              stale_manifest=None):
    repo = _git_repo(tmp_path / "repo")
    art = tmp_path / "evidence" / "drift"
    art.mkdir(parents=True)
    if stale_manifest is not None:  # left over from an earlier run: must never be read as evidence
        shutil.copy(stale_manifest, art / "detection_run.json")
    gh = tmp_path / "evidence" / "gh_output"
    gh.write_text("")
    tools = os.pathsep.join(sorted({str(Path(shutil.which(t)).parent) for t in ("git", "jq")}))
    env = {"PATH": f"{tools}:/usr/bin:/bin", "HOME": str(tmp_path), "GIT_CONFIG_NOSYSTEM": "1",
           "WORK_DIR": "terraform/environments/dev", "VAR_FILE": var_file, "ARTIFACT_DIR": str(art),
           "GITHUB_WORKSPACE": str(repo), "GITHUB_OUTPUT": str(gh), "SCRIPT_RC": str(rc),
           "FIXTURE_PLAN": str(plan or ""), "FIXTURE_MANIFEST": str(manifest or ""),
           "TOUCH_LOCK": "1" if touch_lock else ""}
    script = tmp_path / "evidence" / "step.sh"
    script.write_text(steps_by_name(wf["jobs"]["plan-and-analyze"])["Generate Plan Evidence"]["run"])
    proc = subprocess.run([BASH, "-e", str(script)], cwd=repo, env=env, capture_output=True, text=True, timeout=60)
    return proc, _outputs(gh), art


# Plan exit 0/2 are valid evidence; drift is decided by the classification alone (exit 2 = pending changes).
@pytest.mark.parametrize("name, plan_rc, drift", [
    ("in_sync", "0", "false"), ("converged_drift", "0", "true"),
    ("external_drift", "2", "true"), ("external_deletion", "2", "true"),
    ("config_change", "2", "false"), ("output_only_change", "2", "false"),
])
def test_plan_exit_0_and_2_are_valid_and_classification_decides_drift(wf, tmp_path, engine_shim, name, plan_rc,
                                                                     drift):
    plan, manifest = _fixture(name)
    proc, outputs, art = _evidence(wf, tmp_path, plan=plan, manifest=manifest)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert outputs["plan_exit_code"] == plan_rc and outputs["outcome"] == "succeeded"
    assert outputs["manifest_present"] == "true" and "::error::" not in proc.stdout
    proc, outputs, _ = _analyze(wf, tmp_path, engine_shim, art / "plan.json", art / "detection_run.json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert outputs["drift_detected"] == drift
    assert outputs["drift_status"] == ("detected" if drift == "true" else "none")
    assert ("::warning::Drift detected" in proc.stdout) is (drift == "true")


@pytest.mark.parametrize("case", ["plan_failed", "unusable_artifact_dir", "unexpected_plan_exit_code",
                                  "lock_modified", "non_dev_var_file"])
def test_evidence_failures_fail_the_step_and_drift_is_unknown(wf, tmp_path, engine_shim, case):
    plan, manifest = _fixture("external_drift")
    failed_manifest = TESTS / "fixtures" / "plan_evidence" / "failed_run" / "detection_run.json"
    odd = tmp_path / "odd_manifest.json"
    odd.write_text(json.dumps({**json.loads(manifest.read_text()), "plan_exit_code": 3}))
    kwargs = {
        "plan_failed": {"rc": 1, "manifest": failed_manifest},
        "unusable_artifact_dir": {"rc": 64, "stale_manifest": manifest},
        "unexpected_plan_exit_code": {"rc": 0, "plan": plan, "manifest": odd},
        "lock_modified": {"rc": 0, "plan": plan, "manifest": manifest, "touch_lock": True},
        "non_dev_var_file": {"var_file": "prod.tfvars", "plan": plan, "manifest": manifest},
    }[case]
    proc, outputs, art = _evidence(wf, tmp_path, **kwargs)
    assert proc.returncode != 0
    assert "Drift status: UNKNOWN." in proc.stdout
    if case == "unusable_artifact_dir":
        assert outputs["manifest_present"] == "false"  # Analyze Drift is skipped; the job output falls back
        assert wf["jobs"]["plan-and-analyze"]["outputs"]["drift_detected"] == \
            "${{ steps.analyze.outputs.drift_detected || 'unknown' }}"
    elif (art / "detection_run.json").exists():  # Analyze Drift runs after a failed evidence step
        proc, outputs, _ = _analyze(wf, tmp_path, engine_shim, art / "plan.json" if (art / "plan.json").exists()
                                    else plan, art / "detection_run.json", evidence="failure")
        assert proc.returncode != 0 and outputs["drift_detected"] == "unknown"


def _conditions(wf):
    for job_name, job in wf["jobs"].items():
        if "if" in job:
            yield job_name, job["if"]
        for step in job.get("steps", []):
            if "if" in step:
                yield f"{job_name} / {step['name']}", step["if"]


def test_g18_no_condition_treats_drift_differently_from_no_drift(wf):
    gated = []
    for where, cond in _conditions(wf):
        if "drift_detected" in cond:
            gated.append(where)
            assert "drift_detected == 'true'" in cond and "drift_detected == 'false'" in cond, where
        for token in ("has_drift", "drift_status", "plan_exit_code"):
            assert token not in cond, where
    assert gated == ["plan-and-analyze / Drift Investigation", "plan-and-analyze / Infracost Cost Estimate",
                     "issues", "cost", "investigation"]


def test_g18_only_known_steps_read_the_drift_result(wf):
    # Every step that sees the drift result is executed by a test showing drift alone never fails it:
    # Analyze Drift and Generate Plan Evidence (above), Require Investigation Success (above), Run Summary
    # (below), Drift Investigation (outcome mapping) and Manage Drift Issues (tests/test_github_automation.py).
    readers = set()
    for job_name, job in wf["jobs"].items():
        for step in job.get("steps", []):
            text = json.dumps({"env": step.get("env", {}), "run": step.get("run", "")})
            if re.search(r"drift_detected|DRIFT_DETECTED|has_drift|plan_exit_code|plan_rc", text):
                readers.add(f"{job_name} / {step['name']}")
    assert readers == {"plan-and-analyze / Generate Plan Evidence", "plan-and-analyze / Analyze Drift",
                       "plan-and-analyze / Drift Investigation", "issues / Manage Drift Issues",
                       "investigation / Require Investigation Success", "report / Run Summary"}


def _run_summary(wf, tmp_path, drift, stage="success"):
    summary = tmp_path / "run_summary.md"
    summary.write_text("")
    stages = "; ".join(f"{name}={stage if name == 'Analyze Drift' else 'success'}" for name in (
        "Require main branch", "Checkout Code", "Generate Plan Evidence", "Analyze Drift", "Upload Drift Report"))
    env = {"PATH": "/usr/bin:/bin", "GITHUB_STEP_SUMMARY": str(summary), "GITHUB_RUN_ID": str(CURRENT_RUN),
           "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_SHA": "0" * 40, "TERRAFORM_VERSION": "1.14.7",
           "DRIFT_ENVIRONMENT": "dev", "WORK_DIR": "terraform/environments/dev", "VAR_FILE": "dev.tfvars",
           "PLAN_EXIT_CODE": "2", "DRIFT_STATUS": "detected" if drift == "true" else "none",
           "DRIFT_DETECTED": drift, "CLASSIFICATION_COUNTS": "{}", "STAGE_OUTCOMES": stages,
           "JOB_RESULTS": "Preflight job=success; Terraform Plan & Drift Analysis job=success",
           "INIT_OUTCOME": "success", "VALIDATE_OUTCOME": "success", "UPLOAD_OUTCOME": "success"}
    script = tmp_path / "run_summary.sh"
    script.write_text(steps_by_name(wf["jobs"]["report"])["Run Summary"]["run"])
    proc = subprocess.run([BASH, "-e", str(script)], env=env, capture_output=True, text=True, timeout=60)
    return proc, summary.read_text()


@pytest.mark.parametrize("drift", ["true", "false"])
def test_run_summary_reports_drift_as_a_valid_result(wf, tmp_path, drift):
    proc, summary = _run_summary(wf, tmp_path, drift)
    assert proc.returncode == 0, proc.stderr
    assert "| Result | **VALID** |" in summary and f"| drift_detected | `{drift}` |" in summary
    assert "| Plan exit code | `2`" in summary
    proc, summary = _run_summary(wf, tmp_path, drift, stage="failure")  # a process error: never "no drift"
    assert proc.returncode == 0  # reporting only; the failed step turned the run red
    assert "FAILED - drift status UNKNOWN" in summary and "| drift_detected | `unknown` |" in summary


# --------------------------------------------------------------------------- ci/azure-constraints.txt


def azure_pins() -> dict[str, str]:
    pins = {}
    for line in AZURE_CONSTRAINTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*==[0-9][0-9A-Za-z.+!-]*", line), line
        name, version = line.split("==")
        key = re.sub(r"[-_.]+", "-", name).lower()
        assert key not in pins, f"duplicate pin {name}"
        pins[key] = version
    return pins


def test_azure_pins_are_exact_and_agree_with_the_ai_pins():
    pins = azure_pins()
    for required in ("azure-identity", "azure-mgmt-monitor", "azure-core", "pydantic", "pyyaml", "msal"):
        assert required in pins, required
    from test_ai_cli import constraint_pins
    ai = constraint_pins()
    assert {k: v for k, v in pins.items() if k in ai} == {k: v for k, v in ai.items() if k in pins}


def test_azure_constraints_equal_the_complete_azure_closure():
    """Every distribution `drift-engine[azure]` needs, from pyproject.toml and the installed metadata, is pinned
    exactly, and nothing else is (the test environment is installed with these constraints)."""
    import tomllib
    from importlib.metadata import PackageNotFoundError, requires, version
    from packaging.requirements import Requirement

    norm = lambda name: re.sub(r"[-_.]+", "-", name).lower()
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    pending = [Requirement(spec) for spec in project["dependencies"] + project["optional-dependencies"]["azure"]]
    closure: dict[str, list] = {}
    expanded: set[tuple[str, str]] = set()
    while pending:
        req = pending.pop()
        name = norm(req.name)
        closure.setdefault(name, []).append(req)
        for extra in [""] + sorted(req.extras):
            if (name, extra) in expanded:
                continue
            expanded.add((name, extra))
            try:
                children = requires(req.name) or []
            except PackageNotFoundError:
                pytest.skip(f"{req.name} (drift-engine[azure]) is not installed")
            for child in map(Requirement, children):
                if child.marker is None or child.marker.evaluate({"extra": extra}):
                    pending.append(child)
    pins = azure_pins()
    assert sorted(set(closure) - set(pins)) == [], "required but not pinned"
    assert sorted(set(pins) - set(closure)) == [], "pinned but not required by drift-engine[azure]"
    outside = [f"{req} (pinned {pins[name]})" for name, reqs in closure.items() for req in reqs
               if not req.specifier.contains(pins[name], prereleases=True)]
    assert outside == []
    mismatched = [f"{name}: installed {version(name)}, pinned {pins[name]}" for name in closure
                  if version(name) != pins[name]]
    assert mismatched == [], "installed versions differ from the pins"
