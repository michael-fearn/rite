Status: needs-triage

# Live TrueNAS client preflight

## What to build

Introduce a thin fortress adapter around the official `truenas_api_client` package for live NAS Reconcile and run a non-mutating credential preflight before building a live plan. Fortress should not implement the WebSocket/JSON-RPC protocol itself; the adapter owns only fortress-specific method calls, error translation, and test seams.

## Acceptance criteria

- [ ] Live mode connects through `truenas_api_client.Client` to the selected NAS Endpoint `management_address` using the token value exported by issue 01.
- [ ] The TrueNAS API client dependency is installed/pinned through the project toolchain, preferably using a TrueNAS-version-matched stable tag.
- [ ] Preflight verifies the management API is reachable and Dataset/NFS Share read capabilities are available before reconciliation logic runs.
- [ ] Apply mode checks NFS Share write capability only if TrueNAS exposes a safe non-mutating permission check.
- [ ] Preflight never creates, updates, or deletes a Dataset or Share as a credential test.
- [ ] Connection failure, invalid credential, and insufficient privilege failures name the failed capability class without printing the credential value.
- [ ] Tests fake the fortress adapter boundary and do not require a live TrueNAS system.

## Blocked by

- .scratch/truenas-authentication/issues/01-live-nas-reconcile-sops-env-entrypoint.md
