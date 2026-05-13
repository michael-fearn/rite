# fortress

Homelab infrastructure automation for a fleet of standalone Proxmox 9 machines. The operator declares desired state in flat per-entity YAML files; tooling converges live infrastructure toward that declared state through workflow-specific ceremonies.

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

**Template Verification VM**:
A deliberately disposable VM provisioned from a Template on a specific Host to prove the Template satisfies the fortress VM lifecycle contract before ordinary VMs depend on it there.
_Avoid_: test guest, smoke instance.

**Operational VM**:
A VM reserved for fortress workflows rather than long-lived Service-bearing use.
_Avoid_: utility instance, temp VM.

**Template Verification Policy**:
The fleet-level declaration of the reusable VMID, hardware, storage, and IP allocation used when creating Template Verification VMs across Hosts.
_Avoid_: per-host test file, fixture inventory.

**Acceptance Policy**:
A fleet-level declaration of the reusable VMIDs, hardware, storage, and IP allocations used when an Acceptance Test creates disposable Operational VMs.
_Avoid_: hard-coded test constants, fixture inventory.

**Primary Acceptance VM**:
The generated temporary Operational VM that hosts the resource being proven by a multi-VM Acceptance Test.
_Avoid_: service VM, test host, first VM.

**Peer Acceptance VM**:
The generated temporary Operational VM that verifies a multi-VM Acceptance Test from outside the Primary Acceptance VM.
_Avoid_: secondary VM, client VM, second VM.

**Template**:
A stopped Proxmox VM marked `template: 1` with a cloud-init drive, declared in `inventory/templates/<name>.yaml`. Used as the clone source for new VMs. Lives on a specific Host.
_Avoid_: image (reserve for the upstream Cloud Image).

**Cloud Image**:
The upstream qcow2 (Debian / Ubuntu) that a Template is built from. Pinned by SHA-512 checksum.
_Avoid_: ISO, base image.

**Service**:
A deployed application or co-located group of containers, declared in `inventory/services/<svc>.yaml`. Runs inside a VM. Substrate is either Quadlet (default) or Native.
_Avoid_: app, workload; "systemd service" (always qualify as "systemd unit").

**Service Group**:
A named set of one or more Services on the same VM that intentionally share a VM-local Podman network for private Service-to-Service communication.
_Avoid_: stack (too Compose-specific), app suite.

**Media VM**:
The Apps VLAN VM that runs media playback, request, catalog, and indexer Services such as Jellyfin, Overseerr, Sonarr, Radarr, Lidarr, Prowlarr, and Bazarr.
_Avoid_: media automation VM, Jellyfin VM.

**Download VM**:
The Apps VLAN VM that runs downloader Services such as qBittorrent, SABnzbd, NZBGet, and VPN-bound download components.
_Avoid_: downloader container, media automation VM.

**Immich VM**:
The Apps VLAN VM that runs the Immich Service Group, including Immich application containers, Postgres, and Redis.
_Avoid_: photos VM, shared database client.

**File Browser VM**:
The Apps VLAN VM that fronts the personal media Dataset for Trusted-only file access.
_Avoid_: files container, NAS UI.

**Vaultwarden VM**:
The Apps VLAN VM that runs Vaultwarden with VM-local primary data.
_Avoid_: password manager container, shared secrets VM.

**Backend**:
The VM (and TCP port) that the Ingress reverse-proxies a Service to. Declared as `backend.vm` and `backend.port`. Becomes a list when the Service is HA.
_Avoid_: upstream (overloaded with apt/git senses).

**Published Port**:
A VM-local port exposed by a Quadlet container for another VM or the Ingress to reach; defaults to loopback binding and TCP unless declared otherwise.
_Avoid_: exposed port (overloaded between container metadata and host publishing).

**Service Data Directory**:
The VM-local directory tree under `/srv/services/<service>/` that holds Service-owned bind-mounted data.
_Avoid_: app folder, container data path.

**Service Data Owner**:
The numeric UID/GID fortress applies to a Service's Service Data Directory when declared.
_Avoid_: app user (image-specific), container user.

**Service Path**:
A path declared by a Service relative to its Service Data Directory.
_Avoid_: host path (too broad), local volume path.

**Share-backed Volume**:
A Service container bind mount whose source references a VM Mount's Share and whose target is a container path.
_Avoid_: NFS volume (the Service references the VM-side Mount, not NFS topology directly).

**Entity**:
A Host, VM, Service, or Dataset. The thing each `<entity>.yaml` (and optional `<entity>.sops.yaml`) describes.
_Avoid_: object, record.

**Inventory**:
The set of per-entity YAML files at `inventory/{hosts,vms,services,datasets,nas}/`. Source of truth for all declared state.
_Avoid_: catalog, registry.

**Infrastructure VLAN**:
VLAN 40 (`10.40.0.0/24`), the routed network for static infrastructure Services such as the Ingress.
_Avoid_: management network, apps network.

**Trusted VLAN**:
VLAN 20 (`10.20.0.0/24`), the routed network for admin workstations flagged as trusted by router policy.
_Avoid_: ordinary client network, user LAN.

**Known VLAN**:
VLAN 25 (`10.25.0.0/24`), the routed network for ordinary non-admin clients.
_Avoid_: trusted network, guest network.

**IoT VLAN**:
VLAN 30 (`10.30.0.0/24`), the routed network for appliance-style clients that are denied internal access by default.
_Avoid_: smart home LAN, trusted devices.

**Guest VLAN**:
VLAN 70 (`10.70.0.0/24`), the internet-only client network with no access to internal DNS or internal VLANs.
_Avoid_: visitor LAN, untrusted LAN.

**DMZ VLAN**:
VLAN 60 (`10.60.0.0/24`), the future public-service network with a separate ingress and authentication stack from internal Services.
_Avoid_: public app subnet, external ingress.

**Firewall Matrix**:
The implementation-facing source of truth for VLAN layout, service placement intent, and inter-VLAN access expectations.
_Avoid_: router config, firewall export.

### Operator and ceremony

**Operator**:
The single human running fortress. The only intended persona; "future-self on a new workstation" is the only second viewer.
_Avoid_: user, admin.

**Remote Operator Workstation**:
A trusted workstation-like environment outside the local admin network that can run full fortress Operator workflows through tailnet reachability.
_Avoid_: dev VM, remote editor, jump box.

**Remote Operator Session**:
A deliberately unlocked period during which a Remote Operator Workstation has the credentials needed to run fortress Operator workflows.
_Avoid_: permanent remote access, always-on dev credentials.

**Hosted Tailnet**:
The Tailscale-managed tailnet used as the immediate remote-access control plane before the Headscale VM is ready.
_Avoid_: Headscale, local tailnet, VPN.

**Tailnet Subnet Router**:
A tailnet-enrolled network router that advertises selected fortress VLAN routes to Remote Operator Workstations.
_Avoid_: installing Tailscale everywhere, VPN VM.

**Tailnet Auth Key**:
An encrypted Tailscale enrollment credential used by the Tailnet Subnet Router during Configure.
_Avoid_: VPN password, login token, machine credential.

**Bootstrap**:
The one-shot transition of a freshly-installed Host from the shared bootstrap SSH key to a unique per-host SSH key stored encrypted in the repo. Refuses to re-run.
_Avoid_: init; provision (reserve for the tofu step on VMs).

**Prepare**:
The VM-side equivalent: generate the per-VM SSH keypair, write the private half encrypted, write the public half plaintext into the VM yaml. Refuses to re-run. Precedes `tofu apply`.
_Avoid_: setup.

**Configure**:
An idempotent operator workflow that converges a Host or VM to its declared state, usually by wrapping an Ansible run. Re-runnable.
_Avoid_: provision (reserve for tofu).

**VM Lifecycle Convergence**:
The VM workflow that uses Prepare, OpenTofu-managed VM resources, and Configure to move a declared VM toward its desired state.
_Avoid_: VM Reconcile, VM sync.

**Service Deploy**:
The Service workflow that converges one declared Service's VM-local runtime artifacts and running units.
_Avoid_: Service Reconcile, app deploy.

**Ingress Regeneration**:
The operator workflow that regenerates and reloads Ingress routing and Ingress DNS Records from current Inventory.
_Avoid_: Service Deploy, DNS deploy.

**NAS Reconcile**:
An operator workflow that validates declared Datasets and converges derived Shares without deleting ordinary Dataset contents.
_Avoid_: configure NAS, sync shares.

**NAS Reconcile Plan**:
The read-only first phase of NAS Reconcile that compares declared Dataset and derived Share intent with NAS reality without mutating TrueNAS.
_Avoid_: dry run (too generic), manual checklist.

**VM Lifecycle Contract**:
The minimum first-boot guarantees a Template-backed VM must satisfy before Configure can own it: cloud-init completes, the configured VM admin user exists, the VM admin SSH public key is authorized, passwordless sudo works, and hostname is applied.
_Avoid_: smoke test contract, guest readiness.

**Acceptance Test**:
A non-precommit test that proves an operator-facing resource contract by interacting with a live Host, VM, or disposable Operational VM.
_Avoid_: smoke test, integration test (when live infrastructure is required).

**Destroy**:
The VM lifecycle workflow that removes a provisioned Proxmox VM and, after successful removal, deletes the VM's Sibling SOPS File; deleting the VM yaml is an explicit opt-in choice.
_Avoid_: cleanup (too broad).

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

**Service Secret**:
An encrypted structured entry in a Service's Sibling SOPS File whose `value` is installed as a Podman secret and consumed through the Service application's native `_FILE` environment variable when one exists.
_Avoid_: environment secret (the secret value is not an environment variable).

### Service substrate

**Quadlet**:
A systemd unit declaring a Podman container, network, or volume; rendered onto the VM from the Service yaml. The default service substrate.
_Avoid_: pod, compose service.

**Quadlet Fragment**:
A native Quadlet sidecar fragment for options fortress does not model directly, validated so it cannot override fortress-owned invariants.
_Avoid_: raw config (too vague), compose override.

**Container Dependency**:
A same-Service start-order and stop-coupling relationship between Quadlet containers.
_Avoid_: readiness check, health dependency.

**Container Alias**:
The VM-local Podman network DNS name for a Service container, taken from the container's declared name.
_Avoid_: hostname (reserved for Service and VM naming).

**Native (Deploy)**:
The escape-hatch substrate: an apt package plus a systemd unit, configured by Ansible templates. Used when a Service is genuinely better not containerised (Caddy is the canonical case).
_Avoid_: bare-metal (the VM is still a VM); package install.

**Ingress**:
The VM named `internal-ingress-vm`, placed on the `straylight` Host, that terminates TLS and reverse-proxies internal HTTP traffic to backing Services.
_Avoid_: edge, gateway, proxy (reserve "proxy" for the verb).

**Ingress DNS Record**:
A DNS VM local IPv4 A record for an Ingress route hostname that resolves to the Ingress VM address.
_Avoid_: Backend DNS record, wildcard record, CNAME.

**Ingress DNS Record Set**:
The fortress-owned generated-file set of Ingress DNS Records applied to DNS Services during ingress regeneration.
_Avoid_: manual Pi-hole records, ad hoc DNS entries.

**Ingress DNS Target**:
A DNS Service-level declaration that receives the generated Ingress DNS Record Set during Ingress Regeneration.
_Avoid_: DNS peer, DNS VM target.

**Host Ingress Route**:
A management-plane Ingress route from a hostname to a physical Host's management address and web UI port.
_Avoid_: Service, Backend, VM route.

**DNS Capability**:
A Service-level DNS behavior declaration on a DNS Service, such as accepting generated Ingress DNS Records.
_Avoid_: VM role, inferred DNS feature.

**Pi-hole-backed DNS Service**:
A DNS Service whose supported provider for generated DNS records is Pi-hole.
_Avoid_: arbitrary dnsmasq host, generic file target.

**DNS VM**:
An Infrastructure VLAN VM that runs Pi-hole and Unbound as a complete internal resolver.
_Avoid_: DNS server, resolver appliance.

**Forgejo VM**:
The Infrastructure VLAN VM that runs Forgejo and does not run CI runner workloads.
_Avoid_: git server, runner host.

**Forgejo Runner VM**:
A future VM for Forgejo runner workloads, separate from the Forgejo VM.
_Avoid_: co-located runner, build container on Forgejo.

**Observability VM**:
The Infrastructure VLAN VM that runs metrics, alerting, dashboard, log aggregation, and blackbox-check Services.
_Avoid_: monitoring stack, logs box.

**Headscale VM**:
The Infrastructure VLAN VM that runs the local-only tailnet control plane.
_Avoid_: public VPN server, remote enrollment service.

**Identity VM**:
The Infrastructure VLAN VM that runs Authentik as the local-only identity provider for internal ingress authentication.
_Avoid_: SSO box, auth server.

**Exposure**:
A Service's ingress visibility, declared on `ingress.exposure` (e.g. `lan_only`). The full enum is not yet pinned — see flagged ambiguities.

**Ingress Auth**:
A Service's explicit internal ingress authentication requirement, satisfied by the Identity VM when enabled.
_Avoid_: global auth, auth-by-default.

### Backups and storage

**PBS**:
Proxmox Backup Server, deployed in this project as a VM on the `straylight` Host.
_Avoid_: PVE backup (a separate Proxmox feature).

**Datastore**:
PBS's storage location; an NFS Share from TrueNAS, mounted into the PBS VM.
_Avoid_: backup pool.

**NAS Endpoint**:
A named external NAS system fortress can reconcile against.
_Avoid_: NAS server (too broad), TrueNAS host (implementation-specific).

**NAS Software Version**:
The declared product/version release currently running on a NAS Endpoint.
_Avoid_: API version, client version.

**Management Address**:
The address fortress uses to reach a NAS Endpoint's management API.
_Avoid_: NAS address, server address.

**Share Address**:
The stable client-facing address VMs use to consume Shares from a NAS Endpoint.
_Avoid_: NAS address, management address.

**NAS Reconcile Credential**:
An operator-provided NAS API credential used by NAS Reconcile to inspect Datasets and manage Fortress-owned Shares.
_Avoid_: NAS admin token, TrueNAS root credential.

**NAS Reconcile API Key Name**:
The TrueNAS-side name `fortress-nas-reconcile` for the NAS Reconcile Credential.
_Avoid_: generic api key, admin key.

**NAS Credential Ceremony**:
The manual operator process of creating both NAS API credentials outside fortress before storing them in the NAS Endpoint's Sibling SOPS File.
_Avoid_: credential provisioning, credential automation.

**Acceptance NAS Credential**:
An operator-provided NAS API credential used only by Acceptance Tests that must create or destroy Ephemeral Datasets.
_Avoid_: test NAS admin token, ordinary NAS Reconcile Credential.

**Acceptance NAS API Key Name**:
The TrueNAS-side name `fortress-acceptance-ephemeral` for the Acceptance NAS Credential.
_Avoid_: test key, broad acceptance key.

**Credential Source**:
The non-secret location from which an operator workflow obtains a credential.
_Avoid_: credential value, secret source.

**Dataset**:
A durable TrueNAS Dataset whose contents are protected independently from any access surface.
_Avoid_: share, export, mount.

**Adopted Dataset**:
An ordinary Dataset declared in Inventory so fortress can validate its expected state without owning its creation or deletion lifecycle.
_Avoid_: managed dataset, imported share.

**Ephemeral Dataset**:
A deliberately disposable Dataset created for an Acceptance Test and destroyed when that test is complete.
_Avoid_: temp share, test export.

**Share**:
A named NAS-side access declaration for data exposed to VMs or Services.
_Avoid_: export; mount (the VM-side artefact, not the NAS-side declaration).

**Derived Share**:
A Share constructed from VM or Service access expectations rather than declared directly on a Dataset.
_Avoid_: embedded share, dataset share.

**Fortress-owned Share**:
A Derived Share marked as managed by fortress so NAS Reconcile may update or destroy it.
_Avoid_: manual share, unmanaged share.

**NFS Share**:
A Share exposed over NFS from TrueNAS.
_Avoid_: NFS export.

**Mount**:
A systemd `.mount` unit on a VM that mounts a Share at a declared path. Ordering anchor for Service consumption via Share-backed Volumes.

**Mount Name**:
The stable name a Service uses to reference a VM Mount.
_Avoid_: mount path, share name.

**Access Policy**:
The requested read/write and client-access rules for a VM's Dataset access.
_Avoid_: permissions (too broad), ACL (too TrueNAS-specific).

## Relationships

- A **Host** runs zero or more **VMs** and holds zero or more **Templates**.
- A **VM** is provisioned from one **Template** and runs zero or more **Services**.
- A **Remote Operator Workstation** sits outside the fortress-managed infrastructure failure domain.
- A **Remote Operator Workstation** is trusted to run the same Operator workflows as the local workstation.
- A **Remote Operator Workstation** gains workflow authority only during a **Remote Operator Session**.
- A **Remote Operator Workstation** uses the **Hosted Tailnet** for immediate remote reachability while the **Headscale VM** is not ready.
- A **Remote Operator Workstation** reaches fortress networks through a **Tailnet Subnet Router** rather than direct Tailscale installs on each VM.
- The initial **Tailnet Subnet Router** is `tailnet-subnet-router-vm` at `10.20.0.20/24` on the `molly` **Host**.
- The initial **Tailnet Subnet Router** is declared as an ordinary long-lived **VM** in **Inventory**.
- The initial **Tailnet Subnet Router** is attached to the **Trusted VLAN** because it extends trusted Operator reachability.
- The **Tailnet Subnet Router** is routing-only; it is not a Remote Operator Workstation.
- The **Tailnet Subnet Router** enrolls into the **Hosted Tailnet** using a **Tailnet Auth Key** stored in its **Sibling SOPS File**.
- **Tailnet Subnet Router** setup is VM-level configuration, not a **Service**.
- During early bring-up, the **Tailnet Subnet Router** advertises every fortress VLAN route needed for remote recovery and implementation work.
- The **Firewall Matrix** supersedes earlier service placement and NAS mount layout notes.
- The **Ingress** VM is attached to the **Infrastructure VLAN** at `10.40.0.16/24`.
- The primary **DNS VM** is `dns-primary-vm` at `10.40.0.11/24` on the `straylight` Host.
- The secondary **DNS VM** is `dns-secondary-vm` at `10.40.0.18/24` on the `molly` Host.
- Primary and secondary **DNS VMs** are functionally identical peers.
- The **Forgejo VM** is `forgejo-vm` at `10.40.0.12/24` on the `straylight` Host.
- **Forgejo Runner VMs** must not be co-located on the **Forgejo VM**.
- The **Observability VM** is `observability-vm` at `10.40.0.17/24` on the `straylight` Host.
- The **Observability VM** groups Prometheus, Alertmanager, Grafana, Loki, and Blackbox Exporter.
- The **Headscale VM** is `headscale-vm` at `10.40.0.14/24` on the `straylight` Host.
- The **Headscale VM** is local-only; remote devices must be enrolled while local or with a short-lived pre-auth key minted while local.
- The **Identity VM** is an Infrastructure VLAN **VM** and must remain local-only.
- The **Identity VM** is `identity-vm` at `10.40.0.19/24` on the `straylight` Host.
- Headscale does not depend on the **Identity VM** until a later explicit OIDC integration decision.
- A **Dataset** is declared in `inventory/datasets/<dataset>.yaml`.
- A **Service Group** contains one or more **Services** on the same **VM**.
- A **Service Group** name is globally unique within the **Inventory**.
- Media request and playback Services may share a **Service Group** when they have the same storage access and trust boundary.
- Download clients must run on a separate **VM** from media request and playback Services.
- The **Media VM** and **Download VM** both consume the media Dataset, while individual **Services** narrow their visible paths through **Share-backed Volumes**.
- The **Media VM** and **Download VM** mount the media Dataset read-write at the **VM** level, while individual **Services** use **Share-backed Volume** subpaths to narrow read/write exposure.
- Jellyfin uses read-only media library **Share-backed Volumes**.
- Overseerr does not consume the media Dataset unless a later explicit requirement appears.
- The **Immich VM** keeps Immich database and cache state VM-local and consumes the Immich Dataset for library storage.
- The **File Browser VM** is a standalone **VM** and is the only Apps VLAN **VM** that consumes the personal media Dataset.
- The **Vaultwarden VM** is a standalone **VM** and does not use NAS-backed live storage by default.
- The **Vaultwarden VM** is `vaultwarden-vm` at `10.50.0.11/24` on the `neuromancer` Host.
- The **Immich VM** is `immich-vm` at `10.50.0.12/24` on the `neuromancer` Host.
- The **Media VM** is `media-vm` at `10.50.0.13/24` on the `neuromancer` Host.
- The **Download VM** is `download-vm` at `10.50.0.14/24` on the `neuromancer` Host.
- The **File Browser VM** is `file-browser-vm` at `10.50.0.15/24` on the `neuromancer` Host.
- VMIDs `100`-`8899` are for ordinary **VMs**, `8900`-`8999` are for **Operational VMs**, and `9000`-`9999` are for **Templates**.
- VM names beginning with `tmp-` are reserved for generated temporary **VMs** and must not be checked in as ordinary Inventory.
- A **Template Verification VM** is provisioned from exactly one **Template** on exactly one **Host** and destroyed after verification.
- A **Template Verification VM** is an **Operational VM**.
- A **Template Verification Policy** defines the reusable slot from which each **Template Verification VM** is generated.
- An **Acceptance Test** may create or configure a disposable **Operational VM** when the contract can only be proven through live infrastructure.
- A multi-VM **Acceptance Test** uses generated temporary **Operational VMs** rather than checked-in ordinary **VMs**.
- A multi-VM **Acceptance Test** may designate one generated temporary **Operational VM** as the **Primary Acceptance VM** and another as the **Peer Acceptance VM**.
- Each workflow that needs reserved live-infrastructure slots owns its own **Acceptance Policy**.
- The Service-layer **Acceptance Test** owns a dedicated **Acceptance Policy** rather than reusing the NFS shared-mount policy.
- The Service-layer **Acceptance Test** generates and cleans up temporary Service inventory rather than requiring a checked-in ordinary **Service**.
- The Service-layer **Acceptance Test** includes **Service Secrets** so it proves the end-to-end Service deployment ceremony.
- The Service-layer **Acceptance Test** generates a temporary Service **Sibling SOPS File** through the ordinary SOPS encryption ceremony before running Service deployment.
- A failed Service-layer **Acceptance Test** with `keep_on_fail=true` preserves all generated inventory and live resources owned by that run for inspection.
- A **Service** has one **Backend** **VM** (a list when HA is needed).
- A **Service** may belong to at most one **Service Group**.
- A Quadlet **Service**'s **Backend** port must match exactly one **Published Port**.
- A **Published Port** may use TCP, UDP, or both; only TCP-capable Published Ports may satisfy a **Backend**.
- **Ingress** is HTTP-family routing only; non-HTTP Published Ports are exposed directly on the **Backend** VM rather than through Caddy.
- A **Published Port** must opt into **Ingress** routing explicitly; direct VM exposure is deliberate through its bind address.
- A **Published Port** bound to `0.0.0.0` is an explicit direct VM exposure to all VM interfaces.
- An **Ingress**-enabled Quadlet **Service** has exactly one TCP-capable **Published Port** marked for **Ingress** whose host port equals the **Backend** port.
- An **Ingress**-backed **Published Port** must bind to an address reachable from the **Ingress** **VM**; loopback binding is only for same-VM callers.
- A Service-layer **Acceptance Test** must prove direct **Published Port** reachability from the **Peer Acceptance VM** to the **Primary Acceptance VM**.
- A Service-layer **Acceptance Test** proves direct reachability through the tested **Service**'s **Backend** port, not through a separate test-only Published Port.
- A Service-layer **Acceptance Test** may additionally prove **Ingress** hostname reachability when the tested **Service** declares **Ingress**.
- A Service-layer **Acceptance Test** with multiple containers proves systemd unit activation, declared **Container Dependency** ordering, **Container Alias** resolution, and **Share-backed Volume** consumption.
- A Service-layer **Acceptance Test** proves **Share-backed Volume** consumption by serving a pre-written marker file from the **Primary Acceptance VM**'s **Mount** through the tested **Service**.
- A Service-layer **Acceptance Test** proves existing **Mounts** and **Share-backed Volumes** remain usable after a TrueNAS NFS service reload, without remounting VMs or redeploying Services.
- A Service-layer **Acceptance Test** treats fresh post-reload data flow through existing **Mounts** and **Share-backed Volumes** as the contract, not stable container process identity.
- A Service-layer **Acceptance Test** triggers the TrueNAS NFS service reload explicitly through the **Acceptance NAS Credential** rather than relying on **NAS Reconcile** to make a Share change.
- A Service-layer **Acceptance Test** proves **Service Secret** consumption by comparing a deterministic hash from inside the container without printing the secret value.
- User-facing HTTP Services on the **Media VM** and **Download VM** are exposed through the **Ingress** for DNS and TLS.
- Direct client access to media and download backend ports is reserved for explicit Trusted-only emergency or administration paths.
- A **Service Data Directory** belongs to exactly one **Service** and is the default root for Service-owned bind mounts.
- A **Service Data Owner** applies only to Service-owned data; Share-backed Volume ownership follows the VM Mount and NAS ownership convention.
- A **Service Path** is always explicit in Service yaml when a container uses Service-owned bind-mounted data.
- **Service Data Directory** contents are never pruned by Service deployment; Service renames and Service Path changes require explicit data migration.
- A **Share-backed Volume** automatically depends on the corresponding **Mount** before the container starts.
- A **Share-backed Volume** binds the root of a **Mount** with `source: /`.
- Fortress models Quadlet fields only when they enforce fortress invariants; other native Quadlet options belong in **Quadlet Fragments**.
- A **Container Dependency** does not prove application readiness; readiness remains the Service application's responsibility unless modeled separately later.
- A **Container Alias** must be unique within its Podman network; rendered container identity remains service-scoped as `<service>-<container>`.
- Fortress-owned runtime artifacts use a `fortress-` prefix; Podman container and systemd unit identity is `fortress-<service>-<container>`, while the **Container Alias** remains the declared container name.
- The **Ingress** **VM** routes traffic to **Services** by hostname.
- **Ingress** routes are hostname-only; path-based routing is deferred.
- The **Ingress** reverse-proxies each **Service** to its **Backend** **VM**'s declared static address and **Backend** port.
- A **Host Ingress Route** reverse-proxies to a physical **Host** management address rather than to a **Service** **Backend**.
- **Host Ingress Routes** are declared on Host inventory, not Service inventory.
- A **Host Ingress Route** must be explicitly enabled per **Host**; Host existence alone does not create management ingress.
- A Proxmox web UI **Host Ingress Route** hostname is explicitly written in Host inventory and must equal `<host>.<domain>` using the operator-facing **Host** name.
- A Proxmox web UI **Host Ingress Route** targets the Host's `network.management_address` and defaults to TCP port 8006.
- A **Host Ingress Route** must not derive its target from `proxmox.endpoint`.
- `proxmox.endpoint` remains a direct management/API endpoint for automation; **Host Ingress Routes** are for operator browser access and must not become a dependency of OpenTofu or Ansible workflows.
- A Proxmox web UI **Host Ingress Route** defaults to Trusted-only exposure, Let's Encrypt DNS-01 TLS, and no additional Ingress Auth.
- Caddy enforces Trusted-only access for Proxmox web UI **Host Ingress Routes** at the route level, because ordinary Service routes and Host management routes share the same **Ingress** **VM** address.
- Trusted-only **Host Ingress Route** source ranges are declared policy in **Inventory**, not hardcoded in the generator.
- Known, IoT, Guest, and DMZ clients must not reach Proxmox web UI **Host Ingress Routes** through the **Ingress**.
- A Proxmox web UI **Host Ingress Route** relies on Proxmox authentication for the first slice; additional **Ingress Auth** for Host management is deferred.
- **Ingress** terminates TLS and proxies to **Backends** and Proxmox web UI **Host Ingress Routes** over plain HTTP unless a future backend transport model says otherwise.
- **Ingress Regeneration** requires unambiguous static IPv4 addresses for the **Ingress** **VM** and every **Backend** **VM** it routes to.
- **Ingress** TLS for internal Service hostnames uses Let's Encrypt DNS-01 when `ingress.tls` is `letsencrypt_dns`.
- A **Service** needs a hostname only when **Ingress** is enabled.
- A **Service** must declare `ingress.enabled: true` explicitly to enable **Ingress**; a hostname alone does not enable **Ingress**.
- A **Service** that declares an `ingress` block must declare `ingress.enabled` explicitly.
- A **Service** must not declare a hostname when **Ingress** is disabled.
- A LAN-only **Ingress** hostname must be an explicit FQDN under the configured fleet domain.
- An **Ingress**-enabled **Service** defaults to LAN-only **Exposure**, Let's Encrypt DNS-01 TLS, and no **Ingress Auth** when those policy fields are omitted.
- When a mixed-protocol **Service** enables **Ingress**, its **Backend** port is the HTTP-family port used by **Ingress**; non-HTTP **Published Ports** remain direct VM exposure.
- **Ingress DNS Records** are generated only for **Services** with **Ingress** enabled.
- **Ingress DNS Records** are also generated for declared **Host Ingress Routes**.
- **Ingress DNS Records** are not generated for VMs merely because they exist, including the **Ingress** **VM** itself.
- The internal **Ingress DNS Record Set** includes only **Services** whose **Exposure** is `lan_only`.
- **Service** hostnames and **Host Ingress Route** hostnames share one generated **Ingress** hostname namespace and must not collide.
- **Ingress DNS Records** are generated per declared **Service** hostname; fortress does not create a wildcard internal record by default.
- **Ingress DNS Records** are IPv4 A records; IPv6 records are deferred until IPv6 VM addressing is modeled.
- An **Ingress DNS Record** points to the **Ingress** **VM**, not the route's target **Backend** **VM** or **Host**.
- The **Ingress DNS Record** target address is derived from the **Ingress** **VM** declaration in **Inventory**.
- **Ingress DNS Records** are applied to explicitly declared **Ingress DNS Targets**, not inferred from **DNS VM** names.
- An **Ingress DNS Target** is declared through a DNS **Capability** on a DNS **Service**.
- A DNS **Capability** declares its DNS provider explicitly; provider inference from Service names or container images is forbidden.
- The first supported **Ingress DNS Target** provider is a **Pi-hole-backed DNS Service**.
- Ingress regeneration authoritatively replaces the **Ingress DNS Record Set** from current **Inventory**, including removing stale generated records.
- The **Ingress DNS Record Set** must not include or delete manual records outside the fortress-owned generated surface.
- The **Ingress DNS Record Set** is rendered as a fortress-owned DNS configuration file on each **Ingress DNS Target**, rather than mutated through the Pi-hole API.
- Pi-hole-backed DNS **Services** use the `/etc/dnsmasq.d` compatibility surface for the **Ingress DNS Record Set**.
- A **Pi-hole-backed DNS Service** with Ingress DNS Records enabled implicitly requires `/etc/dnsmasq.d` compatibility during **Service Deploy**; **Ingress Regeneration** only writes and reloads the generated DNS file.
- Generated **Ingress** routes and **Ingress DNS Records** are ordered deterministically by route hostname.
- Absent planned DNS peers do not block regeneration.
- **Ingress Regeneration** updates and reloads generated routing and DNS files; it does not perform **Service Deploy** for the **Ingress** or DNS **Services**.
- **Service Deploy** owns stable **Ingress** installation and Caddy scaffolding; **Ingress Regeneration** owns the generated Caddy routes imported by that scaffolding.
- **Ingress Regeneration** is non-transactional but succeeds only when every targeted **Ingress** and DNS reload succeeds.
- Static validation proves **Ingress DNS Targets** are well-formed in **Inventory**; **Ingress Regeneration** proves live reachability and reload success.
- **Ingress Auth** is explicit per **Service** and is not applied globally by default.
- Current **Ingress Regeneration** supports only **Ingress Auth** type `none`; Authentik-backed route generation is deferred until that contract is modeled.
- The **Ingress** performs internal HTTP routing and TLS termination; the **Identity VM** does not replace the **Ingress**.
- The **Identity VM** provides **Ingress Auth** only for **Services** that explicitly declare it.
- The **Identity VM** is reached through the **Ingress** for normal Authentik user and admin flows.
- Direct access to the **Identity VM** backend is a Trusted-only recovery path.
- The **Known VLAN** reaches approved user-facing internal HTTP **Services** through the **Ingress** and does not reach backend or administration ports directly.
- The **IoT VLAN** is denied to internal VLANs by default except for DNS, time, and explicit per-device or per-Service exceptions.
- The **Guest VLAN** uses only UDM or approved non-internal DNS and does not resolve or reach internal `*.fearn.cloud` Services.
- The **DMZ VLAN** does not use the internal **Ingress** or **Identity VM**; future DMZ workloads will use a separate ingress and authentication stack.
- DMZ ingress rules are future-only and are not part of the internal firewall baseline.
- Every **Entity** may have a **Sibling SOPS File**.
- A **Service Secret** belongs to exactly one **Service** and is installed under a service-scoped Podman secret name.
- All **Service Secrets** for a **Service** live in that Service's **Sibling SOPS File**.
- A **Service Secret** stores its secret bytes under `value` and records `created` and `version` metadata alongside that value.
- A **Service Secret** name describes its purpose in fortress language, not the Service application's environment variable name.
- The Pi-hole web/API password for `dns-primary` is represented as the `web_api_password` **Service Secret**.
- The `dns-primary.fearn.cloud` hostname reaches the Pi-hole web UI through the **Ingress**; DNS resolver traffic to `dns-primary` remains direct TCP/UDP port 53 access to the **DNS VM**.
- **Ingress Regeneration** includes `dns-primary.fearn.cloud` in generated **Ingress** routes and **Ingress DNS Records** when `dns-primary` declares **Ingress**.
- `dns-primary` is both an **Ingress DNS Target** and an **Ingress**-enabled **Service** for its Pi-hole web UI.
- **PBS** backs up every **VM** with `backup.enabled: true`; **PBS** itself is a **VM**.
- A **NAS Endpoint** is an **Entity**.
- A **NAS Endpoint** has zero or more **Datasets**.
- A **NAS Endpoint** has exactly one **NAS Software Version**.
- A **NAS Endpoint** has one **Management Address** and one **Share Address**.
- A **NAS Reconcile Credential** belongs to exactly one **NAS Endpoint**.
- A **NAS Credential Ceremony** produces one **NAS Reconcile Credential** and one **Acceptance NAS Credential** for a **NAS Endpoint**.
- An **Acceptance NAS Credential** may mutate **Ephemeral Datasets** but is not used for ordinary fleet **NAS Reconcile**.
- NAS server and protocol defaults are global topology; **Datasets** are per-entity Inventory.
- **NAS Reconcile** validates **Datasets** and converges **Shares**.
- **NAS Reconcile** is conceptually API-backed; its first implementation may be a read-only **NAS Reconcile Plan**.
- **NAS Reconcile** runs before **Configure** for VMs that declare **Mounts**.
- **NAS Reconcile** does not roll back **Shares** after downstream **Configure** or Service deployment failures.
- Ordinary **NAS Reconcile** must refuse all **Dataset** write actions before contacting a NAS Endpoint.
- Service deployment validates Share-backed consumption but does not run **NAS Reconcile** implicitly.
- A **Datastore** uses the same **Dataset**, **Share**, and **Mount** model as other NAS-backed storage.
- A **Dataset** declaration includes the NAS endpoint it belongs to.
- A **Dataset** declaration includes an explicit `lifecycle`.
- **Dataset** `lifecycle` is `adopted` or `ephemeral`.
- A **Dataset** declaration represents a TrueNAS Dataset, not an arbitrary directory beneath one.
- A **Dataset** declaration uses its TrueNAS mount path as the canonical locator.
- **Ephemeral Datasets** are forbidden in ordinary fleet Inventory and appear only in Acceptance Test inventory.
- **Dataset** names are globally unique within **Inventory**.
- **Adopted Dataset** declarations require `owner.uid` and `owner.gid`.
- A **Dataset** may have zero or more **Shares**.
- An ordinary **Dataset** is an **Adopted Dataset** unless explicitly modeled otherwise.
- Dataset file ownership belongs to the **Dataset**, while protocol-specific access rules belong to the **Share** or **Mount**.
- Fortress validates that an **Adopted Dataset** exists at its declared NAS path with its expected root owner UID/GID.
- Fortress reports **Adopted Dataset** ownership drift by default rather than repairing it.
- An ordinary **Dataset** is never deleted by fortress, even if its declaration is removed from Inventory.
- An **Ephemeral Dataset** may be created and destroyed only for an **Acceptance Test**.
- A **Share** exposes exactly one **Dataset**.
- A **Share** with no remaining VM or Service declaration requiring it may be destroyed during NAS reconciliation.
- A **Share** is derived from VM or Service declarations, not embedded in a **Dataset** declaration.
- **NAS Reconcile** may mutate only **Fortress-owned Shares**.
- Every **Fortress-owned Share** carries a durable ownership marker.
- An unmanaged Share that could expose the same **Dataset** as desired fortress-owned Share intent blocks **NAS Reconcile** until the Operator resolves it.
- NFS Share client access is derived from VM static IP addresses.
- Derived NFS Shares allow explicit VM IP clients rather than broad networks by default.
- A **VM** that declares a **Mount** must have a static IP address in Inventory.
- **Share** identity is derived deterministically from Dataset, protocol, and compatible **Access Policies**.
- **Share** identity does not depend on **Mount Name**.
- A **Share** may serve multiple **VMs** when their access policies are compatible.
- **Access Policy** is declared as `access: read_only | read_write`.
- Protocol-specific Mount options may extend global defaults, but must not contradict **Access Policy**.
- Fortress must not merge **Access Policies** when doing so would widen any **VM** beyond its requested access.
- A **Share** is the NAS-side declaration; a **Mount** is the VM-side systemd unit that consumes one.
- A **VM** declares Dataset access by declaring a **Mount** with a required Share protocol.
- A **Mount** declaration uses flat fields: `name`, `dataset`, `protocol`, `mount_point`, and `access`.
- A **Mount** declaration always includes an explicit `mount_point`.
- Changing a declared **Mount**'s `mount_point` requires operator confirmation before **Configure** continues.
- Changing a declared **Mount**'s `access` requires operator confirmation before reconciliation continues.
- Removing a declared **Mount** requires operator confirmation before reconciliation continues.
- A **Mount** declares its Share protocol explicitly; **Datasets** are not protocol-specific.
- A **Service** consumes Dataset access through a **Share-backed Volume** that references a **Mount Name** on its **Backend** **VM**.
- **Mount Names** are unique within a **VM** and resolved relative to a Service's **Backend** **VM**.
- A **Service** must not create Dataset access without a matching **Mount** declaration on its **Backend** **VM**.
- A **Share-backed Volume** may narrow its **Mount**'s access mode, but must not widen it.
- A **Share-backed Volume** binds the root of a **Mount** only when `source: /` is explicit; otherwise its source is a safe relative subpath.
- A **Share-backed Volume** subpath under an **Adopted Dataset** must already exist unless an explicit creation workflow is modeled later.
- A declared **Mount** must be active and accessible during **Configure** before later VM configuration or Service deployment may rely on it.
- Service deployment validates the **Share-backed Volume** subpaths used by that **Service** before starting containers.
- A **Mount** with a declared ownership mapping must prove read/write/delete access as the mapped UID/GID during **Configure**.

## Example dialogue

> **Operator:** "I want to add Immich on a fresh VM. What do I touch?"
>
> **Future-self:** "Three new YAML files. One **VM** under `inventory/vms/`, one **Service** under `inventory/services/` with `backend.vm` pointing at the new VM, and the matching `<svc>.sops.yaml` for the DB password. The **Template** the VM clones from already exists on the **Host**. After commit, `just vm-up`, `just service-deploy`, `just ingress-regenerate`. The **Ingress** picks up the new hostname automatically — you don't touch Caddy by hand."

## Flagged ambiguities

- **"node" vs "host"**: In Proxmox parlance "node" is a cluster member; here we have no cluster, so "node" only ever means the PVE-internal identity (`pve_node_name`). All operator prose uses **Host**.
- **"template"**: Overloaded between the **Template** (a Proxmox VM marked `template: 1`), the `vm-templates/<name>.yaml` recipe that produces it, and Jinja templates inside Ansible roles. The first two are the same concept at recipe and instance layers; Jinja templates should always be qualified ("Jinja template" or "config template").
- **"service"**: Overloaded with "systemd service unit". A **Service** in this project is a deployed app (one yaml under `inventory/services/`); a systemd service unit is always qualified as "systemd unit".
- **Hostname conventions**: A **Service**'s `hostname` is the Ingress-only end-user FQDN (`photos.fearn.cloud`); a **VM**'s `cloud_init.hostname` is the short form (`web01`), with FQDN derived as `<short>.fearn.cloud`; a **Container Alias** is private Podman network DNS. The split is intentional, but easy to reverse by accident.
- **Non-Ingress Service names**: Deferred. A non-Ingress **Service** must not use `hostname`; direct DNS names for non-HTTP or administration surfaces need a separate modeled concept later.
- **Multi-address Ingress VM**: Deferred. The **Ingress DNS Record** target address is unambiguous while the **Ingress** **VM** has one client-facing static address; explicit address selection belongs in a later model if the **Ingress** **VM** gains multiple client-facing addresses.
- **Ingress health name**: Deferred. A dedicated health-check hostname would need its own explicit route concept; it is not implied by the **Ingress** **VM** existing.
- **`ingress.exposure` enum**: Only `lan_only` appears in [docs/architecture.md](docs/architecture.md). Whether `internet_exposed` (or similar) is a planned value, and what it would imply for the Caddy/Cloudflare wiring, is unresolved.
- **`ingress.auth` enum**: The Firewall Matrix requires **File Browser** to use **Ingress Auth**, but the current Service schema only accepts `auth.type: none`. Inventory may temporarily encode the Service as unauthenticated while preserving the policy gap here.
- **Multi-VM Backend**: Deferred. A **Service** has exactly one **Backend** for the initial Quadlet and Ingress implementation; HA Backend semantics will be designed when the Ingress supports multiple Backends.
- **Adopted Share**: Deferred. Existing manual Shares are not adopted by fortress; overlapping unmanaged Shares block **NAS Reconcile** until the Operator removes or otherwise resolves them.
- **Multi-interface NAS clients**: Deferred. Mount-bearing VMs currently require an unambiguous static IP address for NFS Share client access.
- **Dataset ACLs and modes**: Deferred. Dataset declarations model root owner UID/GID only; root-level Acceptance Test writes do not settle mapped UID/GID or ACL semantics.
- **Multi-interface NAS clients**: Deferred. Mount-bearing VMs currently require a static IP address; selecting among multiple VM client addresses will be modeled when multi-interface VMs need NAS access.
