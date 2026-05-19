# Generate Grafana provisioning for Observability Views

Status: ready-for-agent

## What to build

Generate the Grafana file provisioning artifacts needed for Rite-owned Observability Views as Application Configuration Artifacts owned by the Observability Service. First-pass generated views should live in one Rite-owned generated Grafana folder and be reconciled from the current generated view intent.

## Acceptance criteria

- [ ] Observability Service generation emits Grafana dashboard provisioning configuration for one Rite-owned generated folder.
- [ ] Generated dashboard files are written as Observability Service Application Configuration Artifacts with the Observability Service data owner.
- [ ] The Observability Service mounts generated Grafana provisioning and dashboard artifacts into the Grafana container.
- [ ] Generated artifacts are replaceable on refresh so Operator edits to generated Observability Views are not preserved.
- [ ] Focused tests prove provisioning file content, generated folder ownership, mount wiring, and artifact owner behavior.

## Blocked by

- .scratch/instrumentation/issues/10-expose-observability-view-intent-from-inventory.md

