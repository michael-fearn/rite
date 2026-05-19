# Generate VM baseline Observability View

Status: ready-for-agent

## What to build

Generate a first-pass `vm_baseline` Observability View from enabled VM-level Instrumentation. The view should give the Operator a baseline VM-oriented dashboard over the node exporter and VM log signals already collected by the Observability Service, without requiring per-VM dashboard declarations.

## Acceptance criteria

- [ ] Enabled VM-level Instrumentation causes VMs to appear in generated baseline VM Observability Views.
- [ ] VMs with VM-level Instrumentation opted out do not appear in generated baseline VM Observability Views.
- [ ] Generated VM baseline view identity is stable and derived from the VM identity and view kind.
- [ ] Generated dashboard JSON references the Prometheus and Loki data sources through provisioning-safe identifiers or variables.
- [ ] Focused tests prove dashboard generation for included VMs, opted-out VMs, stable identity, and datasource references.

## Blocked by

- .scratch/instrumentation/issues/11-generate-grafana-provisioning-for-observability-views.md

