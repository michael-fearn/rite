Status: done

## Parent

.scratch/initial-building-blocks/issues/10-caddy-ingress-ingress-regenerator.md

## What to build

Complete Trusted-only Host Ingress Routes for Proxmox web UIs as Host inventory declarations rather than synthetic Services. A Host Ingress Route should route `<host>.<domain>` through the Ingress to the physical Host management address on the Proxmox web UI port, with Trusted-only access enforced by generated Caddy route matchers.

The completed slice should finish the Host YAML schema and validation, require Host Ingress Route hostnames to equal `<host>.<domain>`, target `network.management_address` and never `proxmox.endpoint`, use Inventory-declared Trusted-only source ranges, and keep current Host route declarations valid.

## Acceptance criteria

- [ ] Host schema models explicit Proxmox web UI Host Ingress Route declarations.
- [ ] Inventory validation rejects enabled Host Ingress Routes without `network.management_address`.
- [ ] Inventory validation rejects Host Ingress Route hostnames that do not equal `<host>.<domain>` using the operator-facing Host name.
- [ ] Generated Host Ingress Routes target the Host management address and default to TCP port 8006.
- [ ] Host Ingress Route generation and validation do not use `proxmox.endpoint`.
- [ ] Trusted-only source ranges are read from Inventory and missing policy is rejected when any Host Ingress Route is enabled.
- [ ] Fast tests cover valid Host Ingress Routes, hostname collisions, hostname mismatch, missing management address, and missing Trusted-only source ranges.

## Blocked by

- .scratch/ingress-regeneration/issues/01-complete-explicit-service-ingress-inventory-contract.md
