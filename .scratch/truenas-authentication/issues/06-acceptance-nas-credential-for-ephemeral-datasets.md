Status: needs-triage

# Acceptance NAS Credential for Ephemeral Datasets

## What to build

Add the separate Acceptance NAS Credential path for live Acceptance Tests that need to create or destroy Ephemeral Datasets, without broadening the ordinary NAS Reconcile Credential.

## Acceptance criteria

- [ ] Acceptance-only live workflows use a separate SOPS purpose under `api_credentials`, distinct from `api_credentials.reconcile.value`.
- [ ] Ordinary live NAS Reconcile never reads or exports the Acceptance NAS Credential.
- [ ] Ephemeral Dataset create/destroy remains gated by explicit acceptance flags and cannot run against ordinary fleet Inventory by default.
- [ ] Missing acceptance credential material fails before network access when an acceptance workflow requires Ephemeral Dataset mutation.
- [ ] Tests prove ordinary reconcile cannot mutate Datasets with only the ordinary NAS Reconcile Credential path.

## Blocked by

- .scratch/truenas-authentication/issues/04-live-fortress-owned-share-apply.md
