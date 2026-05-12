import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class VMConfigureWorkflowTests(unittest.TestCase):
    def test_just_vm_configure_calls_workflow_script(self):
        justfile = (REPO_ROOT / "justfile").read_text()

        self.assertIn("vm-configure vm:", justfile)
        self.assertIn("./scripts/vm-configure {{vm}}", justfile)

    def test_vm_configure_rejects_undeclared_vms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "inventory" / "vms").mkdir(parents=True)
            env = os.environ.copy()
            env["FORTRESS_ROOT"] = str(root)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "vm-configure"), "ghost"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("VM 'ghost' is not declared", result.stderr)

    def test_vm_configure_requires_vm_sibling_sops_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vm_dir = root / "inventory" / "vms"
            vm_dir.mkdir(parents=True)
            (vm_dir / "media01.yaml").write_text(
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
            )
            env = os.environ.copy()
            env["FORTRESS_ROOT"] = str(root)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "vm-configure"), "media01"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("VM Sibling SOPS File is required", result.stderr)
            self.assertIn("inventory/vms/media01.sops.yaml", result.stderr)

    def test_vm_configure_uses_tmpfs_key_wrapper_for_ansible_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._configure_fixture(tmp)
            env = os.environ.copy()
            env["FORTRESS_ROOT"] = str(root)
            env["CALLS_LOG"] = str(calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "vm-configure"), "media01"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            calls = calls_log.read_text()
            self.assertIn("decrypt-keys", calls)
            self.assertIn("inventory/vms/media01.sops.yaml -- ansible-playbook", calls)
            self.assertIn("ansible/playbooks/vm-configure.yml", calls)
            self.assertIn("--limit media01", calls)
            self.assertIn('"fortress_vm_sops_file":', calls)
            self.assertIn("inventory/vms/media01.sops.yaml", calls)

    def test_tmpfs_key_wrapper_decrypts_structured_bootstrap_private_key(self):
        decrypt_keys = (REPO_ROOT / "scripts" / "decrypt-keys").read_text()

        self.assertIn('["ssh_keys"]["bootstrap"]["private_key"]', decrypt_keys)
        self.assertNotIn("ssh_root_key", decrypt_keys)

    def test_vm_configure_playbook_waits_for_cloud_init_before_admin_finalization(self):
        playbook = (REPO_ROOT / "ansible" / "playbooks" / "vm-configure.yml").read_text()

        self.assertIn("ansible.builtin.wait_for_connection", playbook)
        self.assertIn("cloud-init status --wait", playbook)
        self.assertLess(
            playbook.index("cloud-init status --wait"),
            playbook.index("name: vm_admin_user"),
        )
        self.assertTrue((REPO_ROOT / "ansible" / "roles" / "vm_admin_user" / "tasks" / "main.yml").is_file())

    def test_vm_configure_playbook_writes_nfs_mount_units_before_admin_finalization(self):
        playbook = (REPO_ROOT / "ansible" / "playbooks" / "vm-configure.yml").read_text()

        self.assertIn("name: vm_nfs_mounts", playbook)
        self.assertLess(
            playbook.index("name: vm_nfs_mounts"),
            playbook.index("name: vm_admin_user"),
        )

    def test_vm_configure_playbook_configures_tailnet_subnet_router_before_admin_finalization(self):
        playbook = (REPO_ROOT / "ansible" / "playbooks" / "vm-configure.yml").read_text()

        self.assertIn("name: tailnet_subnet_router", playbook)
        self.assertIn("when: fortress_vm.tailnet_subnet_router is defined", playbook)
        self.assertLess(
            playbook.index("name: tailnet_subnet_router"),
            playbook.index("name: vm_admin_user"),
        )

    def test_vm_admin_user_role_uses_only_builtin_modules_for_configure(self):
        role = (REPO_ROOT / "ansible" / "roles" / "vm_admin_user" / "tasks" / "main.yml").read_text()

        self.assertNotIn("ansible.posix.authorized_key", role)
        self.assertIn("ansible.builtin.lineinfile", role)
        self.assertIn("authorized_keys", role)

    def _configure_fixture(self, tmp):
        root = Path(tmp)
        vm_dir = root / "inventory" / "vms"
        scripts_dir = root / "scripts"
        vm_dir.mkdir(parents=True)
        scripts_dir.mkdir()
        (root / "inventory" / "fortress.yaml").write_text("plugin: fortress\nroot: ..\n")
        (vm_dir / "media01.yaml").write_text(
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
        )
        (vm_dir / "media01.sops.yaml").write_text("encrypted: value\n")
        calls_log = root / "calls.log"
        decrypt_keys = scripts_dir / "decrypt-keys"
        decrypt_keys.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'decrypt-keys %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
        )
        decrypt_keys.chmod(decrypt_keys.stat().st_mode | stat.S_IXUSR)
        return root, calls_log
