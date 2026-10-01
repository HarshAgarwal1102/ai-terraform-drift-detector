# -----------------------------------------------
# Dev Environment Outputs
# -----------------------------------------------
# Phase 1 Minimal Foundation:
# Exposes outputs from the active Resource Group module.
# -----------------------------------------------

# --- Resource Groups (Active Minimal Foundation) ---

output "resource_groups" {
  description = "All created resource groups."
  value       = module.resource_group.resource_groups
}

