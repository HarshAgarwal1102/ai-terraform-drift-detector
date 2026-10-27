# -----------------------------------------------
# Terraform Remote State Backend Configuration
# -----------------------------------------------
# Stores Terraform state in the Azure Storage Account created by bootstrap, in the
# same Azure account (subscription) as the resources it describes.
#
# Partial configuration (docs/azure-account-switching.md): the location is NOT in this
# file, because it changes with every Azure account. It is supplied at init time:
#   - GitHub Actions: scripts/resolve_backend_config.sh writes it from the repository
#     variables TFSTATE_RESOURCE_GROUP / TFSTATE_STORAGE_ACCOUNT / TFSTATE_CONTAINER /
#     TFSTATE_KEY after proving the storage account belongs to the signed-in
#     subscription; init then runs with -reconfigure -backend-config=<that file>.
#   - Local: terraform init -reconfigure -backend-config=<your backend.hcl>
#     (for example the one scripts/onboard_azure_account.sh writes under .artifacts/).
# In a fresh folder an init without these values fails. An already initialized folder
# (.terraform/) KEEPS the backend of its last init, possibly an earlier account's, and a
# plain `terraform init` silently reuses it. So always pass this account's settings with
# -reconfigure -backend-config=<file> (the plan scripts always add -reconfigure). Never use
# -migrate-state when switching accounts, even when Terraform suggests it.
#
# Authentication:
#   - Local dev: Uses Azure CLI authentication (`az login`).
#   - GitHub Actions: Uses OIDC / Workload Identity via Azure Federated Credentials.
#
# No secrets or account keys are stored in configuration files.
# -----------------------------------------------

terraform {
  backend "azurerm" {}
}
