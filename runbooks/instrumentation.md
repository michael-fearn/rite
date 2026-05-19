# Instrumentation

Use this runbook when changing declared VM-level or Service-level Instrumentation and you need the Observability VM to collect from current Inventory.

## Converge Instrumentation

Run:

```sh
just instrumentation-converge
```

Instrumentation Convergence applies enabled VM-level Instrumentation across ordinary VMs, runs VM Configure for each ordinary VM with Instrumentation enabled, and then runs Service Update for the Observability Service. This is the operator path for applying Instrumentation to existing VMs and Services after Inventory changes.

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

## Workflow Boundaries

Service Deploy remains scoped to the named Service. It renders and deploys that Service's artifacts, but it does not refresh the Observability VM when `instrumentation.telemetry_targets` changes.

Use `just instrumentation-converge` after changing Instrumentation on existing Services, or use the higher-level launch workflows when bringing a changed Service online. Service Launch refreshes the Observability VM after Service Deploy when the launched Service declares Service-level Instrumentation. Service Group Launch refreshes the Observability VM after the group's Service Deploy phases when any launched Service declares Service-level Instrumentation.

## Deferred Collector Profiles

VM-level collector profiles are deferred. First-pass enabled VM-level Instrumentation applies one baseline collector set to ordinary VMs; changing that default baseline for subsets of VMs belongs in a future VM-level Instrumentation declaration. When that extension exists, profile changes for already-declared ordinary VMs should be applied to existing VMs through Instrumentation Convergence rather than through Service Deploy.
