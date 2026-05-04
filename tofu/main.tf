terraform {
  required_version = ">= 1.8.0"

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.105"
    }
  }
}

locals {
  vm_files = fileset("../inventory/vms", "*.yaml")
  vms = {
    for path in local.vm_files :
    trimsuffix(basename(path), ".yaml") => yamldecode(file("../inventory/vms/${path}"))
    if !startswith(basename(path), "_")
  }
}
