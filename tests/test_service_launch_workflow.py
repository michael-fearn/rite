import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from fortress_workflows import CommandPhase
from fortress_workflows.service_launch import build_service_launch_plan


REPO_ROOT = Path(__file__).resolve().parents[1]


class ServiceLaunchWorkflowTests(unittest.TestCase):
    def test_service_launch_plan_declares_vm_lifecycle_deploy_then_ingress_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _calls_log = self._workflow_fixture(tmp)

            plan = build_service_launch_plan(root, "immich", auto_confirm=True)

            self.assertEqual("service-launch:immich", plan.id)
            self.assertEqual(
                ["vm-lifecycle", "service-deploy", "ingress-regeneration"],
                [step.id for step in plan.steps],
            )
            vm_lifecycle, service_deploy, ingress_regeneration = plan.steps
            self.assertIsInstance(vm_lifecycle, CommandPhase)
            self.assertEqual("VM Lifecycle Convergence", vm_lifecycle.display_name)
            self.assertEqual(
                [str(root / "scripts" / "vm-up"), "media01", "--auto-confirm"],
                list(vm_lifecycle.command),
            )
            self.assertIsInstance(service_deploy, CommandPhase)
            self.assertEqual("Service Deploy", service_deploy.display_name)
            self.assertEqual([str(root / "scripts" / "service-deploy"), "immich"], list(service_deploy.command))
            self.assertIsInstance(ingress_regeneration, CommandPhase)
            self.assertEqual("Ingress Regeneration", ingress_regeneration.display_name)
            self.assertEqual([str(root / "scripts" / "ingress-regenerate")], list(ingress_regeneration.command))

    def test_service_launch_plan_skips_ingress_and_does_not_pass_auto_confirm_to_deploy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _calls_log = self._workflow_fixture(tmp)
            self._write_service(root, "headless", "media01", ingress_enabled=False)

            plan = build_service_launch_plan(root, "headless", auto_confirm=False)

            self.assertEqual(["vm-lifecycle", "service-deploy"], [step.id for step in plan.steps])
            vm_lifecycle, service_deploy = plan.steps
            self.assertEqual([str(root / "scripts" / "vm-up"), "media01"], list(vm_lifecycle.command))
            self.assertEqual([str(root / "scripts" / "service-deploy"), "headless"], list(service_deploy.command))

    def test_service_launch_plan_refreshes_observability_when_service_declares_instrumentation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _calls_log = self._workflow_fixture(tmp)
            self._write_service(
                root,
                "instrumented",
                "media01",
                ingress_enabled=False,
                instrumentation_enabled=True,
            )

            plan = build_service_launch_plan(root, "instrumented", auto_confirm=True)

            self.assertEqual(
                ["vm-lifecycle", "service-deploy", "observability-refresh"],
                [step.id for step in plan.steps],
            )
            observability_refresh = plan.steps[2]
            self.assertIsInstance(observability_refresh, CommandPhase)
            self.assertEqual("Observability Refresh", observability_refresh.display_name)
            self.assertEqual(
                [str(root / "scripts" / "service-update"), "observability", "--auto-confirm"],
                list(observability_refresh.command),
            )

    def test_service_launch_plan_refreshes_observability_when_service_requests_generated_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _calls_log = self._workflow_fixture(tmp)
            self._write_service(
                root,
                "instrumented",
                "media01",
                ingress_enabled=False,
                instrumentation_enabled=True,
                observability_view_enabled=True,
            )

            plan = build_service_launch_plan(root, "instrumented", auto_confirm=True)

            self.assertEqual(
                ["vm-lifecycle", "service-deploy", "observability-refresh"],
                [step.id for step in plan.steps],
            )
            self.assertEqual(
                [str(root / "scripts" / "service-update"), "observability", "--auto-confirm"],
                list(plan.steps[2].command),
            )

    def test_just_service_launch_calls_workflow_script(self):
        justfile = (REPO_ROOT / "justfile").read_text()

        self.assertIn('service-launch service auto_confirm="false":', justfile)
        self.assertIn("./scripts/service-launch {{service}}", justfile)
        self.assertIn("--auto-confirm", justfile)
        self.assertIn('"{{auto_confirm}}" = "auto_confirm=true"', justfile)

    def test_service_launch_runs_vm_up_deploy_then_ingress_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "service-launch"), "immich", "--auto-confirm"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                [
                    "vm-up media01 --auto-confirm",
                    "service-deploy immich",
                    "ingress-regenerate",
                ],
                calls_log.read_text().splitlines(),
            )

    def test_service_launch_runs_observability_refresh_when_service_declares_instrumentation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            self._write_service(
                root,
                "instrumented",
                "media01",
                ingress_enabled=False,
                instrumentation_enabled=True,
            )
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "service-launch"), "instrumented"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                [
                    "vm-up media01",
                    "service-deploy instrumented",
                    "service-update observability --auto-confirm",
                ],
                calls_log.read_text().splitlines(),
            )

    def test_service_launch_validates_service_before_any_workflow_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "service-launch"), "ghost"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("Service 'ghost' is not declared", result.stderr)
            self.assertFalse(calls_log.exists())

    def test_service_launch_validates_backend_vm_declaration_before_any_workflow_command(self):
        scenarios = {
            "missing-backend": (
                "name: missing-backend\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: web\n"
                "      image: example.invalid/web:1\n",
                "Service 'missing-backend' has no backend.vm",
            ),
            "ghost-vm": (
                "name: ghost-vm\n"
                "backend:\n"
                "  vm: ghost\n"
                "  port: 8080\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: web\n"
                "      image: example.invalid/web:1\n",
                "Backend VM 'ghost' for Service 'ghost-vm' is not declared",
            ),
        }

        for service_name, (service_yaml, message) in scenarios.items():
            with self.subTest(service_name=service_name), tempfile.TemporaryDirectory() as tmp:
                root, calls_log = self._workflow_fixture(tmp)
                (root / "inventory" / "services" / f"{service_name}.yaml").write_text(service_yaml)
                env = self._workflow_env(root, calls_log)

                result = subprocess.run(
                    [str(REPO_ROOT / "scripts" / "service-launch"), service_name],
                    cwd=REPO_ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)
                self.assertFalse(calls_log.exists())

    def test_service_launch_skips_ingress_regenerate_when_ingress_is_not_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            self._write_service(root, "headless", "media01", ingress_enabled=False)
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "service-launch"), "headless"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                [
                    "vm-up media01",
                    "service-deploy headless",
                ],
                calls_log.read_text().splitlines(),
            )

    def test_service_launch_deploys_only_the_named_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            self._write_service(root, "photos", "media01", ingress_enabled=True)
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "service-launch"), "immich"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            calls = calls_log.read_text().splitlines()
            self.assertIn("service-deploy immich", calls)
            self.assertNotIn("service-deploy photos", calls)

    def test_service_launch_rejects_launchable_group_targets_without_running_group_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            (root / "inventory" / "vms" / "media01.yaml").write_text(
                "vmid: 101\n"
                "placement:\n"
                "  host: wintermute\n"
                "launchable_service_groups:\n"
                "  - name: media\n"
                "    launch_order:\n"
                "      - immich\n"
                "      - photos\n"
            )
            self._write_service(root, "immich", "media01", ingress_enabled=True, service_group="media")
            self._write_service(root, "photos", "media01", ingress_enabled=True, service_group="media")
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "service-launch"), "media"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("Service 'media' is not declared", result.stderr)
            self.assertFalse(calls_log.exists())

    def test_service_launch_stops_and_reports_the_failed_phase(self):
        scenarios = {
            "vm-up": (
                "VM Lifecycle Convergence failed for Service immich",
                ["vm-up media01"],
            ),
            "service-deploy": (
                "Service Deploy failed for Service immich",
                ["vm-up media01", "service-deploy immich"],
            ),
            "ingress-regenerate": (
                "Ingress Regeneration failed for Service immich",
                ["vm-up media01", "service-deploy immich", "ingress-regenerate"],
            ),
        }

        for failed_phase, (message, expected_calls) in scenarios.items():
            with self.subTest(failed_phase=failed_phase), tempfile.TemporaryDirectory() as tmp:
                root, calls_log = self._workflow_fixture(tmp)
                env = self._workflow_env(root, calls_log)
                env["FORTRESS_FAIL_PHASE"] = failed_phase

                result = subprocess.run(
                    [str(REPO_ROOT / "scripts" / "service-launch"), "immich"],
                    cwd=REPO_ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                self.assertEqual(result.returncode, 42)
                self.assertIn(message, result.stderr)
                self.assertEqual(expected_calls, calls_log.read_text().splitlines())

    def test_service_launch_rejects_unknown_flags(self):
        result = subprocess.run(
            [str(REPO_ROOT / "scripts" / "service-launch"), "immich", "--yes"],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("usage: scripts/service-launch <service> [--auto-confirm]", result.stderr)

    def _workflow_fixture(self, tmp):
        root = Path(tmp)
        (root / "inventory" / "services").mkdir(parents=True)
        (root / "inventory" / "vms").mkdir(parents=True)
        (root / "scripts").mkdir()
        (root / "inventory" / "vms" / "media01.yaml").write_text(
            "vmid: 101\n"
            "placement:\n"
            "  host: wintermute\n"
        )
        self._write_service(root, "immich", "media01", ingress_enabled=True)
        calls_log = root / "calls.log"
        for name in ["vm-up", "service-deploy", "service-update", "ingress-regenerate"]:
            script = root / "scripts" / name
            script.write_text(
                "#!/usr/bin/env bash\n"
                "name=$(basename \"$0\")\n"
                "printf '%s' \"$name\" >> \"$CALLS_LOG\"\n"
                "if [ \"$#\" -gt 0 ]; then printf ' %s' \"$*\" >> \"$CALLS_LOG\"; fi\n"
                "printf '\\n' >> \"$CALLS_LOG\"\n"
                "if [ \"$FORTRESS_FAIL_PHASE\" = \"$name\" ]; then exit 42; fi\n"
            )
            script.chmod(script.stat().st_mode | stat.S_IXUSR)
        return root, calls_log

    def _write_service(
        self,
        root,
        service_name,
        backend_vm,
        ingress_enabled,
        service_group=None,
        instrumentation_enabled=False,
        observability_view_enabled=False,
    ):
        ingress = "true" if ingress_enabled else "false"
        group = f"service_group: {service_group}\n" if service_group else ""
        observability_view = (
            "  observability_views:\n"
            "    - profile: prometheus_generic\n"
            if observability_view_enabled
            else ""
        )
        instrumentation = (
            "instrumentation:\n"
            "  telemetry_targets:\n"
            "    - name: metrics\n"
            "      type: prometheus_metrics\n"
            "      published_port: 2283\n"
            f"{observability_view}"
            if instrumentation_enabled
            else ""
        )
        (root / "inventory" / "services" / f"{service_name}.yaml").write_text(
            f"name: {service_name}\n"
            f"{group}"
            "backend:\n"
            f"  vm: {backend_vm}\n"
            "  port: 2283\n"
            "ingress:\n"
            f"  enabled: {ingress}\n"
            "deploy:\n"
            "  type: quadlet\n"
            "  containers:\n"
            "    - name: server\n"
            "      image: example.invalid/service:1\n"
            "      published_ports:\n"
            "        - container: 2283\n"
            "          host: 2283\n"
            "          bind: 0.0.0.0\n"
            f"{instrumentation}"
        )

    def _workflow_env(self, root, calls_log):
        env = os.environ.copy()
        env["FORTRESS_ROOT"] = str(root)
        env["CALLS_LOG"] = str(calls_log)
        return env


if __name__ == "__main__":
    unittest.main()
