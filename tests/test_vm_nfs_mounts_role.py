import subprocess
import tempfile
import unittest
from pathlib import Path
import os


REPO_ROOT = Path(__file__).resolve().parents[1]


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
                "        server: 10.0.20.10\n"
                "        default_options: [nfsvers=4.2, soft, _netdev]\n"
                "        exports:\n"
                "          media: /mnt/pool/media\n"
                "    fortress_vm:\n"
                "      nfs_mounts:\n"
                "        - export: media\n"
                f"          mount_point: {mount_root / 'media'}\n"
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
            self.assertTrue((mount_root / "media").is_dir())
            unit = (unit_dir / f"{str(mount_root / 'media').strip('/').replace('/', '-')}.mount").read_text()
            self.assertIn("What=10.0.20.10:/mnt/pool/media", unit)
            self.assertIn(f"Where={mount_root / 'media'}", unit)
            self.assertIn("Type=nfs", unit)
            self.assertIn("Options=nfsvers=4.2,soft,_netdev,x-systemd.automount", unit)
            self.assertIn("WantedBy=multi-user.target", unit)

    def test_role_installs_nfs_client_utilities(self):
        tasks = (REPO_ROOT / "ansible" / "roles" / "vm_nfs_mounts" / "tasks" / "main.yml").read_text()

        self.assertIn("ansible.builtin.apt", tasks)
        self.assertIn("name: nfs-common", tasks)
