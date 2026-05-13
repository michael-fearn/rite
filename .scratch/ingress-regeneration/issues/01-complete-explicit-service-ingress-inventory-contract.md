Status: done

## Parent

.scratch/initial-building-blocks/issues/10-caddy-ingress-ingress-regenerator.md

## What to build

Complete the explicit Service Ingress inventory contract so a Service only participates in Ingress when it opts in deliberately, and invalid hostname or Published Port declarations fail during Inventory validation before Ingress Regeneration runs.

The completed slice should remove hostname-implies-Ingress behavior, require `ingress.enabled` whenever a Service declares an `ingress` block, forbid Service hostnames when Ingress is disabled, require LAN-only Service Ingress hostnames to be explicit FQDNs under the fleet domain, enforce shared hostname uniqueness across Service Ingress and Host Ingress Routes, and tighten Ingress-backed Published Port validation to exactly one TCP-capable matching Published Port.

## Acceptance criteria

- [ ] A Service hostname no longer enables Ingress implicitly; Services must declare `ingress.enabled: true` to become Ingress routes.
- [ ] Inventory validation rejects any Service `ingress` block missing an explicit `ingress.enabled` value.
- [ ] Inventory validation rejects a Service hostname when `ingress.enabled` is false.
- [ ] Inventory validation rejects LAN-only Service Ingress hostnames that are not explicit FQDNs under `inventory/group_vars/all.yaml` `domain`.
- [ ] Inventory validation rejects duplicate hostnames across Service Ingress and Host Ingress Routes.
- [ ] Inventory validation requires an Ingress-enabled Quadlet Service to have exactly one TCP-capable Published Port marked for Ingress whose host port equals the Backend port.
- [ ] Fast tests cover valid and invalid Service Ingress declarations.

## Blocked by

None - can start immediately
