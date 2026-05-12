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
            self.assertIn('endpoint  = "https://10.0.0.11:8006"', providers)
            self.assertIn("insecure  = true", providers)
            self.assertIn('variable "pve_token_wintermute"', providers)
            self.assertIn('variable "pve_ssh_private_key_wintermute"', providers)
            self.assertIn('username    = "root"', providers)
            self.assertIn('address = "10.0.0.11"', providers)
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

    def test_selected_vm_generation_includes_only_that_vms_host(self):
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
                [str(REPO_ROOT / "scripts" / "tofu-generate"), str(root), "--selected-vm", "media01"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            providers = (root / "tofu" / "generated-providers.tf").read_text()
            partitions = (root / "tofu" / "generated-vm-partitions.tf").read_text()
            self.assertIn('alias     = "wintermute"', providers)
            self.assertNotIn("neuromancer", providers)
            self.assertIn('module "vms_wintermute"', partitions)
            self.assertNotIn("vms_neuromancer", partitions)

    def test_selected_vm_generation_can_include_extra_provider_hosts_for_existing_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "hosts" / "straylight.yaml").write_text(
                "proxmox:\n"
                "  pve_node_name: pve-straylight\n"
                "network:\n"
                "  management_address: 10.0.0.12\n"
            )

            subprocess.run(
                [
                    str(REPO_ROOT / "scripts" / "tofu-generate"),
                    str(root),
                    "--selected-vm",
                    "media01",
                    "--provider-host",
                    "straylight",
                ],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            providers = (root / "tofu" / "generated-providers.tf").read_text()
            partitions = (root / "tofu" / "generated-vm-partitions.tf").read_text()
            self.assertIn('alias     = "wintermute"', providers)
            self.assertIn('alias     = "straylight"', providers)
            self.assertIn('module "vms_wintermute"', partitions)
            self.assertIn('module "vms_straylight"', partitions)
            self.assertIn('if vm_name == "media01"', partitions)

    def test_selected_vm_generation_passes_only_the_selected_vm_to_the_host_partition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "vms" / "unprepared-sibling.yaml").write_text(
                "vmid: 102\n"
                "placement:\n"
                "  host: wintermute\n"
                "source:\n"
                "  template: debian-13-base\n"
                "hardware:\n"
                "  cores: 2\n"
                "  memory: 4096\n"
                "cloud_init:\n"
                "  hostname: unprepared-sibling\n"
            )

            subprocess.run(
                [str(REPO_ROOT / "scripts" / "tofu-generate"), str(root), "--selected-vm", "media01"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            partitions = (root / "tofu" / "generated-vm-partitions.tf").read_text()
            self.assertIn('if vm_name == "media01"', partitions)
            self.assertNotIn('if vm.placement.host == "wintermute"', partitions)

    def test_root_tofu_module_decodes_vm_inventory_yaml(self):
        root_module = (REPO_ROOT / "tofu" / "main.tf").read_text()

        self.assertIn('fileset("../inventory/vms", "*.yaml")', root_module)
        self.assertIn("yamldecode(", root_module)
        self.assertIn("vms = {", root_module)
        self.assertNotIn("vms = tomap({", root_module)

    def test_root_tofu_module_keeps_host_sibling_vms_in_configuration(self):
        root_module = (REPO_ROOT / "tofu" / "main.tf").read_text()
        partitions = (REPO_ROOT / "fortress_tofu" / "generate.py").read_text()

        self.assertIn('variable "selected_vm"', root_module)
        self.assertIn("globals = yamldecode", root_module)
        self.assertIn("vms = {", root_module)
        self.assertNotIn("if var.selected_vm == null || vm_name == var.selected_vm", root_module)
        self.assertIn("local.vms", partitions)
        self.assertNotIn("local.selected_vms", partitions)
        self.assertIn("admin_user    = local.globals.vm_admin_user", partitions)
        self.assertIn('!endswith(basename(path), ".sops.yaml")', root_module)
        self.assertNotIn("vms = tomap({", root_module)

    def test_vm_partition_declares_proxmox_vm_resources_from_vm_yaml(self):
        module = (REPO_ROOT / "tofu" / "modules" / "vm-partition" / "main.tf").read_text()

        self.assertIn('resource "proxmox_virtual_environment_vm" "vm"', module)
        self.assertIn("for_each = var.vms", module)
        self.assertIn("vm_id     = each.value.vmid", module)
        self.assertIn("node_name = var.pve_node_name", module)
        self.assertIn("vm_id = var.templates[each.value.source.template].vmid", module)
        self.assertIn("cores = each.value.hardware.cores", module)
        self.assertIn("dedicated = each.value.hardware.memory", module)
        self.assertIn("variable \"admin_user\"", module)
        self.assertIn("type = any", module)
        self.assertIn("name: ${var.admin_user}", module)
        self.assertIn("each.value.ssh_public_key", module)
        self.assertIn("run Prepare first", module)

    def test_vm_partition_attaches_cloud_init_on_scsi_for_q35_ovmf_templates(self):
        module = (REPO_ROOT / "tofu" / "modules" / "vm-partition" / "main.tf").read_text()

        self.assertRegex(module, r"interface\s*=\s*local\.vm_cloud_init_interfaces\[each\.key\]")
        self.assertIn('startswith(local.vm_cloud_init_interfaces[each.key], "scsi")', module)

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
