# Host ingress routes are not Services

Proxmox Host web UI ingress is modeled as Host Ingress Routes declared on Host inventory, not as synthetic Services. Host management routes share Ingress Regeneration, DNS generation, TLS policy, and hostname collision checks with Service ingress, but their targets are physical Host management addresses rather than VM Backends; keeping this boundary avoids diluting the Service model, where a Service is something deployed inside a VM.
