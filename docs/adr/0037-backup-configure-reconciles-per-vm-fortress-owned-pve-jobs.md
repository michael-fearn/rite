# Backup configure reconciles per-VM fortress-owned PVE jobs

Backup Configure is a host-scoped operator workflow that reconciles PVE-side Backup Jobs for Backup Targets, with fleet mode implemented as iteration over Hosts. Each Backup Target gets its own deterministic fortress-owned Backup Job named from the Backup Target and Backup Policy; this avoids reshaping grouped jobs as policy adoption changes over time. Backup Configure may create and update fortress-owned jobs, but it prunes only obsolete fortress-owned Backup Jobs, leaves manual PVE jobs alone, and gates pruning behind operator confirmation.

