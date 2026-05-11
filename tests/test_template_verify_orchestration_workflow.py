import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class TemplateVerifyOrchestrationWorkflowTests(unittest.TestCase):
    def test_single_host_success_runs_generate_vm_up_verify_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._fixture(tmp)
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [
                    str(REPO_ROOT / "scripts" / "template-verify"),
                    "host=wintermute",
                    "template=debian-13-base",
                    'keep_on_fail="false"',
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                [
                    "template-verify-generate wintermute debian-13-base",
                    "vm-up tmp-template-verify",
                    "decrypt-keys inventory/vms/tmp-template-verify.sops.yaml -- ansible-playbook ansible/playbooks/template-verify.yml -i inventory/fortress.yaml --limit tmp-template-verify",
                    "ansible-playbook ansible/playbooks/template-verify.yml -i inventory/fortress.yaml --limit tmp-template-verify",
                    "vm-destroy tmp-template-verify --delete-vm-yaml",
                ],
                calls_log.read_text().splitlines(),
            )
            self.assertIn("wintermute: passed", result.stdout)

    def test_just_template_verify_calls_workflow_script(self):
        justfile = (REPO_ROOT / "justfile").read_text()

        self.assertIn('template-verify host template keep_on_fail="false":', justfile)
        self.assertIn("./scripts/template-verify", justfile)
        self.assertIn("{{host}}", justfile)
        self.assertIn("{{template}}", justfile)
        self.assertIn("{{keep_on_fail}}", justfile)

    def test_new_template_runbook_documents_template_verification_operator_workflow(self):
        content = (REPO_ROOT / "runbooks" / "new-template.md").read_text()

        self.assertIn("just templates-build host=<host>", content)
        self.assertIn("just template-verify host=<host> template=<template>", content)
        self.assertIn("just template-verify host=all template=<template>", content)
        self.assertIn("skipped", content)
        self.assertIn("Host does not declare the selected Template", content)
        self.assertIn("destroys the Template Verification VM", content)
        self.assertIn("keep_on_fail=true", content)
        self.assertIn("preserves the failed Template Verification VM", content)
        self.assertIn("inventory/vms/tmp-template-verify.yaml", content)
        self.assertIn("inventory/vms/tmp-template-verify.sops.yaml", content)

    def test_host_all_reports_passed_failed_and_skipped_hosts_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._fixture(tmp)
            (root / "inventory" / "hosts" / "straylight.yaml").write_text(
                "proxmox:\n"
                "  templates: [debian-13-base]\n"
            )
            (root / "inventory" / "hosts" / "molly.yaml").write_text(
                "proxmox:\n"
                "  templates: []\n"
            )
            env = self._workflow_env(root, calls_log)
            env["FORTRESS_VERIFY_FAIL_ON_HOST"] = "straylight"

            result = subprocess.run(
                [
                    str(REPO_ROOT / "scripts" / "template-verify"),
                    "host=all",
                    "template=debian-13-base",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("molly: skipped", result.stdout)
            self.assertIn("straylight: failed", result.stdout)
            self.assertIn("wintermute: passed", result.stdout)
            self.assertLess(result.stdout.index("molly: skipped"), result.stdout.index("straylight: failed"))
            self.assertLess(result.stdout.index("straylight: failed"), result.stdout.index("wintermute: passed"))
            self.assertEqual(
                [
                    "template-verify-generate straylight debian-13-base",
                    "vm-up tmp-template-verify",
                    "decrypt-keys inventory/vms/tmp-template-verify.sops.yaml -- ansible-playbook ansible/playbooks/template-verify.yml -i inventory/fortress.yaml --limit tmp-template-verify",
                    "ansible-playbook ansible/playbooks/template-verify.yml -i inventory/fortress.yaml --limit tmp-template-verify",
                    "vm-destroy tmp-template-verify --delete-vm-yaml",
                    "template-verify-generate wintermute debian-13-base",
                    "vm-up tmp-template-verify",
                    "decrypt-keys inventory/vms/tmp-template-verify.sops.yaml -- ansible-playbook ansible/playbooks/template-verify.yml -i inventory/fortress.yaml --limit tmp-template-verify",
                    "ansible-playbook ansible/playbooks/template-verify.yml -i inventory/fortress.yaml --limit tmp-template-verify",
                    "vm-destroy tmp-template-verify --delete-vm-yaml",
                ],
                calls_log.read_text().splitlines(),
            )

    def test_verification_failure_runs_cleanup_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._fixture(tmp)
            env = self._workflow_env(root, calls_log)
            env["FORTRESS_VERIFY_FAIL_ON_HOST"] = "wintermute"

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "template-verify"), "host=wintermute", "template=debian-13-base"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("wintermute: failed", result.stdout)
            self.assertIn("verification failed on wintermute", result.stderr)
            self.assertIn("vm-destroy tmp-template-verify --delete-vm-yaml", calls_log.read_text())

    def test_default_run_cleans_stale_generated_artifacts_before_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._fixture(tmp)
            vm_yaml = root / "inventory" / "vms" / "tmp-template-verify.yaml"
            vm_sops = root / "inventory" / "vms" / "tmp-template-verify.sops.yaml"
            vm_yaml.write_text(
                "description: Generated Template Verification VM. Do not edit by hand.\n"
                "lifecycle:\n"
                "  kind: operational\n"
                "  purpose: template-verification\n"
                "  generated: true\n"
            )
            vm_sops.write_text("encrypted generated ssh material\n")
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "template-verify"), "host=wintermute", "template=debian-13-base"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                [
                    "vm-destroy tmp-template-verify --delete-vm-yaml",
                    "template-verify-generate wintermute debian-13-base",
                    "vm-up tmp-template-verify",
                    "decrypt-keys inventory/vms/tmp-template-verify.sops.yaml -- ansible-playbook ansible/playbooks/template-verify.yml -i inventory/fortress.yaml --limit tmp-template-verify",
                    "ansible-playbook ansible/playbooks/template-verify.yml -i inventory/fortress.yaml --limit tmp-template-verify",
                    "vm-destroy tmp-template-verify --delete-vm-yaml",
                ],
                calls_log.read_text().splitlines(),
            )

    def test_default_run_cleans_stale_generated_sibling_sops_file_before_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._fixture(tmp)
            (root / "inventory" / "vms" / "tmp-template-verify.sops.yaml").write_text("encrypted generated ssh material\n")
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "template-verify"), "host=wintermute", "template=debian-13-base"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                [
                    "template-verify-generate wintermute debian-13-base",
                    "vm-up tmp-template-verify",
                    "decrypt-keys inventory/vms/tmp-template-verify.sops.yaml -- ansible-playbook ansible/playbooks/template-verify.yml -i inventory/fortress.yaml --limit tmp-template-verify",
                    "ansible-playbook ansible/playbooks/template-verify.yml -i inventory/fortress.yaml --limit tmp-template-verify",
                    "vm-destroy tmp-template-verify --delete-vm-yaml",
                ],
                calls_log.read_text().splitlines(),
            )

    def test_default_run_refuses_to_clean_ambiguous_template_verify_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._fixture(tmp)
            vm_yaml = root / "inventory" / "vms" / "tmp-template-verify.yaml"
            vm_yaml.write_text(
                "description: operator managed VM with colliding name\n"
                "lifecycle:\n"
                "  kind: operational\n"
            )
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "template-verify"), "host=wintermute", "template=debian-13-base"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("not clearly generated for Template Verification", result.stderr)
            self.assertFalse(calls_log.exists())
            self.assertTrue(vm_yaml.exists())

    def test_verification_failure_with_keep_on_fail_preserves_generated_vm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._fixture(tmp)
            env = self._workflow_env(root, calls_log)
            env["FORTRESS_VERIFY_FAIL_ON_HOST"] = "wintermute"

            result = subprocess.run(
                [
                    str(REPO_ROOT / "scripts" / "template-verify"),
                    "host=wintermute",
                    "template=debian-13-base",
                    "keep_on_fail=true",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("preserved Template Verification VM for inspection", result.stderr)
            self.assertNotIn("vm-destroy", calls_log.read_text())

    def test_keep_on_fail_run_preserves_existing_generated_artifacts_with_recovery_instruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._fixture(tmp)
            vm_yaml = root / "inventory" / "vms" / "tmp-template-verify.yaml"
            vm_sops = root / "inventory" / "vms" / "tmp-template-verify.sops.yaml"
            vm_yaml.write_text(
                "description: Generated Template Verification VM. Do not edit by hand.\n"
                "lifecycle:\n"
                "  kind: operational\n"
                "  purpose: template-verification\n"
                "  generated: true\n"
            )
            vm_sops.write_text("encrypted generated ssh material\n")
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [
                    str(REPO_ROOT / "scripts" / "template-verify"),
                    "host=wintermute",
                    "template=debian-13-base",
                    "keep_on_fail=true",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("preserved for inspection", result.stderr)
            self.assertIn("scripts/vm-destroy tmp-template-verify --delete-vm-yaml", result.stderr)
            self.assertFalse(calls_log.exists())
            self.assertTrue(vm_yaml.exists())
            self.assertTrue(vm_sops.exists())

    def test_failed_generate_and_failed_provision_are_reported_with_useful_phase_messages(self):
        scenarios = {
            "template-verify-generate": ("generation/preflight failed", False),
            "vm-up": ("provision failed", True),
        }

        for failed_phase, (message, should_cleanup) in scenarios.items():
            with self.subTest(failed_phase=failed_phase), tempfile.TemporaryDirectory() as tmp:
                root, calls_log = self._fixture(tmp)
                env = self._workflow_env(root, calls_log)
                env["FORTRESS_FAIL_PHASE"] = failed_phase

                result = subprocess.run(
                    [str(REPO_ROOT / "scripts" / "template-verify"), "host=wintermute", "template=debian-13-base"],
                    cwd=REPO_ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                self.assertEqual(result.returncode, 1)
                self.assertIn("wintermute: failed", result.stdout)
                self.assertIn(message, result.stderr)
                self.assertEqual(should_cleanup, "vm-destroy tmp-template-verify --delete-vm-yaml" in calls_log.read_text())

    def test_cleanup_failure_reports_cleanup_without_hiding_original_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._fixture(tmp)
            env = self._workflow_env(root, calls_log)
            env["FORTRESS_VERIFY_FAIL_ON_HOST"] = "wintermute"
            env["FORTRESS_FAIL_PHASE"] = "vm-destroy"

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "template-verify"), "host=wintermute", "template=debian-13-base"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("verification failed on wintermute", result.stderr)
            self.assertIn("cleanup also failed", result.stderr)
            self.assertIn("vm-destroy failed intentionally", result.stderr)
            self.assertIn("vm-destroy tmp-template-verify --delete-vm-yaml", calls_log.read_text())

    def _fixture(self, tmp):
        root = Path(tmp)
        inventory = root / "inventory"
        scripts = root / "scripts"
        (inventory / "hosts").mkdir(parents=True)
        (inventory / "templates").mkdir()
        (inventory / "vms").mkdir()
        scripts.mkdir()
        (inventory / "hosts" / "wintermute.yaml").write_text(
            "proxmox:\n"
            "  templates: [debian-13-base]\n"
        )
        (inventory / "templates" / "debian-13-base.yaml").write_text("name: debian-13-base\nvmid: 9001\n")
        calls_log = root / "calls.log"
        tools = {
            "template-verify-generate": "",
            "vm-up": "",
            "vm-destroy": "",
            "decrypt-keys": 'shift; shift; exec "$@"',
        }
        for name, extra in tools.items():
            script = scripts / name
            script.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s %s\\n' \"$(basename \"$0\")\" \"$*\" >> \"$CALLS_LOG\"\n"
                "if [ \"$(basename \"$0\")\" = template-verify-generate ]; then printf '%s\\n' \"$1\" > \"$FORTRESS_ROOT/current-template-verify-host\"; fi\n"
                "if [ \"$(basename \"$0\")\" = template-verify-generate ] && [ -e \"$FORTRESS_ROOT/inventory/vms/tmp-template-verify.yaml\" ]; then printf 'stale generated inventory blocks generation\\n' >&2; exit 1; fi\n"
                "if [ \"$(basename \"$0\")\" = template-verify-generate ] && [ -e \"$FORTRESS_ROOT/inventory/vms/tmp-template-verify.sops.yaml\" ]; then printf 'stale generated sops blocks generation\\n' >&2; exit 1; fi\n"
                "if [ \"$(basename \"$0\")\" = vm-destroy ]; then rm -f \"$FORTRESS_ROOT/inventory/vms/tmp-template-verify.yaml\" \"$FORTRESS_ROOT/inventory/vms/tmp-template-verify.sops.yaml\"; fi\n"
                "if [ \"$FORTRESS_FAIL_PHASE\" = \"$(basename \"$0\")\" ]; then printf '%s failed intentionally\\n' \"$(basename \"$0\")\" >&2; exit 42; fi\n"
                f"{extra}\n"
            )
            script.chmod(script.stat().st_mode | stat.S_IXUSR)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        ansible = bin_dir / "ansible-playbook"
        ansible.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'ansible-playbook %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
            "current=$(cat \"$FORTRESS_ROOT/current-template-verify-host\")\n"
            "if [ \"$FORTRESS_VERIFY_FAIL_ON_HOST\" = \"$current\" ]; then printf 'verification failed on %s\\n' \"$current\" >&2; exit 42; fi\n"
        )
        ansible.chmod(ansible.stat().st_mode | stat.S_IXUSR)
        return root, calls_log

    def _workflow_env(self, root, calls_log):
        env = os.environ.copy()
        env["FORTRESS_ROOT"] = str(root)
        env["CALLS_LOG"] = str(calls_log)
        env["PATH"] = f"{root / 'bin'}:{env['PATH']}"
        return env


if __name__ == "__main__":
    unittest.main()
