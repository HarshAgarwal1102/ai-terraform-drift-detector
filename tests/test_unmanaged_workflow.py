"""Task 10.4: unmanaged resources in CI (drift-detection.yml, scripts/inventory_analysis.sh).

Runner-realistic: the script and the workflow run: blocks are executed with fake tools on PATH (venv,
pip, timeout, drift-engine). The real `drift-engine inventory` runs with the scripted ARM source of
unmanaged_fixtures (patched in the engine process), so nothing reaches Azure or the network. Every
identifier is synthetic.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
sys.path.insert(0, str(TESTS))

from unmanaged_fixtures import (  # noqa: E402
    MANAGED_VNET, SUB, VNET_ADDRESS, FakePrices, plan_and_report, portal_vm_source, with_managed,
)

from drift_engine import inventory as inv  # noqa: E402
from drift_engine import unmanaged_cost as uc  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "drift-detection.yml"
SCRIPT = ROOT / "scripts" / "inventory_analysis.sh"
BASH = shutil.which("bash") or "/bin/bash"
OUTPUT_LINE = re.compile(r"^inventory_status=(complete|incomplete|failed) inventory_failure=[a-z_]+ "
                         r"inventory_publishable=(true|false) inventory_unmanaged=([0-9]+|n/a) "
                         r"inventory_detail=[a-z_=,0-9]+$")
STATUS_KEYS = {"inventory_status", "inventory_failure", "inventory_detail", "inventory_unmanaged",
               "inventory_publishable"}
VALID = ("${{ steps.upload.outcome == 'success' && (steps.analyze.outputs.drift_detected == 'true' "
         "|| steps.analyze.outputs.drift_detected == 'false') }}")


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


# --------------------------------------------------------------------------- workflow structure


def test_inventory_step_and_upload(wf):
    job = wf["jobs"]["plan-and-analyze"]
    steps = steps_by_name(job)
    step = steps["Unmanaged Resource Inventory"]
    assert step["id"] == "inventory" and step["if"] == VALID
    assert "timeout-minutes" not in step and "continue-on-error" not in step  # never fails plan-and-analyze
    assert step["env"] == {"PLAN_JSON": "${{ runner.temp }}/drift/plan.json",
                           "PUBLIC_REPORT": "${{ runner.temp }}/drift/drift_report.json"}
    assert "./scripts/inventory_analysis.sh || script_rc=$?" in step["run"] and step["run"].rstrip().endswith("exit 0")
    text = json.dumps(step)
    for forbidden in ("secrets.", "GH_TOKEN", "github.token", "INTERNAL_REPORT", "drift-internal", "set -x"):
        assert forbidden not in text, forbidden
    upload = steps["Upload Unmanaged Inventory"]
    assert upload["id"] == "inventory_upload" and upload["continue-on-error"] is True
    assert upload["if"] == "${{ steps.inventory.outputs.inventory_publishable == 'true' }}"
    assert upload["with"] == {"name": "unmanaged-inventory-${{ github.run_id }}",
                              "path": "${{ runner.temp }}/unmanaged/public/unmanaged_inventory.json",
                              "retention-days": 30, "if-no-files-found": "error", "overwrite": True}
    for key in STATUS_KEYS:
        assert job["outputs"][key] == f"${{{{ steps.inventory.outputs.{key} }}}}"
    assert job["outputs"]["inventory_upload_outcome"] == "${{ steps.inventory_upload.outcome }}"
    assert job["permissions"] == {"id-token": "write", "contents": "read", "actions": "read"}  # unchanged


def test_unmanaged_job_is_least_privilege_and_isolated(wf):
    job = wf["jobs"]["unmanaged"]
    assert job["needs"] == ["preflight", "plan-and-analyze"]
    assert job["if"] == ("${{ !cancelled() && (needs.plan-and-analyze.outputs.drift_detected == 'true' || "
                         "needs.plan-and-analyze.outputs.drift_detected == 'false') }}")
    assert job["permissions"] == {"contents": "read"} and job["timeout-minutes"] == 10
    assert [s["name"] for s in job["steps"]] == [
        "Checkout Code", "Setup Python", "Install drift-engine", "Download Drift Report", "Download Unmanaged Inventory",
        "Price Unmanaged Resources", "Verify Unmanaged Documents", "Upload Unmanaged Resources Report",
        "Unmanaged Summary", "Require Unmanaged Inventory"]
    steps = steps_by_name(job)
    assert steps["Checkout Code"]["with"] == {"persist-credentials": False, "set-safe-directory": False}
    assert steps["Install drift-engine"]["run"].split()[-1] == "."  # runtime only: no Azure SDK, no AI stack
    assert steps["Download Unmanaged Inventory"]["with"]["name"] == "unmanaged-inventory-${{ github.run_id }}"
    upload = steps["Upload Unmanaged Resources Report"]
    assert upload["with"]["name"] == "unmanaged-resources-${{ github.run_id }}" and "continue-on-error" not in upload
    assert [p.strip() for p in upload["with"]["path"].splitlines() if p.strip()] == [
        "${{ runner.temp }}/unmanaged/unmanaged_inventory.json", "${{ runner.temp }}/unmanaged/unmanaged_cost.json"]
    for name in ("Unmanaged Summary", "Require Unmanaged Inventory"):
        assert steps[name]["if"] == "${{ !cancelled() }}"
    text = json.dumps(job)
    for forbidden in ("secrets.", "id-token", "azure/login", "ARM_", "AZURE_", "github-token", "GH_TOKEN",
                      "continue-on-error", "plan.json", "drift_detected == 'true' &&"):
        assert forbidden not in text.replace("drift_detected == 'true' ||", ""), forbidden
    # isolation: no other job reads the unmanaged results; report keeps its needs
    for name in ("issues", "cost", "investigation", "report", "preflight"):
        assert "unmanaged" not in json.dumps(wf["jobs"][name]).lower(), name
    assert wf["jobs"]["report"]["needs"] == ["preflight", "plan-and-analyze"]


def test_no_upload_carries_plan_or_restricted_files(wf):
    uploads = [s["with"]["path"] for job in wf["jobs"].values() for s in job.get("steps", [])
               if s.get("uses") == "actions/upload-artifact@v4"]
    for forbidden in ("restricted", "inventory-venv", "plan.json", "inventory.log"):
        assert not any(forbidden in path for path in uploads), forbidden


# --------------------------------------------------------------------------- scripts/inventory_analysis.sh


class Harness:
    """scripts/inventory_analysis.sh with a fake venv/pip/timeout and a real or scripted drift-engine."""

    def __init__(self, tmp: Path) -> None:
        self.tmp, self.n = tmp, 0
        self.ctrl, self.shim, self.site = tmp / "ctrl", tmp / "shim", tmp / "fake-site"
        for d in (self.ctrl, self.shim, self.site):
            d.mkdir()
        real = sys.executable
        # bin/python: pip is controlled; the pin check sees only the fake site (python -S); everything else (the
        # public check) is the real interpreter with drift_engine installed.
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
             'case "$2" in *azure-constraints.txt) PYTHONPATH={self.site} exec {real} -S "$@";; esac\\n'
             'exec {real} "$@"\\n')
with open(os.path.join(b, "drift-engine"), "w") as fh:
    fh.write('#!/bin/sh\\nexec {real} {self.tmp}/engine.py "$@"\\n')
for name in ("python", "drift-engine"):
    os.chmod(os.path.join(b, name), 0o755)
''')
        _exe(self.shim / "timeout", f'''#!{real}
import os, sys
open({str(self.ctrl / "timeout_calls")!r}, "a").write(sys.argv[1] + "\\n")
hit = {str(self.ctrl / "timeout_hit")!r}
if os.path.exists(hit) and open(hit).read().strip() in ("", sys.argv[1]):  # empty: every bound is hit
    sys.exit(124)
os.execvp(sys.argv[2], sys.argv[2:])
''')
        (tmp / "engine.py").write_text(f'''
import json, os, sys
sys.path.insert(0, {str(TESTS)!r})
ctrl = {str(self.ctrl)!r}
open(os.path.join(ctrl, "engine_calls"), "a").write(json.dumps({{"argv": sys.argv[1:],
    "token": "GH_TOKEN" in os.environ or "GITHUB_TOKEN" in os.environ}}) + "\\n")
spec = json.load(open(os.path.join(ctrl, "mode")))
if spec.get("source"):
    import unmanaged_fixtures as f
    from drift_engine import cli, inventory
    sources = {{"portal": f.portal_vm_source,
                "forbidden": lambda: f.FakeArm([inventory.InventorySourceError("authorization_failed", 403)]),
                "detail_failed": lambda: f.FakeArm([f.listing(f.VM)],
                                                   {{f.VM: inventory.InventorySourceError("throttled", 429)}})}}
    cli._inventory_source = sources[spec["source"]]
    sys.exit(cli.main(sys.argv[1:]))
args = sys.argv[1:]
if spec.get("write") is not None:
    open(args[args.index("--output") + 1], "w").write(spec["write"])
sys.exit(spec["rc"])
''')

    def run(self, plan, report, mode, *, pip_rc=0, venv_fail=False, timeout_hit=False, drop=(), extra_site=None,
            report_override=None):
        self.n += 1
        runner = self.tmp / f"runner{self.n}"
        runner.mkdir(exist_ok=True)  # a test may pre-create it (stale-directory check)
        for name in ("mode", "pip_rc", "venv_fail", "timeout_hit", "engine_calls", "timeout_calls", "pip_calls"):
            (self.ctrl / name).unlink(missing_ok=True)
        (self.ctrl / "mode").write_text(json.dumps(mode))
        (self.ctrl / "pip_rc").write_text(str(pip_rc))
        if venv_fail:
            (self.ctrl / "venv_fail").write_text("")
        if timeout_hit:
            (self.ctrl / "timeout_hit").write_text("" if timeout_hit is True else str(timeout_hit))
        for item in self.site.iterdir():
            shutil.rmtree(item)
        if extra_site:
            meta = self.site / f"{extra_site[0]}-{extra_site[1]}.dist-info"
            meta.mkdir()
            (meta / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {extra_site[0]}\nVersion: {extra_site[1]}\n")
        (runner / "plan.json").write_text(json.dumps(plan))
        (runner / "report.json").write_text(json.dumps(report_override or report))
        gh = runner / "gh_output"
        gh.write_text("")
        env = {"PATH": f"{self.shim}:/usr/bin:/bin", "HOME": str(self.tmp), "RUNNER_TEMP": str(runner),
               "GITHUB_OUTPUT": str(gh), "PLAN_JSON": str(runner / "plan.json"),
               "PUBLIC_REPORT": str(runner / "report.json"), "PYTHON": str(self.shim / "python3"),
               "GH_TOKEN": "ghs_synthetic", "HTTPS_PROXY": "http://127.0.0.1:9"}
        for name in drop:
            env.pop(name)
        proc = subprocess.run([BASH, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=300)
        calls = [json.loads(x) for x in (self.ctrl / "engine_calls").read_text().splitlines()] \
            if (self.ctrl / "engine_calls").exists() else []
        return proc, _outputs(gh), runner, calls


@pytest.fixture
def harness(tmp_path):
    return Harness(tmp_path)


@pytest.fixture
def case(tmp_path):
    plan, report = plan_and_report(tmp_path)
    return with_managed(plan, (VNET_ADDRESS, "azurerm_virtual_network", MANAGED_VNET)), report


def _assert_clean(proc, outputs, runner, publishable: bool):
    assert proc.returncode == 0, proc.stdout + proc.stderr  # always exits 0
    assert set(outputs) == STATUS_KEYS
    lines = [line for line in proc.stdout.splitlines() if line.startswith("inventory_status=")]
    assert len(lines) == 1 and OUTPUT_LINE.match(lines[0]), proc.stdout
    text = proc.stdout + proc.stderr + json.dumps(outputs)
    for secret in (SUB, "/subscriptions/", "ghs_synthetic"):
        assert secret not in text
    public = runner / "unmanaged" / "public" / "unmanaged_inventory.json"
    assert public.exists() is publishable
    restricted = runner / "unmanaged" / "restricted"
    if restricted.exists():
        assert stat.S_IMODE(restricted.stat().st_mode) == 0o700


def test_complete_inventory_is_publishable(harness, case):
    proc, outputs, runner, calls = harness.run(*case, {"source": "portal"})
    _assert_clean(proc, outputs, runner, True)
    assert outputs == {"inventory_status": "complete", "inventory_failure": "none", "inventory_detail": "none",
                       "inventory_unmanaged": "6", "inventory_publishable": "true"}
    doc = inv.load_inventory(json.loads((runner / "unmanaged" / "public" / "unmanaged_inventory.json").read_text()))
    assert doc.counts.unmanaged == 6
    (call,) = calls
    assert call["argv"][0] == "inventory" and call["token"] is False  # no GitHub token reaches the engine
    # review fix: every blocking operation is bounded (venv, pip, pin check, inventory, public check)
    assert (harness.ctrl / "timeout_calls").read_text().split() == ["60", "180", "30", "300", "45"]
    pip = (harness.ctrl / "pip_calls").read_text()
    assert "azure-constraints.txt" in pip and "[azure]" in pip


def test_failed_listing_is_published_with_its_code(harness, case):
    proc, outputs, runner, _ = harness.run(*case, {"source": "forbidden"})
    _assert_clean(proc, outputs, runner, True)
    assert (outputs["inventory_status"], outputs["inventory_failure"], outputs["inventory_detail"]) == (
        "failed", "listing_failed", "authorization_failed=1")


def test_failed_detail_read_is_incomplete(harness, case):
    proc, outputs, runner, _ = harness.run(*case, {"source": "detail_failed"})
    _assert_clean(proc, outputs, runner, True)
    assert (outputs["inventory_status"], outputs["inventory_failure"], outputs["inventory_detail"]) == (
        "incomplete", "incomplete", "throttled=1")


@pytest.mark.parametrize("mode,failure", [({"rc": 2}, "inventory_usage"), ({"rc": 70}, "internal_error"),
                                          ({"rc": 73}, "write_failed"), ({"rc": 9}, "internal_error"),
                                          ({"rc": 0}, "internal_error"),  # exit 0 without a document
                                          ({"rc": 0, "write": "{\"x\": \"a@b.example\"}"}, "public_check_failed"),
                                          ({"rc": 0, "write": "not json"}, "public_check_failed")])
def test_engine_outcomes_map_to_fixed_codes(harness, case, mode, failure):
    proc, outputs, runner, _ = harness.run(*case, mode)
    _assert_clean(proc, outputs, runner, False)
    assert (outputs["inventory_status"], outputs["inventory_failure"], outputs["inventory_unmanaged"]) == (
        "failed", failure, "")


def test_inventory_of_another_report_is_never_published(harness, case):
    plan, report = case
    doc = inv.collect_inventory(plan, report, portal_vm_source())
    proc, outputs, runner, _ = harness.run(plan, report, {"rc": 0, "write": inv.render_inventory(doc)},
                                           report_override=dict(report, has_drift=True))
    _assert_clean(proc, outputs, runner, False)
    assert outputs["inventory_failure"] == "public_check_failed"


def test_rc_and_outcome_must_agree(harness, case):
    plan, report = case
    doc = inv.collect_inventory(plan, report, portal_vm_source())  # complete, but the engine claims exit 1
    proc, outputs, runner, _ = harness.run(plan, report, {"rc": 1, "write": inv.render_inventory(doc)})
    _assert_clean(proc, outputs, runner, False)
    assert outputs["inventory_failure"] == "internal_error"


@pytest.mark.parametrize("kwargs,failure", [({"venv_fail": True}, "install_failed"), ({"pip_rc": 1}, "install_failed"),
                                            ({"extra_site": ("rogue", "1.0")}, "pin_mismatch"),
                                            ({"timeout_hit": True}, "timeout"),
                                            ({"drop": ("PLAN_JSON",)}, "inputs_missing"),
                                            ({"drop": ("PUBLIC_REPORT",)}, "inputs_missing")])
def test_setup_failures(harness, case, kwargs, failure):
    proc, outputs, runner, calls = harness.run(*case, {"source": "portal"}, **kwargs)
    _assert_clean(proc, outputs, runner, False)
    assert (outputs["inventory_status"], outputs["inventory_failure"]) == ("failed", failure)
    if failure != "timeout":
        assert calls == []


@pytest.mark.parametrize("bound,engine_ran", [("60", False), ("180", False), ("30", False), ("300", False),
                                               ("45", True)])
def test_every_blocking_stage_is_bounded_and_a_hit_is_timeout(harness, case, bound, engine_ran):
    """Review fix: venv (60 s), pip (180 s), pin check (30 s), inventory (300 s) and public check (45 s) each
    stop at their bound with the fixed failure `timeout`; nothing is published and the step still exits 0."""
    proc, outputs, runner, calls = harness.run(*case, {"source": "portal"}, timeout_hit=bound)
    _assert_clean(proc, outputs, runner, False)
    assert (outputs["inventory_status"], outputs["inventory_failure"]) == ("failed", "timeout")
    assert bool(calls) is engine_ran
    log = runner / "unmanaged" / "restricted" / "inventory.log"
    assert "inventory_status=" not in (log.read_text() if log.exists() else "")  # the status line is never logged


def test_bounds_fit_the_job_budget():
    """Review fix: hard bounds (script defaults) sum to about 615 s, and the inventory's own Azure deadline (240 s)
    ends before its 300 s hard bound."""
    text = SCRIPT.read_text(encoding="utf-8")
    defaults = {name: int(value) for name, value in re.findall(r'^([A-Z_]+_TIMEOUT)="\$\{[A-Z_]+:-([0-9]+)\}"$', text, re.M)}
    assert defaults == {"VENV_TIMEOUT": 60, "PIP_TIMEOUT": 180, "PIN_CHECK_TIMEOUT": 30, "INVENTORY_TIMEOUT": 300,
                        "PUBLIC_CHECK_TIMEOUT": 45}
    assert sum(defaults.values()) == 615
    assert inv.DEFAULT_LIMITS.deadline_seconds == 240 < defaults["INVENTORY_TIMEOUT"]


def test_no_blocking_command_runs_unbounded():
    """Every interpreter, pip or drift-engine invocation in the script runs under `timeout` (directly or through
    `bounded`); only the cheap input checks and the status output run without one."""
    unbounded = []
    for line in SCRIPT.read_text(encoding="utf-8").splitlines():
        code = line.split("#", 1)[0]
        if re.search(r'"\$\{PYTHON\}" -m|"\$\{VENV_DIR\}/bin/', code) \
                and not re.search(r"\b(bounded|timeout)\b", code):
            unbounded.append(line.strip())
    assert unbounded == [], unbounded


def test_stale_directories_are_refused(harness, case, tmp_path):
    runner = tmp_path / "runner1"
    (runner / "unmanaged").mkdir(parents=True)
    proc, outputs, _, calls = harness.run(*case, {"source": "portal"})
    assert proc.returncode == 0 and outputs["inventory_failure"] == "inputs_missing" and calls == []
    assert not (runner / "unmanaged" / "public").exists()  # nothing written into the stale directory


# --------------------------------------------------------------------------- workflow run: blocks, executed


def run_block(script: str, tmp_path: Path, env: dict[str, str], cwd: Path | None = None, path_prefix: str = ""):
    gh, summary = tmp_path / "gh_output", tmp_path / "summary.md"
    gh.write_text("")
    summary.write_text("")
    full = {"PATH": f"{path_prefix}{Path(sys.executable).parent}:/usr/bin:/bin", "GITHUB_OUTPUT": str(gh),
            "GITHUB_STEP_SUMMARY": str(summary), "RUNNER_TEMP": str(tmp_path / "runner"), "GITHUB_RUN_ID": "500",
            **env}
    proc = subprocess.run([BASH, "-e", "-c", script], env=full, capture_output=True, text=True, timeout=120,
                          cwd=cwd or tmp_path)
    return proc, _outputs(gh), summary.read_text()


def test_inventory_step_maps_a_script_failure_and_exits_0(wf, tmp_path):
    (tmp_path / "scripts").mkdir()
    _exe(tmp_path / "scripts" / "inventory_analysis.sh", "#!/bin/sh\nexit 3\n")
    public = tmp_path / "runner" / "unmanaged" / "public" / "unmanaged_inventory.json"
    public.parent.mkdir(parents=True)
    public.write_text("{}")
    step = steps_by_name(wf["jobs"]["plan-and-analyze"])["Unmanaged Resource Inventory"]
    proc, outputs, _ = run_block(step["run"], tmp_path, {})
    assert proc.returncode == 0
    assert outputs == {"inventory_status": "failed", "inventory_failure": "script_error", "inventory_detail": "none",
                       "inventory_unmanaged": "", "inventory_publishable": "false"}
    assert not public.exists() and "::error::Unmanaged resource inventory failed unexpectedly" in proc.stdout


@pytest.mark.parametrize("rc,ok", [(0, True), (1, True), (2, False), (70, False)])
def test_price_step_records_the_exit_code(wf, tmp_path, rc, ok):
    shim = tmp_path / "bin"
    shim.mkdir()
    _exe(shim / "drift-engine", f"#!/bin/sh\necho \"$@\" > {tmp_path}/args\nexit {rc}\n")
    step = steps_by_name(wf["jobs"]["unmanaged"])["Price Unmanaged Resources"]
    proc, outputs, _ = run_block(step["run"], tmp_path, {}, path_prefix=f"{shim}:")
    assert (proc.returncode == 0) is ok and outputs == {"pricing_exit_code": str(rc)}
    assert (tmp_path / "args").read_text().split()[0] == "unmanaged-cost"


def _documents(case, tmp_path, prices=None, source=None):
    plan, report = case
    doc = inv.collect_inventory(plan, report, source or portal_vm_source())
    raw = json.loads(inv.render_inventory(doc))
    cost = uc.estimate_costs(inv.load_inventory(raw), raw, prices or FakePrices())
    directory = tmp_path / "runner" / "unmanaged"
    directory.mkdir(parents=True)
    (directory / "unmanaged_inventory.json").write_text(json.dumps(raw))
    (directory / "unmanaged_cost.json").write_text(uc.render_cost(cost))
    drift = tmp_path / "runner" / "drift-report"
    drift.mkdir()
    (drift / "drift_report.json").write_text(json.dumps(report))


OK = {"INVENTORY_STATUS": "complete", "INVENTORY_FAILURE": "none", "INVENTORY_UPLOAD_OUTCOME": "success",
      "VERIFY_OUTCOME": "success", "REPORT_UPLOAD_OUTCOME": "success"}


def test_require_findings_warn_but_pass(wf, tmp_path, case):
    _documents(case, tmp_path)
    step = steps_by_name(wf["jobs"]["unmanaged"])["Require Unmanaged Inventory"]
    proc, _, _ = run_block(step["run"], tmp_path, OK)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "::warning::6 Azure resource(s) not managed by Terraform" in proc.stdout
    assert "inventory=complete, pricing=complete, unmanaged=6" in proc.stdout


def test_require_partial_pricing_warns_but_passes(wf, tmp_path, case):
    _documents(case, tmp_path, prices=FakePrices(override={"Standard_B1s": []}))
    step = steps_by_name(wf["jobs"]["unmanaged"])["Require Unmanaged Inventory"]
    proc, _, _ = run_block(step["run"], tmp_path, OK)
    assert proc.returncode == 0 and "::warning::Unmanaged cost estimate is partial: 1 unavailable" in proc.stdout


def test_require_pricing_api_failure_fails(wf, tmp_path, case):
    _documents(case, tmp_path, prices=FakePrices(fail="service_error"))
    step = steps_by_name(wf["jobs"]["unmanaged"])["Require Unmanaged Inventory"]
    proc, _, _ = run_block(step["run"], tmp_path, OK)
    assert proc.returncode == 1 and "Unmanaged cost estimate failed (service_error)" in proc.stdout
    assert "never $0" in proc.stdout


@pytest.mark.parametrize("override", [{"INVENTORY_STATUS": "failed", "INVENTORY_FAILURE": "listing_failed"},
                                      {"INVENTORY_STATUS": "incomplete"}, {"INVENTORY_STATUS": ""},
                                      {"INVENTORY_UPLOAD_OUTCOME": "failure"}, {"VERIFY_OUTCOME": "failure"},
                                      {"VERIFY_OUTCOME": "skipped"}, {"REPORT_UPLOAD_OUTCOME": "failure"}])
def test_require_failures_are_explicit(wf, tmp_path, case, override):
    _documents(case, tmp_path)
    step = steps_by_name(wf["jobs"]["unmanaged"])["Require Unmanaged Inventory"]
    proc, _, _ = run_block(step["run"], tmp_path, {**OK, **override})
    assert proc.returncode == 1 and "::error::" in proc.stdout


def test_require_clean_inventory_passes_silently(wf, tmp_path, case):
    from unmanaged_fixtures import FakeArm
    _documents(case, tmp_path, source=FakeArm([[]]))
    step = steps_by_name(wf["jobs"]["unmanaged"])["Require Unmanaged Inventory"]
    proc, _, _ = run_block(step["run"], tmp_path, OK)
    assert proc.returncode == 0 and "::warning::" not in proc.stdout


def test_summary_renders_codes_and_the_verified_section(wf, tmp_path, case):
    _documents(case, tmp_path)
    step = steps_by_name(wf["jobs"]["unmanaged"])["Unmanaged Summary"]
    env = {"INVENTORY_STATUS": "complete", "INVENTORY_FAILURE": "none", "INVENTORY_DETAIL": "none",
           "INVENTORY_UPLOAD_OUTCOME": "success", "PRICING_EXIT_CODE": "0", "VERIFY_OUTCOME": "success"}
    proc, _, summary = run_block(step["run"], tmp_path, env)
    assert proc.returncode == 0, proc.stderr
    assert "| Inventory | `complete` |" in summary and "| Estimated monthly cost | $17.11/month" in summary
    assert "`manual-vm`" in summary and "`unmanaged-resources-500` (30 days)" in summary
    assert SUB not in summary and "/subscriptions/" not in summary


def test_summary_without_verified_documents_shows_codes_only(wf, tmp_path):
    step = steps_by_name(wf["jobs"]["unmanaged"])["Unmanaged Summary"]
    env = {"INVENTORY_STATUS": "failed", "INVENTORY_FAILURE": "listing_failed",
           "INVENTORY_DETAIL": "authorization_failed=1", "INVENTORY_UPLOAD_OUTCOME": "success",
           "PRICING_EXIT_CODE": "1", "VERIFY_OUTCOME": "failure"}
    proc, _, summary = run_block(step["run"], tmp_path, env)
    assert proc.returncode == 0
    assert "| Failure | `listing_failed` |" in summary and "| Detail | `authorization_failed=1` |" in summary
    assert "Estimated monthly cost" not in summary


def test_summary_rejects_unexpected_codes(wf, tmp_path):
    step = steps_by_name(wf["jobs"]["unmanaged"])["Unmanaged Summary"]
    env = {"INVENTORY_STATUS": "<script>", "INVENTORY_FAILURE": "", "INVENTORY_DETAIL": "",
           "INVENTORY_UPLOAD_OUTCOME": "", "PRICING_EXIT_CODE": "", "VERIFY_OUTCOME": "skipped"}
    _, _, summary = run_block(step["run"], tmp_path, env)
    assert "| Inventory | `invalid` |" in summary and "<script>" not in summary


def test_workflow_never_imports_applies_or_writes_azure():
    text = WORKFLOW.read_text(encoding="utf-8") + SCRIPT.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    for forbidden in ("terraform apply", "terraform import", "az resource delete", "az vm delete", "az group delete",
                      "-X PUT", "-X POST", "-X DELETE", "az rest"):
        assert forbidden not in code, forbidden
    assert os.access(SCRIPT, os.X_OK)
