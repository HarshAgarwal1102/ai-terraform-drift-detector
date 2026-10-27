# Switching Azure accounts

The project runs against **one Azure account at a time** (for example a new Azure Free Account
each month) with the same `dev` environment and the same Resource Group-only configuration.
Each account has its own Terraform state, its own CI identity and its own role assignments.
Nothing is migrated between accounts.

## One file per account

Everything that identifies the active account lives in **one local file**,
`config/azure-account.json`. Git ignores it, so it is never committed. The committed template
is [`config/azure-account.example.json`](../config/azure-account.example.json):

```json
{
  "_comment": "Optional free text.",
  "label": "2026-11",
  "azure": {
    "tenant_id": "<tenant-id GUID>",
    "subscription_id": "<subscription-id GUID>",
    "client_id": null,
    "app_name": "aitdd-github-oidc"
  },
  "state_backend": {
    "resource_group": "aitdd-tfstate-rg",
    "storage_account": "aitddtf202611",
    "container": "tfstate",
    "key": "dev-aitddtf202611.tfstate",
    "location": "Central India"
  },
  "github": {
    "repository": "HarshAgarwal1102/ai-terraform-drift-detector"
  }
}
```

| Field | Value |
|---|---|
| `label` | 1-24 lowercase letters, digits or hyphens. Never reuse it for another account. |
| `azure.tenant_id`, `azure.subscription_id` | The new account's IDs |
| `azure.client_id` | `null` for a new account: the script creates (or reuses) the app named `azure.app_name` and **writes its client ID into this field**. Set it yourself only if the app already exists. |
| `state_backend.storage_account` | Globally unique, 3-24 lowercase letters and digits |
| `state_backend.key` | Always `dev-<storage_account>.tfstate`, for example `dev-aitddtf202611.tfstate`. Only the first account's `aitddtfstatesa001` keeps `dev.tfstate` (see below). |
| `github.repository` | This repository; it must match the checkout's `origin` |

The file holds **identifiers only**. A client secret, password, token or key never goes in it,
and the script refuses any field it doesn't know. OIDC needs no secret at all.

`scripts/onboard_azure_account.sh --config config/azure-account.json` is the only reader of the
file. It refuses the file if git tracks it or wouldn't ignore it. It validates every field,
and only then does anything:

| Where the value goes | Values | Visible to |
|---|---|---|
| GitHub repository **secrets** | `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_SUBSCRIPTION_ID`. Values go to `gh` on stdin and are never printed. | The workflows only |
| GitHub repository **variables** | `TFSTATE_RESOURCE_GROUP`, `TFSTATE_STORAGE_ACCOUNT`, `TFSTATE_CONTAINER`, `TFSTATE_KEY` | Anyone with repository access. None of them is an account ID. |
| Local only | `.artifacts/azure-accounts/<label>/backend.hcl` and `account.json` (ignored by git) | You |

The workflows never read the config file. They read the secrets and variables.
`terraform/environments/dev/backend.tf` is a **partial** backend: it holds no location. Both
Azure workflows first run `scripts/resolve_backend_config.sh`. That script:

1. checks the four variables;
2. makes one read-only `az storage account show --subscription <AZURE_SUBSCRIPTION_ID>` call to
   prove that the storage account belongs to the signed-in subscription;
3. only then writes the backend file that `terraform init -reconfigure -backend-config=<file>`
   uses.

The onboarding script runs the same check before it changes GitHub. CI stays plan-only.

## Before merging this change: the first account

The workflows refuse to run without the variables (`backend_configuration_missing`). Set them
once for the account in use today:

1. Copy the template:

   ```bash
   cp config/azure-account.example.json config/azure-account.json
   ```

2. Fill in today's account. Use any unused label, its tenant, subscription and client IDs, and
   the existing state storage: `aitdd-tfstate-rg`, `aitddtfstatesa001`, `tfstate`, `dev.tfstate`.

3. Preview the sync, then run it. `--sync-only` creates nothing in Azure and changes no
   role, state or issue. It checks that the app and the state storage exist (read-only), then
   sets the secrets and variables. It needs the GitHub CLI, signed in (`gh auth login`).

   ```bash
   scripts/onboard_azure_account.sh --config config/azure-account.json --sync-only
   ```

   ```bash
   scripts/onboard_azure_account.sh --config config/azure-account.json --sync-only --apply
   ```

`dev.tfstate` is accepted only for `aitddtfstatesa001`, and only with `--sync-only`.

### The state-key rule

The state key names the storage account:

- `aitddtfstatesa001` (the first account) → `dev.tfstate`;
- any other storage account `<name>` → `dev-<name>.tfstate`.

Storage account names are globally unique, and every account has its own storage account, so
two accounts never share a key. The investigation tells accounts apart by that key
(`run.backend_key`), so it never takes one account's runs as another's baseline.

The rule is checked in two places:

- **CI**, on every run, by `scripts/resolve_backend_config.sh` (`failure_code=backend_key_not_bound`).
  This also catches a `TFSTATE_KEY` edited by hand in GitHub, or set from another machine.
- **The onboarding script**, before it does anything.

The key, and so the storage account name, appears in CI logs and in the public drift report.
Account IDs never do.
`--close-open-drift-issues` is refused with `--sync-only`: the account stays the same, so its
open issues are still current.

Setting the variables before the merge is safe, because the current workflows on `main` don't read
them. The three secrets are overwritten with the same account's IDs.

## Monthly procedure

You need `az`, `gh` (signed in), `terraform` and `jq`. As the new account's creator, you also
need Owner on the subscription and an Entra role that can register apps.

1. Create the new Azure account, then sign in to it and check GitHub:

   ```bash
   az login --tenant <tenant-id>
   ```

   ```bash
   az account set --subscription <subscription-id>
   ```

   ```bash
   gh auth status
   ```

2. **Edit the one file.** In `config/azure-account.json`, change these fields:
   - `label`
   - `azure.tenant_id`
   - `azure.subscription_id`
   - `azure.client_id` (set to `null`)
   - `state_backend.storage_account`
   - `state_backend.key`

   An example is [below](#example-the-monthly-edit). You don't edit any other file.

3. Preview. This is a dry run: it validates the file and calls neither Azure nor GitHub.

   ```bash
   scripts/onboard_azure_account.sh --config config/azure-account.json
   ```

4. Apply. `--close-open-drift-issues` closes **every open `drift-detected` issue** of the
   previous account as "not planned", with a comment. Without it, the new account's first
   in-sync run would close them as "resolved". The script reads `TFSTATE_KEY` from GitHub
   before it changes anything:
   - if the variable already holds this account's key (a re-run), it closes nothing;
   - if the read fails (an API, permission or network error), it stops with nothing changed.
     Only a successful listing without the variable counts as "no key yet".

   ```bash
   scripts/onboard_azure_account.sh --config config/azure-account.json --close-open-drift-issues --apply
   ```

   In order, it:
   - creates the state storage, the identity, the federated credential and the two roles;
   - records the new client ID in `azure.client_id`;
   - runs the ownership check;
   - only then sets the three secrets and four variables;
   - writes `.artifacts/azure-accounts/<label>/backend.hcl`.

5. Wait a few minutes for the federated credential and roles to propagate. Then run
   **Terraform Auth Test** from the Actions tab. The state is still empty, so the plan
   reports the Resource Group to create (exit code 2).

6. Deploy the `dev` configuration **yourself** (never in CI):

   ```bash
   terraform -chdir=terraform/environments/dev init -reconfigure -backend-config=../../../.artifacts/azure-accounts/2026-11/backend.hcl
   ```

   Always pass this account's file with `-reconfigure`. Your `terraform/environments/dev/.terraform`
   folder keeps the backend of its last init, which is the previous account's, and a plain
   `terraform init` would silently reuse it. If Terraform reports that the backend
   configuration changed, use `-reconfigure`, **never** `-migrate-state`.

   ```bash
   terraform -chdir=terraform/environments/dev plan -var-file=dev.tfvars -out=dev.tfplan
   ```

   Review the plan, then apply that saved plan. The local `backend.hcl` has no
   `use_azuread_auth`, so Terraform uses your `az login`, as a plain local init always did.

7. Run **Phase 5 - Drift Detection** (`dev`). The run should report the environment in sync,
   and its drift report carries `run.backend_key = "dev-aitddtf202611.tfstate"`.

8. Same tenant only: remove the CI identity's roles from the previous subscription. In a new
   tenant the previous identity can't reach this account anyway.

To keep the previous month's file, copy it first, for example to
`config/azure-account.2026-10.json`. Git ignores every `config/azure-account*.json` except
the template.

### Example: the monthly edit

```diff
-  "label": "2026-10",
+  "label": "2026-11",
   "azure": {
-    "tenant_id": "<October tenant ID>",
-    "subscription_id": "<October subscription ID>",
-    "client_id": "<October client ID>",
+    "tenant_id": "<November tenant ID>",
+    "subscription_id": "<November subscription ID>",
+    "client_id": null,
     "app_name": "aitdd-github-oidc"
   },
   "state_backend": {
     "resource_group": "aitdd-tfstate-rg",
-    "storage_account": "aitddtf202610",
+    "storage_account": "aitddtf202611",
     "container": "tfstate",
-    "key": "dev-aitddtf202610.tfstate",
+    "key": "dev-aitddtf202611.tfstate",
     "location": "Central India"
   },
```

## What the script refuses

It exits with code 2, before any call to Azure or GitHub, when:

| Problem | Example message |
|---|---|
| No `--config`, a missing file, or a symbolic link | `--config is required`, `not found or not readable` |
| Not exactly one JSON object | `is not valid JSON`, `the file must hold exactly one JSON object` |
| A missing section or field, or the wrong type | `missing field state_backend.key`, `field label must be a string` |
| An unknown field, for example a secret | `unknown field azure.client_secret (the file holds identifiers only, never a secret)` |
| A placeholder left in | `azure.tenant_id is still a placeholder` |
| A value with the wrong shape | `state_backend.storage_account must be 3-24 lowercase letters and digits` |
| Values that contradict each other | `state_backend.key must be dev-aitddtf202611.tfstate (the key names state_backend.storage_account)`, `azure.tenant_id and azure.subscription_id are the same value`, `github.repository … is not this checkout's origin` |
| A file git tracks, or wouldn't ignore | `is tracked by git`, `is not ignored by git` |
| A label already used by another account | `label '2026-11' already belongs to another Azure account` |
| A state key already used by another account under another label (from this machine's `.artifacts/azure-accounts/*/account.json`) | `state key dev.tfstate already belongs to another Azure account (label '2026-10')` |
| The old command-line options | `--tenant is not an option: account settings come from the --config file only` |
| Closing issues while keeping the account | `--close-open-drift-issues … is not allowed with --sync-only` |

## What keeps the accounts apart

| Risk | Protection |
|---|---|
| A run reads or locks the previous account's state | No location in `backend.tf`, the ownership check on every run, and `init -reconfigure` (both plan scripts always add it, so an initialized folder never keeps an earlier account's backend). **Never** `-migrate-state`. |
| The bootstrap re-uses the previous account's local state | Each account gets its own bootstrap workspace (`terraform/bootstrap/terraform.tfstate.d/<label>/`, ignored by git). A label is bound to its tenant and subscription in `.artifacts/azure-accounts/<label>/account.json` and is never reused for another account. |
| The investigation uses the previous account's runs as a baseline | An anchor must have the same `backend_key` as the run (`backend_mismatch` otherwise). The key names the account's storage account, a rule CI enforces on every run, so each account's key is different. |
| Account IDs become public | They stay in the ignored config file and in GitHub secrets. Public reports withhold them, as before. The `backend_key` that tells accounts apart carries the storage account name, never an ID. |
| Open GitHub issues carry over | `--close-open-drift-issues` at the switch. Fingerprints don't include the account. |
| Run History mixes accounts | Earlier runs stay visible. A run's account is its report's `run.backend_key`; the dashboard doesn't show it as a column. |

## Permissions

| Activity | Role | Scope | When |
|---|---|---|---|
| Create the state storage (bootstrap) | Owner or Contributor | New subscription | Onboarding (you) |
| Create the app, its service principal and its federated credential | Application Administrator, Cloud Application Administrator or app Owner | New tenant | Onboarding (you) |
| Create the CI role assignments | Owner, User Access Administrator, or Role Based Access Control Administrator | Subscription and state container | Onboarding (you) |
| Ownership check, plan refresh, unmanaged inventory, Activity Log investigation | **Reader** | Subscription | Every CI run |
| Read and lock the state | **Storage Blob Data Contributor** | That account's state container only | Every CI run |
| Deploy or change `dev` | Owner or Contributor (yours) | `aitdd-dev-main-rg` | Manually, never in CI |

None of this has been verified against a live Azure account by the automated tests. They use
fake `az`, `gh` and `terraform` binaries.

## Failure codes of the state storage check

| Code | Meaning |
|---|---|
| `backend_configuration_missing` | A `TFSTATE_*` variable or the subscription secret is not set |
| `backend_configuration_invalid` | A value has the wrong shape (the key must be `dev.tfstate` or `dev-<3-24 lowercase letters and digits>.tfstate`) |
| `backend_key_not_bound` | `TFSTATE_KEY` isn't the key the storage account gives (`dev-<TFSTATE_STORAGE_ACCOUNT>.tfstate`, or `dev.tfstate` for `aitddtfstatesa001`) |
| `state_storage_unavailable` | The storage account isn't in the signed-in subscription, or the identity can't read it |
| `state_storage_not_in_subscription` | Azure returned an account outside the configured subscription and resource group |
| `backend_config_write_failed` | The runner-local backend file already existed or couldn't be written |

## When an account expires

Its storage, state and identity become unreachable. That's expected, and nothing in the
workflows depends on them. Its reports stay in Run History and in GitHub's artifacts until the
artifacts expire (30 days). Onboard the next account by editing the config file.
