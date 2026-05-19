import io
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fortress_workflows import (
    CommandPhase,
    ConfirmationGate,
    OperatorWorkflowRunner,
    build_service_group_launch_plan,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class ServiceGroupLaunchWorkflowTests(unittest.TestCase):
    def test_service_group_launch_plan_identifies_group_and_converges_shared_backend_vm_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _calls_log = self._workflow_fixture(tmp)

            plan = build_service_group_launch_plan(root, "media", auto_confirm=True)

            self.assertEqual("service-group-launch:media", plan.id)
            self.assertEqual("vm-lifecycle", plan.steps[0].id)
            vm_lifecycle = plan.steps[0]
            self.assertIsInstance(vm_lifecycle, CommandPhase)
            self.assertEqual("VM Lifecycle Convergence", vm_lifecycle.display_name)
            self.assertEqual(
                [str(root / "scripts" / "vm-up"), "media01", "--auto-confirm"],
                list(vm_lifecycle.command),
            )
            self.assertEqual(
                "VM Lifecycle Convergence failed for Service Group Launch media",
                vm_lifecycle.diagnostic_label,
            )

    def test_service_group_launch_plan_deploys_services_in_launch_order_with_ordinary_deploy_phases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _calls_log = self._workflow_fixture(tmp)
            self._write_service(root, "sonarr", "media01", deploy_type="native", ingress_enabled=False)

            plan = build_service_group_launch_plan(root, "media")

            self.assertEqual(
                ["vm-lifecycle", "service-deploy:prowlarr", "service-deploy:sonarr"],
                [step.id for step in plan.steps],
            )
            prowlarr_deploy, sonarr_deploy = plan.steps[1:]
            self.assertIsInstance(prowlarr_deploy, CommandPhase)
            self.assertEqual("Service Deploy", prowlarr_deploy.display_name)
            self.assertEqual(
                [str(root / "scripts" / "service-deploy"), "prowlarr"],
                list(prowlarr_deploy.command),
            )
            self.assertIsInstance(sonarr_deploy, CommandPhase)
            self.assertEqual("Service Deploy", sonarr_deploy.display_name)
            self.assertEqual(
                [str(root / "scripts" / "service-deploy"), "sonarr"],
                list(sonarr_deploy.command),
            )

    def test_service_group_launch_plan_regenerates_ingress_once_at_the_end_for_ingress_services(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _calls_log = self._workflow_fixture(tmp)
            self._write_service(root, "sonarr", "media01", deploy_type="quadlet", ingress_enabled=True)

            plan = build_service_group_launch_plan(root, "media")

            self.assertEqual(service_group_launch_step_ids(include_ingress=True), [step.id for step in plan.steps])
            ingress_regeneration = plan.steps[-1]
            self.assertIsInstance(ingress_regeneration, CommandPhase)
            self.assertEqual("Ingress Regeneration", ingress_regeneration.display_name)
            self.assertEqual(
                [str(root / "scripts" / "ingress-regenerate")],
                list(ingress_regeneration.command),
            )

    def test_service_group_launch_plan_refreshes_observability_when_any_service_declares_instrumentation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _calls_log = self._workflow_fixture(tmp)
            self._write_service(
                root,
                "sonarr",
                "media01",
                deploy_type="quadlet",
                ingress_enabled=False,
                instrumentation_enabled=True,
            )

            plan = build_service_group_launch_plan(root, "media")

            self.assertEqual(
                [
                    "vm-lifecycle",
                    "service-deploy:prowlarr",
                    "service-deploy:sonarr",
                    "observability-refresh",
                ],
                [step.id for step in plan.steps],
            )
            observability_refresh = plan.steps[-1]
            self.assertIsInstance(observability_refresh, CommandPhase)
            self.assertEqual("Observability Refresh", observability_refresh.display_name)
            self.assertEqual(
                [str(root / "scripts" / "service-update"), "observability", "--auto-confirm"],
                list(observability_refresh.command),
            )

    def test_service_group_launch_plan_refreshes_observability_when_service_requests_generated_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _calls_log = self._workflow_fixture(tmp)
            self._write_service(
                root,
                "sonarr",
                "media01",
                deploy_type="quadlet",
                ingress_enabled=False,
                instrumentation_enabled=True,
                observability_view_enabled=True,
            )

            plan = build_service_group_launch_plan(root, "media")

            self.assertEqual(
                [
                    "vm-lifecycle",
                    "service-deploy:prowlarr",
                    "service-deploy:sonarr",
                    "observability-refresh",
                ],
                [step.id for step in plan.steps],
            )
            self.assertEqual(
                [str(root / "scripts" / "service-update"), "observability", "--auto-confirm"],
                list(plan.steps[-1].command),
            )

    def test_observability_service_group_launch_plan_uses_observability_vm_and_service(self):
        plan = build_service_group_launch_plan(REPO_ROOT, "observability", auto_confirm=True)

        self.assertEqual("service-group-launch:observability", plan.id)
        self.assertEqual(
            ["vm-lifecycle", "service-deploy:observability", "ingress-regeneration"],
            [step.id for step in plan.steps],
        )
        self.assertEqual(
            [str(REPO_ROOT / "scripts" / "vm-up"), "observability-vm", "--auto-confirm"],
            list(plan.steps[0].command),
        )
        self.assertEqual(
            [str(REPO_ROOT / "scripts" / "service-deploy"), "observability"],
            list(plan.steps[1].command),
        )

    def test_service_group_launch_plan_omits_ingress_regeneration_when_no_launched_service_declares_ingress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _calls_log = self._workflow_fixture(tmp)

            plan = build_service_group_launch_plan(root, "media")

            self.assertEqual(
                ["vm-lifecycle", "service-deploy:prowlarr", "service-deploy:sonarr"],
                [step.id for step in plan.steps],
            )

    def test_service_group_launch_stops_at_first_failed_service_deploy_without_service_update_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            self._write_service(root, "sonarr", "media01", deploy_type="quadlet", ingress_enabled=True)
            self._write_fake_command_scripts(root)
            plan = build_service_group_launch_plan(root, "media")

            with patch.dict(
                os.environ,
                {"CALLS_LOG": str(calls_log), "FORTRESS_FAIL_PHASE": "service-deploy:prowlarr"},
            ):
                result = OperatorWorkflowRunner(cwd=root, output=io.StringIO()).run(plan)

            self.assertFalse(result.success)
            self.assertEqual(["vm-up media01", "service-deploy prowlarr"], calls_log.read_text().splitlines())
            self.assertEqual(
                ["vm-lifecycle", "service-deploy:prowlarr"],
                [phase.step_id for phase in result.phase_results],
            )
            self.assertFalse(any(isinstance(step, ConfirmationGate) for step in plan.steps))
            commands = [" ".join(step.command) for step in plan.steps if isinstance(step, CommandPhase)]
            self.assertFalse(any("vm-shell" in command for command in commands))
            self.assertFalse(any("systemctl restart" in command for command in commands))
            self.assertFalse(any("systemctl is-active" in command for command in commands))

    def test_service_group_launch_script_runs_group_launch_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            self._write_fake_command_scripts(root)
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "service-group-launch"), "media", "--auto-confirm"],
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
                    "service-deploy prowlarr",
                    "service-deploy sonarr",
                ],
                calls_log.read_text().splitlines(),
            )

    def test_service_group_launch_script_runs_observability_refresh_when_any_service_declares_instrumentation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            self._write_service(
                root,
                "sonarr",
                "media01",
                deploy_type="quadlet",
                ingress_enabled=False,
                instrumentation_enabled=True,
            )
            self._write_fake_command_scripts(root)
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "service-group-launch"), "media"],
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
                    "service-deploy prowlarr",
                    "service-deploy sonarr",
                    "service-update observability --auto-confirm",
                ],
                calls_log.read_text().splitlines(),
            )

    def test_service_group_launch_script_rejects_missing_args_and_unknown_flags_without_running_workflow(self):
        scenarios = [
            [],
            ["media", "--yes"],
            ["--yes"],
        ]

        for args in scenarios:
            with self.subTest(args=args), tempfile.TemporaryDirectory() as tmp:
                root, calls_log = self._workflow_fixture(tmp)
                self._write_fake_command_scripts(root)
                env = self._workflow_env(root, calls_log)

                result = subprocess.run(
                    [str(REPO_ROOT / "scripts" / "service-group-launch"), *args],
                    cwd=REPO_ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                self.assertEqual(result.returncode, 2)
                self.assertIn("usage: scripts/service-group-launch <group> [--auto-confirm]", result.stderr)
                self.assertFalse(calls_log.exists())

    def test_service_group_launch_script_rejects_groups_that_are_not_launchable_without_running_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            (root / "inventory" / "vms" / "media01.yaml").write_text("vmid: 101\n")
            self._write_fake_command_scripts(root)
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "service-group-launch"), "media"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("Service Group media is not launchable", result.stderr)
            self.assertFalse(calls_log.exists())

    def test_service_group_launch_script_reports_failed_service_deploy_and_skips_later_phases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._workflow_fixture(tmp)
            self._write_service(root, "sonarr", "media01", deploy_type="quadlet", ingress_enabled=True)
            self._write_fake_command_scripts(root)
            env = self._workflow_env(root, calls_log)
            env["FORTRESS_FAIL_PHASE"] = "service-deploy:prowlarr"

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "service-group-launch"), "media"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 42)
            self.assertIn("Service Deploy failed for Service prowlarr in Service Group Launch media", result.stderr)
            self.assertEqual(
                ["vm-up media01", "service-deploy prowlarr"],
                calls_log.read_text().splitlines(),
            )

    def test_just_service_group_launch_calls_workflow_script(self):
        justfile = (REPO_ROOT / "justfile").read_text()

        self.assertIn('service-group-launch group auto_confirm="false":', justfile)
        self.assertIn("./scripts/service-group-launch {{group}}", justfile)
        self.assertIn("--auto-confirm", justfile)
        self.assertIn('"{{auto_confirm}}" = "auto_confirm=true"', justfile)

    def _workflow_fixture(self, tmp):
        root = Path(tmp)
        (root / "inventory" / "services").mkdir(parents=True)
        (root / "inventory" / "vms").mkdir(parents=True)
        (root / "scripts").mkdir()
        (root / "inventory" / "vms" / "media01.yaml").write_text(
            "vmid: 101\n"
            "launchable_service_groups:\n"
            "  - name: media\n"
            "    launch_order:\n"
            "      - prowlarr\n"
            "      - sonarr\n"
        )
        self._write_service(root, "prowlarr", "media01", deploy_type="quadlet", ingress_enabled=False)
        self._write_service(root, "sonarr", "media01", deploy_type="quadlet", ingress_enabled=False)
        return root, root / "calls.log"

    def _write_service(
        self,
        root,
        service_name,
        backend_vm,
        deploy_type,
        ingress_enabled,
        instrumentation_enabled=False,
        observability_view_enabled=False,
    ):
        ingress = "true" if ingress_enabled else "false"
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
            "      published_port: 8080\n"
            f"{observability_view}"
            if instrumentation_enabled
            else ""
        )
        if deploy_type == "native":
            deploy_yaml = (
                "deploy:\n"
                "  type: native\n"
                "  package: caddy\n"
                f"  service_name: {service_name}\n"
            )
        else:
            deploy_yaml = (
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                f"    - name: {service_name}\n"
                f"      image: example.invalid/{service_name}:1\n"
                "      published_ports:\n"
                "        - container: 8080\n"
                "          host: 8080\n"
                "          bind: 0.0.0.0\n"
            )
        (root / "inventory" / "services" / f"{service_name}.yaml").write_text(
            f"name: {service_name}\n"
            "service_group: media\n"
            "backend:\n"
            f"  vm: {backend_vm}\n"
            "  port: 8080\n"
            "ingress:\n"
            f"  enabled: {ingress}\n"
            f"{deploy_yaml}"
            f"{instrumentation}"
        )

    def _write_fake_command_scripts(self, root):
        for name in ["vm-up", "service-deploy", "service-update", "ingress-regenerate"]:
            script = root / "scripts" / name
            script.write_text(
                "#!/usr/bin/env bash\n"
                "name=$(basename \"$0\")\n"
                "printf '%s' \"$name\" >> \"$CALLS_LOG\"\n"
                "if [ \"$#\" -gt 0 ]; then printf ' %s' \"$*\" >> \"$CALLS_LOG\"; fi\n"
                "printf '\\n' >> \"$CALLS_LOG\"\n"
                "phase=\"$name\"\n"
                "if [ \"$name\" = service-deploy ]; then phase=\"service-deploy:$1\"; fi\n"
                "if [ \"$FORTRESS_FAIL_PHASE\" = \"$phase\" ]; then exit 42; fi\n"
            )
            script.chmod(script.stat().st_mode | stat.S_IXUSR)

    def _workflow_env(self, root, calls_log):
        env = os.environ.copy()
        env["FORTRESS_ROOT"] = str(root)
        env["CALLS_LOG"] = str(calls_log)
        return env


def service_group_launch_step_ids(include_ingress=False):
    step_ids = ["vm-lifecycle", "service-deploy:prowlarr", "service-deploy:sonarr"]
    if include_ingress:
        step_ids.append("ingress-regeneration")
    return step_ids


if __name__ == "__main__":
    unittest.main()
