terraform {
  required_providers {
    proxmox = {
      source = "bpg/proxmox"
    }
  }
}

variable "host_name" {
  type = string
}

variable "vms" {
  type = map(any)
}

locals {
  vm_names = sort(keys(var.vms))
}

output "vm_names" {
  value = local.vm_names
}
