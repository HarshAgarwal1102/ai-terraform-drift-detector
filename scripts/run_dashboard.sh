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
#   5. GitHub (Task 13.5): no flag needed. The local-admin user holds the data_refresher role; in the
#      dashboard, "Connect GitHub" takes a read-only GitHub token (verified, kept in the server's
#      memory only, never written to disk) and "Check GitHub for new runs" then downloads new runs.
#      --enable-github-fetch (Task 13.4) is DEPRECATED but still works: it asks for the token here
#      and hands it to dashboard-api over a pipe (never an argument, environment variable or file).
#      --no-github (or DASHBOARD_NO_GITHUB=1) turns GitHub access off: no role is granted, the
#      dashboard refuses to connect or fetch, and users.json is left exactly as it is.
#
# Usage:
#   scripts/run_dashboard.sh [--fetch] [--enable-github-fetch | --no-github] [--new-token] [--port N]
#                            [--terraform-json PATH] [--no-browser]
#
# --terraform-json: a local `terraform show -json` state for the "Caller recorded by Azure"
# lookup (needs `az login`); default .artifacts/dashboard-local/terraform-state.json if present.
# Without it the caller shows `Unknown (no local Terraform state configured)`.
#
# Environment (optional): DASHBOARD_DATA_DIR (default .artifacts/dashboard),
# DASHBOARD_VENV (default .venv), DASHBOARD_LOCAL_DIR (default .artifacts/dashboard-local).
# The GitHub token needs Actions: Read, Issues: Read (and Metadata: Read) on this repository only.
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
ENABLE_GITHUB_FETCH=0
NO_GITHUB=0
[[ "${DASHBOARD_NO_GITHUB:-}" == "1" ]] && NO_GITHUB=1
_GH_FETCH_TOKEN=""

die() { echo "ERROR: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fetch) FETCH=1 ;;
    --enable-github-fetch) ENABLE_GITHUB_FETCH=1
      echo "NOTE: --enable-github-fetch is deprecated: connect GitHub in the dashboard (\"Connect GitHub\") instead." >&2 ;;
    --no-github) NO_GITHUB=1 ;;
    --new-token) NEW_TOKEN=1 ;;
    --no-browser) OPEN_BROWSER=0 ;;
    --setup-only) SETUP_ONLY=1; OPEN_BROWSER=0 ;;  # prepare everything, do not start (tests)
    --port) shift; [[ "${1:-}" =~ ^[0-9]{2,5}$ ]] || die "--port needs a number"; PORT="$1" ;;
    --terraform-json) shift; [[ -n "${1:-}" ]] || die "--terraform-json needs a path"; TERRAFORM_JSON="$1" ;;
    -h|--help) sed -n '5,33p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option $1 (see --help)" ;;
  esac
  shift
done
if [[ "${NO_GITHUB}" -eq 1 && ( "${ENABLE_GITHUB_FETCH}" -eq 1 || "${FETCH}" -eq 1 ) ]]; then
  die "--no-github cannot be combined with --enable-github-fetch or --fetch"
fi

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
USERS_OK=1
if [[ -L "${USERS_FILE}" ]] || { [[ -e "${USERS_FILE}" ]] && [[ ! -f "${USERS_FILE}" ]]; }; then
  # Something that is not a regular file is in the way: never replace it. The dashboard then refuses every
  # sign-in (503 auth_unavailable) until it is fixed; nothing is granted.
  echo "WARNING: ${USERS_FILE} is not a regular file; leaving it untouched (sign-in will be refused until it is fixed)." >&2
  USERS_OK=0
elif [[ ! -f "${USERS_FILE}" || "${NEW_TOKEN}" -eq 1 ]]; then
  TOKEN="$("${PY}" - "${USERS_FILE}" <<'EOF'
import hashlib, json, os, secrets, sys
path, token = sys.argv[1], secrets.token_urlsafe(32)
users = {"users": [{"name": "local-admin", "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                    "roles": ["viewer", "caller_reader", "data_refresher"]}]}
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
if [[ "${USERS_OK}" -eq 1 ]]; then
  chmod 600 "${USERS_FILE}" 2>/dev/null || echo "WARNING: could not set ${USERS_FILE} to mode 0600." >&2
fi
# An older users file: give local-admin the data_refresher role (its token is unchanged), so the dashboard can
# connect GitHub and check for new runs without any startup flag. Only the launcher's own local-admin user, only
# when the file parses as the expected shape; any problem leaves the file untouched (the server then decides:
# an unusable file refuses every sign-in) and never stops the launcher. --no-github skips this entirely.
if [[ "${USERS_OK}" -eq 1 && "${NO_GITHUB}" -eq 0 ]]; then
  "${PY}" - "${USERS_FILE}" <<'PYEOF' || echo "WARNING: the users file role check failed; ${USERS_FILE} was left unchanged." >&2
import json, os, sys
path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
except (OSError, ValueError) as exc:  # unreadable, not UTF-8, not JSON: never rewritten
    kind = "not valid JSON" if isinstance(exc, ValueError) else "unreadable"
    print(f"WARNING: {path} is {kind}; it was left unchanged and the data_refresher role was not checked. "
          "Fix it or run scripts/run_dashboard.sh --new-token (sign-in is refused until then).", file=sys.stderr)
    sys.exit(0)
users = doc.get("users") if isinstance(doc, dict) else None
if not isinstance(users, list) or not all(isinstance(u, dict) and isinstance(u.get("roles"), list) for u in users):
    print(f"WARNING: {path} does not have the expected shape; it was left unchanged.", file=sys.stderr)
    sys.exit(0)
changed = False
for user in users:
    if user.get("name") == "local-admin" and "data_refresher" not in user["roles"]:
        user["roles"] = list(user["roles"]) + ["data_refresher"]
        changed = True
if changed:
    try:
        fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(doc, fh)
        os.replace(path + ".tmp", path)
    except OSError:
        try:
            os.remove(path + ".tmp")
        except OSError:
            pass
        print(f"WARNING: could not update {path}; it was left unchanged.", file=sys.stderr)
        sys.exit(0)
    print("==> local-admin now has the data_refresher role (Check GitHub for new runs)")
PYEOF
fi

# GitHub token: asked once, hidden, kept in this shell variable only (never exported or written).
ask_github_token() {
  if [[ -z "${_GH_FETCH_TOKEN}" ]]; then
    echo "    Paste a read-only GitHub token (Actions: Read, Issues: Read); input is hidden."
    read -rs -p "    GitHub token: " _GH_FETCH_TOKEN; echo
    export -n _GH_FETCH_TOKEN 2>/dev/null || true
    [[ -n "${_GH_FETCH_TOKEN}" ]] || die "no token entered"
  fi
}
unset GH_TOKEN GITHUB_TOKEN  # never inherited by the dashboard server or its child processes

# --- 3. Data ----------------------------------------------------------------
if [[ "${FETCH}" -eq 1 || ! -d "${DATA_DIR}" || -z "$(ls -A "${DATA_DIR}" 2>/dev/null)" ]]; then
  if [[ "${NO_GITHUB}" -eq 1 ]]; then
    echo "==> No data in ${DATA_DIR}; GitHub access is off (--no-github), so nothing is downloaded"
  elif [[ "${SETUP_ONLY}" -eq 1 && "${FETCH}" -eq 0 ]]; then
    echo "==> No data in ${DATA_DIR} (run with --fetch to download it)"
  else
    echo "==> Fetching the latest workflow artifacts and drift issues from GitHub"
    ask_github_token
    printf '%s\n' "${_GH_FETCH_TOKEN}" | "${PY}" scripts/fetch_dashboard_data.py --token-stdin \
      --repository "${REPOSITORY}" --data-dir "${DATA_DIR}" \
      || echo "WARNING: the fetch reported a problem (see the line above); continuing with the data present."
  fi
fi
if [[ "${ENABLE_GITHUB_FETCH}" -eq 1 ]]; then
  echo "==> Enabling \"Check GitHub for new runs\" in the dashboard"
  ask_github_token
else
  _GH_FETCH_TOKEN=""
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
GITHUB_ARGS=()
if [[ "${NO_GITHUB}" -eq 1 ]]; then
  GITHUB_ARGS=(--no-github)
  echo "==> GitHub access: off (--no-github)"
fi
if [[ "${SETUP_ONLY}" -eq 1 ]]; then
  if [[ -n "${_GH_FETCH_TOKEN}" ]]; then
    echo "==> Ready: ${VENV}/bin/dashboard-api --port ${PORT} --github-token-fd 3  (${URL}; Check GitHub enabled)"
  else
    echo "==> Ready: ${VENV}/bin/dashboard-api --port ${PORT}${GITHUB_ARGS[*]:+ ${GITHUB_ARGS[*]}}  (${URL})"
  fi
  exit 0
fi
if "${PY}" -c "import socket, sys; s = socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1', ${PORT})) == 0 else 1)"; then
  die "port ${PORT} is already in use (another dashboard running?); use --port N"
fi
echo "==> Dashboard: ${URL}  (sign in with your token; Ctrl+C stops it)"
if [[ "${OPEN_BROWSER}" -eq 1 ]] && command -v open >/dev/null 2>&1; then
  ( sleep 2; open "${URL}" ) &
fi
if [[ -n "${_GH_FETCH_TOKEN}" ]]; then
  echo "==> Check GitHub for new runs: enabled (the token stays in the dashboard's memory only)"
  # printf is a shell builtin: the token is written into the pipe without appearing in any process's arguments.
  exec "${VENV}/bin/dashboard-api" --port "${PORT}" --github-token-fd 3 3< <(printf '%s\n' "${_GH_FETCH_TOKEN}")
fi
exec "${VENV}/bin/dashboard-api" --port "${PORT}" ${GITHUB_ARGS[@]+"${GITHUB_ARGS[@]}"}
