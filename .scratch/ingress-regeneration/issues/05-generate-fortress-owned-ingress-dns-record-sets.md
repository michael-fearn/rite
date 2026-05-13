Status: done

## Parent

.scratch/initial-building-blocks/issues/10-caddy-ingress-ingress-regenerator.md

## What to build

Generate fortress-owned Ingress DNS Record Sets as IPv4 A records for declared Service Ingress hostnames and Host Ingress Route hostnames, rendered as a dnsmasq file per Ingress DNS Target. Generated records should point at the Ingress VM address and must stay isolated from manual Pi-hole records.

The completed slice should exclude wildcard records, VM-existence records, and the Ingress VM itself; include only current declared Ingress route hostnames; render a fortress-owned dnsmasq file for each Pi-hole-backed Ingress DNS Target; authoritatively replace that generated file; and avoid mutating manual Pi-hole records.

## Acceptance criteria

- [ ] DNS rendering produces IPv4 A records only.
- [ ] DNS rendering includes Service Ingress hostnames and Host Ingress Route hostnames.
- [ ] DNS rendering excludes wildcard records, VM-existence records, and any record created merely because the Ingress VM exists.
- [ ] Each Ingress DNS Record points to the Ingress VM address, not the route target Backend VM or Host.
- [ ] DNS rendering is deterministic by hostname.
- [ ] The generated dnsmasq file content is isolated as the fortress-owned Ingress DNS Record Set for each Ingress DNS Target.
- [ ] The workflow design authoritatively replaces only the generated file and does not touch manual Pi-hole records.
- [ ] Fast tests cover record inclusion, exclusion, target address selection, deterministic ordering, and generated-file replacement semantics.

## Blocked by

- .scratch/ingress-regeneration/issues/02-make-dns-primary-web-ui-route-and-ingress-dns-target.md
- .scratch/ingress-regeneration/issues/03-complete-trusted-only-host-ingress-routes.md
- .scratch/ingress-regeneration/issues/04-split-caddy-scaffolding-from-generated-route-file.md
