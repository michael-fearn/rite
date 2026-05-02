# fortress2 Architecture

Homelab automation for a fleet of standalone Proxmox 9 hosts. This document captures the architectural decisions made during the initial design and the reasoning behind each. Implementation flows from these decisions; if you're changing something here, expect to touch multiple files downstream.

---

## 1. Overview

fortress2 manages four Proxmox 9 hosts and the VMs / services that run on them. The two hard constraints that drive the design:

- **Tooling split**: OpenTofu provisions VM shells (the qemu/proxmox layer); Ansible configures everything else (host-level config, in-VM config, services).
- **Secrets stay encrypted in the repo**: SOPS + age, single age recipient (operator) plus an offline backup recipient. Only the age private keys live outside the repo.

The system is designed for a single operator, no CI yet (CI is a known future addition that will require adding a runner age recipient via `sops updatekeys`).

---

## 2. Hardware Fleet

All hosts are standalone — there is no Proxmox cluster, no shared storage, no live migration. Each host is its own island.

| Host | CPU | RAM | Storage | iGPU | GPU passthrough mode |
|---|---|---|---|---|---|
| **wintermute** | i7-12700T (12C/20T) | 64 GB | 2.5 TB | UHD 770 (Alder Lake) | **SR-IOV** (multi-VM sharing, up to 7 VFs) |
| **neuromancer** | i7-8700T (6C/12T) | 32 GB | 750 GB | UHD 630 (Coffee Lake) | **Full passthrough only** (GVT-g dead path on kernel ≥ 6.0) |
| **straylight** | i5-6500T (4C/4T) | 32 GB | 1 TB | HD 530 (Skylake) | **Full passthrough only** (GVT-g dead path) |
| **molly** | AMD A9-9400 (2C) | 8 GB | 128 GB | Radeon R5 (Stoney Ridge) | None — utility-only host, small VMs |

**Per-host responsibility load**:
- **wintermute**: heavy workloads, GPU-shared services (likely candidates: media transcoding, ML inference).
- **neuromancer**: PBS VM + media services (Immich, Jellyfin) — the GPU goes to one of those, not both.
- **straylight**: standard service VMs.
- **molly**: small infrastructure VMs only (no GPU, low resource budget).

**Caveat for full passthrough**: consumer chipsets often place the iGPU in an IOMMU group with other devices. Hosts in `mode: full` will need the `pcie_acs_override` kernel cmdline. This is best-effort on consumer hardware — if straylight or neuromancer end up with an unworkable IOMMU grouping, full passthrough may not function.

---

## 3. External Dependencies

These are not managed by this repo but are required for it to function:

- **TrueNAS** — exports NFS datasets used by:
  - PBS VM as its datastore (`/mnt/pool/pbs`).
  - VMs that need shared storage (media, documents, etc.).
  - Allowed-host ACLs (`sec=sys`, IP-based) maintained on TrueNAS side. Adding a new NFS-mounting VM requires a manual TrueNAS-side ACL update.
  - Loss of TrueNAS → vzdump fails, media services fail.
- **Cloudflare** — DNS for `fearn.cloud`. Used by Caddy for Let's Encrypt DNS-01 challenges. A scoped API token (DNS edit on `fearn.cloud` only) is required, stored in `inventory/services/caddy.sops.yaml`.
- **Proxmox no-subscription repo** — hosts pull updates from here (subscription repo removed by ansible).
- **Cloud image upstreams** — Debian/Ubuntu cloud-image servers, fetched by template-build playbook. Pinned by SHA512.

Document any additions in `runbooks/dependencies.md`.

---

## 4. Repository Layout

```
fortress2/
├── ansible.cfg
├── justfile                                 # all operator commands
├── .sops.yaml                               # encryption rules
├── .gitignore                               # tofu state, /dev/shm tmpdirs, .bootstrap-key
├── age/
│   └── recipients.txt                       # public age keys (operator + offline backup)
│
├── inventory/
│   ├── plugins/
│   │   └── fortress.py                      # custom inventory plugin (~50 LOC)
│   ├── group_vars/
│   │   └── all.yaml                         # domain, NTP, DNS, vm_admin_user, NAS topology, UID/GID map, apt_repos
│   ├── hosts/
│   │   ├── _schema.json
│   │   ├── _example.yaml
│   │   └── <host>.yaml + <host>.sops.yaml
│   ├── vms/
│   │   ├── _schema.json
│   │   ├── _example.yaml
│   │   └── <vm>.yaml + <vm>.sops.yaml
│   └── services/
│       ├── _schema.json
│       ├── _example.yaml
│       └── <svc>.yaml [+ <svc>.sops.yaml]
│
├── vm-templates/                            # template recipes (not inventory)
│   ├── _schema.json
│   ├── _example.yaml
│   └── <template>.yaml
│
├── playbooks/
│   ├── host-bootstrap.yml
│   ├── host-configure.yml
│   ├── host-rotate-ssh-key.yml
│   ├── host-rotate-pve-token.yml
│   ├── templates-build.yml
│   ├── vm-prepare.yml
│   ├── vm-configure.yml
│   ├── vm-rotate-ssh-key.yml
│   ├── vm-destroy.yml
│   ├── service-deploy.yml
│   └── ingress-rebuild.yml
│
├── roles/
│   ├── proxmox_repos/
│   ├── system_hygiene/
│   ├── proxmox_network/
│   ├── proxmox_storage/
│   ├── proxmox_users/
│   ├── proxmox_gpu/
│   ├── nfs_mounts/
│   ├── vm_admin_user/
│   ├── service_quadlet/
│   └── service_native/
│
├── tofu/
│   ├── main.tf                              # multi-aliased provider config
│   ├── locals.tf                            # yamldecode loop over inventory/vms/*.yaml
│   ├── vms.tf                               # for_each VM resource
│   ├── variables.tf                         # TF_VAR_pve_token_<host> declarations
│   ├── outputs.tf
│   └── terraform.tfstate                    # gitignored, manually backed up
│
├── scripts/                                 # bash, called by justfile
│   ├── decrypt-keys-to-tmpfs.sh
│   ├── tofu-wrap.sh
│   ├── state-backup.sh
│   └── validate.sh
│
└── runbooks/
    ├── new-host.md
    ├── new-vm.md
    ├── new-service.md
    ├── rotate-host-key.md
    ├── rotate-pve-token.md
    ├── rotate-age-key.md
    ├── lost-laptop-recovery.md
    ├── proxmox-upgrade.md
    ├── dependencies.md
    └── initial-setup.md
```

---

## 5. Inventory Model — yaml-as-source-of-truth

The core pattern: every managed entity (host, VM, service, template) is a flat per-entity YAML file. The file IS the source of truth. Adding an entity = adding one file. There is no template-rendering layer above the YAML.

**Why flat YAML over Jinja+vars or constructed inventories**: indirection that feels clean on day one becomes a debugging tax on day ninety. The flat YAML is the contract; a JSON Schema enforces shape; the inventory plugin reads it directly.

**Sibling files for secrets**: `<entity>.yaml` (plaintext, in git) and `<entity>.sops.yaml` (encrypted, in git). Co-located so all knowledge about an entity lives in one directory. SOPS encrypts values, not keys, so the structure remains greppable and rules in `.sops.yaml` can target `.sops.yaml` files by path regex.

**One SOPS file per entity, structured schema**:

```yaml
# inventory/hosts/raptor.sops.yaml
ssh_root_key:
  type: ed25519
  created: 2026-05-01T12:00:00Z
  rotation: 1
  public_key: "ssh-ed25519 AAAA..."
  private_key: |-
    -----BEGIN OPENSSH PRIVATE KEY-----
    ...
pve_api_tokens:
  tofu:
    version: 1                              # incremented on rotation
    value: "<token-secret>"
```

The `rotation` and `version` integer fields support hard-cutover rotation policy (no grace-period overlap; old key/token gone immediately after new is verified).

**Globals** (`inventory/group_vars/all.yaml`) hold defaults that can be overridden per-host or per-vm. Examples: `domain: fearn.cloud`, `timezone`, `ntp_servers`, `dns_resolvers`, `vm_admin_user`, NAS topology, UID/GID convention, apt_repos.

---

## 6. Secrets Management

### 6.1. age key topology

- **Primary recipient**: operator's age key on the workstation, at `~/.config/sops/age/keys.txt`.
- **Backup recipient**: an offline age key kept on encrypted external media (paper backup or USB in a safe). Recovery from "I dropped my laptop in a lake."
- **No CI recipient yet** — when CI is added, generate a runner key and `sops updatekeys` over all SOPS files to add it.

`age/recipients.txt` lists the public keys; `.sops.yaml` references them in encryption rules.

### 6.2. SOPS file conventions

- File granularity: **one SOPS file per entity** (host, VM, service). Field-within-file granularity is sufficient for rotation blast-radius — SOPS re-encrypts only changed values.
- Schema: structured key entries with metadata (created, rotation/version, public_key alongside private_key) so future automation can answer "how old is this key" and "what's the public key" without re-derivation.
- Sparse SOPS: a `<entity>.sops.yaml` only exists if the entity has secrets; absence is fine.

### 6.3. Encryption rules (`.sops.yaml`)

```yaml
creation_rules:
  - path_regex: '\.sops\.yaml$'
    age: <comma-separated public keys from age/recipients.txt>
```

Single rule covers all encrypted files via path suffix.

### 6.4. Decryption flows

Two decrypt patterns, both wrapped in operator-facing commands:

- **For ansible (SSH keys)**: `decrypt-keys-to-tmpfs.sh` runs at the start of any `just` target that invokes ansible. It decrypts each entity's private SSH key into `/dev/shm/fortress2/<entity>.key`, sets `ANSIBLE_PRIVATE_KEY_FILE` indirection via the inventory plugin, and traps cleanup on exit. Keys never touch persistent disk.
- **For tofu (PVE tokens)**: `tofu-wrap.sh` decrypts `pve_api_tokens.tofu.value` from each host's SOPS file and exports as `TF_VAR_pve_token_<host>` env vars. Tokens are marked `sensitive = true` in tofu variable declarations so they don't appear in plan output or state.

**Tofu never reads SOPS directly**. This keeps tofu out of the secrets pipeline entirely (no `sops_file` provider, no decrypt-to-tmpfile wrappers in HCL, no risk of secrets in `terraform.tfstate`).

---

## 7. Host Lifecycle

### 7.1. Pre-state (operator, runbook)

1. Install Proxmox 9 manually via ISO.
2. Drop the shared bootstrap key into `/root/.ssh/authorized_keys`. Path on workstation: documented constant (e.g., `~/.ssh/fortress2_bootstrap`), referenced by `host-bootstrap.yml`.
3. Manually create any storage pools (ZFS, LVM-thin, etc.). **Ansible only registers existing pools** in `storage.cfg`; it does not create pools (per design — storage operations are operator-controlled).
4. Create `inventory/hosts/<host>.yaml` filling out the schema.

### 7.2. Bootstrap (`host-bootstrap.yml`)

One-shot transition from shared key to per-host key:

1. **Pre-flight**: refuse if `inventory/hosts/<host>.sops.yaml` already exists. Forces explicit choice between bootstrap and rotate.
2. Connect using the shared key (path set in playbook via `ansible_ssh_private_key_file`).
3. Generate ed25519 keypair on the controller (workstation), with comment `fortress2 host:<host> rotation:1`.
4. Push public key to `/root/.ssh/authorized_keys`.
5. **Verify** the new key works by opening a second SSH connection. **Mandatory** — failure here aborts before removing the shared key.
6. Remove the shared key from `authorized_keys`.
7. Write the SOPS file with the structured `ssh_root_key:` block.
8. Delete the controller-side tempfile holding the unencrypted private key.

If step 6 fails post-verify (extremely unlikely), recovery is via Proxmox console (web UI / IPMI / direct console).

### 7.3. Configure (`host-configure.yml`)

Idempotent, re-runnable. Scope:

- Proxmox repos (remove enterprise repo, add no-subscription, kill subscription nag).
- System hygiene (hostname, `/etc/hosts`, NTP, timezone, base apt packages).
- Proxmox network bridges beyond the install-default `vmbr0` (additional `vmbrN`, VLAN-aware mode, MTU).
- Storage pool registration in `storage.cfg` (pools themselves created by operator — see §7.1.3).
- `datacenter.cfg` and `storage.cfg` settings.
- PVE users + ACL bindings + API tokens. Tokens written to SOPS with versioned naming (e.g., `tofu-v1`). Multi-role support per user.
- GPU passthrough kernel cmdline + vfio modules + initramfs (see §11). **Reboot policy: never auto-reboot**; ansible reports "reboot required" and the operator reboots deliberately.

**Out of scope (deferred)**: PVE/host firewall, monitoring agents, ZFS pool creation. Backup config (vzdump schedules) is in scope as part of PBS integration (§12).

### 7.4. Rotation (`host-rotate-ssh-key.yml`, `host-rotate-pve-token.yml`)

Hard-cutover policy. SSH key rotation mirrors bootstrap but uses the current per-host key for connection and increments `rotation:` in SOPS. PVE token rotation uses versioned token names (`tofu-v1` → `tofu-v2`) on the PVE side to avoid the rename dance; coordination requirement is documented (no `tofu apply` mid-rotation).

---

## 8. VM Templates

VM templates are stopped Proxmox VMs marked `template: 1` with a cloud-init drive attached. Templates are conceptually distinct from inventory (recipes vs instances), so they live at top-level `vm-templates/<name>.yaml`.

### 8.1. Schema (`vm-templates/debian-12-base.yaml`)

```yaml
name: debian-12-base
vmid: 9001                                    # explicit, in 9000-9999 template range

source:
  url: https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2
  checksum:
    algorithm: sha512
    value: <hex>                              # required; ansible refuses without

customize:                                    # virt-customize ops, optional
  packages: [qemu-guest-agent, sudo]
  run_commands:
    - systemctl enable qemu-guest-agent

hardware:
  cores: 2
  memory: 2048
  bios: ovmf
  machine: q35
  scsi_controller: virtio-scsi-pci
  network_model: virtio
  agent_enabled: true
  serial_console: true                        # required for cloud-init console output
```

### 8.2. Host-to-template assignment

Host yaml lists templates it should hold:

```yaml
proxmox:
  pve_node_name: raptor
  templates: [debian-12-base, ubuntu-24.04-base]
```

Host-centric (matches the rest of the pattern; easy to grep "what's on this host"). Defining a new template means editing every host yaml that should have it — explicit and intentional.

### 8.3. Build (`templates-build.yml`)

Per host, per listed template: download cloud image (skip if checksum matches cached), virt-customize into a working copy, `qm create` if VMID doesn't exist, import disk, set hardware + cloud-init drive, `qm template`. Idempotent — skips fully if VMID exists and is already a template. Force rebuild via separate playbook (intentional friction; templates rebuilt = downstream VMs orphaned).

### 8.4. Image checksums

Required field. Cloud images are foundational trust; pinning protects against upstream compromise. Updating a template = update URL + checksum + rebuild.

---

## 9. VM Lifecycle

### 9.1. Schema (`inventory/vms/web01.yaml`)

```yaml
vmid: 101                                    # explicit, in instance range (100-8999)
description: "web frontend"

placement:
  host: wintermute                           # which proxmox host runs this VM

source:
  template: debian-12-base                   # must be present on placement.host

hardware:
  cores: 2
  memory: 4096
  disks:
    - storage: tank
      size: 32G
  pci_devices: []                            # populated only if GPU passthrough

network:
  interfaces:
    - bridge: vmbr0
      vlan: 10
      address: 10.0.10.101/24                # static
      gateway: 10.0.10.1                     # only on the default-route interface

cloud_init:
  hostname: web01                            # FQDN = web01.fearn.cloud

nfs_mounts:                                  # see §13
  - export: media
    mount_point: /mnt/nas/media
    options_extra: [ro]

# populated by vm-prepare playbook (plaintext; public keys aren't secret):
ssh_public_key: "ssh-ed25519 AAAA..."
```

SOPS sibling holds the private SSH key with the same structured schema as host keys.

### 9.2. The prepare → provision → configure sequence

Three steps, one logical operation. Wrapped by `just vm-up <vm>`.

**Why three steps**: cloud-init needs the SSH public key at first boot (no shared-key trust transition for VMs the way there was for hosts — we're provisioning, so we can do it right the first time).

1. **`vm-prepare.yml`**: refuse if SOPS file already exists. Generate ed25519 keypair on controller. Write private key to `<vm>.sops.yaml`. Write public key to `<vm>.yaml`'s `ssh_public_key:` field (plaintext — public keys aren't secret).
2. **`tofu apply`** (via `tofu-wrap.sh`): reads `inventory/vms/*.yaml` via `for_each = fileset(...) + yamldecode()`, clones the cloud-init template, injects `ssh_public_key` and admin user via cloud-init userdata. Tofu never reads SOPS.
3. **`vm-configure.yml`**: connects as the global admin user (default `admin`, NOPASSWD sudo, set in `group_vars/all.yaml`) with the per-VM private key from SOPS. First task: `wait_for_connection` with reasonable timeout (handles the gap between tofu returning and cloud-init completing). Then: VM admin user finalization, NFS mount setup, prep for service deploys.

### 9.3. Destruction (`vm-destroy.yml`)

`just vm-destroy <vm>` → confirmation prompt → pre-flight checks (refuses if any `inventory/services/*.yaml` references the VM as `backend.vm`) → `tofu destroy -target=...` → removes both `<vm>.yaml` and `<vm>.sops.yaml`. Operator commits the deletions.

### 9.4. Connection model

Ansible discovers VMs from `inventory/vms/*.yaml` directly via the custom inventory plugin. No tofu state introspection, no Proxmox API queries, no dynamic inventory script. The yaml is authoritative; tofu's job is to make reality match the yaml.

---

## 10. Service Layer

### 10.1. Service as first-class inventory citizen

Services live at `inventory/services/<svc>.yaml`. This mirrors the host/VM/template pattern. Services that move between VMs are one field change in one file (vs delete-from-one-vm-add-to-another). Multi-VM services (HA pairs, distributed apps) fit cleanly via `backend:` becoming a list when needed.

### 10.2. Schema — quadlet path (`inventory/services/immich.yaml`)

```yaml
name: immich
hostname: photos.fearn.cloud
backend:
  vm: media01
  port: 2283                                 # the port caddy proxies to
ingress:
  enabled: true
  exposure: lan_only
  tls: letsencrypt_dns
auth: { type: none }

deploy:
  type: quadlet
  network: immich-net                        # per-service podman network
  containers:
    - name: server
      image: ghcr.io/immich-app/immich-server:v1.120.0
      ports: ["2283:2283"]
      volumes:
        - host: /opt/services/immich/upload
          container: /usr/src/app/upload
      env:
        DB_HOSTNAME: immich-postgres
        DB_USERNAME: immich
      env_from_secrets:
        - secret: db_password                # ansible loads from <svc>.sops.yaml
          env_var_file: DB_PASSWORD_FILE     # → /run/secrets/db_password
      depends_on: [immich-postgres, immich-redis]
      requires_mounts: []                    # see §13
    - name: postgres
      image: tensorchord/pgvecto-rs:pg14-v0.2.0
      volumes:
        - host: /opt/services/immich/postgres
          container: /var/lib/postgresql/data
      env_from_secrets:
        - secret: db_password
          env_var_file: POSTGRES_PASSWORD_FILE
    - name: redis
      image: docker.io/redis:6.2-alpine
```

### 10.3. Schema — native path (`inventory/services/caddy.yaml`)

```yaml
name: caddy
deploy:
  type: native
  package: caddy
  apt_repo: caddy_official                   # references group_vars/all.yaml/apt_repos
  service_name: caddy
  config_files:
    - template: Caddyfile.j2
      dest: /etc/caddy/Caddyfile
      mode: "0644"
      reload_on_change: true                 # systemctl reload, not restart
  env_files:
    - template: caddy.env.j2
      dest: /etc/default/caddy
      mode: "0600"                           # holds CF_API_TOKEN from SOPS
```

### 10.4. Substrate decisions

- **Default: Podman Quadlets** (systemd-native containers). No daemon, journald-integrated logs, systemd dependency graph (`After=`, `Requires=`), `systemctl status <svc>` works.
- **Native escape hatch**: for things genuinely better as packages (Caddy is the main candidate — single Go binary, well-maintained apt package). Ansible-managed configs equally well in either substrate.
- **Multi-container as first-class** (not single-container with workarounds). `containers:` is a list; ansible renders one quadlet per entry plus a `.network` quadlet for the shared bridge.
- **Secrets via Podman secrets** (`Secret=name,target=/run/secrets/name`). Apps consume via `_FILE` env var convention. For apps without `_FILE` support, fall back to `EnvironmentFile=` pointing at a 0600 ansible-templated file.
- **Image pinning by tag** by default (`v1.120.0`), digest-pinning for security-critical containers (Caddy, Pi-hole). **Auto-update off**; updates flow through PR + `just service-deploy`.
- **Per-service podman networks** (one `.network` quadlet per service). Cross-service traffic blocked unless explicit. Host networking (`network_mode: host`) as opt-in for cases that need it (Pi-hole on :53).
- **Bind-mount volumes** under `/opt/services/<svc>/<volume>/`. Direct filesystem visibility, easy backup (PBS captures via VM disk snapshot), portable across VM rebuilds.

### 10.5. Ingress

Single Caddy VM. All `*.fearn.cloud` DNS records resolve to this VM's IP (Pi-hole serves the records to LAN clients; see §10.6). Caddy reverse-proxies to backing VMs. One TLS cert store, one place for ingress config to live.

`just ingress-rebuild` regenerates the Caddyfile by iterating `inventory/services/*.yaml` where `ingress.enabled: true`, pushes to the Caddy VM, reloads (not restarts — Caddy supports config reload without dropping connections).

### 10.6. DNS

Pi-hole + Unbound on a separate VM (DNS appliance — different criticality and lifecycle from ingress). Pi-hole serves LAN DNS; Unbound is the recursive backend so Pi-hole doesn't query upstream.

`just ingress-rebuild` also generates Pi-hole local DNS records (one per service, hostname → ingress VM IP) and pushes to the Pi-hole VM.

### 10.7. TLS

Let's Encrypt via DNS-01 challenge through Cloudflare API (scope: DNS edit on `fearn.cloud` only). Real public certs for internal hostnames without exposing services to the internet. CF API token in `inventory/services/caddy.sops.yaml`. Token must be provisioned out-of-band before first deploy (documented in `runbooks/dependencies.md`).

---

## 11. GPU Passthrough

Per-host configuration in the host yaml:

```yaml
# wintermute (12th gen — SR-IOV)
gpu_passthrough:
  enabled: true
  vendor: intel
  mode: sriov
  iommu: intel
  sriov_vfs: 7
  blacklist_host_driver: false               # host keeps PF, VFs go to VMs

# straylight / neuromancer (6th/8th gen — full passthrough only)
gpu_passthrough:
  enabled: true
  vendor: intel
  mode: full
  iommu: intel
  blacklist_host_driver: true                # host gives up iGPU entirely
```

Per-VM PCI device assignment in the VM yaml (instance-level, not template-level):

```yaml
hardware:
  pci_devices:
    - host_address: "0000:00:02.1"           # specific VF for SR-IOV
      primary_gpu: false
      pcie: true
      rombar: true
```

Templates can carry GPU-aware *userland* (drivers, vainfo, intel-media-va-driver). Instances carry the actual PCI assignment. Templates remain reusable across hosts that may not all have iGPUs.

**Reboot policy**: never auto-reboot. Ansible makes IOMMU/vfio changes, reports "reboot required", operator coordinates downtime.

**Consumer chipset caveat**: full-passthrough hosts may need `pcie_acs_override=downstream,multifunction` on the kernel cmdline for IOMMU group splitting. Ansible sets this conditionally for `mode: full` hosts. Not guaranteed to work on all consumer boards — fallback is "GPU passthrough not viable on this host."

---

## 12. Backups (PBS)

### 12.1. Architecture

- **PBS VM** on neuromancer (`inventory/vms/pbs.yaml`).
- **Datastore**: NFS mount from TrueNAS (`/mnt/pool/pbs`), mounted into the PBS VM via systemd .mount unit.
- **Client-side encryption enabled from day 1** — master key stored in `inventory/vms/pbs.sops.yaml` AND in the offline backup location alongside the age key. Without the key, backups are unrecoverable.

### 12.2. Per-VM backup config

```yaml
# inventory/vms/<vm>.yaml
backup:
  enabled: true
  schedule: daily
  retention: { keep_daily: 7, keep_weekly: 4, keep_monthly: 6 }
  datastore: main
```

Defaults defined in `group_vars/all.yaml`. Per-VM overrides for special cases (DB-heavy = more frequent, ephemeral = disabled).

### 12.3. Service data backups

Implicit. Bind-mounted service volumes at `/opt/services/<svc>/` are part of the VM disk; PBS captures them in the VM-level backup. Restoring a service = restoring the VM. No separate file-level backup tooling required for service data.

### 12.4. Off-site

**Deferred.** Local-only backups don't survive a site loss (TrueNAS dies → backups die with it; same site as the hosts). This is a known gap, documented, not blocking v1. Off-site options for later: PBS sync to remote PBS, restic to S3/B2, manual external-disk rotation.

### 12.5. Encryption key rotation

Not routine. PBS chunks can't be re-encrypted in place — rotation = create new datastore + fresh backups + eventually delete old. Documented as an incident-response runbook only.

---

## 13. NFS Integration

VMs can mount NFS shares from TrueNAS. Available to both native and quadlet services.

### 13.1. Global NAS topology (`group_vars/all.yaml`)

```yaml
nas:
  server: 10.0.x.x
  default_options: [nfsvers=4.2, soft, _netdev]
  exports:
    media:     /mnt/pool/media
    documents: /mnt/pool/documents
    pbs:       /mnt/pool/pbs
    backups:   /mnt/pool/backups
  uid_gid_map:
    media:     { uid: 1000, gid: 1000 }
    documents: { uid: 1001, gid: 1001 }
```

Single source of truth for NAS topology. VMs reference exports by name.

### 13.2. Per-VM mount declarations

```yaml
# inventory/vms/media01.yaml
nfs_mounts:
  - export: media
    mount_point: /mnt/nas/media
    options_extra: [ro]
  - export: documents
    mount_point: /mnt/nas/documents
```

Ansible role `nfs_mounts` renders systemd `.mount` units into `/etc/systemd/system/`. NFSv4 with `sec=sys`; TrueNAS uses host-based ACLs (allowed-host IP list maintained on TrueNAS side — adding a new mounting VM is a manual TrueNAS-side step, documented in `runbooks/dependencies.md`).

### 13.3. Service consumption

- **Native services**: just reference the host path in their config templates. No new schema needed.
- **Quadlet containers**: existing `containers[].volumes[]` schema already handles host paths. Containers that need NFS-backed volumes declare `requires_mounts:` so the quadlet renderer adds `Requires=mnt-nas-media.mount` and `After=mnt-nas-media.mount` for proper startup ordering.

### 13.4. UID/GID coordination

Numeric UID/GID convention defined in `group_vars/all.yaml/nas.uid_gid_map`. TrueNAS datasets owned by these UIDs/GIDs. VMs create matching users/groups during configure. Containers run as the right UID via quadlet `User=`. Avoids the `PUID/PGID` ad-hoc pattern (which doesn't compose with TrueNAS-side dataset ownership).

---

## 14. OpenTofu

### 14.1. Provider

`bpg/proxmox` — actively maintained, first-class cloud-init, full coverage of qemu config (PCI passthrough, machine types, OVMF, SDN). Telmate provider rejected as in slow decline.

### 14.2. Multi-aliased single-state

Standalone hosts each have their own PVE API endpoint. Multi-aliased provider in one root module:

```hcl
provider "proxmox" { alias = "wintermute"; endpoint = "https://10.0.0.10:8006" ... }
provider "proxmox" { alias = "neuromancer"; endpoint = "https://10.0.0.11:8006" ... }
```

Provider mapping generated from `inventory/hosts/*.yaml`. VM resources reference `provider = proxmox.<placement.host>`. One state file, one `tofu apply` for the whole fleet.

### 14.3. Module structure

```hcl
locals {
  vm_files = fileset("${path.module}/../inventory/vms", "*.yaml")
  vms = {
    for f in local.vm_files :
      trimsuffix(f, ".yaml") => yamldecode(file("${path.module}/../inventory/vms/${f}"))
  }
}

resource "proxmox_virtual_environment_vm" "vm" {
  for_each = local.vms
  provider = proxmox[each.value.placement.host]
  ...
}
```

Single root module, `for_each` over yaml files. Adding a VM = adding a yaml file, no HCL edits.

### 14.4. State

Local `tofu/terraform.tfstate`, gitignored. `just state-backup` copies to a documented location for offline backup (alongside age key + PBS encryption key — the "I dropped my laptop in a lake" plan covers all three).

### 14.5. Approval

Always show plan, require explicit confirmation. No auto-approve.

### 14.6. Auth flow

`tofu-wrap.sh` reads `inventory/hosts/<host>.sops.yaml`, extracts `pve_api_tokens.tofu.value`, exports as `TF_VAR_pve_token_<host>`, runs the tofu command. Tokens marked `sensitive = true` so they don't leak to plan output or state.

---

## 15. Validation

### 15.1. JSON Schema per inventory directory

`inventory/hosts/_schema.json`, `inventory/vms/_schema.json`, `inventory/services/_schema.json`, `vm-templates/_schema.json`. Each yaml file validated against its schema by `check-jsonschema` in `make validate` and pre-commit.

Catches typos and shape errors at validate-time (fast feedback) instead of at play-time.

### 15.2. Cross-file validation

JSON Schema is per-file; some constraints span files. `scripts/validate.sh` invokes a small Python validator that checks:

- Service `backend.vm` references an existing `inventory/vms/<vm>.yaml`.
- No two services on the same VM declare the same `backend.port`.
- No two services declare the same `hostname`.
- VM `placement.host` references an existing `inventory/hosts/<host>.yaml`.
- VM `source.template` exists in `vm-templates/`.
- VM `nfs_mounts[].export` exists in `group_vars/all.yaml/nas.exports`.

### 15.3. Decryption check

`just decrypt-check` iterates all `*.sops.yaml`, runs `sops -d > /dev/null` on each, fails if any fail. Catches "committed file encrypted to a recipient not in current `age/recipients.txt`" before it bites.

### 15.4. Pre-commit hooks

- `check-jsonschema` (per-file schema)
- `ansible-lint`
- `terraform_fmt`, `terraform_validate`
- `detect-secrets` (catch accidental plaintext secrets)
- Custom: `validate.sh` (cross-file)
- Custom: `decrypt-check`

---

## 16. Connection Flow (custom inventory plugin)

`inventory/plugins/fortress.py` (~50 LOC) is the bridge between the per-entity yaml model and ansible's host concept.

At ansible startup, the plugin:

1. Reads `inventory/hosts/*.yaml` and `inventory/vms/*.yaml`.
2. For each entity, builds an ansible host with:
   - `ansible_host` from `mgmt.ip` (host) or `network.interfaces[0].address` (vm).
   - `ansible_user` from convention (root for hosts, `vm_admin_user.name` for VMs).
   - `ansible_ssh_private_key_file` pointing to `/dev/shm/fortress2/<entity>.key` (decrypted at the start of the wrapping `just` target by `decrypt-keys-to-tmpfs.sh`, trap-cleaned on exit).
   - `host_data` / `vm_data` namespaced hostvars containing the full yaml content (so plays can reference `host.network.bridges` etc. without re-loading).
   - `host_secrets` / `vm_secrets` from the SOPS file, decrypted at inventory load.
3. Builds groups automatically:
   - `proxmox_hosts` — every entry from `inventory/hosts/*.yaml`.
   - `vms` — every entry from `inventory/vms/*.yaml`.
   - `vms_on_<hostname>` — VMs grouped by `placement.host`.

Configured via `ansible.cfg`'s `inventory_plugins` setting.

---

## 17. Rotation Flows

All rotations follow hard-cutover policy (no grace-period overlap; recovery via console for hosts, reprovision for VMs).

| Rotation | Mechanism | Frequency |
|---|---|---|
| Host root SSH key | `host-rotate-ssh-key.yml` — mirrors bootstrap with current key | As needed |
| VM admin SSH key | `vm-rotate-ssh-key.yml` — also updates plaintext `ssh_public_key:` field for tofu re-applies | As needed |
| PVE API token | `host-rotate-pve-token.yml` — versioned token names (`tofu-v1` → `tofu-v2`) | As needed; coordinate with no concurrent `tofu apply` |
| Operator age key | `runbooks/rotate-age-key.md` — manual ceremony (`age-keygen` → add to recipients → `sops updatekeys` everywhere → swap identity → remove old recipient → `sops updatekeys` again → backup new private + destroy old) | Rare; on suspected compromise or routine multi-year hygiene |
| Service secret (mechanic) | `just rotate-service-secret SERVICE=<svc> SECRET=<name>` — updates SOPS, redeploys service | Per-service |
| Service secret (app-side) | Per-service runbook in `runbooks/rotate-<svc>.md` — documents app-side steps (e.g., `ALTER USER`) | Per-service |
| Cloudflare API token | `runbooks/rotate-cloudflare-token.md` — operator creates new in CF dashboard, updates SOPS, runs `just service-deploy SERVICE=caddy`, deletes old in dashboard | Rare |
| PBS encryption key | `runbooks/incident-pbs-key-compromise.md` — incident-response only; rotation = new datastore + fresh backups | Incident-only |

---

## 18. Bring-up Sequences

### 18.1. New host

1. (Manual) Install Proxmox 9, drop shared bootstrap key, create storage pools, create `inventory/hosts/<host>.yaml`.
2. `just decrypt-check` (sanity).
3. `just host-bootstrap <host>`. Commit.
4. `just host-configure <host>`. Commit.
5. Reboot if kernel cmdline / IOMMU / vfio changes were made.
6. `just templates-build <host>`.
7. Host is ready to receive VMs.

### 18.2. New VM

1. Create `inventory/vms/<vm>.yaml`.
2. `just vm-prepare <vm>` — generates key, populates `ssh_public_key:`, writes SOPS. Commit.
3. `just vm-up <vm>` — runs `tofu apply -target=...` then `vm-configure.yml`.
4. VM is ready to receive services.

### 18.3. New service

1. Create `inventory/services/<svc>.yaml` (and `<svc>.sops.yaml` if secrets needed). Commit.
2. `just service-deploy <svc>`.
3. `just ingress-rebuild` — regenerates Caddyfile and Pi-hole records, pushes to both VMs.
4. Service reachable at its hostname.

### 18.4. Decommission VM

1. Delete service yamls referencing this VM, run `just ingress-rebuild`.
2. `just vm-destroy <vm>` (refuses if any service still references the VM).
3. Commit.

---

## 19. Open Items / Deferred

- **Off-site backup** (PBS protecting itself) — own subproject when ready.
- **CI runner** — deferred; will need `sops updatekeys` to add a new age recipient.
- **Initial-setup runbook** — needs writing once building blocks are implemented.
- **TrueNAS-side coordination** — every new NFS-mounting VM is a manual TrueNAS-side ACL update.
- **Renovate** for image-tag PRs — easy to add later.
- **Pi-hole + Unbound architecture detail** — likely one VM with two containers in a shared podman network, exact split decided at implementation time.
- **VM disk passthrough schema** — would be needed if PBS datastore moves from NFS to passed-through raw disk.
- **PVE/host firewall** — out of scope for v1.
- **Monitoring / observability** — out of scope for v1; revisit when the service stack stabilizes.
