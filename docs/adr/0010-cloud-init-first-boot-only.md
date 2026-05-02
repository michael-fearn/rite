# Cloud-init handles first boot only

Cloud-init configures the minimum needed for ansible to take over: admin user, SSH public key, hostname, network. Everything else — packages, services, NFS Mounts, GPU userland — is ansible. Cloud-init runs once and is awkward to re-run; ansible is idempotent by design with a much richer module surface. The seam is "first boot": before that point the VM is a tofu/cloud-init problem; after that point it is purely an ansible problem.
