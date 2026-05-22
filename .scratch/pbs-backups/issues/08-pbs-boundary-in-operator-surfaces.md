Status: ready-for-agent

# PBS Boundary In Operator Surfaces

## What to build

Make the PBS protection boundary explicit anywhere the operator might otherwise infer too much from green backup status. PBS protects VM recoverability and VM-local state. It does not protect NAS-backed Dataset history, does not promise point-in-time consistency between restored VM disks and NAS-backed Datasets, and does not back up PBS itself through the local PBS instance.

This slice turns that boundary into visible operator language across validation, readiness, health, and restore-related surfaces.

## Acceptance criteria

- [ ] Operator-facing Backup Policy or validation output describes PBS protection as VM recoverability and VM-local state.
- [ ] Backup Readiness output does not imply NAS-backed Dataset history is protected by PBS.
- [ ] Backup Health output does not imply point-in-time consistency with NAS-backed Datasets.
- [ ] `pbs-vm` output clearly says local PBS does not back up itself.
- [ ] Restore-related planning language warns when a Backup Target has NAS-backed Datasets that require care during recovery or drills.
- [ ] Documentation or runbook updates use the domain terms PBS, Backup Target, Unprotected VM, Dataset, Backup Readiness, Backup Health, PBS Restore, and Restore Drill consistently.
- [ ] Tests or documentation checks cover the operator-facing boundary language where practical.

## Blocked by

- `.scratch/pbs-backups/issues/01-inventory-backup-policy-contract.md`
- `.scratch/pbs-backups/issues/06-backup-readiness-gate.md`
- `.scratch/pbs-backups/issues/07-backup-health-reporting.md`
