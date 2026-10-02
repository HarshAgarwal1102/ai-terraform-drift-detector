#!/usr/bin/env bash
# -----------------------------------------------
# tests/scenarios/run_rg_tag_drift_scenario.sh
# -----------------------------------------------
# Reproducible Resource Group tag-drift scenario (Task 3.6).
#
#   1. baseline  : detection must report in_sync
#   2. inject    : rg_tag_drift_inject.sh --apply   (Azure change)
#   3. detect    : must report external_drift with exactly one change,
#                  tags.aitdd_drift_probe = drifted
#                  (state absent, real "task-3.6", desired absent)
#   4. revert    : rg_tag_drift_revert.sh --apply   (always runs once
#                  drift was injected, even if a check fails)
#   5. detect    : must report in_sync again
#
# Detection = scripts/generate_plan_json.sh (read-only plan) followed by
# scripts/detect_drift.py. Never runs terraform apply.
#
# Usage:
#   tests/scenarios/run_rg_tag_drift_scenario.sh           # read-only: preflight + baseline only
#   tests/scenarios/run_rg_tag_drift_scenario.sh --apply   # full scenario (changes Azure, then reverts)
#
# Evidence for every step is kept in EVIDENCE_ROOT (default: a new temp
# directory outside the repository). Exit 0 only if every check passes.
# -----------------------------------------------

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=rg_tag_drift_common.sh
. "${SCRIPT_DIR}/rg_tag_drift_common.sh"

ADDRESS='module.resource_group.azurerm_resource_group.this["main"]'

APPLY=0
case "${1:-}" in
  "") ;;
  --apply) APPLY=1 ;;
  *) die "usage: $0 [--apply]" ;;
esac

require_tools
command -v python3 >/dev/null 2>&1 || die "python3 is required"
EVIDENCE_ROOT="${EVIDENCE_ROOT:-$(mktemp -d "${TMPDIR:-/tmp}/aitdd-scenario.XXXXXX")}"
if [[ -z "${ARM_SUBSCRIPTION_ID:-}" ]]; then
  ARM_SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
  export ARM_SUBSCRIPTION_ID
fi

FAILED=0
INJECTED=0

# Runs plan generation + classification into EVIDENCE_ROOT/<step>.
detect() {
  local step="$1" dir="${EVIDENCE_ROOT}/$1"
  echo "==> [${step}] detection"
  ARTIFACT_DIR="${dir}" "${ROOT_DIR}/scripts/generate_plan_json.sh" >/dev/null
  local gen_rc=$?
  python3 "${ROOT_DIR}/scripts/detect_drift.py" "${dir}" >/dev/null
  local cls_rc=$?
  if [[ "${gen_rc}" -ne 0 || "${cls_rc}" -ne 0 ]]; then
    echo "    FAIL: detection did not succeed (generate=${gen_rc}, classify=${cls_rc}); see ${dir}"
    FAILED=1
    return 1
  fi
}

# check <step> <description> <jq expression evaluated on drift_classification.json>
check() {
  local step="$1" desc="$2" expr="$3"
  local report="${EVIDENCE_ROOT}/${step}/drift_classification.json"
  if [[ -f "${report}" ]] && jq -e --arg addr "${ADDRESS}" --arg key "${PROBE_KEY}" --arg val "${PROBE_VALUE}" \
      "${expr}" "${report}" >/dev/null 2>&1; then
    echo "    ok: ${desc}"
  else
    echo "    FAIL: ${desc}"
    FAILED=1
  fi
}

expect_in_sync() {
  local step="$1"
  detect "${step}" || return
  check "${step}" "run succeeded" '.outcome == "succeeded"'
  check "${step}" "has_drift is false" '.has_drift == false'
  check "${step}" "plan exit code 0" '.run.plan_exit_code == 0'
  check "${step}" "resource group is in_sync" \
    '[.resources[] | select(.address == $addr)][0].classification == "in_sync"'
  check "${step}" "no attribute changes" \
    '[.resources[] | select(.address == $addr)][0].attribute_changes == []'
}

expect_tag_drift() {
  local step="$1"
  detect "${step}" || return
  local rg='[.resources[] | select(.address == $addr)][0]'
  check "${step}" "run succeeded" '.outcome == "succeeded"'
  check "${step}" "has_drift is true" '.has_drift == true'
  check "${step}" "plan exit code 2" '.run.plan_exit_code == 2'
  check "${step}" "resource group is external_drift" "${rg}.classification == \"external_drift\""
  check "${step}" "drift_action and action are update" "${rg} | .drift_action == \"update\" and .action == \"update\""
  check "${step}" "attributes: tags = drifted" "${rg}.attributes == [{\"name\": \"tags\", \"class\": \"drifted\"}]"
  check "${step}" "exactly one attribute change: tags.${PROBE_KEY}" \
    "${rg}.attribute_changes | length == 1 and .[0].path == [\"tags\", \$key]"
  check "${step}" "change class drifted, state absent, real ${PROBE_VALUE}, desired absent, not redacted" \
    "${rg}.attribute_changes[0] | .class == \"drifted\" and .state == {\"status\": \"absent\"} and .real == {\"status\": \"value\", \"value\": \$val} and .desired == {\"status\": \"absent\"} and .redacted == false"
}

revert_on_exit() {
  if [[ "${INJECTED}" -eq 1 ]]; then
    echo "==> [revert] removing probe tag"
    if ! "${SCRIPT_DIR}/rg_tag_drift_revert.sh" --apply; then
      echo "!!! REVERT FAILED. Restore manually: ${SCRIPT_DIR}/rg_tag_drift_revert.sh --apply" >&2
      FAILED=1
    fi
    INJECTED=0
  fi
}
trap 'revert_on_exit' EXIT
trap 'echo "interrupted" >&2; exit 130' INT TERM

echo "==> Evidence root: ${EVIDENCE_ROOT}"
[[ "$(rg_tags | jq -r --arg k "${PROBE_KEY}" 'has($k)')" == "false" ]] \
  || die "probe tag already present before the scenario; run rg_tag_drift_revert.sh first"

expect_in_sync baseline
if [[ "${FAILED}" -ne 0 ]]; then
  echo "==> Baseline is not in sync; scenario not started (no Azure change made)."
  exit 1
fi

if [[ "${APPLY}" -eq 0 ]]; then
  echo "==> Read-only mode: baseline verified. Re-run with --apply to inject drift, verify, and revert."
  "${SCRIPT_DIR}/rg_tag_drift_inject.sh"
  exit 0
fi

echo "==> [inject] adding probe tag"
INJECTED=1 # armed first: the revert is idempotent, so a partial inject is still cleaned up
"${SCRIPT_DIR}/rg_tag_drift_inject.sh" --apply || die "inject failed"

expect_tag_drift drifted

revert_on_exit
expect_in_sync reverted

if [[ "${FAILED}" -eq 0 ]]; then
  echo "==> SCENARIO PASSED: injected drift was detected exactly and the revert restored in_sync."
  exit 0
fi
echo "==> SCENARIO FAILED: see checks above and evidence in ${EVIDENCE_ROOT}"
exit 1
