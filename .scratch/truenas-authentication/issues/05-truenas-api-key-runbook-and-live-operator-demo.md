Status: needs-triage

# TrueNAS API key runbook and live operator demo

## What to build

Document the operator ceremony for creating the TrueNAS API key, storing it in the NAS Endpoint Sibling SOPS File, and running endpoint-explicit live NAS Reconcile. Include a live demo checklist that proves read-only planning without mutating TrueNAS.

## Acceptance criteria

- [ ] The runbook tells the Operator how to create a dedicated TrueNAS API key with Dataset-read plus NFS-Share-manage intent.
- [ ] The runbook documents the canonical SOPS path `api_credentials.reconcile.value` in `inventory/nas/<endpoint>.sops.yaml`.
- [ ] The runbook makes clear that routine NAS Reconcile credentials must not mutate ordinary Datasets.
- [ ] The demo checklist covers live preflight and read-only plan against `--live truenas`.
- [ ] The demo checklist includes expected failure modes for missing SOPS material and insufficient privilege.
- [ ] Documentation links back to ADR 0019 and uses the glossary terms NAS Endpoint, Management Address, Share Address, and NAS Reconcile Credential.

## Blocked by

- .scratch/truenas-authentication/issues/03-live-truenas-reality-to-nas-reconcile-plan.md
