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

    def test_inventory_plugin_exposes_datasets_to_ansible(self):
        inventory = self.load_inventory()
        media01 = ansible_value(inventory["_meta"]["hostvars"]["media01"])

        self.assertEqual(media01["fortress_datasets"]["media"]["name"], "media")

    def test_inventory_plugin_exposes_nas_endpoints_to_ansible(self):
        inventory = self.load_inventory()
        media01 = ansible_value(inventory["_meta"]["hostvars"]["media01"])

        self.assertEqual(media01["fortress_nas_endpoints"]["truenas"]["share_address"], "10.0.20.10")

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
                "printf '%s\\n' \"$*\" >> \"$SOPS_LOG\"\n"
                "printf '%s' 'OPENSSH PRIVATE KEY'\n"
            )
            fake_sops.chmod(fake_sops.stat().st_mode | stat.S_IXUSR)
            key_dir = root / "tmpfs"

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
            env["FORTRESS_KEY_DIR"] = str(key_dir)
            env["SOPS_LOG"] = str(root / "sops.log")

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
            self.assertIn('["ssh_keys"]["bootstrap"]["private_key"]', (root / "sops.log").read_text())

    def test_inventory_plugin_exposes_sibling_sops_bootstrap_public_key_as_hostvar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vm_dir = root / "inventory" / "vms"
            vm_dir.mkdir(parents=True)
            (root / "inventory" / "hosts").mkdir()
            (root / "inventory" / "services").mkdir()
            (root / "inventory" / "templates").mkdir()
            (root / "inventory" / "group_vars").mkdir()
            (root / "fortress.yaml").write_text("plugin: fortress\nroot: .\n")
            (vm_dir / "tmp-template-verify.yaml").write_text(
                "vmid: 8901\n"
                "placement:\n"
                "  host: wintermute\n"
                "source:\n"
                "  template: debian-12-base\n"
                "hardware:\n"
                "  cores: 1\n"
                "  memory: 1024\n"
                "cloud_init:\n"
                "  hostname: tmp-template-verify\n"
                "ssh_public_key: ssh-ed25519 vm-yaml-key\n"
            )
            (vm_dir / "tmp-template-verify.sops.yaml").write_text("encrypted: value\n")

            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_sops = bin_dir / "sops"
            fake_sops.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$*\" >> \"$SOPS_LOG\"\n"
                "case \"$*\" in\n"
                "  *'public_key'* ) printf '%s' 'ssh-ed25519 sops-public-key' ;;\n"
                "  *'private_key'* ) printf '%s' 'OPENSSH PRIVATE KEY' ;;\n"
                "esac\n"
            )
            fake_sops.chmod(fake_sops.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
            env["FORTRESS_KEY_DIR"] = str(root / "tmpfs")
            env["SOPS_LOG"] = str(root / "sops.log")

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

            self.assertEqual(
                hostvars["tmp-template-verify"]["fortress_sibling_ssh_keys"]["bootstrap"]["public_key"],
                "ssh-ed25519 sops-public-key",
            )
            self.assertIn('["ssh_keys"]["bootstrap"]["public_key"]', (root / "sops.log").read_text())

    def test_inventory_plugin_uses_existing_tmpfs_key_without_decrypting_again(self):
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
            key_dir = root / "tmpfs"
            key_dir.mkdir()
            (key_dir / "wintermute.key").write_text("PREDECRYPTED KEY")

            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_sops = bin_dir / "sops"
            sops_log = root / "sops.log"
            fake_sops.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$*\" >> \"$SOPS_LOG\"\n"
                "case \"$*\" in\n"
                "  *'public_key'* ) printf '%s' 'ssh-ed25519 existing-public-key' ;;\n"
                "  *'private_key'* ) exit 9 ;;\n"
                "esac\n"
            )
            fake_sops.chmod(fake_sops.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
            env["FORTRESS_KEY_DIR"] = str(key_dir)
            env["SOPS_LOG"] = str(sops_log)

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
            self.assertIn('["ssh_keys"]["bootstrap"]["public_key"]', sops_log.read_text())
            self.assertNotIn('["ssh_keys"]["bootstrap"]["private_key"]', sops_log.read_text())

    def test_inventory_plugin_sets_host_connection_from_management_address(self):
        inventory = self.load_inventory()
        wintermute = ansible_value(inventory["_meta"]["hostvars"]["wintermute"])

        self.assertEqual(wintermute["ansible_host"], "10.0.0.10")
        self.assertEqual(wintermute["ansible_user"], "root")
        self.assertIn("StrictHostKeyChecking=accept-new", wintermute["ansible_ssh_common_args"])

    def test_inventory_plugin_sets_vm_connection_from_inventory(self):
        inventory = self.load_inventory()
        media01 = ansible_value(inventory["_meta"]["hostvars"]["media01"])

        self.assertEqual(media01["ansible_host"], "10.0.10.101")
        self.assertEqual(media01["ansible_user"], "admin")
        self.assertIn("StrictHostKeyChecking=accept-new", media01["ansible_ssh_common_args"])
