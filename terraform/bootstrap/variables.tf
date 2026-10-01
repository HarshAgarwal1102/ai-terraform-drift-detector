# -----------------------------------------------
# Terraform Bootstrap - Variable Definitions
# -----------------------------------------------

variable "resource_group_name" {
  description = "Name of the resource group for Terraform remote state."
  type        = string
  default     = "aitdd-tfstate-rg"
}

variable "location" {
  description = "Azure region for the remote state storage account."
  type        = string
  default     = "Central India"
}

variable "storage_account_name" {
  description = "Name of the storage account for Terraform remote state (3-24 lowercase alphanumeric, globally unique)."
  type        = string
  default     = "aitddtfstatesa001"
}

variable "container_name" {
  description = "Name of the blob container for Terraform remote state files."
  type        = string
  default     = "tfstate"
}

variable "tags" {
  description = "Tags applied to all bootstrap resources."
  type        = map(string)
  default = {
    project     = "ai-terraform-drift-detector"
    environment = "bootstrap"
    managed_by  = "terraform"
    purpose     = "terraform-remote-state"
  }
}
