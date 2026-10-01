variable "resource_groups" {
  description = <<-EOT
    Map of resource groups to create.
    Key   = logical identifier used in for_each (e.g. "main").
    Value = object with name suffix, location, and optional extra tags.
  EOT
  type = map(object({
    name       = string
    location   = string
    extra_tags = optional(map(string), {})
  }))

  validation {
    condition     = length(var.resource_groups) > 0
    error_message = "At least one resource group must be defined."
  }
}

variable "resource_name_prefix" {
  description = "Prefix prepended to every resource group name (e.g. 'aitdd-dev')."
  type        = string

  validation {
    condition     = length(var.resource_name_prefix) > 0
    error_message = "resource_name_prefix must not be empty."
  }
}

variable "common_tags" {
  description = "Tags applied to every resource group (merged with per-RG extra_tags)."
  type        = map(string)
  default     = {}
}
