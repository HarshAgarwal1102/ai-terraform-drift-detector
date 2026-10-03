# -----------------------------------------------
# Dev Environment Variables
# -----------------------------------------------
# The dev environment manages the Resource Group module
# (aitdd-dev-main-rg) and the network module (VNet,
# Subnet, NSG) placed inside that group.
# -----------------------------------------------

# --- Global Settings ---

variable "project_name" {
  description = "Short project identifier used in resource naming."
  type        = string
  default     = "aitdd"

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.project_name))
    error_message = "project_name must contain only lowercase letters, numbers, and hyphens."
  }
}

variable "environment" {
  description = "Deployment environment (e.g. dev, staging, prod)."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "common_tags" {
  description = "Tags applied to every resource via modules."
  type        = map(string)
  default = {
    environment = "dev"
    project     = "ai-terraform-drift-detector"
    managed_by  = "terraform"
  }
}

# --- Resource Groups ---

variable "resource_groups" {
  description = "Map of resource groups to create (passed to the resource-group module)."
  type = map(object({
    name       = string
    location   = string
    extra_tags = optional(map(string), {})
  }))
  default = {}
}

# --- Networking ---

variable "virtual_networks" {
  description = <<-EOT
    Map of virtual networks to create (passed to the network module).
    resource_group_key must match a key in resource_groups; the network uses
    that group's name and location.
  EOT
  type = map(object({
    name               = string
    resource_group_key = string
    address_space      = list(string)
    subnets = optional(map(object({
      name                            = string
      address_prefixes                = list(string)
      network_security_group_key      = optional(string)
      default_outbound_access_enabled = optional(bool, false)
    })), {})
    network_security_groups = optional(map(object({
      name = string
    })), {})
    extra_tags = optional(map(string), {})
  }))
  default = {}
}
