import unittest
from pathlib import Path

from fortress_inventory.validate import validate_inventory_tree


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"


class InventoryCrossFileValidatorTests(unittest.TestCase):
    def codes_for(self, fixture_name):
        errors = validate_inventory_tree(FIXTURES / fixture_name)
        return {error.code for error in errors}

    def test_valid_inventory_tree_has_no_cross_file_errors(self):
        self.assertEqual(validate_inventory_tree(FIXTURES / "inventory_valid"), [])

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
