import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class FoundationTests(unittest.TestCase):
    def test_repository_layout_exists(self):
        expected_directories = [
            "inventory/hosts",
            "inventory/vms",
            "inventory/services",
            "inventory/templates",
            "ansible",
            "tofu",
            "runbooks",
            "scripts",
        ]

        for directory in expected_directories:
            with self.subTest(directory=directory):
                self.assertTrue((REPO_ROOT / directory).is_dir())

    def test_just_lists_operator_command_stubs(self):
        expected_recipes = [
            "test",
            "host-bootstrap",
            "host-configure",
            "vm-up",
            "vm-destroy",
            "service-deploy",
            "templates-build",
            "ingress-regenerate",
        ]

        result = subprocess.run(
            ["just", "--list"],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        for recipe in expected_recipes:
            with self.subTest(recipe=recipe):
                self.assertIn(recipe, result.stdout)

    def test_sops_rules_cover_sibling_sops_files(self):
        sops_config = REPO_ROOT / ".sops.yaml"

        self.assertTrue(sops_config.is_file())
        self.assertIn("creation_rules:", sops_config.read_text())
        self.assertIn(r"\.sops\.yaml$", sops_config.read_text())
        self.assertIn("age/recipients.txt", sops_config.read_text())

    def test_decrypt_keys_wrapper_uses_tmpfs_and_trap_cleanup(self):
        wrapper = REPO_ROOT / "scripts" / "decrypt-keys"

        self.assertTrue(wrapper.is_file())
        self.assertTrue(wrapper.stat().st_mode & 0o111)

        script = wrapper.read_text()
        self.assertIn("/dev/shm/fortress", script)
        self.assertIn("trap cleanup EXIT", script)
        self.assertIn("chmod 0600", script)
        self.assertIn("sops --decrypt", script)

    def test_pre_commit_runs_foundation_checks(self):
        pre_commit = REPO_ROOT / ".pre-commit-config.yaml"

        self.assertTrue(pre_commit.is_file())
        config = pre_commit.read_text()
        self.assertIn("fortress-foundation-tests", config)
        self.assertIn("python3 -m unittest", config)
        self.assertIn("fortress-host-schema", config)
        self.assertIn("check-jsonschema --schemafile inventory/hosts/_schema.json", config)
        self.assertIn("fortress-inventory-cross-file", config)
        self.assertIn("python3 -m fortress_inventory.validate_inventory", config)
        self.assertIn("fortress-sops-decryption-health", config)
        self.assertIn("python3 -m fortress_inventory.check_sops_decryptable", config)

    def test_initial_setup_runbook_documents_rebuild_ceremony(self):
        runbook = REPO_ROOT / "runbooks" / "initial-setup.md"

        self.assertTrue(runbook.is_file())
        content = runbook.read_text()
        expected_phrases = [
            "age key import",
            "offline backup",
            "dependency install",
            "repo clone",
            "decrypt-test",
            "DR demo",
        ]

        for phrase in expected_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, content)
