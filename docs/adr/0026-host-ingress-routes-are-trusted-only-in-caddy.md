# Host ingress routes are Trusted-only in Caddy

Proxmox Host web UI Host Ingress Routes are Trusted-only management routes, enforced by generated Caddy route matchers using source ranges declared in Inventory. Ordinary Service ingress and Host management ingress share the same Ingress VM address, so router/firewall rules cannot distinguish `forgejo.fearn.cloud` from `wintermute.fearn.cloud`; Caddy is the layer that can see the hostname and must deny Known, IoT, Guest, and DMZ clients for Host management routes.
