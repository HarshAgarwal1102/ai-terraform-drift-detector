# -----------------------------------------------
# AzureRM Provider Configuration
# -----------------------------------------------
# Authentication: uses Azure CLI credentials by default.
#   az login
# No credentials are hardcoded.
#
# AzureRM v5.x changes:
#   - resource_provider_registrations defaults to "none"
#   - we explicitly register only the providers we need
#   - features {} block is still required (even if empty)
# -----------------------------------------------

provider "azurerm" {
  features {}
}
