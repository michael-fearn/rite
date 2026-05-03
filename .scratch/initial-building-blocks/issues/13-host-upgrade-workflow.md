Status: needs-triage

## Parent

docs/prds/initial-building-blocks.md

## What to build

Operator-visible Host upgrade workflow and runbook for Proxmox package upgrades. Ordinary Host Configure must not run `apt upgrade`, `apt dist-upgrade`, or Proxmox upgrade choreography.

## Acceptance criteria

- [ ] `runbooks/host-upgrade.md` documents preflight checks, VM downtime expectations, backup/snapshot expectations, upgrade command sequence, reboot decision points, and rollback/recovery notes
- [ ] Upgrade workflow is exposed separately from `just host-configure`
- [ ] Upgrade workflow requires explicit operator invocation per Host
- [ ] Upgrade workflow reports whether an operator-controlled reboot is required and never reboots automatically
- [ ] Host Configure documentation links to the upgrade workflow as the place for hypervisor package upgrades

## Blocked by

.scratch/initial-building-blocks/issues/03-host-configurator-workflow.md
