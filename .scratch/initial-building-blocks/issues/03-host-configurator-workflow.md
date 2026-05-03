Status: needs-triage

## Parent

docs/prds/initial-building-blocks.md

## What to build

Convergence of a bootstrapped host to its declared state: repos, system hygiene, network bridges, PVE users with multi-role tokens (auto-created and stored encrypted), GPU passthrough setup. Storage remains operator-controlled and documented only for now. Datacenter configuration is avoided for now because Hosts are standalone. Idempotent, never auto-reboots, tagged so individual scopes can be applied independently.

## Acceptance criteria

- [ ] Roles exist and are independently tagged: `proxmox_repos`, `system_hygiene`, `proxmox_network`, `proxmox_users`, `gpu_passthrough`
- [ ] PVE API token for tofu created during configurator run; written encrypted into the host's sops file
- [ ] GPU passthrough role supports SR-IOV (wintermute) and full passthrough (neuromancer, straylight) per host yaml declaration
- [ ] GPU passthrough validation rejects contradictory declarations; role may flag reboot required but never reboots
- [ ] Network role only changes bridges declared with `managed: true`; manual bridges are still used for VM validation
- [ ] Storage is documented in Host yaml/runbook, used by VM cross-file validation, but Host Configure does not create or register storage
- [ ] System hygiene installs baseline packages and manages host/time settings, but does not run hypervisor package upgrades
- [ ] No automatic reboots — roles append reasons to a shared reboot-required summary for operator action only
- [ ] All roles idempotent; second run is a no-op
- [ ] `just host-configure host=<name> tags=<list>` exposes the workflow; omitting tags fails and prints the all-tags command
- [ ] `runbooks/new-host.md` extended with configure step
- [ ] JSON Schema tests cover new Host fields for documented storage, managed network bridges, PVE users/tokens, and GPU validation constraints
- [ ] Cross-file validator tests reject VM disks using storage not declared by `placement.host`, and VM interfaces using bridges not declared by `placement.host`
- [ ] Wrapper tests cover required tags, unknown-tag failure, token no-op when SOPS already has a token, token merge preserving `ssh_keys.bootstrap`, and rollback when SOPS write fails after token creation
- [ ] Ansible syntax/lint checks pass for the Host Configure playbook and roles
- [ ] Demo: wintermute fully converged from declared state

## Blocked by

.scratch/initial-building-blocks/issues/02-host-bootstrap-workflow.md
