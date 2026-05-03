from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import sys

from ansible.errors import AnsibleParserError
from ansible.plugins.inventory import BaseInventoryPlugin

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fortress_inventory.model import load_inventory_tree


DOCUMENTATION = r"""
name: fortress
plugin_type: inventory
short_description: Load fortress per-Entity YAML Inventory
description:
  - Reads inventory/{hosts,vms,services,templates}/ from a repository or fixture root.
  - Builds proxmox_hosts, vms, and vms_on_<host> groups.
options:
  plugin:
    description: Token that ensures this is a fortress inventory source.
    required: true
    choices: ["fortress"]
  root:
    description: Repository or fixture root. Relative paths resolve from the inventory source file.
    required: false
    default: "."
"""


class InventoryModule(BaseInventoryPlugin):
    NAME = "fortress"

    def verify_file(self, path):
        return super().verify_file(path) and path.endswith((".yaml", ".yml"))

    def parse(self, inventory, loader, path, cache=True):
        super().parse(inventory, loader, path, cache)
        config = self._read_config_data(path)
        if config.get("plugin") != self.NAME:
            raise AnsibleParserError(f"{path} is not a fortress inventory source")

        root = Path(config.get("root", "."))
        if not root.is_absolute():
            root = Path(path).resolve().parent / root
        model = load_inventory_tree(root)

        self.inventory.add_group("proxmox_hosts")
        self.inventory.add_group("vms")

        for host_name, host in model.hosts.items():
            self.inventory.add_host(host_name, "proxmox_hosts")
            self.inventory.set_variable(host_name, "fortress_entity_kind", "Host")
            self.inventory.set_variable(host_name, "fortress_host", host)
            self._set_sibling_ssh_key_var(host_name, root / "inventory" / "hosts" / f"{host_name}.sops.yaml")

        for vm_name, vm in model.vms.items():
            self.inventory.add_host(vm_name, "vms")
            self.inventory.set_variable(vm_name, "fortress_entity_kind", "VM")
            self.inventory.set_variable(vm_name, "fortress_vm", vm)
            self._set_sibling_ssh_key_var(vm_name, root / "inventory" / "vms" / f"{vm_name}.sops.yaml")
            placement_host = vm.get("placement", {}).get("host")
            if placement_host:
                group_name = f"vms_on_{placement_host}"
                self.inventory.add_group(group_name)
                self.inventory.add_host(vm_name, group_name)

        self.inventory.set_variable("all", "fortress_globals", model.globals)
        self.inventory.set_variable("all", "fortress_services", model.services)
        self.inventory.set_variable("all", "fortress_templates", model.templates)

    def _set_sibling_ssh_key_var(self, entity_name, sops_path):
        if not sops_path.is_file():
            return
        key_dir = Path(os.environ.get("FORTRESS_KEY_DIR", "/dev/shm/fortress"))
        key_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        key_path = key_dir / f"{entity_name}.key"
        result = subprocess.run(
            ["sops", "--decrypt", "--extract", '["ssh_root_key"]["private_key"]', str(sops_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            raise AnsibleParserError(f"failed to decrypt {sops_path}: {result.stderr.strip()}")
        key_path.write_text(result.stdout)
        key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        self.inventory.set_variable(entity_name, "ansible_ssh_private_key_file", str(key_path))
