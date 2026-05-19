# Instrumentation

Use this runbook when changing declared VM-level or Service-level Instrumentation and you need the Observability VM to collect from current Inventory.

## Converge Instrumentation

Run:

```sh
just instrumentation-converge
```

Instrumentation Convergence applies enabled VM-level Instrumentation across ordinary VMs, runs VM Configure for each ordinary VM with Instrumentation enabled, and then runs Service Update for the Observability Service. This is the operator path for applying Instrumentation to existing VMs and Services after Inventory changes.

Before running VM Configure, the workflow checks whether each inventory-declared ordinary VM exists on its live Host. It skips inventory-declared VMs that are absent from the live Host. Skipped VMs are also omitted from the generated Observability Service configuration during that convergence run, so Prometheus does not keep scraping VM-level or Service Telemetry Targets for absent VMs.

The workflow stops at the first failed VM Configure or Observability Service Update phase and reports the failed phase. Fix that phase, then rerun `just instrumentation-converge`.

## VM Baseline Instrumentation

Declared ordinary VMs are instrumented by default. Leave `instrumentation` absent, or declare `instrumentation.enabled: true`, when the VM should receive the baseline collector set.

To opt one VM out:

```yaml
instrumentation:
  enabled: false
```

`instrumentation.enabled: false` opts one ordinary VM out of baseline VM-level Instrumentation. VM Configure installs and enables the baseline collectors only for ordinary VMs whose Instrumentation remains enabled. The first-pass baseline collector set is node exporter for system metrics and Grafana Alloy for VM logs.

## Service Telemetry Targets

A Service opts into application-specific Service-level Instrumentation with `instrumentation.telemetry_targets`:

```yaml
instrumentation:
  telemetry_targets:
    - name: web-metrics
      type: prometheus_metrics
      published_port: 9090
    - name: web-health
      type: http_probe
      published_port: 8080
      path: /health
```

First-pass target types are `prometheus_metrics` and `http_probe`. Each target names one `published_port` from the Service's declared Published Ports. The first-pass Telemetry Targets are collected through VM-reachable Published Ports, so the Published Port must be TCP-capable and must not be bound only to loopback.

The target scheme defaults to http. The prometheus_metrics path defaults to /metrics, and the http_probe path defaults to /. Both defaults may be overridden with `scheme` and `path` on the Telemetry Target. The generated Observability configuration targets the Backend VM static IP and Published Port rather than the Service Ingress hostname.

## Generated Observability Views

Generated Observability Views are derived from Instrumentation and refreshed through `just instrumentation-converge`. The Observability Service rebuilds the current generated Grafana provisioning and dashboard files from Inventory-derived VM-level and Service-level Instrumentation, alongside the generated collector configuration.

First-pass generated views are:

- An automatic `vm_baseline` view for each included ordinary VM whose VM-level Instrumentation remains enabled.
- An explicit Service-level `prometheus_generic` view for a Service that declares `instrumentation.observability_views` with `profile: prometheus_generic`.

The Service-level view intent applies to the Service Instrumentation declaration as a whole, not to one Telemetry Target. The `prometheus_generic` profile is valid only when the Service has compatible `prometheus_metrics` Telemetry Targets, and one requested Service view summarizes the compatible targets for that Service.

Generated views live in a single Rite-owned generated Grafana folder. Operator edits to generated views are not preserved; change Inventory Instrumentation or the built-in profile definition, then rerun `just instrumentation-converge` to refresh the generated files.

Per docs/adr/0033-grafana-observability-views-use-file-provisioning.md, Rite uses Grafana file provisioning rather than the Grafana HTTP API for generated Observability Views. This keeps generated views rebuildable from Inventory and avoids adding Grafana admin API credentials to Rite.

## Workflow Boundaries

Service Deploy remains scoped to the named Service. It renders and deploys that Service's artifacts, but it does not refresh the Observability VM when `instrumentation.telemetry_targets` changes.

Use `just instrumentation-converge` after changing Instrumentation on existing Services, or use the higher-level launch workflows when bringing a changed Service online. Service Launch refreshes the Observability VM after Service Deploy when the launched Service declares Service-level Instrumentation. Service Group Launch refreshes the Observability VM after the group's Service Deploy phases when any launched Service declares Service-level Instrumentation.

## Deferred Collector Profiles

VM-level collector profiles are deferred. First-pass enabled VM-level Instrumentation applies one baseline collector set to ordinary VMs; changing that default baseline for subsets of VMs belongs in a future VM-level Instrumentation declaration. When that extension exists, profile changes for already-declared ordinary VMs should be applied to existing VMs through Instrumentation Convergence rather than through Service Deploy.
