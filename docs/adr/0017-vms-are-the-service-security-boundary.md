# VMs are the Service security boundary

Fortress treats the VM as the primary security boundary for Services, so the initial Quadlet renderer deploys rootful system Quadlets managed by the VM's systemd. Services that should not share a trust boundary should be placed on separate VMs rather than relying on rootless Podman as the first isolation mechanism.

Rootful system Quadlets keep Service deployment aligned with VM-level Ansible configuration, system `.mount` ordering, Podman secrets, Service Data Directories, and simple `systemctl` operations. Rootless Quadlets remain a possible future Service isolation mode, but they introduce different unit locations, user systemd management, per-user Podman networks and secrets, ownership migration, and more awkward Mount ordering.
