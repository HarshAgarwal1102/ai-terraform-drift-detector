# ============================================================
# Dev Environment — Resource Definitions
# ============================================================
# Small resource footprint for deterministic drift detection:
# the Phase 1 Resource Group plus one VNet, Subnet and NSG
# (no compute, no storage, no Key Vault).
# ============================================================

# --- Global Settings ---

project_name = "aitdd"
environment  = "dev"

common_tags = {
  environment = "dev"
  project     = "ai-terraform-drift-detector"
  managed_by  = "terraform"
}

# --- Resource Groups (Phase 1 Foundation) ---

resource_groups = {
  main = {
    name     = "main"
    location = "Central India"
  }
}

# --- Networking ---
# One VNet in the main resource group with a single subnet protected by an NSG.
# The NSG has no custom rules (Azure default rules only); no compute is attached.

virtual_networks = {
  main = {
    name               = "main"
    resource_group_key = "main"
    address_space      = ["10.10.0.0/16"]

    network_security_groups = {
      app = {
        name = "app"
      }
    }

    subnets = {
      app = {
        name                       = "app"
        address_prefixes           = ["10.10.1.0/24"]
        network_security_group_key = "app"
      }
    }
  }
}
