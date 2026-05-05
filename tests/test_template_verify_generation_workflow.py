import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class TemplateVerifyGenerationWorkflowTests(unittest.TestCase):
    def test_generates_concrete_template_verification_vm_after_real_template_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._fixture(tmp)
            env = self._fake_tools(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "template-verify-generate"), "wintermute", "debian-12-base"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            calls = calls_log.read_text()
            self.assertIn("sops --decrypt --extract", calls)
            self.assertIn("ssh -i ", calls)
            self.assertIn("root@10.10.0.11 qm config 9001", calls)
            self.assertIn("ssh-keygen -t ed25519", calls)
            self.assertIn("sops --encrypt --config", calls)

            vm_yaml = (root / "inventory" / "vms" / "tmp-template-verify.yaml").read_text()
            self.assertIn("vmid: 8901", vm_yaml)
            self.assertIn("kind: operational", vm_yaml)
            self.assertIn("purpose: template-verification", vm_yaml)
            self.assertIn("generated: true", vm_yaml)
            self.assertIn("host: wintermute", vm_yaml)
            self.assertIn("template: debian-12-base", vm_yaml)
            self.assertIn("cores: 1", vm_yaml)
            self.assertIn("memory: 1024", vm_yaml)
            self.assertIn("storage: fast", vm_yaml)
            self.assertIn("size: 8G", vm_yaml)
            self.assertIn("bridge: vmbr0", vm_yaml)
            self.assertIn("address: 10.10.0.221/24", vm_yaml)
            self.assertIn("gateway: 10.10.0.1", vm_yaml)
            self.assertIn("hostname: tmp-template-verify", vm_yaml)
            self.assertIn("enabled: false", vm_yaml)
            self.assertIn("ssh_public_key: ssh-ed25519 verify-public tmp-template-verify", vm_yaml)

            vm_sops = root / "inventory" / "vms" / "tmp-template-verify.sops.yaml"
            self.assertEqual("encrypted template verify sops\n", vm_sops.read_text())
            plaintext_sops = (root / "template-verify-plaintext.sops.yaml").read_text()
            self.assertIn("ssh_keys:\n", plaintext_sops)
            self.assertIn("  bootstrap:\n", plaintext_sops)
            self.assertIn("    type: vm_ssh\n", plaintext_sops)
            self.assertIn("    public_key: ssh-ed25519 verify-public tmp-template-verify\n", plaintext_sops)
            self.assertIn("    private_key: |\n", plaintext_sops)

    def test_refuses_when_generated_vm_inventory_already_exists_before_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._fixture(tmp)
            (root / "inventory" / "vms" / "tmp-template-verify.yaml").write_text("existing\n")
            env = self._fake_tools(root, calls_log)

            result = self._run_generate(root, env)

            self.assertEqual(result.returncode, 1)
            self.assertIn("tmp-template-verify.yaml already exists", result.stderr)
            self.assertFalse(calls_log.exists())

    def test_refuses_when_generated_sibling_sops_file_already_exists_before_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._fixture(tmp)
            (root / "inventory" / "vms" / "tmp-template-verify.sops.yaml").write_text("existing\n")
            env = self._fake_tools(root, calls_log)

            result = self._run_generate(root, env)

            self.assertEqual(result.returncode, 1)
            self.assertIn("tmp-template-verify.sops.yaml already exists", result.stderr)
            self.assertFalse(calls_log.exists())

    def test_missing_host_template_and_host_template_declaration_fail_before_preflight(self):
        scenarios = {
            "missing-host": ("ghost", "debian-12-base", "Host 'ghost' is not declared"),
            "missing-template": ("wintermute", "ubuntu-24-base", "Template 'ubuntu-24-base' is not declared"),
            "not-declared-on-host": ("wintermute", "debian-12-base", "does not declare Template debian-12-base"),
        }

        for scenario, (host, template, message) in scenarios.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                root, calls_log = self._fixture(tmp)
                if scenario == "not-declared-on-host":
                    (root / "inventory" / "hosts" / "wintermute.yaml").write_text(
                        (root / "inventory" / "hosts" / "wintermute.yaml")
                        .read_text()
                        .replace("templates: [debian-12-base]", "templates: []")
                    )
                env = self._fake_tools(root, calls_log)

                result = subprocess.run(
                    [str(REPO_ROOT / "scripts" / "template-verify-generate"), host, template],
                    cwd=REPO_ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)
                self.assertFalse(calls_log.exists())
                self.assertFalse((root / "inventory" / "vms" / "tmp-template-verify.yaml").exists())
                self.assertFalse((root / "inventory" / "vms" / "tmp-template-verify.sops.yaml").exists())

    def test_missing_policy_entries_fail_before_preflight(self):
        scenarios = {
            "storage_by_host:\n  wintermute: fast\n": "storage_by_host entry for Host wintermute",
            "address_by_host:\n  wintermute: 10.10.0.221/24\n": "address_by_host entry for Host wintermute",
        }

        for removed_block, message in scenarios.items():
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmp:
                root, calls_log = self._fixture(tmp)
                policy_path = root / "inventory" / "template-verification-policy.yaml"
                policy_path.write_text(policy_path.read_text().replace(removed_block, ""))
                env = self._fake_tools(root, calls_log)

                result = self._run_generate(root, env)

                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)
                self.assertFalse(calls_log.exists())
                self.assertFalse((root / "inventory" / "vms" / "tmp-template-verify.yaml").exists())

    def test_bridge_derivation_requires_exactly_one_matching_management_cidr_with_gateway(self):
        scenarios = {
            "missing-match": (
                "      cidr: 10.10.0.11/24\n",
                "      cidr: 10.20.0.11/24\n",
                "must match exactly one Host bridge CIDR; found 0",
            ),
            "ambiguous-match": (
                "      gateway: 10.10.0.1\n",
                "      gateway: 10.10.0.1\n"
                "    - name: vmbr1\n"
                "      cidr: 10.10.0.99/24\n"
                "      gateway: 10.10.0.1\n",
                "must match exactly one Host bridge CIDR; found 2",
            ),
            "missing-gateway": (
                "      gateway: 10.10.0.1\n",
                "",
                "has no gateway",
            ),
        }

        for scenario, (old, new, message) in scenarios.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                root, calls_log = self._fixture(tmp)
                host_path = root / "inventory" / "hosts" / "wintermute.yaml"
                host_path.write_text(host_path.read_text().replace(old, new))
                env = self._fake_tools(root, calls_log)

                result = self._run_generate(root, env)

                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)
                self.assertFalse(calls_log.exists())
                self.assertFalse((root / "inventory" / "vms" / "tmp-template-verify.yaml").exists())

    def test_real_template_preflight_failure_does_not_write_generated_files(self):
        scenarios = {
            "absent": ("absent", "is absent on Host wintermute"),
            "not-template": ("vm", "is not marked template: 1"),
        }

        for scenario, (fake_config, message) in scenarios.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                root, calls_log = self._fixture(tmp)
                env = self._fake_tools(root, calls_log)
                env["FORTRESS_FAKE_QM_CONFIG"] = fake_config

                result = self._run_generate(root, env)

                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)
                calls = calls_log.read_text()
                self.assertIn("sops --decrypt --extract", calls)
                self.assertIn("root@10.10.0.11 qm config 9001", calls)
                self.assertNotIn("ssh-keygen", calls)
                self.assertFalse((root / "inventory" / "vms" / "tmp-template-verify.yaml").exists())
                self.assertFalse((root / "inventory" / "vms" / "tmp-template-verify.sops.yaml").exists())

    def _run_generate(self, root, env):
        return subprocess.run(
            [str(REPO_ROOT / "scripts" / "template-verify-generate"), "wintermute", "debian-12-base"],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def _fixture(self, tmp):
        root = Path(tmp)
        inventory = root / "inventory"
        (inventory / "hosts").mkdir(parents=True)
        (inventory / "templates").mkdir()
        (inventory / "vms").mkdir()
        (root / ".sops.yaml").write_text("creation_rules: []\n")
        (inventory / "template-verification-policy.yaml").write_text(
            "vmid: 8901\n"
            "hardware:\n"
            "  cores: 1\n"
            "  memory: 1024\n"
            "  disk_size: 8G\n"
            "storage_by_host:\n"
            "  wintermute: fast\n"
            "address_by_host:\n"
            "  wintermute: 10.10.0.221/24\n"
        )
        (inventory / "hosts" / "wintermute.yaml").write_text(
            "proxmox:\n"
            "  pve_node_name: wintermute\n"
            "  templates: [debian-12-base]\n"
            "hardware:\n"
            "  storage:\n"
            "    - name: fast\n"
            "network:\n"
            "  management_address: 10.10.0.11\n"
            "  bridges:\n"
            "    - name: vmbr0\n"
            "      cidr: 10.10.0.11/24\n"
            "      gateway: 10.10.0.1\n"
        )
        (inventory / "hosts" / "wintermute.sops.yaml").write_text(
            "ssh_keys:\n"
            "  bootstrap:\n"
            "    private_key: ENC[AES256_GCM,data:key,iv:iv,tag:tag,type:str]\n"
        )
        (inventory / "templates" / "debian-12-base.yaml").write_text(
            "name: debian-12-base\n"
            "vmid: 9001\n"
            "source:\n"
            "  url: https://example.invalid/debian.qcow2\n"
            "  checksum:\n"
            "    algorithm: sha512\n"
            f"    value: {'a' * 128}\n"
            "hardware:\n"
            "  cores: 2\n"
            "  memory: 2048\n"
        )
        return root, root / "calls.log"

    def _fake_tools(self, root, calls_log):
        bin_dir = root / "bin"
        bin_dir.mkdir()
        tools = {
            "sops": (
                "#!/usr/bin/env bash\n"
                "printf 'sops %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
                "if [ \"$1\" = --decrypt ]; then printf '%s\\n' 'OPENSSH PRIVATE KEY'; exit 0; fi\n"
                "while [ $# -gt 0 ]; do\n"
                "  if [ \"$1\" = --output ]; then shift; output=\"$1\"; fi\n"
                "  input=\"$1\"\n"
                "  shift\n"
                "done\n"
                "cp \"$input\" \"$FORTRESS_ROOT/template-verify-plaintext.sops.yaml\"\n"
                "printf 'encrypted template verify sops\\n' > \"$output\"\n"
            ),
            "ssh": (
                "#!/usr/bin/env bash\n"
                "printf 'ssh %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
                "if [ \"$FORTRESS_FAKE_QM_CONFIG\" = absent ]; then printf 'missing\\n' >&2; exit 2; fi\n"
                "if [ \"$FORTRESS_FAKE_QM_CONFIG\" = vm ]; then printf 'template: 0\\n'; exit 0; fi\n"
                "printf 'template: 1\\n'\n"
            ),
            "ssh-keygen": (
                "#!/usr/bin/env bash\n"
                "printf 'ssh-keygen %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
                "while [ $# -gt 0 ]; do\n"
                "  if [ \"$1\" = -f ]; then shift; key_path=\"$1\"; fi\n"
                "  shift\n"
                "done\n"
                "printf 'PRIVATE KEY tmp-template-verify\\n' > \"$key_path\"\n"
                "printf 'ssh-ed25519 verify-public tmp-template-verify\\n' > \"$key_path.pub\"\n"
            ),
        }
        for name, body in tools.items():
            tool = bin_dir / name
            tool.write_text(body)
            tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        env["FORTRESS_ROOT"] = str(root)
        env["CALLS_LOG"] = str(calls_log)
        return env


if __name__ == "__main__":
    unittest.main()
