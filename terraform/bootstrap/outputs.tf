# -----------------------------------------------
# Terraform Bootstrap - Outputs
# -----------------------------------------------

output "resource_group_name" {
  description = "The name of the Resource Group containing the Terraform remote state storage."
  value       = azurerm_resource_group.tfstate.name
}

output "storage_account_name" {
  description = "The name of the Azure Storage Account used for Terraform remote state."
  value       = azurerm_storage_account.tfstate.name
}

output "container_name" {
  description = "The name of the Blob Container storing Terraform state files."
  value       = azurerm_storage_container.tfstate.name
}

output "backend_config_instructions" {
  description = "CLI configuration parameters for initializing remote backend in environment modules."
  value       = <<EOT
The dev backend is a partial configuration (docs/azure-account-switching.md). Initialize it
against THIS account's storage with (the key names the storage account; only the first
account's aitddtfstatesa001 keeps dev.tfstate):

terraform -chdir=terraform/environments/dev init -reconfigure \
  -backend-config="resource_group_name=${azurerm_resource_group.tfstate.name}" \
  -backend-config="storage_account_name=${azurerm_storage_account.tfstate.name}" \
  -backend-config="container_name=${azurerm_storage_container.tfstate.name}" \
  -backend-config="key=${azurerm_storage_account.tfstate.name == "aitddtfstatesa001" ? "dev.tfstate" : "dev-${azurerm_storage_account.tfstate.name}.tfstate"}"

Never use -migrate-state when switching accounts: each account starts from its own empty state.
EOT
}
