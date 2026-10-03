#!/usr/bin/env bash
# -----------------------------------------------
# scripts/run_tflint.sh
# -----------------------------------------------
# Task 9.1: static Terraform linting with TFLint.
# This is NOT drift detection: a finding is a lint failure,
# never a drift result.
#
# The one command used locally and in CI
# (.github/workflows/security-scan.yml). No Azure
# authentication, no terraform init.
#
# Usage:
#   TFLINT_PLUGIN_DIR=<directory outside the repository> ./scripts/run_tflint.sh
#
# Any TFLint finding (warning or error) or TFLint failure
# makes this script exit non-zero with TFLint's own exit code.
# -----------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd -P)"
# Absolute path: under --recursive a relative --config is resolved per module directory.
CONFIG="${ROOT_DIR}/.tflint.hcl"
EXPECTED_AZURERM_RULESET="ruleset.azurerm (0.32.0)"

if [ ! -f "${CONFIG}" ]; then
  echo "error: TFLint config not found: ${CONFIG}" >&2
  exit 1
fi

# Plugins are installed outside the repository (never committed, never the
# repository's own .tflint.d), e.g. the session scratchpad locally and
# RUNNER_TEMP in CI.
if [ -z "${TFLINT_PLUGIN_DIR:-}" ]; then
  echo "error: TFLINT_PLUGIN_DIR must be set to an existing directory outside the repository." >&2
  exit 1
fi
if [ ! -d "${TFLINT_PLUGIN_DIR}" ]; then
  echo "error: TFLINT_PLUGIN_DIR is not an existing directory: ${TFLINT_PLUGIN_DIR}" >&2
  exit 1
fi
plugin_dir="$(cd "${TFLINT_PLUGIN_DIR}" && pwd -P)"
case "${plugin_dir}/" in
  "${ROOT_DIR}/"*)
    echo "error: TFLINT_PLUGIN_DIR must be outside the repository (got ${plugin_dir})." >&2
    exit 1
    ;;
esac
export TFLINT_PLUGIN_DIR="${plugin_dir}"

echo "==> TFLint: static Terraform lint (not drift detection)"

# Plugin download (pinned versions, signature verification at its default).
# GITHUB_TOKEN, when present, is used only here to avoid download rate limits
# and is removed before TFLint inspects any code.
echo "==> Installing pinned TFLint plugins..."
tflint --init --config "${CONFIG}"
unset GITHUB_TOKEN

echo "==> Verifying TFLint and plugin versions..."
version_output="$(tflint --version --config "${CONFIG}")"
printf '%s\n' "${version_output}"
if ! printf '%s\n' "${version_output}" | grep -Fq "${EXPECTED_AZURERM_RULESET}"; then
  echo "error: expected '${EXPECTED_AZURERM_RULESET}' to be loaded." >&2
  exit 1
fi

# Terraform code only: the scan never reaches other repository directories.
echo "==> Linting terraform/ recursively..."
cd "${ROOT_DIR}/terraform"
tflint --recursive --config "${CONFIG}" --format compact
echo "==> TFLint passed: no findings ✓"
