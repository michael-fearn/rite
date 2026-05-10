# Homelab Firewall Matrix

This matrix is the implementation-facing source of truth for VLAN layout, VM placement, NAS mount layout, and intended communication paths. The router/firewall may be configured manually, but fortress Inventory and generated service configuration should converge toward this model.

The posture is default-deny between VLANs with explicit allow rules. `VLAN 1 Default` is intentionally ignored for homelab service placement and trust modeling.

## VLANs and Addressing

| VLAN | Name | CIDR | Gateway | Static convention |
| --- | --- | --- | --- | --- |
| 10 | Management | `10.10.0.0/24` | `10.10.0.1` | preserve existing Proxmox Host IPs |
| 20 | Trusted | `10.20.0.0/24` | `10.20.0.1` | admin workstations flagged by router policy |
| 25 | Known | `10.25.0.0/24` | `10.25.0.1` | ordinary non-admin DHCP clients |
| 30 | IoT | `10.30.0.0/24` | `10.30.0.1` | appliance-style DHCP clients |
| 40 | Infrastructure | `10.40.0.0/24` | `10.40.0.1` | static services start at `.11` |
| 50 | Apps | `10.50.0.0/24` | `10.50.0.1` | static services start at `.11` |
| 60 | DMZ | `10.60.0.0/24` | `10.60.0.1` | future public-service stack |
| 70 | Guest | `10.70.0.0/24` | `10.70.0.1` | internet-only DHCP clients |

## Address Inventory

Existing Proxmox Host and NAS IPs are authoritative inventory facts and must be preserved unless a later task explicitly readdresses them.

| Address | Name | VLAN | Role |
| --- | --- | --- | --- |
| `10.10.0.1` | `UDM-SE` | Management | router/firewall |
| `10.10.0.11` | `wintermute` | Management | Proxmox Host |
| `10.10.0.12` | `straylight` | Management | Proxmox Host |
| `10.10.0.13` | `neuromancer` | Management | Proxmox Host |
| `10.10.0.14` | `molly` | Management | Proxmox Host |
| `10.10.0.15` | `NAS` | Management | TrueNAS management address |
| `10.40.0.15` | `NAS` | Infrastructure | TrueNAS share address |

## Infrastructure VMs

| VM | Address | Host | Services | Storage |
| --- | --- | --- | --- | --- |
| `dns-primary-vm` | `10.40.0.11` | `straylight` | Pi-hole, Unbound | VM-local |
| `forgejo-vm` | `10.40.0.12` | `straylight` | Forgejo | VM-local |
| `pbs-vm` | `10.40.0.13` | `straylight` | Proxmox Backup Server | NFS Datastore from NAS |
| `headscale-vm` | `10.40.0.14` | `straylight` | Headscale | VM-local |
| `internal-ingress-vm` | `10.40.0.16` | `straylight` | Caddy | VM-local |
| `observability-vm` | `10.40.0.17` | `straylight` | Prometheus, Alertmanager, Grafana, Loki, Blackbox Exporter | VM-local unless later expanded |
| `dns-secondary-vm` | `10.40.0.18` | `molly` | Pi-hole, Unbound | VM-local |
| `identity-vm` | `10.40.0.19` | `straylight` | Authentik | VM-local |

Primary and secondary DNS VMs are functionally identical peers. Headscale is local-only; remote devices must be enrolled while local or with a short-lived pre-auth key minted while local. Headscale does not depend on Authentik until a later explicit OIDC integration decision.

Caddy remains the internal Ingress for routing and TLS. Authentik provides optional per-Service Ingress Auth and does not replace Caddy.

Forgejo runners must not run on `forgejo-vm`. Add a separate runner VM when runner workload trust and placement are defined.

## Apps VMs

| VM | Address | Host | Services | Storage |
| --- | --- | --- | --- | --- |
| `vaultwarden-vm` | `10.50.0.11` | `neuromancer` | Vaultwarden | VM-local primary data, PBS-backed |
| `immich-vm` | `10.50.0.12` | `neuromancer` | Immich application containers, Postgres, Redis | NFS `tank/immich` for library storage; database/cache VM-local |
| `media-vm` | `10.50.0.13` | `neuromancer` | Jellyfin, Overseerr, Sonarr, Radarr, Lidarr, Prowlarr, Bazarr | NFS `tank/media` |
| `download-vm` | `10.50.0.14` | `neuromancer` | qBittorrent, SABnzbd, NZBGet, VPN-bound download components | NFS `tank/media` |
| `file-browser-vm` | `10.50.0.15` | `neuromancer` | File Browser | NFS `tank/personal-media` |

`media-vm` and `download-vm` both mount `tank/media` read-write at the VM level. Individual Services narrow visible paths and read/write exposure through Share-backed Volume subpaths. Jellyfin uses read-only library subpaths. Overseerr does not consume the media Dataset unless a later explicit requirement appears.

User-facing HTTP Services on `media-vm` and `download-vm` are exposed through `internal-ingress-vm` for DNS and TLS. Direct backend access is reserved for explicit Trusted-only emergency or administration paths.

`file-browser-vm` is Trusted-only through internal ingress and should use Authentik Ingress Auth. `vaultwarden-vm` is not Authentik-protected by default because Vaultwarden has its own security model and clients may be sensitive to forward-auth behavior.

## DMZ

DMZ is future-only for this internal baseline. DMZ workloads will use a separate ingress and authentication stack, not `internal-ingress-vm` or `identity-vm`.

## Baseline Rules

| ID | Source | Destination | Protocol | Port(s) | Required | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| `BASE-001-ALLOW-CLIENT-INTERNET` | Trusted, Known, IoT, Guest | Internet | TCP/UDP | required outbound | Yes | Normal internet access where policy allows |
| `BASE-002-DENY-GUEST-INTERNAL` | Guest | RFC1918/internal VLANs | Any | Any | Yes | Guest is internet-only |
| `BASE-003-DENY-IOT-INTERNAL` | IoT | RFC1918/internal VLANs | Any | Any | Yes | IoT is denied internal access except explicit narrow rules |
| `BASE-004-DENY-KNOWN-MANAGEMENT` | Known | Management | Any | Any | Yes | Known is non-admin |
| `BASE-005-DENY-DMZ-INTERNAL` | DMZ | Management, Trusted, Known, Apps, Infrastructure | Any | Any | Yes | DMZ uses a separate future public-service stack |

## DNS and Time

| ID | Source | Destination | Protocol | Port(s) | Required | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| `DNS-001-ALLOW-INTERNAL-RESOLUTION` | Trusted, Known, IoT, Apps, Infrastructure, DMZ | `dns-primary-vm`, `dns-secondary-vm` | TCP/UDP | 53 | Yes | Internal DNS resolution and Pi-hole filtering |
| `DNS-002-ALLOW-GUEST-RESOLUTION` | Guest | UDM or approved non-internal resolver | TCP/UDP | 53 | Yes | Guest DNS without internal resolver dependency or internal records |
| `DNS-003-ALLOW-DNS-UPSTREAM` | `dns-primary-vm`, `dns-secondary-vm` | Internet | TCP/UDP | 53, 853 as chosen | Yes | Upstream recursion via Unbound or configured resolver path |
| `DNS-004-BLOCK-DIRECT-INTERNET-DNS` | All non-Guest VLANs | Internet DNS | TCP/UDP | 53 | Optional | Block or redirect direct DNS if UDM supports clean enforcement |
| `NTP-001-ALLOW-TIME-SYNC` | All VLANs | UDM or approved NTP | UDP | 123 | Yes | Stable time for TLS, logs, backups, and auth |

Guest must not use internal DNS and must not resolve internal `*.fearn.cloud` records.

## Administration

| ID | Source | Destination | Protocol | Port(s) | Required | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| `ADMIN-001-ALLOW-TRUSTED-PROXMOX` | Trusted | Proxmox Hosts | TCP | 8006, 22 | Yes | Proxmox UI and SSH administration |
| `ADMIN-002-ALLOW-TRUSTED-UDM` | Trusted | UDM SE | TCP/UDP | admin UI and management ports | Yes | Router/firewall administration |
| `ADMIN-003-ALLOW-TRUSTED-NAS` | Trusted | NAS management address | TCP | 443, 22 | Yes | TrueNAS administration and recovery |
| `ADMIN-004-ALLOW-TRUSTED-INFRA` | Trusted | Infrastructure VMs | TCP | 22, service admin ports | Yes | Direct service administration during bootstrap and incidents |
| `ADMIN-005-DENY-NONADMIN-ADMIN-PORTS` | Known, IoT, Guest | Management, Infrastructure admin ports | Any | Any | Yes | Non-admin networks cannot reach admin surfaces |

Trusted VLAN is the admin workstation network. Known is the ordinary non-admin client network.

## Internal Ingress and Identity

| ID | Source | Destination | Protocol | Port(s) | Required | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| `ING-001-ALLOW-INTERNAL-HTTPS` | Trusted, Known, tailnet-routed clients | `internal-ingress-vm` | TCP | 443 | Yes | Standard user-facing internal app access through DNS and TLS |
| `ING-002-ALLOW-INGRESS-BACKENDS` | `internal-ingress-vm` | Published app backends | TCP | backend app ports | Yes | Caddy reverse proxy to approved internal Services |
| `ING-003-ALLOW-INGRESS-IDENTITY` | `internal-ingress-vm` | `identity-vm` | TCP | Authentik backend ports | Yes | Authentik flows for Services with Ingress Auth |
| `ING-004-ALLOW-TRUSTED-IDENTITY-RECOVERY` | Trusted | `identity-vm` | TCP | Authentik backend/admin ports | Yes | Direct recovery if ingress is down |
| `ING-005-DENY-DIRECT-BACKEND-BYPASS` | Known, IoT, Guest, DMZ | App and Infrastructure backend ports | Any | Any | Yes | Clients should use Ingress rather than direct backend paths |

Ingress Auth is explicit per Service. It is not applied globally.

## Core Infrastructure

| ID | Source | Destination | Protocol | Port(s) | Required | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| `PBS-001-ALLOW-HOST-BACKUPS` | Proxmox Hosts | `pbs-vm` | TCP | 8007 | Yes | Proxmox Hosts send VM backups to PBS |
| `PBS-002-ALLOW-PBS-DATASTORE` | `pbs-vm` | NAS share address | TCP/UDP | NFS ports | Yes | PBS Datastore mounted from NAS |
| `PBS-003-ALLOW-TRUSTED-PBS` | Trusted | `pbs-vm` | TCP | 8007, 22 | Yes | PBS administration and recovery |
| `GIT-001-ALLOW-TRUSTED-FORGEJO` | Trusted | `forgejo-vm` | TCP | 22, 443 | Yes | Git over SSH/HTTPS from admin workstation |
| `GIT-002-ALLOW-FUTURE-RUNNERS` | Forgejo Runner VMs | `forgejo-vm` | TCP | 443, 22 as configured | Future | Runner registration and job execution after runner placement is defined |
| `TAIL-001-ALLOW-LOCAL-HEADSCALE` | Trusted, tailnet-routed clients | `headscale-vm` | TCP | 443 | Yes | Local-only Headscale control-plane access |
| `TAIL-002-ALLOW-HEADSCALE-OUTBOUND` | `headscale-vm` | Internet | TCP | 443 | Yes | Headscale external coordination as required |

No public `Internet -> headscale-vm` rule exists in this baseline.

## Apps and NAS

| ID | Source | Destination | Protocol | Port(s) | Required | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| `APP-001-ALLOW-IMMICH-NAS` | `immich-vm` | NAS share address | TCP/UDP | NFS ports | Yes | Mount `tank/immich` |
| `APP-002-ALLOW-MEDIA-NAS` | `media-vm` | NAS share address | TCP/UDP | NFS ports | Yes | Mount `tank/media` |
| `APP-003-ALLOW-DOWNLOAD-NAS` | `download-vm` | NAS share address | TCP/UDP | NFS ports | Yes | Mount `tank/media` |
| `APP-004-ALLOW-FILE-BROWSER-NAS` | `file-browser-vm` | NAS share address | TCP/UDP | NFS ports | Yes | Mount `tank/personal-media` |
| `APP-005-ALLOW-TRUSTED-VAULTWARDEN-BYPASS` | Trusted | `vaultwarden-vm` | TCP | Vaultwarden backend port | Yes | Emergency direct backend access if internal ingress is down |
| `APP-006-DENY-VAULTWARDEN-BYPASS` | Known, IoT, Guest, DMZ | `vaultwarden-vm` backend | Any | Any | Yes | Deny emergency bypass path to non-admin networks |
| `APP-007-ALLOW-TRUSTED-FILE-BROWSER` | Trusted | `internal-ingress-vm`, `file-browser-vm` | TCP | 443, File Browser backend port | Yes | Trusted-only personal files access and recovery |
| `APP-008-DENY-FILE-BROWSER-BYPASS` | Known, IoT, Guest, DMZ | `file-browser-vm` backend | Any | Any | Yes | Deny personal files backend to non-admin networks |

Treat NFS access as VM-specific, not VLAN-wide.

## Observability

| ID | Source | Destination | Protocol | Port(s) | Required | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| `OBS-001-ALLOW-METRICS-SCRAPE` | `observability-vm` | Proxmox Hosts and Linux VMs | TCP | exporter ports | Yes | Metrics collection |
| `OBS-002-ALLOW-LOG-SHIPPING` | Proxmox Hosts and Linux VMs | `observability-vm` | TCP/UDP | log shipping ports | Yes | Central logs |
| `OBS-003-ALLOW-HEALTH-CHECKS` | `observability-vm` | DNS, PBS, Forgejo, Headscale, Ingress, Identity, Apps | TCP/UDP | service check ports | Yes | Blackbox and health checks |
| `OBS-004-ALLOW-TRUSTED-OBSERVABILITY` | Trusted | `observability-vm` | TCP | 443, Grafana/admin ports | Yes | Dashboard and alert administration |

## DMZ Placeholder

| ID | Source | Destination | Protocol | Port(s) | Required | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| `DMZ-001-FUTURE-PUBLIC-INGRESS` | Internet | Future DMZ ingress | TCP | 80, 443 | Future | Future public service ingress only |
| `DMZ-002-DENY-DMZ-INTERNAL` | DMZ workloads | Infrastructure, Apps, Management | Any | Any | Yes | DMZ is separate from the internal stack |
| `DMZ-003-FUTURE-DMZ-UPSTREAM` | DMZ workloads | Approved upstream service | TCP/UDP | service-specific | Future | Add only for a documented public workload need |

## Implementation Notes

- Create explicit allow rules before broad deny rules where the UDM rule model requires ordering.
- Prefer address groups for VLANs and service groups for VMs.
- Keep Service backend ports out of broad client access rules; clients should usually enter through `internal-ingress-vm`.
- Treat NFS access as VM-specific, not VLAN-wide.
- Any new Service should add DNS, ingress, firewall, backup, and monitoring requirements in the same repo change.
