Status: needs-triage

## Parent

docs/prds/initial-building-blocks.md

## What to build

A single Caddy VM as the fleet's ingress, Caddy installed via the slice-9 native renderer. Cloudflare API token encrypted in the repo and scoped to this VM only. Let's Encrypt DNS-01 challenge via Cloudflare yields real public certs for internal services. The ingress regenerator workflow rebuilds the Caddyfile and Pi-hole local DNS records from the current service inventory and pushes both.

## Acceptance criteria

- [ ] Caddy VM declared in inventory, provisioned, Caddy installed via native renderer
- [ ] Cloudflare API token stored encrypted, decrypted only into the Caddy VM's environment, never elsewhere
- [ ] Let's Encrypt DNS-01 via Cloudflare configured; real cert issued for a test hostname
- [ ] Ingress regenerator: iterates service inventory, generates Caddyfile, generates Pi-hole local DNS records pointing `*.fearn.cloud` at the Caddy VM, pushes both, reloads both services
- [ ] `just ingress-regenerate` exposes the workflow
- [ ] `runbooks/ingress.md` documents the Caddy/Cloudflare/Pi-hole flow
- [ ] Demo: deploy a service with ingress enabled, run regenerator, reach `https://<name>.fearn.cloud` from the LAN with a real cert

## Blocked by

.scratch/initial-building-blocks/issues/08-native-service-renderer.md, .scratch/initial-building-blocks/issues/09-pi-hole-unbound-dns-vm.md