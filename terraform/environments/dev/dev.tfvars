# ============================================================
# Dev Environment — Resource Definitions (Phase 1 Minimal Foundation)
# ============================================================
# Minimal resource footprint focused on Azure Resource Group
# to establish a clean baseline for Terraform state management
# and deterministic drift detection.
# ============================================================

# --- Global Settings ---

project_name = "aitdd"
environment  = "dev"
location     = "Central India"

common_tags = {
  environment = "dev"
  project     = "ai-terraform-drift-detector"
  managed_by  = "terraform"
}

# --- Resource Groups (Active Minimal Foundation) ---

resource_groups = {
  main = {
    name     = "main"
    location = "Central India"
  }
}

