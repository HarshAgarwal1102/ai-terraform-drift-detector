# -----------------------------------------------
# TFLint Configuration (Task 9.1)
# -----------------------------------------------
# Static Terraform linting only. A TFLint finding is a lint failure,
# never a drift result (drift detection is .github/workflows/drift-detection.yml).
#
# Run through scripts/run_tflint.sh (locally and in CI), which passes this
# file by absolute path: under --recursive a relative --config is resolved
# per module directory.
#
# Versions are pinned exactly. Upgrades are one reviewed change that updates
# this file, .github/workflows/security-scan.yml and README.md together.
# No varfile: terraform/bootstrap and the modules have no dev.tfvars.
# -----------------------------------------------

tflint {
  required_version = "= 0.64.0"
}

config {
  call_module_type = "local"
}

plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

# Generated from the AzureRM 4.65.0 schema (no released AzureRM v5 build yet);
# the rules removed by the upstream v5 work cover no resource used here.
plugin "azurerm" {
  enabled = true
  version = "0.32.0"
  source  = "github.com/terraform-linters/tflint-ruleset-azurerm"
}
