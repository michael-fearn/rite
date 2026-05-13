Status: done

## Parent

.scratch/initial-building-blocks/issues/10-caddy-ingress-ingress-regenerator.md

## What to build

Turn `ingress-regenerate` into the operator workflow that validates Inventory, renders generated Caddy routes and Ingress DNS Record Sets, pushes them to the Ingress VM and all declared Ingress DNS Targets, reloads Caddy and Pi-hole DNS, and fails if any targeted reload fails.

The workflow is intentionally non-transactional: no rollback is required, but success means every targeted generated file was pushed and every targeted reload succeeded. The workflow should be exposed through `just ingress-regenerate`.

## Acceptance criteria

- [ ] `ingress-regenerate` validates Inventory before rendering or pushing generated artifacts.
- [ ] The workflow renders and pushes the generated Caddy route file to the Ingress VM.
- [ ] The workflow renders and pushes fortress-owned dnsmasq files to every declared Ingress DNS Target.
- [ ] The workflow reloads Caddy after route file updates.
- [ ] The workflow reloads Pi-hole DNS on every targeted Pi-hole-backed DNS Service after DNS file updates.
- [ ] The command exits non-zero if any targeted push or reload fails.
- [ ] `just ingress-regenerate` exposes the workflow.
- [ ] Fast tests cover orchestration order, push/reload command construction, multi-target DNS behavior, validation failures, and targeted reload failures.

## Blocked by

- .scratch/ingress-regeneration/issues/04-split-caddy-scaffolding-from-generated-route-file.md
- .scratch/ingress-regeneration/issues/05-generate-fortress-owned-ingress-dns-record-sets.md
