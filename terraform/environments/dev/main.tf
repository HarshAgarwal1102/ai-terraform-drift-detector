# -----------------------------------------------
# Dev Environment — Module Composition
# -----------------------------------------------
# Resource Group (Phase 1 foundation) plus the
# networking expansion: VNet, Subnet, NSG and the
# Subnet-NSG association, all inside that group.
# -----------------------------------------------

locals {
  resource_name_prefix = "${var.project_name}-${var.environment}"
}

# -----------------------------------------------
# 1. Resource Groups (Phase 1 Foundation)
# -----------------------------------------------

module "resource_group" {
  source = "../../modules/resource-group"

  resource_name_prefix = local.resource_name_prefix
  resource_groups      = var.resource_groups
  common_tags          = var.common_tags
}

# -----------------------------------------------
# 2. Networking (VNet, Subnets, NSGs)
# -----------------------------------------------
# Each network lives in an existing resource group (looked up by key) and
# inherits that group's location, so the resource group stays the parent.

module "network" {
  source   = "../../modules/network"
  for_each = var.virtual_networks

  resource_name_prefix    = local.resource_name_prefix
  name                    = each.value.name
  resource_group_name     = module.resource_group.resource_groups[each.value.resource_group_key].name
  location                = module.resource_group.resource_groups[each.value.resource_group_key].location
  address_space           = each.value.address_space
  subnets                 = each.value.subnets
  network_security_groups = each.value.network_security_groups
  common_tags             = var.common_tags
  extra_tags              = each.value.extra_tags
}
