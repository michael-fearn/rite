# Remote Operator Access

Use this runbook to bring up the immediate Hosted Tailnet path for running fortress Operator workflows away from the local network.

## Tailnet Subnet Router

The initial Tailnet Subnet Router is `tailnet-subnet-router-vm`, an ordinary VM on the `molly` Host attached to the Trusted VLAN at `10.20.0.20/24`.

Create a Tailscale auth key for this VM, then store it in the VM's Sibling SOPS File:

```yaml
tailnet:
  auth_key:
    type: tailscale_auth_key
    created: 2026-05-12T00:00:00Z
    value: tskey-auth-...
```

Bring the VM up through the ordinary VM lifecycle:

```sh
just vm-up vm=tailnet-subnet-router-vm
```

After Configure completes, approve the advertised subnet routes in the Tailscale admin console. During early bring-up, this VM advertises all fortress VLANs so the Operator can recover or continue implementation work remotely.

The router VM is routing-only. Do not use it as a remote shell, editor, or credential-holding Operator environment.
