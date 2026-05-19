import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class InstrumentationConvergenceWorkflowTests(unittest.TestCase):
    def test_just_instrumentation_converge_calls_workflow_script(self):
        justfile = (REPO_ROOT / "justfile").read_text()

        self.assertIn("instrumentation-converge:", justfile)
        self.assertIn("./scripts/instrumentation-converge", justfile)

    def test_instrumentation_converge_configures_instrumented_vms_then_refreshes_observability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "instrumentation-converge")],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                [
                    "vm-configure app-vm",
                    "vm-configure observability-vm",
                    "service-update observability --auto-confirm",
                ],
                calls_log.read_text().splitlines(),
            )

    def test_instrumentation_converge_skips_opted_out_and_non_ordinary_vms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            (root / "inventory" / "vms" / "opted-out-vm.yaml").write_text(
                "vmid: 103\n"
                "instrumentation:\n"
                "  enabled: false\n"
            )
            (root / "inventory" / "vms" / "verification-vm.yaml").write_text(
                "vmid: 104\n"
                "lifecycle:\n"
                "  kind: operational\n"
            )
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "instrumentation-converge")],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                [
                    "vm-configure app-vm",
                    "vm-configure observability-vm",
                    "service-update observability --auto-confirm",
                ],
                calls_log.read_text().splitlines(),
            )

    def test_instrumentation_converge_stops_and_reports_the_failed_phase(self):
        scenarios = {
            "vm-configure app-vm": (
                "VM Configure failed for VM app-vm",
                ["vm-configure app-vm"],
            ),
            "vm-configure observability-vm": (
                "VM Configure failed for VM observability-vm",
                ["vm-configure app-vm", "vm-configure observability-vm"],
            ),
            "service-update observability --auto-confirm": (
                "Observability Service Update failed",
                [
                    "vm-configure app-vm",
                    "vm-configure observability-vm",
                    "service-update observability --auto-confirm",
                ],
            ),
        }

        for failed_call, (message, expected_calls) in scenarios.items():
            with self.subTest(failed_call=failed_call), tempfile.TemporaryDirectory() as tmp:
                root, calls_log = self._workflow_fixture(tmp)
                env = self._workflow_env(root, calls_log)
                env["FORTRESS_FAIL_CALL"] = failed_call

                result = subprocess.run(
                    [str(REPO_ROOT / "scripts" / "instrumentation-converge")],
                    cwd=REPO_ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                self.assertEqual(result.returncode, 42)
                self.assertIn(message, result.stderr)
                self.assertEqual(expected_calls, calls_log.read_text().splitlines())

    def _workflow_fixture(self, tmp):
        root = Path(tmp)
        (root / "inventory" / "services").mkdir(parents=True)
        (root / "inventory" / "vms").mkdir(parents=True)
        (root / "scripts").mkdir()
        (root / "inventory" / "vms" / "app-vm.yaml").write_text("vmid: 101\n")
        (root / "inventory" / "vms" / "observability-vm.yaml").write_text("vmid: 102\n")
        (root / "inventory" / "services" / "observability.yaml").write_text(
            "name: observability\n"
            "backend:\n"
            "  vm: observability-vm\n"
            "  port: 3000\n"
            "deploy:\n"
            "  type: quadlet\n"
            "  containers:\n"
            "    - name: prometheus\n"
            "      image: example.invalid/prometheus:1\n"
        )
        calls_log = root / "calls.log"
        for name in ["vm-configure", "service-update"]:
            script = root / "scripts" / name
            script.write_text(
                "#!/usr/bin/env bash\n"
                "name=$(basename \"$0\")\n"
                "call=\"$name\"\n"
                "if [ \"$#\" -gt 0 ]; then call=\"$call $*\"; fi\n"
                "printf '%s' \"$name\" >> \"$CALLS_LOG\"\n"
                "if [ \"$#\" -gt 0 ]; then printf ' %s' \"$*\" >> \"$CALLS_LOG\"; fi\n"
                "printf '\\n' >> \"$CALLS_LOG\"\n"
                "if [ \"$FORTRESS_FAIL_CALL\" = \"$call\" ]; then exit 42; fi\n"
                "if [ \"$FORTRESS_FAIL_PHASE\" = \"$name\" ]; then exit 42; fi\n"
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
