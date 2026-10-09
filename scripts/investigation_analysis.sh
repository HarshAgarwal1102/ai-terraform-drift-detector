#!/usr/bin/env bash
# -----------------------------------------------
# scripts/investigation_analysis.sh
# -----------------------------------------------
# Drift investigation of one detection run in CI (Task 9B.5; PROJECT_PLAN.md
# Phase 9B G8-G13 and the Task 9B.5 outcome mapping). Runs in plan-and-analyze
# after `Upload Drift Report` and before the cost step, while the job's Azure CLI
# session (Reader) is still active. The investigation never changes the drift
# result: the calling step always exits 0 (the documented D5 pattern) and the
# `investigation` job reports the outcome.
#
# Stages: inputs -> pinned venv (.[azure], ci/azure-constraints.txt, exact-pin
# check) -> anchor fetch (drifted runs only; fail closed) -> `drift-engine
# investigate` (internal drift report) -> public check against the PUBLIC drift
# report -> outputs.
#
# Environment:
#   PLAN_JSON, MANIFEST   the run's plan.json and detection_run.json
#   INTERNAL_REPORT       the internal drift report (runner-only; investigate reads it)
#   PUBLIC_REPORT         the public drift report (uploaded; the binding check uses it)
#   DRIFT_DETECTED        "true" or "false" (the step runs only for a valid result)
#   REPOSITORY            OWNER/NAME;  CURRENT_RUN_ID  the GitHub run id
#   RUNNER_TEMP           absolute runner temp directory
#   GH_TOKEN              GitHub token (actions: read), passed ONLY to the anchor fetch
#   DRIFT_ENGINE_PIPELINE_PRINCIPAL  the job's client id (compared on the runner, never written)
#   PYTHON                interpreter that creates the venv (default: python3)
#   INVESTIGATE_TIMEOUT / FETCH_TIMEOUT  seconds (default 1500 / 300); no step-level timeout
#
# Runner layout (never uploaded except public/):
#   $RUNNER_TEMP/investigation-venv          pinned venv
#   $RUNNER_TEMP/investigation/restricted/   0700: restricted investigation, evidence, logs
#   $RUNNER_TEMP/investigation/anchors/      0700: anchor candidates
#   $RUNNER_TEMP/investigation/public/drift_investigation.json   the only uploadable file
#
# Always exits 0. Outputs (also printed as one counts-only line):
#   investigation_status       succeeded | incomplete | failed
#   investigation_failure      none | inputs_missing | install_failed | pin_mismatch |
#                              anchor_fetch_failed | incomplete | evidence_failed |
#                              evidence_binding_failed | input_failed | investigate_usage |
#                              investigate_internal_error | write_failed | timeout |
#                              public_check_failed
#   investigation_detail       counts by fixed Activity Log failure/limit code and, for
#                              authentication_failed, auth_<reason> (Task 9B.5), or none
#   investigation_publishable  true only for a public file that passed the check
#                              (succeeded, incomplete, or failed but bindable: decision 1)
# -----------------------------------------------

# No `set -e`: every exit status is captured and mapped explicitly.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd -P)"
CONSTRAINTS="${ROOT_DIR}/ci/azure-constraints.txt"
FETCH="${ROOT_DIR}/scripts/fetch_prior_drift_reports.py"
INVESTIGATE_TIMEOUT="${INVESTIGATE_TIMEOUT:-1500}"
FETCH_TIMEOUT="${FETCH_TIMEOUT:-300}"
PYTHON="${PYTHON:-python3}"

# The token is used by the anchor fetch only: removed from the environment of everything else.
FETCH_TOKEN="${GH_TOKEN:-}"
unset GH_TOKEN GITHUB_TOKEN

INVESTIGATION_DIR=""
PUBLIC_FILE=""
RESTRICTED_DIR=""
VENV_DIR=""

# -----------------------------------------------
# Status reporting
# -----------------------------------------------
detail_codes() {
  local evidence="${RESTRICTED_DIR}/activity_log_evidence.json" py="${PYTHON}"
  [[ -n "${RESTRICTED_DIR}" && -s "${evidence}" ]] || { echo none; return; }
  [[ -x "${VENV_DIR}/bin/python" ]] && py="${VENV_DIR}/bin/python"
  "${py}" - "${evidence}" 2>/dev/null <<'EOF' || echo none
import json, re, sys
from collections import Counter
doc = json.load(open(sys.argv[1], encoding="utf-8"))
codes = Counter()
for scope in doc.get("scopes") or []:
    code = (scope.get("error") or {}).get("code")
    if isinstance(code, str) and re.fullmatch(r"[a-z_]{1,40}", code):
        codes[code] += 1
    reason = (scope.get("error") or {}).get("auth_reason")  # Task 9B.5: drift_engine.activity_logs.AUTH_REASONS
    if reason in ("arm_rejected", "assertion_expired", "federation_mismatch", "no_aadsts", "other_aadsts"):
        codes[f"auth_{reason}"] += 1
reason = (doc.get("failure") or {}).get("reason")
if isinstance(reason, str) and re.fullmatch(r"[a-z_]{1,40}", reason):
    codes[reason] += 1
print(",".join(f"{k}={v}" for k, v in sorted(codes.items())) or "none")
EOF
}

public_counts() {
  local py="${PYTHON}"
  [[ -x "${VENV_DIR}/bin/python" ]] && py="${VENV_DIR}/bin/python"
  "${py}" - "${PUBLIC_FILE}" 2>/dev/null <<'EOF' || true
import json, sys
from collections import Counter
doc = json.load(open(sys.argv[1], encoding="utf-8"))
verdicts = Counter(r["verdict"] for r in doc["resources"])
anchors = doc["anchors"]
print(f"outcome={doc['outcome']} resources={len(doc['resources'])} "
      f"verdicts=[{','.join(f'{k}={v}' for k, v in sorted(verdicts.items()))}] "
      f"anchors_examined={anchors['examined']} anchors_accepted={anchors['accepted']}")
EOF
}

# finish <status> <failure> <publishable>: outputs, one counts-only line, exit 0.
finish() {
  local status="$1" failure="$2" publishable="$3" detail counts=""
  detail="$(detail_codes)"
  if [[ "${publishable}" != true && -n "${PUBLIC_FILE}" ]]; then
    rm -f "${PUBLIC_FILE}"  # never uploadable unless it passed the public check
  fi
  [[ "${publishable}" == true ]] && counts=" $(public_counts)"
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    {
      echo "investigation_status=${status}"
      echo "investigation_failure=${failure}"
      echo "investigation_detail=${detail}"
      echo "investigation_publishable=${publishable}"
    } >> "${GITHUB_OUTPUT}"
  fi
  echo "investigation_status=${status} investigation_failure=${failure} investigation_publishable=${publishable} investigation_detail=${detail}${counts}"
  exit 0
}

fail() { finish failed "$1" false; }

# -----------------------------------------------
# Inputs and runner directories
# -----------------------------------------------
for name in PLAN_JSON MANIFEST INTERNAL_REPORT PUBLIC_REPORT; do
  value="${!name:-}"
  if [[ -z "${value}" || "${value}" != /* || ! -f "${value}" || ! -r "${value}" ]]; then
    echo "ERROR: ${name} is missing or not a readable absolute path." >&2
    fail inputs_missing
  fi
done
[[ "${DRIFT_DETECTED:-}" == true || "${DRIFT_DETECTED:-}" == false ]] || { echo "ERROR: DRIFT_DETECTED must be true or false." >&2; fail inputs_missing; }
[[ "${REPOSITORY:-}" =~ ^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$ ]] || { echo "ERROR: REPOSITORY is invalid." >&2; fail inputs_missing; }
[[ "${CURRENT_RUN_ID:-}" =~ ^[1-9][0-9]{0,19}$ ]] || { echo "ERROR: CURRENT_RUN_ID is invalid." >&2; fail inputs_missing; }
[[ -n "${RUNNER_TEMP:-}" && "${RUNNER_TEMP}" == /* ]] || { echo "ERROR: RUNNER_TEMP must be absolute." >&2; fail inputs_missing; }
[[ -f "${CONSTRAINTS}" && -f "${FETCH}" ]] || { echo "ERROR: repository files are missing." >&2; fail inputs_missing; }

INVESTIGATION_DIR="${RUNNER_TEMP}/investigation"
VENV_DIR="${RUNNER_TEMP}/investigation-venv"
for dir in "${INVESTIGATION_DIR}" "${VENV_DIR}"; do
  if [[ -e "${dir}" || -L "${dir}" ]]; then
    echo "ERROR: ${dir##*/} already exists; stale files must never be mistaken for this run." >&2
    INVESTIGATION_DIR="" VENV_DIR=""
    fail inputs_missing
  fi
done
mkdir -p "${INVESTIGATION_DIR}/public" || fail inputs_missing
mkdir -m 0700 "${INVESTIGATION_DIR}/restricted" || fail inputs_missing
RESTRICTED_DIR="${INVESTIGATION_DIR}/restricted"
PUBLIC_FILE="${INVESTIGATION_DIR}/public/drift_investigation.json"
ANCHORS_DIR="${INVESTIGATION_DIR}/anchors"
LOG="${RESTRICTED_DIR}/investigation.log"

# -----------------------------------------------
# Pinned venv (G10): exactly ci/azure-constraints.txt
# -----------------------------------------------
"${PYTHON}" -m venv "${VENV_DIR}" >>"${LOG}" 2>&1 || fail install_failed
"${VENV_DIR}/bin/python" -m pip install --disable-pip-version-check --no-input -c "${CONSTRAINTS}" \
  "${ROOT_DIR}[azure]" >>"${LOG}" 2>&1 || fail install_failed
"${VENV_DIR}/bin/python" - "${CONSTRAINTS}" >>"${LOG}" 2>&1 <<'EOF' || fail pin_mismatch
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
# Anchor fetch (G9): drifted runs only; fail closed (decision 2)
# -----------------------------------------------
ANCHOR_ARGS=()
if [[ "${DRIFT_DETECTED}" == true ]]; then
  [[ -n "${FETCH_TOKEN}" ]] || fail anchor_fetch_failed
  mkdir -m 0700 "${ANCHORS_DIR}" 2>/dev/null || fail anchor_fetch_failed
  rmdir "${ANCHORS_DIR}"  # the fetch script creates it (0700) and requires it new or empty
  fetch_rc=0
  GH_TOKEN="${FETCH_TOKEN}" timeout "${FETCH_TIMEOUT}" "${VENV_DIR}/bin/python" "${FETCH}" \
    --repository "${REPOSITORY}" --current-run-id "${CURRENT_RUN_ID}" --output-dir "${ANCHORS_DIR}" \
    >"${RESTRICTED_DIR}/anchor_fetch.log" 2>&1 || fetch_rc=$?
  grep -E '^anchor_fetch=' "${RESTRICTED_DIR}/anchor_fetch.log" | head -n 1  # counts and fixed codes only
  [[ "${fetch_rc}" -eq 0 ]] || fail anchor_fetch_failed
  ANCHOR_ARGS=(--anchors "${ANCHORS_DIR}" --repository "${REPOSITORY}")
fi
FETCH_TOKEN=""

# -----------------------------------------------
# Investigation (internal drift report) and its exit mapping
# -----------------------------------------------
investigate_rc=0
timeout "${INVESTIGATE_TIMEOUT}" "${VENV_DIR}/bin/drift-engine" investigate \
  --plan "${PLAN_JSON}" --manifest "${MANIFEST}" --report "${INTERNAL_REPORT}" \
  ${ANCHOR_ARGS[@]+"${ANCHOR_ARGS[@]}"} \
  --output "${RESTRICTED_DIR}/drift_investigation.restricted.json" \
  --evidence-output "${RESTRICTED_DIR}/activity_log_evidence.json" \
  --public-output "${PUBLIC_FILE}" >>"${LOG}" 2>&1 || investigate_rc=$?

case "${investigate_rc}" in
  0 | 1) ;;
  2) fail investigate_usage ;;
  70) fail investigate_internal_error ;;
  73) fail write_failed ;;
  124 | 137) fail timeout ;;
  *) fail investigate_internal_error ;;
esac
[[ -s "${PUBLIC_FILE}" ]] || fail investigate_internal_error

# -----------------------------------------------
# Public check against the PUBLIC drift report (item 2; D3: an unbindable document fails here)
# -----------------------------------------------
"${VENV_DIR}/bin/drift-engine" investigation-check --public "${PUBLIC_FILE}" --report "${PUBLIC_REPORT}" \
  >>"${LOG}" 2>&1 || fail public_check_failed

outcome="$("${VENV_DIR}/bin/python" -c 'import json, sys; d = json.load(open(sys.argv[1], encoding="utf-8")); print(d["outcome"], (d.get("failure") or {}).get("stage", "-"))' "${PUBLIC_FILE}" 2>/dev/null)" \
  || fail investigate_internal_error

case "${investigate_rc}:${outcome}" in
  "0:complete -") finish succeeded none true ;;
  "1:incomplete -") finish incomplete incomplete true ;;
  "1:failed evidence") finish failed evidence_failed true ;;
  "1:failed binding") finish failed evidence_binding_failed true ;;
  "1:failed input") finish failed input_failed true ;;
  *) fail investigate_internal_error ;;
esac
