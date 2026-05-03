Status: needs-triage

## Parent

docs/prds/initial-building-blocks.md

## What to build

The yaml-as-source-of-truth machinery: schemas to enforce shape per file, cross-file validator to catch errors that span files, custom ansible inventory plugin to load the per-entity yaml model into ansible's flat host model. First real host yaml (wintermute) registered to demonstrate the path end-to-end.

## Acceptance criteria

- [ ] JSON Schemas exist for: host, vm, service, template, global vars
- [ ] `check-jsonschema` wired into pre-commit, validates each inventory file against its schema
- [ ] Cross-file validator (Python, pure-function) checks: service-to-VM refs, port collisions, hostname uniqueness, VM-to-host refs, VM-to-template refs, NFS export name refs
- [ ] Cross-file validator wired into pre-commit
- [ ] Decryption health check: every `.sops.yaml` in the repo is decryptable with the current age recipients; wired into pre-commit
- [ ] Custom ansible inventory plugin (Python) reads `inventory/{hosts,vms,services}/`, decrypts sibling `.sops.yaml` to tmpfs, builds groups (`proxmox_hosts`, `vms`, `vms_on_<host>`), shapes namespaced hostvars
- [ ] Inventory plugin has unit tests with fixture trees: yaml loading variants, SOPS decryption (test age key), group construction, hostvar shaping, missing-file resilience
- [ ] Cross-file validator has unit tests with curated valid + invalid trees, one test per rule plus combination cases
- [ ] Schema fixtures: directory of valid examples (must pass) and invalid examples (must fail with expected error path)
- [ ] `inventory/hosts/wintermute.yaml` written, declares intended state
- [ ] `ansible-inventory --graph` shows wintermute under `proxmox_hosts`

## Blocked by

None - can start immediately