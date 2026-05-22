# Backup readiness gates production readiness for backup targets

Production VMs that set `backup.enabled: true` become Backup Targets and must pass Backup Readiness before they are treated as production-ready. Backup Readiness confirms the selected Backup Policy, required datastores, PBS encryption Recovery Secret availability, and at least one successful Backup Run; the exact checks may expand as PBS workflows mature. Production VMs with `backup.enabled: false` are Unprotected VMs and must carry an explicit operator-facing reason, while generated or disposable VMs are exempt from that requirement.

