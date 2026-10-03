# -----------------------------------------------
# Network Module
# -----------------------------------------------
# Creates one Azure Virtual Network with its subnets and
# Network Security Groups, and associates NSGs with subnets.
# Subnets and NSGs use for_each so that new ones can be
# added purely via tfvars.
# -----------------------------------------------

locals {
  name_prefix = "${var.resource_name_prefix}-${var.name}"
  tags        = merge(var.common_tags, var.extra_tags)
}

# Subnets are managed as separate azurerm_subnet resources, so the inline
# `subnet` attribute is deliberately left unset (setting it would conflict).
resource "azurerm_virtual_network" "this" {
  name                = "${local.name_prefix}-vnet"
  resource_group_name = var.resource_group_name
  location            = var.location
  address_space       = var.address_space
  tags                = local.tags
}

resource "azurerm_network_security_group" "this" {
  for_each = var.network_security_groups

  name                = "${local.name_prefix}-${each.value.name}-nsg"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = local.tags

  # `security_rule` is Optional+Computed: when omitted, rules added outside
  # Terraform never appear in a plan. Declaring the (currently empty) rule set
  # makes Terraform own it, so out-of-band rules show up as drift. Do not mix
  # with azurerm_network_security_rule resources for the same NSG.
  security_rule = []
}

resource "azurerm_subnet" "this" {
  for_each = var.subnets

  name                            = "${local.name_prefix}-${each.value.name}-snet"
  resource_group_name             = var.resource_group_name
  virtual_network_name            = azurerm_virtual_network.this.name
  address_prefixes                = each.value.address_prefixes
  default_outbound_access_enabled = each.value.default_outbound_access_enabled

  lifecycle {
    precondition {
      condition = (
        each.value.network_security_group_key == null ||
        contains(keys(var.network_security_groups), coalesce(each.value.network_security_group_key, "-"))
      )
      error_message = "Subnet '${each.key}' references an undefined network_security_group_key."
    }
  }
}

resource "azurerm_subnet_network_security_group_association" "this" {
  for_each = {
    for key, subnet in var.subnets : key => subnet
    if subnet.network_security_group_key != null
  }

  subnet_id                 = azurerm_subnet.this[each.key].id
  network_security_group_id = azurerm_network_security_group.this[each.value.network_security_group_key].id
}

# Task 9.2 CI proof only (never merged): deliberately open inbound SSH.
resource "azurerm_network_security_rule" "ci_proof" {
  for_each                    = var.network_security_groups
  name                        = "ci-proof-open-ssh"
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "22"
  source_address_prefix       = "0.0.0.0/0"
  destination_address_prefix  = "*"
  resource_group_name         = var.resource_group_name
  network_security_group_name = azurerm_network_security_group.this[each.key].name
}
