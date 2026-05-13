import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from fortress_inventory.model import load_inventory_tree
from fortress_services.deploy import quadlet_deploy_vars


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
            service_sops.write_text("encrypted service secret material\n")
            self._fake_sops(
                root / "bin" / "sops",
                calls_log,
                "secrets:\n"
                "  db_password:\n"
                "    created: 2026-05-12T00:00:00Z\n"
                "    version: 1\n"
                "    value: structured-db-password\n",
            )
            env["PATH"] = f"{root / 'bin'}:{env['PATH']}"

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
                        "sops_extract": '["secrets"]["db_password"]["value"]',
                    }
                ],
                extra_vars["fortress_service_secrets"],
            )

    def test_service_deploy_rejects_scalar_legacy_service_secret_before_remote_playbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["cp", "-R", str(FIXTURES / "inventory_valid") + "/.", str(root)], check=True)
            scripts_dir = root / "scripts"
            scripts_dir.mkdir(exist_ok=True)
            calls_log = root / "calls.log"
            self._fake_decrypt_keys(scripts_dir / "decrypt-keys", calls_log)
            self._fake_sops(
                root / "bin" / "sops",
                calls_log,
                "secrets:\n"
                "  db_password: do-not-print-this-legacy-secret\n",
            )
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
            (root / "inventory" / "services" / "immich.sops.yaml").write_text("encrypted service secret material\n")
            env = os.environ.copy()
            env["FORTRESS_ROOT"] = str(root)
            env["CALLS_LOG"] = str(calls_log)
            env["PATH"] = f"{root / 'bin'}:{env['PATH']}"

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "service-deploy"), "immich"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("Service Secret secrets.db_password", result.stderr)
            self.assertIn("structured entry", result.stderr)
            self.assertNotIn("do-not-print-this-legacy-secret", result.stderr)
            self.assertNotIn("ansible-playbook", calls_log.read_text())

    def test_service_deploy_preflight_reports_missing_structured_service_secret_fields(self):
        cases = {
            "missing_entry": (
                "secrets:\n"
                "  other_password:\n"
                "    created: 2026-05-12T00:00:00Z\n"
                "    version: 1\n"
                "    value: do-not-print-other\n",
                "missing Service Secret secrets.db_password",
            ),
            "missing_created": (
                "secrets:\n"
                "  db_password:\n"
                "    version: 1\n"
                "    value: do-not-print-password\n",
                "missing required field(s): created",
            ),
            "missing_version": (
                "secrets:\n"
                "  db_password:\n"
                "    created: 2026-05-12T00:00:00Z\n"
                "    value: do-not-print-password\n",
                "missing required field(s): version",
            ),
            "missing_value": (
                "secrets:\n"
                "  db_password:\n"
                "    created: 2026-05-12T00:00:00Z\n"
                "    version: 1\n",
                "missing required field(s): value",
            ),
        }
        for scenario, (decrypted, expected_error) in cases.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                subprocess.run(["cp", "-R", str(FIXTURES / "inventory_valid") + "/.", str(root)], check=True)
                scripts_dir = root / "scripts"
                scripts_dir.mkdir(exist_ok=True)
                calls_log = root / "calls.log"
                self._fake_decrypt_keys(scripts_dir / "decrypt-keys", calls_log)
                self._fake_sops(root / "bin" / "sops", calls_log, decrypted)
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
                (root / "inventory" / "services" / "immich.sops.yaml").write_text("encrypted service secret material\n")
                env = os.environ.copy()
                env["FORTRESS_ROOT"] = str(root)
                env["CALLS_LOG"] = str(calls_log)
                env["PATH"] = f"{root / 'bin'}:{env['PATH']}"

                result = subprocess.run(
                    [str(REPO_ROOT / "scripts" / "service-deploy"), "immich"],
                    cwd=REPO_ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                self.assertEqual(result.returncode, 1)
                self.assertIn(expected_error, result.stderr)
                self.assertNotIn("do-not-print", result.stderr)
                self.assertNotIn("ansible-playbook", calls_log.read_text())

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
        self.assertIn("stdin_add_newline: false", playbook)

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
                ["ghcr.io/immich-app/immich-server:v1.120.0", "postgres:16"],
                extra_vars["fortress_service_container_images"],
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

    def test_service_deploy_renders_pihole_dnsmasq_d_compatibility_for_ingress_dns_targets(self):
        model = load_inventory_tree(REPO_ROOT)
        service = model.services["dns-primary"]
        vm = model.vms["dns-primary-vm"]

        deploy_vars = quadlet_deploy_vars(service, vm, inventory_root=REPO_ROOT / "inventory")
        pihole_artifact = next(
            artifact
            for artifact in deploy_vars["fortress_quadlet_artifacts"]
            if artifact["filename"] == "fortress-dns-primary-pihole.container"
        )

        self.assertIn("Environment=FTLCONF_misc_etc_dnsmasq_d=true\n", pihole_artifact["content"])

    def test_internal_ingress_service_deploy_scaffolding_imports_generated_routes(self):
        caddyfile = (REPO_ROOT / "inventory" / "services" / "internal-ingress.native.d" / "Caddyfile.j2").read_text()

        self.assertIn("admin {$CADDY_ADMIN}", caddyfile)
        self.assertIn("import /etc/caddy/fortress/generated-routes.caddy", caddyfile)
        self.assertNotIn("forgejo.fearn.cloud {", caddyfile)
        self.assertNotIn("reverse_proxy 10.", caddyfile)

    def test_service_deploy_passes_native_package_repo_unit_and_config_files_to_playbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["cp", "-R", str(FIXTURES / "inventory_valid") + "/.", str(root)], check=True)
            scripts_dir = root / "scripts"
            scripts_dir.mkdir(exist_ok=True)
            calls_log = root / "calls.log"
            self._fake_decrypt_keys(scripts_dir / "decrypt-keys", calls_log)
            (root / "inventory" / "group_vars" / "all.yaml").write_text(
                "domain: fearn.cloud\n"
                "nas:\n"
                "  default_options:\n"
                "    - nfsvers=4.2\n"
                "apt_repos:\n"
                "  caddy_official:\n"
                "    url: https://dl.cloudsmith.io/public/caddy/stable/deb/debian\n"
            )
            (root / "inventory" / "vms" / "media01.sops.yaml").write_text("encrypted vm material\n")
            template_dir = root / "inventory" / "services" / "caddy.native.d"
            template_dir.mkdir()
            (template_dir / "Caddyfile.j2").write_text(":80 { respond \"ok\" }\n")
            (template_dir / "caddy.env.j2").write_text("CADDY_ADMIN=localhost:2019\n")
            (root / "inventory" / "services" / "caddy.yaml").write_text(
                "name: caddy\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 80\n"
                "deploy:\n"
                "  type: native\n"
                "  package: caddy\n"
                "  apt_repo: caddy_official\n"
                "  service_name: caddy\n"
                "  config_files:\n"
                "    - template: Caddyfile.j2\n"
                "      dest: /etc/caddy/Caddyfile\n"
                "      mode: '0644'\n"
                "      reload_on_change: true\n"
                "    - template: caddy.env.j2\n"
                "      dest: /etc/default/caddy\n"
                "      mode: '0600'\n"
                "      restart_on_change: true\n"
            )
            env = os.environ.copy()
            env["FORTRESS_ROOT"] = str(root)
            env["CALLS_LOG"] = str(calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "service-deploy"), "caddy"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            extra_vars = json.loads(calls_log.read_text().split("--extra-vars ", 1)[1])
            self.assertEqual("native", extra_vars["fortress_service_deploy_type"])
            self.assertEqual("caddy", extra_vars["fortress_native_package"])
            self.assertEqual("caddy", extra_vars["fortress_native_systemd_unit"])
            self.assertEqual(
                {
                    "name": "caddy_official",
                    "url": "https://dl.cloudsmith.io/public/caddy/stable/deb/debian",
                },
                extra_vars["fortress_native_apt_repo"],
            )
            self.assertEqual(
                [
                    {
                        "src": str(template_dir / "Caddyfile.j2"),
                        "dest": "/etc/caddy/Caddyfile",
                        "mode": "0644",
                        "action": "reload",
                    },
                    {
                        "src": str(template_dir / "caddy.env.j2"),
                        "dest": "/etc/default/caddy",
                        "mode": "0600",
                        "action": "restart",
                    },
                ],
                extra_vars["fortress_native_config_files"],
            )
            self.assertNotIn("fortress_quadlet_artifacts", extra_vars)

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
        self.assertLess(
            playbook.index("name: Pull Service container images before systemd starts units"),
            playbook.index("name: Stop Service containers in reverse dependency order"),
        )
        self.assertLess(
            playbook.index("name: Pull Service container images before systemd starts units"),
            playbook.index("name: Start Service containers in dependency order"),
        )
        self.assertLess(
            playbook.index("name: Enable Service Quadlet units for boot"),
            playbook.index("name: Start Service networks before containers"),
        )
        self.assertIn("enabled: true", playbook)
        self.assertIn("podman image pull {{ item }}", playbook)
        self.assertIn("systemctl start {{ item }}", deploy_workflow)
        self.assertIn("name: Wait briefly for Service container early exits", deploy_workflow)
        self.assertIn("systemctl is-active --quiet {{ item }}", deploy_workflow)
        self.assertIn("until: fortress_service_unit_active.rc == 0", deploy_workflow)
        self.assertIn("Failed to start or keep {{ item }} active", deploy_workflow)
        self.assertIn("journalctl -u {{ item }}", deploy_workflow)
        self.assertNotIn("/srv/services/{{ deploy_service }}", deploy_workflow)

    def test_service_deploy_playbook_installs_native_packages_templates_configs_and_reloads_or_restarts(self):
        playbook = (REPO_ROOT / "ansible" / "playbooks" / "service-deploy.yml").read_text()

        self.assertIn("name: Configure Native Service apt repository", playbook)
        self.assertIn("name: Ensure Native Service apt repository tooling is installed", playbook)
        self.assertIn("name: gnupg", playbook)
        self.assertIn("fortress_native_apt_repo", playbook)
        self.assertIn("name: Install Native Service package", playbook)
        self.assertIn("name: Render Native Service config files", playbook)
        self.assertIn("loop: \"{{ fortress_native_config_files | default([]) }}\"", playbook)
        self.assertIn("src: \"{{ item.src }}\"", playbook)
        self.assertIn("dest: \"{{ item.dest }}\"", playbook)
        self.assertIn("mode: \"{{ item.mode }}\"", playbook)
        self.assertIn("name: Restart Native Service after restart-marked config changes", playbook)
        self.assertIn("name: Reload Native Service after reload-only config changes", playbook)
        self.assertIn("fortress_service_start_units | default([])", playbook)
        self.assertIn("fortress_service_stop_units | default([])", playbook)
        self.assertIn("systemctl restart {{ fortress_native_systemd_unit }}", playbook)
        self.assertIn("systemctl reload {{ fortress_native_systemd_unit }}", playbook)
        self.assertIn("selectattr('item.action', 'equalto', 'restart')", playbook)
        self.assertIn("selectattr('item.action', 'equalto', 'reload')", playbook)
        self.assertLess(
            playbook.index("name: Ensure Native Service apt repository tooling is installed"),
            playbook.index("name: Configure Native Service apt repository"),
        )
        self.assertLess(
            playbook.index("name: Restart Native Service after restart-marked config changes"),
            playbook.index("name: Reload Native Service after reload-only config changes"),
        )
        self.assertIn("fortress_native_restart_needed | default(false) | bool", playbook)
        self.assertIn("not (fortress_native_restart_needed | default(false) | bool)", playbook)

    def _fake_decrypt_keys(self, path, calls_log):
        path.write_text(
            "#!/usr/bin/env bash\n"
            "shift 2\n"
            "printf '%s ' \"$@\" > \"$CALLS_LOG\"\n"
        )
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def _fake_sops(self, path, calls_log, decrypted):
        path.parent.mkdir(exist_ok=True)
        path.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'sops %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
            "if [ \"$1\" = \"--decrypt\" ]; then\n"
            "  cat <<'YAML'\n"
            f"{decrypted}"
            "YAML\n"
            "fi\n"
        )
        path.chmod(path.stat().st_mode | stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()
