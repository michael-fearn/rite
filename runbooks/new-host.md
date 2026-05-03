# New Host

Use this runbook after a fresh Proxmox install is reachable as `root` with the shared bootstrap SSH key.

## Place the Shared Bootstrap Key

Keep the shared bootstrap private key on the operator workstation. The Host only receives the matching public key in `root`'s `authorized_keys`.

On the workstation, print the shared bootstrap public key:

```sh
ssh-keygen -y -f ~/.ssh/fortress-bootstrap
```

In the Proxmox UI, open the Host's shell as `root` and install that public key:

```sh
install -d -m 700 /root/.ssh
cat >> /root/.ssh/authorized_keys <<'EOF'
<paste the shared bootstrap public key here>
EOF
chmod 600 /root/.ssh/authorized_keys
```

From the workstation, verify the private key can authenticate before continuing:

```sh
ssh -i ~/.ssh/fortress-bootstrap root@<management-address> true
```

## Declare the Host

Create `inventory/hosts/<name>.yaml` before running automation. The Host declaration must include `network.management_address`; Bootstrap uses that address while the Host is still carrying the shared bootstrap SSH key.

## Bootstrap SSH

Run:

```sh
just host-bootstrap <name>
```

The command generates a per-Host SSH keypair locally, pushes the public key to the Host using the shared bootstrap SSH key, verifies the new private key can authenticate, removes the shared bootstrap public key from `authorized_keys`, and writes `inventory/hosts/<name>.sops.yaml`.

The Sibling SOPS File contains a structured `ssh_keys.bootstrap` entry with `type`, `created`, `public_key`, and encrypted `private_key` fields. Bootstrap refuses to re-run if that bootstrap key entry already exists; use the Host SSH rotation workflow for later credential replacement.

By default the shared bootstrap private key is read from `~/.ssh/fortress-bootstrap`. Set `FORTRESS_BOOTSTRAP_SSH_KEY=/path/to/key` when using a different local path.

## Continue

After Bootstrap succeeds, commit the new Host Sibling SOPS File and run the Host configure workflow when the Host is ready for convergence.
