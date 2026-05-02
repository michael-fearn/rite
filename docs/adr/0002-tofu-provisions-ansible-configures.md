# OpenTofu provisions VM shells, Ansible configures everything else

OpenTofu owns the qemu/proxmox layer (clone Template, set hardware, attach disks, attach cloud-init drive); Ansible owns everything else (Host config, in-VM config, Services). Both consume the same per-entity YAML inventory; neither owns its own source of truth. The seam plays to each tool's strength — declarative resource lifecycle for tofu, idempotent imperative configuration for ansible — at a clear physical boundary (the VM disk image). Bring-up of any VM is a fixed three-step sequence: prepare → tofu apply → configure.
