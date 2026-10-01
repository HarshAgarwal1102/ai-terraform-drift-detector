# -----------------------------------------------
# Dev Environment — Module Composition
# -----------------------------------------------
# Phase 1 Minimal Foundation:
# Focuses on Azure Resource Group as the primary
# Terraform-managed resource.
# -----------------------------------------------

locals {
  resource_name_prefix = "${var.project_name}-${var.environment}"
}

# -----------------------------------------------
# 1. Resource Groups (Active Minimal Foundation)
# -----------------------------------------------

module "resource_group" {
  source = "../../modules/resource-group"

  resource_name_prefix = local.resource_name_prefix
  resource_groups      = var.resource_groups
  common_tags          = var.common_tags
}

