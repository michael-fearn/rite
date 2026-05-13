Status: done

## Parent

.scratch/initial-building-blocks/issues/10-caddy-ingress-ingress-regenerator.md

## What to build

Split stable Caddy scaffolding from generated route content so Service Deploy owns installation, environment, and the stable import surface, while Ingress Regeneration owns a deterministic generated route file imported by that scaffolding.

The completed slice should build one sorted route model from Service Ingress routes and Host Ingress Routes, require unambiguous static IPv4 target addresses for the Ingress VM and every routed Backend or Host, generate hostname-only Caddy routes, proxy Service Backends and Proxmox Host web UIs over plain HTTP, honor `letsencrypt_dns` for public-side TLS, and generate route-level source filtering for Trusted-only Host Ingress Routes.

## Acceptance criteria

- [ ] Service Deploy renders stable Caddy scaffolding that imports a fortress-owned generated route file.
- [ ] Ingress Regeneration renders only the generated route file content and no longer fights Service Deploy over the stable Caddyfile.
- [ ] The route model combines Service Ingress routes and Host Ingress Routes and orders them deterministically by hostname.
- [ ] Route generation fails validation when the Ingress VM, a Backend VM, or a Host Ingress Route target lacks an unambiguous static IPv4 address.
- [ ] Generated routes are hostname-only and do not introduce path-based routing.
- [ ] Generated Service and Host routes proxy to plain HTTP targets.
- [ ] Generated Host Ingress Routes include Caddy Trusted-only source filtering.
- [ ] Fast tests cover route model construction, deterministic ordering, Caddy rendering, TLS policy, source filtering, and ambiguous-address failures.

## Blocked by

- .scratch/ingress-regeneration/issues/01-complete-explicit-service-ingress-inventory-contract.md
- .scratch/ingress-regeneration/issues/02-make-dns-primary-web-ui-route-and-ingress-dns-target.md
- .scratch/ingress-regeneration/issues/03-complete-trusted-only-host-ingress-routes.md
