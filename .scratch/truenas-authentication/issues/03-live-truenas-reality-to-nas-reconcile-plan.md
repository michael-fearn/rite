Status: needs-triage

# Live TrueNAS reality to NAS Reconcile Plan

## What to build

Make live NAS Reconcile fetch TrueNAS reality for the selected NAS Endpoint and map it into the existing `NasReality` shape so the current Dataset validation and Derived Share planning logic works unchanged for live read-only plans.

## Acceptance criteria

- [ ] `scripts/nas-reconcile-plan --live truenas` builds a read-only NAS Reconcile Plan from live client data after preflight succeeds.
- [ ] Live reality includes Dataset metadata needed to validate declared Dataset path and root owner UID/GID.
- [ ] Live reality includes NFS Share definitions needed to detect missing, stale, drifted, and overlapping Shares.
- [ ] The output plan shape remains compatible with existing `--reality-json` output, including redacted connection information and `credentials: operator_environment`.
- [ ] Fixture-backed `--reality-json` behavior is unchanged.
- [ ] Tests prove the mapping with fake TrueNAS API responses.

## Blocked by

- .scratch/truenas-authentication/issues/02-live-truenas-client-preflight.md
