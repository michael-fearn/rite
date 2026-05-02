# Bootstrap idempotency by refusal, not silent skip

`host-bootstrap.yml` and `vm-prepare.yml` refuse to run if the entity's Sibling SOPS File already exists, instead of silently skipping the keygen step. Bootstrap and Prepare are the only steps that mint irreversible material (the per-entity SSH key); a silent skip would either overwrite a valid key or no-op past a real divergence. Refusal forces an explicit operator choice between bootstrap (first time) and rotation (subsequent times); the rotation playbook is documented by name in the error message.
