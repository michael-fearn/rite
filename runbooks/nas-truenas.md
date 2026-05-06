# TrueNAS NFS exports

Fortress keeps NAS topology in `inventory/group_vars/all.yaml` under `nas`. VMs declare `nfs_mounts` by export name, and `vm-configure` renders those declarations as systemd `.mount` units on the VM.

Use the TrueNAS share address for `nas.server`, not the management UI address. In the current topology, TrueNAS management is `10.10.0.15` and NFS exports are served from the infra share address `10.40.0.15`.

## UID/GID convention

Use the `nas.uid_gid_map` block as the shared ownership contract between TrueNAS datasets and VM workloads. Each key names the export/workload convention, and each value records the numeric `uid` and `gid` expected to own files for that dataset.

Example:

```yaml
nas:
  uid_gid_map:
    media:
      uid: 1000
      gid: 1000
```

On TrueNAS, create the matching user/group or otherwise ensure the dataset ACL resolves to the same numeric IDs. Before exposing a dataset, set ownership to the mapped IDs, for example:

```sh
chown -R 1000:1000 /mnt/pool/media
```

## TrueNAS dataset steps

1. Create the dataset at the path declared in `nas.exports`, such as `/mnt/pool/media`.
2. Apply ownership using the matching `nas.uid_gid_map` entry.
3. Configure an NFS share for the dataset path.
4. Allow the VM network or host addresses that need the export.
5. Keep the export path stable; VMs reference the Fortress export name, but the generated mount unit uses the TrueNAS path from `nas.exports`.
