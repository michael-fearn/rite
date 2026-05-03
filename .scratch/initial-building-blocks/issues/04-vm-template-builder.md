Status: needs-triage

## Parent

docs/prds/initial-building-blocks.md

## What to build

Per-host template inventory: download a cloud image (with required checksum verification), customize via virt-customize, create a Proxmox VM at the declared template VMID, mark as template. Idempotent skip if already a template at that VMID. Host yamls declare which templates they should hold.

## Acceptance criteria

- [ ] Template yaml schema includes: name, vmid (9000-9999), source URL, **required** checksum, virt-customize ops, hardware defaults
- [ ] Builder downloads image; refuses if checksum doesn't match declared value
- [ ] Image-checksum cache avoids redundant downloads
- [ ] virt-customize runs against a working copy, not the cache
- [ ] `qm` creates VM at declared VMID, imports disk, sets hardware + cloud-init drive, marks as template
- [ ] Skip if VMID already exists as a template on that host
- [ ] Host yaml schema includes a list of templates the host should hold
- [ ] `just templates-build host=<name>` builds all templates declared on that host
- [ ] `runbooks/new-template.md` written
- [ ] Demo: a debian-cloud template at the declared VMID on wintermute, second run is a no-op

## Blocked by

.scratch/initial-building-blocks/issues/03-host-configurator-workflow.md