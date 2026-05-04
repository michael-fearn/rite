# OpenTofu VM Scaffold

Fortress keeps one root OpenTofu module under `tofu/`. That root module is the future fleet state boundary for VM provisioning. Inventory YAML remains the source of truth: `tofu/main.tf` decodes `inventory/vms/*.yaml`, while `inventory/hosts/*.yaml` drives generated Host provider coverage.

`just vm-up <vm>` is the operator surface for VM bring-up. It delegates to `scripts/vm-up <vm>`, which validates the VM, runs Prepare, shows a selected-VM plan through `scripts/tofu-wrap plan -var selected_vm=<vm>`, requires the operator to type `apply <vm>`, then runs `scripts/tofu-wrap apply -var selected_vm=<vm> -auto-approve` and Configure. The tofu wrapper remains available for direct debugging. It decrypts each Host's current `pve_tokens.tofu.value` from its Host Sibling SOPS File into an ephemeral `TF_VAR_pve_token_<host>` environment variable, regenerates the ignored HCL, and invokes `tofu` from the `tofu/` working directory. Direct `tofu` invocation is unsupported because Tofu must never read SOPS.

Run `scripts/tofu-generate` after changing Host inventory. The command writes ignored build output:

- `tofu/generated-providers.tf` contains one literal `provider "proxmox"` alias per Host and one sensitive `pve_token_<host>` variable per Host.
- `tofu/generated-vm-partitions.tf` contains one literal per-Host VM partition module, filtering decoded VMs by `selected_vm` and `placement.host`.

The generated files are not committed. They are reproducible from Inventory and are ignored alongside `.terraform/`, lock files, and local state.

OpenTofu provider aliases must be literal at configuration load time. Fortress therefore does not use dynamic provider indexing such as `proxmox[each.value.host]`; that shape cannot select a provider alias from VM data. Instead, generated static partition blocks bind each Host partition to a literal provider address like `proxmox.wintermute`.

The current `tofu/modules/vm-partition` module creates Proxmox VM resources from declared VM YAML. It clones the declared Template, reads hardware, disk, network, placement, and cloud-init fields from Inventory, uploads per-VM cloud-init userdata, and passes the plaintext VM SSH public key written by Prepare. If that public key is missing, the plan fails with an instruction to run Prepare first.

Use `-var selected_vm=<vm>` for early VM plans and applies so unrelated VMs in the fleet state root are not planned. Omitting `selected_vm` leaves the module shaped for whole-fleet reconciliation later, still with one root module and one local fleet state file.
