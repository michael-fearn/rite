Status: needs-triage

# Live NAS Reconcile SOPS env entrypoint

## What to build

Add the live NAS Reconcile command surface for a named NAS Endpoint and export its NAS Reconcile Credential from the endpoint Sibling SOPS File into the process-local environment variable declared by `api_token_env`. Fixture-backed `--reality-json` mode remains credential-free and endpoint-implicit.

## Acceptance criteria

- [ ] `scripts/nas-reconcile-plan --live truenas` requires `inventory/nas/truenas.yaml` and `inventory/nas/truenas.sops.yaml` before attempting network access.
- [ ] The workflow decrypts `api_credentials.reconcile.value` from `inventory/nas/truenas.sops.yaml` and exports it only to the child process environment named by `api_token_env`.
- [ ] Missing endpoint, missing Sibling SOPS File, missing `api_token_env`, and failed SOPS extraction produce clear operator errors without printing the credential value.
- [ ] Existing `--reality-json` plan/apply tests continue to pass without any NAS Endpoint Sibling SOPS File.
- [ ] `just` exposes endpoint-explicit live plan/apply tasks.

## Blocked by

None - can start immediately
