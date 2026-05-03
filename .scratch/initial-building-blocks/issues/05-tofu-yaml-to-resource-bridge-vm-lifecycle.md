Status: needs-triage

## Parent

docs/prds/initial-building-blocks.md

## What to build

OpenTofu reads the same VM yaml files Ansible uses; provider aliases come from the host yaml directory; PVE tokens decrypted only into ephemeral env vars by a wrapper. The full VM lifecycle command sequences prepare → tofu apply → configure into one operator command. Destroy refuses while services still reference the VM.

## Acceptance criteria

- [ ] HCL module iterates VM yaml directory via `for_each`
- [ ] Multi-aliased provider map built from host yaml directory; one state file for the whole fleet
- [ ] Tofu wrapper script decrypts PVE API tokens into env vars, invokes tofu, marks vars `sensitive = true`
- [ ] Tokens never appear in plan output or tfstate
- [ ] Cloud-init userdata assembled from VM yaml + the plaintext public-key field
- [ ] `prepare` playbook: generates VM SSH keypair, writes private encrypted, writes public into VM yaml in plaintext
- [ ] `prepare` refuses if VM's encrypted file already exists
- [ ] `configure` playbook: waits for cloud-init completion, finalizes admin user
- [ ] `just vm-up vm=<name>` runs prepare → tofu apply (with explicit plan approval) → configure
- [ ] `just vm-destroy vm=<name>` runs `tofu destroy` and removes the encrypted secrets file
- [ ] `vm-destroy` refuses if any service yaml references the VM
- [ ] PVE token rotation uses versioned names so rotations are atomic on the PVE side
- [ ] `runbooks/new-vm.md` written
- [ ] Demo: provision a test VM end-to-end on wintermute, destroy cleanly

## Blocked by

.scratch/initial-building-blocks/issues/04-vm-template-builder.md