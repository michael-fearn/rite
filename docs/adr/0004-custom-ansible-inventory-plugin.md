# Custom Ansible inventory plugin, not constructed or dynamic

A small (~50 LOC) custom inventory plugin reads the per-entity YAML files directly and shapes ansible's host model; it does not query Proxmox. Constructed inventories can't decrypt sibling SOPS files at load time or shape namespaced hostvars; dynamic inventories couple ansible to runtime state and break reasoning offline. The YAML is authoritative — `tofu apply` makes reality match the YAML, and the inventory plugin is the bridge between the YAML model and ansible's flat host concept.
