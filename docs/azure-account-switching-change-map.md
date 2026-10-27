# Change map: monthly Azure Free Account switching

**Goal:** use a new Azure account each month with the same `dev` environment and Resource Group
configuration, by editing **one local file**. Each account gets its own Terraform state, CI stays
plan-only, and nothing is migrated between accounts.

"Before" is the committed code on `main` (`8ec563d`). "Now" is the implementation in the working
tree of `feat/azure-account-switching` (not committed yet). The procedure is in
[`azure-account-switching.md`](azure-account-switching.md).

## How the values flow

```text
config/azure-account.json  (local, ignored by git; identifiers only)
        │  scripts/onboard_azure_account.sh --config … [--sync-only] --apply
        ├─► GitHub secrets    AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_SUBSCRIPTION_ID
        ├─► GitHub variables  TFSTATE_RESOURCE_GROUP, TFSTATE_STORAGE_ACCOUNT, TFSTATE_CONTAINER, TFSTATE_KEY
        └─► .artifacts/azure-accounts/<label>/backend.hcl   (your own local init)

GitHub Actions (main only):  OIDC login ─► scripts/resolve_backend_config.sh (ownership check)
                             ─► terraform init -reconfigure -backend-config=<verified file> ─► plan only
```

## Configuration and onboarding

| File | Before | Now | Why |
|---|---|---|---|
| `config/azure-account.example.json` (**new**) | — | Committed template with placeholders and no IDs | Shows the one file's structure |
| `config/azure-account.json` (**new, local only**) | — | The active account's label, tenant, subscription, client ID, app name, state backend and repository | The single source of truth; never committed |
| `.gitignore` | — | Ignores `config/azure-account*` except the template | Real IDs, renamed copies and backups stay out of git |
| `scripts/onboard_azure_account.sh` (**new**) | Manual portal and repository steps | Reads `--config` only. It validates every field, rejects unknown fields and placeholders, checks the values are consistent, and refuses a file git tracks or doesn't ignore. Without `--apply` it's a dry run. With `--apply` it bootstraps the state storage, identity and roles, runs the ownership check, then syncs the secrets (on stdin) and variables. `--sync-only` creates nothing in Azure. | One command per month |

## State backend and isolation

| File | Before | Now | Why |
|---|---|---|---|
| `terraform/environments/dev/backend.tf` | Hardcoded `aitdd-tfstate-rg` / `aitddtfstatesa001` / `tfstate` / `dev.tfstate` | `backend "azurerm" {}` (partial). In a fresh folder an init without the settings fails; an initialized folder keeps its last backend, so every init passes `-reconfigure`. | The location changes with each account |
| `scripts/resolve_backend_config.sh` (**new**) | — | Validates the 4 variables, and requires the key the storage account gives: `dev-<TFSTATE_STORAGE_ACCOUNT>.tfstate`, or `dev.tfstate` for `aitddtfstatesa001` (`backend_key_not_bound` otherwise, before any Azure call). Proves with a read-only `az storage account show --subscription <AZURE_SUBSCRIPTION_ID>` that the storage account belongs to the signed-in subscription, then writes a new runner-local backend file. | No run can read or lock another account's state. No two accounts share a `backend_key`, whatever machine or hand-edited variable set it. |
| `terraform/bootstrap/outputs.tf` | Printed `-migrate-state` | Prints `init -reconfigure`, and says never to use `-migrate-state` | Accounts never share or migrate state |
| `terraform/bootstrap/` (usage) | One local state | One local workspace per label, created by the script. `prevent_destroy` still protects the storage account and container. | An earlier account's bootstrap state is never touched |

## GitHub Actions and Terraform scripts

| File | Before | Now | Why |
|---|---|---|---|
| `.github/workflows/drift-detection.yml` | `init -input=false -lockfile=readonly` | New step "Verify Terraform State Storage" after the OIDC check. Init uses `-reconfigure -backend-config=<verified file>`, and the new step is in the run summary. | Plan-only, with the current account's state only |
| `.github/workflows/terraform-auth-test.yml` | Plan with the hardcoded backend | Same check step, and `BACKEND_CONFIG` for the plan script | Same |
| `scripts/generate_plan_json.sh`, `scripts/auth_test_plan.sh` | Plain `terraform init` | `init -reconfigure` **always**, plus `-backend-config=<file>` from `BACKEND_CONFIG` (a regular file, not a symlink). `TF_CLI_ARGS*` is still refused. | The location comes only from the verified file. An initialized folder never keeps an earlier account's backend; without the file, the partial backend fails. |

## Investigation and reports

| File | Before | Now | Why |
|---|---|---|---|
| `src/drift_engine/investigation.py` | An earlier run was an anchor if its `environment` matched | It must also have the same **non-empty** `backend_key` (`backend_mismatch` otherwise) | Every account is `dev`. Runs without a key can't be told apart, so they never count as the same account. |
| `src/drift_engine/investigation_public.py` | — | `backend_mismatch` added to the public rejection codes | The strict public model accepts it |
| Reports and dashboard | `run.backend_key` already recorded | Unchanged code. It now names the account's key (`dev.tfstate`, `dev-<storage account>.tfstate`), so the storage account name is public; IDs stay withheld. | Runs from different accounts can be told apart |

## Tests

| File | Covers |
|---|---|
| `tests/test_onboard_azure_account.py` (**new**, 124 tests) | Missing, malformed, wrongly typed, unknown (secret) and placeholder fields; invalid and inconsistent values; git tracking and ignore rules (including through a symlinked directory); dry run; apply order (GitHub last); secrets on stdin and never printed; `--sync-only` and its closing message; issue closing (never with `--sync-only`, never for the same key, stops if the `TFSTATE_KEY` read fails); a label or state key bound to one account; the storage-account key rule (the first account's `dev.tfstate`, new keys, mismatches); local `backend.hcl` |
| `tests/test_backend_config.py` (**new**) | The ownership check, partial backend, workflow step order, no `-migrate-state` and no `terraform apply` in CI; both plan scripts always pass `-reconfigure`, including a real-Terraform check that a previously initialized folder's backend is not reused; the storage-account key rule (`backend_key_not_bound`) |
| `tests/test_investigation.py` | Anchors from another account, or without a key, are rejected; the public model accepts `backend_mismatch` |
| `tests/test_auth_test_workflow.py`, `tests/test_generate_plan_json.py` | The new step, and `BACKEND_CONFIG` handling |

## Documentation

| File | Change |
|---|---|
| `docs/azure-account-switching.md` (**new**) | Runbook: the one file, the first-account sync, the monthly procedure, what the script refuses |
| `README.md`, `docs/architecture.md`, `docs/MASTER_PROJECT_GUIDE.md` | Partial backend, the variables and the config file |

## No change needed

`dev.tfvars`, `providers.tf`, `versions.tf`, `.terraform.lock.hcl`, `main.tf`, `src/drift_engine/inventory.py`,
`src/drift_engine/activity_logs.py` (both take the subscription from the plan's resource IDs), the issue
fingerprint in `scripts/github_automation.py` (the previous account's issues are closed at the switch
instead), the AI analysis workflow, and the dashboard.

## Known limitations

- **The state-key rule rests on storage account names being globally unique.** A later
  account that deliberately reuses a deleted account's storage account name would get the same
  key. The first account's `dev.tfstate` is tied to the name `aitddtfstatesa001` in the same way.
- **The real-Terraform regression tests run in CI, in the `tests.yml` full job.** That job
  installs Terraform 1.14.7 with the same SHA-pinned `hashicorp/setup-terraform` step the drift
  and auth workflows use, and sets `AITDD_REQUIRE_REAL_TERRAFORM=1`, so a missing binary fails
  them instead of skipping them. Locally they still skip without Terraform 1.14.7. The fast
  tier runs no integration tests, so it doesn't install Terraform.

## Each month

Edit `config/azure-account.json`, then run
`scripts/onboard_azure_account.sh --config config/azure-account.json --close-open-drift-issues --apply`.
No repository file changes.
