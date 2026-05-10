# New Service

Use this runbook when adding a Service declared in Inventory and deployed onto an existing VM.

## Declare the Service

Create `inventory/services/<service>.yaml`. The Service name is the filename stem, should match the top-level `name`, and is the value passed to the deployment command.

Required fields are defined by `inventory/services/_schema.json`; at minimum the declaration needs `name`, one `backend`, and a `deploy` block. Issue 07 supports the Quadlet substrate as rootful system units.

The naming planes are separate:

- `name` is the Service identity in Inventory and the prefix for fortress-owned Quadlet artifacts.
- `backend.vm` is the Backend VM where containers run.
- `backend.port` is the VM-local Backend TCP port used by Ingress.
- `hostname` is the public Ingress hostname. If it is absent, future Ingress regeneration may derive one from the Service name; keep it explicit when the name matters.

Ingress defaults are intentionally small in issue 07. `ingress.enabled: true` means Ingress should route the Service hostname to `backend.vm:backend.port`; `ingress.exposure`, `ingress.tls`, and `ingress.auth` are optional policy fields for later Ingress work. A Service with Ingress enabled must mark exactly the Published Port that backs the Ingress path with `ingress: true`.

Published Ports live under each Quadlet container. A Published Port defaults to TCP and uses the container port as the host port when `host` is absent. Set `bind: 127.0.0.1` for ports intended only for Ingress or VM-local callers.

Use a Service Group when multiple Services on the same Backend VM intentionally share one VM-local Podman network. Within a Service, containers always share the Service network. Each container name becomes its Container Alias on that network; use that alias for same-network communication rather than the fortress runtime container name.

## Volumes

Service-owned volume entries use `service_path` and mount a path under the Service Data Directory, `/srv/services/<service>/`. Fortress creates declared Service Data Directory paths during `service-deploy`; Service Data Directory cleanup/migration is explicit, and service-deploy never prunes /srv/services/<service>/.

Share-backed Volume entries use `mount`, `source`, and `container`. The `mount` value references an existing Backend VM Mount by name. Service yaml does not declare NAS Endpoint, Dataset, Share, or protocol details directly; those live on the VM and Dataset declarations that NAS Reconcile and VM Configure own.

Use `source: /` to mount the root of the existing Backend VM Mount, or a relative subpath such as `photos`. `service-deploy may validate Share-backed Volume subpaths`, but it does not run NAS Reconcile, does not create NAS Shares, and does not create VM Mount units.

## Secrets And Fragments

A Service Secret is declared on a container with `secret` and `env`. The value comes from `inventory/services/<service>.sops.yaml`; `service-deploy` installs it as a Podman secret and sets the declared `_FILE` environment variable to `/run/secrets/<podman-secret>`.

Quadlet Fragment files live under `inventory/services/<service>.quadlet.d/`. Use `network.network` for the generated network artifact or `<container>.container` for a generated container artifact. Fragments are for native Quadlet options fortress does not model directly; validation refuses unknown fragment files and fortress-owned invariants.

If the containers need a numeric data owner, declare `service_data_owner.uid` and `service_data_owner.gid`. The Service Data Owner applies only to Service-owned volume paths under `/srv/services/<service>/`, not Share-backed Volumes.

## Deploy

Run:

```sh
just service-deploy <service>
```

The command validates Inventory, renders Quadlet artifacts, validates Share-backed Volume subpaths when they are not `source: /`, installs Service Secrets, creates Service-owned volume directories, reloads systemd, and starts containers in Container Dependency order.

VM placement is the Service security boundary. Put Services that should not share a rootful Podman/systemd trust boundary on different VMs. Issue 07 Quadlets are rootful system units installed under `/etc/containers/systemd`.

Service deletion/destruction is not automated in issue 07. Removing a Service yaml does not remove containers, Quadlet units, Podman secrets, Service Data Directories, Published Ports, DNS, or Ingress routing. Plan deletion as an explicit operator change.

## Live Acceptance Demo

The live acceptance shape is captured in `inventory/acceptance/service-demo.yaml`. Before running it live, copy that file to `inventory/services/fortress-service-demo.yaml`, create an encrypted `inventory/services/fortress-service-demo.sops.yaml` from `inventory/acceptance/service-demo.sops.yaml.example`, and copy `inventory/acceptance/services/fortress-service-demo.quadlet.d/` to `inventory/services/fortress-service-demo.quadlet.d/`.

It is a contrived but real-world-shaped multi-container Service on an existing Backend VM that already has a VM Mount named `nfs-demo`:

```yaml
name: fortress-service-demo
hostname: fortress-service-demo.fearn.cloud
service_group: service-demo
service_data_owner:
  uid: 1000
  gid: 1000
backend:
  vm: wintermute-demo
  port: 8080
ingress:
  enabled: true
  exposure: lan_only
  tls: letsencrypt_dns
  auth:
    type: none
deploy:
  type: quadlet
  containers:
    - name: web
      image: docker.io/library/nginx:1.27
      depends_on: [postgres, redis]
      published_ports:
        - bind: 127.0.0.1
          host: 8080
          container: 80
          ingress: true
        - bind: 127.0.0.1
          host: 18080
          container: 8080
      volumes:
        - service_path: web
          container: /usr/share/nginx/html
          access: read_write
        - mount: nfs-demo
          source: /
          container: /mnt/shared
          access: read_write
      secrets:
        - secret: secrets.demo_password
          env: DEMO_PASSWORD_FILE
    - name: postgres
      image: docker.io/library/postgres:16
      secrets:
        - secret: secrets.demo_password
          env: POSTGRES_PASSWORD_FILE
      volumes:
        - service_path: postgres
          container: /var/lib/postgresql/data
          access: read_write
    - name: redis
      image: docker.io/library/redis:7
```

Add a validated Quadlet Fragment at `inventory/services/fortress-service-demo.quadlet.d/web.container`:

```ini
[Service]
RestartSec=5
```

Deploy:

```sh
just service-deploy fortress-service-demo
```

Operator-facing verification commands and expected signals:

```sh
just vm-shell wintermute-demo
systemctl is-active fortress-fortress-service-demo-postgres.service
systemctl is-active fortress-fortress-service-demo-redis.service
systemctl is-active fortress-fortress-service-demo-web.service
podman exec fortress-fortress-service-demo-web getent hosts postgres
podman exec fortress-fortress-service-demo-web getent hosts redis
podman exec fortress-fortress-service-demo-web test -f "$DEMO_PASSWORD_FILE"
curl -fsS http://127.0.0.1:8080/
curl -fsS https://fortress-service-demo.fearn.cloud/
```

Success signals are `active` for all three systemd units, `getent hosts` returning addresses for the `postgres` and `redis` Container Aliases, the secret file test exiting zero, the VM-local curl returning HTTP content, and the Ingress curl succeeding when Ingress is enabled.

Failure signals are `Failed to start fortress-fortress-service-demo-*.service`, `journalctl -u <unit>` showing container startup errors, missing Share-backed Volume paths during deploy, `getent hosts` failing for Container Aliases, or the Ingress curl failing while the VM-local curl succeeds.
