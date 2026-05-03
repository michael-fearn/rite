Status: needs-triage

## Parent

docs/prds/initial-building-blocks.md

## What to build

The transition from a freshly-installed Proxmox host carrying a shared bootstrap key to a host with a unique per-host SSH key stored encrypted in the repo. Idempotency is by refusal — re-running on a bootstrapped host fails rather than clobbers.

## Acceptance criteria

- [ ] Bootstrap playbook generates a per-host SSH keypair locally
- [ ] Pushes public key to host via shared bootstrap key
- [ ] Verifies new key works (auth-test) before proceeding
- [ ] Removes shared key from host's `authorized_keys`
- [ ] Writes encrypted private key into `inventory/hosts/<host>.sops.yaml` as a structured key entry (type, created, public_key, private_key)
- [ ] Refuses to run if `<host>.sops.yaml` already contains a bootstrap key entry
- [ ] `just host-bootstrap host=<name>` exposes the workflow
- [ ] `runbooks/new-host.md` documents the bootstrap step
- [ ] Demo: fresh PVE install of wintermute transitioned end-to-end

## Blocked by

.scratch/initial-building-blocks/issues/01-inventory-plugin-json-schemas-cross-file-validator.md