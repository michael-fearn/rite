# PRD: PBS Backup Policy, Readiness, and Restore Discipline

**Status**: ready-for-agent
**Date**: 2026-05-22
**Companion documents**: `CONTEXT.md`, ADR 0015, ADR 0034, ADR 0035, ADR 0036, ADR 0037

---

## Problem Statement

The operator wants Fortress backups to become an explicit, testable operational discipline instead of informal PBS setup and loose `backup` metadata on VMs. Today PBS exists as a VM and several VMs declare backup blocks, but the repo does not yet have a fleet-level Backup Policy model, static validation that every production VM is either a Backup Target or an intentional Unprotected VM, PVE-side Backup Job reconciliation, live Backup Readiness, Backup Health reporting, or Restore Drill workflow.

The operator also wants the backup boundary to be precise. PBS protects VM recoverability and VM-local state. It does not protect NAS-backed Dataset history, does not promise point-in-time consistency with NAS-backed Datasets, and does not back up PBS itself through the local PBS instance. Those boundaries need to be represented in Inventory, validation, workflows, reporting, and restore practice.

## Solution

Introduce a fleet-level Backup Policy inventory model with one initial `default` policy. The `default` policy defines daily Backup Runs at `03:30 America/Denver`, deterministic per-VM staggering over `60m`, and retention of 14 daily, 8 weekly, and 12 monthly restore points. Production VMs explicitly declare whether they are Backup Targets or Unprotected VMs. Backup Targets use `default` when no policy is named; Unprotected VMs require an operator-facing reason. Generated or disposable VMs are exempt.

Add static validation first: backup policy schema, policy loading, policy reference checks, production VM backup declaration rules, unprotected reason checks, and real Inventory migration. Then add Backup Configure as a host-scoped operator workflow that plans and later applies one deterministic PVE-side Backup Job per Backup Target. Backup Configure owns only fortress-owned Backup Jobs, leaves manual PVE jobs alone, gates pruning behind confirmation, shows derived staggered times in its plan, and may trigger initial Backup Runs only by explicit operator choice.

Add live Backup Readiness after Backup Configure exists. A Backup Target is not production-ready until its policy, datastore path, PBS encryption Recovery Secret availability, and at least one successful Backup Run are proven. Add Backup Health reporting from PBS restore-point freshness, evaluated per Backup Target and rolled up by Host and fleet, with Unprotected VMs shown as excluded. Finally, add Restore Drills that create isolated, disposable Restored Drill VMs to prove recovery from backup reality without production identity collisions or production NAS-backed Dataset mutation.

## User Stories

1. As the operator, I want PBS backup intent declared in Inventory, so that backup protection is reviewable before workflows run.

2. As the operator, I want a fleet-level Backup Policy file, so that schedule and retention are defined once instead of repeated across VMs.

3. As the operator, I want the first committed Backup Policy to be `default`, so that current backup behavior starts simple.

4. As the operator, I want `default` to run daily, so that every Backup Target gets routine VM recovery points.

5. As the operator, I want `default` to run at `03:30 America/Denver`, so that Backup Runs happen at a predictable local quiet time.

6. As the operator, I want Backup Jobs staggered over `60m`, so that all protected VMs do not start backing up at once.

7. As the operator, I want Backup Job stagger offsets derived from Backup Target identity, so that schedules stay stable across reconciliation.

8. As the operator, I want `default` retention to keep 14 daily restore points, so that recent mistakes can be rolled back.

9. As the operator, I want `default` retention to keep 8 weekly restore points, so that weekly rollback remains available beyond the daily window.

10. As the operator, I want `default` retention to keep 12 monthly restore points, so that long-horizon VM recovery remains possible.

11. As the operator, I want retention keys to use domain names like daily, weekly, and monthly, so that Inventory does not expose PBS CLI syntax.

12. As the operator, I want every production VM to declare backup enablement explicitly, so that omission cannot silently mean unprotected.

13. As the operator, I want `backup.enabled: true` to make a VM a Backup Target, so that protection is explicit.

14. As the operator, I want `backup.policy` to be optional for Backup Targets, so that ordinary VMs use `default` without noisy metadata.

15. As the operator, I want a named policy reference when a VM deviates from default later, so that policy adoption can evolve without changing schema shape.

16. As the operator, I want `backup.enabled: false` production VMs to require a reason, so that Unprotected VMs are deliberate.

17. As the operator, I want `pbs-vm` to remain an Unprotected VM with a reason, so that PBS self-reference does not confuse recovery.

18. As the operator, I want generated and disposable VMs exempt from backup declarations, so that acceptance, verification, and drill artifacts do not need production recovery metadata.

19. As the operator, I want PBS to protect VM recoverability and VM-local state, so that the recovery promise is clear.

20. As the operator, I want NAS-backed Dataset history to stay outside the PBS promise, so that I do not confuse VM restore with NAS recovery.

21. As the operator, I want PBS Restore to avoid promising point-in-time consistency with NAS-backed Datasets, so that split-state services are treated carefully.

22. As the operator, I want policy validation to reject unknown policy references, so that Backup Targets cannot point at typos.

23. As the operator, I want policy validation to allow future named policies structurally, so that the model can grow without a schema rewrite.

24. As the operator, I want current repo Inventory migrated in the same static slice, so that validation stays green immediately.

25. As the operator, I want every current production VM except `pbs-vm` protected by `default`, so that existing durable VMs are backed up.

26. As the operator, I want Backup Jobs provisioned through PVE, so that VM backup scheduling happens where VMs and hosts are managed.

27. As the operator, I want each Backup Target to have its own Backup Job, so that policy adoption changes remain local to a VM.

28. As the operator, I want Backup Jobs named deterministically from Backup Target and Backup Policy, so that PVE state is readable and reconcilable.

29. As the operator, I want Backup Configure to be a dedicated workflow, so that backup scheduling does not get buried inside Host Configure.

30. As the operator, I want Backup Configure to be host-scoped, so that backup job reconciliation failures are contained.

31. As the operator, I want fleet Backup Configure to iterate Hosts, so that I can still converge the whole fleet when desired.

32. As the operator, I want Backup Configure plan-only before apply, so that risky PVE mutations can be inspected first.

33. As the operator, I want Backup Configure plans to show VM, policy, datastore, action, deterministic job name, and derived scheduled time, so that I can review exactly what will happen.

34. As the operator, I want Backup Configure to leave manual PVE jobs alone, so that Fortress does not delete operator break-glass or experimental jobs.

35. As the operator, I want Backup Configure to prune only obsolete fortress-owned Backup Jobs, so that policy changes and backup disablement do not leave stale Fortress jobs behind.

36. As the operator, I want Backup Job pruning confirmation-gated, so that deleting future protection is never a surprise.

37. As the operator, I want Backup Configure to optionally trigger initial Backup Runs explicitly, so that I can establish Backup Readiness immediately when I choose.

38. As the operator, I want initial Backup Runs to ignore scheduled stagger when explicitly triggered, so that readiness can be achieved now.

39. As the operator, I want first-run triggering to support one VM or a host-scoped set, so that both targeted and host-readiness workflows are ergonomic.

40. As the operator, I want Backup Configure to report pending first successful runs, so that job creation is not confused with actual protection.

41. As the operator, I want Backup Readiness to require at least one successful Backup Run, so that an unused job is not treated as protection.

42. As the operator, I want static Backup Readiness foundations separated from live checks, so that the first slice can validate Inventory without pretending PBS was contacted.

43. As the operator, I want Backup Readiness to gate production readiness for Backup Targets, so that Services are not launched on VMs that claim backup protection but are not actually protected.

44. As the operator, I want Service Launch to treat Backup Readiness as a prerequisite without running Backup Configure, so that launch remains focused and backup changes stay explicit.

45. As the operator, I want Backup Health based first on PBS restore-point freshness, so that reports reflect actual recoverable snapshots.

46. As the operator, I want default Backup Targets unhealthy after 36 hours without a fresh successful restore point, so that a missed daily backup becomes visible promptly.

47. As the operator, I want Backup Health evaluated per Backup Target, so that each VM has an explicit protection status.

48. As the operator, I want Host and fleet Backup Health rollups, so that I can see backup status at operational scopes.

49. As the operator, I want Unprotected VMs shown as excluded in Backup Health reporting, so that accepted risks stay visible without becoming false failures.

50. As the operator, I want the PBS encryption key treated as a Recovery Secret, so that encrypted backups are recoverable after workstation or VM loss.

51. As the operator, I want Backup Readiness to include Recovery Secret availability, so that green backup jobs do not hide unrecoverable encryption.

52. As the operator, I want Restore Drills distinct from Acceptance Tests, so that recovery from backup reality is not confused with creation from declared intent.

53. As the operator, I want Restore Drills to use generated disposable Restored Drill VMs, so that production Inventory does not fill with restore clones.

54. As the operator, I want Restored Drill VM placement selected per drill, so that capacity and isolation can be chosen intentionally.

55. As the operator, I want Restored Drill VMs on a Drill Network by default, so that restored production identity does not collide with live VMs.

56. As the operator, I want Restored Drill VMs to avoid production ingress and DNS, so that restored services are not accidentally exposed.

57. As the operator, I want Restore Drills to avoid mutating production NAS-backed Datasets, so that drill verification does not damage live data.

58. As the operator, I want Restore Drills to preserve restored production secrets but keep drill access operator-only, so that the drill proves real recovery while remaining contained.

59. As the operator, I want Restore Drills to destroy Restored Drill VMs by default, so that sensitive recovered VMs do not linger.

60. As the operator, I want keep-on-fail for Restore Drills, so that failed drills can be diagnosed explicitly.

61. As a future maintainer, I want backup policy parsing isolated behind a small interface, so that schema, validation, planning, and workflows do not duplicate YAML traversal.

62. As a future maintainer, I want Backup Configure planning isolated from PVE mutation, so that deterministic naming, staggering, and pruning decisions are easy to test without live infrastructure.

63. As a future maintainer, I want live Backup Health querying isolated from reporting, so that PBS API details do not leak into rollup and operator output logic.

64. As a future maintainer, I want Restore Drill planning isolated from execution, so that identity, network, NAS, and cleanup safety can be tested before live restore support.

## Implementation Decisions

- Use the glossary in `CONTEXT.md`: **PBS**, **Datastore**, **Primary Datastore**, **Backup Policy**, **Backup Target**, **Unprotected VM**, **Backup Job**, **Backup Configure**, **Backup Readiness**, **Backup Health**, **PBS Restore**, **Restore Drill**, **Restored Drill VM**, **Drill Network**, and **Recovery Secret**.

- Respect ADR 0015: PBS client-side encryption exists from day one, and the PBS encryption key is a Recovery Secret stored in SOPS and offline recovery material.

- Respect ADR 0034: Backup Targets opt in with `backup.enabled`, choose a named Backup Policy defaulting to `default`, and each Backup Target gets one PVE-side Backup Job staggered from the policy time by Backup Target identity.

- Respect ADR 0035: Restore Drills use isolated disposable Restored Drill VMs and are distinct from Acceptance Tests.

- Respect ADR 0036: Backup Readiness gates production readiness for Backup Targets, and Unprotected VMs require explicit reasons.

- Respect ADR 0037: Backup Configure reconciles per-VM fortress-owned PVE jobs, leaves manual PVE jobs alone, and confirmation-gates pruning.

- Build a backup policy inventory contract with a required `default` policy. The initial committed Inventory contains no unused future policy placeholders.

- Let the policy file structurally support multiple named policies, while validation requires that every referenced policy exists.

- Make the initial `default` policy daily at `03:30` in `America/Denver`, with a `60m` stagger band and daily/weekly/monthly retention of 14/8/12.

- Keep the literal string `MST` out of Inventory. Use the IANA timezone name.

- Treat schedule and retention as Backup Policy concerns. VM inventory selects protection and optional policy, but does not define schedule or retention details.

- Keep `backup.enabled` separate from `backup.policy`. Policy selection alone does not make a VM a Backup Target.

- Require every production VM to explicitly become a Backup Target or an Unprotected VM. Generated or disposable VMs are exempt.

- Treat `pbs-vm` as an Unprotected VM with an explicit reason because PBS itself is rebuilt from Inventory, the Primary Datastore, and Recovery Secrets.

- Model PBS protection as VM-level recoverability. NAS-backed Dataset history and VM/NAS point-in-time consistency are out of the PBS protection promise.

- Add a backup policy loader to the Inventory model so validation and future workflows consume one canonical parsed representation.

- Add a backup policy schema to the existing schema validation suite and fixtures.

- Tighten the VM backup schema so `backup.enabled` is required for production VMs, optional `backup.policy` is a non-empty string when present, and `backup.reason` is required only for unprotected production VMs.

- Add cross-file validation for missing policy file, missing `default`, invalid policy references, missing backup declaration on production VMs, missing unprotected reasons, and invalid backup metadata on generated/disposable VMs if needed.

- Update current VM Inventory in the same static slice. Existing production VMs except `pbs-vm` remain or become Backup Targets on `default`; `pbs-vm` becomes an Unprotected VM with a reason.

- Implement Backup Configure as a separate host-scoped workflow, not as Host Configure and not as implicit Service Launch behavior.

- Add Backup Configure plan-only before apply. The plan is a deep, testable module that receives Inventory plus observed PVE job state and returns create/update/prune/no-op actions.

- Derive Backup Job names deterministically from Backup Target and Backup Policy.

- Derive Backup Job scheduled times deterministically from Backup Target identity and the policy stagger band.

- Have Backup Configure plans report each Backup Job action, target VM, policy, Primary Datastore, deterministic name, and derived scheduled time.

- Add Backup Configure apply after plan-only is proven. Apply creates and updates fortress-owned jobs, prunes only obsolete fortress-owned jobs, and leaves manual jobs alone.

- Gate Backup Job pruning behind operator confirmation, with explicit auto-confirm behavior only when requested.

- Let Backup Configure optionally trigger initial Backup Runs by explicit operator choice. Job creation alone does not satisfy Backup Readiness.

- Implement live Backup Readiness after Backup Configure. It includes policy validity, usable datastore path, Recovery Secret availability, Backup Job presence, and at least one successful Backup Run.

- Implement Backup Health from PBS restore-point freshness first. PVE task history can later enrich diagnostics but is not the first source of truth.

- Represent Backup Health per Backup Target, then roll up to Host and fleet. Represent Unprotected VMs as excluded.

- Keep Restore Drill implementation out of the first static slice and out of Backup Configure. Restore Drill is its own later workflow family.

- Restore Drill workflows create generated/disposable Restored Drill VMs rather than durable VM Inventory entities.

- Restore Drill safety defaults: Drill Network by default, no production identity collision, no production ingress/DNS, no production NAS-backed Dataset mutation, operator-only access, cleanup by default, keep-on-fail by explicit operator choice.

## Testing Decisions

- Tests should verify external behavior and domain contracts: accepted schema shapes, rejected invalid Inventory, cross-file validation errors, Backup Configure plans, apply safety boundaries, live readiness status, health rollups, and Restore Drill safety planning.

- Add schema tests for the backup policy file. Prior art: the existing inventory schema test suite that runs `check-jsonschema` against valid and invalid fixtures.

- Add VM schema tests for protected and unprotected backup declarations. Prior art: existing VM schema tests for lifecycle, mounts, instrumentation, service group launch order, and tailnet subnet router declarations.

- Add inventory model tests proving backup policies load through the Inventory model. Prior art: existing model tests for Datasets, template verification policy, and defaulted VM instrumentation.

- Add cross-file validator tests for missing `default`, unknown policy reference, missing production backup declaration, missing unprotected reason, `pbs-vm` unprotected reason, generated/disposable VM exemption, and real repo Inventory validity.

- Add tests that the real Inventory contains only the `default` policy initially and that all current production VMs except `pbs-vm` are Backup Targets.

- Add focused unit tests for deterministic stagger derivation. Tests should assert stability, schedule times inside the `60m` band, and independence from policy name except for the policy's band.

- Add Backup Configure plan tests against fake Inventory and fake observed PVE jobs. The tests should cover create, update, no-op, prune obsolete fortress-owned job, and ignore manual job.

- Add Backup Configure plan tests that show derived per-VM scheduled times in operator-facing output.

- Add Backup Configure apply tests with a fake PVE client. Cover create/update calls, confirmation-gated prune, no prune without confirmation, and manual jobs untouched.

- Add tests for explicit initial Backup Run triggering. Cover single VM, host-scoped set, no implicit run by default, and failure reporting.

- Add live Backup Readiness tests using fake PBS/PVE/secret providers. Cover job exists but no successful run, successful restore point exists, missing Recovery Secret, missing datastore, and unknown policy.

- Add Backup Health tests using fake PBS snapshot metadata. Cover healthy default Backup Target, unhealthy stale target after 36 hours, missing snapshot, Host/fleet rollups, and Unprotected VM excluded status.

- Add Restore Drill planner tests before live restore implementation. Cover isolated Drill Network default, production identity collision avoidance, production NAS mutation prevention, restored secret sensitivity, cleanup default, and keep-on-fail.

- Avoid tests that assert private helper structure. Prefer planner outputs, validation error codes, rendered commands, provider calls, and operator-facing plan summaries.

## Out of Scope

- Hourly or high-frequency backup policy design is out of scope. It was deliberately removed from the current plan.

- Local PBS Datastore and Backup Sync are out of scope.

- NAS Dataset snapshots, NAS replication, and NAS-backed Dataset recovery are out of scope.

- VM/NAS point-in-time consistency is out of scope.

- Off-site PBS replication is out of scope.

- PBS self-backup through the local PBS instance is out of scope.

- Backup Configure live apply is out of scope for the first static Inventory slice.

- Backup Health reporting is out of scope for the first static Inventory slice.

- Restore Drill implementation is out of scope for the first static Inventory slice.

- Service Launch automatically running Backup Configure is out of scope.

- PVE task-history based Backup Health diagnostics are out of scope for the first health slice.

- Application-specific restore validation is out of scope; Restore Drill proves VM recovery shape and later workflow health hooks, not every application's semantic correctness.

## Further Notes

- The implementation should be sliced in this order: static backup policy Inventory and validation; Backup Configure plan-only; Backup Configure apply; live Backup Readiness and first-run verification; Backup Health reporting; Restore Drill workflow.

- Natural deep modules are: backup policy parsing/resolution, backup declaration validation, deterministic schedule/stagger planning, Backup Configure planning, PVE Backup Job reconciliation, PBS restore-point freshness querying, Backup Readiness evaluation, Backup Health rollup, and Restore Drill planning.

- The first issue should be a tracer bullet: add the policy file, schema, loader, validator, and current VM migration in one change so the repo proves the static model end to end.

- Later issues should keep mutation behind plan/apply boundaries. Backup Configure plan-only should land before live PVE mutation.

- `CONTEXT.md` and ADRs 0034 through 0037 were updated during design and should remain the terminology source for future issues.

