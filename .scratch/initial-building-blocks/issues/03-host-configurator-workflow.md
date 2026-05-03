Status: needs-triage

## Parent

docs/prds/initial-building-blocks.md

## What to build

Convergence of a bootstrapped host to its declared state: repos, system hygiene, network bridges, storage registration, datacenter config, PVE users with multi-role tokens (auto-created and stored encrypted), GPU passthrough setup. Idempotent, never auto-reboots, tagged so individual scopes can be applied independently.

## Acceptance criteria

- [ ] Roles exist and are independently tagged: `proxmox_repos`, `system_hygiene`, `proxmox_network`, `proxmox_storage`, `proxmox_datacenter`, `proxmox_users`, `gpu_passthrough`
- [ ] PVE API token for tofu created during configurator run; written encrypted into the host's sops file
- [ ] GPU passthrough role supports SR-IOV (wintermute) and full passthrough (neuromancer, straylight) per host yaml declaration
- [ ] Storage role registers operator-created pools (does not create them)
- [ ] No automatic reboots — role flags `reboot_required` for operator action only
- [ ] All roles idempotent; second run is a no-op
- [ ] `just host-configure host=<name> [tags=<list>]` exposes the workflow
- [ ] `runbooks/new-host.md` extended with configure step
- [ ] Demo: wintermute fully converged from declared state

## Blocked by

.scratch/initial-building-blocks/issues/02-host-bootstrap-workflow.md