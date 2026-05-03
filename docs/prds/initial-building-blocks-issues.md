# Issues: Initial Building Blocks

Vertical-slice breakdown of [initial-building-blocks.md](initial-building-blocks.md).

**Status**: Drafted, pending tracker setup. When a tracker is configured (`/setup-matt-pocock-skills`), each section below ports as a single issue with the `needs-triage` label.

**Parent for all issues**: [docs/prds/initial-building-blocks.md](initial-building-blocks.md)

---

## 1. Repo scaffold + SOPS + age key ceremony

**Type**: HITL
**Blocked by**: None — can start immediately

### What to build

The foundation every other slice depends on: directory layout, secrets pipeline, operator surface stub, and a workstation-loss recovery story. The age key generation and offline-backup placement are operator ceremony, hence HITL.

End-to-end: an operator can clone an empty repo, run the bootstrapping ceremony, end up with `sops` encrypt/decrypt working against a test file, `just --list` showing command stubs, pre-commit firing on a sample commit, and a written runbook that lets a future-self rebuild this state on a new workstation.

### Acceptance criteria

- [ ] Repository directory layout established: `inventory/{hosts,vms,services,templates}/`, `ansible/`, `tofu/`, `runbooks/`, `scripts/`
- [ ] Operator age key generated; offline backup recipient generated and physically placed off-workstation
- [ ] `.sops.yaml` rules cover all encrypted file paths (sibling `<entity>.sops.yaml` pattern)
- [ ] `scripts/decrypt-keys` wrapper decrypts SSH keys into `/dev/shm` tmpfs and trap-cleans on exit
- [ ] `justfile` exists with stub recipes for the operator commands (`host-bootstrap`, `host-configure`, `vm-up`, `vm-destroy`, `service-deploy`, `templates-build`, `ingress-regenerate`)
- [ ] Pre-commit installed and runs (no real hooks yet beyond formatting; schema/validator hooks land in slice 2)
- [ ] `runbooks/initial-setup.md` documents the workstation-rebuild ceremony from scratch (age key import, offline backup retrieval, dependency install, repo clone, decrypt-test)
- [ ] DR runbook successfully executed end-to-end on a clean test workstation as the acceptance demo

### User stories covered

#68, #69, #70

---

## 2. Inventory plugin + JSON Schemas + cross-file validator

**Type**: AFK
**Blocked by**: Slice 1

### What to build

The yaml-as-source-of-truth machinery: schemas to enforce shape per file, cross-file validator to catch errors that span files, custom ansible inventory plugin to load the per-entity yaml model into ansible's flat host model. First real host yaml (wintermute) registered to demonstrate the path end-to-end.

### Acceptance criteria

- [ ] JSON Schemas exist for: host, vm, service, template, global vars
- [ ] `check-jsonschema` wired into pre-commit, validates each inventory file against its schema
- [ ] Cross-file validator (Python, pure-function) checks: service-to-VM refs, port collisions, hostname uniqueness, VM-to-host refs, VM-to-template refs, NFS export name refs
- [ ] Cross-file validator wired into pre-commit
- [ ] Decryption health check: every `.sops.yaml` in the repo is decryptable with the current age recipients; wired into pre-commit
- [ ] Custom ansible inventory plugin (Python) reads `inventory/{hosts,vms,services}/`, decrypts sibling `.sops.yaml` to tmpfs, builds groups (`proxmox_hosts`, `vms`, `vms_on_<host>`), shapes namespaced hostvars
- [ ] Inventory plugin has unit tests with fixture trees: yaml loading variants, SOPS decryption (test age key), group construction, hostvar shaping, missing-file resilience
- [ ] Cross-file validator has unit tests with curated valid + invalid trees, one test per rule plus combination cases
- [ ] Schema fixtures: directory of valid examples (must pass) and invalid examples (must fail with expected error path)
- [ ] `inventory/hosts/wintermute.yaml` written, declares intended state
- [ ] `ansible-inventory --graph` shows wintermute under `proxmox_hosts`

### User stories covered

#1, #2, #57, #58, #59, #61, #62, #63, #64

---

## 3. Host bootstrap workflow

**Type**: AFK
**Blocked by**: Slice 2

### What to build

The transition from a freshly-installed Proxmox host carrying a shared bootstrap key to a host with a unique per-host SSH key stored encrypted in the repo. Idempotency is by refusal — re-running on a bootstrapped host fails rather than clobbers.

### Acceptance criteria

- [ ] Bootstrap playbook generates a per-host SSH keypair locally
- [ ] Pushes public key to host via shared bootstrap key
- [ ] Verifies new key works (auth-test) before proceeding
- [ ] Removes shared key from host's `authorized_keys`
- [ ] Writes encrypted private key into `inventory/hosts/<host>.sops.yaml` as a structured key entry (type, created, public_key, private_key)
- [ ] Refuses to run if `<host>.sops.yaml` already contains a bootstrap key entry
- [ ] `just host-bootstrap <name>` exposes the workflow
- [ ] `runbooks/new-host.md` documents the bootstrap step
- [ ] Demo: fresh PVE install of wintermute transitioned end-to-end

### User stories covered

#3, #4, #5, #67, #71

---

## 4. Host configurator workflow

**Type**: AFK
**Blocked by**: Slice 3

### What to build

Convergence of a bootstrapped host to its declared state: repos, system hygiene, explicitly managed network bridges, PVE users with multi-role tokens (auto-created and stored encrypted), GPU passthrough setup. Storage remains operator-controlled and documented/validated only for now. Datacenter configuration is deferred while Hosts remain standalone. Idempotent, never auto-reboots, tagged so individual scopes can be applied independently.

### Acceptance criteria

- [ ] Roles exist and are independently tagged: `proxmox_repos`, `system_hygiene`, `proxmox_network`, `proxmox_users`, `gpu_passthrough`
- [ ] PVE API token for tofu created during configurator run; written encrypted into the host's sops file
- [ ] GPU passthrough role supports SR-IOV (wintermute) and full passthrough (neuromancer, straylight) per host yaml declaration
- [ ] Storage is documented in Host yaml/runbook and used by VM cross-file validation, but Host Configure does not create or register storage
- [ ] No automatic reboots — role flags `reboot_required` for operator action only
- [ ] All roles idempotent; second run is a no-op
- [ ] `just host-configure host=<name> tags=<list>` exposes the workflow; omitting tags fails and prints the all-tags command
- [ ] `runbooks/new-host.md` extended with configure step
- [ ] Demo: wintermute fully converged from declared state

### User stories covered

#6, #7, #8, #9, #10

---

## 5. VM template builder

**Type**: AFK
**Blocked by**: Slice 4

### What to build

Per-host template inventory: download a cloud image (with required checksum verification), customize via virt-customize, create a Proxmox VM at the declared template VMID, mark as template. Idempotent skip if already a template at that VMID. Host yamls declare which templates they should hold.

### Acceptance criteria

- [ ] Template yaml schema includes: name, vmid (9000-9999), source URL, **required** checksum, virt-customize ops, hardware defaults
- [ ] Builder downloads image; refuses if checksum doesn't match declared value
- [ ] Image-checksum cache avoids redundant downloads
- [ ] virt-customize runs against a working copy, not the cache
- [ ] `qm` creates VM at declared VMID, imports disk, sets hardware + cloud-init drive, marks as template
- [ ] Skip if VMID already exists as a template on that host
- [ ] Host yaml schema includes a list of templates the host should hold
- [ ] `just templates-build host=<name>` builds all templates declared on that host
- [ ] `runbooks/new-template.md` written
- [ ] Demo: a debian-cloud template at the declared VMID on wintermute, second run is a no-op

### User stories covered

#11, #12, #13, #14, #15

---

## 6. Tofu yaml-to-resource bridge + VM lifecycle

**Type**: AFK
**Blocked by**: Slice 5

### What to build

OpenTofu reads the same VM yaml files Ansible uses; provider aliases come from the host yaml directory; PVE tokens decrypted only into ephemeral env vars by a wrapper. The full VM lifecycle command sequences prepare → tofu apply → configure into one operator command. Destroy refuses while services still reference the VM.

### Acceptance criteria

- [ ] HCL module iterates VM yaml directory via `for_each`
- [ ] Multi-aliased provider map built from host yaml directory; one state file for the whole fleet
- [ ] Tofu wrapper script decrypts PVE API tokens into env vars, invokes tofu, marks vars `sensitive = true`
- [ ] Tokens never appear in plan output or tfstate
- [ ] Cloud-init userdata assembled from VM yaml + the plaintext public-key field
- [ ] `prepare` playbook: generates VM SSH keypair, writes private encrypted, writes public into VM yaml in plaintext
- [ ] `prepare` refuses if VM's encrypted file already exists
- [ ] `configure` playbook: waits for cloud-init completion, finalizes admin user
- [ ] `just vm-up vm=<name>` runs prepare → tofu apply (with explicit plan approval) → configure
- [ ] `just vm-destroy vm=<name>` runs `tofu destroy` and removes the encrypted secrets file
- [ ] `vm-destroy` refuses if any service yaml references the VM
- [ ] Tofu wrapper reads the current versioned PVE token produced by Host Configure; token rotation itself remains in the rotation workflow
- [ ] `runbooks/new-vm.md` written
- [ ] Demo: provision a test VM end-to-end on wintermute, destroy cleanly

### User stories covered

#16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #43

---

## 7. NFS integration

**Type**: AFK
**Blocked by**: Slice 6

### What to build

NAS topology declared once globally; per-VM NFS mount declarations reference exports by name; mounts implemented as systemd `.mount` units so quadlets can declare `Requires=` for ordering. UID/GID convention coordinated with TrueNAS dataset ownership.

### Acceptance criteria

- [ ] Global NAS topology in `group_vars/all/nas.yaml`: server, named exports, default mount options, UID/GID convention
- [ ] VM yaml schema supports a `nfs_mounts:` block referencing exports by name
- [ ] Per-VM mounts rendered as systemd `.mount` units on the VM
- [ ] UID/GID convention documented in `runbooks/nas-truenas.md` alongside required TrueNAS-side dataset ownership steps
- [ ] Cross-file validator checks NFS export name references resolve against global exports
- [ ] `vm-up` workflow extended to write mount units when present
- [ ] Demo: a test VM with declared mount has a functional, systemd-managed NFS mount

### User stories covered

#53, #54, #55, #56, #72

---

## 8. Quadlet renderer + first multi-container service

**Type**: AFK
**Blocked by**: Slice 7

### What to build

Service deployment via Podman Quadlets as the default substrate. Multi-container layouts are first-class. Podman secrets are injected via the `_FILE` env convention; each service runs on its own podman network; container volumes are bind-mounts under a predictable VM path; `requires_mounts:` wires NFS mount dependencies; image tags are pinned and auto-update is disabled.

### Acceptance criteria

- [ ] Service yaml schema with `deploy.type: quadlet`: hostname, backend (VM + port; list for HA), ingress block (enabled/exposure/TLS strategy/auth), deploy block with network name and list of containers (image, ports, volumes, env, env-from-secrets, depends_on, requires_mounts)
- [ ] Quadlet renderer ansible role produces `.container`, `.network`, dependency-aware unit options
- [ ] Podman secrets created from encrypted service sops file; consumed via `_FILE` env convention
- [ ] Each service on its own podman network
- [ ] Container volumes bind-mounted under a predictable path (e.g., `/srv/services/<name>/`)
- [ ] `requires_mounts:` translates to `Requires=` + `After=` on the matching `.mount` unit
- [ ] Image tags pinned (no `:latest`); auto-update disabled
- [ ] Golden-file tests cover: single-container, multi-container, secrets injection, networks, NFS-mount deps, image pinning variants
- [ ] Cross-file validator extended: port collisions on the same VM, hostname uniqueness, VM ref resolution
- [ ] `just service-deploy service=<name>` deploys or redeploys a single service
- [ ] `runbooks/new-service.md` written
- [ ] Demo: a real multi-container service (e.g., Immich-shaped fixture: app + postgres + redis) deployed on a VM

### User stories covered

#26, #27, #28, #30, #31, #32, #33, #35, #36, #37

---

## 9. Native service renderer

**Type**: AFK
**Blocked by**: Slice 8

### What to build

The escape hatch for services genuinely better as native packages (Caddy is the canonical case). Same service yaml schema, different deploy block. Apt repo handling, config-file templating with reload-vs-restart logic.

### Acceptance criteria

- [ ] Service yaml schema with `deploy.type: native`: package name, optional apt-repo reference, service name, list of config-file templates each flagged reload-vs-restart
- [ ] Native renderer role installs the package (with optional apt repo configuration), templates configs, manages the systemd unit
- [ ] Reload-vs-restart logic respected: reload-flagged template change triggers `systemctl reload`; restart-flagged triggers `systemctl restart`
- [ ] Multi-config-file services supported
- [ ] Golden-file tests cover: apt-repo handling, reload vs restart, multi-config-file
- [ ] Demo: a native test service deployed via `just service-deploy`

### User stories covered

#29

---

## 10. Pi-hole + Unbound DNS VM

**Type**: AFK
**Blocked by**: Slice 8

### What to build

Pi-hole + Unbound deployed via the quadlet path on a dedicated VM, serving LAN DNS. The exact split (single container vs two) is implementation-time. DNS records for `*.fearn.cloud` come in slice 11 alongside the ingress regenerator.

### Acceptance criteria

- [ ] DNS VM declared in inventory and provisioned via the slice-6 path
- [ ] Pi-hole + Unbound deployed via the slice-8 quadlet renderer
- [ ] LAN clients can resolve external names through the VM
- [ ] Architecture (single vs split container, upstream config) documented in `runbooks/dns-architecture.md`
- [ ] Demo: a LAN client configured with the new resolver successfully resolves both external and internal queries

### User stories covered

#39 (resolver side; record-generation side comes in slice 11)

---

## 11. Caddy ingress + ingress regenerator

**Type**: AFK
**Blocked by**: Slices 9, 10

### What to build

A single Caddy VM as the fleet's ingress, Caddy installed via the slice-9 native renderer. Cloudflare API token encrypted in the repo and scoped to this VM only. Let's Encrypt DNS-01 challenge via Cloudflare yields real public certs for internal services. The ingress regenerator workflow rebuilds the Caddyfile and Pi-hole local DNS records from the current service inventory and pushes both.

### Acceptance criteria

- [ ] Caddy VM declared in inventory, provisioned, Caddy installed via native renderer
- [ ] Cloudflare API token stored encrypted, decrypted only into the Caddy VM's environment, never elsewhere
- [ ] Let's Encrypt DNS-01 via Cloudflare configured; real cert issued for a test hostname
- [ ] Ingress regenerator: iterates service inventory, generates Caddyfile, generates Pi-hole local DNS records pointing `*.fearn.cloud` at the Caddy VM, pushes both, reloads both services
- [ ] `just ingress-regenerate` exposes the workflow
- [ ] `runbooks/ingress.md` documents the Caddy/Cloudflare/Pi-hole flow
- [ ] Demo: deploy a service with ingress enabled, run regenerator, reach `https://<name>.fearn.cloud` from the LAN with a real cert

### User stories covered

#34, #38, #39, #40

---

## 12. PBS VM + backup discipline

**Type**: AFK
**Blocked by**: Slice 7

### What to build

Proxmox Backup Server deployed in the inventory like any other VM. Datastore on a TrueNAS-hosted NFS export. Client-side encryption from day one (avoids re-encryption when off-site replication is added later). PBS encryption master key stored in the encrypted repo and at the offline backup location. Per-VM backup schedule and retention declared in the VM yaml with sensible global defaults.

### Acceptance criteria

- [ ] PBS VM declared in `inventory/vms/pbs.yaml`, provisioned via slice-6 path
- [ ] PBS NFS datastore mounted via slice-7 path
- [ ] Client-side encryption enabled at PBS initialization
- [ ] Encryption master key generated as part of an operator ceremony in `runbooks/pbs.md`; stored both encrypted in repo and at offline backup location
- [ ] VM yaml schema supports `backup:` block (schedule, retention)
- [ ] Global backup defaults in `group_vars/all/backup.yaml`; per-VM block overrides
- [ ] Service data captured implicitly via VM-level snapshot (no parallel file-level backup tool)
- [ ] `runbooks/pbs.md` covers initial setup, encryption-key ceremony, restore drill
- [ ] Demo: scheduled backup of a test VM runs; restore succeeds

### User stories covered

#47, #48, #49, #50, #51, #52

---

## 13. Rotation workflows

**Type**: AFK
**Blocked by**: Slice 11

### What to build

Hard-cutover rotation flows for every credential type the fleet manages: host root SSH keys, VM admin SSH keys, PVE API tokens, service secrets. The age key rotation is documented as a manual ceremony rather than automated. No grace-period overlap anywhere.

### Acceptance criteria

- [ ] `just host-rotate-key host=<name>` rotates the per-host root SSH key, hard cutover, console-recovery path documented
- [ ] `just vm-rotate-admin-key vm=<name>` updates the encrypted store **and** the plaintext public-key field on the VM yaml so a future tofu re-apply uses the current key
- [ ] `just pve-rotate-token host=<name>` uses versioned token names on the PVE side so rotation is atomic
- [ ] `just service-rotate-secret service=<name> secret=<key>` updates the encrypted store and redeploys the service; per-service runbooks document app-side steps (e.g., `ALTER USER` for DB password)
- [ ] `runbooks/rotate-age-key.md` documents the manual age-key rotation ceremony
- [ ] Per-rotation runbooks under `runbooks/rotate-*.md`
- [ ] Demo: each rotation type executed end-to-end against a real entity

### User stories covered

#41, #42, #43, #44, #45, #46
