# -----------------------------------------------
# Terraform Remote State Backend Configuration
# -----------------------------------------------
# Stores Terraform state in the Azure Storage Account created by bootstrap.
#
# Authentication:
#   - Local dev: Uses Azure CLI authentication (`az login`).
#   - GitHub Actions: Uses OIDC / Workload Identity via Azure Federated Credentials.
#
# No secrets or account keys are stored in configuration files.
# -----------------------------------------------

terraform {
  backend "azurerm" {
    resource_group_name  = "aitdd-tfstate-rg"
    storage_account_name = "aitddtfstatesa001"
    container_name       = "tfstate"
    key                  = "dev.tfstate"
  }
}
