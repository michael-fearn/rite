# Scoped Update Workflows

Use this runbook for routine maintenance on already-declared fortress Entities. Update is routine in-place advancement within the current compatibility band. Upgrade is reserved for version-boundary or migration-bearing advancement.

Host Update, Template Update, VM Update, and Service Update are separate workflows because they have different blast radii and safety gates. They preserve identity, placement, and declared shape. Routine Update avoids package removals, release transitions, database migrations, and application breaking migrations; plan those as explicit Upgrade or application maintenance work.

Host Update and VM Update are package-manager-neutral domain concepts even when the current implementation uses apt below the domain model. Keep package-manager specifics in the workflow implementation or lower-level operator notes, not in the glossary.

## Host Update

Run the non-reboot Host maintenance path with:

```sh
just host-update <host>
```

Host Update runs Host Configure first, then performs routine Host software advancement. It updates only the selected Host. Hosted VMs and resident Services are impacted dependents, not update targets.

When the Host requires a maintenance-window reboot, use the reboot path:

```sh
just host-update <host> --reboot
```

Before rebooting, Host Update reports `Ordinary VMs impacted on Host` and `Resident Services impacted through those VMs`. Continue only in a maintenance window. Type `reboot <host>` at the confirmation gate. The workflow gracefully shuts down the ordinary VMs it reported, reboots the selected Host, verifies Host reachability, and starts the same ordinary VMs it shut down.

If an ordinary VM does not stop cleanly, stop and inspect before continuing. Do not force the reboot from this workflow unless the operator has made a separate recovery decision.

Out of scope for Host Update: it does not run Template Update, does not update VMs or Services implicitly, does not rebuild Templates held by the Host, and does not perform release transitions or package removals.

## VM Update

Run the non-reboot VM maintenance path with:

```sh
just vm-update <vm>
```

VM Update runs VM Configure first, then performs routine VM software advancement. It updates only the selected VM. Resident Services may be interrupted by VM maintenance, but they are impacted dependents, not update targets.

When the VM requires a maintenance-window reboot, use the reboot-capable VM Update path once that command surface is present:

```sh
just vm-update <vm> --reboot
```

Before rebooting, VM Update reports `Resident fortress-managed Services on VM`. Continue only in a maintenance window. Type `reboot <vm>` at the confirmation gate. The workflow stops resident fortress-managed Services normally, verifies they are stopped, reboots the selected VM, verifies VM reachability, and restores the same resident fortress-managed Services it stopped.

If a Service does not stop cleanly or fails to return to active state, stop and inspect the named Service units before continuing.

Out of scope for VM Update: it does not run Template Update, does not mutate the source Template, does not update resident Services to newer declared versions, and does not perform release transitions, package removals, database migrations, or application breaking migrations.

## Template Update

Run Template Update for one selected Host copy with:

```sh
just template-update host=<host> template=<template>
```

Template Update rebuilds the selected Template from declared Template Inventory, replaces one selected Host copy, and proves the result with Template Verification. Its live side effect is temporary Template Verification VM use during verification.

Use explicit all-Hosts mode only when every declaring Host copy should be updated:

```sh
just template-update host=all template=<template>
```

There is no implicit fleet-wide Template Update path. `host=all` is the visible operator choice for all-Hosts mode.

Before rebuilding, review the lineage report. It lists existing VMs that declare the selected Template so the operator can see the relationship, but existing VMs are not changed. Existing VMs are durable cloned Entities after creation; updating a Template does not update, rebuild, reboot, or reconfigure them.

If Template Verification fails, follow the reported preservation policy. Use `keep_on_fail=true` when preserving the temporary Template Verification VM and generated artifacts is useful for inspection.

Out of scope for Template Update: it does not change existing VMs, does not run VM Update, does not deploy Services, and does not perform release transitions or application migrations inside existing workloads.

## Service Update

Run Service Update with:

```sh
just service-update <service>
```

For non-interactive restart approval after the operator has already decided the interruption is acceptable, run:

```sh
just service-update <service> auto_confirm=true
```

Service Update runs Service Deploy first so generated artifacts, Service Secrets, Service-owned directories, and systemd units match current Inventory. It advances only to declared runtime references. Selecting a newer image tag, package stream, or application version happens by changing Inventory first.

After Service Deploy, Service Update restarts all fortress-owned units for the named Service and verifies all fortress-owned units for the named Service reach active state. It updates only the named Service and does not restart Service Group peers implicitly, even when other Services share the same Backend VM, Service Group, or Service Network.

Out of scope for Service Update: it does not choose newer runtime references outside Inventory, does not coordinate grouped Service maintenance, does not run application health checks beyond active systemd state, and does not perform database migrations or application breaking migrations. There is no Service Group Update workflow.
