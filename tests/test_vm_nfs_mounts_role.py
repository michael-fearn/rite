import subprocess
import tempfile
import unittest
from pathlib import Path
import os
import importlib.util


REPO_ROOT = Path(__file__).resolve().parents[1]
SYSTEMD_UNITS = importlib.util.spec_from_file_location(
    "systemd_units",
    REPO_ROOT / "ansible" / "roles" / "vm_nfs_mounts" / "filter_plugins" / "systemd_units.py",
)
systemd_units = importlib.util.module_from_spec(SYSTEMD_UNITS)
SYSTEMD_UNITS.loader.exec_module(systemd_units)


class VMNFSMountsRoleTests(unittest.TestCase):
    def test_role_materializes_declared_nfs_mount_as_systemd_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            playbook = root / "playbook.yml"
            unit_dir = root / "systemd"
            mount_root = root / "mnt"
            playbook.write_text(
                "- hosts: localhost\n"
                "  connection: local\n"
                "  gather_facts: false\n"
                "  vars:\n"
                "    fortress_skip_nfs_client_install: true\n"
                f"    fortress_systemd_unit_dir: {unit_dir}\n"
                "    fortress_globals:\n"
                "      nas:\n"
                "        default_options: [nfsvers=4.2, soft, _netdev]\n"
                "    fortress_nas_endpoints:\n"
                "      truenas:\n"
                "        name: truenas\n"
                "        management_address: 10.0.10.10\n"
                "        share_address: 10.0.20.10\n"
                "    fortress_datasets:\n"
                "      media:\n"
                "        name: media\n"
                "        nas: truenas\n"
                "        path: /mnt/pool/media\n"
                "    fortress_vm:\n"
                "      mounts:\n"
                "        - name: media\n"
                "          dataset: media\n"
                "          protocol: nfs\n"
                f"          mount_point: {mount_root / 'media-files'}\n"
                "          access: read_only\n"
                "          options_extra: [x-systemd.automount]\n"
                "  roles:\n"
                "    - vm_nfs_mounts\n"
            )

            env = os.environ.copy()
            env["ANSIBLE_ROLES_PATH"] = str(REPO_ROOT / "ansible" / "roles")
            result = subprocess.run(
                [
                    "ansible-playbook",
                    str(playbook),
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((mount_root / "media-files").is_dir())
            unit = (unit_dir / systemd_units.fortress_systemd_mount_unit(mount_root / "media-files")).read_text()
            self.assertIn("What=10.0.20.10:/mnt/pool/media", unit)
            self.assertIn(f"Where={mount_root / 'media-files'}", unit)
            self.assertIn("Type=nfs", unit)
            self.assertIn("Options=nfsvers=4.2,soft,_netdev,ro,x-systemd.automount", unit)
            self.assertIn("WantedBy=multi-user.target", unit)

    def test_role_installs_nfs_client_utilities(self):
        tasks = (REPO_ROOT / "ansible" / "roles" / "vm_nfs_mounts" / "tasks" / "main.yml").read_text()

        self.assertIn("ansible.builtin.apt", tasks)
        self.assertIn("name: nfs-common", tasks)

    def test_role_retries_starting_nfs_mount_units(self):
        tasks = (REPO_ROOT / "ansible" / "roles" / "vm_nfs_mounts" / "tasks" / "main.yml").read_text()

        self.assertIn("name: Enable and start NFS mount units", tasks)
        self.assertIn("register: fortress_nfs_mount_start", tasks)
        self.assertIn("until: fortress_nfs_mount_start is succeeded", tasks)
        self.assertIn("retries:", tasks)
        self.assertIn("delay:", tasks)

    def test_role_renders_read_write_access_as_rw_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            playbook = root / "playbook.yml"
            unit_dir = root / "systemd"
            mount_root = root / "mnt"
            playbook.write_text(
                "- hosts: localhost\n"
                "  connection: local\n"
                "  gather_facts: false\n"
                "  vars:\n"
                "    fortress_skip_nfs_client_install: true\n"
                f"    fortress_systemd_unit_dir: {unit_dir}\n"
                "    fortress_globals:\n"
                "      nas:\n"
                "        default_options: [nfsvers=4.2, soft, _netdev]\n"
                "    fortress_nas_endpoints:\n"
                "      truenas:\n"
                "        name: truenas\n"
                "        management_address: 10.0.10.10\n"
                "        share_address: 10.0.20.10\n"
                "    fortress_datasets:\n"
                "      media:\n"
                "        name: media\n"
                "        nas: truenas\n"
                "        path: /mnt/pool/media\n"
                "    fortress_vm:\n"
                "      mounts:\n"
                "        - name: media\n"
                "          dataset: media\n"
                "          protocol: nfs\n"
                f"          mount_point: {mount_root / 'media'}\n"
                "          access: read_write\n"
                "  roles:\n"
                "    - vm_nfs_mounts\n"
            )

            env = os.environ.copy()
            env["ANSIBLE_ROLES_PATH"] = str(REPO_ROOT / "ansible" / "roles")
            result = subprocess.run(
                ["ansible-playbook", str(playbook)],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            unit = (unit_dir / systemd_units.fortress_systemd_mount_unit(mount_root / "media")).read_text()
            self.assertIn("Options=nfsvers=4.2,soft,_netdev,rw", unit)
