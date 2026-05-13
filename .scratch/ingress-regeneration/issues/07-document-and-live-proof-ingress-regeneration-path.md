Status: ready-for-human

## Parent

.scratch/initial-building-blocks/issues/10-caddy-ingress-ingress-regenerator.md

## What to build

Update the operator-facing documentation and perform the live proof for the Ingress Regeneration path. This slice stays human-owned because it requires real Cloudflare credentials, live DNS-01 certificate issuance, reachable VMs, and LAN validation.

The completed slice should update the new-Service and DNS runbooks plus relevant architecture notes, reconcile the parent issue 10 acceptance criteria against the split implementation work, run the live Caddy/Cloudflare/Pi-hole proof, and record any remaining operator caveats.

## Acceptance criteria

- [ ] `runbooks/new-service.md` explains how an Operator declares a new Ingress-enabled Service and runs Ingress Regeneration.
- [ ] The DNS runbook explains generated Ingress DNS Records, Ingress DNS Targets, the fortress-owned dnsmasq file, and what manual Pi-hole records remain outside fortress ownership.
- [ ] Architecture notes describe Service Ingress, Host Ingress Routes, Caddy generated-route ownership, and generated DNS ownership consistently with the ADRs.
- [ ] Parent issue 10 acceptance criteria are updated or commented with the split between AFK implementation issues and live human proof.
- [ ] Live proof issues a real Let's Encrypt DNS-01 certificate through Cloudflare for an Ingress hostname.
- [ ] Live proof reaches at least one Service Ingress hostname from the LAN with the expected certificate.
- [ ] Live proof reaches a Proxmox web UI Host Ingress Route from a Trusted source and confirms non-Trusted source ranges are denied where practical.
- [ ] Any live-only caveats or follow-up issues are recorded in the local issue tracker.

## Blocked by

- .scratch/ingress-regeneration/issues/06-make-ingress-regenerate-push-and-reload-generated-files.md
- .scratch/initial-building-blocks/issues/09-pi-hole-unbound-dns-vm.md
