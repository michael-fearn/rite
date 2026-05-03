# Initial Setup

This runbook rebuilds a fortress operator workstation from scratch. The goal is
to recover the repo, restore the age recipients, and prove that a Sibling SOPS
File can be decrypted before any Host or VM workflow runs.

## Fresh Workstation Ceremony

1. Install Debian 13 or open the devcontainer.
2. dependency install: run `sudo bash scripts/setup/install-toolchain.sh` on a
   local Debian 13 workstation, or rebuild the devcontainer so it runs the same
   script.
3. repo clone: clone this repository and enter the checkout.
4. age key import: place the operator age private key at
   `~/.config/sops/age/keys.txt` with `0600` permissions.
5. offline backup: retrieve the backup age key from physical offline storage
   only when the workstation key is lost or being rotated.
6. Confirm `age/recipients.txt` contains exactly two public Recipients: the
   operator workstation Recipient and the offline backup Recipient.
7. Update `.sops.yaml` so its `age` value is the comma-separated public
   Recipients from `age/recipients.txt`.
8. Run `pre-commit install`.
9. Run `pre-commit run --all-files`.

## Decrypt Test

Use a throwaway Sibling SOPS File to prove the current age key can decrypt repo
secrets:

```bash
cat > /tmp/fortress-decrypt-test.sops.yaml <<'YAML'
ssh_keys:
  bootstrap:
    private_key: test-private-key
YAML
sops --encrypt --in-place /tmp/fortress-decrypt-test.sops.yaml
scripts/decrypt-keys /tmp/fortress-decrypt-test.sops.yaml -- test -f /dev/shm/fortress/fortress-decrypt-test.key
```

The wrapper removes `/dev/shm/fortress` on exit. If the file remains, stop and
debug the cleanup trap before using real SSH private keys.

## DR Demo

The acceptance DR demo is complete when a clean test workstation can perform
the full ceremony above, run the decrypt-test successfully, and then delete the
temporary test SOPS file without leaving plaintext SSH material on disk.
