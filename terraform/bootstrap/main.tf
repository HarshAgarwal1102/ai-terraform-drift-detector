# -----------------------------------------------
# Terraform Remote State Bootstrap
# -----------------------------------------------
# Creates the Azure Storage Account and Blob Container
# required to store Terraform state files remotely.
#
# IMPORTANT: This bootstrap configuration uses LOCAL state
# so it does not depend on the remote state it creates.
# -----------------------------------------------

resource "azurerm_resource_group" "tfstate" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

resource "azurerm_storage_account" "tfstate" {
  name                     = var.storage_account_name
  resource_group_name      = azurerm_resource_group.tfstate.name
  location                 = azurerm_resource_group.tfstate.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  # Security Hardening
  https_traffic_only_enabled      = true
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  public_network_access           = "Enabled"
  shared_access_key_enabled       = true

  blob_properties {
    versioning_enabled = true

    container_delete_retention_policy {
      days = 7
    }

    delete_retention_policy {
      days = 7
    }
  }

  tags = var.tags

  # Holds the Terraform remote state: protected from accidental destruction.
  # Destroying it on purpose requires a reviewed change removing this first.
  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_storage_container" "tfstate" {
  name                  = var.container_name
  storage_account_id    = azurerm_storage_account.tfstate.id
  container_access_type = "private"

  # Holds the Terraform remote state: protected from accidental destruction.
  # Destroying it on purpose requires a reviewed change removing this first.
  lifecycle {
    prevent_destroy = true
  }
}
