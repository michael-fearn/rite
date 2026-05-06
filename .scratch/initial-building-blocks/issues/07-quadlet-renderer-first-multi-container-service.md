Status: needs-triage

## Parent

docs/prds/initial-building-blocks.md

## What to build

Service deployment via Podman Quadlets as the default substrate. Multi-container layouts are first-class. Podman secrets are injected via the `_FILE` env convention; each Service runs on an isolated Podman network unless it joins a same-VM Service Group; Service-owned container volumes are bind-mounts under `/srv/services/<service>/`; Export-backed volumes infer NFS Mount ordering and may bind the root of the Mount; image tags are pinned and auto-update is disabled.

The initial renderer uses rootful system Quadlets; fortress treats VM placement as the Service security boundary.

## Acceptance criteria

- [ ] Service yaml schema with `deploy.type: quadlet`: hostname, optional `service_group`, singular backend (VM + port), ingress block (enabled/exposure/TLS strategy/auth), optional Service Data Owner, deploy block with list of containers (image, structured publish ports, source/target volumes, env, secrets, depends_on)
- [ ] Optional Service Data Owner (`storage.uid`/`storage.gid`) creates/chowns Service-owned paths only; Export-backed Volume ownership remains governed by VM Mount/NAS conventions
- [ ] Quadlet Services may publish multiple TCP/UDP ports, but exactly one TCP-capable Published Port with `ingress: true` satisfies the HTTP-family Ingress Backend when ingress is enabled
- [ ] Quadlet renderer ansible role produces `.container`, `.network`, dependency-aware unit options
- [ ] Quadlets are rendered as rootful system units; rootless user Quadlets are out of scope for this issue
- [ ] `depends_on` validates same-Service container references, rejects cycles, and renders start-order/stop-coupling systemd unit dependencies without promising application readiness
- [ ] Podman secrets created from `secrets:` in the Service Sibling SOPS File, installed with service-scoped names, and consumed only via env vars ending in `_FILE`
- [ ] Non-secret `env` is declared in Service yaml; `env` and Quadlet Fragment `Environment=` entries cannot override generated secret `_FILE` env vars or each other
- [ ] Each Service gets its own Podman network by default; Services in the same Service Group share a group network
- [ ] Deploying one Service ensures its isolated or Service Group network exists but does not deploy other Services in the Service Group
- [ ] Container `name` becomes the Podman network DNS alias, while rendered container identity is service-scoped as `<service>-<container>`; validator rejects alias collisions within each Service or Service Group network
- [ ] Runtime artifacts use `fortress-` names: container units and Podman container names as `fortress-<service>-<container>`, isolated networks as `fortress-<service>`, and Service Group networks as `fortress-group-<service_group>`
- [ ] Container volumes bind-mounted under a predictable path (e.g., `/srv/services/<name>/`)
- [ ] Export-backed volumes translate to bind mounts and add `Requires=` + `After=` on the matching `.mount` unit; unusual extra native options use validated Quadlet Fragments
- [ ] Quadlet Fragment sidecar files use native Quadlet syntax but cannot override fortress-owned generated keys such as image, container identity, network, published ports, volumes, secrets, or generated dependencies
- [ ] Quadlet Fragments live under `inventory/services/<service>.quadlet.d/` as `<container>.container` fragments plus optional `network.network`; unknown fragment filenames are invalid
- [ ] Quadlet Fragments are plaintext-only and must not contain secret values; all Service secrets go through the Service Sibling SOPS File and `_FILE` injection
- [ ] Quadlet Fragment validation derives forbidden keys from the generated Quadlet for that Service/container; repeated additive keys such as `Unit.Requires`, `Unit.After`, and `Unit.Wants` may add values without replacing/removing generated dependencies
- [ ] Images require either a non-`latest` tag or a digest; untagged images and `:latest` are rejected; auto-update is disabled
- [ ] Golden-file tests cover: single-container, multi-container, secrets injection, networks, NFS-mount deps, image pinning variants
- [ ] Cross-file validator extended: all Published Port collisions on the same VM, hostname uniqueness for ingress-enabled Services, VM ref resolution
- [ ] Validator requires `hostname` only when `ingress.enabled: true`; duplicate hostname checks apply only to ingress-enabled Services
- [ ] Ingress defaults: `enabled: true` when `hostname` is present, `enabled: false` when absent; enabled Ingress defaults to `exposure: lan_only`, `tls: letsencrypt_dns`, and `auth.type: none`
- [ ] Cross-file validator treats `service_group` as a globally unique Service Group name and rejects a Service Group whose Services point at different Backend VMs
- [ ] `just service-deploy service=<name>` deploys or redeploys a single service
- [ ] `service-deploy` requires the Backend VM Sibling SOPS File for SSH and requires the Service Sibling SOPS File only when containers declare Service Secrets
- [ ] Redeploy prunes only fortress-rendered Quadlet units for the Service and obsolete service-scoped Podman secrets; it never prunes `/srv/services/<service>/` data
- [ ] Redeploy performs a full Service restart in dependency order: stop containers in reverse topological order and start them in topological order; avoiding data loss or bad state takes priority over zero-downtime updates
- [ ] If a container fails to start, deploy aborts remaining starts, surfaces the failed unit name and relevant journal/status guidance, and leaves rollback as an explicit operator action
- [ ] `runbooks/new-service.md` written
- [ ] Live acceptance demo deploys a contrived but real-world-shaped multi-container Service on a VM: web + postgres-like + redis-like containers, Service Secret, Service-owned volume, Export-backed root Mount volume, `depends_on`, multiple Published Ports with one Ingress Backend, optional Service Data Owner, and one validated Quadlet Fragment

## Out of scope

- Service deletion/destruction is not automated in this issue. `service-deploy` only deploys or redeploys a declared Service and prunes obsolete rendered artifacts within that Service; a later `service-destroy` workflow must define safe removal while preserving Service data by default.
- Compatibility with the pre-issue-07 scaffolded Quadlet shape is out of scope; existing fixtures should be rewritten to the new schema rather than supported through a migration layer.

## Blocked by

.scratch/initial-building-blocks/issues/06-nfs-integration.md
