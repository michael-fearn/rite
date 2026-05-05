# New VM

Use this runbook when adding a VM declared in Inventory and provisioned onto a Host.

## Declare the VM

Create `inventory/vms/<vm>.yaml`. The VM name is the filename stem and is the value passed to the lifecycle commands.

Required fields are defined by `inventory/vms/_schema.json`; at minimum the declaration needs a VMID, `placement.host`, a Template source, hardware, network, and cloud-init identity. Choose the Host intentionally. For a wintermute demo, set `placement.host: wintermute` and use a Template that already exists on that Host.

Prepare writes the VM SSH public key back into this same file. Leave the field absent before the first Prepare run unless you are intentionally preserving an already-generated key.

## Bring Up

Run:

```sh
just vm-up vm=<name>
```

The command is the operator path for the full VM lifecycle bring-up:

1. Prepare generates the per-VM SSH keypair. Prepare refuses to run when inventory/vms/<vm>.sops.yaml already exists, because that Sibling SOPS File means VM private key material has already been minted.
2. The VM public key is plaintext in inventory/vms/<vm>.yaml; the VM private key is encrypted in inventory/vms/<vm>.sops.yaml. Tofu reads the public key only. It never reads SOPS.
3. `scripts/tofu-wrap plan -var selected_vm=<name>` shows the selected-VM OpenTofu plan.
4. Review the plan. Type `apply <name>` only when the plan creates or updates the intended VM.
5. `scripts/tofu-wrap apply -var selected_vm=<name> -auto-approve` provisions the Proxmox VM.
6. Configure runs after apply. Configure waits for cloud-init to complete before finalizing the VM with Ansible, so it does not race first boot.

If the plan is surprising, deny the prompt and inspect Inventory before trying again.

## Destroy

Run:

```sh
just vm-destroy vm=<name>
```

Destroy validates that the VM is declared, then refuses while any Service Backend references the VM. Remove or move those Service Backend references in a separate reviewable change before destroying the VM.

The destroy command targets only the VM resource selected by `selected_vm`. It removes the provisioned Proxmox VM and, after a successful destroy, deletes inventory/vms/<vm>.sops.yaml so encrypted VM private key material does not linger for a VM that no longer exists. Missing VM Sibling SOPS Files are treated as already clean.

To also delete the VM yaml after successful destroy, run:

```sh
just vm-destroy vm=<name> delete_vm_yaml=true
```

That opt-in removes only inventory/vms/<vm>.yaml after the VM Sibling SOPS File has been deleted. It does not remove Service yamls or parent directories.

## AFK Agent Stop Points

An AFK agent must stop and alert the maintainer instead of guessing whenever the workflow needs:

- real Host access, including SSH or Proxmox access to wintermute;
- destructive approval, including accepting an OpenTofu apply or destroy plan;
- manual intervention, including console recovery, unexpected cloud-init failure, missing Templates, missing Host tokens, or any plan that does not match the requested VM.

When stopping, include the exact command that was running and the relevant output.

## Wintermute Demo Notes

For the acceptance demo, choose a throwaway VM name and declare it under `inventory/vms/<vm>.yaml` with `placement.host: wintermute`.

Provision:

```sh
just vm-up vm=<name>
```

Record the selected-VM plan summary and the final Configure result. If maintainer intervention is needed, record the exact command and output that caused the stop.

Destroy:

```sh
just vm-destroy vm=<name>
```

Record the destroy result and confirm the Proxmox VM is gone. The VM Sibling SOPS File should be deleted by the destroy command. The Inventory yaml should remain unless the demo explicitly used `delete_vm_yaml=true`.
