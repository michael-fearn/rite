import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class VMUpWorkflowTests(unittest.TestCase):
    def test_just_vm_up_calls_workflow_script(self):
        justfile = (REPO_ROOT / "justfile").read_text()

        self.assertIn("vm-up vm:", justfile)
        self.assertIn("./scripts/vm-up {{vm}}", justfile)

    def test_vm_up_rejects_undeclared_vms_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "inventory" / "vms").mkdir(parents=True)
            calls_log = root / "calls.log"
            env = os.environ.copy()
            env["FORTRESS_ROOT"] = str(root)
            env["CALLS_LOG"] = str(calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "vm-up"), "ghost"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                input="apply ghost\n",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("VM 'ghost' is not declared", result.stderr)
            self.assertFalse(calls_log.exists())

    def test_vm_up_runs_prepare_selected_plan_apply_then_configure_after_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "vm-up"), "media01"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                input="apply media01\n",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                [
                    "vm-prepare media01",
                    "tofu-wrap plan -var selected_vm=media01",
                    "tofu-wrap apply -var selected_vm=media01 -auto-approve",
                    "vm-configure media01",
                ],
                calls_log.read_text().splitlines(),
            )

    def test_vm_up_denies_apply_without_explicit_matching_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "vm-up"), "media01"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                input="yes\n",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("Apply denied for VM media01", result.stderr)
            self.assertEqual(
                [
                    "vm-prepare media01",
                    "tofu-wrap plan -var selected_vm=media01",
                ],
                calls_log.read_text().splitlines(),
            )

    def test_vm_up_stops_and_reports_the_failed_phase(self):
        scenarios = {
            "vm-prepare": (
                "Prepare failed for VM media01",
                ["vm-prepare media01"],
            ),
            "tofu-plan": (
                "tofu plan failed for VM media01",
                ["vm-prepare media01", "tofu-wrap plan -var selected_vm=media01"],
            ),
            "tofu-apply": (
                "tofu apply failed for VM media01",
                [
                    "vm-prepare media01",
                    "tofu-wrap plan -var selected_vm=media01",
                    "tofu-wrap apply -var selected_vm=media01 -auto-approve",
                ],
            ),
            "vm-configure": (
                "Configure failed for VM media01",
                [
                    "vm-prepare media01",
                    "tofu-wrap plan -var selected_vm=media01",
                    "tofu-wrap apply -var selected_vm=media01 -auto-approve",
                    "vm-configure media01",
                ],
            ),
        }

        for failed_phase, (message, expected_calls) in scenarios.items():
            with self.subTest(failed_phase=failed_phase), tempfile.TemporaryDirectory() as tmp:
                root, calls_log = self._workflow_fixture(tmp)
                env = self._workflow_env(root, calls_log)
                env["FORTRESS_FAIL_PHASE"] = failed_phase

                result = subprocess.run(
                    [str(REPO_ROOT / "scripts" / "vm-up"), "media01"],
                    cwd=REPO_ROOT,
                    env=env,
                    text=True,
                    input="apply media01\n",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                self.assertEqual(result.returncode, 42)
                self.assertIn(message, result.stderr)
                self.assertEqual(expected_calls, calls_log.read_text().splitlines())

    def test_vm_up_reports_missing_phase_command_as_failed_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _calls_log = self._workflow_fixture(tmp)
            (root / "scripts" / "vm-prepare").unlink()
            env = self._workflow_env(root, root / "calls.log")

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "vm-up"), "media01"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                input="apply media01\n",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("Prepare failed for VM media01", result.stderr)

    def _workflow_fixture(self, tmp):
        root = Path(tmp)
        vm_dir = root / "inventory" / "vms"
        scripts_dir = root / "scripts"
        vm_dir.mkdir(parents=True)
        scripts_dir.mkdir()
        (vm_dir / "media01.yaml").write_text(
            "vmid: 101\n"
            "placement:\n"
            "  host: wintermute\n"
        )
        calls_log = root / "calls.log"
        for name in ["vm-prepare", "tofu-wrap", "vm-configure"]:
            script = scripts_dir / name
            script.write_text(
                "#!/usr/bin/env bash\n"
                "name=$(basename \"$0\")\n"
                "printf '%s %s\\n' \"$name\" \"$*\" >> \"$CALLS_LOG\"\n"
                "phase=\"$name\"\n"
                "if [ \"$name\" = tofu-wrap ]; then phase=\"tofu-$1\"; fi\n"
                "if [ \"$FORTRESS_FAIL_PHASE\" = \"$phase\" ]; then exit 42; fi\n"
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
