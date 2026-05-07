# TrueNAS Datasets and NFS Shares

Fortress models NAS data as protected Datasets and disposable Shares. Ordinary Datasets are declared under `inventory/datasets/` with `lifecycle: adopted`; NAS Reconcile validates their expected state and derives NFS Shares from VM Mount and Service consumption declarations.

Use the TrueNAS share address for the NAS endpoint, not the management UI address. In the current topology, TrueNAS management is `10.10.0.15` and NFS Shares are served from the infra share address `10.40.0.15`.

```yaml
nas:
  endpoints:
    truenas:
      address: 10.40.0.15
```

## UID/GID convention

Keep NAS-facing numeric identities in `inventory/group_vars/all.yaml` under `nas.uid_gid_map` so VMs and TrueNAS agree on ownership by number:

```yaml
nas:
  uid_gid_map:
    media:
      uid: 1000
      gid: 1000
```

Use the same UID/GID values when declaring Dataset ownership and when creating the matching TrueNAS user/group. Numeric IDs are the contract; names may differ between TrueNAS and guest VMs.

## Dataset ownership

Declare Dataset ownership on the Dataset, not on the Share:

```yaml
# inventory/datasets/media.yaml
name: media
nas: truenas
path: /mnt/pool/media
lifecycle: adopted
owner:
  uid: 1000
  gid: 1000
```

On TrueNAS, create the matching user/group or otherwise ensure the Dataset root resolves to the same numeric IDs. Before exposing an adopted Dataset, set its root ownership to the declared IDs, for example:

```sh
chown 1000:1000 /mnt/pool/media
```

NAS Reconcile validates the Dataset root owner UID/GID and fails on drift by default. It does not recursively repair ownership for adopted data.

## VM Mount declarations

VMs declare Dataset access through Mounts:

```yaml
mounts:
  - name: media
    dataset: media
    protocol: nfs
    mount_point: /mnt/nas/media
    access: read_write
```

Mount-bearing VMs must have an unambiguous static IP address in Inventory. Derived NFS Shares allow explicit VM IP clients rather than broad networks by default.

## NAS Reconcile

The first NAS Reconcile implementation may be a read-only plan that compares fortress intent with TrueNAS reality. The target workflow is API-backed reconciliation:

1. Validate each adopted Dataset exists at its declared TrueNAS path.
2. Validate each adopted Dataset root owner UID/GID.
3. Derive desired NFS Shares from VM Mount and Service consumption declarations.
4. Report unmanaged Shares that could expose the same Dataset as a desired fortress-owned Share.
5. Update or destroy only fortress-owned Shares with durable ownership markers.

Unused fortress-owned Shares may be destroyed during NAS Reconcile after the relevant Mount removal is confirmed. Ordinary Datasets are never deleted by fortress.
