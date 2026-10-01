#!/usr/bin/env bash
# -----------------------------------------------
# scripts/generate_plan_json.sh
# -----------------------------------------------
# Deterministic Terraform plan generation (Task 3.2).
# Implements the command, exit-code and integrity contract in
# docs/drift-detection-spec.md (§4, §5, §8). Read-only: runs init,
# plan and show — never apply.
#
# Usage:
#   ARTIFACT_DIR=/abs/path/outside/repo ./scripts/generate_plan_json.sh
#
# Environment:
#   ARTIFACT_DIR       Absolute, empty (or new) directory OUTSIDE the
#                      repository. Default: $RUNNER_TEMP/drift in CI,
#                      otherwise a fresh mktemp directory.
#   TF_DIR             Terraform root (default: terraform/environments/dev).
#   TERRAFORM_VERSION  Pinned Terraform version (default: 1.14.7).
#
# Evidence written to ARTIFACT_DIR:
#   detection_run.json  run manifest (always, once ARTIFACT_DIR is usable)
#   plan.log            init/plan/show output (always)
#   plan.json           terraform show -json output (plan exit 0 or 2 only)
#   tfplan              binary plan (transient; not consumed downstream)
#
# Script exit status (process outcome only — never a drift verdict):
#   0   run succeeded (plan exit 0 or 2, integrity gate passed);
#       see plan_exit_code in the manifest
#   1   detection failed (preflight/init/plan/show/integrity)
#   64  unusable ARTIFACT_DIR (no manifest can be written)
# -----------------------------------------------

# No `set -e`: terraform plan -detailed-exitcode returns 2 on success,
# so every exit status is captured and evaluated explicitly.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TF_DIR="${TF_DIR:-${ROOT_DIR}/terraform/environments/dev}"
TERRAFORM_VERSION="${TERRAFORM_VERSION:-1.14.7}"
VAR_FILE="dev.tfvars"

# -----------------------------------------------
# Artifact directory: must be outside the tracked tree
# -----------------------------------------------
if [[ -z "${ARTIFACT_DIR:-}" ]]; then
  if [[ -n "${RUNNER_TEMP:-}" ]]; then
    ARTIFACT_DIR="${RUNNER_TEMP}/drift"
  else
    ARTIFACT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/aitdd-drift.XXXXXX")"
  fi
fi

if [[ "${ARTIFACT_DIR}" != /* ]]; then
  echo "ERROR: ARTIFACT_DIR must be an absolute path: ${ARTIFACT_DIR}" >&2
  exit 64
fi
created_dir=0
[[ -d "${ARTIFACT_DIR}" ]] || created_dir=1
mkdir -p "${ARTIFACT_DIR}" || { echo "ERROR: cannot create ARTIFACT_DIR: ${ARTIFACT_DIR}" >&2; exit 64; }
requested_dir="${ARTIFACT_DIR}"
ARTIFACT_DIR="$(cd "${ARTIFACT_DIR}" && pwd -P)"
ROOT_REAL="$(cd "${ROOT_DIR}" && pwd -P)"
if [[ "${ARTIFACT_DIR}/" == "${ROOT_REAL}/"* ]]; then
  # Only remove a directory this script just created (rmdir refuses non-empty ones).
  [[ "${created_dir}" -eq 0 ]] || rmdir "${requested_dir}" 2>/dev/null || true
  echo "ERROR: ARTIFACT_DIR must be outside the repository (${ROOT_REAL}): ${ARTIFACT_DIR}" >&2
  exit 64
fi
if [[ -n "$(ls -A "${ARTIFACT_DIR}")" ]]; then
  echo "ERROR: ARTIFACT_DIR must be empty so stale evidence cannot be mistaken for this run: ${ARTIFACT_DIR}" >&2
  exit 64
fi

PLAN_FILE="${ARTIFACT_DIR}/tfplan"
PLAN_JSON="${ARTIFACT_DIR}/plan.json"
PLAN_LOG="${ARTIFACT_DIR}/plan.log"
MANIFEST="${ARTIFACT_DIR}/detection_run.json"
: > "${PLAN_LOG}"

# -----------------------------------------------
# Run state (written to the manifest)
# -----------------------------------------------
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [[ -n "${GITHUB_RUN_ID:-}" ]]; then
  RUN_ID="github-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT:-1}"
else
  RUN_ID="local-$(date -u +%Y%m%dT%H%M%SZ)-$$"
fi
GIT_COMMIT="$(git -C "${ROOT_DIR}" rev-parse HEAD 2>/dev/null || true)"
ENVIRONMENT="$(basename "${TF_DIR}")"
TF_DIR_REAL="$(cd "${TF_DIR}" 2>/dev/null && pwd -P || echo "${TF_DIR}")"
WORKING_DIR="${TF_DIR_REAL#"${ROOT_REAL}/"}" # repo-relative when inside the repository
TF_ACTUAL_VERSION=""
BACKEND_KEY=""
PLAN_RC=""
SHOW_RC=""
OUTCOME="failed"
FAILURE_STAGE="preflight"
FAILURE_REASON="script did not complete"
MANIFEST_WRITTEN=0

log_section() { printf '\n===== %s (%s) =====\n' "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "${PLAN_LOG}"; }

write_manifest() {
  local finished_at
  finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  # Built with jq (when present) so every value is correctly JSON-escaped.
  if command -v jq >/dev/null 2>&1; then
    jq -n \
      --arg outcome "${OUTCOME}" \
      --arg failure_stage "${FAILURE_STAGE}" \
      --arg failure_reason "${FAILURE_REASON}" \
      --arg plan_rc "${PLAN_RC}" \
      --arg show_rc "${SHOW_RC}" \
      --arg tf_version "${TF_ACTUAL_VERSION}" \
      --arg environment "${ENVIRONMENT}" \
      --arg working_dir "${WORKING_DIR}" \
      --arg backend_key "${BACKEND_KEY}" \
      --arg git_commit "${GIT_COMMIT}" \
      --arg started_at "${STARTED_AT}" \
      --arg finished_at "${finished_at}" \
      --arg run_id "${RUN_ID}" \
      '
      def num_or_null: if . == "" then null else tonumber end;
      def str_or_null: if . == "" then null else . end;
      {
        outcome: $outcome,
        failure_stage: (if $outcome == "succeeded" then null else $failure_stage end),
        failure_reason: (if $outcome == "succeeded" then null else $failure_reason end),
        plan_exit_code: ($plan_rc | num_or_null),
        show_exit_code: ($show_rc | num_or_null),
        terraform_version: ($tf_version | str_or_null),
        environment: $environment,
        working_dir: $working_dir,
        backend_key: ($backend_key | str_or_null),
        git_commit: ($git_commit | str_or_null),
        started_at: $started_at,
        finished_at: $finished_at,
        run_id: $run_id
      }' > "${MANIFEST}"
  else
    # jq unavailable: minimal manifest; values here contain no quotes.
    printf '{"outcome":"failed","failure_stage":"preflight","failure_reason":"jq is required but was not found","started_at":"%s","finished_at":"%s","run_id":"%s"}\n' \
      "${STARTED_AT}" "${finished_at}" "${RUN_ID}" > "${MANIFEST}"
  fi
  MANIFEST_WRITTEN=1
}

fail() {
  FAILURE_STAGE="$1"
  FAILURE_REASON="$2"
  OUTCOME="failed"
  echo "DETECTION FAILED [${FAILURE_STAGE}]: ${FAILURE_REASON}" >&2
  echo "  Drift status is UNKNOWN for this run — it must not be treated as 'no drift'." >&2
  echo "  Evidence: ${ARTIFACT_DIR}" >&2
  write_manifest
  exit 1
}

# Any unexpected termination still leaves an explicit failed manifest.
INTERRUPTED=0
on_exit() {
  local rc=$?
  if [[ "${MANIFEST_WRITTEN}" -eq 0 ]]; then
    OUTCOME="failed"
    if [[ "${INTERRUPTED}" -eq 1 ]]; then
      FAILURE_REASON="interrupted by signal during ${FAILURE_STAGE}"
    else
      FAILURE_REASON="script terminated unexpectedly (exit ${rc}) during ${FAILURE_STAGE}"
    fi
    write_manifest
  fi
}
trap on_exit EXIT
trap 'INTERRUPTED=1; exit 130' INT TERM

# -----------------------------------------------
# Preflight
# -----------------------------------------------
command -v jq >/dev/null 2>&1 || fail preflight "jq is required but was not found"
command -v terraform >/dev/null 2>&1 || fail preflight "terraform is required but was not found"
[[ -f "${TF_DIR}/${VAR_FILE}" ]] || fail preflight "var-file not found: ${TF_DIR}/${VAR_FILE}"

# TF_CLI_ARGS* would silently inject flags (e.g. -refresh=false, -target,
# -lock=false, -var) that the contract forbids.
for v in TF_CLI_ARGS TF_CLI_ARGS_init TF_CLI_ARGS_plan TF_CLI_ARGS_show; do
  [[ -z "${!v:-}" ]] || fail preflight "${v} is set; extra Terraform CLI arguments are not permitted by the detection contract"
done

TF_ACTUAL_VERSION="$(terraform version -json 2>>"${PLAN_LOG}" | jq -r '.terraform_version // empty' 2>>"${PLAN_LOG}")"
[[ "${TF_ACTUAL_VERSION}" == "${TERRAFORM_VERSION}" ]] \
  || fail preflight "Terraform version '${TF_ACTUAL_VERSION:-unknown}' does not match pinned ${TERRAFORM_VERSION}"

echo "==> Evidence directory: ${ARTIFACT_DIR}"

# -----------------------------------------------
# 1. Init (remote backend)
# -----------------------------------------------
FAILURE_STAGE="init"
log_section "terraform init"
terraform -chdir="${TF_DIR}" init -input=false -no-color >> "${PLAN_LOG}" 2>&1
init_rc=$?
[[ "${init_rc}" -eq 0 ]] || fail init "terraform init exited ${init_rc}"
BACKEND_KEY="$(jq -r '.backend.config.key // empty' "${TF_DIR}/.terraform/terraform.tfstate" 2>/dev/null || true)"

# -----------------------------------------------
# 2. Plan — refresh ON, lock ON, exit code captured explicitly
# -----------------------------------------------
FAILURE_STAGE="plan"
echo "==> terraform plan (-detailed-exitcode)"
log_section "terraform plan"
terraform -chdir="${TF_DIR}" plan \
  -var-file="${VAR_FILE}" \
  -input=false -no-color \
  -lock-timeout=120s \
  -detailed-exitcode \
  -out="${PLAN_FILE}" >> "${PLAN_LOG}" 2>&1
PLAN_RC=$?

case "${PLAN_RC}" in
  0 | 2) ;;
  1) fail plan "terraform plan exited 1 (error); any plan file written is not valid evidence" ;;
  *) fail plan "terraform plan exited unexpectedly with ${PLAN_RC}" ;;
esac

# -----------------------------------------------
# 3. Show — machine-readable plan JSON
# -----------------------------------------------
FAILURE_STAGE="show"
echo "==> terraform show -json"
log_section "terraform show -json (stderr only)"
terraform -chdir="${TF_DIR}" show -no-color -json "${PLAN_FILE}" > "${PLAN_JSON}" 2>> "${PLAN_LOG}"
SHOW_RC=$?
if [[ "${SHOW_RC}" -ne 0 ]]; then
  rm -f "${PLAN_JSON}" # partial output must not look like evidence
  fail show "terraform show -json exited ${SHOW_RC}"
fi

# -----------------------------------------------
# 4. Integrity gate (spec §5.3)
# -----------------------------------------------
FAILURE_STAGE="integrity"
if ! jq -s -e 'length == 1 and (.[0] | type == "object")' "${PLAN_JSON}" > /dev/null 2>&1; then
  fail integrity "plan.json is not exactly one valid JSON object"
fi

# Prints one line per violation; empty output means the gate passed.
violations="$(jq -r --argjson rc "${PLAN_RC}" --arg tfv "${TERRAFORM_VERSION}" '
  def actions_ok: (.change.actions | type) == "array";
  def structural:
    [
      (if (.format_version | type) != "string" then "format_version missing or not a string"
       elif (.format_version | split(".")[0]) != "1" then "unsupported format_version \(.format_version) (major must be 1)"
       else empty end),
      (if .terraform_version != $tfv then "terraform_version \(.terraform_version) != pinned \($tfv)" else empty end),
      (if .errored != false then "errored is \(.errored | tojson) (must be false)" else empty end),
      (if .complete != true then "complete is \(.complete | tojson) (must be true)" else empty end),
      (if has("resource_changes") and (.resource_changes | type) != "array" then "resource_changes is not an array"
       elif any(.resource_changes[]?; (type != "object") or ((.address | type) != "string") or (actions_ok | not))
       then "resource_changes contains an entry without address/change.actions" else empty end),
      (if has("resource_drift") and (.resource_drift | type) != "array" then "resource_drift is not an array"
       elif any(.resource_drift[]?; (type != "object") or ((.address | type) != "string") or (actions_ok | not))
       then "resource_drift contains an entry without address/change.actions" else empty end),
      (if has("output_changes") and (.output_changes | type) != "object" then "output_changes is not an object"
       elif any(.output_changes[]?; (type != "object") or ((.actions | type) != "array"))
       then "output_changes contains an entry without actions" else empty end)
    ];
  def pending:
    ([.resource_changes[]?
       | select((.change.actions != ["no-op"] and .change.actions != ["read"])
                or (.previous_address != null) or (.change.importing != null))] | length)
    + ([.output_changes[]? | select(.actions != ["no-op"])] | length);
  structural as $s
  | if ($s | length) > 0 then $s[]
    elif $rc == 0 and pending > 0 then "plan exit 0 but plan.json contains \(pending) pending change(s)"
    elif $rc == 2 and pending == 0 then "plan exit 2 but plan.json contains no pending change"
    else empty end
' "${PLAN_JSON}" 2>&1)"
gate_rc=$?

if [[ "${gate_rc}" -ne 0 ]]; then
  fail integrity "integrity gate could not evaluate plan.json: ${violations}"
fi
if [[ -n "${violations}" ]]; then
  log_section "integrity gate violations"
  printf '%s\n' "${violations}" >> "${PLAN_LOG}"
  fail integrity "$(printf '%s' "${violations}" | paste -sd ';' -)"
fi

# -----------------------------------------------
# Success — evidence is valid; drift is decided downstream from plan.json
# -----------------------------------------------
OUTCOME="succeeded"
FAILURE_STAGE=""
FAILURE_REASON=""
write_manifest

if [[ "${PLAN_RC}" -eq 0 ]]; then
  echo "==> Plan succeeded: no pending changes (exit 0). Drift is decided from plan.json, not this exit code."
else
  echo "==> Plan succeeded: pending changes present (exit 2). This is not by itself drift; see plan.json."
fi
echo "==> Evidence: ${MANIFEST}"
exit 0
