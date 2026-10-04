#!/usr/bin/env bash
# -----------------------------------------------
# scripts/run_trufflehog.sh
# -----------------------------------------------
# Task 9.3: secret scan of the repository's Git history with TruffleHog.
# This is NOT drift detection: a finding is a secret-scan failure, never a
# drift result.
#
# The one command used locally and in CI (.github/workflows/security-scan.yml).
# No Azure authentication, no token. Requires TruffleHog 3.97.9, git and jq on
# PATH (CI installs the SHA-256-verified release binary first) and the full
# history (CI checks out with fetch-depth: 0).
#
# Policy (PROJECT_PLAN.md Task 9.3):
#   - full history of every ref (`trufflehog git file://<repo>`), never a range;
#   - --no-update (TruffleHog would otherwise update itself) and
#     --no-verification (no candidate is sent to a provider API);
#   - every result blocks: TruffleHog exits 183 with --fail; that exit code, or
#     its error exit code, is passed through unchanged;
#   - TruffleHog's JSON holds raw secret values, so it is written to a private
#     temporary file and only detector, verification status, file, line and
#     commit are printed;
#   - inline ignore annotations are not allowed anywhere in files or history.
# -----------------------------------------------

set -euo pipefail

# Builtins only until jq is confirmed (the prerequisite check comes first).
SCRIPT_DIR="$(cd "${BASH_SOURCE[0]%/*}" && pwd -P)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd -P)"
TRUFFLEHOG_VERSION="3.97.9"
# Built from two parts so this file never contains the annotation itself.
IGNORE_ANNOTATION="trufflehog"":ignore"

if ! command -v jq >/dev/null 2>&1; then
  echo "error: jq is required to evaluate the TruffleHog JSON results and was not found on PATH." >&2
  exit 1
fi
for tool in git trufflehog; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "error: ${tool} was not found on PATH (TruffleHog ${TRUFFLEHOG_VERSION} is required)." >&2
    exit 1
  fi
done

echo "==> TruffleHog: secret scan of the Git history (not drift detection)"
actual_version="$(trufflehog --no-update --version 2>&1)"
echo "TruffleHog version: ${actual_version}"
if [ "${actual_version}" != "trufflehog ${TRUFFLEHOG_VERSION}" ]; then
  echo "error: TruffleHog ${TRUFFLEHOG_VERSION} is required (got '${actual_version}')." >&2
  exit 1
fi

cd "${ROOT_DIR}"
if git grep -q -I -F "${IGNORE_ANNOTATION}" -- .; then
  echo "error: inline TruffleHog ignore annotations are not allowed in the repository files." >&2
  exit 1
fi
if [ -n "$(git log --all --full-history --format=%h -G "${IGNORE_ANNOTATION}")" ]; then
  echo "error: inline TruffleHog ignore annotations are not allowed anywhere in the Git history." >&2
  exit 1
fi

temp_base="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
work_dir="$(mktemp -d "${temp_base%/}/trufflehog.XXXXXX")"
work_dir="$(cd "${work_dir}" && pwd -P)"
trap 'rm -rf "${work_dir}"' EXIT
case "${work_dir}/" in
  "${ROOT_DIR}/"*)
    echo "error: the TruffleHog work directory must be outside the repository (got ${work_dir})." >&2
    exit 1
    ;;
esac
results="${work_dir}/results.jsonl"
scan_log="${work_dir}/trufflehog.log"

echo "==> Scanning the full history of file://${ROOT_DIR}"
scan_rc=0
trufflehog git "file://${ROOT_DIR}" \
  --no-update \
  --no-verification \
  --json \
  --fail \
  >"${results}" 2>"${scan_log}" || scan_rc=$?

# TruffleHog's own log: level, message and error only.
jq -R -r 'fromjson? // {msg: .} | select(type == "object")
  | "trufflehog: \(.level // "-") \(.msg // "-")\(if .error then " error=\(.error)" else "" end)"' "${scan_log}"

if ! jq -e -s 'all(.[]; type == "object")' "${results}" >/dev/null 2>&1; then
  echo "error: unexpected TruffleHog output; the results cannot be evaluated safely." >&2
  exit 1
fi
result_count="$(jq -s '[.[] | select(has("DetectorName"))] | length' "${results}")"
# Metadata only: never Raw, RawV2, Redacted, ExtraData, StructuredData or author email.
jq -r 'select(has("DetectorName"))
  | (.SourceMetadata.Data.Git // {}) as $git
  | "FINDING  detector=\(.DetectorName)  verified=\(.Verified)  file=\($git.file // "?")  line=\($git.line // "?")  commit=\(($git.commit // "?")[0:12])"' "${results}"

case "${scan_rc}" in
  0)
    if [ "${result_count}" -gt 0 ]; then
      echo "error: TruffleHog exited 0 but reported ${result_count} result(s)." >&2
      exit 1
    fi
    echo "==> TruffleHog passed: no secrets found in the Git history ✓"
    ;;
  183)
    if [ "${result_count}" -eq 0 ]; then
      echo "error: TruffleHog reported findings (exit 183) but no result could be read." >&2
    else
      echo "error: ${result_count} secret finding(s) in the Git history (TruffleHog exit 183). Rotate any real secret first; see PROJECT_PLAN.md Task 9.3." >&2
    fi
    exit 183
    ;;
  *)
    echo "error: TruffleHog failed to run (exit ${scan_rc}); this is a scanner error, not a finding." >&2
    exit "${scan_rc}"
    ;;
esac
