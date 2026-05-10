# Single Caddy ingress VM, separate Pi-hole+Unbound DNS VM

There is exactly one Caddy VM, terminating TLS via Let's Encrypt DNS-01 (Cloudflare) and reverse-proxying every internal `*.fearn.cloud` Service. DNS (Pi-hole + Unbound) lives on separate DNS VMs. Ingress and DNS have different criticality (DNS-down breaks everything; ingress-down only breaks HTTP) and different lifecycles (Pi-hole's blocklist updates aren't an ingress concern); having one IP for internal `*.fearn.cloud` records gives one place to look for HTTP routing. `just ingress-regenerate` writes both the Caddyfile and the Pi-hole local-DNS records from a single iteration over the Service inventory.

Placement details in this ADR are superseded by ADR-0020 and the Homelab Firewall Matrix. The current layout uses `internal-ingress-vm` for Caddy and functionally identical primary and secondary DNS VMs.
