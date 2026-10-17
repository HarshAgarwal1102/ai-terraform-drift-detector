"""Task 12.1A (E6, P1-P3): no Terraform plan or Azure account detail reaches a public job log.

Covers scripts/auth_test_plan.sh (the terraform-auth-test.yml dev check) and the
`Verify Azure OIDC Authentication` step of terraform-auth-test.yml and drift-detection.yml.

Runner-realistic: the script and the workflow run: blocks are executed with a fake
`terraform` and a fake `az` on PATH (real jq). Every fake prints a random sentinel in its
plan output, drift section, error text and account values; no executed case may let the
sentinel reach stdout, stderr or the step summary. Nothing here reaches Azure or the
network.

Evidence classes are kept apart (test names say which):
- `real`: the committed plans in tests/fixtures/plan_evidence/ are real Terraform 1.14.7
  output (tests/test_detect_drift.py), each with its real plan exit code;
- `synthetic`: tests/fixtures/root_cause_plans/ plans are hand-built (build.py) and have no
  exit code; the exit code used with them is an assumption;
- `assumed`: hand-written minimal plans for action shapes no fixture contains
  (["create","delete"], ["forget"], data ["read"], output ["create"]), shaped after
  Terraform's JSON plan format. They prove the script's contract, not Terraform's behavior.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
SCRIPT = ROOT / "scripts" / "auth_test_plan.sh"
AUTH_WORKFLOW = ROOT / ".github" / "workflows" / "terraform-auth-test.yml"
DRIFT_WORKFLOW = ROOT / ".github" / "workflows" / "drift-detection.yml"
REAL = TESTS / "fixtures" / "plan_evidence"
SYNTHETIC = TESTS / "fixtures" / "root_cause_plans"
BASH = shutil.which("bash") or "/bin/bash"
JQ = shutil.which("jq")
PIN = "1.14.7"
COUNT_KEYS = ("add", "change", "destroy", "replace", "import", "moved", "forget", "output_changes")
CODES = {"preflight_failed", "version_mismatch", "init_failed", "validate_failed", "plan_failed",
         "plan_unexpected_exit", "show_failed", "plan_json_invalid", "counts_inconsistent", "internal_error"}

FAKE_TERRAFORM = r"""#!/bin/sh
# Fake terraform: every subcommand prints the sentinel to stdout and stderr.
echo "$*" >> "${FAKE_CALLS}"
cmd=""
for a in "$@"; do
  case "$a" in -chdir=*) ;; *) cmd="$a"; break ;; esac
done
case "$cmd" in
  version)
    printf '{"terraform_version":"%s","platform":"linux_%s","provider_selections":{}}\n' \
      "${FAKE_TF_VERSION:-1.14.7}" "${SENTINEL}"
    echo "version note ${SENTINEL}" >&2
    exit "${FAKE_VERSION_RC:-0}" ;;
  init)
    echo "Initializing the backend... storage account ${SENTINEL}"
    echo "Error: Failed to get existing workspaces: ${SENTINEL}" >&2
    exit "${FAKE_INIT_RC:-0}" ;;
  validate)
    echo "Success! The configuration is valid. ${SENTINEL}"
    echo "Warning: ${SENTINEL}" >&2
    exit "${FAKE_VALIDATE_RC:-0}" ;;
  plan)
    out=""
    for a in "$@"; do
      case "$a" in -out=*) out="${a#-out=}" ;; esac
    done
    echo "azurerm_resource_group.this: Refreshing state... [id=/subscriptions/${SENTINEL}/resourceGroups/rg]"
    echo "Note: Objects have changed outside of Terraform"
    echo "  ~ tags = { \"probe\" = \"${SENTINEL}\" }"
    echo "Plan: 0 to add, 1 to change, 0 to destroy."
    echo "Error: retrieving Resource Group ${SENTINEL}" >&2
    if [ "${FAKE_PLAN_WRITE:-1}" != 0 ] && [ -n "$out" ]; then
      printf 'binary-plan %s' "${SENTINEL}" > "$out"
    fi
    if [ -n "${FAKE_PLAN_SIGNAL:-}" ]; then
      kill -TERM "$PPID"
    fi
    exit "${FAKE_PLAN_RC:-0}" ;;
  show)
    echo "show note ${SENTINEL}" >&2
    if [ -n "${FAKE_SHOW_FILE:-}" ]; then
      cat "${FAKE_SHOW_FILE}"
    fi
    exit "${FAKE_SHOW_RC:-0}" ;;
  *)
    echo "unexpected terraform subcommand ${cmd} ${SENTINEL}" >&2
    exit 97 ;;
esac
"""

# Fails only the jq call that carries JQ_FAIL_ON as an argument, quoting the sentinel the
# way a real jq error quotes a value; every other call is the real jq.
JQ_SHIM = r"""#!/bin/sh
for a in "$@"; do
  if [ "$a" = "${JQ_FAIL_ON}" ]; then
    echo "jq: error (at plan.json:7): Cannot iterate over string (\"${SENTINEL}\")" >&2
    exit 5
  fi
done
exec "${REAL_JQ}" "$@"
"""

FAKE_AZ = r"""#!/bin/sh
# Fake az: `az account show --query id|tenantId --output tsv`.
echo "$*" >> "${FAKE_CALLS}"
if [ -n "${FAKE_AZ_FAIL:-}" ]; then
  echo "ERROR: AADSTS700213: No matching federated identity record found for ${SENTINEL}" >&2
  exit 1
fi
query=""
prev=""
for a in "$@"; do
  [ "$prev" = "--query" ] && query="$a"
  prev="$a"
done
case "$query" in
  id) printf '%s\n' "${FAKE_SUBSCRIPTION}" ;;
  tenantId) printf '%s\n' "${FAKE_TENANT}" ;;
  *) printf '{"id":"%s","tenantId":"%s","user":{"name":"%s"}}\n' "${FAKE_SUBSCRIPTION}" "${FAKE_TENANT}" "${SENTINEL}" ;;
esac
"""


def _exe(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture
def sentinel() -> str:
    return f"E6-SENTINEL-{secrets.token_hex(8)}"


# --------------------------------------------------------------------------- plan builders


def plan_doc(resource_changes=None, output_changes=None, **header) -> dict:
    """Minimal `terraform show -json` shape (assumed; mirrors the committed real plans' keys)."""
    doc = {"format_version": "1.2", "terraform_version": PIN, "errored": False, "complete": True,
           "resource_changes": resource_changes or [], "output_changes": output_changes or {}}
    doc.update(header)
    return doc


def rc_entry(actions, *, address="azurerm_resource_group.this", mode="managed", value="v", **extra) -> dict:
    entry = {"address": address, "mode": mode, "type": "azurerm_resource_group", "name": "this",
             "change": {"actions": actions, "before": {"tags": {"probe": value}},
                        "after": {"tags": {"probe": value}}}}
    entry.update(extra)
    return entry


class Runner:
    """Runs scripts/auth_test_plan.sh with fakes; returns (proc, summary text, runner dir)."""

    def __init__(self, tmp_path: Path, sentinel: str):
        self.tmp = tmp_path
        self.sentinel = sentinel
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        _exe(self.bin / "terraform", FAKE_TERRAFORM)
        self.jqdir = tmp_path / "jqbin"
        self.jqdir.mkdir()
        (self.jqdir / "jq").symlink_to(JQ)
        self.tf_dir = tmp_path / "tf"
        self.tf_dir.mkdir()
        (self.tf_dir / "dev.tfvars").write_text('environment = "dev"\n')
        self.calls = tmp_path / "calls.log"
        self.calls.write_text("")

    def run(self, plan=None, *, plan_rc=0, env=None, jq_fail_on=None, with_jq=True, runner_temp=True):
        runner = self.tmp / f"runner{len(list(self.tmp.glob('runner*')))}"
        if runner_temp:
            runner.mkdir()
        summary = self.tmp / f"summary{len(list(self.tmp.glob('summary*')))}.md"
        summary.write_text("")
        show = self.tmp / "show.json"
        if isinstance(plan, (dict, list)):
            show.write_text(json.dumps(plan))
        elif isinstance(plan, str):
            show.write_text(plan)
        elif isinstance(plan, Path):
            shutil.copy(plan, show)
        path = [str(self.bin)]
        if jq_fail_on:
            shim_dir = self.tmp / "jqshim"
            shim_dir.mkdir(exist_ok=True)
            _exe(shim_dir / "jq", JQ_SHIM)
            path.append(str(shim_dir))
        if with_jq:
            path.append(str(self.jqdir))
        full = {"PATH": os.pathsep.join(path + ["/usr/bin", "/bin"]), "HOME": str(self.tmp),
                "SENTINEL": self.sentinel, "FAKE_CALLS": str(self.calls), "TF_DIR": str(self.tf_dir),
                "TERRAFORM_VERSION": PIN, "GITHUB_STEP_SUMMARY": str(summary),
                "FAKE_PLAN_RC": str(plan_rc), "FAKE_SHOW_FILE": str(show) if plan is not None else "",
                "REAL_JQ": JQ, "JQ_FAIL_ON": jq_fail_on or ""}
        if runner_temp:
            full["RUNNER_TEMP"] = str(runner)
        full.update(env or {})
        proc = subprocess.run([BASH, str(SCRIPT)], env=full, capture_output=True, text=True, timeout=60)
        return proc, summary.read_text(), runner


@pytest.fixture
def runner(tmp_path, sentinel) -> Runner:
    return Runner(tmp_path, sentinel)


def assert_no_leak(proc, summary: str, sentinel: str) -> None:
    for where, text in (("stdout", proc.stdout), ("stderr", proc.stderr), ("summary", summary)):
        assert sentinel not in text, f"sentinel leaked to {where}: {text!r}"


def assert_success(proc, summary, sentinel, plan_rc, counts: dict) -> None:
    assert_no_leak(proc, summary, sentinel)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stderr == ""
    counts_line = f"auth-test: plan_exit_code={plan_rc} " + " ".join(f"{k}={counts[k]}" for k in COUNT_KEYS)
    expected = [f"auth-test: terraform_version={PIN}", "auth-test: init=succeeded validate=succeeded", counts_line]
    assert proc.stdout.splitlines() == expected
    assert summary.splitlines() == expected


def assert_failure(proc, summary, sentinel, code: str) -> None:
    assert code in CODES
    assert_no_leak(proc, summary, sentinel)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert proc.stdout.splitlines() == [f"::error::auth-test failed: failure_code={code}"]
    assert proc.stderr == ""
    assert "add=" not in proc.stdout + summary  # fail closed: never a counts line after a failure
    assert summary.splitlines() == [f"auth-test failed: failure_code={code}"]


def counts(**nonzero) -> dict:
    return {k: nonzero.get(k, 0) for k in COUNT_KEYS}


# --------------------------------------------------------------------------- counts: real fixtures


REAL_EXPECTED = {
    "in_sync": (0, counts()),
    "converged_drift": (0, counts()),  # drift found only by refresh: exit 0, nothing pending
    "config_change": (2, counts(change=1)),
    "external_drift": (2, counts(change=1)),
    "drift_and_config_change": (2, counts(change=1)),
    "output_only_change": (2, counts(output_changes=1)),
    "replace": (2, counts(add=1, destroy=1, replace=1, output_changes=1)),  # ["delete","create"]
    "resource_added": (2, counts(add=1, output_changes=1)),
    "external_deletion": (2, counts(add=1, output_changes=1)),
    "resource_removed": (2, counts(add=1, destroy=1, output_changes=1)),  # ["delete"] + ["create"]
}


def test_every_committed_real_plan_is_covered():
    assert sorted(REAL_EXPECTED) == sorted(p.name for p in REAL.iterdir() if (p / "plan.sanitized.json").exists())


@pytest.mark.integration
@pytest.mark.parametrize("name", sorted(REAL_EXPECTED))
def test_counts_real_terraform_plans(runner, sentinel, name):
    plan_rc, expected = REAL_EXPECTED[name]
    # The exit code is the one real Terraform returned for this plan.
    assert json.loads((REAL / name / "detection_run.json").read_text())["plan_exit_code"] == plan_rc
    proc, summary, _ = runner.run(REAL / name / "plan.sanitized.json", plan_rc=plan_rc)
    assert_success(proc, summary, sentinel, plan_rc, expected)


# --------------------------------------------------------------------------- counts: synthetic and assumed


@pytest.mark.integration
@pytest.mark.parametrize("name, expected", [
    ("importing_resource", counts(change=1) | {"import": 1}),
    ("moved_resource", counts(change=1) | {"moved": 1}),
])
def test_counts_synthetic_plans_with_assumed_exit_2(runner, sentinel, name, expected):
    # Hand-built plans without a real exit code; exit 2 is an assumption.
    proc, summary, _ = runner.run(SYNTHETIC / name / "plan.synthetic.json", plan_rc=2)
    assert_success(proc, summary, sentinel, 2, expected)


@pytest.mark.integration
@pytest.mark.parametrize("case, entries, outputs, plan_rc, expected", [
    ("create_before_destroy", [rc_entry(["create", "delete"])], {}, 2,
     counts(add=1, destroy=1, replace=1)),
    ("forget", [rc_entry(["forget"])], {}, 2, counts(forget=1)),
    ("import_only_no_op", [rc_entry(["no-op"], change_importing=True)], {}, 2, counts() | {"import": 1}),
    ("data_read_is_not_counted", [rc_entry(["read"], mode="data", address="data.x.y"), rc_entry(["update"])], {}, 2,
     counts(change=1)),
    ("data_no_op", [rc_entry(["no-op"], mode="data", address="data.x.y")], {}, 0, counts()),
    ("output_create", [], {"o": {"actions": ["create"]}}, 2, counts(output_changes=1)),
    ("mixed", [rc_entry(["create"], address="a.b"), rc_entry(["delete"], address="c.d"),
               rc_entry(["update"], address="e.f"), rc_entry(["delete", "create"], address="g.h"),
               rc_entry(["no-op"], address="i.j", previous_address="i.old")],
     {"o1": {"actions": ["update"]}, "o2": {"actions": ["no-op"]}}, 2,
     counts(add=2, change=1, destroy=2, replace=1, moved=1, output_changes=1)),
])
def test_counts_assumed_action_shapes(runner, sentinel, case, entries, outputs, plan_rc, expected):
    for entry in entries:  # `change_importing` is a builder flag for change.importing
        if entry.pop("change_importing", False):
            entry["change"]["importing"] = {"id": f"/subscriptions/{sentinel}/x"}
    proc, summary, _ = runner.run(plan_doc(entries, outputs), plan_rc=plan_rc)
    assert_success(proc, summary, sentinel, plan_rc, expected)


# --------------------------------------------------------------------------- fail closed: plan.json


def _with(doc: dict, **changes) -> dict:
    return {**doc, **changes}


def _rejections(s: str) -> dict:
    ok = [rc_entry(["update"], value=s)]
    base = plan_doc(ok)
    return {
        "unknown_action": plan_doc([rc_entry(["frobnicate"], value=s)]),
        "empty_actions": plan_doc([rc_entry([], value=s)]),
        "managed_read": plan_doc([rc_entry(["read"], value=s)]),
        "create_then_forget_not_allowlisted": plan_doc([rc_entry(["create", "forget"], value=s)]),
        "reordered_actions": plan_doc([rc_entry(["create", "update"], value=s)]),
        "data_update": plan_doc([rc_entry(["update"], mode="data", value=s)]),
        "mode_missing": plan_doc([{k: v for k, v in rc_entry(["update"], value=s).items() if k != "mode"}]),
        "mode_unknown": plan_doc([rc_entry(["update"], mode=s, value=s)]),
        "address_missing": plan_doc([{k: v for k, v in rc_entry(["update"], value=s).items() if k != "address"}]),
        "change_missing": plan_doc([{"address": "a.b", "mode": "managed", "x": s}]),
        "actions_not_array": plan_doc([{"address": "a.b", "mode": "managed", "change": {"actions": s}}]),
        "entry_not_object": plan_doc([s]),
        "resource_changes_not_array": _with(base, resource_changes={"x": s}),
        "resource_drift_malformed": _with(base, resource_drift=[{"address": s}]),
        "output_changes_not_object": _with(base, output_changes=[s]),
        "output_action_unknown": plan_doc(ok, {"o": {"actions": ["replace"], "after": s}}),
        "errored_true": _with(base, errored=True),
        "errored_missing": {k: v for k, v in base.items() if k != "errored"},
        "errored_string": _with(base, errored=s),
        "complete_false": _with(base, complete=False),
        "complete_missing": {k: v for k, v in base.items() if k != "complete"},
        "format_major_2": _with(base, format_version=f"2.{s}"),
        "format_not_string": _with(base, format_version=1.2),
        "terraform_version_mismatch": _with(base, terraform_version=s),
    }


REJECTION_CASES = sorted(_rejections("x"))


@pytest.mark.integration
@pytest.mark.parametrize("case", REJECTION_CASES)
def test_invalid_plan_json_fails_closed(runner, sentinel, case):
    proc, summary, _ = runner.run(_rejections(sentinel)[case], plan_rc=2)
    assert_failure(proc, summary, sentinel, "plan_json_invalid")


@pytest.mark.integration
@pytest.mark.parametrize("raw", ["not json {", '{"a": 1}\n{"b": 2}\n', "[1, 2]", ""])
def test_unparseable_show_output_fails_closed(runner, sentinel, raw):
    proc, summary, _ = runner.run(raw + sentinel if raw.startswith("not") else raw, plan_rc=2)
    assert_failure(proc, summary, sentinel, "plan_json_invalid")


@pytest.mark.integration
def test_jq_error_text_never_reaches_the_log(runner, sentinel):
    proc, summary, run_dir = runner.run(REAL / "external_drift" / "plan.sanitized.json", plan_rc=2,
                                        jq_fail_on="tfv")
    assert_failure(proc, summary, sentinel, "plan_json_invalid")
    assert sentinel in (run_dir / "auth-test" / "jq.log").read_text()  # runner-local only


@pytest.mark.integration
@pytest.mark.parametrize("plan_rc, name", [(0, "external_drift"), (2, "in_sync")])
def test_exit_code_and_plan_must_agree(runner, sentinel, plan_rc, name):
    proc, summary, _ = runner.run(REAL / name / "plan.sanitized.json", plan_rc=plan_rc)
    assert_failure(proc, summary, sentinel, "counts_inconsistent")


# --------------------------------------------------------------------------- fail closed: process


@pytest.mark.integration
@pytest.mark.parametrize("env, plan_rc, code", [
    ({"FAKE_INIT_RC": "1"}, 0, "init_failed"),
    ({"FAKE_VALIDATE_RC": "1"}, 0, "validate_failed"),
    ({}, 1, "plan_failed"),
    ({}, 3, "plan_unexpected_exit"),
    ({"FAKE_SHOW_RC": "1"}, 2, "show_failed"),
    ({"FAKE_PLAN_WRITE": "0"}, 2, "show_failed"),
    ({"FAKE_TF_VERSION": "1.13.0"}, 0, "version_mismatch"),
    ({"FAKE_VERSION_RC": "1"}, 0, "preflight_failed"),
    ({"TF_CLI_ARGS_plan": "-lock=false"}, 0, "preflight_failed"),
    ({"TF_CLI_ARGS": "-no-color"}, 0, "preflight_failed"),
])
def test_process_failures_have_fixed_codes(runner, sentinel, env, plan_rc, code):
    proc, summary, _ = runner.run(REAL / "external_drift" / "plan.sanitized.json", plan_rc=plan_rc, env=env)
    assert_failure(proc, summary, sentinel, code)


@pytest.mark.integration
def test_missing_runner_temp_fails_closed(runner, sentinel):
    proc, summary, _ = runner.run(REAL / "in_sync" / "plan.sanitized.json", runner_temp=False)
    assert_failure(proc, summary, sentinel, "preflight_failed")


@pytest.mark.integration
def test_missing_jq_fails_closed(runner, sentinel, tmp_path):
    tools = tmp_path / "tools"  # what the script needs before its jq check, and no jq
    tools.mkdir()
    (tools / "dirname").symlink_to(shutil.which("dirname"))
    proc, summary, _ = runner.run(REAL / "in_sync" / "plan.sanitized.json", with_jq=False,
                                  env={"PATH": f"{runner.bin}:{tools}"})
    assert_failure(proc, summary, sentinel, "preflight_failed")


@pytest.mark.integration
def test_missing_var_file_fails_closed(runner, sentinel):
    (runner.tf_dir / "dev.tfvars").unlink()
    proc, summary, _ = runner.run(REAL / "in_sync" / "plan.sanitized.json")
    assert_failure(proc, summary, sentinel, "preflight_failed")


@pytest.mark.integration
def test_stale_log_directory_fails_closed(runner, sentinel, tmp_path):
    stale = tmp_path / "stale"
    (stale / "auth-test").mkdir(parents=True)
    proc, summary, _ = runner.run(REAL / "in_sync" / "plan.sanitized.json", env={"RUNNER_TEMP": str(stale)})
    assert_failure(proc, summary, sentinel, "preflight_failed")


@pytest.mark.integration
def test_interruption_ends_with_internal_error(runner, sentinel):
    proc, summary, _ = runner.run(REAL / "external_drift" / "plan.sanitized.json", plan_rc=2,
                                  env={"FAKE_PLAN_SIGNAL": "1"})
    assert_failure(proc, summary, sentinel, "internal_error")


@pytest.mark.integration
def test_inherited_xtrace_is_switched_off(runner, sentinel):
    proc, summary, _ = runner.run(REAL / "external_drift" / "plan.sanitized.json", plan_rc=2,
                                  env={"SHELLOPTS": "xtrace"})
    assert sentinel not in proc.stdout + proc.stderr + summary
    assert proc.returncode == 0 and proc.stdout.splitlines()[-1].startswith("auth-test: plan_exit_code=2 ")
    assert proc.stderr.strip() in ("", "+ set +x")  # only the switch-off itself is traced


@pytest.mark.integration
def test_terraform_is_called_read_only_with_the_contract_flags(runner, sentinel):
    proc, summary, run_dir = runner.run(REAL / "external_drift" / "plan.sanitized.json", plan_rc=2)
    assert proc.returncode == 0
    calls = runner.calls.read_text().splitlines()
    verbs = [next(a for a in c.split() if not a.startswith("-chdir=")) for c in calls]
    assert verbs == ["version", "init", "validate", "plan", "show"]
    plan = calls[3].split()
    for flag in ("-var-file=dev.tfvars", "-input=false", "-no-color", "-detailed-exitcode",
                 f"-out={run_dir / 'auth-test' / 'tfplan'}"):
        assert flag in plan
    assert not any("lock-timeout" in a for a in plan)  # out of scope for Task 12.1A (user decision)
    assert "-input=false" in calls[1].split() and "-no-color" in calls[2].split()
    assert not any("apply" in c.split() for c in calls)


@pytest.mark.integration
def test_files_stay_runner_local(runner, sentinel):
    proc, summary, run_dir = runner.run(REAL / "external_drift" / "plan.sanitized.json", plan_rc=2)
    assert proc.returncode == 0
    files = sorted(p.name for p in (run_dir / "auth-test").iterdir())
    assert files == ["init.log", "jq.log", "plan.json", "plan.log", "show.log", "tfplan", "validate.log",
                     "version.log"]
    assert sentinel in (run_dir / "auth-test" / "plan.log").read_text()  # the plan output went here
    assert sorted(p.name for p in runner.tf_dir.iterdir()) == ["dev.tfvars"]  # nothing in the checkout


# --------------------------------------------------------------------------- workflow structure


@pytest.fixture(scope="module")
def auth_wf() -> dict:
    return yaml.safe_load(AUTH_WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def drift_wf() -> dict:
    return yaml.safe_load(DRIFT_WORKFLOW.read_text(encoding="utf-8"))


def _steps(job: dict) -> dict:
    return {s["name"]: s for s in job["steps"]}


def _run_blocks(wf: dict):
    for job_name, job in wf["jobs"].items():
        for step in job.get("steps", []):
            if "run" in step:
                yield f"{job_name} / {step['name']}", step["run"]


def test_auth_test_triggers_and_permissions(auth_wf):
    assert auth_wf[True] == {"push": {"branches": ["main", "master"]},
                             "pull_request": {"branches": ["main", "master"]}, "workflow_dispatch": None}
    assert auth_wf["permissions"] == {"contents": "read"}  # only the authenticated job gets an OIDC token
    assert set(auth_wf["jobs"]) == {"offline-validate", "validate-and-plan"}
    assert "pull_request_target" not in AUTH_WORKFLOW.read_text(encoding="utf-8")


def test_pull_requests_get_offline_validation_without_azure(auth_wf):
    """PR runs: fmt and backend-less validate of both roots; no OIDC token, secret, login or state."""
    job = auth_wf["jobs"]["offline-validate"]
    assert "if" not in job and job["permissions"] == {"contents": "read"}
    text = yaml.safe_dump(job)
    for forbidden in ("secrets.", "id-token", "azure/login", "ARM_", "az ", "auth_test_plan"):
        assert forbidden not in text, forbidden
    steps = _steps(job)
    assert steps["Checkout Code"]["with"] == {"persist-credentials": False}
    assert steps["Setup Terraform"]["with"]["terraform_wrapper"] is False
    assert steps["Check Terraform Formatting"]["run"].strip() == "terraform fmt -check -recursive"
    for name, root in (("Validate Bootstrap Configuration (offline, no state)", "terraform/bootstrap"),
                       ("Validate Dev Environment Configuration (offline, no state)", "terraform/environments/dev")):
        assert steps[name]["run"].split("\n")[1:3] == [
            f"terraform -chdir={root} init -backend=false -input=false", f"terraform -chdir={root} validate"]
    for _, run in _run_blocks({"jobs": {"offline-validate": job}}):
        assert " plan" not in run and " apply" not in run


def test_azure_login_only_on_trusted_events_after_offline_checks(auth_wf):
    job = auth_wf["jobs"]["validate-and-plan"]
    assert job["if"] == "github.event_name != 'pull_request'"
    assert job["needs"] == "offline-validate"
    assert job["permissions"] == {"id-token": "write", "contents": "read"}
    assert [s["name"] for s in job["steps"]] == ["Checkout Code", "Azure OIDC Login", "Verify Azure OIDC Authentication",
                                                 "Setup Terraform", "Validate Dev Environment Configuration"]
    for name, other in auth_wf["jobs"].items():
        if name != "validate-and-plan":
            assert "azure/login" not in yaml.safe_dump(other) and "secrets." not in yaml.safe_dump(other), name


def test_auth_test_uses_the_real_terraform_binary_and_the_script(auth_wf):
    steps = _steps(auth_wf["jobs"]["validate-and-plan"])
    assert steps["Setup Terraform"]["with"]["terraform_wrapper"] is False
    dev = steps["Validate Dev Environment Configuration"]
    assert dev["run"].strip() == "./scripts/auth_test_plan.sh"
    assert dev["env"] == {"ARM_CLIENT_ID": "${{ secrets.AZURE_CLIENT_ID }}",
                          "ARM_TENANT_ID": "${{ secrets.AZURE_TENANT_ID }}",
                          "ARM_SUBSCRIPTION_ID": "${{ secrets.AZURE_SUBSCRIPTION_ID }}",
                          "ARM_USE_OIDC": "true", "ARM_USE_AZUREAD": "true"}
    text = AUTH_WORKFLOW.read_text(encoding="utf-8")
    assert "upload-artifact" not in text and "lock-timeout" not in text
    for where, run in _run_blocks(auth_wf):
        assert "terraform -chdir=terraform/environments/dev plan" not in run, where


def test_script_is_executable_and_hardened():
    assert os.access(SCRIPT, os.X_OK)
    joined = re.sub(r"\\\n\s*", " ", SCRIPT.read_text(encoding="utf-8"))  # join continuation lines
    code = [ln for ln in joined.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    assert code[0] == "set +x"  # first command
    text = "\n".join(code)
    assert "set -x" not in text and "lock-timeout" not in text and " apply" not in text
    assert "-detailed-exitcode" in text
    for line in code:
        if re.search(r"\bterraform -chdir", line) or re.search(r"\bjq\b.*(PLAN_JSON|version_json)", line):
            assert re.search(r"2>>?\s*\"\$\{(LOG_DIR|JQ_LOG)", line) or "2>&1" in line, line


@pytest.mark.parametrize("which", ["auth", "drift"])
def test_no_step_prints_runner_local_logs_or_traces(auth_wf, drift_wf, which):
    wf = auth_wf if which == "auth" else drift_wf
    for where, run in _run_blocks(wf):
        assert not re.search(r"\b(tail|cat|head|less|more)\b[^\n]*\.log\b", run), where
        assert not re.search(r"::group::[^\n]*\.log", run), where
        assert not re.search(r"(^|\s)set -[a-z]*x", run), where
        assert "SHELLOPTS" not in run and "TF_LOG" not in run, where


def test_generate_plan_evidence_never_prints_plan_log(drift_wf):
    run = _steps(drift_wf["jobs"]["plan-and-analyze"])["Generate Plan Evidence"]["run"]
    assert "plan.log" not in run and "tail " not in run


@pytest.mark.parametrize("which", ["auth", "drift"])
def test_account_context_is_only_ever_captured(auth_wf, drift_wf, which):
    wf = auth_wf if which == "auth" else drift_wf
    for where, run in _run_blocks(wf):
        for line in run.splitlines():
            if "az account show" in line:
                assert re.search(r'="\$\(az account show [^)]*2>/dev/null\)"', line), (where, line)


def test_drift_detection_auth_step_identity_unchanged(drift_wf):
    job = drift_wf["jobs"]["plan-and-analyze"]
    step = _steps(job)["Verify Azure OIDC Authentication"]
    assert step["id"] == "auth"
    assert job["outputs"]["auth_outcome"] == "${{ steps.auth.outcome }}"


# --------------------------------------------------------------------------- auth check (P2, P3)


SUB = "00000000-1111-2222-3333-444444444444"
TENANT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _auth_step(which: str) -> str:
    if which == "auth":
        wf, job = yaml.safe_load(AUTH_WORKFLOW.read_text(encoding="utf-8")), "validate-and-plan"
    else:
        wf, job = yaml.safe_load(DRIFT_WORKFLOW.read_text(encoding="utf-8")), "plan-and-analyze"
    return _steps(wf["jobs"][job])["Verify Azure OIDC Authentication"]


def _run_auth(tmp_path: Path, which: str, sentinel: str, *, actual=(SUB, TENANT), expected=(SUB, TENANT),
              az_fail=False, xtrace=False):
    step = _auth_step(which)
    assert step["env"] == {"EXPECTED_SUBSCRIPTION_ID": "${{ secrets.AZURE_SUBSCRIPTION_ID }}",
                           "EXPECTED_TENANT_ID": "${{ secrets.AZURE_TENANT_ID }}"}
    bindir = tmp_path / "azbin"
    bindir.mkdir(exist_ok=True)
    _exe(bindir / "az", FAKE_AZ)
    script = tmp_path / "auth_step.sh"
    script.write_text(step["run"], encoding="utf-8")
    env = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(tmp_path), "SENTINEL": sentinel,
           "FAKE_CALLS": str(tmp_path / "az_calls.log"), "FAKE_SUBSCRIPTION": actual[0], "FAKE_TENANT": actual[1],
           "EXPECTED_SUBSCRIPTION_ID": expected[0], "EXPECTED_TENANT_ID": expected[1]}
    if az_fail:
        env["FAKE_AZ_FAIL"] = "1"
    if xtrace:
        env["SHELLOPTS"] = "xtrace"
    # GitHub's default bash invocation for run: steps.
    return subprocess.run([BASH, "--noprofile", "--norc", "-eo", "pipefail", str(script)], env=env,
                          capture_output=True, text=True, timeout=30)


VERIFIED = "Azure OIDC context verified (subscription and tenant match the configured values; not printed)."


@pytest.mark.integration
@pytest.mark.parametrize("which", ["auth", "drift"])
def test_auth_check_match_prints_one_fixed_line(tmp_path, sentinel, which):
    proc = _run_auth(tmp_path, which, sentinel, actual=(SUB, f"{TENANT}\n"),
                     expected=(SUB.upper(), f" {TENANT.upper()} "))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.splitlines() == [VERIFIED] and proc.stderr == ""
    calls = (tmp_path / "az_calls.log").read_text().splitlines()
    assert calls == ["account show --only-show-errors --query id --output tsv",
                     "account show --only-show-errors --query tenantId --output tsv"]


@pytest.mark.integration
@pytest.mark.parametrize("which", ["auth", "drift"])
@pytest.mark.parametrize("case", ["subscription", "tenant"])
def test_auth_check_mismatch_prints_no_value(tmp_path, sentinel, which, case):
    actual = (f"{sentinel}-sub", TENANT) if case == "subscription" else (SUB, f"{sentinel}-tenant")
    proc = _run_auth(tmp_path, which, sentinel, actual=actual)
    assert proc.returncode == 1
    assert proc.stdout.splitlines() == ["::error::Azure auth check failed: failure_code=auth_context_mismatch"]
    out = proc.stdout + proc.stderr
    assert sentinel not in out and SUB not in out and TENANT not in out


@pytest.mark.integration
@pytest.mark.parametrize("which", ["auth", "drift"])
def test_auth_check_unavailable_hides_az_error_text(tmp_path, sentinel, which):
    proc = _run_auth(tmp_path, which, sentinel, az_fail=True)
    assert proc.returncode == 1
    assert proc.stdout.splitlines() == ["::error::Azure auth check failed: failure_code=auth_context_unavailable"]
    assert sentinel not in proc.stdout + proc.stderr


@pytest.mark.integration
@pytest.mark.parametrize("which", ["auth", "drift"])
def test_auth_check_empty_context_is_unavailable(tmp_path, sentinel, which):
    proc = _run_auth(tmp_path, which, sentinel, actual=(" ", TENANT))
    assert proc.returncode == 1
    assert proc.stdout.splitlines() == ["::error::Azure auth check failed: failure_code=auth_context_unavailable"]


@pytest.mark.integration
@pytest.mark.parametrize("which", ["auth", "drift"])
def test_auth_check_missing_configuration(tmp_path, sentinel, which):
    proc = _run_auth(tmp_path, which, sentinel, expected=("", TENANT))
    assert proc.returncode == 1
    assert proc.stdout.splitlines() == ["::error::Azure auth check failed: failure_code=auth_configuration_missing"]
    assert not (tmp_path / "az_calls.log").exists()


@pytest.mark.integration
@pytest.mark.parametrize("which", ["auth", "drift"])
def test_auth_check_under_inherited_xtrace_prints_no_value(tmp_path, sentinel, which):
    proc = _run_auth(tmp_path, which, sentinel, actual=(f"{sentinel}-sub", TENANT), xtrace=True)
    assert proc.returncode == 1
    out = proc.stdout + proc.stderr
    assert sentinel not in out and SUB not in out and TENANT not in out
