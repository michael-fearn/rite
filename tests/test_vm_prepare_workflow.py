import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class VMPrepareWorkflowTests(unittest.TestCase):
    def test_vm_prepare_rejects_undeclared_vms_before_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "inventory" / "vms").mkdir(parents=True)
            calls_log = root / "calls.log"
            env = self._fake_tools(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "vm-prepare"), "ghost"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("VM 'ghost' is not declared", result.stderr)
            self.assertFalse(calls_log.exists())

    def test_vm_prepare_refuses_when_vm_sibling_sops_file_already_contains_vm_ssh_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._prepare_fixture(tmp)
            (root / "inventory" / "vms" / "demo01.sops.yaml").write_text("encrypted ssh\n")
            env = self._fake_tools(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "vm-prepare"), "demo01"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("already contains a VM SSH key entry", result.stderr)
            calls = calls_log.read_text()
            self.assertIn('sops --decrypt --extract ["ssh_keys"]["bootstrap"]["private_key"]', calls)
            self.assertNotIn("ssh-keygen", calls)

    def test_vm_prepare_merges_generated_ssh_key_into_existing_non_ssh_sibling_sops_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._prepare_fixture(tmp)
            (root / "inventory" / "vms" / "demo01.sops.yaml").write_text("encrypted tailnet\n")
            env = self._fake_tools(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "vm-prepare"), "demo01"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            plaintext = (root / "last-plaintext.sops.yaml").read_text()
            self.assertIn("tailnet:", plaintext)
            self.assertIn("auth_key:", plaintext)
            self.assertIn("ssh_keys:", plaintext)
            self.assertIn("private_key: |", plaintext)

    def test_vm_prepare_writes_public_key_and_encrypted_sibling_sops_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._prepare_fixture(tmp)
            env = self._fake_tools(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "vm-prepare"), "demo01"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            vm_yaml = (root / "inventory" / "vms" / "demo01.yaml").read_text()
            vm_sops = root / "inventory" / "vms" / "demo01.sops.yaml"
            self.assertIn("ssh_public_key: ssh-ed25519 vm-public demo01", vm_yaml)
            self.assertEqual("encrypted vm sops\n", vm_sops.read_text())
            calls = calls_log.read_text()
            self.assertIn("ssh-keygen -t ed25519 -N  -C fortress-vm-prepare:demo01:", calls)
            self.assertIn("sops --encrypt --config", calls)
            self.assertIn("inventory/vms/demo01.sops.yaml", calls)

    def _prepare_fixture(self, tmp):
        root = Path(tmp)
        vm_dir = root / "inventory" / "vms"
        vm_dir.mkdir(parents=True)
        (root / ".sops.yaml").write_text("creation_rules: []\n")
        (vm_dir / "demo01.yaml").write_text(
            "vmid: 801\n"
            "placement:\n"
            "  host: wintermute\n"
            "source:\n"
            "  template: debian-13-base\n"
            "hardware:\n"
            "  cores: 1\n"
            "  memory: 1024\n"
            "cloud_init:\n"
            "  hostname: demo01\n"
        )
        return root, root / "calls.log"

    def _fake_tools(self, root, calls_log):
        bin_dir = root / "bin"
        bin_dir.mkdir()
        ssh_keygen = bin_dir / "ssh-keygen"
        ssh_keygen.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'ssh-keygen %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
            "while [ $# -gt 0 ]; do\n"
            "  if [ \"$1\" = -f ]; then shift; key_path=\"$1\"; fi\n"
            "  shift\n"
            "done\n"
            "printf 'PRIVATE KEY demo01\\n' > \"$key_path\"\n"
            "printf 'ssh-ed25519 vm-public demo01\\n' > \"$key_path.pub\"\n"
        )
        ssh_keygen.chmod(ssh_keygen.stat().st_mode | stat.S_IXUSR)
        sops = bin_dir / "sops"
        sops.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'sops %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
            "if [ \"$1\" = --decrypt ] && [ \"$2\" = --extract ]; then\n"
            "  if grep -q 'encrypted ssh' \"${@: -1}\"; then printf 'PRIVATE KEY demo01\\n'; exit 0; fi\n"
            "  exit 1\n"
            "fi\n"
            "if [ \"$1\" = --decrypt ]; then\n"
            "  if grep -q 'encrypted tailnet' \"$2\"; then printf 'tailnet:\\n  auth_key:\\n    value: tskey-auth-example\\n'; exit 0; fi\n"
            "  exit 1\n"
            "fi\n"
            "input=\"${@: -1}\"\n"
            "while [ $# -gt 0 ]; do\n"
            "  if [ \"$1\" = --output ]; then shift; output=\"$1\"; fi\n"
            "  shift\n"
            "done\n"
            "cp \"$input\" \"$FORTRESS_ROOT/last-plaintext.sops.yaml\"\n"
            "printf 'encrypted vm sops\\n' > \"$output\"\n"
        )
        sops.chmod(sops.stat().st_mode | stat.S_IXUSR)
        env = os.environ.copy()
        env["FORTRESS_ROOT"] = str(root)
        env["CALLS_LOG"] = str(calls_log)
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        return env


if __name__ == "__main__":
    unittest.main()
