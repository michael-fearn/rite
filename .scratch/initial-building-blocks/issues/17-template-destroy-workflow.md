Status: ready-for-agent
Type: enhancement

## Agent Brief

**Category:** enhancement
**Summary:** Add `template-destroy` command that removes a built Proxmox Template while leaving the Template YAML intact

**Current behavior:**
The `templates-build` workflow creates a Proxmox Template (a stopped VM marked `template: 1`) from a Template YAML declaration. There is no inverse: once built, the only way to remove the Proxmox Template is manually via `qm destroy`. The Template YAML stays in the inventory regardless, but there is no scripted workflow to remove the Proxmox object safely.

**Desired behavior:**
`just template-destroy host=<host> template=<template>` removes the Proxmox Template identified by the template's `vmid` from the specified Host, after running a preflight check. It does not delete `inventory/templates/<template>.yaml` by default; `--delete-template-yaml` opts into that removal.

Preflight: if any Host in the inventory lists the template under `proxmox.templates`, refuse and name the referencing Hosts. This mirrors the Service Backend guard in `vm-destroy` — the operator must delist the template from all Hosts before destroying it.

Remote execution: if `qm` is not available locally (i.e. not running on the Host), SSH to the Host using its `network.management_address` and the decrypted bootstrap key from the Host Sibling SOPS File — mirroring the remote fallback in `templates-build`.

**Key interfaces:**
- `just template-destroy host=<host> template=<template>` — new justfile recipe
- `scripts/template-destroy <host> <template> [--delete-template-yaml]` — new script
- `load_inventory_tree()` result — read `hosts[*].proxmox.templates` for referencing-host preflight; read `templates[<name>].vmid` to get the VMID to destroy
- Remote execution uses the same SSH + bootstrap-key pattern as the remote path in `templates-build`

**Acceptance criteria:**
- [ ] `just template-destroy host=<host> template=<template>` invokes `scripts/template-destroy`.
- [ ] The script rejects an undeclared template with a clear error.
- [ ] The script rejects an undeclared host with a clear error.
- [ ] The script refuses to proceed when one or more Hosts still list the template under `proxmox.templates`, and names them.
- [ ] When `qm` is available locally, the script runs `qm destroy <vmid>` directly.
- [ ] When `qm` is not available locally, the script SSHes to the Host's `network.management_address` using the decrypted bootstrap key and runs `qm destroy <vmid>` remotely.
- [ ] `inventory/templates/<template>.yaml` is left untouched by default.
- [ ] `--delete-template-yaml` deletes `inventory/templates/<template>.yaml` after a successful destroy.
- [ ] Tests cover: undeclared template rejection, undeclared host rejection, referencing-host preflight refusal (naming the blocking hosts), successful destroy command wiring (local path), and preservation of template YAML.

**Out of scope:**
- Destroying all Templates on a Host in one invocation.
- Removing the template from `host.proxmox.templates` automatically.
- Any OpenTofu involvement (Templates are not tofu-managed resources).
- Clearing the local Cloud Image cache.
