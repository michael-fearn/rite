Status: needs-triage

# Live Fortress-owned Share apply

## What to build

Wire live `--apply` to execute the existing NAS Reconcile write actions against TrueNAS NFS Shares for the selected NAS Endpoint. The workflow may create, update, and delete Fortress-owned Shares, but must not mutate ordinary Datasets.

## Acceptance criteria

- [ ] `scripts/nas-reconcile-plan --live truenas --apply` executes planned `create_nfs_share`, `update_nfs_share`, and `delete_nfs_share` actions through the TrueNAS client.
- [ ] Apply refuses to create, update, delete, or repair ordinary Adopted Datasets.
- [ ] Share writes include the durable Fortress ownership marker used by existing planning logic.
- [ ] If a TrueNAS write fails, the workflow stops at the first failed operation, returns non-zero, and reports the operation class and Share target.
- [ ] Failed apply does not attempt rollback or compensating delete/update; the next live plan shows remaining drift.
- [ ] Tests prove forward-retry behavior with a fake client that fails mid-apply.

## Blocked by

- .scratch/truenas-authentication/issues/03-live-truenas-reality-to-nas-reconcile-plan.md
