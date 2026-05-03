Status: needs-triage

## Parent

docs/prds/initial-building-blocks.md

## What to build

Proxmox Backup Server deployed in the inventory like any other VM. Datastore on a TrueNAS-hosted NFS export. Client-side encryption from day one (avoids re-encryption when off-site replication is added later). PBS encryption master key stored in the encrypted repo and at the offline backup location. Per-VM backup schedule and retention declared in the VM yaml with sensible global defaults.

## Acceptance criteria

- [ ] PBS VM declared in `inventory/vms/pbs.yaml`, provisioned via slice-6 path
- [ ] PBS NFS datastore mounted via slice-7 path
- [ ] Client-side encryption enabled at PBS initialization
- [ ] Encryption master key generated as part of an operator ceremony in `runbooks/pbs.md`; stored both encrypted in repo and at offline backup location
- [ ] VM yaml schema supports `backup:` block (schedule, retention)
- [ ] Global backup defaults in `group_vars/all/backup.yaml`; per-VM block overrides
- [ ] Service data captured implicitly via VM-level snapshot (no parallel file-level backup tool)
- [ ] `runbooks/pbs.md` covers initial setup, encryption-key ceremony, restore drill
- [ ] Demo: scheduled backup of a test VM runs; restore succeeds

## Blocked by

.scratch/initial-building-blocks/issues/06-nfs-integration.md