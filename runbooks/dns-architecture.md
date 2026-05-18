# Pi-hole + Unbound DNS architecture

`dns-primary` and `dns-secondary` are functionally identical LAN resolver
Services. They run on Infrastructure VLAN DNS VMs and are declared by:

- `inventory/vms/dns-primary-vm.yaml`
- `inventory/services/dns-primary.yaml`
- `inventory/services/dns-primary.sops.yaml`
- `inventory/vms/dns-secondary-vm.yaml`
- `inventory/services/dns-secondary.yaml`
- `inventory/services/dns-secondary.sops.yaml`

Each VM is provisioned through the standard VM lifecycle path:

```bash
scripts/vm-up dns-primary-vm
scripts/vm-up dns-secondary-vm
```

Each resolver Service is deployed through the standard Service deploy path:

```bash
scripts/service-deploy dns-primary
scripts/service-deploy dns-secondary
```

Those deploys render per-Service shared network and container artifacts:

- `fortress-network-dns-primary.network`
- `fortress-dns-primary-pihole.container`
- `fortress-dns-primary-unbound.container`
- `fortress-network-dns-secondary.network`
- `fortress-dns-secondary-pihole.container`
- `fortress-dns-secondary-unbound.container`

The corresponding systemd services are:

- `fortress-dns-primary-pihole.service`
- `fortress-dns-primary-unbound.service`
- `fortress-dns-secondary-pihole.service`
- `fortress-dns-secondary-unbound.service`

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
deploying them as one Service unit group. Each DNS Service enables Ingress for
its Pi-hole web UI at `dns-primary.fearn.cloud` or
`dns-secondary.fearn.cloud`; DNS resolver traffic still reaches the DNS VM
directly through firewall rule `DNS-001-ALLOW-INTERNAL-RESOLUTION`, not through
Caddy.

`FTLCONF_dns_listeningMode: all` is required for Pi-hole v6 in this container
topology so queries from routed LAN clients are accepted instead of being
treated as non-local Docker-network traffic.

## Pi-hole web/API password

The Pi-hole admin web/API password is a Service Secret in each Service Sibling
SOPS File: `inventory/services/dns-primary.sops.yaml` and
`inventory/services/dns-secondary.sops.yaml`. The structured entry is stored at
`secrets.web_api_password.value` with `created` and `version` metadata beside
it.

Each DNS Service declaration maps that Fortress purpose name to Pi-hole's
native `WEBPASSWORD_FILE` environment variable. `service-deploy` installs only
the nested `value` bytes as the Podman secret. Pi-hole's v6 container expects
`WEBPASSWORD_FILE` to contain the secret name and then reads
`/run/secrets/$WEBPASSWORD_FILE`, so each DNS Service declares
`env_value: secret_name`. The rendered Quadlet contains the Podman secret name,
not the password.

## Addressing and ports

`dns-primary-vm` is the primary Infrastructure VLAN resolver:

- Address: `10.40.0.11/24`
- Gateway: `10.40.0.1`
- Host: `straylight`
- VLAN: `VLAN 40`

`dns-secondary-vm` is the secondary Infrastructure VLAN resolver:

- Address: `10.40.0.18/24`
- Gateway: `10.40.0.1`
- Host: `molly`
- VLAN: `VLAN 40`

Pi-hole must listen on each DNS VM's resolver address for TCP and UDP port 53.
The Service Backend port is the Pi-hole web UI published port, `8080`, so
Caddy routes `dns-primary.fearn.cloud` and `dns-secondary.fearn.cloud` to the
matching Pi-hole admin UI while resolver traffic remains direct TCP/UDP 53
access to the DNS VM.

Because both DNS Services are also Pi-hole-backed Ingress DNS Targets, Service
Deploy enables Pi-hole v6 `/etc/dnsmasq.d` compatibility with
`FTLCONF_misc_etc_dnsmasq_d=true`. Ingress Regeneration owns the generated DNS
record files at
`/srv/services/dns-primary/pihole/etc-dnsmasq.d/99-fortress-ingress.conf` and
`/srv/services/dns-secondary/pihole/etc-dnsmasq.d/99-fortress-ingress.conf`,
which are mounted into the Pi-hole containers at
`/etc/dnsmasq.d/99-fortress-ingress.conf`. Those files are the fortress-owned
Ingress DNS Record Set on each peer: they are authoritatively replaced from
current Inventory and do not mutate Pi-hole manual records. Ingress
Regeneration does not mutate Pi-hole manual records.

## Ingress DNS Records and Targets

Ingress DNS Records are generated local IPv4 A records for declared Ingress
hostnames. Each generated record points to the Ingress VM, not the Backend VM,
Host management address, DNS VM, or Service VM that ultimately receives the
proxied request. The dnsmasq shape is:

```text
address=/<hostname>/<ingress-vm-ip>
```

An Ingress DNS Target is a DNS Service that opts into receiving those generated
records through its Service capability declaration:

```yaml
# capabilities.ingress_records
capabilities:
  ingress_records:
    provider: pihole_dnsmasq
    path: /srv/services/<dns-service>/pihole/etc-dnsmasq.d/99-fortress-ingress.conf
```

`just ingress-regenerate` renders the fortress-owned generated file for every
declared Ingress DNS Target, installs it at
`/srv/services/<dns-service>/pihole/etc-dnsmasq.d/99-fortress-ingress.conf`,
and restarts the target Pi-hole DNS Service so FTL rereads dnsmasq config
from `/etc/dnsmasq.d`. The file appears inside the Pi-hole
container at `/etc/dnsmasq.d/99-fortress-ingress.conf`. It contains generated
Ingress DNS Records for Ingress-enabled Services and declared Host Ingress
Routes. It is replaced from Inventory on every run, so stale generated records
disappear when the corresponding hostname is removed.

Manual Pi-hole records remain operator-owned. Records created in the Pi-hole UI,
Pi-hole API, or another local dnsmasq file are outside fortress ownership and
must not be placed in 99-fortress-ingress.conf, because Ingress Regeneration may
replace that file at any time.

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
- `/srv/services/dns-secondary/pihole/etc-pihole` stores Pi-hole configuration
  and persistent application state.
- `/srv/services/dns-secondary/unbound` stores Unbound configuration mounted at
  `/opt/unbound/etc/unbound`.

Service Data Directory cleanup and migration are explicit operator actions.
Redeploying a DNS Service must not be treated as permission to prune these
paths.

## Operator validation

After provisioning each VM and deploying each Service, validate each resolver
from a LAN client whose firewall policy is allowed by
`DNS-001-ALLOW-INTERNAL-RESOLUTION`.

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
dig @10.40.0.18 example.com A
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
scripts/vm-shell dns-secondary-vm -- systemctl --no-pager status fortress-dns-secondary-pihole.service
scripts/vm-shell dns-secondary-vm -- systemctl --no-pager status fortress-dns-secondary-unbound.service
```

Confirm both DNS protocols are listening on the declared resolver address:

```bash
scripts/vm-shell dns-primary-vm -- ss -lntup 'sport = :53'
scripts/vm-shell dns-secondary-vm -- ss -lntup 'sport = :53'
```

Expected result: listeners exist for both TCP and UDP port 53 on `10.40.0.11`
and `10.40.0.18`.

## Failure checks

If clients cannot resolve through the VM, check in this order:

1. `scripts/vm-up <dns-vm>` completed and the VM has its declared resolver
   address.
2. `scripts/service-deploy <dns-service>` completed and both systemd units are
   active.
3. Pi-hole is configured with `FTLCONF_dns_upstreams: unbound`.
4. Pi-hole is configured with `FTLCONF_dns_listeningMode: all`.
5. Firewall rules include `DNS-001-ALLOW-INTERNAL-RESOLUTION` for the client
   VLAN and `DNS-003-ALLOW-DNS-UPSTREAM` for resolver egress.
6. The test client is not on Guest, because Guest must not use internal DNS.
