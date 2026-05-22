Status: ready-for-agent

# Backup Configure Apply

## What to build

Apply Backup Configure plans to PVE. The workflow creates and updates fortress-owned Backup Jobs, prunes only obsolete fortress-owned Backup Jobs, and leaves manual PVE jobs untouched. Pruning is confirmation-gated so removal of future protection is always explicit.

This slice turns the tested plan into live PVE mutation while preserving plan-only inspection before apply.

## Acceptance criteria

- [ ] Backup Configure can apply a previously inspectable host-scoped plan.
- [ ] Apply creates missing fortress-owned Backup Jobs for Backup Targets.
- [ ] Apply updates drifted fortress-owned Backup Jobs to match the current Backup Policy and target identity.
- [ ] Apply prunes obsolete fortress-owned Backup Jobs only after operator confirmation.
- [ ] Apply supports explicit auto-confirm behavior for pruning when requested by the operator.
- [ ] Apply never deletes or mutates manual PVE jobs.
- [ ] Failures are reported with enough context to identify the Host, Backup Target, Backup Job, and action.
- [ ] Tests cover create, update, prune confirmation, prune refusal, auto-confirm pruning, manual job preservation, and failure reporting.

## Blocked by

- `.scratch/pbs-backups/issues/03-backup-configure-plan.md`
