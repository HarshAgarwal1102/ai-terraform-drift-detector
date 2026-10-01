# -----------------------------------------------
# Resource Group Module
# -----------------------------------------------
# Creates Azure Resource Groups using for_each so
# that new groups can be added purely via tfvars.
# -----------------------------------------------

resource "azurerm_resource_group" "this" {
  for_each = var.resource_groups

  name     = "${var.resource_name_prefix}-${each.value.name}-rg"
  location = each.value.location
  tags     = merge(var.common_tags, each.value.extra_tags)
}
