import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class FoundationTests(unittest.TestCase):
    def files_containing(self, needle):
        matches = []
        for path in REPO_ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or ".scratch" in path.parts or "__pycache__" in path.parts:
                continue
            if path.suffix in {".pyc", ".pyo"}:
                continue
            if needle in path.read_text(errors="ignore"):
                matches.append(path.relative_to(REPO_ROOT))
        return matches

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

    def test_debian_13_base_is_the_canonical_debian_base_template(self):
        retired_template = "debian-" + "12-base"
        matches = self.files_containing(retired_template)

        self.assertEqual(matches, [])

    def test_just_lists_operator_command_stubs(self):
        expected_recipes = [
            "test",
            "host-bootstrap",
            "host-configure",
            "host-shell",
            "vm-up",
            "vm-shell",
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

    def test_decrypt_keys_wrapper_preserves_known_hosts_but_removes_decrypted_keys(self):
        wrapper = REPO_ROOT / "scripts" / "decrypt-keys"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key_dir = root / "keys"
            bin_dir = root / "bin"
            key_dir.mkdir()
            bin_dir.mkdir()
            (key_dir / "known_hosts").write_text("10.0.0.1 ssh-ed25519 test\n")
            sops_file = root / "media01.sops.yaml"
            sops_file.write_text("encrypted: value\n")

            fake_sops = bin_dir / "sops"
            fake_sops.write_text("#!/usr/bin/env bash\nprintf '%s\\n' 'PRIVATE KEY'\n")
            fake_sops.chmod(fake_sops.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["FORTRESS_KEY_DIR"] = str(key_dir)
            env["PATH"] = f"{bin_dir}:{env['PATH']}"

            result = subprocess.run(
                [
                    str(wrapper),
                    str(sops_file),
                    "--",
                    "bash",
                    "-lc",
                    'test -f "$FORTRESS_KEY_DIR/media01.key" && test -f "$FORTRESS_KEY_DIR/known_hosts"',
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((key_dir / "known_hosts").is_file())
            self.assertFalse((key_dir / "media01.key").exists())

    def test_pre_commit_runs_foundation_checks(self):
        pre_commit = REPO_ROOT / ".pre-commit-config.yaml"

        self.assertTrue(pre_commit.is_file())
        config = pre_commit.read_text()
        self.assertIn("fortress-foundation-tests", config)
        self.assertIn("python3 -m unittest", config)
        self.assertIn("fortress-host-schema", config)
        self.assertIn("check-jsonschema --schemafile inventory/hosts/_schema.json", config)
        self.assertIn("fortress-dataset-schema", config)
        self.assertIn("check-jsonschema --schemafile inventory/datasets/_schema.json", config)
        self.assertIn("fortress-nas-schema", config)
        self.assertIn("check-jsonschema --schemafile inventory/nas/_schema.json", config)
        self.assertIn("fortress-inventory-cross-file", config)
        self.assertIn("python3 -m fortress_inventory.validate_inventory", config)
        self.assertIn("fortress-template-verification-policy-schema", config)
        self.assertIn("check-jsonschema --schemafile inventory/template-verification-policy.schema.json", config)
        self.assertIn("fortress-sops-decryption-health", config)
        self.assertIn("python3 -m fortress_inventory.check_sops_decryptable", config)

    def test_generated_template_verification_vm_artifacts_are_ignored(self):
        gitignore = (REPO_ROOT / ".gitignore").read_text()

        for pattern in [
            "inventory/vms/tmp-template-verify*.yaml",
            "inventory/vms/tmp-template-verify*.sops.yaml",
        ]:
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, gitignore)

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
