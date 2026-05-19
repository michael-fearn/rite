# PRD: Deepen Service Runtime Intent

**Status**: ready-for-agent
**Date**: 2026-05-19
**Companion documents**: `CONTEXT.md`, `docs/adr/0016-fortress-models-only-service-invariants-above-quadlet.md`, `docs/adr/0023-service-secrets-are-structured-per-service-sops-entries.md`, `docs/adr/0030-service-groups-are-logical-service-networks-own-podman-networking.md`

---

## Problem Statement

The operator wants Service deployment, validation, rendering, and later workflow planning to speak in fortress domain facts instead of repeatedly traversing raw Service yaml. The codebase already has **Service Runtime Intent**, but the first completed tracer bullet covers only Backend placement, Published Ports, and Telemetry Targets.

That leaves important fortress-owned runtime meaning split across shallow Modules. Share-backed Volumes are resolved partly in the Inventory Entity Graph, partly in validation, partly in Service Deploy, and partly in Quadlet rendering. Service-owned volumes and Service Data Directories are resolved in Quadlet rendering even though Service Deploy and validation also need that meaning. Service Secrets and Native Service Environment Secrets are interpreted by deploy helpers, validation, preflight, and renderers independently.

This creates low Locality. A change to Service volume or secret semantics requires touching several callers that all know nested `deploy.containers` shape. It also weakens tests: many tests must assert deploy vars, rendered Quadlet text, or validation errors to prove rules that should be testable directly at the **Service Runtime Intent** seam.

## Solution

Deepen **Service Runtime Intent** into the canonical fleet-wide Module for fortress-owned Service runtime meaning. Fleet-wide analysis remains canonical because cross-Service facts such as port collisions and Service Network alias collisions require global visibility. Per-Service access should be a convenience view over the fleet-wide result, not a second analysis path.

**Service Runtime Intent** owns meaning and diagnostics, not rendered artifacts. It should expose resolved facts for Backend placement, Published Ports, Telemetry Targets, Share-backed Volumes, Service-owned volumes, Service Data Directories, Service Secrets, Native Service Environment Secrets, Service Network wiring, and container start order. Inventory validation remains the Adapter that turns runtime diagnostics into operator-facing validation errors. Quadlet rendering, Ansible variable names, systemd command details, Grafana JSON, generated Prometheus files, and application-specific configuration remain Adapter concerns.

The next implementation milestone is **Share-backed Volumes, Service Data Directories, and Service secret wiring through Service Runtime Intent**. It should preserve current operator behavior while moving runtime meaning into the deeper Module.

## User Stories

1. As the operator, I want **Service Runtime Intent** to explain a Service's runtime facts, so that I do not need to reason through raw Service yaml.

2. As the operator, I want Inventory validation to report the same errors after this refactor, so that architectural cleanup does not change the command surface unexpectedly.

3. As the operator, I want Share-backed Volumes resolved through the Service's Backend VM Mounts, so that Service yaml never needs to know NAS Endpoint, Dataset, or Share topology directly.

4. As the operator, I want a Share-backed Volume that references a missing Mount Name to be diagnosed before Service deployment, so that deployment fails early.

5. As the operator, I want a Share-backed Volume source to be either `/` or a safe relative subpath, so that container bind mounts cannot escape the VM Mount root.

6. As the operator, I want a Share-backed Volume to narrow Mount access but never widen it, so that a read-only Mount cannot become read-write inside a container.

7. As the operator, I want Share-backed Volume source paths to be resolved once, so that validation, deploy preflight, and Quadlet rendering do not each rebuild the same path.

8. As the operator, I want Share-backed Volumes to expose their required systemd mount units as runtime facts, so that rendered Quadlet containers can order after the correct Mount.

9. As the operator, I want Service-owned volumes to resolve to Service Data Directory paths under `/srv/services/<service>/`, so that Service-owned state has one predictable root.

10. As the operator, I want Service Data Owner to apply only to Service Data Directories, so that Share-backed Volume ownership stays governed by the VM Mount and NAS ownership convention.

11. As the operator, I want Service Data Directory contents to remain unpruned by Service Deploy, so that a refactor does not accidentally destroy durable Service data.

12. As the operator, I want Service Data Directory facts separated from rendered Service Data Files, so that generated Observability artifacts and application configuration remain Adapter concerns.

13. As the operator, I want Quadlet Service Secrets to resolve to service-scoped Podman secret names, so that secret installation and rendering use one naming rule.

14. As the operator, I want Service Secret references to require `secrets.<name>`, so that all Service Secrets live in the Service Sibling SOPS File.

15. As the operator, I want Service Secret `_FILE` environment wiring to remain explicit, so that containers receive secret file paths only when declared.

16. As the operator, I want Service Secrets that use `env_value: secret_name` to keep working, so that images expecting Podman secret names remain supported.

17. As the operator, I want Native Service Environment Secrets to use the same structured SOPS entry interpretation, so that native Services and Quadlet Services share secret lifecycle rules.

18. As the operator, I want Native Service Environment Secrets to stay distinct from Quadlet Service Secrets, so that native config/template deployment does not pretend to install Podman secrets.

19. As the operator, I want missing or malformed structured SOPS entries to fail before remote execution, so that secret values are never printed or passed through unsafe paths.

20. As the operator, I want Service Deploy to keep producing the same Ansible variables while its source of meaning moves deeper, so that the remote playbook does not change unnecessarily.

21. As the operator, I want Quadlet rendering output to remain unchanged in the first milestone, so that the refactor does not alter container runtime behavior.

22. As the operator, I want Observability generated Service Data Files to stay out of this first milestone, so that application configuration generation does not expand the blast radius.

23. As the operator, I want Application Configuration Templates to stay Adapter-owned, so that fortress still models only its own invariants above Quadlet.

24. As a future maintainer, I want Service Runtime Intent tests to prove Service volume and secret meaning directly, so that deploy and renderer tests can focus on their Adapter behavior.

25. As a future maintainer, I want runtime diagnostics to carry stable code, path, and message fields, so that Inventory validation can adapt them without losing operator-facing clarity.

26. As a future maintainer, I want per-Service runtime intent access to be a view over fleet-wide analysis, so that single-Service deploy code does not accidentally get different semantics.

27. As a future maintainer, I want partial facts returned alongside diagnostics, so that validation can report multiple problems in one run.

28. As a future maintainer, I want Service Runtime Intent to become the natural place for later Service Network and container start-order facts, so that the Module continues to deepen over time.

29. As a future maintainer, I want the compatibility Adapter in the old import location to keep working while new code imports the canonical Module, so that migration can happen safely.

30. As a future maintainer, I want existing runbooks and terminology to keep using **Service Runtime Intent**, **Share-backed Volume**, **Service Data Directory**, **Service Secret**, and **Native Service Environment Secret** consistently, so that future agents do not reintroduce raw-config language.

## Implementation Decisions

- **Service Runtime Intent** owns fortress-owned Service runtime meaning, not rendered artifacts.

- Fleet-wide Service Runtime Intent analysis is canonical. Per-Service access is allowed only as a convenience view over the fleet-wide result.

- Service Runtime Intent owns diagnostics for runtime-meaning invariants. Inventory validation adapts those diagnostics into `ValidationError`s. JSON Schema remains responsible for schema-shape validation.

- Preserve existing operator-facing validation codes and messages wherever practical. Improve messages only when the current shape is misleading or incomplete.

- The first milestone covers Share-backed Volumes, Service-owned volumes, Service Data Directories, Quadlet Service Secrets, and Native Service Environment Secrets.

- Share-backed Volume runtime facts should identify the Service, Backend VM, container, volume index, Mount Name, Dataset when available, VM Mount path, resolved source path, container path, effective access mode, and required systemd mount unit.

- Service-owned volume or Service Data Directory runtime facts should identify the Service, container, volume index, Service Path, resolved VM-local path, container path, effective access mode, and Service Data Owner when declared.

- Service Secret runtime facts should identify the Service, container, secret index, secret key, service-scoped Podman secret name, environment variable name, and whether the container receives a file path or the secret name.

- Native Service Environment Secret runtime facts should identify the Service, secret index, secret key, environment variable name, and SOPS extraction path.

- Structured SOPS entry preflight can continue to decrypt only inside Service Deploy, but the required secret keys and extraction paths should come from Service Runtime Intent facts.

- Do not move secret values into Service Runtime Intent. The Module handles secret references, names, and required structured paths only.

- Keep rendered Quadlet text in the Quadlet renderer. The renderer may consume runtime facts, but Service Runtime Intent should not render `.container` or `.network` files.

- Keep Ansible variable names and playbook shape in Service Deploy. Service Deploy may consume runtime facts to build existing vars, but Service Runtime Intent should not become a deploy-var renderer.

- Keep Observability generated files, Grafana dashboards, Prometheus configuration, and Application Configuration Templates out of the first milestone.

- Keep current Service Deploy behavior unchanged: subpath validation still happens before starting containers, Service Secrets still install before container start, and Service Data Directories/Files still exist before start.

- Keep the existing compatibility Adapter for `fortress_services.runtime_intent`, but new code should prefer the canonical Inventory-owned Service Runtime Intent Module.

- Later slices should move Service Network wiring, Container Alias namespace facts, container start order, and additional Observability/Ingress callers onto the deeper Service Runtime Intent seam.

## Testing Decisions

- Good tests should cross the deepest stable seam available. Service Runtime Intent tests should prove runtime facts and diagnostics directly; validation, deploy, and renderer tests should cover Adapter behavior and preserve external output.

- Add direct Service Runtime Intent tests for Share-backed Volume facts, including root Mount binding, relative subpath binding, effective access, resolved source path, missing Mount diagnostics, unsafe source diagnostics, and access-widening diagnostics.

- Add direct Service Runtime Intent tests for Service-owned volume and Service Data Directory facts, including Service Data Owner application and duplicate directory de-duplication.

- Add direct Service Runtime Intent tests for Quadlet Service Secret facts, including service-scoped Podman secret names, `secrets.<name>` extraction, `_FILE` environment default, and `env_value: secret_name`.

- Add direct Service Runtime Intent tests for Native Service Environment Secret facts, including environment variable name and SOPS extraction path.

- Add direct Service Runtime Intent tests proving partial facts and diagnostics can coexist.

- Update Inventory validation tests only where the implementation migrates existing diagnostics. Preserve current expected codes for missing Share-backed Volume Mounts, unsafe sources, access widening, invalid Service Secret references, and invalid Service Secret environment wiring.

- Keep Service Deploy workflow tests that assert external Ansible extra vars for Share-backed Volume subpaths, Service Secrets, Native Service Environment Secret specs, Service Data Directories, and start order.

- Keep Quadlet rendering golden/focused tests that assert output text for Volume lines, mount unit ordering, Podman Secret lines, environment wiring, Service Network lines, and Service Data Directory discovery.

- Add or update tests around the per-Service convenience view if it is introduced in this milestone. The test should prove it is derived from the fleet-wide result.

- Run the full unit test suite after implementation because this seam is shared by validation, deploy, rendering, observability, and workflows.

## Out of Scope

- Changing rendered Quadlet output is out of scope for the first milestone.

- Changing Service Deploy playbook behavior or Ansible variable names is out of scope unless required to consume the new facts safely.

- Moving Observability generated Service Data Files, Grafana dashboards, Prometheus configuration, or generated endpoints into Service Runtime Intent is out of scope.

- Moving Application Configuration Templates or application-specific config content into Service Runtime Intent is out of scope.

- Modeling secret values, decrypting SOPS inside Service Runtime Intent, or passing plaintext through runtime facts is out of scope.

- Moving Service Network wiring, Container Alias namespace validation, and container start order into Service Runtime Intent is out of scope for the first milestone, though it remains part of the longer-term direction.

- Changing Ingress route generation, DNS record generation, NAS Reconcile, or Operator Workflow Runner behavior is out of scope.

- Introducing a new Service schema shape is out of scope. Inventory YAML remains the source of truth.

## Further Notes

- A completed tracer bullet already introduced Backend and Published Port analysis under `.scratch/service-runtime-intent/issues/01-service-runtime-intent-backend-published-port-analysis.md`.

- The next issue should be sliced as the first post-tracer milestone: move Service volume and secret runtime meaning into Service Runtime Intent while preserving existing external behavior.

- The Deletion Test points toward deepening, not deleting, the existing Module: if Service Runtime Intent disappeared, Backend, Published Port, Share-backed Volume, Service Data Directory, and secret rules would reappear across validation, deploy helpers, Quadlet rendering, and tests.

- `CONTEXT.md` has been updated with resolved decisions for the Service Runtime Intent edge, scope, and diagnostic ownership.
