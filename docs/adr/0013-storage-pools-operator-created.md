# Ansible registers storage pools but does not create them

`host-configure.yml` registers existing storage pools in `storage.cfg` but never runs `zpool create`, `vgcreate`, or any other pool-creation command. Pool creation is destructive — a wrong device path is total data loss — and the cost of typing one command at the Proxmox console by hand is negligible against that risk. Configure fails clearly if a declared pool is missing on the Host, instead of creating it. Pool creation lives in `runbooks/new-host.md`, deliberately operator-controlled.
