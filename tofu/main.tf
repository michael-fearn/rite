terraform {
  required_version = ">= 1.8.0"

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.105"
    }
  }
}

variable "selected_vm" {
  type        = string
  default     = null
  description = "Optional VM name to plan or apply while preserving the single fleet state root."
}

locals {
  globals = yamldecode(file("../inventory/group_vars/all.yaml"))
  vm_files = fileset("../inventory/vms", "*.yaml")
  vms = {
    for path in local.vm_files :
    trimsuffix(basename(path), ".yaml") => yamldecode(file("../inventory/vms/${path}"))
    if !startswith(basename(path), "_") && !endswith(basename(path), ".sops.yaml")
  }
  template_files = fileset("../inventory/templates", "*.yaml")
  templates = tomap({
    for path in local.template_files :
    trimsuffix(basename(path), ".yaml") => yamldecode(file("../inventory/templates/${path}"))
    if !startswith(basename(path), "_")
  })
}
