# Pi-hole + Unbound DNS architecture

`dns-primary` is the primary LAN resolver Service. It runs on `dns-primary-vm`
at `10.40.0.11` in `VLAN 40` and is declared by:

- `inventory/vms/dns-primary-vm.yaml`
- `inventory/services/dns-primary.yaml`
- `inventory/services/dns-primary.sops.yaml`

The VM is provisioned through the standard VM lifecycle path:

```bash
scripts/vm-up dns-primary-vm
```

The resolver Service is deployed through the standard Service deploy path:

```bash
scripts/service-deploy dns-primary
```

That deploy renders the shared network and container artifacts:

- `fortress-group-dns-primary.network`
- `fortress-dns-primary-pihole.container`
- `fortress-dns-primary-unbound.container`

The corresponding systemd services are:

- `fortress-dns-primary-pihole.service`
- `fortress-dns-primary-unbound.service`

## Container split

The chosen architecture is a two-container Quadlet Service:

- `pihole` binds the resolver address and exposes TCP and UDP port 53 to LAN
  clients.
- `unbound` runs as the recursive upstream resolver on the shared Quadlet
  network.

Pi-hole depends on Unbound and forwards recursive lookups to the container alias
declared in service inventory:

```yaml
FTLCONF_dns_upstreams: unbound
FTLCONF_dns_listeningMode: all
```

This keeps LAN-facing filtering and recursive resolution separate while still
deploying them as one Service unit group. The Service enables Ingress for the
Pi-hole web UI at `dns-primary.fearn.cloud`; DNS resolver traffic still reaches
the VM directly through firewall rule `DNS-001-ALLOW-INTERNAL-RESOLUTION`, not
through Caddy.

`FTLCONF_dns_listeningMode: all` is required for Pi-hole v6 in this container
topology so queries from routed LAN clients are accepted instead of being
treated as non-local Docker-network traffic.

## Pi-hole web/API password

The Pi-hole admin web/API password is a Service Secret in the Service Sibling
SOPS File at `inventory/services/dns-primary.sops.yaml`. The structured entry is
stored at `secrets.web_api_password.value` with `created` and `version` metadata
beside it.

The `dns-primary` Service declaration maps that Fortress purpose name to
Pi-hole's native `WEBPASSWORD_FILE` environment variable. `service-deploy`
installs only the nested `value` bytes as the Podman secret. Pi-hole's v6
container expects `WEBPASSWORD_FILE` to contain the secret name and then reads
`/run/secrets/$WEBPASSWORD_FILE`, so `dns-primary` declares
`env_value: secret_name`. The rendered Quadlet contains the Podman secret name,
not the password.

## Addressing and ports

`dns-primary-vm` is the Infrastructure VLAN resolver:

- Address: `10.40.0.11/24`
- Gateway: `10.40.0.1`
- Host: `straylight`
- VLAN: `VLAN 40`

Pi-hole must listen on `10.40.0.11` for TCP and UDP port 53. The Service Backend
port is the Pi-hole web UI published port, `8080`, so Caddy routes
`dns-primary.fearn.cloud` to the Pi-hole admin UI while resolver traffic remains
direct TCP/UDP 53 access to the DNS VM.

Because `dns-primary` is also the Pi-hole-backed Ingress DNS Target, Service
Deploy enables Pi-hole v6 `/etc/dnsmasq.d` compatibility with
`FTLCONF_misc_etc_dnsmasq_d=true`. Ingress Regeneration owns the generated DNS
record file at `/etc/dnsmasq.d/99-fortress-ingress.conf`. That file is the
fortress-owned Ingress DNS Record Set: it is authoritatively replaced from
current Inventory and does not mutate Pi-hole manual records.

The firewall model comes from `docs/firewall-matrix.md`:

- `DNS-001-ALLOW-INTERNAL-RESOLUTION`: Trusted, Known, IoT, Apps,
  Infrastructure, and DMZ clients may query the DNS VMs on TCP/UDP 53.
- `DNS-003-ALLOW-DNS-UPSTREAM`: DNS VMs may reach their chosen upstream path.
- Guest must not use internal DNS and must not resolve internal `*.fearn.cloud`
  records.

## Persistent data

The Quadlet renderer maps Service-owned volumes under the standard Service Data
Directory layout:

- `/srv/services/dns-primary/pihole/etc-pihole` stores Pi-hole configuration and
  persistent application state.
- `/srv/services/dns-primary/unbound` stores Unbound configuration mounted at
  `/opt/unbound/etc/unbound`.

Service Data Directory cleanup and migration are explicit operator actions.
Redeploying `dns-primary` must not be treated as permission to prune these
paths.

## Operator validation

After provisioning the VM and deploying the Service, validate the resolver from
a LAN client whose firewall policy is allowed by `DNS-001-ALLOW-INTERNAL-RESOLUTION`.

The first-class live acceptance workflow assumes the durable primary DNS VM
already exists, deploys the Service, checks the resolver units and port binding
on the VM, then performs an external DNS lookup from the operator workstation:

```bash
just acceptance-dns-primary
```

If the VM lifecycle proof itself needs to be rerun, opt into that phase
explicitly:

```bash
just acceptance-dns-primary provision=true auto_confirm=true
```

Confirm external recursive resolution:

```bash
dig @10.40.0.11 example.com A
```

Confirm the current-stage internal DNS path with an expected internal name:

```bash
just acceptance-dns-primary internal=internal-ingress.fearn.cloud
```

At this stage, wildcard `*.fearn.cloud` record generation belongs to the
ingress regeneration slice. If the internal record has not been generated yet,
record that as the expected blocker instead of changing this DNS Service issue
to include ingress record generation.

From an admin workstation, confirm the VM is reachable and the deployed units
are active:

```bash
scripts/vm-shell dns-primary-vm -- systemctl --no-pager status fortress-dns-primary-pihole.service
scripts/vm-shell dns-primary-vm -- systemctl --no-pager status fortress-dns-primary-unbound.service
```

Confirm both DNS protocols are listening on the declared resolver address:

```bash
scripts/vm-shell dns-primary-vm -- ss -lntup 'sport = :53'
```

Expected result: listeners exist for both TCP and UDP port 53 on `10.40.0.11`.

## Failure checks

If clients cannot resolve through the VM, check in this order:

1. `scripts/vm-up dns-primary-vm` completed and the VM has `10.40.0.11`.
2. `scripts/service-deploy dns-primary` completed and both systemd units are
   active.
3. Pi-hole is configured with `FTLCONF_dns_upstreams: unbound`.
4. Pi-hole is configured with `FTLCONF_dns_listeningMode: all`.
5. Firewall rules include `DNS-001-ALLOW-INTERNAL-RESOLUTION` for the client
   VLAN and `DNS-003-ALLOW-DNS-UPSTREAM` for resolver egress.
6. The test client is not on Guest, because Guest must not use internal DNS.
