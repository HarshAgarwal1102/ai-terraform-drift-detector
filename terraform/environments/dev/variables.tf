# -----------------------------------------------
# Dev Environment Variables
# -----------------------------------------------
# Phase 1 Minimal Foundation:
# The active dev environment manages ONLY the Resource
# Group module (aitdd-dev-main-rg).
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

variable "location" {
  description = "Default Azure region for resources."
  type        = string
  default     = "Central India"
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

