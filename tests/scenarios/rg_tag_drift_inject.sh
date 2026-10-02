#!/usr/bin/env bash
# -----------------------------------------------
# tests/scenarios/rg_tag_drift_inject.sh
# -----------------------------------------------
# Introduces controlled external drift (Task 3.6): adds the probe tag
# aitdd_drift_probe=task-3.6 to aitdd-dev-main-rg with the Azure CLI,
# outside Terraform. Uses `az tag update --operation Merge`, which adds
# only this key and leaves every other tag as it is.
#
# Usage:
#   tests/scenarios/rg_tag_drift_inject.sh            # dry run: checks + prints the change
#   tests/scenarios/rg_tag_drift_inject.sh --apply    # performs the Azure change
#
# Undo with: tests/scenarios/rg_tag_drift_revert.sh --apply
# -----------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=rg_tag_drift_common.sh
. "${SCRIPT_DIR}/rg_tag_drift_common.sh"

APPLY=0
case "${1:-}" in
  "") ;;
  --apply) APPLY=1 ;;
  *) die "usage: $0 [--apply]" ;;
esac

require_tools
id="$(rg_id)"
tags_before="$(rg_tags)"
managed_before="$(managed_tags)"

if [[ "$(jq -r --arg k "${PROBE_KEY}" 'has($k)' <<<"${tags_before}")" == "true" ]]; then
  die "probe tag ${PROBE_KEY} is already present; run the revert script first"
fi

echo "==> Target:  ${RG_NAME} ($(printf '%s' "${id}" | masked))"
echo "==> Change:  add tag ${PROBE_KEY}=${PROBE_VALUE} (Merge; other tags untouched)"
echo "==> Command: az tag update --resource-id $(printf '%s' "${id}" | masked) --operation Merge --tags ${PROBE_KEY}=${PROBE_VALUE}"

if [[ "${APPLY}" -eq 0 ]]; then
  echo "==> Dry run only. Re-run with --apply to change Azure."
  exit 0
fi

az tag update --resource-id "${id}" --operation Merge \
  --tags "${PROBE_KEY}=${PROBE_VALUE}" --only-show-errors -o none

tags_after="$(rg_tags)"
[[ "$(jq -r --arg k "${PROBE_KEY}" '.[$k] // ""' <<<"${tags_after}")" == "${PROBE_VALUE}" ]] \
  || die "probe tag was not applied"
[[ "$(managed_tags)" == "${managed_before}" ]] \
  || die "Terraform-managed tags changed unexpectedly: before ${managed_before}, after $(managed_tags)"

echo "==> Drift injected. Tags now: ${tags_after}"
