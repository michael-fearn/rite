import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class VMDestroyWorkflowTests(unittest.TestCase):
    def test_just_vm_destroy_calls_workflow_script(self):
        justfile = (REPO_ROOT / "justfile").read_text()

        self.assertIn("vm-destroy vm:", justfile)
        self.assertIn("./scripts/vm-destroy {{vm}}", justfile)

    def test_vm_destroy_refuses_vm_referenced_by_service_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "vm-destroy"), "media01"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("VM media01 is still referenced by Service Backend(s): immich", result.stderr)
            self.assertFalse(calls_log.exists())

    def test_vm_destroy_rejects_undeclared_vms_before_tofu(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "vm-destroy"), "ghost"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("VM 'ghost' is not declared", result.stderr)
            self.assertFalse(calls_log.exists())

    def test_vm_destroy_runs_selected_vm_tofu_destroy_after_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            (root / "inventory" / "services" / "immich.yaml").unlink()
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "vm-destroy"), "media01"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                [
                    'tofu-wrap destroy -var selected_vm=media01 -target module.vms_wintermute.proxmox_virtual_environment_vm.vm["media01"] -auto-approve'
                ],
                calls_log.read_text().splitlines(),
            )

    def test_vm_destroy_preserves_vm_yaml_and_sibling_sops_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _calls_log = self._workflow_fixture(tmp)
            (root / "inventory" / "services" / "immich.yaml").unlink()
            vm_yaml = root / "inventory" / "vms" / "media01.yaml"
            vm_sops = root / "inventory" / "vms" / "media01.sops.yaml"
            original_yaml = vm_yaml.read_text()
            original_sops = vm_sops.read_text()
            env = self._workflow_env(root, root / "calls.log")

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "vm-destroy"), "media01"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(original_yaml, vm_yaml.read_text())
            self.assertEqual(original_sops, vm_sops.read_text())

    def test_docs_state_destroy_does_not_delete_inventory_files(self):
        docs = (REPO_ROOT / "docs" / "opentofu.md").read_text()

        self.assertIn("just vm-destroy", docs)
        self.assertIn("Deleting VM YAML and VM Sibling SOPS Files is separate human cleanup", docs)

    def _workflow_fixture(self, tmp):
        root = Path(tmp)
        vm_dir = root / "inventory" / "vms"
        service_dir = root / "inventory" / "services"
        scripts_dir = root / "scripts"
        vm_dir.mkdir(parents=True)
        service_dir.mkdir(parents=True)
        scripts_dir.mkdir()
        (vm_dir / "media01.yaml").write_text(
            "vmid: 101\n"
            "placement:\n"
            "  host: wintermute\n"
        )
        (vm_dir / "media01.sops.yaml").write_text("encrypted vm material\n")
        (service_dir / "immich.yaml").write_text(
            "backend:\n"
            "  vm: media01\n"
            "  port: 2283\n"
        )
        calls_log = root / "calls.log"
        script = scripts_dir / "tofu-wrap"
        script.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'tofu-wrap %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
        )
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
        return root, calls_log

    def _workflow_env(self, root, calls_log):
        env = os.environ.copy()
        env["FORTRESS_ROOT"] = str(root)
        env["CALLS_LOG"] = str(calls_log)
        return env


if __name__ == "__main__":
    unittest.main()
