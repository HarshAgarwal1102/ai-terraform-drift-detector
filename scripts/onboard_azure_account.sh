#!/usr/bin/env bash
# -----------------------------------------------
# scripts/onboard_azure_account.sh
# -----------------------------------------------
# Switch the project to a new Azure account (docs/azure-account-switching.md). Run it on
# YOUR machine, signed in to the new account with `az login --tenant <tenant>` and to
# GitHub with `gh auth login`. It never runs in GitHub Actions.
#
# ONE FILE PER ACCOUNT: every account setting comes from --config, a local JSON file
# (config/azure-account.json, ignored by git; template: config/azure-account.example.json).
# It holds identifiers only, never a secret, and the script refuses a config file that
# git tracks or would commit. The workflows never read it: this script copies it to
# GitHub, the IDs as secrets and the state location as variables.
#
# DRY RUN BY DEFAULT: without --apply it only validates the config file and prints the
# plan; it calls neither Azure nor GitHub. With --apply, in this order:
#   1. checks that `az` is signed in to exactly azure.tenant_id / azure.subscription_id;
#   2. bootstrap state storage: terraform/bootstrap in a NEW local workspace named after
#      the label (the earlier accounts' bootstrap state is never touched), creating the
#      resource group, storage account and container of state_backend;
#   3. identity: the Entra app azure.client_id or, when that is null, the app named
#      azure.app_name (created if missing; its client ID is then recorded in the config
#      file), its service principal and one federated credential for this repository's
#      `main` branch (GitHub's immutable subject, computed from the repository's numeric IDs);
#   4. least-privilege roles for that service principal: Reader on the subscription and
#      Storage Blob Data Contributor on the state container only;
#   5. the state-storage ownership check CI runs (scripts/resolve_backend_config.sh);
#   6. GitHub, only after 1-5 succeeded: the secrets AZURE_TENANT_ID / AZURE_CLIENT_ID /
#      AZURE_SUBSCRIPTION_ID (values passed on stdin, never as arguments or output) and the
#      variables TFSTATE_RESOURCE_GROUP / TFSTATE_STORAGE_ACCOUNT / TFSTATE_CONTAINER /
#      TFSTATE_KEY;
#   7. with --close-open-drift-issues only (never with --sync-only): closes the open
#      `drift-detected` issues of the previous account as "not planned", with a comment;
#      skipped when TFSTATE_KEY already named this account (a re-run). That variable is
#      read before any change, and a failed read stops the run;
#   8. writes <state dir>/<label>/backend.hcl for your own local
#      `terraform init -reconfigure -backend-config=<that file>` (your az login).
# --sync-only skips 2-4 (nothing is created in Azure; the app must exist): for an account
# whose state storage and identity already exist, such as the first one.
# It never applies the dev environment, never runs -migrate-state and never prints a
# credential. Tenant, subscription and client IDs are shown masked (last 4 characters).
#
# Usage:
#   scripts/onboard_azure_account.sh --config config/azure-account.json \
#       [--sync-only] [--close-open-drift-issues] [--oidc-subject SUBJECT] [--apply]
#
# Config file (all fields required; see config/azure-account.example.json):
#   label                          1-24 lowercase letters, digits or hyphens (e.g. 2026-11)
#   azure.tenant_id                tenant ID (GUID)
#   azure.subscription_id          subscription ID (GUID)
#   azure.client_id                the CI app's client ID (GUID), or null to create or
#                                  reuse the app named azure.app_name (not with --sync-only)
#   azure.app_name                 Entra app display name
#   state_backend.resource_group   resource group of the state storage
#   state_backend.storage_account  3-24 lowercase letters and digits, globally unique
#   state_backend.container        blob container
#   state_backend.key              dev-<storage_account>.tfstate; dev.tfstate only for
#                                  aitddtfstatesa001, the first account (--sync-only)
#   state_backend.location         Azure region of the state storage
#   github.repository              OWNER/REPO; must be this checkout's origin
#   _comment                       optional, ignored
#
# Environment: ONBOARD_STATE_DIR (default .artifacts/azure-accounts, ignored by git) holds
# one folder per label: account.json binds the label, and its state key, to its tenant and
# subscription (neither is ever reused for another account) and backend.hcl.
#
# Exit status: 0 done (or dry run), 1 a step failed (it names the step; GitHub is left
# unchanged if the failure came before the github step), 2 usage, config or precondition error.
# -----------------------------------------------

# An inherited SHELLOPTS=xtrace would print expanded values; turn it off first.
set +x
set -uo pipefail
umask 077

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(CDPATH='' cd -- "${SCRIPT_DIR}/.." && pwd -P)"
BOOTSTRAP_DIR="${ROOT_DIR}/terraform/bootstrap"
STATE_ROOT="${ONBOARD_STATE_DIR:-${ROOT_DIR}/.artifacts/azure-accounts}"
ISSUER="https://token.actions.githubusercontent.com"
AUDIENCE="api://AzureADTokenExchange"
GUID_RE='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
LOCATION_RE='^[A-Za-z0-9][A-Za-z0-9 ]{1,39}$'  # a variable: a literal space cannot stand in a [[ =~ ]] pattern

CONFIG="" SUBJECT="" APPLY=0 SYNC_ONLY=0 CLOSE_ISSUES=0 STEP="preflight"

usage() { sed -n '/^# Usage:/,/^#$/p' "${BASH_SOURCE[0]}" | sed -e 's/^# \{0,1\}//' -e '$d'; }
die_usage() { echo "onboard: $1" >&2; exit 2; }
bad_config() { die_usage "config ${CONFIG}: $1"; }
die() { echo "onboard: FAILED at step '${STEP}': $1" >&2; exit 1; }
mask() { printf '…%s' "${1: -4}"; }
lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1; shift; continue ;;
    --sync-only) SYNC_ONLY=1; shift; continue ;;
    --close-open-drift-issues) CLOSE_ISSUES=1; shift; continue ;;
    -h|--help) usage; exit 0 ;;
    --config|--oidc-subject) [ $# -ge 2 ] || die_usage "$1 needs a value" ;;
    --label|--tenant|--subscription|--client-id|--storage-account|--location|--resource-group|--container|--app-name|--repository)
      die_usage "$1 is not an option: account settings come from the --config file only" ;;
    *) die_usage "unknown option: $1 (see --help)" ;;
  esac
  case "$1" in
    --config) CONFIG="$2" ;;
    --oidc-subject) SUBJECT="$2" ;;
  esac
  shift 2
done

# -----------------------------------------------
# The config file: where it lives, its structure, then every value
# -----------------------------------------------
[ "${GITHUB_ACTIONS:-}" != "true" ] || die_usage "runs on your machine only, never in GitHub Actions"
[ -n "${CONFIG}" ] \
  || die_usage "--config is required (copy config/azure-account.example.json to config/azure-account.json)"
command -v jq >/dev/null 2>&1 || die_usage "jq is required but was not found"
[ ! -L "${CONFIG}" ] || bad_config "must be a regular file, not a symbolic link"
[ -f "${CONFIG}" ] && [ -r "${CONFIG}" ] || bad_config "not found or not readable"
# Physical paths on both sides: a symlinked directory cannot hide a file inside the repository.
CONFIG_ABS="$(CDPATH='' cd -- "$(dirname -- "${CONFIG}")" && pwd -P)/$(basename -- "${CONFIG}")"

# Real IDs never reach git: a config file inside this repository must be untracked and ignored.
case "${CONFIG_ABS}" in
  "${ROOT_DIR}"/*)
    rel="${CONFIG_ABS#"${ROOT_DIR}"/}"
    if command -v git >/dev/null 2>&1 && git -C "${ROOT_DIR}" rev-parse --git-dir >/dev/null 2>&1; then
      if git -C "${ROOT_DIR}" ls-files --error-unmatch -- "${rel}" >/dev/null 2>&1; then
        bad_config "is tracked by git; account IDs must never be committed (use config/azure-account.json)"
      fi
      git -C "${ROOT_DIR}" check-ignore -q -- "${rel}" \
        || bad_config "is not ignored by git; use config/azure-account.json or config/azure-account.<label>.json"
    fi ;;
esac

# One JSON object, the known sections and fields only (a typo or a secret is refused), and
# every field present with the right type. All problems are reported together.
SCHEMA='
def unknown($o; $allowed; $prefix):
  [$o | keys[] | select(. as $k | $allowed | any(. == $k) | not)
   | "unknown field \($prefix)\(.) (the file holds identifiers only, never a secret)"];
if length != 1 or (.[0] | type) != "object" then ["the file must hold exactly one JSON object"]
else .[0]
  | [("azure", "state_backend", "github") as $s | select((.[$s] | type) != "object") | "missing section \($s)"] as $missing
  | if $missing != [] then $missing
    else unknown(.; ["_comment", "label", "azure", "state_backend", "github"]; "")
      + unknown(.azure; ["tenant_id", "subscription_id", "client_id", "app_name"]; "azure.")
      + unknown(.state_backend; ["resource_group", "storage_account", "container", "key", "location"]; "state_backend.")
      + unknown(.github; ["repository"]; "github.")
      + [(["label"], ["azure", "tenant_id"], ["azure", "subscription_id"], ["azure", "app_name"],
          ["state_backend", "resource_group"], ["state_backend", "storage_account"], ["state_backend", "container"],
          ["state_backend", "key"], ["state_backend", "location"], ["github", "repository"]) as $p
         | select((getpath($p) | type) != "string")
         | if getpath($p) == null then "missing field \($p | join("."))" else "field \($p | join(".")) must be a string" end]
      + (if (.azure | has("client_id")) | not then ["missing field azure.client_id (a GUID, or null)"]
         elif ((.azure.client_id | type) as $t | $t != "string" and $t != "null")
         then ["field azure.client_id must be a GUID string or null"] else [] end)
      + (if has("_comment") and (._comment | type) != "string" then ["field _comment must be a string"] else [] end)
    end
end
| join("; ")'
problems="$(jq -r -s "${SCHEMA}" "${CONFIG}" 2>/dev/null)" || bad_config "is not valid JSON"
[ -z "${problems}" ] || bad_config "${problems}"

cfg() { jq -r "$1 // \"\"" "${CONFIG}"; }
LABEL="$(cfg .label)"
TENANT="$(lower "$(cfg .azure.tenant_id)")"
SUBSCRIPTION="$(lower "$(cfg .azure.subscription_id)")"
CLIENT_ID="$(lower "$(cfg .azure.client_id)")"
APP_NAME="$(cfg .azure.app_name)"
RESOURCE_GROUP="$(cfg .state_backend.resource_group)"
STORAGE_ACCOUNT="$(cfg .state_backend.storage_account)"
CONTAINER="$(cfg .state_backend.container)"
KEY="$(cfg .state_backend.key)"
LOCATION="$(cfg .state_backend.location)"
REPOSITORY="$(cfg .github.repository)"

for pair in "label=${LABEL}" "azure.tenant_id=${TENANT}" "azure.subscription_id=${SUBSCRIPTION}" \
            "azure.client_id=${CLIENT_ID}" "azure.app_name=${APP_NAME}" \
            "state_backend.resource_group=${RESOURCE_GROUP}" "state_backend.storage_account=${STORAGE_ACCOUNT}" \
            "state_backend.container=${CONTAINER}" "state_backend.key=${KEY}" \
            "state_backend.location=${LOCATION}" "github.repository=${REPOSITORY}"; do
  case "${pair#*=}" in "<"*) bad_config "${pair%%=*} is still a placeholder; fill in the real value" ;; esac
done

# Shapes: the same ones resolve_backend_config.sh accepts in CI.
[[ "${LABEL}" =~ ^[a-z0-9][a-z0-9-]{0,23}$ ]] \
  || bad_config "label must be 1-24 lowercase letters, digits or hyphens, starting with a letter or digit"
[[ "${TENANT}" =~ ${GUID_RE} ]] || bad_config "azure.tenant_id must be a tenant ID (GUID)"
[[ "${SUBSCRIPTION}" =~ ${GUID_RE} ]] || bad_config "azure.subscription_id must be a subscription ID (GUID)"
[ -z "${CLIENT_ID}" ] || [[ "${CLIENT_ID}" =~ ${GUID_RE} ]] \
  || bad_config "azure.client_id must be a client ID (GUID) or null"
[[ "${APP_NAME}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$ ]] || bad_config "azure.app_name is not a valid name"
[[ "${RESOURCE_GROUP}" =~ ^[A-Za-z0-9_().-]{1,90}$ && "${RESOURCE_GROUP}" != *. ]] \
  || bad_config "state_backend.resource_group is not a valid resource group name"
[[ "${STORAGE_ACCOUNT}" =~ ^[a-z0-9]{3,24}$ ]] \
  || bad_config "state_backend.storage_account must be 3-24 lowercase letters and digits (globally unique)"
[[ "${CONTAINER}" =~ ^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$ && "${CONTAINER}" != *--* ]] \
  || bad_config "state_backend.container is not a valid container name"
[[ "${LOCATION}" =~ ${LOCATION_RE} ]] || bad_config "state_backend.location is not a valid Azure region name"
[[ "${REPOSITORY}" =~ ^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$ ]] || bad_config "github.repository must be OWNER/REPO"
if [ -n "${SUBJECT}" ]; then
  [[ "${SUBJECT}" =~ ^repo:[A-Za-z0-9._@/-]+:ref:refs/heads/main$ ]] \
    || die_usage "--oidc-subject must be the main-branch subject (repo:...:ref:refs/heads/main)"
fi

# Consistency between the values. The key names the storage account, the rule CI enforces
# on every run (resolve_backend_config.sh): storage account names are globally unique, so two
# accounts never share a key, and the investigation never takes one's runs as the other's
# baseline. Only the first account's storage keeps dev.tfstate.
if [ "${STORAGE_ACCOUNT}" = "aitddtfstatesa001" ]; then expected_key="dev.tfstate"; else expected_key="dev-${STORAGE_ACCOUNT}.tfstate"; fi
[ "${KEY}" = "${expected_key}" ] \
  || bad_config "state_backend.key must be ${expected_key} (the key names state_backend.storage_account)"
# The first account already exists: it is only ever synced, never onboarded again.
[ "${KEY}" != "dev.tfstate" ] || [ "${SYNC_ONLY}" -eq 1 ] \
  || bad_config "state_backend.storage_account aitddtfstatesa001 (dev.tfstate) is the first account's; use --sync-only, or a new storage account for a new account"
[ "${TENANT}" != "${SUBSCRIPTION}" ] || bad_config "azure.tenant_id and azure.subscription_id are the same value"
if [ -n "${CLIENT_ID}" ]; then
  [ "${CLIENT_ID}" != "${TENANT}" ] && [ "${CLIENT_ID}" != "${SUBSCRIPTION}" ] \
    || bad_config "azure.client_id must differ from the tenant and subscription IDs"
elif [ "${SYNC_ONLY}" -eq 1 ]; then
  bad_config "azure.client_id is required with --sync-only (the app must already exist)"
fi
# --sync-only keeps (or re-syncs) an account, so its open issues are still current.
[ "${SYNC_ONLY}" -eq 0 ] || [ "${CLOSE_ISSUES}" -eq 0 ] \
  || die_usage "--close-open-drift-issues retires the previous account's issues; it is not allowed with --sync-only"
origin="$(git -C "${ROOT_DIR}" remote get-url origin 2>/dev/null \
  | sed -E -e 's#^(https://github\.com/|git@github\.com:|ssh://git@github\.com/)##' -e 's#\.git$##')" || origin=""
if [[ "${origin}" =~ ^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$ ]] && [ "$(lower "${origin}")" != "$(lower "${REPOSITORY}")" ]; then
  bad_config "github.repository ${REPOSITORY} is not this checkout's origin (${origin})"
fi

ACCOUNT_DIR="${STATE_ROOT}/${LABEL}"
SUB_SCOPE="/subscriptions/${SUBSCRIPTION}"
CONTAINER_SCOPE="${SUB_SCOPE}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Storage/storageAccounts/${STORAGE_ACCOUNT}/blobServices/default/containers/${CONTAINER}"

# Local bindings (<state dir>/<label>/account.json, one per account onboarded on this machine):
# a label belongs to one account for good, and so does a state key. Two accounts sharing a key
# would share run.backend_key, so the investigation could take one's runs as the other's baseline.
MARKER="${ACCOUNT_DIR}/account.json"
if [ -e "${MARKER}" ]; then
  bound="$(jq -r '"\(.tenant) \(.subscription)"' "${MARKER}" 2>/dev/null)" || die_usage "unreadable ${MARKER}"
  [ "${bound}" = "${TENANT} ${SUBSCRIPTION}" ] \
    || die_usage "label '${LABEL}' already belongs to another Azure account; choose a new label"
fi
for other in "${STATE_ROOT}"/*/account.json; do
  [ -e "${other}" ] && [ "${other}" != "${MARKER}" ] || continue
  binding="$(jq -r '[.label, .key, .tenant, .subscription] | map(. // "") | @tsv' "${other}" 2>/dev/null)" \
    || die_usage "unreadable ${other}"
  IFS=$'\t' read -r other_label other_key other_tenant other_subscription <<<"${binding}"
  if [ "${other_key}" = "${KEY}" ] && [ "${other_tenant} ${other_subscription}" != "${TENANT} ${SUBSCRIPTION}" ]; then
    die_usage "state key ${KEY} already belongs to another Azure account (label '${other_label}'); each storage account has its own key"
  fi
done

# -----------------------------------------------
# The plan (printed in both modes)
# -----------------------------------------------
if [ "${APPLY}" -eq 1 ]; then
  echo "Switching to Azure account '${LABEL}' from ${CONFIG} (applying)."
else
  echo "Switching to Azure account '${LABEL}' from ${CONFIG} (DRY RUN: nothing is changed; add --apply to run these steps)."
fi
if [ -n "${CLIENT_ID}" ]; then
  app_desc="app $(mask "${CLIENT_ID}") (azure.client_id)"
else
  app_desc="app '${APP_NAME}' (reused if it exists in this tenant; its client ID is recorded in ${CONFIG})"
fi
echo "  1. check az is signed in to tenant $(mask "${TENANT}") and subscription $(mask "${SUBSCRIPTION}")"
if [ "${SYNC_ONLY}" -eq 1 ]; then
  cat <<EOF
  2. state storage bootstrap: skipped (--sync-only; storage account ${STORAGE_ACCOUNT} must exist)
  3. identity: check that ${app_desc} exists; nothing is created (--sync-only)
  4. roles: unchanged (--sync-only)
EOF
else
  cat <<EOF
  2. bootstrap state storage (terraform/bootstrap, local workspace '${LABEL}'):
     resource group ${RESOURCE_GROUP}, storage account ${STORAGE_ACCOUNT}, container ${CONTAINER}, ${LOCATION}
  3. Entra ${app_desc}, its service principal,
     federated credential for ${REPOSITORY} main (${SUBJECT:-immutable subject from the repository IDs})
  4. roles for that service principal: Reader on the subscription;
     Storage Blob Data Contributor on container ${CONTAINER} only
EOF
fi
cat <<EOF
  5. state storage ownership check (scripts/resolve_backend_config.sh, as in CI)
  6. GitHub ${REPOSITORY}: secrets AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_SUBSCRIPTION_ID (values on stdin, never shown);
     variables TFSTATE_RESOURCE_GROUP=${RESOURCE_GROUP} TFSTATE_STORAGE_ACCOUNT=${STORAGE_ACCOUNT}
     TFSTATE_CONTAINER=${CONTAINER} TFSTATE_KEY=${KEY}
  7. close open drift-detected issues of the previous account: $(if [ "${CLOSE_ISSUES}" -eq 1 ]; then echo "yes (not if TFSTATE_KEY is already ${KEY})"; elif [ "${SYNC_ONLY}" -eq 1 ]; then echo "no (never with --sync-only)"; else echo "no (add --close-open-drift-issues)"; fi)
  8. local backend file: ${ACCOUNT_DIR}/backend.hcl
EOF
[ "${APPLY}" -eq 1 ] || exit 0

# -----------------------------------------------
# Apply
# -----------------------------------------------
tools="az gh"
[ "${SYNC_ONLY}" -eq 1 ] || tools="az gh terraform"
for tool in ${tools}; do
  command -v "${tool}" >/dev/null 2>&1 || die_usage "${tool} is required but was not found"
done

STEP="azure_context"
current_sub="$(az account show --only-show-errors --query id --output tsv 2>/dev/null)" \
  || die "az is not signed in (az login --tenant <tenant-id>)"
current_tenant="$(az account show --only-show-errors --query tenantId --output tsv 2>/dev/null)" \
  || die "az is not signed in (az login --tenant <tenant-id>)"
if [ "$(lower "${current_sub}")" != "${SUBSCRIPTION}" ] || [ "$(lower "${current_tenant}")" != "${TENANT}" ]; then
  die "az is signed in to another tenant or subscription (az login --tenant <tenant-id>; az account set --subscription <subscription-id>)"
fi
STEP="github_preflight"
gh auth status >/dev/null 2>&1 || die "gh is not signed in (gh auth login)"
# With --close-open-drift-issues: the key GitHub points at now, read before anything changes.
# Unchanged means the same account (a re-run), whose open issues must stay open. Only a
# successful listing without TFSTATE_KEY means "no key yet"; any API or network failure stops
# here, never read as an absent key.
previous_key=""
if [ "${CLOSE_ISSUES}" -eq 1 ]; then
  previous_key="$(gh api --paginate "repos/${REPOSITORY}/actions/variables" \
    --jq '.variables[] | select(.name == "TFSTATE_KEY") | .value' 2>/dev/null)" \
    || die "could not read the repository variables (GitHub API or network error); nothing was changed"
fi
if [ "${SYNC_ONLY}" -eq 0 ] && [ -z "${SUBJECT}" ]; then
  ids="$(gh api "repos/${REPOSITORY}" --jq '"\(.owner.login)@\(.owner.id)/\(.name)@\(.id)"' 2>/dev/null)" \
    || die "could not read the repository IDs of ${REPOSITORY}"
  [[ "${ids}" =~ ^[A-Za-z0-9-]+@[0-9]+/[A-Za-z0-9._-]+@[0-9]+$ ]] || die "unexpected repository IDs"
  SUBJECT="repo:${ids}:ref:refs/heads/main"
fi
mkdir -p "${ACCOUNT_DIR}" || die "cannot create ${ACCOUNT_DIR}"
if [ ! -e "${MARKER}" ]; then
  jq -n --arg label "${LABEL}" --arg tenant "${TENANT}" --arg subscription "${SUBSCRIPTION}" \
    --arg storage_account "${STORAGE_ACCOUNT}" --arg key "${KEY}" \
    '{label: $label, tenant: $tenant, subscription: $subscription, storage_account: $storage_account, key: $key}' \
    > "${MARKER}" || die "cannot write ${MARKER}"
fi

if [ "${SYNC_ONLY}" -eq 0 ]; then
  STEP="bootstrap"
  export ARM_SUBSCRIPTION_ID="${SUBSCRIPTION}" ARM_TENANT_ID="${TENANT}"
  terraform -chdir="${BOOTSTRAP_DIR}" init -input=false -no-color >/dev/null || die "terraform init (bootstrap) failed"
  terraform -chdir="${BOOTSTRAP_DIR}" workspace select -or-create=true "${LABEL}" >/dev/null \
    || die "could not select the bootstrap workspace '${LABEL}'"
  terraform -chdir="${BOOTSTRAP_DIR}" apply -input=false -auto-approve -no-color \
    -var "resource_group_name=${RESOURCE_GROUP}" -var "storage_account_name=${STORAGE_ACCOUNT}" \
    -var "container_name=${CONTAINER}" -var "location=${LOCATION}" \
    || die "terraform apply (bootstrap) failed; the storage account name may be taken (state_backend.storage_account)"
fi

STEP="identity"
if [ -n "${CLIENT_ID}" ]; then
  shown="$(az ad app show --only-show-errors --id "${CLIENT_ID}" --query appId --output tsv 2>/dev/null)" \
    || die "azure.client_id is not an app registration in this tenant"
  [ "$(lower "${shown}")" = "${CLIENT_ID}" ] || die "azure.client_id is not an app registration in this tenant"
  client_id="${CLIENT_ID}"
else
  apps="$(az ad app list --only-show-errors --display-name "${APP_NAME}" --query "[].appId" --output tsv)" \
    || die "could not list app registrations"
  case "$(printf '%s' "${apps}" | grep -c .)" in
    0) client_id="$(az ad app create --only-show-errors --display-name "${APP_NAME}" --sign-in-audience AzureADMyOrg \
         --query appId --output tsv)" || die "could not create the app registration" ;;
    1) client_id="${apps}" ;;
    *) die "more than one app registration is named '${APP_NAME}' (azure.app_name)" ;;
  esac
  client_id="$(lower "${client_id}")"
  [[ "${client_id}" =~ ${GUID_RE} ]] || die "unexpected application ID"
  # The config file stays the single source of truth: it now names the app.
  recorded="$(mktemp "${CONFIG_ABS}.XXXXXX")" || die "cannot record azure.client_id in ${CONFIG}"
  if jq --arg client "${client_id}" '.azure.client_id = $client' "${CONFIG}" > "${recorded}" \
      && mv -f "${recorded}" "${CONFIG_ABS}"; then
    echo "Recorded the app's client ID ($(mask "${client_id}")) as azure.client_id in ${CONFIG}."
  else
    rm -f "${recorded}"
    die "cannot record azure.client_id in ${CONFIG}"
  fi
fi
if [ "${SYNC_ONLY}" -eq 0 ]; then
  sp_id="$(az ad sp show --only-show-errors --id "${client_id}" --query id --output tsv 2>/dev/null)" \
    || sp_id="$(az ad sp create --only-show-errors --id "${client_id}" --query id --output tsv)" \
    || die "could not create the service principal"
  [[ "$(lower "${sp_id}")" =~ ${GUID_RE} ]] || die "unexpected service principal ID"
  fics="$(az ad app federated-credential list --only-show-errors --id "${client_id}" \
    --query "[?subject=='${SUBJECT}'] | length(@)" --output tsv)" || die "could not list federated credentials"
  if [ "${fics}" = "0" ]; then
    params="${ACCOUNT_DIR}/federated-credential.json"
    jq -n --arg subject "${SUBJECT}" --arg issuer "${ISSUER}" --arg audience "${AUDIENCE}" \
      '{name: "github-main", issuer: $issuer, subject: $subject, audiences: [$audience],
        description: "GitHub Actions, main branch (drift detection, plan only)"}' > "${params}" \
      || die "cannot write the federated credential parameters"
    az ad app federated-credential create --only-show-errors --id "${client_id}" --parameters "@${params}" --output none \
      || die "could not create the federated credential"
  fi

  STEP="roles"
  assign() {  # role, scope: created only when missing
    local count
    count="$(az role assignment list --only-show-errors --assignee "${sp_id}" --role "$1" --scope "$2" \
      --query "length(@)" --output tsv)" || return 1
    [ "${count}" != "0" ] || az role assignment create --only-show-errors --assignee-object-id "${sp_id}" \
      --assignee-principal-type ServicePrincipal --role "$1" --scope "$2" --output none
  }
  assign "Reader" "${SUB_SCOPE}" || die "could not assign Reader on the subscription"
  assign "Storage Blob Data Contributor" "${CONTAINER_SCOPE}" \
    || die "could not assign Storage Blob Data Contributor on the state container"
fi

# The check every CI run makes, before GitHub is pointed at this storage account.
STEP="state_storage"
PENDING="${ACCOUNT_DIR}/backend.hcl.pending"
rm -f "${PENDING}"
TFSTATE_RESOURCE_GROUP="${RESOURCE_GROUP}" TFSTATE_STORAGE_ACCOUNT="${STORAGE_ACCOUNT}" \
  TFSTATE_CONTAINER="${CONTAINER}" TFSTATE_KEY="${KEY}" EXPECTED_SUBSCRIPTION_ID="${SUBSCRIPTION}" \
  BACKEND_CONFIG="${PENDING}" bash "${SCRIPT_DIR}/resolve_backend_config.sh" \
  || die "storage account ${STORAGE_ACCOUNT} is not usable in subscription $(mask "${SUBSCRIPTION}") (failure_code above)"

STEP="github"
printf '%s' "${TENANT}" | gh secret set AZURE_TENANT_ID --repo "${REPOSITORY}" >/dev/null \
  || die "could not set AZURE_TENANT_ID"
printf '%s' "${client_id}" | gh secret set AZURE_CLIENT_ID --repo "${REPOSITORY}" >/dev/null \
  || die "could not set AZURE_CLIENT_ID"
printf '%s' "${SUBSCRIPTION}" | gh secret set AZURE_SUBSCRIPTION_ID --repo "${REPOSITORY}" >/dev/null \
  || die "could not set AZURE_SUBSCRIPTION_ID"
for pair in "TFSTATE_RESOURCE_GROUP=${RESOURCE_GROUP}" "TFSTATE_STORAGE_ACCOUNT=${STORAGE_ACCOUNT}" \
            "TFSTATE_CONTAINER=${CONTAINER}" "TFSTATE_KEY=${KEY}"; do
  gh variable set "${pair%%=*}" --repo "${REPOSITORY}" --body "${pair#*=}" >/dev/null \
    || die "could not set ${pair%%=*}"
done

if [ "${CLOSE_ISSUES}" -eq 1 ] && [ "${previous_key}" = "${KEY}" ]; then
  echo "Not closing drift-detected issues: TFSTATE_KEY was already ${KEY}, so they belong to this account."
elif [ "${CLOSE_ISSUES}" -eq 1 ]; then
  STEP="issues"
  numbers="$(gh issue list --repo "${REPOSITORY}" --label drift-detected --state open --limit 200 \
    --json number --jq '.[].number')" || die "could not list open drift-detected issues"
  for n in ${numbers}; do
    [[ "${n}" =~ ^[0-9]+$ ]] || die "unexpected issue number"
    gh issue close "${n}" --repo "${REPOSITORY}" --reason "not planned" \
      --comment "Closed by the switch to Azure account '${LABEL}': the account this drift was found in is retired." \
      >/dev/null || die "could not close issue #${n}"
  done
fi

STEP="local_backend"
# Your own local init: no use_azuread_auth (that is CI's identity, which has the data-plane
# role; an Owner has none), so Terraform authenticates with your az login as before.
rm -f "${PENDING}"
cat > "${ACCOUNT_DIR}/backend.hcl" <<EOF || die "cannot write ${ACCOUNT_DIR}/backend.hcl"
resource_group_name  = "${RESOURCE_GROUP}"
storage_account_name = "${STORAGE_ACCOUNT}"
container_name       = "${CONTAINER}"
key                  = "${KEY}"
EOF

if [ "${SYNC_ONLY}" -eq 1 ]; then
  cat <<EOF
Done: account '${LABEL}' is synced to GitHub (client $(mask "${client_id}")). Nothing was created in Azure;
the state (${STORAGE_ACCOUNT}/${CONTAINER}/${KEY}) and its backend are unchanged.
Next: run "Terraform Auth Test" from the Actions tab to confirm CI reads this state;
drift detection keeps using the same state.
EOF
else
  cat <<EOF
Done: account '${LABEL}' is configured (client $(mask "${client_id}")).
Next (docs/azure-account-switching.md):
  - wait a few minutes for the federated credential and role assignments to propagate;
  - run "Terraform Auth Test" and "Phase 5 - Drift Detection" (dev) from the Actions tab;
  - the first scan sees an empty state: deploy the dev configuration yourself (never in CI).
EOF
fi
