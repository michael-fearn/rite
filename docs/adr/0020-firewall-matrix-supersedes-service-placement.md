# Firewall matrix supersedes service placement

The Homelab Firewall Matrix is now the implementation-facing source of truth for VLAN layout, VM placement, service grouping, and NAS mount layout. Earlier documents and ADRs remain authoritative for architectural intent such as separate Ingress and DNS VMs, VM-level Service boundaries, and derived NAS Shares, but any older Host/IP placement facts are superseded by the matrix and must be updated in Inventory as implementation catches up.

This deliberately favors a security/topology-first model over the earlier organic service layout: firewall rules, static IPs, NFS client access, DNS records, and ingress paths should all be reviewable from the same placement matrix before the router/firewall is configured.
