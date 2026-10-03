#!/usr/bin/env bash
# -----------------------------------------------
# scripts/run_trivy_config.sh
# -----------------------------------------------
# Task 9.2: static Terraform security scan with Trivy (`trivy config`,
# misconfiguration scanning only). This is NOT drift detection: a finding is a
# security-scan failure, never a drift result.
#
# The one command used locally and in CI (.github/workflows/security-scan.yml).
# No Azure authentication, no terraform init. Requires Trivy 0.75.0 and jq on
# PATH (CI installs the SHA-256-verified release binary first).
#
# Gate (PROJECT_PLAN.md Task 9.2):
#   - HIGH and CRITICAL findings fail, except the single finding that exactly
#     matches the active record in security/trivy-risk-acceptance.json
#     (ID, CauseMetadata.Resource and ArtifactName + "/" + Target);
#   - the record fails the run when it is missing, malformed, expired, stale
#     (no matching finding) or matches more than one finding;
#   - MEDIUM and LOW findings are printed and do not block.
# No .trivyignore, no Trivy ignore/suppression flags: Trivy reports every finding
# and only this gate classifies them.
# -----------------------------------------------

set -euo pipefail

# Builtins only until jq is confirmed (the prerequisite check comes first).
SCRIPT_DIR="$(cd "${BASH_SOURCE[0]%/*}" && pwd -P)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd -P)"
ACCEPTANCE="${ROOT_DIR}/security/trivy-risk-acceptance.json"
TRIVY_VERSION="0.75.0"

if ! command -v jq >/dev/null 2>&1; then
  echo "error: jq is required to evaluate the Trivy JSON report and was not found on PATH." >&2
  exit 1
fi
if ! command -v trivy >/dev/null 2>&1; then
  echo "error: trivy ${TRIVY_VERSION} was not found on PATH." >&2
  exit 1
fi

# Settings from the environment or a config file could change what Trivy reports.
for name in $(compgen -e -X '!TRIVY_*'); do
  unset "${name}"
done
for path in .trivyignore .trivyignore.yaml trivy.yaml; do
  if [ -e "${ROOT_DIR}/${path}" ]; then
    echo "error: ${path} is not allowed (no Trivy ignore or config files; see PROJECT_PLAN.md Task 9.2)." >&2
    exit 1
  fi
done
if grep -rIn --include='*.tf' --include='*.tfvars' -i 'trivy:ignore' "${ROOT_DIR}/terraform" >&2; then
  echo "error: inline trivy:ignore annotations are not allowed." >&2
  exit 1
fi

echo "==> Trivy config: static security scan (not drift detection)"
actual_version="$(trivy --version --format json | jq -r '.Version // empty')"
echo "Trivy version: ${actual_version}"
if [ "${actual_version}" != "${TRIVY_VERSION}" ]; then
  echo "error: Trivy ${TRIVY_VERSION} is required (got '${actual_version}')." >&2
  exit 1
fi

# --- Risk-acceptance record ---------------------------------------------------
if [ ! -f "${ACCEPTANCE}" ]; then
  echo "error: risk-acceptance record not found: ${ACCEPTANCE}" >&2
  exit 1
fi
if ! jq -e '
  (keys == ["acceptances"]) and (.acceptances | type == "array" and length == 1)
  and (.acceptances[0] | type == "object"
       and (keys == (["expires", "file", "id", "justification", "reference", "resource", "scope"]))
       and all(.[]; type == "string" and length > 0)
       and (.expires | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$"))
       and ((.expires + "T00:00:00Z" | fromdateiso8601 | todate | .[0:10]) == .expires))
' "${ACCEPTANCE}" >/dev/null 2>&1; then
  echo "error: malformed risk-acceptance record ${ACCEPTANCE} (exactly one entry with id, resource, file, expires (YYYY-MM-DD), justification, scope, reference)." >&2
  exit 1
fi
record="$(jq -c '.acceptances[0]' "${ACCEPTANCE}")"
expires="$(jq -r '.expires' <<<"${record}")"
today="$(date -u +%Y-%m-%d)"
if [[ "${today}" > "${expires}" ]]; then
  echo "error: risk acceptance $(jq -r '.id' <<<"${record}") expired on ${expires}; review it through PROJECT_PLAN.md." >&2
  exit 1
fi

# --- Scans --------------------------------------------------------------------
# Run from the repository root with repo-relative roots, so ArtifactName is exactly
# the root path and ArtifactName + "/" + Target is the repo-relative file.
temp_base="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
work_dir="$(mktemp -d "${temp_base%/}/trivy-config.XXXXXX")"
work_dir="$(cd "${work_dir}" && pwd -P)"
trap 'rm -rf "${work_dir}"' EXIT
case "${work_dir}/" in
  "${ROOT_DIR}/"*)
    echo "error: the Trivy work directory must be outside the repository (got ${work_dir})." >&2
    exit 1
    ;;
esac

cd "${ROOT_DIR}"
scan() { # <root> [extra trivy args...]
  local root="$1"; shift
  local name="${root//\//_}"
  # Fresh, empty cache per scan: with --skip-check-update Trivy then uses the checks
  # embedded in the verified binary (it logs "Falling back to embedded checks").
  local cache_dir="${work_dir}/cache-${name}"
  mkdir "${cache_dir}"
  echo "==> Scanning ${root}"
  trivy config \
    --skip-check-update \
    --disable-telemetry \
    --skip-version-check \
    --misconfig-scanners terraform \
    --cache-dir "${cache_dir}" \
    --format json \
    --output "${work_dir}/${name}.json" \
    "$@" \
    "${root}"
  if ! jq -e --arg root "${root}" '
    .SchemaVersion == 2 and .ArtifactName == $root and (.Results | type == "array")
    and all(.Results[]; (.Target | type == "string")
      and all((.Misconfigurations // [])[];
        (.ID | type == "string" and length > 0)
        and (.Severity | IN("LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"))
        and (.Status | type == "string")
        and (.CauseMetadata.Resource | type == "string" and length > 0)))
  ' "${work_dir}/${name}.json" >/dev/null; then
    echo "error: unexpected Trivy JSON for ${root}; the gate cannot evaluate it safely." >&2
    exit 1
  fi
}
scan terraform/environments/dev --tf-vars terraform/environments/dev/dev.tfvars
scan terraform/bootstrap

# --- Gate ---------------------------------------------------------------------
findings="$(jq -s -c '[.[] | .ArtifactName as $artifact | .Results[] | .Target as $target
  | (.Misconfigurations // [])[] | select(.Status == "FAIL")
  | {id: .ID, severity: .Severity, resource: .CauseMetadata.Resource,
     file: ($artifact + "/" + $target), title: .Title}]' "${work_dir}"/*.json)"
evaluation="$(jq -c --argjson rec "${record}" '
  def accepted: .id == $rec.id and .resource == $rec.resource and .file == $rec.file;
  {
    matches: [.[] | select(accepted)],
    blocking: [.[] | select((.severity == "HIGH" or .severity == "CRITICAL") and (accepted | not))],
    reported: [.[] | select(.severity != "HIGH" and .severity != "CRITICAL" and (accepted | not))]
  }' <<<"${findings}")"

echo "==> Findings"
jq -r --argjson rec "${record}" '.matches[]
  | "ACCEPTED RISK  \(.severity)  \(.id)  \(.resource)  \(.file)  \(.title)",
    "  justification: \($rec.justification)", "  scope: \($rec.scope)", "  expires: \($rec.expires)"' <<<"${evaluation}"
jq -r '.reported[] | "REPORTED (non-blocking)  \(.severity)  \(.id)  \(.resource)  \(.file)  \(.title)"' <<<"${evaluation}"
jq -r '.blocking[] | "BLOCKING  \(.severity)  \(.id)  \(.resource)  \(.file)  \(.title)"' <<<"${evaluation}"

status=0
match_count="$(jq '.matches | length' <<<"${evaluation}")"
if [ "${match_count}" -eq 0 ]; then
  echo "error: stale risk acceptance: no finding matches $(jq -r '"\(.id) \(.resource) \(.file)"' <<<"${record}")." >&2
  status=1
elif [ "${match_count}" -gt 1 ]; then
  echo "error: the risk acceptance matches ${match_count} findings; it must match exactly one." >&2
  status=1
fi
blocking_count="$(jq '.blocking | length' <<<"${evaluation}")"
if [ "${blocking_count}" -gt 0 ]; then
  echo "error: ${blocking_count} HIGH/CRITICAL finding(s) not covered by the risk acceptance." >&2
  status=1
fi
if [ "${status}" -ne 0 ]; then
  exit 1
fi
echo "==> Trivy config passed: no unaccepted HIGH/CRITICAL findings ✓"
