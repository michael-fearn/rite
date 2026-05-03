Status: needs-triage

## Parent

docs/prds/initial-building-blocks.md

## What to build

Pi-hole + Unbound deployed via the quadlet path on a dedicated VM, serving LAN DNS. The exact split (single container vs two) is implementation-time. DNS records for `*.fearn.cloud` come in slice 11 alongside the ingress regenerator.

## Acceptance criteria

- [ ] DNS VM declared in inventory and provisioned via the slice-6 path
- [ ] Pi-hole + Unbound deployed via the slice-8 quadlet renderer
- [ ] LAN clients can resolve external names through the VM
- [ ] Architecture (single vs split container, upstream config) documented in `runbooks/dns-architecture.md`
- [ ] Demo: a LAN client configured with the new resolver successfully resolves both external and internal queries

## Blocked by

.scratch/initial-building-blocks/issues/07-quadlet-renderer-first-multi-container-service.md