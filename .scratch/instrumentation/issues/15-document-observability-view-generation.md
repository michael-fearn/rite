# Document Observability View generation

Status: ready-for-agent

## What to build

Document how generated Observability Views relate to Instrumentation, which first-pass Observability View Profiles exist, how generated Grafana dashboards are reconciled, and how the Operator applies changes through Instrumentation Convergence.

## Acceptance criteria

- [ ] Runbooks explain that generated Observability Views are derived from Instrumentation and refreshed through `instrumentation-converge`.
- [ ] Documentation explains that generated views live in one Rite-owned Grafana folder and Operator edits to generated views are not preserved.
- [ ] Documentation explains first-pass profiles: automatic `vm_baseline` and explicit Service-level `prometheus_generic`.
- [ ] Documentation explains that Service-level view intent applies to Service Instrumentation as a whole, not one Telemetry Target.
- [ ] Documentation or tests preserve the ADR decision that Grafana Observability Views use file provisioning rather than the Grafana HTTP API.

## Blocked by

- .scratch/instrumentation/issues/14-refresh-observability-views-through-instrumentation-convergence.md

