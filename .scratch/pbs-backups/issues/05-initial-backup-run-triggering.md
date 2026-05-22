Status: ready-for-agent

# Initial Backup Run Triggering

## What to build

Let Backup Configure explicitly trigger initial Backup Runs when the operator chooses to establish Backup Readiness immediately. Triggering may target one Backup Target or a host-scoped set. Explicit initial runs ignore scheduled stagger because the operator is asking for protection now.

Job creation alone must still be reported as not yet protected until a successful Backup Run exists.

## Acceptance criteria

- [ ] The operator can explicitly trigger an initial Backup Run for one Backup Target.
- [ ] The operator can explicitly trigger initial Backup Runs for a Host-scoped set of Backup Targets.
- [ ] Initial Backup Run triggering is never implicit in normal Backup Configure apply.
- [ ] Explicit initial Backup Runs ignore scheduled stagger.
- [ ] Output reports which Backup Targets have pending first successful Backup Runs.
- [ ] Output distinguishes successful trigger submission from proven backup protection.
- [ ] Tests cover single-target triggering, host-scoped triggering, no implicit triggering, stagger bypass, and pending-first-run reporting.

## Blocked by

- `.scratch/pbs-backups/issues/04-backup-configure-apply.md`
