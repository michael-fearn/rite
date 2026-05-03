Status: needs-triage

## Parent

docs/prds/initial-building-blocks.md

## What to build

The escape hatch for services genuinely better as native packages (Caddy is the canonical case). Same service yaml schema, different deploy block. Apt repo handling, config-file templating with reload-vs-restart logic.

## Acceptance criteria

- [ ] Service yaml schema with `deploy.type: native`: package name, optional apt-repo reference, service name, list of config-file templates each flagged reload-vs-restart
- [ ] Native renderer role installs the package (with optional apt repo configuration), templates configs, manages the systemd unit
- [ ] Reload-vs-restart logic respected: reload-flagged template change triggers `systemctl reload`; restart-flagged triggers `systemctl restart`
- [ ] Multi-config-file services supported
- [ ] Golden-file tests cover: apt-repo handling, reload vs restart, multi-config-file
- [ ] Demo: a native test service deployed via `just service-deploy`

## Blocked by

.scratch/initial-building-blocks/issues/07-quadlet-renderer-first-multi-container-service.md