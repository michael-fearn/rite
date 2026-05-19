# Refresh Observability Views through Instrumentation Convergence

Status: ready-for-agent

## What to build

Make Instrumentation Convergence refresh generated Observability Views along with the Observability Service's generated collector configuration. The Operator should be able to run the existing convergence workflow after Instrumentation changes and receive current Prometheus collection plus current Grafana Observability Views in one ceremony.

## Acceptance criteria

- [ ] Instrumentation Convergence refreshes generated Grafana Observability View artifacts when Instrumentation declarations change.
- [ ] Service Launch and Service Group Launch continue to refresh the Observability Service when launched Services change Instrumentation that affects generated views.
- [ ] Removing an Observability View request or opting out VM-level Instrumentation removes the corresponding generated view from the next refresh.
- [ ] Workflow output or tests make the Observability View refresh behavior visible enough for failures to diagnose.
- [ ] Focused workflow tests prove convergence refresh, higher-level launch refresh, and removal/reconciliation behavior.

## Blocked by

- .scratch/instrumentation/issues/12-generate-vm-baseline-observability-view.md
- .scratch/instrumentation/issues/13-generate-prometheus-generic-service-observability-view.md

