import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


SCHEMA_CASES = [
    ("Host", "inventory/hosts/_schema.json", "tests/fixtures/schema/hosts"),
    ("VM", "inventory/vms/_schema.json", "tests/fixtures/schema/vms"),
    ("Service", "inventory/services/_schema.json", "tests/fixtures/schema/services"),
    ("Template", "inventory/templates/_schema.json", "tests/fixtures/schema/templates"),
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
            "templates": "source",
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
