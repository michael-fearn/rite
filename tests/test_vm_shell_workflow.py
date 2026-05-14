import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class VMShellWorkflowTests(unittest.TestCase):
    def test_just_vm_shell_calls_workflow_script(self):
        justfile = (REPO_ROOT / "justfile").read_text()

        self.assertIn("vm-shell vm:", justfile)
        self.assertIn("./scripts/vm-shell {{vm}}", justfile)

    def test_vm_shell_rejects_extra_arguments_without_separator(self):
        result = subprocess.run(
            [str(REPO_ROOT / "scripts" / "vm-shell"), "media01", "hostname"],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("usage: scripts/vm-shell <vm> [-- <command>...]", result.stderr)

    def test_vm_shell_rejects_undeclared_vms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "inventory" / "vms").mkdir(parents=True)
            env = os.environ.copy()
            env["FORTRESS_ROOT"] = str(root)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "vm-shell"), "ghost"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("VM 'ghost' is not declared", result.stderr)

    def test_vm_shell_requires_vm_sibling_sops_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vm_dir = root / "inventory" / "vms"
            vm_dir.mkdir(parents=True)
            (vm_dir / "media01.yaml").write_text("vmid: 101\n")
            env = os.environ.copy()
            env["FORTRESS_ROOT"] = str(root)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "vm-shell"), "media01"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("VM Sibling SOPS File is required", result.stderr)
            self.assertIn("inventory/vms/media01.sops.yaml", result.stderr)

    def test_vm_shell_fails_before_ssh_without_ansible_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._shell_fixture(tmp, {"ansible_user": "admin"})
            env = self._shell_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "vm-shell"), "media01"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("VM 'media01' has no ansible_host in Ansible Inventory", result.stderr)
            self.assertNotIn("ssh ", calls_log.read_text())

    def test_vm_shell_uses_ansible_inventory_connection_vars_for_ssh(self):
        hostvars = {
            "ansible_host": "10.0.10.101",
            "ansible_user": "admin",
            "ansible_ssh_private_key_file": "/dev/shm/fortress/media01.key",
            "ansible_ssh_common_args": "-o StrictHostKeyChecking=accept-new",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._shell_fixture(tmp, hostvars)
            env = self._shell_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "vm-shell"), "media01"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("ansible-inventory -i", calls_log.read_text())
            self.assertIn("decrypt-keys", calls_log.read_text())
            self.assertIn("inventory/vms/media01.sops.yaml -- ssh", calls_log.read_text())
            self.assertIn(
                "ssh -F /dev/null -t -o StrictHostKeyChecking=accept-new -i /dev/shm/fortress/media01.key admin@10.0.10.101",
                calls_log.read_text(),
            )

    def test_vm_shell_runs_command_after_separator(self):
        hostvars = {
            "ansible_host": "10.0.10.101",
            "ansible_user": "admin",
            "ansible_ssh_private_key_file": "/dev/shm/fortress/media01.key",
            "ansible_ssh_common_args": "-o StrictHostKeyChecking=accept-new",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._shell_fixture(tmp, hostvars)
            env = self._shell_env(root, calls_log)

            result = subprocess.run(
                [
                    str(REPO_ROOT / "scripts" / "vm-shell"),
                    "media01",
                    "--",
                    "systemctl",
                    "is-active",
                    "fortress-dns-primary-pihole.service",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "ssh -F /dev/null -o StrictHostKeyChecking=accept-new -i /dev/shm/fortress/media01.key "
                "admin@10.0.10.101 systemctl is-active fortress-dns-primary-pihole.service",
                calls_log.read_text(),
            )

    def test_vm_shell_shell_quotes_remote_command_arguments(self):
        hostvars = {
            "ansible_host": "10.0.10.101",
            "ansible_user": "admin",
            "ansible_ssh_private_key_file": "/dev/shm/fortress/media01.key",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._shell_fixture(tmp, hostvars)
            env = self._shell_env(root, calls_log)

            result = subprocess.run(
                [
                    str(REPO_ROOT / "scripts" / "vm-shell"),
                    "media01",
                    "--",
                    "sh",
                    "-lc",
                    "printf '%s\\n' \"$tcp\" | awk '{print $4}'",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                """ssh -F /dev/null -i /dev/shm/fortress/media01.key admin@10.0.10.101 sh -lc 'printf '"'"'%s\\n'"'"' "$tcp" | awk '"'"'{print $4}'"'"''""",
                calls_log.read_text(),
            )

    def _shell_fixture(self, tmp, vm_hostvars):
        root = Path(tmp)
        vm_dir = root / "inventory" / "vms"
        bin_dir = root / "bin"
        vm_dir.mkdir(parents=True)
        bin_dir.mkdir()
        (root / "inventory" / "fortress.yaml").write_text("plugin: fortress\nroot: ..\n")
        (vm_dir / "media01.yaml").write_text("vmid: 101\n")
        (vm_dir / "media01.sops.yaml").write_text("encrypted: value\n")

        calls_log = root / "calls.log"
        inventory = {"_meta": {"hostvars": {"media01": vm_hostvars}}}
        fake_inventory = bin_dir / "ansible-inventory"
        fake_inventory.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "with open(os.environ['CALLS_LOG'], 'a') as log:\n"
            "    log.write('ansible-inventory ' + ' '.join(sys.argv[1:]) + '\\n')\n"
            f"print({json.dumps(inventory)!r})\n"
        )
        fake_inventory.chmod(fake_inventory.stat().st_mode | stat.S_IXUSR)

        fake_ssh = bin_dir / "ssh"
        fake_ssh.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'ssh %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
        )
        fake_ssh.chmod(fake_ssh.stat().st_mode | stat.S_IXUSR)

        scripts_dir = root / "scripts"
        scripts_dir.mkdir()
        fake_decrypt_keys = scripts_dir / "decrypt-keys"
        fake_decrypt_keys.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'decrypt-keys %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
            "while [ \"$1\" != \"--\" ]; do shift; done\n"
            "shift\n"
            "exec \"$@\"\n"
        )
        fake_decrypt_keys.chmod(fake_decrypt_keys.stat().st_mode | stat.S_IXUSR)
        return root, calls_log

    def _shell_env(self, root, calls_log):
        env = os.environ.copy()
        env["FORTRESS_ROOT"] = str(root)
        env["CALLS_LOG"] = str(calls_log)
        env["PATH"] = f"{root / 'bin'}:{env['PATH']}"
        return env


if __name__ == "__main__":
    unittest.main()
