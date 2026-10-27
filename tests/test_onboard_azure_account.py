"""Azure account switching, stage 3: scripts/onboard_azure_account.sh --config <file>.

The REAL script runs with fake `az`, `gh` and `terraform` binaries that log every call;
nothing reaches Azure or GitHub. Covered: the config file (missing, malformed, incomplete,
wrongly typed, placeholder, invalid, inconsistent, tracked or not ignored by git, and
valid), the dry run calls nothing, it refuses CI, the order of the steps (GitHub changes
only after the identity, roles and state-storage check), credentials only ever on stdin,
idempotent reuse in the same tenant, the client ID recorded back into the config file,
--sync-only, fail-fast stops, label binding, the issue clean-up and the bootstrap-only apply.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
sys.path.insert(0, str(TESTS))

from test_auth_test_workflow import _exe  # noqa: E402

pytestmark = pytest.mark.integration

SCRIPT = ROOT / "scripts" / "onboard_azure_account.sh"
EXAMPLE = ROOT / "config" / "azure-account.example.json"
BASH = shutil.which("bash") or "/bin/bash"
JQ = shutil.which("jq")
GIT = shutil.which("git")
BOOTSTRAP = ROOT / "terraform" / "bootstrap"
REPO = "HarshAgarwal1102/ai-terraform-drift-detector"
GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

FAKE_AZ = r"""#!/bin/sh
printf 'az %s\n' "$*" >> "${FAKE_LOG}"
case "$*" in
  "account show"*"--query id"*) echo "${FAKE_SUB}" ;;
  "account show"*"--query tenantId"*) echo "${FAKE_TENANT}" ;;
  "ad app list"*) if [ -n "${FAKE_EXISTING_APPS:-}" ]; then printf '%s\n' ${FAKE_EXISTING_APPS}; fi ;;
  "ad app show"*) if [ "${FAKE_APP_SHOW_RC:-0}" != 0 ]; then echo "not found" >&2; exit "${FAKE_APP_SHOW_RC}"; fi
                  echo "${FAKE_NEW_APP}" ;;
  "ad app create"*) echo "${FAKE_NEW_APP}" ;;
  "ad sp show"*) if [ "${FAKE_SP_EXISTS:-0}" = 1 ]; then echo "${FAKE_SP}"; else echo "not found" >&2; exit 3; fi ;;
  "ad sp create"*) echo "${FAKE_SP}" ;;
  "ad app federated-credential list"*) echo "${FAKE_FIC_COUNT:-0}" ;;
  "ad app federated-credential create"*)
    for a in "$@"; do case "$a" in @*) cat "${a#@}" > "${FAKE_FIC_FILE}" ;; esac; done ;;
  "role assignment list"*) echo "${FAKE_ROLE_COUNT:-0}" ;;
  "role assignment create"*) : ;;
  "storage account show"*) if [ "${FAKE_SA_RC:-0}" != 0 ]; then echo "not found" >&2; exit "${FAKE_SA_RC}"; fi
                           echo "${FAKE_SA_ID}" ;;
  *) echo "unexpected az $*" >&2; exit 97 ;;
esac
"""

FAKE_GH = r"""#!/bin/sh
printf 'gh %s\n' "$*" >> "${FAKE_LOG}"
case "$1 $2" in
  "auth status") exit "${FAKE_GH_AUTH_RC:-0}" ;;
  "secret set") printf '%s=%s\n' "$3" "$(cat)" >> "${FAKE_SECRETS}" ;;
  "variable set"|"issue close") : ;;
  "issue list") printf '11\n12\n' ;;
  *) case "$1" in
       api) case "$*" in
              *actions/variables*)
                if [ -n "${FAKE_VARS_FAIL:-}" ]; then echo "${FAKE_VARS_FAIL}" >&2; exit 1; fi
                if [ -n "${FAKE_PREV_KEY:-}" ]; then echo "${FAKE_PREV_KEY}"; fi ;;
              *) echo "HarshAgarwal1102@111/ai-terraform-drift-detector@222" ;;
            esac ;;
       *) echo "unexpected gh $*" >&2; exit 97 ;;
     esac ;;
esac
"""

FAKE_TERRAFORM = r"""#!/bin/sh
printf 'terraform %s\n' "$*" >> "${FAKE_LOG}"
case "$*" in
  *" apply "*) printf '%s %s\n' "${ARM_SUBSCRIPTION_ID}" "${ARM_TENANT_ID}" > "${FAKE_TF_ENV}"
               exit "${FAKE_TF_APPLY_RC:-0}" ;;
esac
exit 0
"""


class Account:
    def __init__(self) -> None:
        self.tenant = str(uuid.uuid4())
        self.subscription = str(uuid.uuid4())
        self.client = str(uuid.uuid4())
        self.sp = str(uuid.uuid4())


@pytest.fixture
def account() -> Account:
    return Account()


def make_config(account: Account, label: str = "2026-11", client_id: str | None = None) -> dict:
    storage = "aitddtf" + label.replace("-", "")
    return {
        "label": label,
        "azure": {"tenant_id": account.tenant, "subscription_id": account.subscription,
                  "client_id": client_id, "app_name": "aitdd-github-oidc"},
        "state_backend": {"resource_group": "aitdd-tfstate-rg", "storage_account": storage,
                          "container": "tfstate", "key": f"dev-{storage}.tfstate", "location": "Central India"},
        "github": {"repository": REPO},
    }


class Run:
    def __init__(self, proc, tmp: Path, config: Path):
        self.proc = proc
        self.tmp = tmp
        self.config = config
        log = tmp / "calls.log"
        self.calls = log.read_text().splitlines() if log.exists() else []
        secrets_file = tmp / "secrets.log"
        self.secrets = dict(line.split("=", 1) for line in secrets_file.read_text().splitlines()) \
            if secrets_file.exists() else {}
        self.state = tmp / "accounts"

    @property
    def text(self) -> str:
        return self.proc.stdout + self.proc.stderr

    def called(self, prefix: str) -> list[str]:
        return [c for c in self.calls if c.startswith(prefix)]

    def index(self, prefix: str) -> int:
        return next(i for i, c in enumerate(self.calls) if c.startswith(prefix))


def onboard(tmp: Path, account: Account, *args: str, config: dict | str | Path | None = None, apply=True,
            env=None, with_config_flag=True) -> Run:
    """Writes `config` (a dict, raw text, or an existing path; default: a valid config) and runs the script."""
    bindir = tmp / "bin"
    bindir.mkdir(exist_ok=True)
    _exe(bindir / "az", FAKE_AZ)
    _exe(bindir / "gh", FAKE_GH)
    _exe(bindir / "terraform", FAKE_TERRAFORM)
    if isinstance(config, Path):
        config_path = config
    else:
        config_path = tmp / "azure-account.json"
        body = config if isinstance(config, str) else json.dumps(config if config is not None else make_config(account))
        config_path.write_text(body)
    loaded = _load(config_path)
    sa = (loaded or {}).get("state_backend", {}).get("storage_account", "x") if isinstance(loaded, dict) else "x"
    sub = (loaded or {}).get("azure", {}).get("subscription_id", "x") if isinstance(loaded, dict) else "x"
    base = {"PATH": os.pathsep.join([str(bindir), str(Path(JQ).parent), "/usr/bin", "/bin"]), "HOME": str(tmp),
            "FAKE_LOG": str(tmp / "calls.log"), "FAKE_SECRETS": str(tmp / "secrets.log"),
            "FAKE_FIC_FILE": str(tmp / "fic.json"), "FAKE_TF_ENV": str(tmp / "tf_env"),
            "FAKE_SUB": account.subscription, "FAKE_TENANT": account.tenant, "FAKE_NEW_APP": account.client,
            "FAKE_SP": account.sp, "ONBOARD_STATE_DIR": str(tmp / "accounts"),
            "FAKE_SA_ID": f"/subscriptions/{sub}/resourceGroups/aitdd-tfstate-rg/providers/"
                          f"Microsoft.Storage/storageAccounts/{sa}"}
    argv = (["--config", str(config_path)] if with_config_flag else []) + list(args)
    if apply:
        argv.append("--apply")
    proc = subprocess.run([BASH, str(SCRIPT), *argv], env={**base, **(env or {})}, capture_output=True, text=True,
                          timeout=60)
    return Run(proc, tmp, config_path)


def _load(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def without(config: dict, dotted: str) -> dict:
    out = copy.deepcopy(config)
    *parents, last = dotted.split(".")
    node = out
    for p in parents:
        node = node[p]
    del node[last]
    return out


def with_value(config: dict, dotted: str, value) -> dict:
    out = copy.deepcopy(config)
    *parents, last = dotted.split(".")
    node = out
    for p in parents:
        node = node[p]
    node[last] = value
    return out


def assert_ids_not_shown(run: Run, account: Account) -> None:
    for value in (account.tenant, account.subscription, account.client, account.sp):
        assert value not in run.text, value


def assert_refused(run: Run, message: str) -> None:
    assert run.proc.returncode == 2, run.text
    assert run.proc.stderr.startswith("onboard: "), run.proc.stderr
    assert message in run.proc.stderr, run.proc.stderr
    assert run.calls == [] and run.secrets == {} and not run.state.exists()


REQUIRED = ["label", "azure.tenant_id", "azure.subscription_id", "azure.app_name", "state_backend.resource_group",
            "state_backend.storage_account", "state_backend.container", "state_backend.key", "state_backend.location",
            "github.repository"]


# ---------------------------------------------------------------- the config file: valid

def test_dry_run_prints_the_plan_and_calls_nothing(tmp_path, account):
    run = onboard(tmp_path, account, apply=False)
    assert run.proc.returncode == 0, run.proc.stderr
    assert run.calls == [] and run.secrets == {}
    assert not run.state.exists()  # nothing written either
    out = run.proc.stdout
    assert "DRY RUN" in out and "add --apply" in out and str(run.config) in out
    for expected in ("workspace '2026-11'", "storage account aitddtf202611", "TFSTATE_KEY=dev-aitddtf202611.tfstate",
                     "Reader on the subscription", "Storage Blob Data Contributor on container tfstate only",
                     "state storage ownership check", f"…{account.tenant[-4:]}", f"…{account.subscription[-4:]}"):
        assert expected in out, expected
    assert_ids_not_shown(run, account)
    assert json.loads(run.config.read_text()) == make_config(account)  # the file is only read


def test_upper_case_ids_and_a_comment_are_accepted(tmp_path, account):
    config = make_config(account, client_id=account.client.upper())
    config["azure"]["tenant_id"] = account.tenant.upper()
    config["_comment"] = "November account"
    run = onboard(tmp_path, account, config=config)
    assert run.proc.returncode == 0, run.proc.stderr
    assert run.secrets == {"AZURE_TENANT_ID": account.tenant, "AZURE_CLIENT_ID": account.client,
                           "AZURE_SUBSCRIPTION_ID": account.subscription}


# ---------------------------------------------------------------- the config file: missing or malformed

def test_the_config_flag_is_required(tmp_path, account):
    assert_refused(onboard(tmp_path, account, with_config_flag=False), "--config is required")


def test_a_missing_config_file_is_refused(tmp_path, account):
    assert_refused(onboard(tmp_path, account, config=tmp_path / "nope.json"), "not found or not readable")


def test_a_symlinked_config_file_is_refused(tmp_path, account):
    real = tmp_path / "real.json"
    real.write_text(json.dumps(make_config(account)))
    link = tmp_path / "link.json"
    link.symlink_to(real)
    assert_refused(onboard(tmp_path, account, config=link), "not a symbolic link")


@pytest.mark.parametrize("body, message", [
    ("{not json", "is not valid JSON"),
    ('{"label": "2026-11",}', "is not valid JSON"),
    ("", "exactly one JSON object"),
    ("[]", "exactly one JSON object"),
    ("null", "exactly one JSON object"),
    ('"2026-11"', "exactly one JSON object"),
    ('{"label": "a"} {"label": "b"}', "exactly one JSON object"),
])
def test_malformed_config_is_refused(tmp_path, account, body, message):
    assert_refused(onboard(tmp_path, account, config=body), message)


@pytest.mark.parametrize("section", ["azure", "state_backend", "github"])
def test_a_missing_section_is_refused(tmp_path, account, section):
    assert_refused(onboard(tmp_path, account, config=without(make_config(account), section)),
                   f"missing section {section}")


@pytest.mark.parametrize("field", REQUIRED)
def test_a_missing_field_is_refused(tmp_path, account, field):
    assert_refused(onboard(tmp_path, account, config=without(make_config(account), field)), f"missing field {field}")


def test_client_id_must_be_present_even_when_null(tmp_path, account):
    assert_refused(onboard(tmp_path, account, config=without(make_config(account), "azure.client_id")),
                   "missing field azure.client_id")


def test_every_problem_is_reported_at_once(tmp_path, account):
    config = without(without(make_config(account), "label"), "state_backend.key")
    run = onboard(tmp_path, account, config=config)
    assert_refused(run, "missing field label")
    assert "missing field state_backend.key" in run.proc.stderr


@pytest.mark.parametrize("field, value, message", [
    ("label", 202611, "field label must be a string"),
    ("azure.tenant_id", ["x"], "field azure.tenant_id must be a string"),
    ("azure.client_id", 5, "azure.client_id must be a GUID string or null"),
    ("state_backend.key", True, "field state_backend.key must be a string"),
    ("_comment", 1, "_comment must be a string"),
])
def test_wrong_types_are_refused(tmp_path, account, field, value, message):
    assert_refused(onboard(tmp_path, account, config=with_value(make_config(account), field, value)), message)


@pytest.mark.parametrize("field", ["azure.client_secret", "password", "github.token", "state_backend.access_key",
                                   "azure.tenantid"])
def test_unknown_fields_such_as_secrets_are_refused(tmp_path, account, field):
    run = onboard(tmp_path, account, config=with_value(make_config(account), field, "s3cr3t-value"))
    assert_refused(run, f"unknown field {field} (the file holds identifiers only, never a secret)")
    assert "s3cr3t-value" not in run.text


def test_the_example_template_still_has_placeholders(tmp_path, account):
    copied = tmp_path / "azure-account.json"
    shutil.copy(EXAMPLE, copied)
    assert_refused(onboard(tmp_path, account, config=copied), "label is still a placeholder")


@pytest.mark.parametrize("field", ["azure.tenant_id", "azure.subscription_id", "azure.client_id",
                                   "state_backend.storage_account", "state_backend.key"])
def test_any_placeholder_is_refused(tmp_path, account, field):
    run = onboard(tmp_path, account, config=with_value(make_config(account), field, "<fill me in>"))
    assert_refused(run, f"{field} is still a placeholder")


# ---------------------------------------------------------------- the config file: invalid values

@pytest.mark.parametrize("field, value", [
    ("label", "Bad"), ("label", "-x"), ("label", "a" * 25), ("label", "2026/11"), ("label", ""),
    ("azure.tenant_id", "not-a-guid"), ("azure.subscription_id", "12345"), ("azure.client_id", "abc"),
    ("azure.app_name", "-app"),
    ("state_backend.storage_account", "Has-Dash"), ("state_backend.storage_account", "ab"),
    ("state_backend.container", "tf--state"), ("state_backend.resource_group", "rg."),
    ("state_backend.location", "x;rm -rf /"), ("github.repository", "no-slash"),
    ("azure.tenant_id", "11111111-1111-4111-8111-111111111111\nextra"),
])
def test_invalid_values_are_refused_before_any_call(tmp_path, account, field, value):
    run = onboard(tmp_path, account, config=with_value(make_config(account), field, value))
    assert_refused(run, field)


@pytest.mark.parametrize("args, message", [
    (["--oidc-subject", "repo:o/r:pull_request"], "--oidc-subject must be the main-branch subject"),
    (["--oidc-subject", "repo:o/r']|[?x:ref:refs/heads/main"], "--oidc-subject must be the main-branch subject"),
    (["--unknown"], "unknown option"),
    (["--config"], "--config needs a value"),
    (["--tenant", "x"], "account settings come from the --config file only"),
    (["--label", "2026-11"], "account settings come from the --config file only"),
    (["--storage-account", "x"], "account settings come from the --config file only"),
])
def test_invalid_options_are_refused(tmp_path, account, args, message):
    alone = args == ["--config"]  # --config as the last argument, with no value
    assert_refused(onboard(tmp_path, account, *args, with_config_flag=not alone, apply=not alone), message)


# ---------------------------------------------------------------- the config file: inconsistent values

FIRST = {"resource_group": "aitdd-tfstate-rg", "storage_account": "aitddtfstatesa001", "container": "tfstate",
         "key": "dev.tfstate", "location": "Central India"}  # the October account, synced as it is


@pytest.mark.parametrize("key", ["dev-2026-11.tfstate",  # the earlier label-based rule
                                 "dev.tfstate", "dev-aitddtfstatesa001.tfstate", "dev-aitddtf202612.tfstate",
                                 "dev-AITDDTF202611.tfstate", "aitddtf202611.tfstate"])
@pytest.mark.parametrize("sync_only", [False, True])
def test_the_key_must_name_the_storage_account(tmp_path, account, key, sync_only):
    """The rule CI enforces too: dev-<storage_account>.tfstate, so two accounts never share a key."""
    config = with_value(make_config(account, client_id=account.client), "state_backend.key", key)
    args = ["--sync-only"] if sync_only else []
    assert_refused(onboard(tmp_path, account, *args, config=config),
                   "state_backend.key must be dev-aitddtf202611.tfstate (the key names state_backend.storage_account)")


@pytest.mark.parametrize("storage", ["abc", "mystatestorage", "a" * 24])
def test_any_new_storage_account_gives_its_own_key(tmp_path, account, storage):
    config = with_value(make_config(account), "state_backend.storage_account", storage)
    config["state_backend"]["key"] = f"dev-{storage}.tfstate"
    run = onboard(tmp_path, account, config=config, apply=False)
    assert run.proc.returncode == 0, run.proc.stderr
    assert f"TFSTATE_KEY=dev-{storage}.tfstate" in run.proc.stdout


def test_the_first_account_keeps_dev_tfstate_with_sync_only(tmp_path, account):
    config = with_value(make_config(account, label="2026-10", client_id=account.client), "state_backend", FIRST)
    run = onboard(tmp_path, account, "--sync-only", config=config, apply=False)
    assert run.proc.returncode == 0, run.proc.stderr
    assert "TFSTATE_STORAGE_ACCOUNT=aitddtfstatesa001" in run.proc.stdout and "TFSTATE_KEY=dev.tfstate" in run.proc.stdout
    assert_refused(onboard(tmp_path, account, config=config), "aitddtfstatesa001 (dev.tfstate) is the first account's")


@pytest.mark.parametrize("key", ["dev-aitddtfstatesa001.tfstate", "dev-aitddtf202610.tfstate"])
def test_the_first_accounts_storage_only_takes_dev_tfstate(tmp_path, account, key):
    config = with_value(make_config(account, label="2026-10", client_id=account.client), "state_backend",
                        {**FIRST, "key": key})
    assert_refused(onboard(tmp_path, account, "--sync-only", config=config),
                   "state_backend.key must be dev.tfstate (the key names state_backend.storage_account)")


def test_tenant_and_subscription_must_differ(tmp_path, account):
    config = with_value(make_config(account), "azure.subscription_id", account.tenant)
    assert_refused(onboard(tmp_path, account, config=config), "are the same value")


@pytest.mark.parametrize("which", ["tenant", "subscription"])
def test_client_id_must_differ_from_the_tenant_and_subscription(tmp_path, account, which):
    config = make_config(account, client_id=getattr(account, which))
    assert_refused(onboard(tmp_path, account, config=config), "azure.client_id must differ")


def test_sync_only_needs_a_client_id(tmp_path, account):
    assert_refused(onboard(tmp_path, account, "--sync-only"), "azure.client_id is required with --sync-only")


def _origin() -> str | None:
    if not GIT:
        return None
    proc = subprocess.run([GIT, "-C", str(ROOT), "remote", "get-url", "origin"], capture_output=True, text=True)
    match = re.search(r"github\.com[/:]([A-Za-z0-9-]+/[A-Za-z0-9._-]+?)(?:\.git)?$", proc.stdout.strip())
    return match.group(1) if match else None


def test_the_repository_must_be_this_checkouts_origin(tmp_path, account):
    if _origin() is None:
        pytest.skip("no GitHub origin in this checkout")
    config = with_value(make_config(account), "github.repository", "SomeoneElse/ai-terraform-drift-detector")
    assert_refused(onboard(tmp_path, account, config=config), "is not this checkout's origin")


# ---------------------------------------------------------------- the config file and git

def _git_ok() -> bool:
    return bool(GIT) and subprocess.run([GIT, "-C", str(ROOT), "rev-parse", "--git-dir"],
                                        capture_output=True).returncode == 0


@pytest.mark.skipif(not _git_ok(), reason="not a git checkout")
def test_gitignore_keeps_real_configs_out_and_the_template_in():
    def ignored(rel: str) -> bool:
        return subprocess.run([GIT, "-C", str(ROOT), "check-ignore", "-q", "--no-index", rel]).returncode == 0
    assert ignored("config/azure-account.json")
    assert ignored("config/azure-account.2026-11.json")
    assert ignored("config/azure-account.json.bak")  # regression: a backup copy was committable
    assert not ignored("config/azure-account.example.json")
    tracked = subprocess.run([GIT, "-C", str(ROOT), "ls-files", "config/azure-account.json",
                              "config/azure-account.*.json"], capture_output=True, text=True).stdout.split()
    assert all(path == "config/azure-account.example.json" for path in tracked), tracked


@pytest.mark.skipif(not _git_ok(), reason="not a git checkout")
def test_a_config_inside_the_repository_must_be_ignored(tmp_path, account):
    # The committed template is tracked; before its first commit it is merely not ignored.
    template_tracked = subprocess.run([GIT, "-C", str(ROOT), "ls-files", "--error-unmatch", "--",
                                       str(EXAMPLE.relative_to(ROOT))], capture_output=True).returncode == 0
    assert_refused(onboard(tmp_path, account, config=EXAMPLE),
                   "is tracked by git" if template_tracked else "is not ignored by git")
    stray = ROOT / "config" / f"pytest-{uuid.uuid4().hex}.json"
    try:
        stray.write_text(json.dumps(make_config(account)))
        assert_refused(onboard(tmp_path, account, config=stray), "is not ignored by git")
    finally:
        stray.unlink(missing_ok=True)


@pytest.mark.skipif(not _git_ok(), reason="not a git checkout")
def test_a_symlinked_directory_cannot_hide_a_config_inside_the_repository(tmp_path, account):
    """Regression: the git checks compared logical paths, so a path through a symlink skipped them."""
    name = f"pytest-{uuid.uuid4().hex}.json"
    stray = ROOT / "config" / name
    link = tmp_path / "elsewhere"
    link.symlink_to(ROOT / "config", target_is_directory=True)
    try:
        stray.write_text(json.dumps(make_config(account)))
        assert_refused(onboard(tmp_path, account, config=link / name), "is not ignored by git")
    finally:
        stray.unlink(missing_ok=True)


@pytest.mark.skipif(not _git_ok(), reason="not a git checkout")
def test_an_ignored_config_inside_the_repository_is_accepted(tmp_path, account):
    ignored = ROOT / "config" / f"azure-account.pytest-{uuid.uuid4().hex[:8]}.json"
    try:
        ignored.write_text(json.dumps(make_config(account)))
        run = onboard(tmp_path, account, config=ignored, apply=False)
        assert run.proc.returncode == 0, run.proc.stderr
    finally:
        ignored.unlink(missing_ok=True)


def test_the_example_is_a_safe_complete_template():
    text = EXAMPLE.read_text(encoding="utf-8")
    example = json.loads(text)
    assert not GUID.search(text)  # no real or real-looking IDs
    assert set(example) == {"_comment", "label", "azure", "state_backend", "github"}
    assert set(example["azure"]) == {"tenant_id", "subscription_id", "client_id", "app_name"}
    assert set(example["state_backend"]) == {"resource_group", "storage_account", "container", "key", "location"}
    assert set(example["github"]) == {"repository"}
    assert example["azure"]["client_id"] is None
    for value in (example["label"], example["azure"]["tenant_id"], example["azure"]["subscription_id"],
                  example["state_backend"]["storage_account"], example["state_backend"]["key"]):
        assert value.startswith("<"), value  # must be filled in, or the script refuses it
    assert re.search(r"secret|password|token|key", example["_comment"], re.I)  # says what never goes in


# ---------------------------------------------------------------- precondition

def test_it_refuses_to_run_in_github_actions(tmp_path, account):
    run = onboard(tmp_path, account, env={"GITHUB_ACTIONS": "true"})
    assert_refused(run, "never in GitHub Actions")


def test_a_label_stays_bound_to_its_account(tmp_path, account):
    first = onboard(tmp_path, account)
    assert first.proc.returncode == 0, first.proc.stderr
    other = Account()
    (tmp_path / "calls.log").unlink()
    run = onboard(tmp_path, other)  # same label, another tenant and subscription
    assert run.proc.returncode == 2 and "already belongs to another Azure account" in run.proc.stderr
    assert run.calls == []


def _bind(tmp_path: Path, label: str, key: str, account: Account) -> None:
    """A local marker as an earlier onboarding on this machine left it."""
    folder = tmp_path / "accounts" / label
    folder.mkdir(parents=True)
    (folder / "account.json").write_text(json.dumps({
        "label": label, "tenant": account.tenant, "subscription": account.subscription,
        "storage_account": "aitddtfstatesa001", "key": key}))


def _first_account_config(account: Account, label: str) -> dict:
    return with_value(make_config(account, label=label, client_id=account.client), "state_backend", FIRST)


@pytest.mark.parametrize("apply", [False, True])
def test_a_state_key_stays_bound_to_its_account(tmp_path, account, apply):
    """Two labels, one key, two accounts: refused before any call, even in a dry run."""
    first = Account()
    _bind(tmp_path, "2026-10", "dev.tfstate", first)
    run = onboard(tmp_path, account, "--sync-only", config=_first_account_config(account, "2026-12"), apply=apply)
    assert run.proc.returncode == 2, run.text
    assert "state key dev.tfstate already belongs to another Azure account (label '2026-10')" in run.proc.stderr
    assert run.calls == [] and run.secrets == {} and not (run.state / "2026-12").exists()
    assert_ids_not_shown(run, account)
    assert_ids_not_shown(run, first)


def test_the_same_account_may_keep_its_key_under_another_label(tmp_path, account):
    _bind(tmp_path, "2026-10", "dev.tfstate", account)
    run = onboard(tmp_path, account, "--sync-only", config=_first_account_config(account, "2026-12"))
    assert run.proc.returncode == 0, run.proc.stderr


def test_other_labels_with_other_keys_do_not_conflict(tmp_path, account):
    _bind(tmp_path, "2026-10", "dev.tfstate", Account())
    _bind(tmp_path, "2026-12", "dev-aitddtf202612.tfstate", Account())
    run = onboard(tmp_path, account)  # 2026-11, dev-aitddtf202611.tfstate
    assert run.proc.returncode == 0, run.proc.stderr


def test_an_unreadable_marker_is_refused(tmp_path, account):
    folder = tmp_path / "accounts" / "2026-10"
    folder.mkdir(parents=True)
    (folder / "account.json").write_text("{not json")
    run = onboard(tmp_path, account)
    assert run.proc.returncode == 2 and "unreadable" in run.proc.stderr and run.calls == []


# ---------------------------------------------------------------- apply

def test_new_tenant_creates_everything_in_order_and_github_last(tmp_path, account):
    run = onboard(tmp_path, account)
    assert run.proc.returncode == 0, run.proc.stderr
    assert_ids_not_shown(run, account)
    boot = f"terraform -chdir={BOOTSTRAP}"
    assert run.called("terraform") == [
        f"{boot} init -input=false -no-color",
        f"{boot} workspace select -or-create=true 2026-11",
        f"{boot} apply -input=false -auto-approve -no-color -var resource_group_name=aitdd-tfstate-rg "
        "-var storage_account_name=aitddtf202611 -var container_name=tfstate -var location=Central India"]
    assert (tmp_path / "tf_env").read_text().split() == [account.subscription, account.tenant]
    sub = f"/subscriptions/{account.subscription}"
    container = (f"{sub}/resourceGroups/aitdd-tfstate-rg/providers/Microsoft.Storage/storageAccounts/aitddtf202611"
                 "/blobServices/default/containers/tfstate")
    creates = [c for c in run.calls if " create " in f" {c} "]
    assert creates == [
        "az ad app create --only-show-errors --display-name aitdd-github-oidc --sign-in-audience AzureADMyOrg "
        "--query appId --output tsv",
        f"az ad sp create --only-show-errors --id {account.client} --query id --output tsv",
        f"az ad app federated-credential create --only-show-errors --id {account.client} "
        f"--parameters @{run.state / '2026-11' / 'federated-credential.json'} --output none",
        f"az role assignment create --only-show-errors --assignee-object-id {account.sp} --assignee-principal-type "
        f"ServicePrincipal --role Reader --scope {sub} --output none",
        f"az role assignment create --only-show-errors --assignee-object-id {account.sp} --assignee-principal-type "
        f"ServicePrincipal --role Storage Blob Data Contributor --scope {container} --output none"]
    fic = json.loads((tmp_path / "fic.json").read_text())
    assert fic == {"name": "github-main", "issuer": "https://token.actions.githubusercontent.com",
                   "subject": "repo:HarshAgarwal1102@111/ai-terraform-drift-detector@222:ref:refs/heads/main",
                   "audiences": ["api://AzureADTokenExchange"],
                   "description": "GitHub Actions, main branch (drift detection, plan only)"}
    # The CI ownership check runs after the roles; GitHub changes only after all of it.
    guard = run.index("az storage account show")
    assert run.calls[guard] == (f"az storage account show --only-show-errors --name aitddtf202611 --resource-group "
                                f"aitdd-tfstate-rg --subscription {account.subscription} --query id --output tsv")
    assert guard > max(i for i, c in enumerate(run.calls) if c.startswith("az role assignment create"))
    first_github_change = run.index("gh secret set")
    assert first_github_change > guard > run.index(f"{boot} apply")
    assert run.called("gh secret set") == [f"gh secret set {name} --repo {REPO}" for name in
                                            ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_SUBSCRIPTION_ID")]
    assert run.secrets == {"AZURE_TENANT_ID": account.tenant, "AZURE_CLIENT_ID": account.client,
                           "AZURE_SUBSCRIPTION_ID": account.subscription}  # delivered on stdin
    assert run.called("gh variable set") == [
        f"gh variable set TFSTATE_RESOURCE_GROUP --repo {REPO} --body aitdd-tfstate-rg",
        f"gh variable set TFSTATE_STORAGE_ACCOUNT --repo {REPO} --body aitddtf202611",
        f"gh variable set TFSTATE_CONTAINER --repo {REPO} --body tfstate",
        f"gh variable set TFSTATE_KEY --repo {REPO} --body dev-aitddtf202611.tfstate"]
    assert run.called("gh issue") == []  # closing issues is opt-in
    for call in run.calls:  # no credential as an argument, no migration, no other apply
        assert "-migrate-state" not in call
        if call.startswith("gh "):
            for value in (account.tenant, account.subscription, account.client):
                assert value not in call, call
    # Your own local init: no use_azuread_auth, so an Owner without a data-plane role can init.
    assert (run.state / "2026-11" / "backend.hcl").read_text() == (
        'resource_group_name  = "aitdd-tfstate-rg"\nstorage_account_name = "aitddtf202611"\n'
        'container_name       = "tfstate"\nkey                  = "dev-aitddtf202611.tfstate"\n')
    assert not (run.state / "2026-11" / "backend.hcl.pending").exists()
    marker = json.loads((run.state / "2026-11" / "account.json").read_text())
    assert (marker["tenant"], marker["subscription"], marker["key"]) == (account.tenant, account.subscription,
                                                                          "dev-aitddtf202611.tfstate")
    # The config file stays the single source of truth: it now names the created app.
    assert json.loads(run.config.read_text()) == make_config(account, client_id=account.client)
    assert f"…{account.client[-4:]}" in run.proc.stdout
    assert "Done: account '2026-11' is configured" in run.proc.stdout
    assert "the first scan sees an empty state" in run.proc.stdout and "synced to GitHub" not in run.proc.stdout


def test_a_configured_client_id_is_used_and_never_looked_up_by_name(tmp_path, account):
    run = onboard(tmp_path, account, config=make_config(account, client_id=account.client),
                  env={"FAKE_SP_EXISTS": "1", "FAKE_FIC_COUNT": "1", "FAKE_ROLE_COUNT": "1"})
    assert run.proc.returncode == 0, run.proc.stderr
    assert run.called("az ad app show") == [f"az ad app show --only-show-errors --id {account.client} "
                                            "--query appId --output tsv"]
    assert run.called("az ad app list") == [] and [c for c in run.calls if " create " in f" {c} "] == []
    assert run.secrets["AZURE_CLIENT_ID"] == account.client
    assert json.loads(run.config.read_text()) == make_config(account, client_id=account.client)  # unchanged
    assert_ids_not_shown(run, account)


def test_a_client_id_that_is_not_in_the_tenant_stops_before_github(tmp_path, account):
    run = onboard(tmp_path, account, config=make_config(account, client_id=account.client),
                  env={"FAKE_APP_SHOW_RC": "3"})
    assert run.proc.returncode == 1 and "FAILED at step 'identity'" in run.proc.stderr
    assert run.called("gh secret") == [] and run.called("gh variable") == [] and run.called("az role") == []


def test_same_tenant_reuses_the_app_credential_and_roles(tmp_path, account):
    run = onboard(tmp_path, account, env={"FAKE_EXISTING_APPS": account.client, "FAKE_SP_EXISTS": "1",
                                          "FAKE_FIC_COUNT": "1", "FAKE_ROLE_COUNT": "1"})
    assert run.proc.returncode == 0, run.proc.stderr
    assert [c for c in run.calls if " create " in f" {c} "] == []  # nothing duplicated
    assert run.secrets["AZURE_CLIENT_ID"] == account.client
    assert run.called("gh variable set TFSTATE_KEY")
    assert json.loads(run.config.read_text())["azure"]["client_id"] == account.client


def test_az_signed_in_elsewhere_changes_nothing(tmp_path, account):
    run = onboard(tmp_path, account, env={"FAKE_SUB": str(uuid.uuid4())})
    assert run.proc.returncode == 1
    assert "FAILED at step 'azure_context'" in run.proc.stderr
    assert run.called("terraform") == [] and run.called("gh") == [] and run.secrets == {}
    assert_ids_not_shown(run, account)


def test_a_failed_bootstrap_leaves_github_and_entra_unchanged(tmp_path, account):
    run = onboard(tmp_path, account, env={"FAKE_TF_APPLY_RC": "1"})
    assert run.proc.returncode == 1 and "FAILED at step 'bootstrap'" in run.proc.stderr
    assert run.called("az ad") == [] and run.called("az role") == []
    assert run.called("gh secret") == [] and run.called("gh variable") == []
    assert json.loads(run.config.read_text())["azure"]["client_id"] is None


def test_ambiguous_app_names_stop_before_github(tmp_path, account):
    run = onboard(tmp_path, account, env={"FAKE_EXISTING_APPS": f"{uuid.uuid4()} {uuid.uuid4()}"})
    assert run.proc.returncode == 1 and "FAILED at step 'identity'" in run.proc.stderr
    assert run.called("gh secret") == [] and run.called("az role") == []


def test_a_missing_gh_login_stops_before_any_change(tmp_path, account):
    run = onboard(tmp_path, account, env={"FAKE_GH_AUTH_RC": "1"})
    assert run.proc.returncode == 1 and "gh is not signed in" in run.proc.stderr
    assert run.called("terraform") == [] and run.called("az ad") == []


@pytest.mark.parametrize("env, code", [
    ({"FAKE_SA_RC": "3"}, "state_storage_unavailable"),
    ({"FAKE_SA_ID": "/subscriptions/00000000-0000-4000-8000-000000000000/resourceGroups/aitdd-tfstate-rg/"
                    "providers/Microsoft.Storage/storageAccounts/aitddtf202611"}, "state_storage_not_in_subscription"),
])
def test_a_failed_ownership_check_leaves_github_unchanged(tmp_path, account, env, code):
    run = onboard(tmp_path, account, env=env)
    assert run.proc.returncode == 1 and "FAILED at step 'state_storage'" in run.proc.stderr
    assert f"failure_code={code}" in run.proc.stdout
    assert run.called("gh secret") == [] and run.called("gh variable") == []
    assert not (run.state / "2026-11" / "backend.hcl").exists()
    assert_ids_not_shown(run, account)


def test_closing_the_previous_accounts_issues_is_explicit(tmp_path, account):
    run = onboard(tmp_path, account, "--close-open-drift-issues")
    assert run.proc.returncode == 0, run.proc.stderr
    assert run.called("gh issue list") == [f"gh issue list --repo {REPO} --label drift-detected --state open "
                                           "--limit 200 --json number --jq .[].number"]
    closes = run.called("gh issue close")
    assert [c.split()[3] for c in closes] == ["11", "12"]
    assert all('--reason not planned' in c and "Closed by the switch to Azure account '2026-11'" in c for c in closes)
    lookup = run.index("gh api --paginate repos/HarshAgarwal1102/ai-terraform-drift-detector/actions/variables")  # read before any change, in Azure or GitHub
    assert lookup < run.index("terraform") and lookup < run.index("az ad") and lookup < run.index("gh secret set")


def test_a_rerun_for_the_same_account_never_closes_its_issues(tmp_path, account):
    """Regression: re-running --apply with the flag closed the CURRENT account's open issues."""
    run = onboard(tmp_path, account, "--close-open-drift-issues", env={"FAKE_PREV_KEY": "dev-aitddtf202611.tfstate"})
    assert run.proc.returncode == 0, run.proc.stderr
    assert run.called("gh issue") == []
    assert "Not closing drift-detected issues" in run.proc.stdout


def test_a_switch_from_another_key_closes_the_previous_accounts_issues(tmp_path, account):
    run = onboard(tmp_path, account, "--close-open-drift-issues", env={"FAKE_PREV_KEY": "dev.tfstate"})
    assert run.proc.returncode == 0, run.proc.stderr
    assert len(run.called("gh issue close")) == 2


@pytest.mark.parametrize("failure", ["gh: Server Error (HTTP 500)", "error connecting to api.github.com",
                                     "gh: Resource not accessible by integration (HTTP 403)"])
def test_a_failed_tfstate_key_lookup_stops_before_any_change(tmp_path, account, failure):
    """Regression: an API or network error was read as "no TFSTATE_KEY", so issues could be closed."""
    run = onboard(tmp_path, account, "--close-open-drift-issues", env={"FAKE_VARS_FAIL": failure})
    assert run.proc.returncode == 1 and "FAILED at step 'github_preflight'" in run.proc.stderr
    assert "could not read the repository variables" in run.proc.stderr
    assert run.called("terraform") == [] and run.called("az ad") == [] and run.called("az role") == []
    assert run.called("gh secret") == [] and run.called("gh variable") == [] and run.called("gh issue") == []
    assert_ids_not_shown(run, account)


def test_the_tfstate_key_lookup_runs_only_when_closing_issues(tmp_path, account):
    run = onboard(tmp_path, account, env={"FAKE_VARS_FAIL": "gh: Server Error (HTTP 500)"})
    assert run.proc.returncode == 0, run.proc.stderr
    assert run.called("gh api --paginate repos/HarshAgarwal1102/ai-terraform-drift-detector/actions/variables") == []


def test_sync_only_refuses_to_close_issues(tmp_path, account):
    """Regression: --sync-only keeps the account, so closing would retire its own current issues."""
    run = onboard(tmp_path, account, "--sync-only", "--close-open-drift-issues",
                  config=make_config(account, client_id=account.client))
    assert_refused(run, "not allowed with --sync-only")


def test_an_explicit_subject_is_used_without_reading_the_repository(tmp_path, account):
    subject = "repo:SomeOwner/some-repo:ref:refs/heads/main"
    run = onboard(tmp_path, account, "--oidc-subject", subject)
    assert run.proc.returncode == 0, run.proc.stderr
    assert run.called("gh api") == []
    assert json.loads((tmp_path / "fic.json").read_text())["subject"] == subject


# ---------------------------------------------------------------- --sync-only

def test_sync_only_creates_nothing_and_syncs_github_after_the_checks(tmp_path, account):
    config = with_value(make_config(account, label="2026-10", client_id=account.client), "state_backend", {
        "resource_group": "aitdd-tfstate-rg", "storage_account": "aitddtfstatesa001", "container": "tfstate",
        "key": "dev.tfstate", "location": "Central India"})  # the first account's existing storage
    run = onboard(tmp_path, account, "--sync-only", config=config)
    assert run.proc.returncode == 0, run.proc.stderr
    assert run.called("terraform") == [] and run.called("gh api") == []
    assert [c for c in run.calls if " create " in f" {c} "] == [] and run.called("az ad sp") == []
    assert run.called("az ad app list") == [] and run.called("az role") == []
    assert run.index("az ad app show") < run.index("az storage account show") < run.index("gh secret set")
    assert run.secrets == {"AZURE_TENANT_ID": account.tenant, "AZURE_CLIENT_ID": account.client,
                           "AZURE_SUBSCRIPTION_ID": account.subscription}
    assert f"gh variable set TFSTATE_KEY --repo {REPO} --body dev.tfstate" in run.calls
    backend = (run.state / "2026-10" / "backend.hcl").read_text()
    assert 'key                  = "dev.tfstate"' in backend and "use_azuread_auth" not in backend
    assert run.called("gh issue") == [] and run.called("az storage account create") == []
    assert json.loads(run.config.read_text()) == config
    out = run.proc.stdout
    assert "Done: account '2026-10' is synced to GitHub" in out and "Nothing was created in Azure" in out
    assert "the state (aitddtfstatesa001/tfstate/dev.tfstate) and its backend are unchanged" in out
    for misleading in ("empty state", "deploy", "propagate", "is configured"):  # new-account wording
        assert misleading not in out, misleading
    assert_ids_not_shown(run, account)


def test_sync_only_dry_run_says_what_is_skipped(tmp_path, account):
    run = onboard(tmp_path, account, "--sync-only", config=make_config(account, client_id=account.client),
                  apply=False)
    assert run.proc.returncode == 0, run.proc.stderr
    assert "skipped (--sync-only" in run.proc.stdout and "nothing is created (--sync-only)" in run.proc.stdout
    assert "previous account: no (never with --sync-only)" in run.proc.stdout
    assert run.calls == []


def test_sync_only_with_missing_storage_leaves_github_unchanged(tmp_path, account):
    run = onboard(tmp_path, account, "--sync-only", config=make_config(account, client_id=account.client),
                  env={"FAKE_SA_RC": "3"})
    assert run.proc.returncode == 1 and "FAILED at step 'state_storage'" in run.proc.stderr
    assert run.called("gh secret") == [] and run.called("gh variable") == []


# ---------------------------------------------------------------- the script itself

def test_script_is_executable_and_hardened():
    assert os.access(SCRIPT, os.X_OK)
    code = [ln for ln in SCRIPT.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    assert code[:3] == ["set +x", "set -uo pipefail", "umask 077"]
    assert "-migrate-state" not in "\n".join(code)
    assert "environments/dev" not in "\n".join(code)  # never touches the dev workload
