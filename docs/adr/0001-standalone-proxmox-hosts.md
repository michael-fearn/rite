# Standalone Proxmox hosts, no cluster

The fleet is four heterogeneous Proxmox 9 machines run by a single operator. Each Host is its own island — no Proxmox cluster, no shared storage, no live migration, no quorum. Heterogeneous CPU generations and iGPU passthrough modes don't benefit from cluster features at this scale, and the operational tax of cluster maintenance (corosync, fencing, quorum management) is unjustified for a one-operator homelab. The OpenTofu module aliases one provider per Host writing to a single state file; loss of a Host is downtime, not failover.
