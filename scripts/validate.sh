#!/usr/bin/env bash
# -----------------------------------------------
# scripts/validate.sh
# -----------------------------------------------
# Runs local Terraform validation across bootstrap
# and environments (no Azure auth required).
# Safe to run in CI before plan/apply.
# -----------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/.."
BOOTSTRAP_DIR="${ROOT_DIR}/terraform/bootstrap"
DEV_DIR="${ROOT_DIR}/terraform/environments/dev"

echo "==> Checking Terraform format across codebase..."
terraform -chdir="${ROOT_DIR}" fmt -check -recursive

echo "==> Validating Bootstrap configuration..."
terraform -chdir="${BOOTSTRAP_DIR}" init -backend=false -input=false
terraform -chdir="${BOOTSTRAP_DIR}" validate

echo "==> Validating Dev environment configuration..."
terraform -chdir="${DEV_DIR}" init -backend=false -input=false
terraform -chdir="${DEV_DIR}" validate

echo "==> All local validations passed ✓"
