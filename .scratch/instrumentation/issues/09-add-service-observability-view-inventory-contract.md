# Add Service Observability View inventory contract

Status: ready-for-agent

## What to build

Allow a Service to request one application-specific Observability View from its Service-level Instrumentation declaration by naming a built-in Observability View Profile. The first accepted explicit profile is `prometheus_generic`, and validation should reject unsupported profiles or profile requests that do not have compatible Instrumentation.

## Acceptance criteria

- [ ] Service inventory accepts at most one Service-level Observability View request under Instrumentation.
- [ ] The explicit first-pass Service profile set is limited to `prometheus_generic`.
- [ ] Validation rejects unknown Observability View Profiles.
- [ ] Validation rejects `prometheus_generic` when the Service has no compatible `prometheus_metrics` Telemetry Target.
- [ ] Focused schema and cross-file validation tests cover accepted, unknown-profile, and incompatible-profile cases.

## Blocked by

- None - can start immediately

