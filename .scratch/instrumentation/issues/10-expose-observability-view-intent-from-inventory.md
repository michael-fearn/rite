# Expose Observability View intent from Inventory

Status: ready-for-agent

## What to build

Expose generated Observability View intent from Inventory so downstream Observability Service generation can ask which baseline VM views and explicit Service views should exist without traversing raw YAML. The intent should use stable view identities derived from observed Entity identity and view kind.

## Acceptance criteria

- [ ] Inventory queries expose baseline VM Observability View intent for VMs with enabled VM-level Instrumentation.
- [ ] Inventory queries expose Service Observability View intent for Services that request a valid application-specific Observability View Profile.
- [ ] Generated view identity is derived from Entity identity and view kind, not display title.
- [ ] View intent excludes VMs omitted from the current Observability generation context when that context excludes absent or skipped VMs.
- [ ] Focused tests prove VM baseline view intent, explicit Service view intent, stable IDs, and exclusion behavior.

## Blocked by

- .scratch/instrumentation/issues/09-add-service-observability-view-inventory-contract.md

