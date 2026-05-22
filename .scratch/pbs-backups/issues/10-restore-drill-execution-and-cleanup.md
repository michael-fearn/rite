Status: ready-for-agent

# Restore Drill Execution And Cleanup

## What to build

Execute a planned Restore Drill against PBS backup reality. The workflow creates the disposable Restored Drill VM, keeps it isolated from production identity, ingress, DNS, and production NAS-backed Dataset mutation, supports operator verification, and destroys the Restored Drill VM by default. An explicit keep-on-fail option leaves failed drill artifacts available for diagnosis.

## Acceptance criteria

- [ ] A Restore Drill can execute from an approved Restore Drill plan.
- [ ] Execution restores a Backup Target restore point into a disposable Restored Drill VM.
- [ ] The Restored Drill VM uses the planned placement and Drill Network.
- [ ] Execution preserves production secrets inside the restored VM while keeping access operator-only.
- [ ] Execution does not expose production ingress or DNS for the Restored Drill VM.
- [ ] Execution does not mutate production NAS-backed Datasets.
- [ ] Successful Restore Drills destroy the Restored Drill VM by default.
- [ ] Failed Restore Drills destroy the Restored Drill VM by default unless keep-on-fail is explicitly requested.
- [ ] Output distinguishes drill verification from production Service health.
- [ ] Tests cover successful execution, cleanup by default, keep-on-fail, containment boundaries, NAS mutation prevention, and failure reporting.

## Blocked by

- `.scratch/pbs-backups/issues/09-restore-drill-plan.md`
