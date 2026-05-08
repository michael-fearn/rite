# TrueNAS Datasets and NFS Shares

Fortress models NAS data as protected Datasets and disposable Shares. Ordinary Datasets are declared under `inventory/datasets/` with `lifecycle: adopted`; NAS Reconcile validates their expected state and derives NFS Shares from VM Mount and Service consumption declarations.

Declare both TrueNAS addresses on the NAS Endpoint. In the current topology, TrueNAS management is `10.10.0.15` and NFS Shares are served from the infra share address `10.40.0.15`.

```yaml
# inventory/nas/truenas.yaml
name: truenas
management_address: 10.10.0.15
share_address: 10.40.0.15
tls_verify: false
```

`management_address` is for TrueNAS API-backed NAS Reconcile. `share_address` is what VMs use when mounting NFS Shares. Live NAS Reconcile connects with encrypted WebSocket transport. Use `tls_verify: false` only when the endpoint presents a self-signed certificate that fortress cannot verify by CA chain, such as the IP-addressed lab endpoint. The NAS Reconcile Credential lives in `inventory/nas/truenas.sops.yaml`; no API token value or token environment variable belongs in plaintext Inventory.

```yaml
# inventory/nas/truenas.sops.yaml
api_credentials:
  reconcile:
    type: truenas_api_key
    value: ENC[...] # generated API key string
  acceptance:
    type: truenas_api_key
    value: ENC[...] # generated API key string
```

The workflow decrypts `api_credentials.reconcile.value` directly into a private child-process environment variable derived from the endpoint name, such as `FORTRESS_NAS_RECONCILE_TRUENAS_TOKEN`; it does not write a temporary token file. Store each TrueNAS API credential value as the generated API key string shown once by TrueNAS when the key is created or reset.

## NAS Credential Ceremony

ADR [0019](../docs/adr/0019-truenas-api-authentication-uses-operator-environment.md) defines the authentication model for live NAS Reconcile. Perform this NAS Credential Ceremony manually in TrueNAS for each NAS Endpoint, then store the generated credential values in the NAS Endpoint Sibling SOPS File at `inventory/nas/<endpoint>.sops.yaml`.

Create the ordinary NAS Reconcile Credential first:

1. In TrueNAS, create an API key named `fortress-nas-reconcile`.
2. Grant it Dataset-read intent so NAS Reconcile can inspect Dataset metadata and ownership.
3. Grant it NFS-Share-manage intent so NAS Reconcile can create, update, and destroy fortress-owned Shares.
4. Store the generated API key string at `api_credentials.reconcile.value` in `inventory/nas/<endpoint>.sops.yaml`.

The ordinary NAS Reconcile Credential must not create, update, or delete ordinary Datasets. Routine NAS Reconcile validates ordinary Datasets and manages derived Shares only.

Create the Acceptance NAS Credential in the same operator session:

1. In TrueNAS, create an API key named `fortress-acceptance-ephemeral`.
2. Grant it only the privileges needed by Acceptance Tests that create or destroy Ephemeral Datasets.
3. Store the generated API key string at `api_credentials.acceptance.value` in `inventory/nas/<endpoint>.sops.yaml`.

Do not use the Acceptance NAS Credential for routine NAS Reconcile. It exists so Acceptance Tests can prove Ephemeral Dataset mutation without widening the ordinary NAS Reconcile Credential.

Live NAS Reconcile uses the official `truenas_api_client` package to target the current TrueNAS SCALE API client/WebSocket API surface. Fortress does not implement the WebSocket/JSON-RPC protocol itself. The deprecated REST API is out of scope.

Before live planning or apply, NAS Reconcile performs a non-mutating credential preflight: the workflow must decrypt and export the SOPS-backed credential into its child process, the management API must be reachable over encrypted WebSocket transport, and Dataset/NFS Share read capabilities must be available. TrueNAS 25.10 requires TLS for API-key authentication and can revoke API keys presented over insecure transport; if live auth starts returning `Invalid API key`, reset the user-linked API key in TrueNAS and update `api_credentials.reconcile.value`. Write capability is checked only if TrueNAS exposes a safe non-mutating permission check; NAS Reconcile does not create a throwaway Share to test credentials.

Live commands name the NAS Endpoint explicitly, for example `scripts/nas-reconcile-plan --live truenas`. Fixture-backed commands with `--reality-json` remain endpoint-implicit, credential-free, and available for offline planning and tests.

Both live plan and live apply require `inventory/nas/<endpoint>.sops.yaml`; missing endpoint SOPS material fails before any network access.

## Live operator demo checklist

Use this checklist to prove endpoint-explicit live NAS Reconcile can read TrueNAS and produce a read-only plan without mutating TrueNAS:

1. Confirm `inventory/nas/truenas.yaml` declares the NAS Endpoint, its Management Address, and its Share Address.
2. Confirm `inventory/nas/truenas.sops.yaml` contains the NAS Reconcile Credential at `api_credentials.reconcile.value`.
3. Run `scripts/nas-reconcile-plan --live truenas` without `--apply`.
4. Confirm the command performs live preflight against the Management Address, loads TrueNAS reality, and prints a read-only plan.
5. Confirm the output reports the Credential Source as `inventory/nas/truenas.sops.yaml:api_credentials.reconcile.value` and never prints the credential value.
6. Confirm no ordinary Datasets are created, updated, or deleted, and no TrueNAS mutation occurs during the demo.

Expected failure modes:

- missing SOPS material: if `inventory/nas/truenas.sops.yaml` is absent or does not contain `api_credentials.reconcile.value`, the command fails before network access.
- insufficient privilege: if the `fortress-nas-reconcile` API key lacks Dataset-read or NFS Share read capability, live preflight fails before reconciliation logic runs. If later apply privileges are missing, retry after fixing the TrueNAS-side key rather than broadening the credential to mutate ordinary Datasets.

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
