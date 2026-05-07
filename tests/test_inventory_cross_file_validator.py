import shutil
import tempfile
import unittest
from pathlib import Path

from fortress_inventory.model import load_inventory_tree
from fortress_inventory.validate import validate_inventory_tree


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"


class InventoryCrossFileValidatorTests(unittest.TestCase):
    def codes_for(self, fixture_name):
        errors = validate_inventory_tree(FIXTURES / fixture_name)
        return {error.code for error in errors}

    def test_valid_inventory_tree_has_no_cross_file_errors(self):
        self.assertEqual(validate_inventory_tree(FIXTURES / "inventory_valid"), [])

    def test_inventory_model_loads_template_verification_policy(self):
        model = load_inventory_tree(REPO_ROOT)

        self.assertEqual(model.template_verification_policy["vmid"], 8901)

    def test_inventory_model_loads_datasets(self):
        model = load_inventory_tree(FIXTURES / "inventory_valid")

        self.assertEqual(model.datasets["media"]["path"], "/mnt/pool/media")

    def test_dataset_names_must_be_unique(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "datasets" / "photos.yaml").write_text(
                "name: media\n"
                "nas: truenas\n"
                "path: /mnt/pool/photos\n"
                "lifecycle: adopted\n"
                "owner:\n"
                "  uid: 1000\n"
                "  gid: 1000\n"
            )

            self.assertIn("duplicate_dataset_name", {error.code for error in validate_inventory_tree(root)})

    def test_dataset_nas_endpoint_must_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "datasets" / "media.yaml").write_text(
                "name: media\n"
                "nas: missing-nas\n"
                "path: /mnt/pool/media\n"
                "lifecycle: adopted\n"
                "owner:\n"
                "  uid: 1000\n"
                "  gid: 1000\n"
            )

            self.assertIn("missing_dataset_nas_endpoint", {error.code for error in validate_inventory_tree(root)})

    def test_ordinary_inventory_rejects_ephemeral_datasets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "datasets" / "media.yaml").write_text(
                "name: media\n"
                "nas: truenas\n"
                "path: /mnt/pool/media\n"
                "lifecycle: ephemeral\n"
            )

            self.assertIn("ordinary_ephemeral_dataset", {error.code for error in validate_inventory_tree(root)})

    def test_acceptance_inventory_allows_ephemeral_datasets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "datasets" / "media.yaml").write_text(
                "name: media\n"
                "nas: truenas\n"
                "path: /mnt/pool/media\n"
                "lifecycle: ephemeral\n"
            )

            codes = {error.code for error in validate_inventory_tree(root, allow_ephemeral_datasets=True)}
            self.assertNotIn("ordinary_ephemeral_dataset", codes)

    def test_service_backend_vm_must_exist(self):
        self.assertIn("missing_service_backend_vm", self.codes_for("inventory_invalid/missing-service-vm"))

    def test_backend_ports_must_not_collide_on_same_vm(self):
        self.assertIn("backend_port_collision", self.codes_for("inventory_invalid/port-collision"))

    def test_service_hostnames_must_be_unique(self):
        self.assertIn("duplicate_service_hostname", self.codes_for("inventory_invalid/duplicate-hostname"))

    def test_vm_placement_host_must_exist(self):
        self.assertIn("missing_vm_host", self.codes_for("inventory_invalid/missing-vm-host"))

    def test_vm_template_must_exist(self):
        self.assertIn("missing_vm_template", self.codes_for("inventory_invalid/missing-vm-template"))

    def test_vm_nfs_exports_must_exist_in_global_vars(self):
        self.assertIn("missing_nfs_export", self.codes_for("inventory_invalid/missing-nfs-export"))

    def test_vm_disks_must_use_storage_declared_by_placement_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "vms" / "media01.yaml").write_text(
                "vmid: 101\n"
                "placement:\n"
                "  host: wintermute\n"
                "source:\n"
                "  template: debian-12-base\n"
                "hardware:\n"
                "  cores: 2\n"
                "  memory: 4096\n"
                "  disks:\n"
                "    - storage: missing-store\n"
                "      size: 32G\n"
                "cloud_init:\n"
                "  hostname: media01\n"
            )

            self.assertIn("missing_host_storage", {error.code for error in validate_inventory_tree(root)})

    def test_vm_interfaces_must_use_bridges_declared_by_placement_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "vms" / "media01.yaml").write_text(
                "vmid: 101\n"
                "placement:\n"
                "  host: wintermute\n"
                "source:\n"
                "  template: debian-12-base\n"
                "hardware:\n"
                "  cores: 2\n"
                "  memory: 4096\n"
                "network:\n"
                "  interfaces:\n"
                "    - bridge: missing-bridge\n"
                "cloud_init:\n"
                "  hostname: media01\n"
            )

            self.assertIn("missing_host_bridge", {error.code for error in validate_inventory_tree(root)})

    def test_ordinary_vms_must_not_use_operational_vmids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_vm(root, "media01", 8901)

            self.assertIn("ordinary_vm_operational_vmid", {error.code for error in validate_inventory_tree(root)})

    def test_operational_vms_must_use_operational_vmids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_vm(
                root,
                "template-verify",
                8801,
                "lifecycle:\n"
                "  kind: operational\n"
                "  purpose: template-verification\n"
                "  generated: true\n",
            )

            self.assertIn("operational_vm_vmid_out_of_range", {error.code for error in validate_inventory_tree(root)})

    def test_template_vmids_are_reserved_for_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_vm(root, "media01", 9001)

            self.assertIn("vm_uses_template_vmid", {error.code for error in validate_inventory_tree(root)})

    def test_checked_in_tmp_vm_names_are_reserved_for_generated_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_vm(root, "tmp-template-verify", 101)

            self.assertIn("reserved_tmp_vm_name", {error.code for error in validate_inventory_tree(root)})

    def test_generated_tmp_operational_vm_names_are_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_vm(
                root,
                "tmp-template-verify",
                8901,
                "lifecycle:\n"
                "  kind: operational\n"
                "  purpose: template-verification\n"
                "  generated: true\n",
            )

            self.assertNotIn("reserved_tmp_vm_name", {error.code for error in validate_inventory_tree(root)})

    def write_fixture_vm(self, root, name, vmid, lifecycle=""):
        (root / "inventory" / "vms" / f"{name}.yaml").write_text(
            f"vmid: {vmid}\n"
            f"{lifecycle}"
            "placement:\n"
            "  host: wintermute\n"
            "source:\n"
            "  template: debian-12-base\n"
            "hardware:\n"
            "  cores: 2\n"
            "  memory: 4096\n"
            "cloud_init:\n"
            f"  hostname: {name}\n"
        )
