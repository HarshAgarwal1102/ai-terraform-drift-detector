# -----------------------------------------------
# Dev Environment Outputs
# -----------------------------------------------
# Exposes outputs from the Resource Group and network modules.
# -----------------------------------------------

# --- Resource Groups (Phase 1 Foundation) ---

output "resource_groups" {
  description = "All created resource groups."
  value       = module.resource_group.resource_groups
}

# --- Networking ---

output "virtual_networks" {
  description = "All created virtual networks with their subnets and network security groups."
  value = {
    for key, network in module.network : key => {
      virtual_network         = network.virtual_network
      subnets                 = network.subnets
      network_security_groups = network.network_security_groups
    }
  }
}
