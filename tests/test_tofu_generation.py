import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"


class TofuGenerationTests(unittest.TestCase):
    def test_generates_literal_provider_aliases_from_host_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "hosts" / "neuromancer.yaml").write_text(
                "proxmox:\n"
                "  pve_node_name: pve-neuromancer\n"
                "network:\n"
                "  management_address: 10.0.0.11\n"
            )

            subprocess.run(
                [str(REPO_ROOT / "scripts" / "tofu-generate"), str(root)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            providers = (root / "tofu" / "generated-providers.tf").read_text()
            self.assertIn('provider "proxmox" {', providers)
            self.assertRegex(providers, r'alias\s*=\s*"wintermute"')
            self.assertRegex(providers, r'alias\s*=\s*"neuromancer"')
            self.assertIn('variable "pve_token_wintermute"', providers)
            self.assertRegex(
                providers,
                r'variable "pve_token_wintermute" \{[^}]*sensitive\s*=\s*true',
            )
            self.assertRegex(
                providers,
                r'variable "pve_token_neuromancer" \{[^}]*sensitive\s*=\s*true',
            )

    def test_fails_when_vm_placement_has_no_generated_host_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_invalid" / "missing-vm-host", root, dirs_exist_ok=True)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "tofu-generate"), str(root)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing_host_provider", result.stderr)
            self.assertIn("media01", result.stderr)
            self.assertIn("missing-host", result.stderr)

    def test_generates_static_vm_partition_per_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)

            subprocess.run(
                [str(REPO_ROOT / "scripts" / "tofu-generate"), str(root)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            partitions = (root / "tofu" / "generated-vm-partitions.tf").read_text()
            self.assertIn('module "vms_wintermute"', partitions)
            self.assertIn('if vm.placement.host == "wintermute"', partitions)
            self.assertIn("proxmox = proxmox.wintermute", partitions)
            self.assertNotIn("proxmox[", partitions)

    def test_root_tofu_module_decodes_vm_inventory_yaml(self):
        root_module = (REPO_ROOT / "tofu" / "main.tf").read_text()

        self.assertIn('fileset("../inventory/vms", "*.yaml")', root_module)
        self.assertIn("yamldecode(", root_module)
        self.assertIn("vms = {", root_module)

    def test_generated_tofu_outputs_and_local_state_are_ignored(self):
        gitignore = (REPO_ROOT / ".gitignore").read_text()

        for pattern in [
            "tofu/generated-providers.tf",
            "tofu/generated-vm-partitions.tf",
            "tofu/.terraform/",
            "tofu/.terraform.lock.hcl",
            "tofu/*.tfstate",
            "tofu/*.tfstate.backup",
        ]:
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, gitignore)

    def test_provider_generation_strategy_is_documented(self):
        docs = (REPO_ROOT / "docs" / "opentofu.md").read_text()

        self.assertIn("generated-providers.tf", docs)
        self.assertIn("generated-vm-partitions.tf", docs)
        self.assertIn("proxmox[each.value.host]", docs)
        self.assertIn("provider aliases must be literal", docs)
