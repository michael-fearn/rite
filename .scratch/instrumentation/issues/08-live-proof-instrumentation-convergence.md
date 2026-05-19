# Live-proof Instrumentation Convergence

Status: ready-for-human

## What to build

Perform the live infrastructure proof for Instrumentation Convergence after the agent-ready implementation and runbook slices land. This slice should prove the real operator path against ordinary VMs and the live Observability Service, then record any live-only caveats or follow-up work.

## Acceptance criteria

- [ ] Run `instrumentation-converge` against real ordinary VMs.
- [ ] Confirm node exporter scrape targets for instrumented VMs are up in Prometheus.
- [ ] Confirm Grafana Alloy ships VM logs to Loki.
- [ ] Confirm at least one Service Telemetry Target appears in the generated observability configuration and is collected successfully.
- [ ] Confirm an opted-out VM is not configured or scraped by baseline VM-level Instrumentation, if a safe opt-out candidate exists.
- [ ] Record any firewall, VLAN, credential, or live Observability caveats in the issue comments or runbook.

## Blocked by

- .scratch/instrumentation/issues/07-document-instrumentation-operator-runbooks-and-migration-path.md

