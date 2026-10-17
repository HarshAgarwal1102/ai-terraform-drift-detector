#!/usr/bin/env bash
# -----------------------------------------------
# scripts/run_dashboard.sh
# -----------------------------------------------
# Phase 13: start the drift dashboard with one command.
#
#   1. Python environment: uses .venv (created if missing) and installs the
#      dashboard dependencies there if they are missing (pinned by ci/*-constraints.txt).
#   2. Sign-in: on first run creates .artifacts/dashboard-local/users.json (0600,
#      SHA-256 digest only) and prints the sign-in token ONCE. --new-token replaces it.
#   3. Data: with --fetch (or when the data directory is empty) asks for a read-only
#      GitHub token (input hidden, never stored) and runs scripts/fetch_dashboard_data.py.
#   4. Starts dashboard-api on 127.0.0.1 (loopback only) and opens the browser.
#
# Usage:
#   scripts/run_dashboard.sh [--fetch] [--new-token] [--port N] [--terraform-json PATH] [--no-browser]
#
# --terraform-json: a local `terraform show -json` state for the "Caller recorded by Azure"
# lookup (needs `az login`); default .artifacts/dashboard-local/terraform-state.json if present.
# Without it the caller shows `Unknown (no local Terraform state configured)`.
#
# Environment (optional): DASHBOARD_DATA_DIR (default .artifacts/dashboard),
# DASHBOARD_VENV (default .venv), DASHBOARD_LOCAL_DIR (default .artifacts/dashboard-local).
# Stop the dashboard with Ctrl+C.
# -----------------------------------------------

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

REPOSITORY="HarshAgarwal1102/ai-terraform-drift-detector"
DATA_DIR="${DASHBOARD_DATA_DIR:-.artifacts/dashboard}"
VENV="${DASHBOARD_VENV:-.venv}"
LOCAL_DIR="${DASHBOARD_LOCAL_DIR:-.artifacts/dashboard-local}"
USERS_FILE="${LOCAL_DIR}/users.json"
PORT=8000
FETCH=0
NEW_TOKEN=0
OPEN_BROWSER=1
SETUP_ONLY=0
TERRAFORM_JSON=""

die() { echo "ERROR: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fetch) FETCH=1 ;;
    --new-token) NEW_TOKEN=1 ;;
    --no-browser) OPEN_BROWSER=0 ;;
    --setup-only) SETUP_ONLY=1; OPEN_BROWSER=0 ;;  # prepare everything, do not start (tests)
    --port) shift; [[ "${1:-}" =~ ^[0-9]{2,5}$ ]] || die "--port needs a number"; PORT="$1" ;;
    --terraform-json) shift; [[ -n "${1:-}" ]] || die "--terraform-json needs a path"; TERRAFORM_JSON="$1" ;;
    -h|--help) sed -n '5,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option $1 (see --help)" ;;
  esac
  shift
done

# --- 1. Python environment --------------------------------------------------
PY="${VENV}/bin/python"
if [[ ! -x "${PY}" ]]; then
  BASE=""
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "${candidate}" >/dev/null 2>&1 \
        && "${candidate}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
      BASE="${candidate}"; break
    fi
  done
  [[ -n "${BASE}" ]] || die "Python 3.11 or newer is required"
  echo "==> Creating ${VENV} with ${BASE}"
  "${BASE}" -m venv "${VENV}"
fi
if ! "${PY}" -c 'import fastapi, uvicorn, azure.identity, dashboard_api, drift_engine' >/dev/null 2>&1; then
  echo "==> Installing the dashboard dependencies into ${VENV} (first run only)"
  "${PY}" -m pip install --disable-pip-version-check --quiet \
    -c ci/ai-constraints.txt -c ci/azure-constraints.txt -c ci/dashboard-constraints.txt -e ".[azure,dashboard]"
fi

# --- 2. Sign-in token -------------------------------------------------------
mkdir -p "${LOCAL_DIR}" && chmod 700 "${LOCAL_DIR}"
if [[ ! -f "${USERS_FILE}" || "${NEW_TOKEN}" -eq 1 ]]; then
  TOKEN="$("${PY}" - "${USERS_FILE}" <<'EOF'
import hashlib, json, os, secrets, sys
path, token = sys.argv[1], secrets.token_urlsafe(32)
users = {"users": [{"name": "local-admin", "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                    "roles": ["viewer", "caller_reader"]}]}
fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as fh:
    json.dump(users, fh)
os.replace(path + ".tmp", path)
print(token)
EOF
)"
  echo
  echo "=================================================================="
  echo " Dashboard sign-in token (shown once; keep it in your password manager):"
  echo
  echo "   ${TOKEN}"
  echo
  echo " Lost it? Run: scripts/run_dashboard.sh --new-token"
  echo "=================================================================="
  echo
  unset TOKEN
fi
chmod 600 "${USERS_FILE}"

# --- 3. Data ----------------------------------------------------------------
if [[ "${FETCH}" -eq 1 || ! -d "${DATA_DIR}" || -z "$(ls -A "${DATA_DIR}" 2>/dev/null)" ]]; then
  if [[ "${SETUP_ONLY}" -eq 1 && "${FETCH}" -eq 0 ]]; then
    echo "==> No data in ${DATA_DIR} (run with --fetch to download it)"
  else
    echo "==> Fetching the latest workflow artifacts and drift issues from GitHub"
    echo "    Paste a read-only GitHub token (Actions: Read, Issues: Read); input is hidden."
    read -rs -p "    GitHub token: " GH_TOKEN; echo
    [[ -n "${GH_TOKEN}" ]] || die "no token entered"
    GH_TOKEN="${GH_TOKEN}" "${PY}" scripts/fetch_dashboard_data.py --repository "${REPOSITORY}" \
      --data-dir "${DATA_DIR}" || echo "WARNING: the fetch reported a problem (see the line above); continuing with the data present."
    unset GH_TOKEN
  fi
fi

# --- 4. Start ---------------------------------------------------------------
if [[ -z "${TERRAFORM_JSON}" && -f "${LOCAL_DIR}/terraform-state.json" ]]; then
  TERRAFORM_JSON="${LOCAL_DIR}/terraform-state.json"
fi
if [[ -n "${TERRAFORM_JSON}" ]]; then
  [[ -f "${TERRAFORM_JSON}" ]] || die "terraform JSON not found: ${TERRAFORM_JSON}"
  export DASHBOARD_TERRAFORM_JSON="${TERRAFORM_JSON}"
  echo "==> Caller lookup enabled (Terraform state: ${TERRAFORM_JSON}; needs az login)"
else
  unset DASHBOARD_TERRAFORM_JSON
  echo "==> Caller lookup off: no Terraform state given (--terraform-json PATH)"
fi
export DASHBOARD_DATA_DIR="${DATA_DIR}" DASHBOARD_USERS_FILE="${USERS_FILE}"

URL="http://127.0.0.1:${PORT}/"
if [[ "${SETUP_ONLY}" -eq 1 ]]; then
  echo "==> Ready: ${VENV}/bin/dashboard-api --port ${PORT}  (${URL})"
  exit 0
fi
if "${PY}" -c "import socket, sys; s = socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1', ${PORT})) == 0 else 1)"; then
  die "port ${PORT} is already in use (another dashboard running?); use --port N"
fi
echo "==> Dashboard: ${URL}  (sign in with your token; Ctrl+C stops it)"
if [[ "${OPEN_BROWSER}" -eq 1 ]] && command -v open >/dev/null 2>&1; then
  ( sleep 2; open "${URL}" ) &
fi
exec "${VENV}/bin/dashboard-api" --port "${PORT}"
