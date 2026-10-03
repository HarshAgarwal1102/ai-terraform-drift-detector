variable "resource_name_prefix" {
  description = "Prefix prepended to every resource name (e.g. 'aitdd-dev')."
  type        = string

  validation {
    condition     = length(var.resource_name_prefix) > 0
    error_message = "resource_name_prefix must not be empty."
  }
}

variable "name" {
  description = "Logical network name; used in every resource name (e.g. 'main' -> 'aitdd-dev-main-vnet')."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.name))
    error_message = "name must contain only lowercase letters, numbers, and hyphens."
  }
}

variable "resource_group_name" {
  description = "Name of the existing parent resource group."
  type        = string
}

variable "location" {
  description = "Azure region for the network resources (normally the parent resource group's location)."
  type        = string
}

variable "address_space" {
  description = "Address space (CIDR blocks) of the virtual network."
  type        = list(string)

  validation {
    condition     = length(var.address_space) > 0 && alltrue([for cidr in var.address_space : can(cidrhost(cidr, 0))])
    error_message = "address_space must contain at least one valid CIDR block."
  }
}

variable "subnets" {
  description = <<-EOT
    Map of subnets to create in the virtual network.
    Key   = logical identifier used in for_each (e.g. "app").
    Value = name suffix, address prefixes, optional NSG key (from
            network_security_groups) and default outbound access flag.
  EOT
  type = map(object({
    name                            = string
    address_prefixes                = list(string)
    network_security_group_key      = optional(string)
    default_outbound_access_enabled = optional(bool, false)
  }))
  default = {}

  validation {
    condition = alltrue([
      for subnet in values(var.subnets) :
      length(subnet.address_prefixes) > 0 && alltrue([for cidr in subnet.address_prefixes : can(cidrhost(cidr, 0))])
    ])
    error_message = "Every subnet must have at least one valid CIDR address prefix."
  }
}

variable "network_security_groups" {
  description = <<-EOT
    Map of Network Security Groups to create.
    Key   = logical identifier referenced by subnets[*].network_security_group_key.
    Value = object with the name suffix.
  EOT
  type = map(object({
    name = string
  }))
  default = {}
}

variable "common_tags" {
  description = "Tags applied to every network resource that supports tags."
  type        = map(string)
  default     = {}
}

variable "extra_tags" {
  description = "Additional tags for this network's resources (merged over common_tags)."
  type        = map(string)
  default     = {}
}

variable "ci_proof_unused" {
  description = "Task 9.1 CI proof only: deliberately unused (never merged)."
  type        = string
  default     = "ci-proof"
}
