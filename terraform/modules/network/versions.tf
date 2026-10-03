# -----------------------------------------------
# Network Module - Version Requirements
# -----------------------------------------------
# Same constraints as the root configurations, so the
# committed provider lock (azurerm 5.7.0) still applies.
# -----------------------------------------------

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.0"
    }
  }
}
