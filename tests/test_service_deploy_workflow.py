import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"


class ServiceDeployWorkflowTests(unittest.TestCase):
    def test_just_service_deploy_calls_workflow_script(self):
        justfile = (REPO_ROOT / "justfile").read_text()

        self.assertIn("service-deploy service:", justfile)
        self.assertIn("./scripts/service-deploy {{service}}", justfile)

    def test_service_deploy_passes_share_backed_subpaths_to_playbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["cp", "-R", str(FIXTURES / "inventory_valid") + "/.", str(root)], check=True)
            scripts_dir = root / "scripts"
            scripts_dir.mkdir(exist_ok=True)
            calls_log = root / "calls.log"
            self._fake_decrypt_keys(scripts_dir / "decrypt-keys", calls_log)
            (root / "inventory" / "vms" / "media01.sops.yaml").write_text("encrypted vm material\n")
            (root / "inventory" / "services" / "immich.yaml").write_text(
                "name: immich\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 2283\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: server\n"
                "      image: ghcr.io/immich-app/immich-server:v1.120.0\n"
                "      volumes:\n"
                "        - mount: media\n"
                "          source: photos\n"
                "          container: /photos\n"
                "          access: read_only\n"
            )
            env = os.environ.copy()
            env["FORTRESS_ROOT"] = str(root)
            env["CALLS_LOG"] = str(calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "service-deploy"), "immich"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            command = calls_log.read_text()
            self.assertIn("ansible-playbook", command)
            self.assertIn("service-deploy.yml", command)
            extra_vars = json.loads(command.split("--extra-vars ", 1)[1])
            self.assertEqual("media01", extra_vars["deploy_service_backend_vm"])
            self.assertEqual(["/mnt/nas/media/photos"], extra_vars["fortress_share_backed_volume_subpaths"])
            self.assertNotIn("fortress_service_sops_file", extra_vars)
            self.assertEqual([], extra_vars["fortress_service_secrets"])

    def test_service_deploy_requires_service_sibling_sops_file_only_when_service_secrets_are_declared(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["cp", "-R", str(FIXTURES / "inventory_valid") + "/.", str(root)], check=True)
            scripts_dir = root / "scripts"
            scripts_dir.mkdir(exist_ok=True)
            calls_log = root / "calls.log"
            self._fake_decrypt_keys(scripts_dir / "decrypt-keys", calls_log)
            (root / "inventory" / "vms" / "media01.sops.yaml").write_text("encrypted vm material\n")
            (root / "inventory" / "services" / "immich.yaml").write_text(
                "name: immich\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 2283\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: server\n"
                "      image: ghcr.io/immich-app/immich-server:v1.120.0\n"
                "      secrets:\n"
                "        - secret: secrets.db_password\n"
                "          env: IMMICH_DB_PASSWORD_FILE\n"
            )
            env = os.environ.copy()
            env["FORTRESS_ROOT"] = str(root)
            env["CALLS_LOG"] = str(calls_log)

            missing = subprocess.run(
                [str(REPO_ROOT / "scripts" / "service-deploy"), "immich"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(missing.returncode, 1)
            self.assertIn("Service Sibling SOPS File is required", missing.stderr)

            service_sops = root / "inventory" / "services" / "immich.sops.yaml"
            service_sops.write_text("secrets:\n  db_password: encrypted\n")

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "service-deploy"), "immich"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            extra_vars = json.loads(calls_log.read_text().split("--extra-vars ", 1)[1])
            self.assertEqual(str(service_sops), extra_vars["fortress_service_sops_file"])
            self.assertEqual(
                [
                    {
                        "podman_name": "fortress_immich_db_password",
                        "sops_extract": '["secrets"]["db_password"]',
                    }
                ],
                extra_vars["fortress_service_secrets"],
            )

    def test_service_deploy_playbook_validates_subpaths_before_starting_containers(self):
        playbook = (REPO_ROOT / "ansible" / "playbooks" / "service-deploy.yml").read_text()

        self.assertIn("become: true", playbook)
        self.assertLess(
            playbook.index("name: Validate Share-backed Volume subpaths"),
            playbook.index("name: Start Service containers"),
        )

    def test_service_deploy_playbook_installs_service_secrets_before_starting_containers(self):
        playbook = (REPO_ROOT / "ansible" / "playbooks" / "service-deploy.yml").read_text()

        self.assertLess(
            playbook.index("name: Ensure Podman is installed for Quadlet Services"),
            playbook.index("name: Install Service Secrets as Podman secrets"),
        )
        self.assertLess(
            playbook.index("name: Remove Service Secrets before replacement"),
            playbook.index("name: Install Service Secrets as Podman secrets"),
        )
        self.assertLess(
            playbook.index("name: Install Service Secrets as Podman secrets"),
            playbook.index("name: Start Service containers"),
        )
        self.assertIn("no_log: true", playbook)
        self.assertIn("podman secret rm", playbook)
        self.assertIn("podman secret create", playbook)

    def test_service_deploy_passes_rendered_artifacts_and_restart_order_to_playbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["cp", "-R", str(FIXTURES / "inventory_valid") + "/.", str(root)], check=True)
            scripts_dir = root / "scripts"
            scripts_dir.mkdir(exist_ok=True)
            calls_log = root / "calls.log"
            self._fake_decrypt_keys(scripts_dir / "decrypt-keys", calls_log)
            (root / "inventory" / "vms" / "media01.sops.yaml").write_text("encrypted vm material\n")
            (root / "inventory" / "services" / "immich.yaml").write_text(
                "name: immich\n"
                "service_group: media\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 2283\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: server\n"
                "      image: ghcr.io/immich-app/immich-server:v1.120.0\n"
                "      depends_on: [postgres]\n"
                "    - name: postgres\n"
                "      image: postgres:16\n"
            )
            env = os.environ.copy()
            env["FORTRESS_ROOT"] = str(root)
            env["CALLS_LOG"] = str(calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "service-deploy"), "immich"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            extra_vars = json.loads(calls_log.read_text().split("--extra-vars ", 1)[1])
            self.assertEqual(
                ["fortress-group-media.network", "fortress-immich-server.container", "fortress-immich-postgres.container"],
                [artifact["filename"] for artifact in extra_vars["fortress_quadlet_artifacts"]],
            )
            self.assertEqual(
                ["fortress-group-media-network.service"],
                extra_vars["fortress_service_network_units"],
            )
            self.assertEqual(
                ["fortress-immich-postgres.service", "fortress-immich-server.service"],
                extra_vars["fortress_service_start_units"],
            )
            self.assertEqual(
                ["fortress-immich-server.service", "fortress-immich-postgres.service"],
                extra_vars["fortress_service_stop_units"],
            )
            self.assertEqual(
                ["/etc/containers/systemd/fortress-immich-server.container", "/etc/containers/systemd/fortress-immich-postgres.container"],
                extra_vars["fortress_owned_quadlet_prune_paths"],
            )
            self.assertEqual("fortress_immich_", extra_vars["fortress_service_secret_prefix"])

    def test_service_deploy_playbook_prunes_restarts_and_reports_start_failures(self):
        playbook = (REPO_ROOT / "ansible" / "playbooks" / "service-deploy.yml").read_text()
        start_tasks = (REPO_ROOT / "ansible" / "tasks" / "service-start-unit.yml").read_text()
        deploy_workflow = playbook + "\n" + start_tasks

        self.assertIn("name: Find obsolete fortress-rendered container Quadlets for selected Service", playbook)
        self.assertIn("patterns: \"fortress-{{ deploy_service }}-*.container\"", playbook)
        self.assertIn("fortress_owned_quadlet_prune_paths", playbook)
        self.assertIn("name: List fortress-owned Podman secrets for selected Service", playbook)
        self.assertIn("{{ fortress_service_secret_prefix }}", playbook)
        self.assertLess(
            playbook.index("name: Stop Service containers in reverse dependency order"),
            playbook.index("name: Start Service networks before containers"),
        )
        self.assertLess(
            playbook.index("name: Start Service networks before containers"),
            playbook.index("name: Start Service containers in dependency order"),
        )
        self.assertIn("systemctl start {{ item }}", deploy_workflow)
        self.assertIn("Failed to start {{ item }}", deploy_workflow)
        self.assertIn("journalctl -u {{ item }}", deploy_workflow)
        self.assertNotIn("/srv/services/{{ deploy_service }}", deploy_workflow)

    def _fake_decrypt_keys(self, path, calls_log):
        path.write_text(
            "#!/usr/bin/env bash\n"
            "shift 2\n"
            "printf '%s ' \"$@\" > \"$CALLS_LOG\"\n"
        )
        path.chmod(path.stat().st_mode | stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()
