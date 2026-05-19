import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class VMBaselineCollectorsRoleTests(unittest.TestCase):
    def test_ordinary_vm_gets_default_alloy_log_config_for_observability_vm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self._run_collectors_playbook(root)

            self.assertEqual(result.returncode, 0, result.stderr)
            config = (root / "etc" / "alloy" / "config.alloy").read_text()
            self.assertIn('fortress_vm = "media01"', config)
            self.assertIn('hostname = "media01"', config)
            self.assertIn('url = "http://10.40.0.17:3100/loki/api/v1/push"', config)
            self.assertIn('loki.source.journal "systemd"', config)

    def test_vm_instrumentation_opt_out_skips_baseline_collectors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self._run_collectors_playbook(root, instrumentation_enabled=False)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / "etc" / "alloy" / "config.alloy").exists())

    def test_non_ordinary_vm_without_vm_instrumentation_is_not_default_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self._run_collectors_playbook(root, lifecycle_kind="operational")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / "etc" / "alloy" / "config.alloy").exists())

    def test_reapplying_baseline_collectors_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = self._run_collectors_playbook(root)
            second = self._run_collectors_playbook(root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("changed=0", second.stdout)

    def test_baseline_collectors_plan_installs_and_enables_node_exporter_and_alloy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self._run_collectors_playbook(
                root,
                extra_args=["--list-tasks"],
                manage_packages=True,
                manage_services=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Install node exporter and Grafana Alloy", result.stdout)
            self.assertIn("Enable and start node exporter and Grafana Alloy", result.stdout)

    def _run_collectors_playbook(
        self,
        root,
        instrumentation_enabled=None,
        lifecycle_kind="ordinary",
        extra_args=None,
        manage_packages=False,
        manage_services=False,
    ):
        inventory = root / "inventory.yaml"
        playbook = root / "playbook.yml"
        (root / "etc" / "alloy").mkdir(parents=True, exist_ok=True)
        instrumentation_yaml = ""
        if instrumentation_enabled is not None:
            instrumentation_yaml = (
                "        instrumentation:\n"
                f"          enabled: {str(instrumentation_enabled).lower()}\n"
            )
        lifecycle_yaml = ""
        if lifecycle_kind != "ordinary":
            lifecycle_yaml = (
                "        lifecycle:\n"
                f"          kind: {lifecycle_kind}\n"
            )
        inventory.write_text(
            "all:\n"
            "  hosts:\n"
            "    media01:\n"
            "      ansible_connection: local\n"
            f"      ansible_python_interpreter: {sys.executable}\n"
            "      fortress_entity_kind: VM\n"
            "      fortress_vm:\n"
            "        cloud_init:\n"
            "          hostname: media01\n"
            f"{lifecycle_yaml}"
            f"{instrumentation_yaml}"
            "    observability-vm:\n"
            "      ansible_connection: local\n"
            "      ansible_host: 10.40.0.17\n"
            "  vars:\n"
            "    fortress_services:\n"
            "      observability:\n"
            "        backend:\n"
            "          vm: observability-vm\n"
        )
        playbook.write_text(
            "- name: Apply VM baseline collectors\n"
            "  hosts: media01\n"
            "  gather_facts: false\n"
            "  become: false\n"
            "  vars:\n"
            f"    fortress_vm_baseline_collectors_alloy_config_dir: {root / 'etc' / 'alloy'}\n"
            f"    fortress_vm_baseline_collectors_alloy_config_path: {root / 'etc' / 'alloy' / 'config.alloy'}\n"
            f"    fortress_vm_baseline_collectors_manage_packages: {str(manage_packages).lower()}\n"
            f"    fortress_vm_baseline_collectors_manage_services: {str(manage_services).lower()}\n"
            "  roles:\n"
            "    - vm_baseline_collectors\n"
        )
        env = os.environ.copy()
        env["ANSIBLE_ROLES_PATH"] = str(REPO_ROOT / "ansible" / "roles")
        command = ["ansible-playbook", "-i", str(inventory), str(playbook)]
        if extra_args:
            command.extend(extra_args)
        return subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
