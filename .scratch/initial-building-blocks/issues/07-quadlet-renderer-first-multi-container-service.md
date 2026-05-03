Status: needs-triage

## Parent

docs/prds/initial-building-blocks.md

## What to build

Service deployment via Podman Quadlets as the default substrate. Multi-container layouts are first-class. Podman secrets are injected via the `_FILE` env convention; each service runs on its own podman network; container volumes are bind-mounts under a predictable VM path; `requires_mounts:` wires NFS mount dependencies; image tags are pinned and auto-update is disabled.

## Acceptance criteria

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

## Blocked by

.scratch/initial-building-blocks/issues/06-nfs-integration.md