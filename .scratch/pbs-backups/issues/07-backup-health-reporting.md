Status: ready-for-agent

# Backup Health Reporting

## What to build

Add operator-facing Backup Health reporting based first on PBS restore-point freshness. Backup Health is evaluated per Backup Target and rolled up by Host and fleet. Default Backup Targets are unhealthy after 36 hours without a fresh successful restore point. Unprotected VMs appear as excluded rather than false failures.

The PBS query layer is isolated from reporting and rollup logic so future diagnostics can enrich the report without leaking API details throughout the codebase.

## Acceptance criteria

- [ ] Backup Health is derived from PBS restore-point freshness.
- [ ] Each Backup Target receives an explicit health status.
- [ ] Default Backup Targets become unhealthy after 36 hours without a fresh successful restore point.
- [ ] Host-level Backup Health rollups summarize Backup Target statuses for that Host.
- [ ] Fleet-level Backup Health rollups summarize all Hosts.
- [ ] Unprotected VMs appear in reports as excluded with their reason visible.
- [ ] PBS querying is isolated from health evaluation and operator output formatting.
- [ ] Tests cover fresh restore points, stale restore points, missing restore points, Host rollups, fleet rollups, and Unprotected VM exclusion.

## Blocked by

- `.scratch/pbs-backups/issues/06-backup-readiness-gate.md`
