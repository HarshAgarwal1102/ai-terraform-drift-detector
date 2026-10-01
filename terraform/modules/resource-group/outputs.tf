output "resource_groups" {
  description = "Map of created resource groups keyed by the logical identifier."
  value = {
    for key, rg in azurerm_resource_group.this : key => {
      name     = rg.name
      id       = rg.id
      location = rg.location
    }
  }
}
