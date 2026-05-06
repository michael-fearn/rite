Status: ready-for-human

## Parent

docs/prds/initial-building-blocks.md

## What to build

NAS topology declared once globally; per-VM NFS mount declarations reference exports by name; mounts implemented as systemd `.mount` units so quadlets can declare `Requires=` for ordering. UID/GID convention coordinated with TrueNAS dataset ownership.

## Acceptance criteria

- [x] Global NAS topology in `inventory/group_vars/all.yaml`: server, named exports, default mount options, UID/GID convention
- [x] VM yaml schema supports a `nfs_mounts:` block referencing exports by name
- [x] Per-VM mounts rendered as systemd `.mount` units on the VM
- [x] UID/GID convention documented in `runbooks/nas-truenas.md` alongside required TrueNAS-side dataset ownership steps
- [x] Cross-file validator checks NFS export name references resolve against global exports
- [x] `vm-up` workflow extended to write mount units when present
- [ ] Demo: a test VM with declared mount has a functional, systemd-managed NFS mount

## Blocked by

.scratch/initial-building-blocks/issues/05-tofu-yaml-to-resource-bridge-vm-lifecycle.md
