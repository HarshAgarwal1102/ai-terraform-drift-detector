#!/usr/bin/env bash
# -----------------------------------------------
# scripts/auth_test_plan.sh
# -----------------------------------------------
# Task 12.1A (E6): the dev check of terraform-auth-test.yml. Runs init,
# validate, `plan -detailed-exitcode -out` and `show -json` against the remote
# dev backend and prints ONLY fixed lines: the pinned Terraform version, the
# stage results, the plan exit code and validated action counts, or exactly
# one fixed failure code. Every Terraform and jq output goes to runner-local
# files under $RUNNER_TEMP/auth-test, which are never printed or uploaded: the
# job log of this public repository is public. Read-only: never applies.
#
# Usage (CI): ./scripts/auth_test_plan.sh   (ARM_* OIDC variables set by the step)
#
# Environment:
#   RUNNER_TEMP          required; a NEW directory $RUNNER_TEMP/auth-test is created
#   TF_DIR               Terraform root (default: terraform/environments/dev)
#   TERRAFORM_VERSION    pinned Terraform version (default: 1.14.7)
#   GITHUB_STEP_SUMMARY  optional; the same fixed lines are appended
#
# Output (stdout) on success, exit 0:
#   auth-test: terraform_version=<pin>
#   auth-test: init=succeeded validate=succeeded
#   auth-test: plan_exit_code=<0|2> add=N change=N destroy=N replace=N import=N moved=N forget=N output_changes=N
# On failure, exit 1: exactly one line
#   ::error::auth-test failed: failure_code=<code>
# and never a counts line. Codes: preflight_failed version_mismatch init_failed
# validate_failed plan_failed plan_unexpected_exit show_failed plan_json_invalid
# counts_inconsistent internal_error.
#
# plan.json is validated before anything is counted (fail closed):
#   format_version major 1, terraform_version == pin, errored == false,
#   complete == true; every resource_changes entry is an object with a string
#   address, mode managed or data, and change.actions EXACTLY one of
#     managed: ["no-op"] ["create"] ["update"] ["delete"] ["delete","create"]
#              ["create","delete"] ["forget"]
#     data:    ["read"] ["no-op"]
#   output_changes entries: ["no-op"] ["create"] ["update"] ["delete"].
#   Anything else is plan_json_invalid.
# Counts (they overlap by design: a replacement is in add, destroy and replace):
#   add      ["create"], ["delete","create"], ["create","delete"]
#   change   ["update"]
#   destroy  ["delete"], ["delete","create"], ["create","delete"]
#   replace  ["delete","create"], ["create","delete"]
#   import   change.importing set (any allowed action)
#   moved    previous_address set (any allowed action)
#   forget   ["forget"]
#   output_changes  output actions other than ["no-op"]
# Consistency (same rule as generate_plan_json.sh): plan exit 0 requires no
# pending change, plan exit 2 at least one; otherwise counts_inconsistent.
# -----------------------------------------------

# An inherited SHELLOPTS=xtrace would print expanded commands; turn it off first.
set +x
# No `set -e`: plan -detailed-exitcode returns 2 on success, so every exit
# status is captured and evaluated explicitly.
set -uo pipefail
umask 077
unset TF_LOG TF_LOG_PATH TF_LOG_CORE TF_LOG_PROVIDER
export TF_IN_AUTOMATION=1 TF_INPUT=0

RESULT_WRITTEN=0

summary() {
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    printf '%s\n' "$1" >> "${GITHUB_STEP_SUMMARY}" 2>/dev/null || true
  fi
}

# Only ever called with one of the fixed codes listed above.
fail() {
  RESULT_WRITTEN=1
  printf '::error::auth-test failed: failure_code=%s\n' "$1"
  summary "auth-test failed: failure_code=$1"
  exit 1
}

# Any other termination (signal, unexpected error) still ends with a fixed code.
on_exit() {
  if [ "${RESULT_WRITTEN}" -eq 0 ]; then
    RESULT_WRITTEN=1
    printf '::error::auth-test failed: failure_code=internal_error\n'
    summary "auth-test failed: failure_code=internal_error"
    exit 1
  fi
}
trap on_exit EXIT
trap 'exit 130' INT TERM

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(CDPATH='' cd -- "${SCRIPT_DIR}/.." && pwd)"
TF_DIR="${TF_DIR:-${ROOT_DIR}/terraform/environments/dev}"
TERRAFORM_VERSION="${TERRAFORM_VERSION:-1.14.7}"
VAR_FILE="dev.tfvars"

# -----------------------------------------------
# Preflight
# -----------------------------------------------
[ -n "${RUNNER_TEMP:-}" ] && [ -d "${RUNNER_TEMP}" ] || fail preflight_failed
command -v terraform >/dev/null 2>&1 || fail preflight_failed
command -v jq >/dev/null 2>&1 || fail preflight_failed
[ -f "${TF_DIR}/${VAR_FILE}" ] || fail preflight_failed
# TF_CLI_ARGS* would silently inject flags (e.g. -lock=false, -target, -var).
for v in TF_CLI_ARGS TF_CLI_ARGS_init TF_CLI_ARGS_validate TF_CLI_ARGS_plan TF_CLI_ARGS_show; do
  [ -z "${!v:-}" ] || fail preflight_failed
done

# A new directory, so no stale file can be read as this run's evidence.
LOG_DIR="${RUNNER_TEMP}/auth-test"
mkdir "${LOG_DIR}" 2>/dev/null || fail preflight_failed
JQ_LOG="${LOG_DIR}/jq.log"
PLAN_FILE="${LOG_DIR}/tfplan"
PLAN_JSON="${LOG_DIR}/plan.json"

if ! version_json="$(terraform version -json 2>"${LOG_DIR}/version.log")"; then
  fail preflight_failed
fi
actual_version="$(printf '%s' "${version_json}" | jq -r '.terraform_version // empty' 2>>"${JQ_LOG}")"
[ "${actual_version}" = "${TERRAFORM_VERSION}" ] || fail version_mismatch

# -----------------------------------------------
# Init, validate, plan, show (output to runner-local files only)
# -----------------------------------------------
rc=0
terraform -chdir="${TF_DIR}" init -input=false -no-color > "${LOG_DIR}/init.log" 2>&1 || rc=$?
[ "${rc}" -eq 0 ] || fail init_failed

rc=0
terraform -chdir="${TF_DIR}" validate -no-color > "${LOG_DIR}/validate.log" 2>&1 || rc=$?
[ "${rc}" -eq 0 ] || fail validate_failed

rc=0
terraform -chdir="${TF_DIR}" plan -var-file="${VAR_FILE}" -input=false -no-color \
  -detailed-exitcode -out="${PLAN_FILE}" > "${LOG_DIR}/plan.log" 2>&1 || rc=$?
case "${rc}" in
  0 | 2) plan_rc="${rc}" ;;
  1) fail plan_failed ;;
  *) fail plan_unexpected_exit ;;
esac
[ -s "${PLAN_FILE}" ] || fail show_failed

rc=0
terraform -chdir="${TF_DIR}" show -no-color -json "${PLAN_FILE}" > "${PLAN_JSON}" 2> "${LOG_DIR}/show.log" || rc=$?
[ "${rc}" -eq 0 ] || fail show_failed

# -----------------------------------------------
# Validate plan.json and count (one jq pass; output is checked before use)
# -----------------------------------------------
jq -s -e 'length == 1 and (.[0] | type == "object")' "${PLAN_JSON}" > /dev/null 2>>"${JQ_LOG}" \
  || fail plan_json_invalid

# Every count is its own parenthesized expression: in jq, `|` binds more
# loosely than `,`, so `[a | length, b | length]` would not mean two counts.
COUNT_PROGRAM='
  def managed_ok: [["no-op"], ["create"], ["update"], ["delete"], ["delete", "create"], ["create", "delete"],
                   ["forget"]];
  def data_ok: [["read"], ["no-op"]];
  def output_ok: [["no-op"], ["create"], ["update"], ["delete"]];
  def entry_ok:
    type == "object"
    and ((.address | type) == "string")
    and ((.change | type) == "object")
    and ((.change.actions | type) == "array")
    and (.change.actions as $a
         | (.mode == "managed" and any(managed_ok[]; . == $a))
           or (.mode == "data" and any(data_ok[]; . == $a)));
  def drift_ok:
    type == "object" and ((.address | type) == "string")
    and ((.change | type) == "object") and ((.change.actions | type) == "array");
  def output_entry_ok:
    type == "object" and ((.actions | type) == "array")
    and (.actions as $a | any(output_ok[]; . == $a));
  def valid:
    ((.format_version | type) == "string")
    and ((.format_version | split(".")[0]) == "1")
    and (.terraform_version == $tfv)
    and (.errored == false)
    and (.complete == true)
    and ((has("resource_changes") | not)
         or (((.resource_changes | type) == "array") and all(.resource_changes[]; entry_ok)))
    and ((has("resource_drift") | not)
         or (((.resource_drift | type) == "array") and all(.resource_drift[]; drift_ok)))
    and ((has("output_changes") | not)
         or (((.output_changes | type) == "object") and all(.output_changes[]; output_entry_ok)));
  def acts: .change.actions;
  def replaced: acts == ["delete", "create"] or acts == ["create", "delete"];
  if (valid | not) then "invalid"
  else
    [.resource_changes[]?] as $rc
    | [(.output_changes // {})[] | select(.actions != ["no-op"])] as $oc
    | [ ($rc | map(select(acts == ["create"] or replaced)) | length),
        ($rc | map(select(acts == ["update"])) | length),
        ($rc | map(select(acts == ["delete"] or replaced)) | length),
        ($rc | map(select(replaced)) | length),
        ($rc | map(select(.change.importing != null)) | length),
        ($rc | map(select(.previous_address != null)) | length),
        ($rc | map(select(acts == ["forget"])) | length),
        ($oc | length),
        (($rc | map(select((acts != ["no-op"] and acts != ["read"])
                           or .previous_address != null or .change.importing != null)) | length)
         + ($oc | length))
      ]
    | map(tostring) | join(" ")
  end
'
counts="$(jq -r --arg tfv "${TERRAFORM_VERSION}" "${COUNT_PROGRAM}" "${PLAN_JSON}" 2>>"${JQ_LOG}")" \
  || fail plan_json_invalid
counts_shape='^[0-9]+( [0-9]+){8}$'
[[ "${counts}" =~ ${counts_shape} ]] || fail plan_json_invalid
read -r n_add n_change n_destroy n_replace n_import n_moved n_forget n_outputs n_pending <<< "${counts}"

if [ "${plan_rc}" -eq 0 ] && [ "${n_pending}" -ne 0 ]; then fail counts_inconsistent; fi
if [ "${plan_rc}" -eq 2 ] && [ "${n_pending}" -eq 0 ]; then fail counts_inconsistent; fi

# -----------------------------------------------
# Success: fixed lines only
# -----------------------------------------------
RESULT_WRITTEN=1
for line in \
  "auth-test: terraform_version=${TERRAFORM_VERSION}" \
  "auth-test: init=succeeded validate=succeeded" \
  "auth-test: plan_exit_code=${plan_rc} add=${n_add} change=${n_change} destroy=${n_destroy} replace=${n_replace} import=${n_import} moved=${n_moved} forget=${n_forget} output_changes=${n_outputs}"; do
  printf '%s\n' "${line}"
  summary "${line}"
done
exit 0
