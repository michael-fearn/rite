Status: ready-for-agent

# Backup Configure Plan

## What to build

Add Backup Configure planning as a host-scoped operator workflow, with fleet mode represented as iteration over Hosts. The plan receives Inventory plus observed PVE Backup Job state and returns deterministic create, update, prune, and no-op actions for fortress-owned Backup Jobs.

Each Backup Target gets one PVE-side Backup Job. Plans show the Backup Target VM, selected Backup Policy, Primary Datastore, action, deterministic Backup Job name, and derived scheduled time. Manual PVE jobs remain outside fortress ownership and are shown or ignored without being pruned.

## Acceptance criteria

- [ ] Backup Configure has a plan-only mode for one Host.
- [ ] Fleet Backup Configure planning iterates Hosts without changing the host-scoped ownership boundary.
- [ ] The plan creates one desired Backup Job per Backup Target on the selected Host.
- [ ] Backup Job names are deterministic from Backup Target and Backup Policy.
- [ ] Backup Job scheduled times are deterministically staggered from Backup Target identity within the policy stagger band.
- [ ] Plan output includes VM, policy, Primary Datastore, action, deterministic job name, and derived scheduled time.
- [ ] Planning detects create, update, no-op, and obsolete fortress-owned prune actions.
- [ ] Planning leaves manual PVE jobs alone.
- [ ] Planning reports Backup Targets that still need a first successful Backup Run.
- [ ] Unit tests cover deterministic staggering stability, schedule bounds, create/update/no-op/prune planning, and manual job preservation.

## Blocked by

- `.scratch/pbs-backups/issues/01-inventory-backup-policy-contract.md`
- `.scratch/pbs-backups/issues/02-pbs-availability-and-configuration.md`
