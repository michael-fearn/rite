import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


SCHEMA_CASES = [
    ("Host", "inventory/hosts/_schema.json", "tests/fixtures/schema/hosts"),
    ("VM", "inventory/vms/_schema.json", "tests/fixtures/schema/vms"),
    ("Service", "inventory/services/_schema.json", "tests/fixtures/schema/services"),
    ("Dataset", "inventory/datasets/_schema.json", "tests/fixtures/schema/datasets"),
    ("NAS Endpoint", "inventory/nas/_schema.json", "tests/fixtures/schema/nas"),
    ("Template", "inventory/templates/_schema.json", "tests/fixtures/schema/templates"),
    (
        "Template Verification Policy",
        "inventory/template-verification-policy.schema.json",
        "tests/fixtures/schema/template_verification_policy",
    ),
    ("global vars", "inventory/group_vars/all.schema.json", "tests/fixtures/schema/group_vars"),
]


class InventorySchemaTests(unittest.TestCase):
    def run_schema(self, schema_path, yaml_path):
        return subprocess.run(
            ["check-jsonschema", "--schemafile", schema_path, yaml_path],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_valid_schema_fixtures_pass(self):
        for name, schema_path, fixture_root in SCHEMA_CASES:
            for yaml_path in sorted((REPO_ROOT / fixture_root / "valid").glob("*.yaml")):
                with self.subTest(schema=name, fixture=yaml_path.name):
                    result = self.run_schema(schema_path, str(yaml_path.relative_to(REPO_ROOT)))
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_invalid_schema_fixtures_fail_with_expected_paths(self):
        expected_paths = {
            "hosts": "proxmox",
            "vms": "placement",
            "services": "backend",
            "datasets": "owner",
            "nas": "management_address",
            "templates": "source",
            "template_verification_policy": "storage_by_host",
            "group_vars": "nas",
        }

        for _name, schema_path, fixture_root in SCHEMA_CASES:
            fixture_kind = Path(fixture_root).name
            for yaml_path in sorted((REPO_ROOT / fixture_root / "invalid").glob("*.yaml")):
                with self.subTest(fixture=yaml_path.name):
                    result = self.run_schema(schema_path, str(yaml_path.relative_to(REPO_ROOT)))
                    output = result.stdout + result.stderr
                    self.assertNotEqual(result.returncode, 0, output)
                    self.assertIn(expected_paths[fixture_kind], output)

    def test_host_schema_accepts_configurator_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            host_yaml = Path(tmp) / "wintermute.yaml"
            host_yaml.write_text(
                "proxmox:\n"
                "  pve_node_name: wintermute\n"
                "  users:\n"
                "    - name: tofu@pve\n"
                "      roles: [PVEVMAdmin, PVEDatastoreAdmin, PVESDNAdmin]\n"
                "      tokens:\n"
                "        - id: tofu\n"
                "          roles: [PVEVMAdmin, PVEDatastoreAdmin, PVESDNAdmin]\n"
                "hardware:\n"
                "  storage:\n"
                "    - name: local-lvm\n"
                "      kind: lvmthin\n"
                "network:\n"
                "  management_address: 10.10.0.11\n"
                "  bridges:\n"
                "    - name: vmbr0\n"
                "      managed: true\n"
                "      vlan: 10\n"
                "      cidr: 10.10.0.11/24\n"
                "      gateway: 10.10.0.1\n"
                "gpu_passthrough:\n"
                "  enabled: true\n"
                "  vendor: intel\n"
                "  mode: sriov\n"
                "  iommu: intel\n"
                "  sriov_vfs: 7\n"
                "  blacklist_host_driver: false\n"
            )

            result = self.run_schema("inventory/hosts/_schema.json", str(host_yaml))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_host_schema_ignores_gpu_passthrough_details_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            host_yaml = Path(tmp) / "wintermute.yaml"
            host_yaml.write_text(
                "proxmox:\n"
                "  pve_node_name: wintermute\n"
                "gpu_passthrough:\n"
                "  enabled: false\n"
                "  vendor: intel\n"
                "  mode: sriov\n"
                "  iommu: intel\n"
                "  sriov_vfs: 7\n"
            )

            result = self.run_schema("inventory/hosts/_schema.json", str(host_yaml))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_host_schema_accepts_proxmox_web_ui_host_ingress_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            host_yaml = Path(tmp) / "wintermute.yaml"
            host_yaml.write_text(
                "proxmox:\n"
                "  pve_node_name: wintermute\n"
                "network:\n"
                "  management_address: 10.10.0.11\n"
                "ingress:\n"
                "  proxmox_web_ui:\n"
                "    enabled: true\n"
                "    hostname: wintermute.fearn.cloud\n"
            )

            result = self.run_schema("inventory/hosts/_schema.json", str(host_yaml))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_service_schema_accepts_explicit_service_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            service_yaml = Path(tmp) / "immich.yaml"
            service_yaml.write_text(
                "name: immich\n"
                "service_group: media\n"
                "service_network: media\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 2283\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: server\n"
                "      image: ghcr.io/immich-app/immich-server:v1.120.0\n"
            )

            result = self.run_schema("inventory/services/_schema.json", str(service_yaml))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_service_schema_rejects_invalid_service_network_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            service_yaml = Path(tmp) / "immich.yaml"
            service_yaml.write_text(
                "name: immich\n"
                "service_network:\n"
                "  name: media\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 2283\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: server\n"
                "      image: ghcr.io/immich-app/immich-server:v1.120.0\n"
            )

            result = self.run_schema("inventory/services/_schema.json", str(service_yaml))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("service_network", result.stdout + result.stderr)

    def test_template_schema_accepts_builder_defaults_and_supported_customize_ops(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_yaml = Path(tmp) / "debian-13-base.yaml"
            template_yaml.write_text(
                "name: debian-13-base\n"
                "vmid: 9001\n"
                "source:\n"
                "  url: https://example.invalid/debian.qcow2\n"
                "  checksum:\n"
                "    algorithm: sha512\n"
                f"    value: {'a' * 128}\n"
                "customize:\n"
                "  packages: [qemu-guest-agent]\n"
                "  run_commands:\n"
                "    - systemctl enable qemu-guest-agent\n"
                "hardware:\n"
                "  cores: 2\n"
                "  memory: 2048\n"
                "  disk_storage: fast\n"
                "  cloud_init_storage: local-lvm\n"
                "  bridge: vmbr0\n"
                "  network_model: virtio\n"
            )

            result = self.run_schema("inventory/templates/_schema.json", str(template_yaml))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_template_schema_rejects_unsupported_customize_ops(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_yaml = Path(tmp) / "debian-13-base.yaml"
            template_yaml.write_text(
                "name: debian-13-base\n"
                "vmid: 9001\n"
                "source:\n"
                "  url: https://example.invalid/debian.qcow2\n"
                "  checksum:\n"
                "    algorithm: sha512\n"
                f"    value: {'a' * 128}\n"
                "customize:\n"
                "  write_files:\n"
                "    - path: /etc/example\n"
                "hardware:\n"
                "  cores: 2\n"
                "  memory: 2048\n"
            )

            result = self.run_schema("inventory/templates/_schema.json", str(template_yaml))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("customize", result.stdout + result.stderr)

    def test_vm_schema_accepts_operational_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            vm_yaml = Path(tmp) / "template-verify.yaml"
            vm_yaml.write_text(
                "vmid: 8901\n"
                "lifecycle:\n"
                "  kind: operational\n"
                "  purpose: template-verification\n"
                "  generated: true\n"
                "placement:\n"
                "  host: wintermute\n"
                "source:\n"
                "  template: debian-13-base\n"
                "hardware:\n"
                "  cores: 1\n"
                "  memory: 1024\n"
                "cloud_init:\n"
                "  hostname: template-verify\n"
            )

            result = self.run_schema("inventory/vms/_schema.json", str(vm_yaml))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_vm_schema_accepts_dataset_backed_mounts_and_requires_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            vm_yaml = Path(tmp) / "media01.yaml"
            vm_yaml.write_text(
                "vmid: 101\n"
                "placement:\n"
                "  host: wintermute\n"
                "source:\n"
                "  template: debian-13-base\n"
                "hardware:\n"
                "  cores: 2\n"
                "  memory: 4096\n"
                "cloud_init:\n"
                "  hostname: media01\n"
                "mounts:\n"
                "  - name: media\n"
                "    dataset: media\n"
                "    protocol: nfs\n"
                "    mount_point: /mnt/nas/media\n"
                "    access: read_only\n"
            )

            result = self.run_schema("inventory/vms/_schema.json", str(vm_yaml))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            vm_yaml.write_text(vm_yaml.read_text().replace("    access: read_only\n", ""))

            result = self.run_schema("inventory/vms/_schema.json", str(vm_yaml))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("access", result.stdout + result.stderr)

            vm_yaml.write_text(
                "vmid: 101\n"
                "placement:\n"
                "  host: wintermute\n"
                "source:\n"
                "  template: debian-13-base\n"
                "hardware:\n"
                "  cores: 2\n"
                "  memory: 4096\n"
                "cloud_init:\n"
                "  hostname: media01\n"
                "nfs_mounts:\n"
                "  - export: media\n"
                "    mount_point: /mnt/nas/media\n"
            )

            result = self.run_schema("inventory/vms/_schema.json", str(vm_yaml))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("nfs_mounts", result.stdout + result.stderr)

    def test_vm_schema_accepts_tailnet_subnet_router_declaration(self):
        with tempfile.TemporaryDirectory() as tmp:
            vm_yaml = Path(tmp) / "tailnet-subnet-router-vm.yaml"
            vm_yaml.write_text(
                "vmid: 1020\n"
                "placement:\n"
                "  host: molly\n"
                "source:\n"
                "  template: debian-13-base\n"
                "hardware:\n"
                "  cores: 1\n"
                "  memory: 512\n"
                "cloud_init:\n"
                "  hostname: tailnet-subnet-router-vm\n"
                "tailnet_subnet_router:\n"
                "  advertise_routes:\n"
                "    - 10.10.0.0/24\n"
                "    - 10.40.0.0/24\n"
            )

            result = self.run_schema("inventory/vms/_schema.json", str(vm_yaml))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_vm_schema_accepts_launchable_service_group_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            vm_yaml = Path(tmp) / "media01.yaml"
            vm_yaml.write_text(
                "vmid: 101\n"
                "placement:\n"
                "  host: wintermute\n"
                "source:\n"
                "  template: debian-13-base\n"
                "hardware:\n"
                "  cores: 2\n"
                "  memory: 4096\n"
                "cloud_init:\n"
                "  hostname: media01\n"
                "launchable_service_groups:\n"
                "  - name: media\n"
                "    launch_order:\n"
                "      - prowlarr\n"
                "      - sonarr\n"
            )

            result = self.run_schema("inventory/vms/_schema.json", str(vm_yaml))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_vm_schema_accepts_instrumentation_enabled_opt_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            vm_yaml = Path(tmp) / "media01.yaml"
            vm_yaml.write_text(
                "vmid: 101\n"
                "placement:\n"
                "  host: wintermute\n"
                "source:\n"
                "  template: debian-13-base\n"
                "hardware:\n"
                "  cores: 2\n"
                "  memory: 4096\n"
                "cloud_init:\n"
                "  hostname: media01\n"
                "instrumentation:\n"
                "  enabled: false\n"
            )

            result = self.run_schema("inventory/vms/_schema.json", str(vm_yaml))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_service_schema_accepts_share_backed_volumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            service_yaml = Path(tmp) / "immich.yaml"
            service_yaml.write_text(
                "name: immich\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 2283\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: server\n"
                "      image: ghcr.io/immich-app/immich-server:v1.120.0\n"
                "      volumes:\n"
                "        - service_path: upload\n"
                "          container: /usr/src/app/upload\n"
                "        - mount: media\n"
                "          source: /\n"
                "          container: /photos\n"
                "          access: read_only\n"
            )

            result = self.run_schema("inventory/services/_schema.json", str(service_yaml))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            service_yaml.write_text(
                service_yaml.read_text().replace(
                    "        - mount: media\n",
                    "        - service_path: photos\n"
                    "          mount: media\n",
                )
            )

            result = self.run_schema("inventory/services/_schema.json", str(service_yaml))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("volumes", result.stdout + result.stderr)

    def test_service_schema_accepts_instrumentation_telemetry_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            service_yaml = Path(tmp) / "immich.yaml"
            service_yaml.write_text(
                "name: immich\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 2283\n"
                "instrumentation:\n"
                "  telemetry_targets:\n"
                "    - name: metrics\n"
                "      type: prometheus_metrics\n"
                "      published_port: 2283\n"
                "      scheme: http\n"
                "      path: /metrics\n"
                "    - name: health\n"
                "      type: http_probe\n"
                "      published_port: 2283\n"
                "      path: /healthz\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: server\n"
                "      image: ghcr.io/immich-app/immich-server:v1.120.0\n"
                "      published_ports:\n"
                "        - container: 2283\n"
            )

            result = self.run_schema("inventory/services/_schema.json", str(service_yaml))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_service_schema_accepts_service_observability_view_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            service_yaml = Path(tmp) / "immich.yaml"
            service_yaml.write_text(
                "name: immich\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 2283\n"
                "instrumentation:\n"
                "  telemetry_targets:\n"
                "    - name: metrics\n"
                "      type: prometheus_metrics\n"
                "      published_port: 2283\n"
                "  observability_views:\n"
                "    - profile: prometheus_generic\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: server\n"
                "      image: ghcr.io/immich-app/immich-server:v1.120.0\n"
                "      published_ports:\n"
                "        - container: 2283\n"
            )

            result = self.run_schema("inventory/services/_schema.json", str(service_yaml))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_service_schema_rejects_unknown_service_observability_view_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            service_yaml = Path(tmp) / "immich.yaml"
            service_yaml.write_text(
                "name: immich\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 2283\n"
                "instrumentation:\n"
                "  telemetry_targets:\n"
                "    - name: metrics\n"
                "      type: prometheus_metrics\n"
                "      published_port: 2283\n"
                "  observability_views:\n"
                "    - profile: postgres\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: server\n"
                "      image: ghcr.io/immich-app/immich-server:v1.120.0\n"
            )

            result = self.run_schema("inventory/services/_schema.json", str(service_yaml))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("prometheus_generic", result.stdout + result.stderr)

    def test_service_schema_rejects_multiple_service_observability_view_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            service_yaml = Path(tmp) / "immich.yaml"
            service_yaml.write_text(
                "name: immich\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 2283\n"
                "instrumentation:\n"
                "  telemetry_targets:\n"
                "    - name: metrics\n"
                "      type: prometheus_metrics\n"
                "      published_port: 2283\n"
                "  observability_views:\n"
                "    - profile: prometheus_generic\n"
                "    - profile: prometheus_generic\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: server\n"
                "      image: ghcr.io/immich-app/immich-server:v1.120.0\n"
            )

            result = self.run_schema("inventory/services/_schema.json", str(service_yaml))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("observability_views", result.stdout + result.stderr)

    def test_service_schema_rejects_telemetry_target_config_beyond_scheme_and_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            service_yaml = Path(tmp) / "immich.yaml"
            service_yaml.write_text(
                "name: immich\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 2283\n"
                "instrumentation:\n"
                "  telemetry_targets:\n"
                "    - name: metrics\n"
                "      type: prometheus_metrics\n"
                "      published_port: 2283\n"
                "      interval: 30s\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: server\n"
                "      image: ghcr.io/immich-app/immich-server:v1.120.0\n"
                "      published_ports:\n"
                "        - container: 2283\n"
            )

            result = self.run_schema("inventory/services/_schema.json", str(service_yaml))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("interval", result.stdout + result.stderr)

    def test_service_schema_rejects_pre_issue_07_quadlet_scaffold_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            service_yaml = Path(tmp) / "immich.yaml"
            service_yaml.write_text(
                "name: immich\n"
                "hostname: photos.fearn.cloud\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 2283\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  network: immich-net\n"
                "  containers:\n"
                "    - name: server\n"
                "      image: ghcr.io/immich-app/immich-server:v1.120.0\n"
                "      ports: ['2283:2283']\n"
                "      volumes:\n"
                "        - host: /srv/services/immich/upload\n"
                "          container: /usr/src/app/upload\n"
                "      env_from_secrets:\n"
                "        - secret: db_password\n"
                "          env_var_file: DB_PASSWORD_FILE\n"
                "      requires_mounts: []\n"
            )

            result = self.run_schema("inventory/services/_schema.json", str(service_yaml))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("deploy", result.stdout + result.stderr)

    def test_service_schema_accepts_secret_env_value_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            service_yaml = Path(tmp) / "pihole.yaml"
            service_yaml.write_text(
                "name: pihole\n"
                "backend:\n"
                "  vm: dns-primary-vm\n"
                "  port: 80\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: pihole\n"
                "      image: docker.io/pihole/pihole:2025.05.0\n"
                "      secrets:\n"
                "        - secret: secrets.web_api_password\n"
                "          env: WEBPASSWORD_FILE\n"
                "          env_value: secret_name\n"
            )

            result = self.run_schema("inventory/services/_schema.json", str(service_yaml))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_service_schema_accepts_dns_ingress_records_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            service_yaml = Path(tmp) / "pihole.yaml"
            service_yaml.write_text(
                "name: pihole\n"
                "dns:\n"
                "  provider: pihole\n"
                "  ingress_records:\n"
                "    enabled: true\n"
                "backend:\n"
                "  vm: dns-primary-vm\n"
                "  port: 80\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: pihole\n"
                "      image: docker.io/pihole/pihole:2025.05.0\n"
            )

            result = self.run_schema("inventory/services/_schema.json", str(service_yaml))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_service_schema_accepts_native_config_files_and_requires_reload_or_restart_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            service_yaml = Path(tmp) / "caddy.yaml"
            service_yaml.write_text(
                "name: caddy\n"
                "backend:\n"
                "  vm: ingress01\n"
                "  port: 80\n"
                "deploy:\n"
                "  type: native\n"
                "  package: caddy\n"
                "  apt_repo: caddy_official\n"
                "  service_name: caddy\n"
                "  config_files:\n"
                "    - template: Caddyfile.j2\n"
                "      dest: /etc/caddy/Caddyfile\n"
                "      mode: '0644'\n"
                "      reload_on_change: true\n"
                "    - template: caddy.env.j2\n"
                "      dest: /etc/default/caddy\n"
                "      mode: '0600'\n"
                "      restart_on_change: true\n"
            )

            result = self.run_schema("inventory/services/_schema.json", str(service_yaml))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            service_yaml.write_text(
                service_yaml.read_text().replace("      restart_on_change: true\n", "")
            )

            result = self.run_schema("inventory/services/_schema.json", str(service_yaml))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("config_files", result.stdout + result.stderr)

    def test_service_schema_accepts_native_environment_secrets_but_not_on_quadlet_services(self):
        with tempfile.TemporaryDirectory() as tmp:
            service_yaml = Path(tmp) / "caddy.yaml"
            service_yaml.write_text(
                "name: caddy\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 80\n"
                "deploy:\n"
                "  type: native\n"
                "  package: caddy\n"
                "  service_name: caddy\n"
                "  environment_secrets:\n"
                "    - secret: secrets.cloudflare_api_token\n"
                "      env: CLOUDFLARE_API_TOKEN\n"
                "  config_files:\n"
                "    - template: caddy.env.j2\n"
                "      dest: /etc/default/caddy\n"
                "      mode: '0600'\n"
                "      restart_on_change: true\n"
            )

            result = self.run_schema("inventory/services/_schema.json", str(service_yaml))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            service_yaml.write_text(
                "name: immich\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 2283\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  environment_secrets:\n"
                "    - secret: secrets.cloudflare_api_token\n"
                "      env: CLOUDFLARE_API_TOKEN\n"
                "  containers:\n"
                "    - name: server\n"
                "      image: ghcr.io/immich-app/immich-server:v1.120.0\n"
            )

            result = self.run_schema("inventory/services/_schema.json", str(service_yaml))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("environment_secrets", result.stdout + result.stderr)
