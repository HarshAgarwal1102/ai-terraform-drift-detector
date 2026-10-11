#!/usr/bin/env bash
# -----------------------------------------------
# scripts/inventory_analysis.sh
# -----------------------------------------------
# Unmanaged Azure resource inventory of one detection run in CI (Task 10.4). Runs in
# plan-and-analyze after `Upload Drift Report` and before the drift investigation and the
# cost step (which runs `az logout`), while the job's Azure CLI session (Reader) is active.
# It only reads Azure (GET requests to management.azure.com). Unmanaged resources are not
# drift: the calling step always exits 0 (the documented D5 pattern) and the `unmanaged`
# job reports the outcome.
#
# Stages: inputs -> pinned venv (.[azure], ci/azure-constraints.txt, exact-pin check) ->
# `drift-engine inventory` (plan.json + PUBLIC drift report) -> public check (leak scan,
# contract, binding to the public drift report) -> outputs.
#
# Environment:
#   PLAN_JSON           the run's plan.json (runner-only; managed IDs and scope)
#   PUBLIC_REPORT       the public drift report (the binding)
#   RUNNER_TEMP         absolute runner temp directory
#   PYTHON              interpreter that creates the venv (default: python3)
#   Hard bounds in seconds (no step-level timeout; every potentially blocking operation is bounded,
#   worst case about 615 s; a hit is the failure `timeout`):
#     VENV_TIMEOUT 60, PIP_TIMEOUT 180, PIN_CHECK_TIMEOUT 30, INVENTORY_TIMEOUT 300 (drift-engine
#     inventory; its own Azure deadline is 240 s), PUBLIC_CHECK_TIMEOUT 45
#
# Runner layout (never uploaded except public/):
#   $RUNNER_TEMP/inventory-venv                              pinned venv
#   $RUNNER_TEMP/unmanaged/restricted/                       0700: logs
#   $RUNNER_TEMP/unmanaged/public/unmanaged_inventory.json   the only uploadable file
#
# Always exits 0. Outputs (also printed as one counts-only line):
#   inventory_status       complete | incomplete | failed
#   inventory_failure      none | inputs_missing | install_failed | pin_mismatch | inventory_usage |
#                          internal_error | write_failed | timeout | public_check_failed |
#                          listing_failed | incomplete | no_managed_resource_group
#   inventory_detail       counts by fixed scope/detail error code, or none
#   inventory_unmanaged    the number of unmanaged resources (empty unless a document was checked)
#   inventory_publishable  true only for a document that passed the public check (any outcome)
# -----------------------------------------------

# No `set -e`: every exit status is captured and mapped explicitly.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd -P)"
CONSTRAINTS="${ROOT_DIR}/ci/azure-constraints.txt"
VENV_TIMEOUT="${VENV_TIMEOUT:-60}"
PIP_TIMEOUT="${PIP_TIMEOUT:-180}"
PIN_CHECK_TIMEOUT="${PIN_CHECK_TIMEOUT:-30}"
INVENTORY_TIMEOUT="${INVENTORY_TIMEOUT:-300}"
PUBLIC_CHECK_TIMEOUT="${PUBLIC_CHECK_TIMEOUT:-45}"
PYTHON="${PYTHON:-python3}"

# Nothing here needs a GitHub token.
unset GH_TOKEN GITHUB_TOKEN

# The original standard output: the one status line goes there even when finish runs inside a
# command whose output is redirected to the log.
exec 3>&1

UNMANAGED_DIR=""
PUBLIC_FILE=""
VENV_DIR=""
UNMANAGED_COUNT=""
DETAIL="none"

# finish <status> <failure> <publishable>: outputs, one counts-only line, exit 0.
finish() {
  local status="$1" failure="$2" publishable="$3"
  if [[ "${publishable}" != true && -n "${PUBLIC_FILE}" ]]; then
    rm -f "${PUBLIC_FILE}"  # never uploadable unless it passed the public check
    UNMANAGED_COUNT=""
  fi
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    {
      echo "inventory_status=${status}"
      echo "inventory_failure=${failure}"
      echo "inventory_detail=${DETAIL}"
      echo "inventory_unmanaged=${UNMANAGED_COUNT}"
      echo "inventory_publishable=${publishable}"
    } >> "${GITHUB_OUTPUT}"
  fi
  echo "inventory_status=${status} inventory_failure=${failure} inventory_publishable=${publishable} inventory_unmanaged=${UNMANAGED_COUNT:-n/a} inventory_detail=${DETAIL}" >&3
  exit 0
}

fail() { finish failed "$1" false; }

# bounded <seconds> <failure> <command...>: the command under `timeout`; a timeout fails with
# `timeout`, any other non-zero exit with <failure>.
bounded() {
  local seconds="$1" failure="$2" rc=0
  shift 2
  timeout "${seconds}" "$@" || rc=$?
  case "${rc}" in
    0) return 0 ;;
    124 | 137) fail timeout ;;
    *) fail "${failure}" ;;
  esac
}

# -----------------------------------------------
# Inputs and runner directories
# -----------------------------------------------
for name in PLAN_JSON PUBLIC_REPORT; do
  value="${!name:-}"
  if [[ -z "${value}" || "${value}" != /* || ! -f "${value}" || ! -r "${value}" ]]; then
    echo "ERROR: ${name} is missing or not a readable absolute path." >&2
    fail inputs_missing
  fi
done
[[ -n "${RUNNER_TEMP:-}" && "${RUNNER_TEMP}" == /* ]] || { echo "ERROR: RUNNER_TEMP must be absolute." >&2; fail inputs_missing; }
[[ -f "${CONSTRAINTS}" ]] || { echo "ERROR: repository files are missing." >&2; fail inputs_missing; }

UNMANAGED_DIR="${RUNNER_TEMP}/unmanaged"
VENV_DIR="${RUNNER_TEMP}/inventory-venv"
for dir in "${UNMANAGED_DIR}" "${VENV_DIR}"; do
  if [[ -e "${dir}" || -L "${dir}" ]]; then
    echo "ERROR: ${dir##*/} already exists; stale files must never be mistaken for this run." >&2
    UNMANAGED_DIR="" VENV_DIR=""
    fail inputs_missing
  fi
done
mkdir -p "${UNMANAGED_DIR}/public" || fail inputs_missing
mkdir -m 0700 "${UNMANAGED_DIR}/restricted" || fail inputs_missing
PUBLIC_FILE="${UNMANAGED_DIR}/public/unmanaged_inventory.json"
LOG="${UNMANAGED_DIR}/restricted/inventory.log"

# -----------------------------------------------
# Pinned venv: exactly ci/azure-constraints.txt (as the drift investigation, G10)
# -----------------------------------------------
bounded "${VENV_TIMEOUT}" install_failed "${PYTHON}" -m venv "${VENV_DIR}" >>"${LOG}" 2>&1
bounded "${PIP_TIMEOUT}" install_failed "${VENV_DIR}/bin/python" -m pip install --disable-pip-version-check \
  --no-input -c "${CONSTRAINTS}" "${ROOT_DIR}[azure]" >>"${LOG}" 2>&1
bounded "${PIN_CHECK_TIMEOUT}" pin_mismatch "${VENV_DIR}/bin/python" - "${CONSTRAINTS}" >>"${LOG}" 2>&1 <<'EOF'
import re, sys
from importlib.metadata import distributions
norm = lambda name: re.sub(r"[-_.]+", "-", name).lower()
pins = {}
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#"):
        name, version = line.split("==")
        pins[norm(name)] = version
bad = sorted(f"{norm(d.metadata['Name'])}=={d.version}" for d in distributions()
             if norm(d.metadata["Name"]) not in ("drift-engine", "pip", "setuptools", "wheel")
             and pins.get(norm(d.metadata["Name"])) != d.version)
if bad:
    print("installed packages not matching ci/azure-constraints.txt: " + ", ".join(bad))
    sys.exit(1)
EOF

# -----------------------------------------------
# Inventory and its exit mapping
# -----------------------------------------------
inventory_rc=0
timeout "${INVENTORY_TIMEOUT}" "${VENV_DIR}/bin/drift-engine" inventory \
  --plan "${PLAN_JSON}" --report "${PUBLIC_REPORT}" --output "${PUBLIC_FILE}" >>"${LOG}" 2>&1 || inventory_rc=$?

case "${inventory_rc}" in
  0 | 1) ;;
  2) fail inventory_usage ;;
  73) fail write_failed ;;
  124 | 137) fail timeout ;;
  *) fail internal_error ;;
esac
[[ -s "${PUBLIC_FILE}" ]] || fail internal_error

# -----------------------------------------------
# Public check (leak scan, contract, binding to the PUBLIC drift report) and counts
# -----------------------------------------------
check_rc=0
result="$(timeout "${PUBLIC_CHECK_TIMEOUT}" "${VENV_DIR}/bin/python" - "${PUBLIC_FILE}" "${PUBLIC_REPORT}" \
  2>>"${LOG}" <<'EOF'
import json, re, sys
from collections import Counter
from drift_engine.investigation_public import leak_findings, strict_json
from drift_engine.inventory import load_inventory
from drift_engine.unmanaged_cost import inventory_bound_to_report
raw = strict_json(open(sys.argv[1], "rb").read())
report = strict_json(open(sys.argv[2], "rb").read())
if leak_findings(raw):
    sys.exit(1)
doc = load_inventory(raw)
if not inventory_bound_to_report(doc, report):
    sys.exit(1)
codes = Counter([s.error for s in doc.scopes if s.error] + [r.detail_error for r in doc.resources if r.detail_error])
detail = ",".join(f"{k}={v}" for k, v in sorted(codes.items()) if re.fullmatch(r"[a-z_]{1,40}", k)) or "none"
print(doc.outcome, doc.failure or "-", doc.counts.unmanaged, detail)
EOF
)" || check_rc=$?
case "${check_rc}" in
  0) ;;
  124 | 137) fail timeout ;;
  *) fail public_check_failed ;;
esac

read -r outcome failure count detail <<<"${result}"
DETAIL="${detail}"
UNMANAGED_COUNT="${count}"

case "${inventory_rc}:${outcome}:${failure}" in
  "0:complete:-") finish complete none true ;;
  "1:incomplete:-") finish incomplete incomplete true ;;
  "1:failed:listing_failed") finish failed listing_failed true ;;
  "1:failed:no_managed_resource_group") finish failed no_managed_resource_group true ;;
  *) fail internal_error ;;
esac
