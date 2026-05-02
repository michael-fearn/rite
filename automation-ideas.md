I'm working on a homelab infratstructure automation project and am setting requirements for the automation building blocks. I have n number of named hosts all running proxmox 9 hypervisor. For the starting state all hosts are reachable over shh with the root user using the same key.

1. I want ansible to be able to connect to each host and set a host specific private key and save each key to repo with sops + age. These sops files will be strutured in such a way that make future key rotation easy.

2. I want each host to be represented as template that contains all of the configurable hosts information.

3. I want to be able to fill out a template that ansible can use to produce cloudinit vm template that can be used for provisioning through opentofu.

4. I want to be provision vms through opentofu using templates and have the newly provisioned vms have a default admin user with a vm specific ssh key that is also stored via sops + age.

5. I want ansible to configure the vm and the service stack.

Preserve the split: OpenTofu provisions VM shells; Ansible configures guests and services.
Keep secrets in SOPS; do not commit plaintext secret material. Only the SOPS keys live outside the repo.
Manual user interventions are documented in runbooks
