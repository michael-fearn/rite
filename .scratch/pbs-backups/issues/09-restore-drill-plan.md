Status: ready-for-agent

# Restore Drill Plan

## What to build

Add Restore Drill planning as a distinct workflow family from Acceptance Tests. A Restore Drill proves recovery from PBS backup reality by planning a generated disposable Restored Drill VM from a selected Backup Target restore point.

The plan selects placement per drill, defaults the Restored Drill VM to a Drill Network, avoids production VM identity collisions, avoids production ingress and DNS, avoids production NAS-backed Dataset mutation, and treats restored production secrets as operator-only.

## Acceptance criteria

- [ ] Restore Drill planning is distinct from Acceptance Test planning and language.
- [ ] A Restore Drill plan targets a Backup Target restore point, not declared intent alone.
- [ ] Restored Drill VMs are modeled as generated disposable VMs rather than durable production Inventory entities.
- [ ] Placement is selected per Restore Drill.
- [ ] Drill Network is the default network for Restored Drill VMs.
- [ ] Plans reject or warn on production VM identity collisions.
- [ ] Plans avoid production ingress and DNS exposure.
- [ ] Plans avoid mutating production NAS-backed Datasets.
- [ ] Plans make operator-only access explicit because restored production secrets may be present.
- [ ] Restore Drill planning is isolated from execution so identity, network, NAS, and cleanup safety are testable.
- [ ] Tests cover normal planning, placement selection, Drill Network defaulting, identity collision prevention, ingress/DNS avoidance, NAS mutation avoidance, and operator-only access.

## Blocked by

- `.scratch/pbs-backups/issues/02-pbs-availability-and-configuration.md`
- `.scratch/pbs-backups/issues/07-backup-health-reporting.md`
