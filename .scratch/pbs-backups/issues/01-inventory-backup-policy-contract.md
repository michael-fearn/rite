Status: ready-for-agent

# Inventory Backup Policy Contract

## What to build

Introduce the static Inventory contract for PBS backup intent. The fleet has a named Backup Policy model with an initial required `default` policy, and every production VM explicitly declares whether it is a Backup Target or an Unprotected VM. Backup Targets default to the `default` policy when no policy is named. Unprotected VMs require an operator-facing reason. Generated or disposable VMs are exempt.

The current repo Inventory is migrated in the same slice so validation remains green immediately: every current production VM except `pbs-vm` is a Backup Target on `default`, and `pbs-vm` is an Unprotected VM with an explicit reason.

## Acceptance criteria

- [ ] Inventory contains a fleet-level Backup Policy contract with exactly the initial `default` policy committed.
- [ ] The `default` Backup Policy declares a daily Backup Run at `03:30 America/Denver`, a deterministic `60m` stagger band, and retention of 14 daily, 8 weekly, and 12 monthly restore points.
- [ ] Backup Policy validation rejects a missing policy file, missing `default`, malformed schedules or retention, and unknown policy references.
- [ ] VM validation requires every production VM to declare `backup.enabled` and requires `backup.reason` for Unprotected VMs.
- [ ] Backup Targets may omit `backup.policy` and then resolve to `default`.
- [ ] Generated or disposable VMs are exempt from production backup declaration requirements.
- [ ] The Inventory model exposes one canonical parsed representation of Backup Policies for validation and future workflows.
- [ ] Current repo Inventory validates with every production VM except `pbs-vm` protected by `default`.
- [ ] `pbs-vm` validates as an Unprotected VM with an explicit reason.
- [ ] Schema, model, cross-file validation, and real Inventory tests cover the accepted and rejected backup contract shapes.

## Blocked by

None - can start immediately
