# PRD: Initial Building Blocks

**Status**: Draft (would be `needs-triage` in tracker; published locally pending tracker setup)
**Date**: 2026-05-02
**Companion document**: [docs/architecture.md](../architecture.md)

---

## Problem Statement

The operator manages a fleet of four standalone Proxmox 9 hosts as a homelab. Today every interaction with the fleet is manual: installing Proxmox, distributing SSH keys, configuring network bridges and storage pools, creating VM templates, provisioning VMs from those templates, deploying services into VMs, wiring up DNS records, and rotating credentials. Concretely:

- **No source of truth.** What should exist on each host lives in the operator's head and on the boxes themselves. There is no document the operator can read to know what's deployed where, what version, with what config.
- **Hours per host.** A new host takes a sequence of manual steps the operator has to remember each time. Mistakes accumulate quietly and surface later.
- **Insecure or lossy secrets.** Either the same SSH key is reused across hosts (any compromise = total compromise) or per-host credentials are scattered across the operator's machine with no recovery path.
- **Ad-hoc service deployment.** Adding a new service means editing Pi-hole DNS by hand in its UI, editing Caddy config on the ingress box, deploying the container manually, hoping nothing collides with an existing service.
- **No recovery story.** Losing the operator's workstation means losing access to the fleet (no offline backup), losing tofu state, losing knowledge of what was deployed.
- **No backup discipline.** Backups are taken occasionally and informally; no schedule, no retention policy, no encryption story.
- **No verification.** Config changes are applied directly; there is no validate-then-apply flow that catches typos or schema violations before they hit a host.

The cost isn't just the per-task time — it's the cumulative drag of having no confidence that the fleet is in a known state, no ability to recreate it, and no cheap way to make a small change.

## Solution

A repository of declarative configuration describing the entire homelab fleet, paired with two automation tools (Ansible and OpenTofu) operating against that configuration through a unified operator command surface (Just). The operator declares desired state in flat per-entity YAML files; the tools reconcile reality to match.

The split is intentional and load-bearing: **OpenTofu provisions VM shells** (the qemu/proxmox layer — clone a template, set hardware, attach disks); **Ansible configures everything else** (host-level config, in-VM config, services). Both tools consume the same YAML inventory; neither owns its own source of truth.

All secrets stay encrypted in the repository via SOPS+age. The operator holds one age private key on their workstation and a second backup key offline (the "I dropped my laptop in a lake" plan). Tofu never reads SOPS directly — a wrapper script decrypts only what tofu needs into ephemeral environment variables.

For the operator, the surface area collapses to: **create one yaml file, run one command, commit the result.** Adding a new host, VM, or service all follow the same shape. Rotations follow the same shape. Validation runs at commit time and again at apply time. Pre-commit hooks catch shape errors before they can be merged.

The deliverable of this PRD is the set of building blocks needed to make all of the above true for the first time. Implementation of specific workloads (which Plex VM goes where, which database hosts what) is downstream of these blocks.

## User Stories

### Onboarding a new host

1. As the operator, I want to declare a new Proxmox host by creating a single YAML file describing it, so that the host's intended configuration is reviewable and version-controlled before any automation runs against it.

2. As the operator, I want a JSON Schema to validate my host declaration before I commit, so that typos and missing required fields are caught at edit time rather than during a play.

3. As the operator, I want one command to transition a freshly-installed Proxmox host from a shared bootstrap key to a unique per-host SSH key, so that I never have to manage that transition manually and so that compromise of one host does not compromise others.

4. As the operator, I want the bootstrap process to verify the new key works before removing the shared key, so that a key-distribution failure does not lock me out of the host.

5. As the operator, I want the bootstrap command to refuse re-runs if the host is already bootstrapped, so that I cannot accidentally clobber a working credential.

6. As the operator, I want one command to apply the full host configuration (repos, hygiene, explicitly managed network bridges, PVE users with multiple roles, GPU passthrough setup), so that bringing a host to a usable state is one operation rather than many.

7. As the operator, I want host configuration to be idempotent and re-runnable, so that I can converge the host to the declared state at any time without worrying about side effects.

8. As the operator, I want host configuration to never automatically reboot the host, so that I retain control over downtime windows for VMs running on it.

9. As the operator, I want the tofu PVE API token created automatically during host configuration and stored encrypted in the repository, so that I do not have to provision tokens manually through the Proxmox UI.

10. As the operator, I want each Proxmox host's configuration scoped clearly so that the host yaml expresses only what the host should look like, with no leakage of VM- or service-level concerns.

### VM templates

11. As the operator, I want to declare a VM template (cloud image source, checksum, customization steps, hardware) as a single YAML file, so that the template definition is reproducible and reviewable.

12. As the operator, I want one command per host to build all VM templates that host should hold, so that I can stand up template inventory in parallel across the fleet.

13. As the operator, I want template build to be idempotent (skip if the template already exists at the declared VMID), so that I can safely re-run the build playbook.

14. As the operator, I want the cloud image checksum to be a required field, so that the template build process refuses to use an unverified image.

15. As the operator, I want host yamls to declare which templates they should hold, so that template-to-host assignment is explicit and host-yaml-centric.

### VM provisioning

16. As the operator, I want to declare a VM by creating a single YAML file describing its placement (which host), source template, hardware overrides, network attachments, and optional GPU/NFS-mount needs, so that the VM's full intended state is in one reviewable place.

17. As the operator, I want one command to generate a per-VM SSH keypair, store the private half encrypted, and write the public half into the VM yaml in plaintext, so that the cloud-init injection step has the public key it needs without ever exposing the private key.

18. As the operator, I want the prepare command to refuse if the VM's encrypted secrets already exist, so that I cannot accidentally overwrite a working key.

19. As the operator, I want one command to provision a VM end-to-end (prepare → tofu apply → configure), so that I do not have to remember the sequence or type three commands.

20. As the operator, I want OpenTofu to read VM declarations from the same yaml files Ansible uses, so that there is one source of truth and no chance of the two tools disagreeing about what should exist.

21. As the operator, I want OpenTofu to never read SOPS directly, so that the secrets pipeline does not extend into HCL and so that no secret can leak into tfstate.

22. As the operator, I want tofu to always show a plan and require explicit approval, so that I never accidentally destroy a VM during a routine apply.

23. As the operator, I want VM destruction to be a single command that runs `tofu destroy`, removes the VM's Sibling SOPS File after successful destroy, and can optionally remove the VM yaml, so that the repository does not accumulate orphaned key material while VM declaration removal stays explicit.

24. As the operator, I want VM destruction to refuse if any service still references the VM, so that I cannot destroy a VM that is still load-bearing for a deployed service.

25. As the operator, I want ansible to wait for cloud-init to complete before attempting to configure a freshly-provisioned VM, so that the configure step does not race the boot sequence.

### Service deployment

26. As the operator, I want to declare a service (hostname, backend VM and port, ingress exposure, TLS, deployment substrate, container layout or native package, secrets references) as a single YAML file, so that the service's full intent is reviewable and source-of-truth.

27. As the operator, I want services to support multi-container layouts as a first-class schema feature, so that apps like Immich (server + postgres + redis) fit without workarounds.

28. As the operator, I want to deploy services as Podman Quadlets by default, so that they integrate natively with systemd (logs in journald, restarts via systemctl, dependency ordering via Requires=).

29. As the operator, I want a native escape hatch for services genuinely better as native packages (Caddy), so that I am not forced to containerize a single Go binary just for consistency.

30. As the operator, I want service secrets injected via Podman secrets and consumed by apps via the `_FILE` environment variable convention, so that secrets never appear in environment variable text or quadlet unit files.

31. As the operator, I want each service to run on its own podman network, so that cross-service traffic is blocked by default unless explicitly bridged.

32. As the operator, I want service container volumes to be bind mounts under a predictable path on the VM, so that backups capture them via the VM-level snapshot and so that I can inspect data directly when debugging.

33. As the operator, I want one command to deploy or redeploy a single service, so that updating one app does not require touching others.

34. As the operator, I want one command to regenerate the Caddy ingress config and the Pi-hole local DNS records from all current service yamls, so that changes propagate automatically when I add or move a service.

35. As the operator, I want container images pinned to explicit tags by default, so that surprise updates do not change behavior.

36. As the operator, I want auto-update disabled, so that updates only happen through a deliberate PR and re-deploy.

37. As the operator, I want service yamls validated at commit time for cross-file consistency (referenced VM exists, no port collisions on the same VM, no duplicate hostnames), so that an obviously broken service definition cannot reach a deploy.

### TLS and DNS

38. As the operator, I want TLS certificates issued via Let's Encrypt DNS-01 challenges through Cloudflare, so that internal services get real public certificates without needing internet exposure.

39. As the operator, I want all `*.fearn.cloud` records resolved by Pi-hole on the LAN to point at the single Caddy ingress VM, so that DNS and ingress topology stay simple.

40. As the operator, I want the Cloudflare API token stored encrypted in the repository and used only by the Caddy VM, so that the credential's blast radius is minimized.

### Rotation

41. As the operator, I want to rotate any host's root SSH key with one command using a hard-cutover policy, so that key rotation is a routine non-event.

42. As the operator, I want VM admin SSH key rotation to update both the encrypted store and the plaintext public-key field on the VM yaml, so that a future tofu re-apply uses the current key.

43. As the operator, I want PVE API token rotation to use versioned token names on the Proxmox side, so that I avoid a rename dance and the rotation is atomic on the PVE side.

44. As the operator, I want a hybrid service-secret rotation flow: a single command updates the encrypted store and redeploys the service, while app-side steps (e.g., `ALTER USER` for a database password) are documented in a per-service runbook.

45. As the operator, I want the operator age key rotation to be a documented manual ceremony, so that the high-stakes identity transfer is a deliberate operator action rather than buried in tooling.

46. As the operator, I want all rotation flows to follow a hard-cutover policy with no grace-period overlap, so that the system never has to track "which entities are mid-rotation."

### Backups

47. As the operator, I want a Proxmox Backup Server VM in the inventory, so that PBS itself is reproducible from the repository like any other VM.

48. As the operator, I want PBS to back up to a NAS-hosted NFS datastore, so that backup chunks live separately from the host running PBS.

49. As the operator, I want client-side encryption enabled on PBS from day one, so that adding off-site replication later does not require re-encrypting existing backups.

50. As the operator, I want the PBS encryption master key stored both in the encrypted repo and at the offline backup location, so that loss of either does not lose all backups.

51. As the operator, I want per-VM backup schedules and retention policies declared in the VM yaml with sensible global defaults, so that special cases (database VMs, ephemeral VMs) can override without bespoke playbooks.

52. As the operator, I want service data backed up implicitly via the VM-level snapshot, so that I do not have to maintain a parallel file-level backup tool for service volumes.

### NAS integration

53. As the operator, I want to declare NAS endpoints and protocol defaults globally while declaring durable Datasets as per-entity inventory, so that topology and data ownership do not blur together.

54. As the operator, I want to declare per-VM Mounts referencing Datasets by name with explicit protocol and access policy, so that VM yaml describes required Dataset access.

55. As the operator, I want NFS-backed Mounts implemented as systemd `.mount` units, so that quadlet containers can declare ordering dependencies on them and start in the correct order.

56. As the operator, I want Dataset root owner UID/GID declared and validated against TrueNAS, so that file ownership behaves predictably across hosts and containers.

### Connection model

57. As the operator, I want Ansible to discover hosts and VMs by reading the per-entity yaml files directly (not by querying Proxmox or by reading tofu state), so that the inventory is decoupled from runtime state and can be reasoned about offline.

58. As the operator, I want a custom inventory plugin to provide the full yaml content as namespaced host vars, so that plays can reference declared structure without re-reading files.

59. As the operator, I want the inventory plugin to auto-build groups (`proxmox_hosts`, `vms`, `vms_on_<host>`), so that targeting subsets of the fleet is convenient without per-play boilerplate.

60. As the operator, I want SSH private keys decrypted only into RAM-backed temporary storage at the start of each operator command, with cleanup on exit, so that decrypted secrets never touch persistent disk.

### Validation and pre-commit

61. As the operator, I want JSON Schema validation per inventory file, so that shape errors are caught at edit time.

62. As the operator, I want cross-file validation (referenced VM exists, no port collisions, no duplicate hostnames, Dataset and Mount references resolve, VM disk storage exists on the placed host, VM bridge exists on the placed host), so that errors that span files are caught before deploy.

63. As the operator, I want a decryption health check that verifies every encrypted file in the repo can be decrypted with the current age recipients, so that a misconfigured `.sops.yaml` rule cannot silently produce undecryptable files.

64. As the operator, I want pre-commit hooks running schema validation, ansible-lint, tofu fmt/validate, and the cross-file validator, so that broken commits are blocked at the source.

### Operator surface

65. As the operator, I want one tool (Just) for all routine commands, so that the operator interface is consistent and discoverable via `just --list`.

66. As the operator, I want commands named after intent (e.g., `host-bootstrap`, `vm-up`, `service-deploy`) rather than after the underlying tool, so that the surface stays stable even if the underlying playbook structure changes.

67. As the operator, I want operator commands to compose smaller building blocks (decrypt → run → cleanup) rather than baking that wiring into each playbook, so that the wiring can evolve in one place.

### Recovery and continuity

68. As the operator, I want my age private key backed up offline in a location separate from the workstation, so that workstation loss does not mean fleet loss.

69. As the operator, I want tofu state and the PBS encryption master key backed up alongside the offline age key, so that one backup operation covers all "lose-everything" recovery prerequisites.

70. As the operator, I want a documented initial-setup runbook covering the very first time the system is built from scratch on a new workstation, so that disaster recovery is a written procedure rather than a re-derivation.

### Documentation

71. As the operator, I want runbooks for every operator-facing flow (new host, new VM, new service, each rotation type) co-located with the code in the repository, so that documentation cannot drift from code without showing up in PR review.

72. As the operator, I want external-dependency documentation (TrueNAS Datasets and Shares, Cloudflare scope, Proxmox-side prerequisites) maintained in the same repository, so that a future operator can understand what the system depends on.

## Implementation Decisions

### Twelve modules

Six **deep modules** with narrow interfaces and significant internal complexity, suitable for isolated testing:

1. **Inventory plugin** (Python). Implements ansible's inventory plugin protocol. Encapsulates yaml loading from per-entity files, SOPS decryption to tmpfs, group construction (`proxmox_hosts`, `vms`, `vms_on_<host>`), and namespaced hostvar shaping. Bridges the per-entity yaml model to ansible's flat host concept.

2. **Cross-file validator** (Python). Pure-function validator over the inventory tree. Checks service-to-VM references, port collisions on a single VM, hostname uniqueness across services, VM-to-host references, VM-to-template references, Dataset references from Mounts, and Service Share-backed Volume references to Backend VM Mount Names.

3. **Quadlet renderer** (ansible role). Takes a service yaml with `deploy.type: quadlet` and produces systemd quadlet unit files (`.container`, `.network`, dependency-aware unit options). Encapsulates multi-container layout, podman-secrets injection via `_FILE` convention, per-service network isolation, NFS-mount dependency wiring, and image pinning.

4. **Native service renderer** (ansible role). Takes a service yaml with `deploy.type: native` and installs the package (with optional apt repo), templates config files, and manages the systemd unit with reload-vs-restart logic.

5. **Tofu yaml-to-resource bridge** (HCL module). Iterates over the VM yaml directory via `for_each`, builds a multi-aliased provider mapping from the host yaml directory, assembles cloud-init userdata from VM yaml plus the public-key field. The HCL module is the bridge between the declarative yaml inventory and the bpg/proxmox provider's resource API.

6. **JSON Schemas** (declarative). Per-inventory-directory schemas (host, VM, service, NAS endpoint, template) plus the global vars schema. Validated by `check-jsonschema` per-file in pre-commit.

Five **workflow modules** that compose roles into operator-facing playbooks; integration-tested only:

7. **Host bootstrap** workflow. Generates per-host SSH key, pushes public, verifies, removes shared, writes encrypted private. Idempotency-refuses if encrypted file already exists.

8. **Host configurator** workflow. Composes roles for proxmox repos, system hygiene, explicitly managed proxmox network bridges, proxmox users with multi-role tokens, and GPU passthrough. Storage remains documented/validated but operator-controlled; datacenter configuration is deferred while Hosts remain standalone. The workflow requires explicit ansible tags so individual scopes are applied deliberately.

9. **VM template builder** workflow. Per host, downloads listed cloud images (with checksum cache), runs virt-customize against a working copy, creates the proxmox VM at the declared template VMID, imports the disk, sets hardware and cloud-init drive, marks as template. Skips if already a template at that VMID.

10. **VM lifecycle** workflow. Three steps wired into one operator command: prepare (keygen → SOPS + plaintext public-key field), provision (tofu apply with token-decrypt wrapper), configure (wait-for-connection, admin user finalization, NFS mount setup). Plus a destroy workflow that pre-flight-refuses if any service references the VM.

11. **Ingress regenerator** workflow. Iterates the service inventory, generates a Caddyfile and Pi-hole local DNS records, pushes both to their respective VMs and reloads.

One **orchestration module** (declarative + bash):

12. **Operator surface**: Just task file with intent-named commands; bash wrapper scripts for tofu (decrypt PVE tokens to env, run tofu, sensitive-flag the variable) and for ansible (decrypt SSH keys to tmpfs, set inventory-plugin pointer, trap-clean on exit). Pre-commit configuration wires schema + lint + fmt + validate + decrypt-check.

### Key architectural decisions

- **Yaml as source of truth.** Per-entity flat YAML files. No template-rendering layer above them. JSON Schema enforces shape. Both Ansible (via inventory plugin) and OpenTofu (via yamldecode) consume the same files.

- **Sibling SOPS files for secrets.** `<entity>.yaml` plaintext and `<entity>.sops.yaml` encrypted, co-located. SOPS encrypts values, not keys; structure remains greppable.

- **One SOPS file per entity, structured key entries.** Single SOPS file per host/VM/service holds all that entity's secrets. Each key entry is a structured block with metadata (type, created, rotation/version, public_key, private_key) so future automation can answer "how old is this" without re-derivation.

- **Single age recipient + offline backup recipient.** One operator key on the workstation, one offline backup. CI runner key deferred. Recovery from workstation loss requires the offline key.

- **Tofu never reads SOPS.** A wrapper script decrypts only the PVE API tokens into ephemeral environment variables before invoking tofu. Tokens marked `sensitive = true` so they do not appear in plan output or state. Keeps the secrets pipeline out of HCL entirely.

- **Standalone hosts, multi-aliased single-state tofu.** No proxmox cluster. One root tofu module with a provider alias per host, one state file for the whole fleet. Provider alias map generated from the host inventory.

- **bpg/proxmox** as the OpenTofu provider, on the basis of active maintenance and feature coverage.

- **Hard-cutover rotation policy** for all credential rotations. No grace-period overlap. Console access is the recovery path for hosts; reprovision is the path for VMs.

- **Bootstrap idempotency via refusal**, not silent skip. Bootstrap commands fail if the entity is already bootstrapped; rotation commands are separate and explicit.

- **Cloud-init for VM first-boot only.** Minimum viable: admin user, SSH key, hostname, network. Everything else is ansible. Cloud-init is one-shot; idempotent ongoing config is ansible's domain.

- **Podman Quadlets default for services, native escape hatch.** Multi-container as first-class. Podman secrets via `_FILE` env convention. Per-service networks. Bind-mount volumes under a predictable path on the VM so backups capture them via VM snapshot.

- **Single Caddy ingress VM, Pi-hole + Unbound DNS VM, Let's Encrypt DNS-01 via Cloudflare.** All `*.fearn.cloud` resolves to the ingress VM; Pi-hole serves the records on the LAN. TLS certs issued out-of-band via DNS-01.

- **PBS on neuromancer, NFS datastore on TrueNAS, client-side encryption from day one.** Per-VM backup config with global defaults. Off-site replication deferred.

- **NFS mounts as systemd .mount units** with global topology in shared vars and per-VM mount declarations. Per-container `requires_mounts:` for quadlet ordering. UID/GID convention coordinated with TrueNAS dataset ownership.

- **Just** for orchestration (not Make). Roles-based ansible. JSON Schema + cross-file validator for validation. Pre-commit hooks for schema, lint, fmt, validate, decrypt-check.

- **Custom inventory plugin** as the bridge. SSH keys decrypted to RAM-backed tmpfs at the start of each operator command, trap-cleaned on exit. Ansible never sees the encrypted form; persistent disk never sees the decrypted form.

### Schema additions captured

The host yaml schema includes connection metadata, network bridges with explicit `managed` ownership, documented storage IDs used for VM validation, PVE users with multi-role token declarations, GPU passthrough mode (sriov/full/none with vendor and IOMMU type), and an explicit list of templates the host should hold. Storage registration and datacenter configuration are not Host Configure automation contracts in this slice.

The VM yaml schema includes vmid, placement (target host), source template, hardware overrides, network interfaces (static IP), cloud-init essentials (hostname), optional GPU PCI device assignment, optional Mounts referencing Datasets with explicit protocol and access policy, optional backup schedule with retention, and a populated-by-prepare plaintext public-key field.

The service yaml schema includes hostname, backend (VM and port — list for HA cases), ingress config (enabled, exposure, TLS strategy), auth, and a deploy block branching on `type: quadlet | native`. Quadlet deploys carry a network name and a list of containers (image, ports, volumes, env, env-from-secrets, depends_on, requires_mounts). Native deploys carry package name, optional apt-repo reference, service name, and config-file templates with reload-vs-restart flags.

The template yaml schema includes name, vmid (in 9000-9999 range), source URL with required checksum, virt-customize ops, and hardware defaults.

Global vars hold domain, NTP, DNS, timezone, default proxmox config, default vm admin user spec, NAS endpoint and protocol defaults, named apt repos, and global backup defaults.

## Testing Decisions

### What makes a good test in this project

Tests assert external behavior visible at the module's interface — what the module accepts and what it produces or does — not the internal sequence of how it produces it. For the inventory plugin: assert that given a fixture inventory directory, the plugin returns the expected host-and-group structure. Do not assert which internal helper functions get called or in what order. The renderers should be tested by giving a fixture service yaml and asserting on the rendered unit-file content. The cross-file validator should be tested with curated valid and invalid inventory trees and assertions on the returned error list.

Tests should be fast enough to run in pre-commit (< 5 seconds total for the unit-tested modules) and should not require Proxmox, TrueNAS, network access, or any non-deterministic environment.

### Modules being tested in v1

- **Inventory plugin** — unit tests with fixture inventory directories. Cover: yaml loading variants, SOPS decryption (using a test age key), group construction, hostvar shaping, missing-file resilience.
- **Cross-file validator** — unit tests with curated valid and invalid trees. Cover each rule independently plus combination cases.
- **Quadlet renderer** — golden-file tests: take a fixture service yaml, render the role, assert on produced unit-file content. Cover single-container, multi-container, secrets injection, networks, NFS-mount dependencies, image pinning variants.
- **Native renderer** — golden-file tests: same shape as quadlet renderer. Cover apt-repo handling, reload-vs-restart logic, multi-config-file services.
- **JSON Schemas** — fixture-based: a directory of valid examples (must pass) and invalid examples (must fail with expected error path).

### Modules deferred until CI exists

- **Tofu yaml-to-resource bridge** — `tofu validate` and plan-on-fixture would be the right approach, but requires a CI-runnable tofu environment. Defer.
- **Host bootstrap, host configurator, template builder, VM lifecycle, ingress regenerator** — all touch real SSH, real Proxmox APIs, real VMs. Integration tests against a throwaway Proxmox host are the only meaningful test surface; defer until CI is in place to host such an environment.
- **Operator surface** — bash + just; smoke-tested by use.

### Prior art

None. Greenfield project; no existing test patterns to mirror. Test scaffolding (Python pytest for the Python modules, a thin assertion harness for the ansible-role golden-file tests) is part of the v1 work.

## Out of Scope

- **CI runner setup.** The system is designed for single-operator local execution. Adding a CI runner is a known future addition that requires generating a runner age key and re-encrypting via `sops updatekeys`. Integration tests for workflow modules are also gated on this.
- **Off-site backup of PBS.** Acknowledged gap. Local-only backups do not survive a site loss (TrueNAS shares the site). Off-site is its own subproject (provider selection, encryption-in-transit policy, restore drills).
- **Host firewall** (PVE firewall or host-level nftables/ufw). Risks lock-out, not blocking v1.
- **Monitoring and observability stack.** Defer to when the service stack stabilizes.
- **VM disk passthrough schema additions.** Only needed if a future PBS deployment moves from NFS to passed-through raw disks.
- **Renovate / automated image-tag bumps.** The service deploy flow supports manual tag bumps via PR; renovate is an easy add-on but not required for v1.
- **Pi-hole + Unbound architecture refinement.** The service exists in v1; the exact split (single container with both vs two containers) is implementation-time.
- **Workload assignment.** Which Plex VM lives where, which database hosts what — these are post-v1 decisions enabled by v1's building blocks.
- **HA / multi-host service redundancy.** No active-active or hot-standby; loss of a host means downtime for VMs on that host until manual intervention.
- **Proxmox host installation, BMC/IPMI configuration, boot disk partitioning.** These are runbook steps, not automation targets.
- **Storage pool creation and registration.** Storage stays operator-controlled. Host yaml documents storage IDs for VM validation, but Ansible does not create pools or register `storage.cfg` entries in this slice.
- **TrueNAS write reconciliation.** TrueNAS is an external dependency. Ordinary Dataset creation/deletion/repair is out of scope; initial NAS Reconcile may be a read-only plan before fortress-owned Share writes are automated.

## Further Notes

- The full architectural decisions and reasoning are captured in [docs/architecture.md](../architecture.md) — that document is the canonical reference; this PRD is the work-tracking artifact derived from it.
- The repository is greenfield as of this PRD's date; there is no prior code to refactor and no migration path to design. Implementation can flow in any order subject to dependencies sketched in the bring-up sequences (inventory plugin and decrypt wrapper come first because everything else relies on them).
- A natural first vertical slice is: inventory plugin + cross-file validator + decrypt-keys script + host-bootstrap + host-configure (the smallest set that demonstrates yaml-as-source-of-truth end-to-end against one host). The second slice adds VM templates + VM lifecycle + tofu bridge. The third slice adds service deployment + ingress regenerator + Caddy + Pi-hole. PBS and NFS integration thread through the second and third slices.
- This PRD would be filed with the `needs-triage` label in a tracker. As of writing, no tracker is configured for this repository. When tracker setup is completed (`/setup-matt-pocock-skills` or equivalent), this PRD can be ported with no content changes.
