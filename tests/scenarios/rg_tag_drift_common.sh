# -----------------------------------------------
# tests/scenarios/rg_tag_drift_common.sh
# -----------------------------------------------
# Shared settings and guards for the Resource Group tag-drift scenario
# (Task 3.6). Sourced by the inject, revert and runner scripts; not run
# directly.
#
# The scenario changes exactly ONE thing outside Terraform: a dedicated
# probe tag on the dev Resource Group. The Terraform-managed tags
# (environment, managed_by, project) are never touched, and the probe
# key is never one of them.
# -----------------------------------------------

RG_NAME="aitdd-dev-main-rg"
PROBE_KEY="aitdd_drift_probe"
PROBE_VALUE="task-3.6"
MANAGED_TAG_KEYS="environment managed_by project"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_tools() {
  command -v az >/dev/null 2>&1 || die "Azure CLI (az) is required"
  command -v jq >/dev/null 2>&1 || die "jq is required"
  az account show --only-show-errors -o none >/dev/null 2>&1 || die "not logged in to Azure (run: az login)"
  case " ${MANAGED_TAG_KEYS} " in
    *" ${PROBE_KEY} "*) die "probe key must not be a Terraform-managed tag" ;;
  esac
}

# Resource ID of the Resource Group, looked up at runtime (never hard-coded).
rg_id() {
  az group show --name "${RG_NAME}" --query id -o tsv --only-show-errors \
    || die "Resource Group ${RG_NAME} not found or not readable"
}

# Current tags as a compact JSON object ({} when the RG has none).
rg_tags() {
  az group show --name "${RG_NAME}" --query tags -o json --only-show-errors | jq -c '. // {}'
}

# Terraform-managed tags only, used to prove they are left unchanged.
managed_tags() {
  rg_tags | jq -c --arg keys "${MANAGED_TAG_KEYS}" \
    'with_entries(select(.key as $k | ($keys | split(" ") | index($k))))'
}

# Resource ID with the subscription masked, for anything printed.
masked() {
  sed -E 's#/subscriptions/[^/]+#/subscriptions/***#'
}
