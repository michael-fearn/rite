# NFS mounts as systemd `.mount` units

NFS Exports are mounted via systemd `.mount` units — not `/etc/fstab`, not autofs, not in-container mounts. Global NAS topology lives in `group_vars/all.yaml`; per-VM Mount declarations reference Exports by name. The `.mount` unit is a first-class systemd dependency, which lets Quadlet containers declare `Requires=`/`After=` on it via `requires_mounts:` and start in the correct order. Fstab and autofs offer no equivalent ordering hook, and in-container mounts couple service definitions to NFS topology.
