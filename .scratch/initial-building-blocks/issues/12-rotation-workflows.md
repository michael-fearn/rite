Status: needs-triage

## Parent

docs/prds/initial-building-blocks.md

## What to build

Hard-cutover rotation flows for every credential type the fleet manages: host root SSH keys, VM admin SSH keys, PVE API tokens, service secrets. The age key rotation is documented as a manual ceremony rather than automated. No grace-period overlap anywhere.

## Acceptance criteria

- [ ] `just host-rotate-key host=<name>` rotates the per-host root SSH key, hard cutover, console-recovery path documented
- [ ] `just vm-rotate-admin-key vm=<name>` updates the encrypted store **and** the plaintext public-key field on the VM yaml so a future tofu re-apply uses the current key
- [ ] `just pve-rotate-token host=<name>` uses versioned token names on the PVE side so rotation is atomic
- [ ] `just service-rotate-secret service=<name> secret=<key>` updates the encrypted store and redeploys the service; per-service runbooks document app-side steps (e.g., `ALTER USER` for DB password)
- [ ] `runbooks/rotate-age-key.md` documents the manual age-key rotation ceremony
- [ ] Per-rotation runbooks under `runbooks/rotate-*.md`
- [ ] Demo: each rotation type executed end-to-end against a real entity

## Blocked by

.scratch/initial-building-blocks/issues/10-caddy-ingress-ingress-regenerator.md