#!/usr/bin/env bash
# -----------------------------------------------
# scripts/infracost_analysis.sh
# -----------------------------------------------
# Deterministic Infracost cost estimate of a drift-detection plan (Task 10.1).
# Implements PROJECT_PLAN.md Task 10.1 D1-D8 and the implementation interface
# I1-I5. Cost is informational and never a drift result: this script never
# reads or changes the drift report beyond passing it to the sanitiser for the
# run binding, and its exit status is a cost status only.
#
# Usage (from the repository checkout, inside the de-privileged cost step):
#   PLAN_JSON=... DRIFT_REPORT=... RUN_ID=... DRIFT_ENVIRONMENT=... \
#     INFRACOST_API_KEY=... ./scripts/infracost_analysis.sh
#
# Environment (I3):
#   PLAN_JSON          Absolute path of the same run's `terraform show -json` plan.
#   DRIFT_REPORT       Absolute path of the same run's drift_report.json.
#   RUN_ID             Drift run id (github-<run_id>-<run_attempt> in CI).
#   DRIFT_ENVIRONMENT  Environment name (e.g. dev).
#   RUNNER_TEMP        Absolute runner temp directory (required).
#   COST_DIR           Infracost working directory (default: $RUNNER_TEMP/cost).
#                      raw/    raw Infracost output and logs (never uploaded)
#                      report/ sanitised artifact files (infracost.json, cost_run.json)
#   INFRACOST_API_KEY  Pricing API key (D6); never printed or written.
# Infracost HOME is $RUNNER_TEMP/infracost-home (D6). COST_DIR and that HOME
# must be absolute, outside the repository and new or empty.
#
# Exit status (I2):
#   0   succeeded: sanitised report written to $COST_DIR/report
#   1   cost failure (cost_failure gives the reason)
#   64  usage: missing/invalid input or unusable directory
# The final line is always `cost_status=<succeeded|failed> cost_failure=<code>`,
# and both values are appended to $GITHUB_OUTPUT when it is set.
# -----------------------------------------------

# No `set -e`: every exit status is captured and mapped explicitly.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd -P)"
SANITIZER="${ROOT_DIR}/scripts/sanitize_infracost.py"

# Locked values (D1, D7).
EXPECTED_VERSION="Infracost v0.10.46"
INFRACOST_VERSION_TAG="v0.10.46"

INFRACOST_HOME=""
RAW_DIR=""

# -----------------------------------------------
# Status reporting (I2)
# -----------------------------------------------
# finish <cost_failure> <exit code>. Once Infracost has used its HOME, a
# Terraform Checkpoint directory there overrides any other reason (D7 amendment).
finish() {
  local failure="$1" rc="$2" status="failed"
  if [[ -n "${INFRACOST_HOME}" && -e "${INFRACOST_HOME}/.terraform.d" ]]; then
    failure="unexpected_egress"
    rc=1
  fi
  [[ "${failure}" == "none" ]] && status="succeeded"
  if [[ "${status}" == "failed" && -n "${RAW_DIR}" ]]; then
    local log
    for log in "${RAW_DIR}/infracost.log" "${RAW_DIR}/sanitize.log"; do
      if [[ -s "${log}" ]]; then
        echo "--- last 20 lines of ${log##*/} ---"
        tail -n 20 "${log}"
      fi
    done
  fi
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    {
      echo "cost_status=${status}"
      echo "cost_failure=${failure}"
    } >> "${GITHUB_OUTPUT}"
  fi
  echo "cost_status=${status} cost_failure=${failure}"
  exit "${rc}"
}

usage_error() {
  echo "ERROR: $*" >&2
  finish usage 64
}

failure() {
  local code="$1"
  shift
  echo "ERROR: $*" >&2
  finish "${code}" 1
}

# -----------------------------------------------
# Inputs and directories (I3) -> exit 64
# -----------------------------------------------
require_file() {
  local name="$1" value="$2"
  [[ -n "${value}" ]] || usage_error "${name} is not set."
  [[ "${value}" == /* ]] || usage_error "${name} must be an absolute path."
  [[ -f "${value}" && -r "${value}" ]] || usage_error "${name} is not a readable file."
}

# Creates <dir> if needed; it must be absolute, outside the repository and empty.
prepare_dir() {
  local name="$1" dir="$2" real
  [[ "${dir}" == /* ]] || usage_error "${name} must be an absolute path."
  mkdir -p "${dir}" 2>/dev/null || usage_error "cannot create ${name}."
  real="$(cd "${dir}" && pwd -P)" || usage_error "cannot resolve ${name}."
  if [[ "${real}/" == "${ROOT_DIR}/"* ]]; then
    usage_error "${name} must be outside the repository."
  fi
  if [[ -n "$(ls -A "${real}")" ]]; then
    usage_error "${name} must be new or empty so stale files cannot be mistaken for this run."
  fi
}

require_file PLAN_JSON "${PLAN_JSON:-}"
require_file DRIFT_REPORT "${DRIFT_REPORT:-}"
[[ "${RUN_ID:-}" =~ ^[A-Za-z0-9._-]{1,128}$ ]] || usage_error "RUN_ID is missing or invalid."
[[ "${DRIFT_ENVIRONMENT:-}" =~ ^[a-z0-9-]{1,64}$ ]] || usage_error "DRIFT_ENVIRONMENT is missing or invalid."
[[ -n "${RUNNER_TEMP:-}" && "${RUNNER_TEMP}" == /* ]] || usage_error "RUNNER_TEMP must be set to an absolute path."

COST_DIR="${COST_DIR:-${RUNNER_TEMP}/cost}"
prepare_dir COST_DIR "${COST_DIR}"
prepare_dir "Infracost HOME" "${RUNNER_TEMP}/infracost-home"
COST_DIR="$(cd "${COST_DIR}" && pwd -P)"
RAW_DIR="${COST_DIR}/raw"
REPORT_DIR="${COST_DIR}/report"
mkdir "${RAW_DIR}" "${REPORT_DIR}" || usage_error "cannot create raw/ and report/ in COST_DIR."
RAW_JSON="${RAW_DIR}/infracost.raw.json"

# -----------------------------------------------
# Secret and privilege checks (D6, I4) -> cost failure
# -----------------------------------------------
# Presence only; the value is never printed.
[[ -n "${INFRACOST_API_KEY:-}" ]] || failure missing_api_key "INFRACOST_API_KEY is not set."

if [[ -n "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" || -n "${ACTIONS_ID_TOKEN_REQUEST_TOKEN:-}" ]]; then
  failure oidc_token_present "an OIDC token request variable is still set; the step must blank both."
fi

# Checked with the caller's HOME, where `az logout` / `az account clear` acted.
if command -v az >/dev/null 2>&1; then
  if az account show --only-show-errors >/dev/null 2>&1; then
    failure azure_session_present "an Azure CLI session is still active; the step must log out first."
  fi
fi

INFRACOST_HOME="$(cd "${RUNNER_TEMP}/infracost-home" && pwd -P)"

# Runs Infracost in a subshell with an allowlisted environment: only PATH,
# locale/TLS basics, the isolated HOME, the key and the five D7 controls. The
# key is inherited, never passed as an argument. Everything else (ARM_*, AZURE_*,
# TF_*, GITHUB_*, tokens, any other INFRACOST_*) is removed.
run_infracost() (
  local var
  for var in $(compgen -e); do
    case "${var}" in
      PATH | INFRACOST_API_KEY | TMPDIR | LANG | LC_* | SSL_CERT_FILE | SSL_CERT_DIR) ;;
      *) unset "${var}" 2>/dev/null || true ;;
    esac
  done
  export HOME="${INFRACOST_HOME}"
  export INFRACOST_SKIP_UPDATE_CHECK=true
  export INFRACOST_ENABLE_CLOUD=false
  export INFRACOST_DISABLE_ENVFILE=true
  export INFRACOST_NO_COLOR=true
  export CHECKPOINT_DISABLE=1
  cd "${COST_DIR}" || exit 1
  exec infracost "$@"
)

# -----------------------------------------------
# Version check (D1)
# -----------------------------------------------
command -v infracost >/dev/null 2>&1 || failure version_mismatch "infracost is not on PATH."
version_out="$(run_infracost --version 2>>"${RAW_DIR}/infracost.log")"
version_line="$(printf '%s\n' "${version_out}" | head -n 1)"
if [[ "${version_line}" != "${EXPECTED_VERSION}" ]]; then
  failure version_mismatch "expected '${EXPECTED_VERSION}', got '${version_line}'."
fi

# -----------------------------------------------
# Breakdown (D2): exactly the locked command, on the same run's plan.json
# -----------------------------------------------
infracost_rc=0
run_infracost breakdown --path "${PLAN_JSON}" --format json --out-file "${RAW_JSON}" --no-color \
  >>"${RAW_DIR}/infracost.log" 2>&1 || infracost_rc=$?

# D7 amendment: fail closed if Terraform Checkpoint ran (also enforced in finish).
[[ -e "${INFRACOST_HOME}/.terraform.d" ]] && failure unexpected_egress "${INFRACOST_HOME}/.terraform.d exists after the Infracost run."
[[ "${infracost_rc}" -eq 0 ]] || failure infracost_failed "infracost breakdown exited ${infracost_rc}."

if [[ ! -s "${RAW_JSON}" ]] || ! python3 -c 'import json, sys; json.load(open(sys.argv[1], encoding="utf-8"))' "${RAW_JSON}" 2>/dev/null; then
  failure raw_output_invalid "raw Infracost output is missing or not valid JSON."
fi

# -----------------------------------------------
# Sanitisation (D8, I1)
# -----------------------------------------------
# Checked first: a missing script would make python exit 2, which means price_not_found.
[[ -f "${SANITIZER}" ]] || failure sanitize_failed "sanitiser not found: scripts/sanitize_infracost.py."

sanitize_rc=0
python3 "${SANITIZER}" \
  --raw "${RAW_JSON}" \
  --drift-report "${DRIFT_REPORT}" \
  --run-id "${RUN_ID}" \
  --environment "${DRIFT_ENVIRONMENT}" \
  --infracost-version "${INFRACOST_VERSION_TAG}" \
  --output-dir "${REPORT_DIR}" >"${RAW_DIR}/sanitize.log" 2>&1 || sanitize_rc=$?

case "${sanitize_rc}" in
  0) ;;
  2) failure price_not_found "a cost component has priceNotFound: true." ;;
  *) failure sanitize_failed "sanitiser exited ${sanitize_rc}." ;;
esac

# Exactly the two artifact files (D8).
report_files="$(find "${REPORT_DIR}" -mindepth 1 -maxdepth 1 -exec basename {} \; | LC_ALL=C sort | tr '\n' ' ')"
[[ "${report_files}" == "cost_run.json infracost.json " ]] || failure sanitize_failed "report/ must hold exactly cost_run.json and infracost.json (got: ${report_files})."

finish none 0
