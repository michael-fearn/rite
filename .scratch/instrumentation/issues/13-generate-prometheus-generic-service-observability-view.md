# Generate prometheus_generic Service Observability View

Status: ready-for-agent

## What to build

Generate one application-specific Service Observability View for each Service that explicitly requests the `prometheus_generic` Observability View Profile and has compatible Prometheus metrics Instrumentation. The generated view should be Service-scoped, not Telemetry Target-scoped.

## Acceptance criteria

- [ ] A Service that requests `prometheus_generic` gets exactly one generated application-specific Observability View.
- [ ] The generated view can include one or more compatible Prometheus metrics Telemetry Targets for that Service.
- [ ] A Service without an explicit application-specific Observability View request does not get a Service-specific generated dashboard.
- [ ] Generated Service view identity is stable and derived from the Service identity and view kind.
- [ ] Focused tests prove one-view-per-Service behavior, multi-target Service handling, no implicit Service dashboard, and stable identity.

## Blocked by

- .scratch/instrumentation/issues/11-generate-grafana-provisioning-for-observability-views.md

