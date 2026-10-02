#!/usr/bin/env bash
# -----------------------------------------------
# tests/scenarios/rg_tag_drift_revert.sh
# -----------------------------------------------
# Reverts the controlled drift from rg_tag_drift_inject.sh (Task 3.6):
# removes ONLY the probe tag aitdd_drift_probe from aitdd-dev-main-rg
# with `az tag update --operation Delete`. Idempotent: does nothing when
# the probe tag is absent. Never runs terraform apply.
#
# Usage:
#   tests/scenarios/rg_tag_drift_revert.sh            # dry run: checks + prints the change
#   tests/scenarios/rg_tag_drift_revert.sh --apply    # performs the Azure change
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

if [[ "$(jq -r --arg k "${PROBE_KEY}" 'has($k)' <<<"${tags_before}")" != "true" ]]; then
  echo "==> Probe tag ${PROBE_KEY} is absent; nothing to revert."
  exit 0
fi
# Delete the key with whatever value it currently has.
current="$(jq -r --arg k "${PROBE_KEY}" '.[$k]' <<<"${tags_before}")"

echo "==> Target:  ${RG_NAME} ($(printf '%s' "${id}" | masked))"
echo "==> Change:  remove tag ${PROBE_KEY} (Delete; other tags untouched)"
echo "==> Command: az tag update --resource-id $(printf '%s' "${id}" | masked) --operation Delete --tags ${PROBE_KEY}=${current}"

if [[ "${APPLY}" -eq 0 ]]; then
  echo "==> Dry run only. Re-run with --apply to change Azure."
  exit 0
fi

az tag update --resource-id "${id}" --operation Delete \
  --tags "${PROBE_KEY}=${current}" --only-show-errors -o none

tags_after="$(rg_tags)"
[[ "$(jq -r --arg k "${PROBE_KEY}" 'has($k)' <<<"${tags_after}")" == "false" ]] \
  || die "probe tag is still present after revert"
[[ "$(managed_tags)" == "${managed_before}" ]] \
  || die "Terraform-managed tags changed unexpectedly: before ${managed_before}, after $(managed_tags)"

echo "==> Drift reverted. Tags now: ${tags_after}"
