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
                "      roles: [PVEVMAdmin, PVEDatastoreUser]\n"
                "      tokens:\n"
                "        - id: tofu\n"
                "          roles: [PVEVMAdmin, PVEDatastoreUser]\n"
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

    def test_host_schema_rejects_contradictory_gpu_passthrough(self):
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

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("gpu_passthrough", result.stdout + result.stderr)

    def test_template_schema_accepts_builder_defaults_and_supported_customize_ops(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_yaml = Path(tmp) / "debian-12-base.yaml"
            template_yaml.write_text(
                "name: debian-12-base\n"
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
            template_yaml = Path(tmp) / "debian-12-base.yaml"
            template_yaml.write_text(
                "name: debian-12-base\n"
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
                "  template: debian-12-base\n"
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
                "  template: debian-12-base\n"
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
                "  template: debian-12-base\n"
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
                "        - host: /srv/services/immich/upload\n"
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
                    "        - host: /srv/services/immich/photos\n"
                    "          mount: media\n",
                )
            )

            result = self.run_schema("inventory/services/_schema.json", str(service_yaml))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("volumes", result.stdout + result.stderr)
