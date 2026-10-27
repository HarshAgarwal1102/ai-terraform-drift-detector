"""Azure account switching, stage 1: the partial dev backend and the state storage guard.

terraform/environments/dev/backend.tf holds no state location. CI writes it with
scripts/resolve_backend_config.sh, which first proves (one read-only `az` GET with
--subscription) that the storage account belongs to the signed-in subscription; both init
scripts then run `init -reconfigure -backend-config=<that file>`. These tests run the REAL
scripts with fake `az` / `terraform` binaries that print a sentinel; nothing reaches Azure.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import yaml

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
sys.path.insert(0, str(TESTS))

from test_auth_test_workflow import Runner, _exe  # noqa: E402
from test_generate_plan_json import REAL_PLAN, run_script  # noqa: E402

pytestmark = pytest.mark.integration

RESOLVER = ROOT / "scripts" / "resolve_backend_config.sh"
BACKEND_TF = ROOT / "terraform" / "environments" / "dev" / "backend.tf"
DRIFT_WORKFLOW = ROOT / ".github" / "workflows" / "drift-detection.yml"
AUTH_WORKFLOW = ROOT / ".github" / "workflows" / "terraform-auth-test.yml"
BASH = shutil.which("bash") or "/bin/bash"
CODES = {"backend_configuration_missing", "backend_configuration_invalid", "backend_key_not_bound",
         "state_storage_unavailable", "state_storage_not_in_subscription", "backend_config_write_failed"}
GUARD_ENV = {"TFSTATE_RESOURCE_GROUP": "${{ vars.TFSTATE_RESOURCE_GROUP }}",
             "TFSTATE_STORAGE_ACCOUNT": "${{ vars.TFSTATE_STORAGE_ACCOUNT }}",
             "TFSTATE_CONTAINER": "${{ vars.TFSTATE_CONTAINER }}",
             "TFSTATE_KEY": "${{ vars.TFSTATE_KEY }}",
             "EXPECTED_SUBSCRIPTION_ID": "${{ secrets.AZURE_SUBSCRIPTION_ID }}",
             "BACKEND_CONFIG": "${{ runner.temp }}/backend.hcl"}

FAKE_AZ = r"""#!/bin/sh
# Fake az: logs its arguments; prints FAKE_AZ_ID, or fails with an error that names the sentinel.
echo "$*" >> "${FAKE_AZ_CALLS}"
if [ "${FAKE_AZ_RC:-0}" != 0 ]; then
  echo "ERROR: (ResourceNotFound) storage account ${SENTINEL} was not found" >&2
  exit "${FAKE_AZ_RC}"
fi
printf '%s\n' "${FAKE_AZ_ID}"
"""


def arm_id(subscription: str, group: str, account: str) -> str:
    return (f"/subscriptions/{subscription}/resourceGroups/{group}/providers/Microsoft.Storage/"
            f"storageAccounts/{account}")


class Account:
    """A random state location, so any value that leaks into output is recognisable."""

    def __init__(self) -> None:
        token = secrets.token_hex(4)
        self.subscription = str(uuid.uuid4())
        self.group = f"aitdd-tfstate-rg-{token}"
        self.account = f"aitddtf{token}"
        self.container = "tfstate"
        self.key = f"dev-{self.account}.tfstate"  # the key names the storage account


@pytest.fixture
def account() -> Account:
    return Account()


def resolve(tmp_path: Path, account: Account, *, az_id=None, az_rc=0, with_az=True, **overrides):
    bindir = tmp_path / "azbin"
    bindir.mkdir(exist_ok=True)
    if with_az:
        _exe(bindir / "az", FAKE_AZ)
    calls = tmp_path / "az.log"
    out = tmp_path / "runner" / "backend.hcl"
    out.parent.mkdir(exist_ok=True)
    env = {"PATH": os.pathsep.join([str(bindir), "/usr/bin", "/bin"]), "HOME": str(tmp_path),
           "SENTINEL": account.account, "FAKE_AZ_CALLS": str(calls), "FAKE_AZ_RC": str(az_rc),
           "FAKE_AZ_ID": az_id if az_id is not None else arm_id(account.subscription, account.group, account.account),
           "TFSTATE_RESOURCE_GROUP": account.group, "TFSTATE_STORAGE_ACCOUNT": account.account,
           "TFSTATE_CONTAINER": account.container, "TFSTATE_KEY": account.key,
           "EXPECTED_SUBSCRIPTION_ID": account.subscription, "BACKEND_CONFIG": str(out)}
    for name, value in overrides.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    proc = subprocess.run([BASH, str(RESOLVER)], env=env, capture_output=True, text=True, timeout=30)
    return proc, out, calls


def assert_no_location(proc, account: Account) -> None:
    # The key names the storage account (it is the public backend_key anyway); nothing else may.
    text = (proc.stdout + proc.stderr).replace(f"key={account.key}\n", "key=<the key>\n")
    for value in (account.subscription, account.group, account.account):
        assert value not in text, value


def assert_failed(proc, account: Account, code: str) -> None:
    assert code in CODES
    assert proc.returncode == 1
    assert proc.stdout.strip() == f"::error::state storage check failed: failure_code={code}"
    assert proc.stderr == ""
    assert_no_location(proc, account)


# ---------------------------------------------------------------- the resolver and ownership guard

def test_resolver_writes_the_verified_backend_and_prints_only_the_key(tmp_path, account):
    proc, out, calls = resolve(tmp_path, account)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout == f"backend: state storage verified in the configured subscription; key={account.key}\n"
    assert proc.stderr == ""
    assert_no_location(proc, account)
    assert out.read_text() == (f'resource_group_name  = "{account.group}"\n'
                               f'storage_account_name = "{account.account}"\n'
                               f'container_name       = "{account.container}"\n'
                               f'key                  = "{account.key}"\n'
                               "use_azuread_auth     = true\n")
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    # One read-only lookup, pinned to the configured subscription.
    assert calls.read_text().splitlines() == [
        f"storage account show --only-show-errors --name {account.account} --resource-group {account.group} "
        f"--subscription {account.subscription} --query id --output tsv"]


def test_resolver_accepts_the_first_account_key_and_case_differences(tmp_path, account):
    """The October account as synced: aitddtfstatesa001 keeps dev.tfstate."""
    upper = arm_id(account.subscription.upper(), account.group.upper(), "aitddtfstatesa001").replace(
        "resourceGroups", "RESOURCEGROUPS")
    proc, out, _ = resolve(tmp_path, account, az_id=upper + "\n", TFSTATE_KEY="dev.tfstate",
                           TFSTATE_STORAGE_ACCOUNT="aitddtfstatesa001",
                           EXPECTED_SUBSCRIPTION_ID=account.subscription.upper())
    assert proc.returncode == 0, proc.stdout
    assert 'key                  = "dev.tfstate"' in out.read_text()


@pytest.mark.parametrize("missing", ["TFSTATE_RESOURCE_GROUP", "TFSTATE_STORAGE_ACCOUNT", "TFSTATE_CONTAINER",
                                     "TFSTATE_KEY", "EXPECTED_SUBSCRIPTION_ID", "BACKEND_CONFIG"])
@pytest.mark.parametrize("how", [None, ""])  # unset, or an unset repository variable (empty string)
def test_resolver_requires_every_value(tmp_path, account, missing, how):
    proc, out, calls = resolve(tmp_path, account, **{missing: how})
    assert_failed(proc, account, "backend_configuration_missing")
    assert not out.exists() and not calls.exists()


@pytest.mark.parametrize("name, value", [
    ("TFSTATE_RESOURCE_GROUP", 'rg" key = "x'), ("TFSTATE_RESOURCE_GROUP", "rg."), ("TFSTATE_RESOURCE_GROUP", "a/b"),
    ("TFSTATE_RESOURCE_GROUP", "rg\nkey"), ("TFSTATE_RESOURCE_GROUP", "r" * 91),
    ("TFSTATE_STORAGE_ACCOUNT", "AitddTf01"), ("TFSTATE_STORAGE_ACCOUNT", "ab"), ("TFSTATE_STORAGE_ACCOUNT", "aitdd-tf"),
    ("TFSTATE_STORAGE_ACCOUNT", "a" * 25),
    ("TFSTATE_CONTAINER", "TFstate"), ("TFSTATE_CONTAINER", "tf--state"), ("TFSTATE_CONTAINER", "-tfstate"),
    ("TFSTATE_CONTAINER", "tf"),
    ("TFSTATE_KEY", "prod.tfstate"), ("TFSTATE_KEY", "dev-.tfstate"), ("TFSTATE_KEY", "dev-2026/11.tfstate"),
    ("TFSTATE_KEY", "../dev.tfstate"), ("TFSTATE_KEY", "dev-2026-11.tfstate.bak"), ("TFSTATE_KEY", "DEV.tfstate"),
    ("TFSTATE_KEY", "dev-2026-11.tfstate"),  # the earlier label-based shape: no hyphen in a storage account name
    ("TFSTATE_KEY", "dev-ab.tfstate"),
    ("TFSTATE_KEY", f"dev-{uuid.uuid4()}.tfstate"),  # a subscription GUID must never become the public backend_key
    ("TFSTATE_KEY", "dev-" + "a" * 25 + ".tfstate"),
    ("EXPECTED_SUBSCRIPTION_ID", "not-a-subscription"),
])
def test_resolver_rejects_malformed_values(tmp_path, account, name, value):
    proc, out, calls = resolve(tmp_path, account, **{name: value})
    assert_failed(proc, account, "backend_configuration_invalid")
    assert not out.exists() and not calls.exists()


def test_resolver_never_reuses_an_existing_file(tmp_path, account):
    proc, out, _ = resolve(tmp_path, account)
    assert proc.returncode == 0
    stale = out.read_text()
    proc, out, _ = resolve(tmp_path, account)
    assert_failed(proc, account, "backend_config_write_failed")
    assert out.read_text() == stale  # untouched


@pytest.mark.parametrize("storage", ["abc", "aitddtf202611", "a" * 24])
def test_resolver_accepts_a_key_that_names_the_storage_account(tmp_path, account, storage):
    proc, out, _ = resolve(tmp_path, account, TFSTATE_STORAGE_ACCOUNT=storage, TFSTATE_KEY=f"dev-{storage}.tfstate",
                           az_id=arm_id(account.subscription, account.group, storage))
    assert proc.returncode == 0, proc.stdout
    assert f'key                  = "dev-{storage}.tfstate"' in out.read_text()


@pytest.mark.parametrize("storage, key", [
    ("aitddtf202611", "dev.tfstate"),                    # the first account's key on another storage account
    ("aitddtf202611", "dev-aitddtf202610.tfstate"),      # the previous account's key, left in the variable
    ("aitddtf202611", "dev-aitddtfstatesa001.tfstate"),
    ("aitddtfstatesa001", "dev-aitddtfstatesa001.tfstate"),  # the first account only ever has dev.tfstate
    ("aitddtfstatesa001", "dev-aitddtf202611.tfstate"),
])
def test_resolver_rejects_a_key_the_storage_account_does_not_give(tmp_path, account, storage, key):
    """Regression: a hand-edited TFSTATE_KEY could give two accounts one backend_key (shared baselines)."""
    proc, out, calls = resolve(tmp_path, account, TFSTATE_STORAGE_ACCOUNT=storage, TFSTATE_KEY=key,
                               az_id=arm_id(account.subscription, account.group, storage))
    assert_failed(proc, account, "backend_key_not_bound")
    assert not out.exists() and not calls.exists()  # refused before any Azure call
    assert storage not in proc.stdout + proc.stderr


def test_resolver_refuses_a_symlink_target(tmp_path, account):
    target = tmp_path / "elsewhere.hcl"
    target.write_text("original\n")
    link = tmp_path / "link.hcl"
    link.symlink_to(target)
    proc, _, calls = resolve(tmp_path, account, BACKEND_CONFIG=str(link))
    assert_failed(proc, account, "backend_config_write_failed")
    assert target.read_text() == "original\n" and not calls.exists()


def test_an_account_the_subscription_cannot_find_is_unavailable(tmp_path, account):
    proc, out, _ = resolve(tmp_path, account, az_rc=3)  # not found, or no access, in this subscription
    assert_failed(proc, account, "state_storage_unavailable")
    assert not out.exists()


def test_a_missing_az_cli_is_unavailable(tmp_path, account):
    proc, out, _ = resolve(tmp_path, account, with_az=False)
    assert_failed(proc, account, "state_storage_unavailable")
    assert not out.exists()


@pytest.mark.parametrize("where", ["other_subscription", "other_group", "other_account", "empty"])
def test_an_account_outside_the_signed_in_subscription_is_refused(tmp_path, account, where):
    """The previous Azure account's state storage (or any other) is never used."""
    other = {"other_subscription": arm_id(str(uuid.uuid4()), account.group, account.account),
             "other_group": arm_id(account.subscription, "aitdd-tfstate-rg-old", account.account),
             "other_account": arm_id(account.subscription, account.group, "aitddtfold"),
             "empty": ""}[where]
    proc, out, _ = resolve(tmp_path, account, az_id=other)
    assert_failed(proc, account, "state_storage_not_in_subscription")
    assert not out.exists()


def test_resolver_ignores_an_inherited_xtrace(tmp_path, account):
    proc, _, _ = resolve(tmp_path, account, SHELLOPTS="xtrace")
    assert proc.returncode == 0
    assert_no_location(proc, account)
    assert proc.stderr.strip() in ("", "+ set +x")  # only the switch-off itself is traced


def test_resolver_is_executable_and_hardened():
    assert os.access(RESOLVER, os.X_OK)
    code = [ln for ln in RESOLVER.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    assert code[:3] == ["set +x", "set -uo pipefail", "umask 077"]


# ---------------------------------------------------------------- both init scripts

def test_plan_evidence_init_uses_the_verified_backend_and_records_its_key(tmp_path):
    sentinel = f"E6-SENTINEL-{secrets.token_hex(8)}"
    backend = tmp_path / "backend.hcl"
    backend.write_text('key = "dev-aitddtf202611.tfstate"\n')

    def stored_backend(tf_dir: Path) -> None:  # what a real init stores: the backend actually used
        (tf_dir / ".terraform").mkdir()
        (tf_dir / ".terraform" / "terraform.tfstate").write_text(
            json.dumps({"backend": {"config": {"key": "dev-aitddtf202611.tfstate"}}}))

    proc, manifest, _ = run_script(tmp_path, sentinel, REAL_PLAN, extra_env={"BACKEND_CONFIG": str(backend)},
                                   prepare=stored_backend)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    init = next(line.split() for line in (tmp_path / "calls.log").read_text().splitlines() if " init " in f" {line} ")
    assert init[1:] == ["init", "-input=false", "-no-color", "-reconfigure", f"-backend-config={backend}"]
    assert manifest["backend_key"] == "dev-aitddtf202611.tfstate"  # becomes the public report's run.backend_key


def test_plan_evidence_init_without_a_backend_file_never_reuses_a_stored_backend(tmp_path):
    """Regression: without BACKEND_CONFIG the init was plain, which silently keeps the last backend."""
    proc, _, _ = run_script(tmp_path, f"E6-SENTINEL-{secrets.token_hex(8)}", REAL_PLAN)
    assert proc.returncode == 0
    init = next(line.split() for line in (tmp_path / "calls.log").read_text().splitlines() if " init " in f" {line} ")
    assert init[1:] == ["init", "-input=false", "-no-color", "-reconfigure"]


@pytest.mark.parametrize("kind", ["missing", "directory", "symlink"])
def test_plan_evidence_refuses_an_unusable_backend_file(tmp_path, kind):
    path = tmp_path / "backend.hcl"
    if kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        (tmp_path / "real.hcl").write_text("key = \"x\"\n")
        path.symlink_to(tmp_path / "real.hcl")
    proc, manifest, _ = run_script(tmp_path, f"E6-SENTINEL-{secrets.token_hex(8)}", REAL_PLAN,
                                   extra_env={"BACKEND_CONFIG": str(path)})
    assert proc.returncode == 1
    assert manifest["outcome"] == "failed" and manifest["failure_stage"] == "preflight"
    assert manifest["failure_reason"] == "backend configuration file not found or not a regular readable file"
    assert str(path) not in json.dumps(manifest)
    assert " init " not in f" {(tmp_path / 'calls.log').read_text() if (tmp_path / 'calls.log').exists() else ''} "


@pytest.fixture
def auth_runner(tmp_path):
    return Runner(tmp_path, f"E6-SENTINEL-{secrets.token_hex(8)}")


def test_auth_test_init_uses_the_verified_backend(auth_runner, tmp_path):
    backend = tmp_path / "backend.hcl"
    backend.write_text('key = "dev-aitddtf202611.tfstate"\n')
    proc, _, _ = auth_runner.run(REAL_PLAN, plan_rc=2, env={"BACKEND_CONFIG": str(backend)})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    init = auth_runner.calls.read_text().splitlines()[1].split()
    assert init[1:] == ["init", "-input=false", "-no-color", "-reconfigure", f"-backend-config={backend}"]


def test_auth_test_init_without_a_backend_file_never_reuses_a_stored_backend(auth_runner):
    """Regression: without BACKEND_CONFIG the init was plain, which silently keeps the last backend."""
    proc, _, _ = auth_runner.run(REAL_PLAN, plan_rc=2)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    init = auth_runner.calls.read_text().splitlines()[1].split()
    assert init[1:] == ["init", "-input=false", "-no-color", "-reconfigure"]


# The same regression with the REAL terraform binary: a folder initialized against a
# "previous account" backend, then each script without BACKEND_CONFIG. Local backend only:
# offline, no provider, no Azure.
TERRAFORM = shutil.which("terraform")


def _real_terraform() -> bool:
    if not TERRAFORM:
        return False
    out = subprocess.run([TERRAFORM, "version", "-json"], capture_output=True, text=True)
    return out.returncode == 0 and json.loads(out.stdout).get("terraform_version") == "1.14.7"


def _stored_backend(tf_dir: Path):
    return json.loads((tf_dir / ".terraform" / "terraform.tfstate").read_text())["backend"]["config"].get("path")


def _require_real_terraform() -> None:
    """Skip locally without Terraform 1.14.7; fail in CI, which installs it (tests.yml, full job)."""
    if _real_terraform():
        return
    if os.environ.get("AITDD_REQUIRE_REAL_TERRAFORM") == "1":
        pytest.fail("AITDD_REQUIRE_REAL_TERRAFORM=1 but terraform 1.14.7 is not on PATH")
    pytest.skip("needs terraform 1.14.7")


def test_ci_fails_instead_of_skipping_without_real_terraform(monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], "_real_terraform", lambda: False)
    monkeypatch.setenv("AITDD_REQUIRE_REAL_TERRAFORM", "1")
    with pytest.raises(pytest.fail.Exception, match="not on PATH"):
        _require_real_terraform()
    monkeypatch.delenv("AITDD_REQUIRE_REAL_TERRAFORM")
    with pytest.raises(pytest.skip.Exception):
        _require_real_terraform()


@pytest.fixture
def previously_initialized(tmp_path):
    _require_real_terraform()
    tf_dir = tmp_path / "dev"
    tf_dir.mkdir()
    (tf_dir / "main.tf").write_text('terraform {\n  backend "local" {}\n}\n')
    (tf_dir / "dev.tfvars").write_text("")
    previous = tmp_path / "previous-account.tfstate"
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "CHECKPOINT_DISABLE": "1"}
    init = [TERRAFORM, f"-chdir={tf_dir}", "init", "-input=false", "-no-color"]
    subprocess.run([*init, f"-backend-config=path={previous}"], env=env, check=True, capture_output=True)
    assert _stored_backend(tf_dir) == str(previous)
    subprocess.run(init, env=env, check=True, capture_output=True)  # control: a plain init keeps it
    assert _stored_backend(tf_dir) == str(previous)
    return tf_dir, previous, env


@pytest.mark.parametrize("script", ["generate_plan_json.sh", "auth_test_plan.sh"])
def test_a_previously_initialized_backend_is_never_reused_by_real_terraform(previously_initialized, tmp_path,
                                                                            script):
    tf_dir, previous, env = previously_initialized
    runner = tmp_path / "runner"
    runner.mkdir()
    env = {**env, "TF_DIR": str(tf_dir), "ARTIFACT_DIR": str(tmp_path / "evidence"), "RUNNER_TEMP": str(runner)}
    proc = subprocess.run([BASH, str(ROOT / "scripts" / script)], env=env, capture_output=True, text=True,
                          timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _stored_backend(tf_dir) != str(previous)  # the previous account's backend is gone


def test_auth_test_refuses_an_unusable_backend_file(auth_runner, tmp_path):
    proc, summary, _ = auth_runner.run(REAL_PLAN, plan_rc=2, env={"BACKEND_CONFIG": str(tmp_path / "missing.hcl")})
    assert proc.returncode == 1
    assert proc.stdout.strip().splitlines()[-1] == "::error::auth-test failed: failure_code=preflight_failed"
    assert "init" not in [c.split()[1] for c in auth_runner.calls.read_text().splitlines() if c.split()[1:]]


# ---------------------------------------------------------------- configuration and workflow wiring

def test_dev_backend_is_partial():
    code = [ln for ln in BACKEND_TF.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    assert code == ["terraform {", '  backend "azurerm" {}', "}"]


def _steps(job: dict) -> list[dict]:
    return job["steps"]


def test_drift_workflow_verifies_state_storage_before_init():
    wf = yaml.safe_load(DRIFT_WORKFLOW.read_text(encoding="utf-8"))
    job = wf["jobs"]["plan-and-analyze"]
    names = [s["name"] for s in _steps(job)]
    order = ["Verify Azure OIDC Authentication", "Verify Terraform State Storage", "Setup Terraform",
             "Terraform Init (remote backend)", "Terraform Validate"]
    assert [n for n in names if n in order] == order
    assert names.index("Verify Terraform State Storage") == names.index("Verify Azure OIDC Authentication") + 1
    steps = {s["name"]: s for s in _steps(job)}
    guard = steps["Verify Terraform State Storage"]
    assert guard["id"] == "state_guard" and guard["run"].strip() == "./scripts/resolve_backend_config.sh"
    assert guard["env"] == GUARD_ENV and "continue-on-error" not in guard and "if" not in guard
    init = steps["Terraform Init (remote backend)"]
    assert init["env"]["BACKEND_CONFIG"] == "${{ runner.temp }}/backend.hcl"
    command = " ".join(init["run"].replace("\\\n", " ").split())
    assert ('terraform -chdir="${WORK_DIR}" init -input=false -reconfigure -backend-config="${BACKEND_CONFIG}" '
            "-lockfile=readonly -no-color") in command
    assert steps["Generate Plan Evidence"]["env"]["BACKEND_CONFIG"] == "${{ runner.temp }}/backend.hcl"
    assert job["outputs"]["state_guard_outcome"] == "${{ steps.state_guard.outcome }}"
    stages = wf["jobs"]["report"]["steps"]
    summary = next(s for s in stages if "STAGE_OUTCOMES" in s.get("env", {}))["env"]["STAGE_OUTCOMES"]
    assert ("Verify Azure OIDC Authentication=${{ needs.plan-and-analyze.outputs.auth_outcome || 'skipped' }}; "
            "Verify Terraform State Storage=${{ needs.plan-and-analyze.outputs.state_guard_outcome || 'skipped' }}; "
            "Setup Terraform=") in summary


def test_auth_workflow_verifies_state_storage_before_terraform():
    wf = yaml.safe_load(AUTH_WORKFLOW.read_text(encoding="utf-8"))
    steps = {s["name"]: s for s in wf["jobs"]["validate-and-plan"]["steps"]}
    assert steps["Verify Terraform State Storage"]["env"] == GUARD_ENV
    assert steps["Validate Dev Environment Configuration"]["env"]["BACKEND_CONFIG"] == "${{ runner.temp }}/backend.hcl"


def _code_lines(path: Path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def test_no_state_migration_and_no_apply_anywhere_in_ci_or_scripts():
    """CI is plan-only. The one apply in the repository is the local onboarding script's state bootstrap."""
    files = sorted((ROOT / ".github" / "workflows").glob("*.yml")) + sorted((ROOT / "scripts").glob("*.sh"))
    for path in files:
        joined = re.sub(r"\\\n\s*", " ", path.read_text(encoding="utf-8"))
        for line in (ln for ln in joined.splitlines() if ln.strip() and not ln.lstrip().startswith("#")):
            assert "-migrate-state" not in line, (path.name, line)
            if re.search(r"\bterraform\b.*\bapply\b", line):
                assert path.name == "onboard_azure_account.sh", (path.name, line)
                assert 'terraform -chdir="${BOOTSTRAP_DIR}" apply' in line, line


def test_every_remote_dev_init_reads_the_verified_backend():
    """A dev init either has no backend (offline validation) or reconfigures from the verified file."""
    files = sorted((ROOT / ".github" / "workflows").glob("*.yml")) + sorted((ROOT / "scripts").glob("*.sh"))
    seen = 0
    for path in files:
        text = re.sub(r"\\\n\s*", " ", path.read_text(encoding="utf-8"))
        for line in text.splitlines():
            if line.lstrip().startswith("#") or not re.search(r"\bterraform\s+-chdir=\S+\s+init\b", line):
                continue
            if "-backend=false" in line:
                continue
            if "BOOTSTRAP_DIR" in line or "terraform/bootstrap" in line:  # the bootstrap's own local state
                assert "-backend-config" not in line and "-reconfigure" not in line, (path.name, line)
                continue
            seen += 1
            assert "-reconfigure" in line or "init_args" in line, (path.name, line)
            assert "-backend-config" in line or "init_args" in line, (path.name, line)
    assert seen >= 3  # the drift workflow's init and both scripts' init
