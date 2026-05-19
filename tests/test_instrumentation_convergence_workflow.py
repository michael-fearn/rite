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

    def test_instrumentation_converge_skips_inventory_vms_absent_from_live_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp, with_live_probe=True)
            (root / "inventory" / "vms" / "stale-vm.yaml").write_text(
                "vmid: 103\n"
                "placement:\n"
                "  host: wintermute\n"
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
            self.assertIn("Skipping VM stale-vm: VMID 103 is absent on Host wintermute", result.stdout)
            self.assertEqual(
                [
                    "vm-configure app-vm",
                    "vm-configure observability-vm",
                    "service-update observability --auto-confirm excluded=stale-vm",
                ],
                calls_log.read_text().splitlines(),
            )

    def test_instrumentation_converge_refreshes_current_generated_observability_view_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            self._write_service_observability_view_request(root)
            env = self._workflow_env(root, calls_log)
            env["FORTRESS_LOG_OBSERVABILITY_ARTIFACTS"] = "1"

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "instrumentation-converge")],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "generated-dashboard /srv/services/observability/grafana-dashboards/generated/service-immich-prometheus_generic.json",
                calls_log.read_text().splitlines(),
            )

            (root / "inventory" / "services" / "immich.yaml").write_text(
                (root / "inventory" / "services" / "immich.yaml")
                .read_text()
                .replace("  observability_views:\n    - profile: prometheus_generic\n", "")
            )
            calls_log.unlink()

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "instrumentation-converge")],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(
                "generated-dashboard /srv/services/observability/grafana-dashboards/generated/service-immich-prometheus_generic.json",
                calls_log.read_text().splitlines(),
            )

    def test_instrumentation_converge_omits_opted_out_vm_observability_view_on_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            (root / "inventory" / "vms" / "app-vm.yaml").write_text(
                "vmid: 101\n"
                "instrumentation:\n"
                "  enabled: false\n"
            )
            env = self._workflow_env(root, calls_log)
            env["FORTRESS_LOG_OBSERVABILITY_ARTIFACTS"] = "1"

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "instrumentation-converge")],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(
                "generated-dashboard /srv/services/observability/grafana-dashboards/generated/vm-app-vm-vm_baseline.json",
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

    def _workflow_fixture(self, tmp, with_live_probe=False):
        root = Path(tmp)
        (root / "inventory" / "hosts").mkdir(parents=True)
        (root / "inventory" / "services").mkdir(parents=True)
        (root / "inventory" / "vms").mkdir(parents=True)
        (root / "scripts").mkdir()
        if with_live_probe:
            (root / "inventory" / "hosts" / "wintermute.yaml").write_text("network:\n  management_address: 10.0.0.10\n")
            vm_placement = "placement:\n  host: wintermute\n"
        else:
            vm_placement = ""
        (root / "inventory" / "vms" / "app-vm.yaml").write_text(f"vmid: 101\n{vm_placement}")
        (root / "inventory" / "vms" / "observability-vm.yaml").write_text(f"vmid: 102\n{vm_placement}")
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
                "if [ \"$name\" = service-update ] && [ -n \"$FORTRESS_OBSERVABILITY_EXCLUDED_VMS\" ]; then printf ' excluded=%s' \"$FORTRESS_OBSERVABILITY_EXCLUDED_VMS\" >> \"$CALLS_LOG\"; fi\n"
                "printf '\\n' >> \"$CALLS_LOG\"\n"
                "if [ \"$name\" = service-update ] && [ \"$FORTRESS_LOG_OBSERVABILITY_ARTIFACTS\" = 1 ]; then\n"
                f"  PYTHONPATH={REPO_ROOT!s} python3 - \"$FORTRESS_ROOT\" \"$CALLS_LOG\" <<'PY'\n"
                "import json\n"
                "import sys\n"
                "from pathlib import Path\n"
                "from fortress_inventory.model import load_inventory_tree\n"
                "from fortress_services.deploy import quadlet_deploy_vars\n"
                "root = Path(sys.argv[1])\n"
                "calls_log = Path(sys.argv[2])\n"
                "model = load_inventory_tree(root)\n"
                "service = model.services['observability']\n"
                "vm = model.vms[service['backend']['vm']]\n"
                "deploy_vars = quadlet_deploy_vars(service, vm, inventory_root=root / 'inventory', model=model)\n"
                "with calls_log.open('a') as handle:\n"
                "    for file in deploy_vars['fortress_service_data_files']:\n"
                "        if file['path'].startswith('/srv/services/observability/grafana-dashboards/generated/'):\n"
                "            handle.write(f\"generated-dashboard {file['path']}\\n\")\n"
                "PY\n"
                "fi\n"
                "if [ \"$FORTRESS_FAIL_CALL\" = \"$call\" ]; then exit 42; fi\n"
                "if [ \"$FORTRESS_FAIL_PHASE\" = \"$name\" ]; then exit 42; fi\n"
            )
            script.chmod(script.stat().st_mode | stat.S_IXUSR)
        host_shell = root / "scripts" / "host-shell"
        host_shell.write_text(
            "#!/usr/bin/env bash\n"
            "vmid=${@: -1}\n"
            "case \"$vmid\" in\n"
            "  101|102) exit 0 ;;\n"
            "  *) echo \"Configuration file 'nodes/wintermute/qemu-server/${vmid}.conf' does not exist\" >&2; exit 2 ;;\n"
            "esac\n"
        )
        host_shell.chmod(host_shell.stat().st_mode | stat.S_IXUSR)
        return root, calls_log

    def _workflow_env(self, root, calls_log):
        env = os.environ.copy()
        env["FORTRESS_ROOT"] = str(root)
        env["CALLS_LOG"] = str(calls_log)
        return env

    def _write_service_observability_view_request(self, root):
        (root / "inventory" / "services" / "immich.yaml").write_text(
            "name: immich\n"
            "backend:\n"
            "  vm: app-vm\n"
            "  port: 2283\n"
            "instrumentation:\n"
            "  telemetry_targets:\n"
            "    - name: metrics\n"
            "      type: prometheus_metrics\n"
            "      published_port: 2283\n"
            "  observability_views:\n"
            "    - profile: prometheus_generic\n"
            "deploy:\n"
            "  type: quadlet\n"
            "  containers:\n"
            "    - name: server\n"
            "      image: example.invalid/immich:1\n"
            "      published_ports:\n"
            "        - container: 2283\n"
            "          host: 2283\n"
            "          bind: 0.0.0.0\n"
        )


if __name__ == "__main__":
    unittest.main()
