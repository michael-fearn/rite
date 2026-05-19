# VM baseline instrumentation uses node exporter and Grafana Alloy

Fortress baseline VM-level Instrumentation uses node exporter for system metrics and Grafana Alloy for VM log collection. Node exporter keeps host metrics in the Prometheus ecosystem's standard shape, while Alloy gives Fortress one VM-local collector that can send logs to Loki now and later grow toward broader telemetry collection without replacing Promtail. The rejected alternative was node exporter plus Promtail, which is simpler for Loki-only log shipping but narrower as a long-term VM telemetry agent.
