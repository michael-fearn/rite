import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def ansible_value(value):
    if isinstance(value, dict) and set(value) == {"__ansible_unsafe"}:
        return value["__ansible_unsafe"]
    if isinstance(value, dict):
        return {key: ansible_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [ansible_value(child) for child in value]
    return value


class FortressInventoryPluginTests(unittest.TestCase):
    def load_inventory(self):
        result = subprocess.run(
            [
                "ansible-inventory",
                "-i",
                "tests/fixtures/inventory_valid/fortress.yaml",
                "--list",
            ],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return json.loads(result.stdout)

    def test_inventory_plugin_builds_host_and_vm_groups(self):
        inventory = self.load_inventory()

        self.assertIn("wintermute", inventory["proxmox_hosts"]["hosts"])
        self.assertIn("media01", inventory["vms"]["hosts"])
        self.assertIn("media01", inventory["vms_on_wintermute"]["hosts"])

    def test_inventory_plugin_shapes_namespaced_hostvars(self):
        inventory = self.load_inventory()
        hostvars = inventory["_meta"]["hostvars"]
        wintermute = ansible_value(hostvars["wintermute"])
        media01 = ansible_value(hostvars["media01"])

        self.assertEqual(wintermute["fortress_entity_kind"], "Host")
        self.assertEqual(wintermute["fortress_host"]["proxmox"]["pve_node_name"], "wintermute")
        self.assertEqual(media01["fortress_entity_kind"], "VM")
        self.assertEqual(media01["fortress_vm"]["placement"]["host"], "wintermute")

    def test_inventory_plugin_materializes_sibling_sops_ssh_key_to_tmpfs_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            host_dir = root / "inventory" / "hosts"
            host_dir.mkdir(parents=True)
            (root / "inventory" / "vms").mkdir()
            (root / "inventory" / "services").mkdir()
            (root / "inventory" / "templates").mkdir()
            (root / "inventory" / "group_vars").mkdir()
            (root / "fortress.yaml").write_text("plugin: fortress\nroot: .\n")
            (host_dir / "wintermute.yaml").write_text("proxmox:\n  pve_node_name: wintermute\n")
            (host_dir / "wintermute.sops.yaml").write_text("encrypted: value\n")

            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_sops = bin_dir / "sops"
            fake_sops.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s' 'OPENSSH PRIVATE KEY'\n"
            )
            fake_sops.chmod(fake_sops.stat().st_mode | stat.S_IXUSR)
            key_dir = root / "tmpfs"

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
            env["FORTRESS_KEY_DIR"] = str(key_dir)

            result = subprocess.run(
                ["ansible-inventory", "-i", str(root / "fortress.yaml"), "--list"],
                cwd=REPO_ROOT,
                env=env,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            hostvars = ansible_value(json.loads(result.stdout)["_meta"]["hostvars"])

            self.assertEqual(hostvars["wintermute"]["ansible_ssh_private_key_file"], str(key_dir / "wintermute.key"))
            self.assertEqual((key_dir / "wintermute.key").read_text(), "OPENSSH PRIVATE KEY")
