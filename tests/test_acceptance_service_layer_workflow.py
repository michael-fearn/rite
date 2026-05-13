import hashlib
import os
import shlex
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class AcceptanceServiceLayerWorkflowTests(unittest.TestCase):
    def test_requires_host_template_and_endpoint_arguments(self):
        result = subprocess.run(
            [
                str(REPO_ROOT / "scripts" / "acceptance-service-layer"),
                "host=wintermute",
                "template=debian-13-base",
            ],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("usage: scripts/acceptance-service-layer", result.stderr)
        self.assertIn("endpoint=<nas-endpoint>", result.stderr)

    def test_auto_confirm_generates_deploys_verifies_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._fixture(tmp)
            env = self._workflow_env(root, calls_log)

            result = subprocess.run(
                [
                    str(REPO_ROOT / "scripts" / "acceptance-service-layer"),
                    "host=wintermute",
                    "template=debian-13-base",
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
            self.assertIn("service-layer acceptance: passed", result.stdout)
            self.assertIn("service-layer acceptance: generating temporary Inventory artifacts", result.stdout)
            self.assertIn("service-layer acceptance: reconciling Ephemeral Dataset and Derived NFS Share on NAS Endpoint truenas", result.stdout)
            self.assertIn("service-layer acceptance: provisioning primary Acceptance VM tmp-service-primary", result.stdout)
            self.assertIn("service-layer acceptance: provisioning peer Acceptance VM tmp-service-peer", result.stdout)
            self.assertIn("service-layer acceptance: deploying generated Service tmp-service-layer to tmp-service-primary", result.stdout)
            self.assertIn("service-layer acceptance: deploying generated Native Service tmp-service-layer-native to tmp-service-primary", result.stdout)
            self.assertIn("service-layer acceptance: verifying Service-layer contract", result.stdout)
            self.assertIn("service-layer acceptance: checking Native Service systemd unit caddy", result.stdout)
            self.assertIn("service-layer acceptance: checking Service Secret bytes inside web container", result.stdout)
            self.assertIn("service-layer acceptance: reloading TrueNAS NFS service on NAS Endpoint truenas", result.stdout)
            self.assertIn("service-layer acceptance: verifying post-reload Mount and Share-backed Volume data flow", result.stdout)
            self.assertIn("service-layer acceptance: writing fresh post-reload marker through Primary Acceptance VM Mount", result.stdout)
            self.assertIn("service-layer acceptance: reading fresh post-reload marker through Peer Acceptance VM Mount", result.stdout)
            self.assertIn("service-layer acceptance: checking already-running Service serves fresh post-reload content", result.stdout)
            self.assertIn("service-layer acceptance: cleaning up generated Acceptance resources", result.stdout)
            calls = calls_log.read_text().splitlines()
            self.assertEqual(
                [
                    "sops --encrypt --in-place " + str(root / "inventory" / "services" / "tmp-service-layer.sops.yaml"),
                    "nas-reconcile-plan --live truenas --acceptance-ephemeral-datasets --apply",
                    "vm-up tmp-service-primary --auto-confirm",
                    "vm-up tmp-service-peer --auto-confirm",
                    "service-deploy tmp-service-layer",
                    "service-deploy tmp-service-layer-native",
                    f"ansible-inventory -i {root / 'inventory' / 'fortress.yaml'} --list",
                    *self._ssh_calls("tmp-service-primary", "10.10.0.233", "systemctl", "is-active", "mnt-service\\x2dlayer.mount"),
                    *self._ssh_calls("tmp-service-primary", "10.10.0.233", "findmnt", "/mnt/service-layer"),
                    *self._ssh_calls("tmp-service-primary", "10.10.0.233", "sh", "-lc", "printf service-layer-marker > /mnt/service-layer/index.html"),
                    *self._ssh_calls("tmp-service-primary", "10.10.0.233", "systemctl", "is-active", "fortress-tmp-service-layer-postgres.service"),
                    *self._ssh_calls("tmp-service-primary", "10.10.0.233", "systemctl", "is-active", "fortress-tmp-service-layer-redis.service"),
                    *self._ssh_calls("tmp-service-primary", "10.10.0.233", "systemctl", "is-active", "fortress-tmp-service-layer-web.service"),
                    *self._ssh_calls("tmp-service-primary", "10.10.0.233", "podman", "exec", "fortress-tmp-service-layer-web", "getent", "hosts", "postgres"),
                    *self._ssh_calls("tmp-service-primary", "10.10.0.233", "podman", "exec", "fortress-tmp-service-layer-web", "getent", "hosts", "redis"),
                    *self._ssh_calls(
                        "tmp-service-primary",
                        "10.10.0.233",
                        "podman",
                        "exec",
                        "fortress-tmp-service-layer-web",
                        "sh",
                        "-lc",
                        "sha256sum \"$ACCEPTANCE_TOKEN_FILE\" | awk '{print $1}'",
                    ),
                    *self._ssh_calls("tmp-service-peer", "10.10.0.234", "curl", "-fsS", "http://10.10.0.233:8080/"),
                    *self._ssh_calls("tmp-service-primary", "10.10.0.233", "systemctl", "is-active", "caddy"),
                    *self._ssh_calls("tmp-service-peer", "10.10.0.234", "curl", "-fsS", "http://10.10.0.233:18080/"),
                    "sops --decrypt --extract [\"api_credentials\"][\"acceptance\"][\"value\"] " + str(root / "inventory" / "nas" / "truenas.sops.yaml"),
                    "truenas reload_nfs_service truenas 10.10.0.15 true acceptance-secret-token",
                    f"ansible-inventory -i {root / 'inventory' / 'fortress.yaml'} --list",
                    *self._ssh_calls(
                        "tmp-service-primary",
                        "10.10.0.233",
                        "sh",
                        "-lc",
                        "printf post-reload-service-layer-marker > /mnt/service-layer/post-reload-marker.txt",
                    ),
                    *self._ssh_calls("tmp-service-peer", "10.10.0.234", "cat", "/mnt/service-layer/post-reload-marker.txt"),
                    *self._ssh_calls(
                        "tmp-service-primary",
                        "10.10.0.233",
                        "sh",
                        "-lc",
                        "printf post-reload-service-layer-content > /mnt/service-layer/index.html",
                    ),
                    *self._ssh_calls("tmp-service-peer", "10.10.0.234", "curl", "-fsS", "http://10.10.0.233:8080/"),
                    *self._ssh_calls("tmp-service-primary", "10.10.0.233", "rm", "-f", "/mnt/service-layer/post-reload-marker.txt"),
                    "vm-destroy tmp-service-primary --delete-vm-yaml",
                    "vm-destroy tmp-service-peer --delete-vm-yaml",
                    "nas-reconcile-plan --live truenas --acceptance-ephemeral-datasets --destroy-ephemeral-datasets --apply",
                ],
                calls,
            )
            self.assertFalse((root / "inventory" / "services" / "tmp-service-layer.yaml").exists())
            self.assertFalse((root / "inventory" / "services" / "tmp-service-layer.sops.yaml").exists())
            self.assertFalse((root / "inventory" / "services" / "tmp-service-layer.quadlet.d").exists())
            self.assertFalse((root / "inventory" / "services" / "tmp-service-layer-native.yaml").exists())
            self.assertFalse((root / "inventory" / "services" / "tmp-service-layer-native.native.d").exists())
            self.assertFalse((root / "inventory" / "datasets" / "acceptance-service-layer.yaml").exists())

    def test_refuses_to_overwrite_generated_artifacts_before_reconcile(self):
        generated_paths = [
            ("inventory/datasets/acceptance-service-layer.yaml", "existing\n"),
            ("inventory/vms/tmp-service-primary.yaml", "existing\n"),
            ("inventory/vms/tmp-service-primary.sops.yaml", "existing\n"),
            ("inventory/vms/tmp-service-peer.yaml", "existing\n"),
            ("inventory/vms/tmp-service-peer.sops.yaml", "existing\n"),
            ("inventory/services/tmp-service-layer.yaml", "existing\n"),
            ("inventory/services/tmp-service-layer.sops.yaml", "existing\n"),
            ("inventory/services/tmp-service-layer-native.yaml", "existing\n"),
        ]
        for relative_path, content in generated_paths:
            with self.subTest(relative_path=relative_path), tempfile.TemporaryDirectory() as tmp:
                root, calls_log = self._fixture(tmp)
                (root / relative_path).write_text(content)
                env = self._workflow_env(root, calls_log)

                result = subprocess.run(
                    [
                        str(REPO_ROOT / "scripts" / "acceptance-service-layer"),
                        "host=wintermute",
                        "template=debian-13-base",
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
            "keep": ({"FORTRESS_FAIL_PHASE": "ssh", "KEEP": "true"}, "preserved Service-layer acceptance resources"),
            "cleanup": ({"FORTRESS_FAIL_PHASE": "ssh", "FORTRESS_CLEANUP_FAIL_PHASE": "vm-destroy"}, "cleanup also failed"),
        }
        for scenario, (overrides, message) in scenarios.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                root, calls_log = self._fixture(tmp)
                env = self._workflow_env(root, calls_log)
                env.update(overrides)
                args = [
                    str(REPO_ROOT / "scripts" / "acceptance-service-layer"),
                    "host=wintermute",
                    "template=debian-13-base",
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
                    service_yaml = (root / "inventory" / "services" / "tmp-service-layer.yaml").read_text()
                    self.assertIn("backend:\n  vm: tmp-service-primary\n  port: 8080", service_yaml)
                    self.assertIn("bind: 0.0.0.0", service_yaml)
                    self.assertIn("depends_on: [postgres, redis]", service_yaml)
                    self.assertIn("mount: service-layer", service_yaml)
                    self.assertIn("service_path: web", service_yaml)
                    self.assertIn("secret: secrets.acceptance_token", service_yaml)
                    service_sops = (root / "inventory" / "services" / "tmp-service-layer.sops.yaml").read_text()
                    self.assertIn("acceptance_token:\n", service_sops)
                    self.assertIn("created: 2026-05-12T00:00:00Z\n", service_sops)
                    self.assertIn("version: 1\n", service_sops)
                    self.assertIn("value: generated-service-layer-acceptance-token\n", service_sops)
                    native_service_yaml = (root / "inventory" / "services" / "tmp-service-layer-native.yaml").read_text()
                    self.assertIn("type: native", native_service_yaml)
                    self.assertIn("package: caddy", native_service_yaml)
                    self.assertIn("port: 18080", native_service_yaml)
                    primary_yaml = (root / "inventory" / "vms" / "tmp-service-primary.yaml").read_text()
                    self.assertIn("purpose: service-layer-acceptance", primary_yaml)
                    self.assertIn("dataset: acceptance-service-layer", primary_yaml)
                    self.assertIn("mount_point: /mnt/service-layer", primary_yaml)
                    dataset_yaml = (root / "inventory" / "datasets" / "acceptance-service-layer.yaml").read_text()
                    self.assertIn("name: acceptance-service-layer", dataset_yaml)
                    self.assertIn("nas: truenas", dataset_yaml)
                    self.assertIn("path: /mnt/tank/fortress-acceptance/service-layer", dataset_yaml)
                    self.assertIn("lifecycle: ephemeral", dataset_yaml)

    def test_reload_failure_reports_reload_phase_and_obeys_keep_on_fail(self):
        scenarios = {
            "cleanup": ([], "TrueNAS NFS service reload failed", True),
            "keep": (["keep_on_fail=true"], "preserved Service-layer acceptance resources", False),
        }
        for scenario, (extra_args, message, should_cleanup) in scenarios.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                root, calls_log = self._fixture(tmp)
                env = self._workflow_env(root, calls_log)
                env["FORTRESS_FAKE_TRUENAS_RELOAD_FAIL"] = "1"

                result = subprocess.run(
                    [
                        str(REPO_ROOT / "scripts" / "acceptance-service-layer"),
                        "host=wintermute",
                        "template=debian-13-base",
                        "endpoint=truenas",
                        "auto_confirm=true",
                        *extra_args,
                    ],
                    cwd=REPO_ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)
                self.assertIn("truenas reload_nfs_service truenas 10.10.0.15 true acceptance-secret-token", calls_log.read_text())
                if should_cleanup:
                    self.assertIn("vm-destroy tmp-service-primary --delete-vm-yaml", calls_log.read_text())
                    self.assertFalse((root / "inventory" / "services" / "tmp-service-layer.yaml").exists())
                else:
                    self.assertNotIn("vm-destroy tmp-service-primary --delete-vm-yaml", calls_log.read_text())
                    self.assertTrue((root / "inventory" / "services" / "tmp-service-layer.yaml").exists())

    def test_reload_uses_selected_fortress_python_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._fixture(tmp)
            fake_python = root / "bin" / "fortress-python"
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                "printf 'fortress-python %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
                "printf 'reload-token=%s\\n' \"$FORTRESS_SERVICE_LAYER_ACCEPTANCE_NAS_TOKEN\" >> \"$CALLS_LOG\"\n"
            )
            fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)
            env = self._workflow_env(root, calls_log)
            env.pop("FORTRESS_FAKE_TRUENAS_RELOAD_LOG")
            env["FORTRESS_PYTHON"] = str(fake_python)

            result = subprocess.run(
                [
                    str(REPO_ROOT / "scripts" / "acceptance-service-layer"),
                    "host=wintermute",
                    "template=debian-13-base",
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
            calls = calls_log.read_text()
            self.assertIn(
                f"fortress-python {REPO_ROOT / 'scripts' / 'acceptance-service-layer'} __reload-truenas-nfs-service truenas 10.10.0.15 true",
                calls,
            )
            self.assertIn("reload-token=acceptance-secret-token", calls)

    def test_static_policy_dataset_recipe_and_runbook_document_workflow(self):
        policy = (REPO_ROOT / "inventory" / "acceptance" / "service-layer.yaml").read_text()
        justfile = (REPO_ROOT / "justfile").read_text()
        runbook = (REPO_ROOT / "runbooks" / "new-service.md").read_text()

        self.assertIn("dataset: acceptance-service-layer", policy)
        self.assertIn("tmp-service-primary", policy)
        self.assertIn("tmp-service-peer", policy)
        self.assertFalse((REPO_ROOT / "inventory" / "datasets" / "acceptance-service-layer.yaml").exists())
        self.assertIn('acceptance-service-layer host template endpoint auto_confirm="false" keep_on_fail="false":', justfile)
        self.assertIn("./scripts/acceptance-service-layer", justfile)
        self.assertIn("just acceptance-service-layer host=<host> template=<template> endpoint=<nas-endpoint>", runbook)
        self.assertIn("Primary Acceptance VM", runbook)
        self.assertIn("Peer Acceptance VM", runbook)
        self.assertIn("Native Service", runbook)
        self.assertIn("keep_on_fail=true", runbook)

    def _fixture(self, tmp):
        root = Path(tmp)
        inventory = root / "inventory"
        scripts = root / "scripts"
        for subdir in ["acceptance", "hosts", "templates", "vms", "datasets", "nas", "services"]:
            (inventory / subdir).mkdir(parents=True, exist_ok=True)
        scripts.mkdir()
        (inventory / "acceptance" / "service-layer.yaml").write_text(
            "dataset: acceptance-service-layer\n"
            "mount:\n"
            "  name: service-layer\n"
            "  mount_point: /mnt/service-layer\n"
            "  access: read_write\n"
            "hardware:\n"
            "  cores: 1\n"
            "  memory: 1024\n"
            "  disk_size: 8G\n"
            "storage_by_host:\n"
            "  wintermute: fast\n"
            "vms:\n"
            "  primary:\n"
            "    name: tmp-service-primary\n"
            "    vmid: 8921\n"
            "    address_by_host:\n"
            "      wintermute: 10.10.0.233/24\n"
            "  peer:\n"
            "    name: tmp-service-peer\n"
            "    vmid: 8922\n"
            "    address_by_host:\n"
            "      wintermute: 10.10.0.234/24\n"
        )
        (inventory / "hosts" / "wintermute.yaml").write_text(
            "proxmox:\n"
            "  templates: [debian-13-base]\n"
            "network:\n"
            "  bridges:\n"
            "    - name: vmbr0\n"
            "      cidr: 10.10.0.11/24\n"
            "      gateway: 10.10.0.1\n"
        )
        (inventory / "templates" / "debian-13-base.yaml").write_text("name: debian-13-base\nvmid: 9001\n")
        (inventory / "nas" / "truenas.yaml").write_text("name: truenas\nmanagement_address: 10.10.0.15\nshare_address: 10.40.0.15\n")
        (inventory / "nas" / "truenas.sops.yaml").write_text("api_credentials:\n  acceptance:\n    value: acceptance-secret-token\n")
        calls_log = root / "calls.log"
        self._write_fake_tools(root, calls_log)
        return root, calls_log

    def _write_fake_tools(self, root, calls_log):
        scripts = root / "scripts"
        for name in ["vm-up", "vm-destroy", "service-deploy"]:
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
            "if [[ \"$*\" != *--destroy-ephemeral-datasets* ]]; then python3 - <<'PY'\n"
            "import os, pathlib, sys\n"
            "dataset = pathlib.Path(os.environ['FORTRESS_ROOT']) / 'inventory' / 'datasets' / 'acceptance-service-layer.yaml'\n"
            "expected = '# Generated Service-layer Acceptance Dataset. Do not edit by hand.\\nname: acceptance-service-layer\\nnas: truenas\\npath: /mnt/tank/fortress-acceptance/service-layer\\nlifecycle: ephemeral\\n'\n"
            "if not dataset.is_file():\n"
            "    print(f'missing generated dataset {dataset}', file=sys.stderr)\n"
            "    sys.exit(42)\n"
            "if dataset.read_text() != expected:\n"
            "    print(f'unexpected generated dataset contents: {dataset.read_text()!r}', file=sys.stderr)\n"
            "    sys.exit(42)\n"
            "PY\n"
            "fi\n"
            "if [[ \"$*\" == *--destroy-ephemeral-datasets* ]]; then python3 - <<'PY'\n"
            "import json\n"
            "print(json.dumps({'write_actions': [{'action': 'delete_nfs_share', 'share': 'fortress-nfs-acceptance-service-layer-read-write'}, {'action': 'delete_dataset', 'dataset': 'acceptance-service-layer'}], 'api_operations': [], 'destroy_postcondition_findings': []}))\n"
            "PY\n"
            "exit 0\n"
            "fi\n"
            "python3 - <<'PY'\n"
            "import json\n"
            "print(json.dumps({'desired_nfs_shares': [{'name': 'fortress-nfs-acceptance-service-layer-read-write', 'dataset': 'acceptance-service-layer', 'protocol': 'nfs', 'access': 'read_write', 'clients': ['10.10.0.233', '10.10.0.234']}]}))\n"
            "PY\n"
        )
        (scripts / "nas-reconcile-plan").chmod((scripts / "nas-reconcile-plan").stat().st_mode | stat.S_IXUSR)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        (bin_dir / "sops").write_text(
            "#!/usr/bin/env bash\n"
            "printf 'sops %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
            "if [ \"$1\" = \"--decrypt\" ]; then echo acceptance-secret-token; fi\n"
        )
        (bin_dir / "sops").chmod((bin_dir / "sops").stat().st_mode | stat.S_IXUSR)
        (bin_dir / "ansible-inventory").write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "with open(os.environ['CALLS_LOG'], 'a') as log:\n"
            "    log.write('ansible-inventory ' + ' '.join(sys.argv[1:]) + '\\n')\n"
            "print(json.dumps({'_meta': {'hostvars': {'tmp-service-primary': {'ansible_host': '10.10.0.233', 'ansible_ssh_private_key_file': '/dev/shm/fortress/tmp-service-primary.key'}, 'tmp-service-peer': {'ansible_host': '10.10.0.234', 'ansible_ssh_private_key_file': '/dev/shm/fortress/tmp-service-peer.key'}}}}))\n"
        )
        (bin_dir / "ansible-inventory").chmod((bin_dir / "ansible-inventory").stat().st_mode | stat.S_IXUSR)
        (bin_dir / "ssh").write_text(
            "#!/usr/bin/env bash\n"
            "printf 'ssh %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
            "if [ \"$FORTRESS_FAIL_PHASE\" = ssh ]; then echo 'verification failed intentionally' >&2; exit 42; fi\n"
            "case \"$*\" in\n"
            "  *'sha256sum'*) echo '" + hashlib.sha256(b"generated-service-layer-acceptance-token").hexdigest() + "' ;;\n"
            "  *'cat /mnt/service-layer/post-reload-marker.txt'*) echo post-reload-service-layer-marker ;;\n"
            "  *'curl -fsS http://10.10.0.233:8080/'*)\n"
            "    if [ -f \"$FORTRESS_POST_RELOAD_CURL\" ]; then echo post-reload-service-layer-content; else touch \"$FORTRESS_POST_RELOAD_CURL\"; echo service-layer-marker; fi ;;\n"
            "  *'curl -fsS http://10.10.0.233:18080/'*) echo native-service-layer-marker ;;\n"
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
        env["FORTRESS_SERVICE_LAYER_MARKER"] = "service-layer-marker"
        env["FORTRESS_POST_RELOAD_CURL"] = str(root / "post-reload-curl-seen")
        env["FORTRESS_FAKE_TRUENAS_RELOAD_LOG"] = str(calls_log)
        return env


if __name__ == "__main__":
    unittest.main()
