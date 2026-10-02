output "virtual_network" {
  description = "The created virtual network."
  value = {
    name          = azurerm_virtual_network.this.name
    id            = azurerm_virtual_network.this.id
    address_space = azurerm_virtual_network.this.address_space
  }
}

output "subnets" {
  description = "Map of created subnets keyed by the logical identifier."
  value = {
    for key, subnet in azurerm_subnet.this : key => {
      name             = subnet.name
      id               = subnet.id
      address_prefixes = subnet.address_prefixes
    }
  }
}

output "network_security_groups" {
  description = "Map of created network security groups keyed by the logical identifier."
  value = {
    for key, nsg in azurerm_network_security_group.this : key => {
      name = nsg.name
      id   = nsg.id
    }
  }
}
