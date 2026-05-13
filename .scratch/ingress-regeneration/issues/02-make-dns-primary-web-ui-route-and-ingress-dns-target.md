Status: done

## Parent

.scratch/initial-building-blocks/issues/10-caddy-ingress-ingress-regenerator.md

## What to build

Make `dns-primary` both an Ingress-enabled Service for the Pi-hole web UI and an Ingress DNS Target that can receive generated Ingress DNS Records. Resolver traffic remains direct TCP/UDP 53 access to the DNS VM, while browser access to Pi-hole uses `dns-primary.fearn.cloud` through the Ingress.

The completed slice should add the DNS Capability model for explicit Pi-hole-backed Ingress DNS Targets, validate that the provider is explicit and only Pi-hole is supported initially, reshape `dns-primary` so its Backend port is the Pi-hole web UI port, keep TCP/UDP 53 as direct Published Port exposure, and configure Pi-hole v6 `/etc/dnsmasq.d` compatibility as part of Service Deploy capability setup.

## Acceptance criteria

- [ ] Service schema and Inventory validation support a DNS Capability declaration for `dns.provider: pihole` and `dns.ingress_records.enabled: true`.
- [ ] Inventory validation rejects Ingress DNS Target declarations without an explicit supported provider.
- [ ] Ingress DNS Target selection comes from DNS Service declarations, not DNS VM names.
- [ ] `dns-primary` declares Ingress for the Pi-hole web UI at `dns-primary.fearn.cloud` and uses the web UI Published Port as its Backend port.
- [ ] `dns-primary` continues to expose resolver TCP/UDP 53 directly on the DNS VM rather than through Caddy.
- [ ] Service Deploy renders the Pi-hole configuration needed for `/etc/dnsmasq.d` compatibility when Ingress DNS Records are enabled.
- [ ] Fast tests cover `dns-primary` as both an Ingress-enabled Service and an Ingress DNS Target.

## Blocked by

- .scratch/ingress-regeneration/issues/01-complete-explicit-service-ingress-inventory-contract.md
