# fortress2

Homelab infrastructure automation for a fleet of standalone Proxmox 9 machines. The operator declares desired state in flat per-entity YAML files; tooling reconciles reality to match.

## Language

### Fleet topology

**Host**:
A physical Proxmox 9 machine in the fleet (e.g. `wintermute`, `neuromancer`). Standalone — there is no Proxmox cluster.
_Avoid_: server, box, machine, node (in operator-facing prose).

**Node**:
The Proxmox-internal identity of a Host (the value of `proxmox.pve_node_name` in the host yaml; what PVE itself uses in `pvesh` and API calls). Distinct from the operator-facing Host name (the yaml filename).
_Avoid_: substituting "node" for "host"; reserve "node" for the PVE-internal identity.

**VM**:
A guest declared in `inventory/vms/<vm>.yaml`, provisioned by OpenTofu, configured by Ansible. Pinned to exactly one Host via `placement.host`.
_Avoid_: guest, instance.

**Template**:
A stopped Proxmox VM marked `template: 1` with a cloud-init drive, declared in `vm-templates/<name>.yaml`. Used as the clone source for new VMs. Lives on a specific Host.
_Avoid_: image (reserve for the upstream Cloud Image).

**Cloud Image**:
The upstream qcow2 (Debian / Ubuntu) that a Template is built from. Pinned by SHA-512 checksum.
_Avoid_: ISO, base image.

**Service**:
A deployed application or co-located group of containers, declared in `inventory/services/<svc>.yaml`. Runs inside a VM. Substrate is either Quadlet (default) or Native.
_Avoid_: app, workload; "systemd service" (always qualify as "systemd unit").

**Backend**:
The VM (and TCP port) that the Ingress reverse-proxies a Service to. Declared as `backend.vm` and `backend.port`. Becomes a list when the Service is HA.
_Avoid_: upstream (overloaded with apt/git senses).

**Entity**:
A Host, VM, or Service. The thing each `<entity>.yaml` (and optional `<entity>.sops.yaml`) describes.
_Avoid_: object, record.

**Inventory**:
The set of per-entity YAML files at `inventory/{hosts,vms,services}/`. Source of truth for all declared state.
_Avoid_: catalog, registry.

### Operator and ceremony

**Operator**:
The single human running fortress2. The only intended persona; "future-self on a new workstation" is the only second viewer.
_Avoid_: user, admin.

**Bootstrap**:
The one-shot transition of a freshly-installed Host from the shared bootstrap SSH key to a unique per-host SSH key stored encrypted in the repo. Refuses to re-run.
_Avoid_: init; provision (reserve for the tofu step on VMs).

**Prepare**:
The VM-side equivalent: generate the per-VM SSH keypair, write the private half encrypted, write the public half plaintext into the VM yaml. Refuses to re-run. Precedes `tofu apply`.
_Avoid_: setup.

**Configure**:
An idempotent Ansible run that converges a Host or VM to its declared state. Re-runnable.
_Avoid_: provision (reserve for tofu).

**Rotation**:
Replacement of a credential (Host SSH key, VM admin SSH key, PVE API token, age key, Service secret) with a fresh one of the same kind.
_Avoid_: rekey (use specifically for SSH-key rotation).

**Hard Cutover**:
Rotation policy in which the old credential is removed immediately after the new one is verified — no grace-period overlap. Recovery is via Proxmox console for Hosts, reprovision for VMs.
_Avoid_: blue/green, rolling rotation.

### Secrets

**Recipient**:
An age public key listed in `age/recipients.txt`. Two exist: the operator's workstation key and an offline backup key.
_Avoid_: identity, key (be specific).

**Sibling SOPS File**:
`<entity>.sops.yaml` co-located with `<entity>.yaml`. Holds that entity's encrypted secrets. Sparse — present only when the entity has secrets.
_Avoid_: secrets file, encrypted store, vault.

### Service substrate

**Quadlet**:
A systemd unit declaring a Podman container, network, or volume; rendered onto the VM from the Service yaml. The default service substrate.
_Avoid_: pod, compose service.

**Native (Deploy)**:
The escape-hatch substrate: an apt package plus a systemd unit, configured by Ansible templates. Used when a Service is genuinely better not containerised (Caddy is the canonical case).
_Avoid_: bare-metal (the VM is still a VM); package install.

**Ingress**:
The single Caddy VM that terminates TLS and reverse-proxies all `*.fearn.cloud` traffic to backing Services. There is exactly one.
_Avoid_: edge, gateway, proxy (reserve "proxy" for the verb).

**Exposure**:
A Service's ingress visibility, declared on `ingress.exposure` (e.g. `lan_only`). The full enum is not yet pinned — see flagged ambiguities.

### Backups and storage

**PBS**:
Proxmox Backup Server, deployed in this project as a VM on `neuromancer`.
_Avoid_: PVE backup (a separate Proxmox feature).

**Datastore**:
PBS's storage location; an NFS Export from TrueNAS, mounted into the PBS VM.
_Avoid_: backup pool.

**Export**:
A named NFS share from TrueNAS (e.g. `media`, `documents`, `pbs`), declared once in the global NAS topology. VMs reference exports by name.
_Avoid_: share; mount (the VM-side artefact, not the NAS-side declaration).

**Mount**:
A systemd `.mount` unit on a VM that mounts an Export at a declared path. Ordering anchor for Quadlet containers via `requires_mounts:`.

## Relationships

- A **Host** runs zero or more **VMs** and holds zero or more **Templates**.
- A **VM** is provisioned from one **Template** and runs zero or more **Services**.
- A **Service** has one **Backend** **VM** (a list when HA is needed).
- The **Ingress** **VM** routes traffic to **Services** by hostname.
- Every **Entity** may have a **Sibling SOPS File**.
- **PBS** backs up every **VM** with `backup.enabled: true`; **PBS** itself is a **VM**.
- An **Export** is the NAS-side declaration; a **Mount** is the VM-side systemd unit that consumes one.

## Example dialogue

> **Operator:** "I want to add Immich on a fresh VM. What do I touch?"
>
> **Future-self:** "Three new YAML files. One **VM** under `inventory/vms/`, one **Service** under `inventory/services/` with `backend.vm` pointing at the new VM, and the matching `<svc>.sops.yaml` for the DB password. The **Template** the VM clones from already exists on the **Host**. After commit, `just vm-up`, `just service-deploy`, `just ingress-regenerate`. The **Ingress** picks up the new hostname automatically — you don't touch Caddy by hand."

## Flagged ambiguities

- **"node" vs "host"**: In Proxmox parlance "node" is a cluster member; here we have no cluster, so "node" only ever means the PVE-internal identity (`pve_node_name`). All operator prose uses **Host**.
- **"template"**: Overloaded between the **Template** (a Proxmox VM marked `template: 1`), the `vm-templates/<name>.yaml` recipe that produces it, and Jinja templates inside Ansible roles. The first two are the same concept at recipe and instance layers; Jinja templates should always be qualified ("Jinja template" or "config template").
- **"service"**: Overloaded with "systemd service unit". A **Service** in this project is a deployed app (one yaml under `inventory/services/`); a systemd service unit is always qualified as "systemd unit".
- **Hostname conventions**: A **Service**'s `hostname` is the FQDN (`photos.fearn.cloud`); a **VM**'s `cloud_init.hostname` is the short form (`web01`), with FQDN derived as `<short>.fearn.cloud`. The split is intentional (a VM hosts one well-known FQDN; a Service may publish many) but easy to reverse by accident.
- **`ingress.exposure` enum**: Only `lan_only` appears in [docs/architecture.md](docs/architecture.md). Whether `internet_exposed` (or similar) is a planned value, and what it would imply for the Caddy/Cloudflare wiring, is unresolved.
- **Multi-VM Backend**: A Service has one `backend.vm` today; the schema allows a list "when needed" for HA, but no Service declares one yet and the cross-file validator currently handles only the singular form.
