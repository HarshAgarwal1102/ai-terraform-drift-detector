#!/usr/bin/env bash
# -----------------------------------------------
# scripts/resolve_backend_config.sh
# -----------------------------------------------
# Azure account switching (one account at a time, docs/azure-account-switching.md):
# writes the AzureRM backend settings of the dev environment to a NEW runner-local
# file and proves that the state storage account belongs to the subscription this run
# is signed in to. terraform/environments/dev/backend.tf holds no location, so a
# `terraform init` without this file fails closed instead of reaching another
# account's state. Read-only: one management-plane GET (Reader is enough).
#
# Usage (CI): ./scripts/resolve_backend_config.sh   (after azure/login)
#
# Environment (all required):
#   TFSTATE_RESOURCE_GROUP    resource group of the state storage account
#   TFSTATE_STORAGE_ACCOUNT   storage account name (3-24 lowercase letters and digits)
#   TFSTATE_CONTAINER         blob container name
#   TFSTATE_KEY               state blob, BOUND TO THE STORAGE ACCOUNT (published in the
#                             public drift report as backend_key):
#                               dev-<TFSTATE_STORAGE_ACCOUNT>.tfstate, except
#                               dev.tfstate for aitddtfstatesa001 (the first account).
#                             Storage account names are globally unique, so two accounts
#                             never share a key, whatever machine or hand-edited variable
#                             set it; the investigation tells accounts apart by this key.
#   EXPECTED_SUBSCRIPTION_ID  the subscription this run must use (AZURE_SUBSCRIPTION_ID)
#   BACKEND_CONFIG            path of the file to write; it must not exist yet
#
# Ownership guard: `az storage account show --subscription <expected>` must find the
# account, and its ARM ID must be exactly (case-insensitive)
#   /subscriptions/<expected>/resourceGroups/<group>/providers/Microsoft.Storage/storageAccounts/<name>
#
# Output on success, exit 0: one fixed line naming the key only (never the account,
# group or subscription):
#   backend: state storage verified in the configured subscription; key=<key>
# On failure, exit 1: exactly one line
#   ::error::state storage check failed: failure_code=<code>
# Codes: backend_configuration_missing backend_configuration_invalid
# backend_key_not_bound (the key is not the one the storage account name gives)
# state_storage_unavailable (not found, or no access, in the configured subscription)
# state_storage_not_in_subscription backend_config_write_failed.
# -----------------------------------------------

# An inherited SHELLOPTS=xtrace would print expanded values; turn it off first.
set +x
set -uo pipefail
umask 077

fail() {
  echo "::error::state storage check failed: failure_code=$1"
  exit 1
}

lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

for v in TFSTATE_RESOURCE_GROUP TFSTATE_STORAGE_ACCOUNT TFSTATE_CONTAINER TFSTATE_KEY \
         EXPECTED_SUBSCRIPTION_ID BACKEND_CONFIG; do
  [ -n "${!v:-}" ] || fail backend_configuration_missing
done

rg="${TFSTATE_RESOURCE_GROUP}"
sa="${TFSTATE_STORAGE_ACCOUNT}"
container="${TFSTATE_CONTAINER}"
key="${TFSTATE_KEY}"
subscription="$(lower "${EXPECTED_SUBSCRIPTION_ID}")"

# Strict shapes: nothing can break out of an HCL string, name another path or carry an identifier.
[[ "${rg}" =~ ^[A-Za-z0-9_().-]{1,90}$ && "${rg}" != *. ]] || fail backend_configuration_invalid
[[ "${sa}" =~ ^[a-z0-9]{3,24}$ ]] || fail backend_configuration_invalid
[[ "${container}" =~ ^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$ && "${container}" != *--* ]] \
  || fail backend_configuration_invalid
[[ "${key}" =~ ^dev(-[a-z0-9]{3,24})?\.tfstate$ ]] || fail backend_configuration_invalid
[[ "${subscription}" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] \
  || fail backend_configuration_invalid
# The key names the storage account (only the first account's keeps dev.tfstate).
if [ "${sa}" = "aitddtfstatesa001" ]; then expected_key="dev.tfstate"; else expected_key="dev-${sa}.tfstate"; fi
[ "${key}" = "${expected_key}" ] || fail backend_key_not_bound
if [ -e "${BACKEND_CONFIG}" ] || [ -L "${BACKEND_CONFIG}" ]; then
  fail backend_config_write_failed  # a new file only: a stale one is never reused
fi
command -v az >/dev/null 2>&1 || fail state_storage_unavailable

# --subscription pins the lookup to this run's subscription: an account of another
# subscription (for example the previous Azure account's) is simply not found.
if ! account_id="$(az storage account show --only-show-errors --name "${sa}" --resource-group "${rg}" \
      --subscription "${subscription}" --query id --output tsv 2>/dev/null)"; then
  fail state_storage_unavailable
fi
expected_id="/subscriptions/${subscription}/resourcegroups/$(lower "${rg}")/providers/microsoft.storage/storageaccounts/${sa}"
[ "$(lower "$(printf '%s' "${account_id}" | tr -d '[:space:]')")" = "${expected_id}" ] \
  || fail state_storage_not_in_subscription

# noclobber: the file is created by this run or the step fails.
if ! ( set -C; cat > "${BACKEND_CONFIG}" ) 2>/dev/null <<EOF
resource_group_name  = "${rg}"
storage_account_name = "${sa}"
container_name       = "${container}"
key                  = "${key}"
use_azuread_auth     = true
EOF
then
  fail backend_config_write_failed
fi

echo "backend: state storage verified in the configured subscription; key=${key}"
