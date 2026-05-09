import json
import os
import shlex
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class AcceptanceNFSSharedMountWorkflowTests(unittest.TestCase):
    def test_requires_host_template_and_endpoint_arguments(self):
        result = subprocess.run(
            [
                str(REPO_ROOT / "scripts" / "acceptance-nfs-shared-mount"),
                "host=wintermute",
                "template=debian-12-base",
            ],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("usage: scripts/acceptance-nfs-shared-mount", result.stderr)
        self.assertIn("endpoint=<nas-endpoint>", result.stderr)

    def test_auto_confirm_success_generates_vms_reconciles_provisions_verifies_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._fixture(tmp)
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [
                    str(REPO_ROOT / "scripts" / "acceptance-nfs-shared-mount"),
                    "host=wintermute",
                    "template=debian-12-base",
                    "endpoint=truenas",
                    "auto_confirm=true",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("nfs shared-mount acceptance: passed", result.stdout)
            self.assertEqual(
                [
                    "nas-reconcile-plan --live truenas --acceptance-ephemeral-datasets --apply",
                    "vm-up tmp-nfs-primary --auto-confirm",
                    "vm-up tmp-nfs-peer --auto-confirm",
                    f"ansible-inventory -i {root / 'inventory' / 'fortress.yaml'} --list",
                    *self._ssh_calls("tmp-nfs-primary", "10.10.0.231", "systemctl", "is-active", "mnt-nfs\\x2ddemo.mount"),
                    *self._ssh_calls("tmp-nfs-primary", "10.10.0.231", "findmnt", "/mnt/nfs-demo"),
                    *self._ssh_calls("tmp-nfs-peer", "10.10.0.232", "systemctl", "is-active", "mnt-nfs\\x2ddemo.mount"),
                    *self._ssh_calls("tmp-nfs-peer", "10.10.0.232", "findmnt", "/mnt/nfs-demo"),
                    *self._ssh_calls("tmp-nfs-primary", "10.10.0.231", "sh", "-lc", "printf primary > /mnt/nfs-demo/fortress-primary.txt"),
                    *self._ssh_calls("tmp-nfs-peer", "10.10.0.232", "cat", "/mnt/nfs-demo/fortress-primary.txt"),
                    *self._ssh_calls("tmp-nfs-peer", "10.10.0.232", "sh", "-lc", "printf peer > /mnt/nfs-demo/fortress-peer.txt"),
                    *self._ssh_calls("tmp-nfs-primary", "10.10.0.231", "cat", "/mnt/nfs-demo/fortress-peer.txt"),
                    *self._ssh_calls("tmp-nfs-peer", "10.10.0.232", "rm", "/mnt/nfs-demo/fortress-primary.txt"),
                    *self._ssh_calls("tmp-nfs-primary", "10.10.0.231", "test", "!", "-e", "/mnt/nfs-demo/fortress-primary.txt"),
                    *self._ssh_calls("tmp-nfs-primary", "10.10.0.231", "rm", "/mnt/nfs-demo/fortress-peer.txt"),
                    *self._ssh_calls("tmp-nfs-peer", "10.10.0.232", "test", "!", "-e", "/mnt/nfs-demo/fortress-peer.txt"),
                    "vm-destroy tmp-nfs-primary --delete-vm-yaml",
                    "vm-destroy tmp-nfs-peer --delete-vm-yaml",
                    "nas-reconcile-plan --live truenas --acceptance-ephemeral-datasets --destroy-ephemeral-datasets --apply",
                ],
                calls_log.read_text().splitlines(),
            )
            primary_yaml = (root / "inventory" / "vms" / "tmp-nfs-primary.yaml").read_text()
            peer_yaml = (root / "inventory" / "vms" / "tmp-nfs-peer.yaml").read_text()
            self.assertIn("vmid: 8911", primary_yaml)
            self.assertIn("hostname: tmp-nfs-primary", primary_yaml)
            self.assertIn("address: 10.10.0.231/24", primary_yaml)
            self.assertIn("dataset: acceptance-nfs-demo", primary_yaml)
            self.assertIn("mount_point: /mnt/nfs-demo", primary_yaml)
            self.assertIn("access: read_write", primary_yaml)
            self.assertIn("vmid: 8912", peer_yaml)
            self.assertIn("hostname: tmp-nfs-peer", peer_yaml)
            self.assertIn("address: 10.10.0.232/24", peer_yaml)

    def test_refuses_to_overwrite_generated_artifacts_before_reconcile(self):
        for path_name in [
            "tmp-nfs-primary.yaml",
            "tmp-nfs-primary.sops.yaml",
            "tmp-nfs-peer.yaml",
            "tmp-nfs-peer.sops.yaml",
        ]:
            with self.subTest(path_name=path_name), tempfile.TemporaryDirectory() as tmp:
                root, calls_log = self._fixture(tmp)
                (root / "inventory" / "vms" / path_name).write_text("existing\n")
                env = self._workflow_env(root, calls_log)

                result = subprocess.run(
                    [
                        str(REPO_ROOT / "scripts" / "acceptance-nfs-shared-mount"),
                        "host=wintermute",
                        "template=debian-12-base",
                        "endpoint=truenas",
                        "auto_confirm=true",
                    ],
                    cwd=REPO_ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                self.assertEqual(result.returncode, 1)
                self.assertIn("refusing to overwrite", result.stderr)
                self.assertFalse(calls_log.exists())

    def test_keep_on_fail_preserves_resources_and_cleanup_failure_reports_both_failures(self):
        scenarios = {
            "keep": ({"FORTRESS_FAIL_PHASE": "ssh", "KEEP": "true"}, "preserved NFS shared-mount acceptance resources"),
            "cleanup": ({"FORTRESS_FAIL_PHASE": "ssh", "FORTRESS_CLEANUP_FAIL_PHASE": "vm-destroy"}, "cleanup also failed"),
        }
        for scenario, (overrides, message) in scenarios.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                root, calls_log = self._fixture(tmp)
                env = self._workflow_env(root, calls_log)
                env.update(overrides)
                args = [
                    str(REPO_ROOT / "scripts" / "acceptance-nfs-shared-mount"),
                    "host=wintermute",
                    "template=debian-12-base",
                    "endpoint=truenas",
                    "auto_confirm=true",
                ]
                if overrides.get("KEEP") == "true":
                    args.append("keep_on_fail=true")

                result = subprocess.run(
                    args,
                    cwd=REPO_ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                self.assertEqual(result.returncode, 1)
                self.assertIn("verification failed", result.stderr)
                self.assertIn(message, result.stderr)
                if scenario == "keep":
                    self.assertNotIn("vm-destroy", calls_log.read_text())

    def test_reconcile_failure_removes_unprovisioned_generated_inventory_without_vm_destroy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._fixture(tmp)
            env = self._workflow_env(root, calls_log)
            env["FORTRESS_FAIL_PHASE"] = "nas-reconcile-plan"

            result = subprocess.run(
                [
                    str(REPO_ROOT / "scripts" / "acceptance-nfs-shared-mount"),
                    "host=wintermute",
                    "template=debian-12-base",
                    "endpoint=truenas",
                    "auto_confirm=true",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("NAS Reconcile failed", result.stderr)
            self.assertNotIn("vm-destroy", calls_log.read_text())
            self.assertFalse((root / "inventory" / "vms" / "tmp-nfs-primary.yaml").exists())
            self.assertFalse((root / "inventory" / "vms" / "tmp-nfs-peer.yaml").exists())

    def test_just_recipe_and_runbook_document_workflow(self):
        justfile = (REPO_ROOT / "justfile").read_text()
        runbook = (REPO_ROOT / "runbooks" / "nas-truenas.md").read_text()

        self.assertIn('acceptance-nfs-shared-mount host template endpoint auto_confirm="false" keep_on_fail="false":', justfile)
        self.assertIn("./scripts/acceptance-nfs-shared-mount", justfile)
        self.assertIn("{{host}}", justfile)
        self.assertIn("{{template}}", justfile)
        self.assertIn("{{endpoint}}", justfile)
        self.assertIn("{{auto_confirm}}", justfile)
        self.assertIn("{{keep_on_fail}}", justfile)
        self.assertIn("just acceptance-nfs-shared-mount host=<host> template=<template> endpoint=<nas-endpoint>", runbook)
        self.assertIn("tmp-nfs-primary", runbook)
        self.assertIn("tmp-nfs-peer", runbook)
        self.assertIn("keep_on_fail=true", runbook)

    def _fixture(self, tmp):
        root = Path(tmp)
        inventory = root / "inventory"
        scripts = root / "scripts"
        (inventory / "acceptance").mkdir(parents=True)
        (inventory / "hosts").mkdir()
        (inventory / "templates").mkdir()
        (inventory / "vms").mkdir()
        (inventory / "datasets").mkdir()
        (inventory / "nas").mkdir()
        scripts.mkdir()
        (inventory / "acceptance" / "nfs-shared-mount.yaml").write_text(
            "dataset: acceptance-nfs-demo\n"
            "mount:\n"
            "  name: nfs-demo\n"
            "  mount_point: /mnt/nfs-demo\n"
            "  access: read_write\n"
            "hardware:\n"
            "  cores: 1\n"
            "  memory: 1024\n"
            "  disk_size: 8G\n"
            "storage_by_host:\n"
            "  wintermute: fast\n"
            "vms:\n"
            "  primary:\n"
            "    name: tmp-nfs-primary\n"
            "    vmid: 8911\n"
            "    address_by_host:\n"
            "      wintermute: 10.10.0.231/24\n"
            "  peer:\n"
            "    name: tmp-nfs-peer\n"
            "    vmid: 8912\n"
            "    address_by_host:\n"
            "      wintermute: 10.10.0.232/24\n"
        )
        (inventory / "hosts" / "wintermute.yaml").write_text(
            "proxmox:\n"
            "  templates: [debian-12-base]\n"
            "network:\n"
            "  bridges:\n"
            "    - name: vmbr0\n"
            "      cidr: 10.10.0.11/24\n"
            "      gateway: 10.10.0.1\n"
        )
        (inventory / "templates" / "debian-12-base.yaml").write_text("name: debian-12-base\nvmid: 9001\n")
        (inventory / "datasets" / "acceptance-nfs-demo.yaml").write_text(
            "name: acceptance-nfs-demo\nnas: truenas\npath: /mnt/tank/fortress-acceptance/nfs-demo\nlifecycle: ephemeral\n"
        )
        (inventory / "nas" / "truenas.yaml").write_text("name: truenas\nmanagement_address: 10.10.0.15\nshare_address: 10.40.0.15\n")
        calls_log = root / "calls.log"
        self._write_fake_tools(root, calls_log)
        return root, calls_log

    def _write_fake_tools(self, root, calls_log):
        scripts = root / "scripts"
        for name in ["vm-up", "vm-destroy"]:
            script = scripts / name
            script.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s %s\\n' \"$(basename \"$0\")\" \"$*\" >> \"$CALLS_LOG\"\n"
                "if [ \"$FORTRESS_CLEANUP_FAIL_PHASE\" = \"$(basename \"$0\")\" ]; then echo \"$(basename \"$0\") cleanup failed intentionally\" >&2; exit 42; fi\n"
            )
            script.chmod(script.stat().st_mode | stat.S_IXUSR)
        (scripts / "decrypt-keys").write_text(
            "#!/usr/bin/env bash\n"
            "printf 'decrypt-keys %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
            "while [ \"$1\" != \"--\" ]; do shift; done\n"
            "shift\n"
            "exec \"$@\"\n"
        )
        (scripts / "decrypt-keys").chmod((scripts / "decrypt-keys").stat().st_mode | stat.S_IXUSR)
        (scripts / "nas-reconcile-plan").write_text(
            "#!/usr/bin/env bash\n"
            "printf 'nas-reconcile-plan %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
            "if [ \"$FORTRESS_FAIL_PHASE\" = nas-reconcile-plan ]; then echo 'nas reconcile failed intentionally' >&2; exit 42; fi\n"
            "python3 - <<'PY'\n"
            "import json\n"
            "print(json.dumps({'desired_nfs_shares': [{'name': 'fortress-nfs-acceptance-nfs-demo-read-write', 'dataset': 'acceptance-nfs-demo', 'path': '/mnt/tank/fortress-acceptance/nfs-demo', 'protocol': 'nfs', 'access': 'read_write', 'clients': ['10.10.0.201', '10.10.0.231', '10.10.0.232']}]}))\n"
            "PY\n"
        )
        (scripts / "nas-reconcile-plan").chmod((scripts / "nas-reconcile-plan").stat().st_mode | stat.S_IXUSR)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        (bin_dir / "ansible-inventory").write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "with open(os.environ['CALLS_LOG'], 'a') as log:\n"
            "    log.write('ansible-inventory ' + ' '.join(sys.argv[1:]) + '\\n')\n"
            "print(json.dumps({'_meta': {'hostvars': {'tmp-nfs-primary': {'ansible_host': '10.10.0.231', 'ansible_ssh_private_key_file': '/dev/shm/fortress/tmp-nfs-primary.key'}, 'tmp-nfs-peer': {'ansible_host': '10.10.0.232', 'ansible_ssh_private_key_file': '/dev/shm/fortress/tmp-nfs-peer.key'}}}}))\n"
        )
        (bin_dir / "ansible-inventory").chmod((bin_dir / "ansible-inventory").stat().st_mode | stat.S_IXUSR)
        (bin_dir / "ssh").write_text(
            "#!/usr/bin/env bash\n"
            "printf 'ssh %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
            "if [ \"$FORTRESS_FAIL_PHASE\" = ssh ]; then echo 'verification failed intentionally' >&2; exit 42; fi\n"
            "case \"$*\" in\n"
            "  *'cat /mnt/nfs-demo/fortress-primary.txt'*) echo primary ;;\n"
            "  *'cat /mnt/nfs-demo/fortress-peer.txt'*) echo peer ;;\n"
            "esac\n"
        )
        (bin_dir / "ssh").chmod((bin_dir / "ssh").stat().st_mode | stat.S_IXUSR)

    def _ssh_calls(self, vm, ip, *command):
        remote_shell_command = f"sudo sh -lc {shlex.quote(shlex.join(command))}"
        ssh_args = (
            f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
            f"-i /dev/shm/fortress/{vm}.key admin@{ip} {remote_shell_command}"
        )
        return [
            f"decrypt-keys inventory/vms/{vm}.sops.yaml -- {ssh_args}",
            ssh_args,
        ]

    def _workflow_env(self, root, calls_log):
        env = os.environ.copy()
        env["FORTRESS_ROOT"] = str(root)
        env["CALLS_LOG"] = str(calls_log)
        env["PATH"] = f"{root / 'bin'}:{env['PATH']}"
        env["FORTRESS_VERIFY_RETRIES"] = "1"
        env["FORTRESS_VERIFY_RETRY_DELAY"] = "0"
        return env


if __name__ == "__main__":
    unittest.main()
