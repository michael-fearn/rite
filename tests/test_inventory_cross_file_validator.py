import shutil
import tempfile
import unittest
from pathlib import Path

from fortress_inventory.model import load_inventory_tree
from fortress_inventory.validate import validate_inventory_tree


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"


class InventoryCrossFileValidatorTests(unittest.TestCase):
    def codes_for(self, fixture_name):
        errors = validate_inventory_tree(FIXTURES / fixture_name)
        return {error.code for error in errors}

    def test_valid_inventory_tree_has_no_cross_file_errors(self):
        self.assertEqual(validate_inventory_tree(FIXTURES / "inventory_valid"), [])

    def test_inventory_model_loads_template_verification_policy(self):
        model = load_inventory_tree(REPO_ROOT)

        self.assertEqual(model.template_verification_policy["vmid"], 8901)

    def test_inventory_model_loads_datasets(self):
        model = load_inventory_tree(FIXTURES / "inventory_valid")

        self.assertEqual(model.datasets["media"]["path"], "/mnt/pool/media")

    def test_repo_media_vm_declares_media_service_group_launch_order(self):
        model = load_inventory_tree(REPO_ROOT)

        self.assertEqual(
            [
                {
                    "name": "media",
                    "launch_order": ["prowlarr", "sonarr", "radarr", "bazarr", "jellyfin", "seerr"],
                }
            ],
            model.vms["media-vm"].get("launchable_service_groups"),
        )

    def test_repo_inventory_does_not_commit_acceptance_ephemeral_datasets(self):
        model = load_inventory_tree(REPO_ROOT)

        self.assertNotIn("acceptance-nfs-demo", model.datasets)
        self.assertNotIn("acceptance-service-layer", model.datasets)
        self.assertNotIn("ordinary_ephemeral_dataset", {error.code for error in validate_inventory_tree(REPO_ROOT)})

    def test_dataset_names_must_be_unique(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "datasets" / "photos.yaml").write_text(
                "name: media\n"
                "nas: truenas\n"
                "path: /mnt/pool/photos\n"
                "lifecycle: adopted\n"
                "owner:\n"
                "  uid: 1000\n"
                "  gid: 1000\n"
            )

            self.assertIn("duplicate_dataset_name", {error.code for error in validate_inventory_tree(root)})

    def test_dataset_nas_endpoint_must_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "datasets" / "media.yaml").write_text(
                "name: media\n"
                "nas: missing-nas\n"
                "path: /mnt/pool/media\n"
                "lifecycle: adopted\n"
                "owner:\n"
                "  uid: 1000\n"
                "  gid: 1000\n"
            )

            self.assertIn("missing_dataset_nas_endpoint", {error.code for error in validate_inventory_tree(root)})

    def test_ordinary_inventory_rejects_ephemeral_datasets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "datasets" / "media.yaml").write_text(
                "name: media\n"
                "nas: truenas\n"
                "path: /mnt/pool/media\n"
                "lifecycle: ephemeral\n"
            )

            self.assertIn("ordinary_ephemeral_dataset", {error.code for error in validate_inventory_tree(root)})

    def test_acceptance_inventory_allows_ephemeral_datasets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "datasets" / "media.yaml").write_text(
                "name: media\n"
                "nas: truenas\n"
                "path: /mnt/pool/media\n"
                "lifecycle: ephemeral\n"
            )

            codes = {error.code for error in validate_inventory_tree(root, allow_ephemeral_datasets=True)}
            self.assertNotIn("ordinary_ephemeral_dataset", codes)

    def test_acceptance_policy_reference_allows_ephemeral_dataset_in_repo_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "acceptance").mkdir()
            (root / "inventory" / "datasets" / "media.yaml").write_text(
                "name: acceptance-media\n"
                "nas: truenas\n"
                "path: /mnt/pool/fortress-acceptance/media\n"
                "lifecycle: ephemeral\n"
            )
            (root / "inventory" / "acceptance" / "nfs-shared-mount.yaml").write_text(
                "dataset: acceptance-media\n"
            )

            codes = {error.code for error in validate_inventory_tree(root)}
            self.assertNotIn("ordinary_ephemeral_dataset", codes)

    def test_service_backend_vm_must_exist(self):
        self.assertIn("missing_service_backend_vm", self.codes_for("inventory_invalid/missing-service-vm"))

    def test_backend_ports_must_not_collide_on_same_vm(self):
        self.assertIn("backend_port_collision", self.codes_for("inventory_invalid/port-collision"))

    def test_service_hostnames_must_be_unique(self):
        self.assertIn("duplicate_service_hostname", self.codes_for("inventory_invalid/duplicate-hostname"))

    def test_service_hostname_does_not_enable_ingress_implicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            service_path = root / "inventory" / "services" / "immich.yaml"
            service_path.write_text(
                "name: immich\n"
                "hostname: photos.fearn.cloud\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 2283\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: server\n"
                "      image: ghcr.io/immich-app/immich-server:v1.120.0\n"
            )

            model = load_inventory_tree(root)

            self.assertEqual({"enabled": False}, model.services["immich"]["ingress"])
            self.assertNotIn("missing_ingress_hostname", {error.code for error in validate_inventory_tree(root)})

    def test_service_ingress_block_requires_explicit_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "services" / "immich.yaml").write_text(
                "name: immich\n"
                "hostname: photos.fearn.cloud\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 2283\n"
                "ingress:\n"
                "  exposure: lan_only\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: server\n"
                "      image: ghcr.io/immich-app/immich-server:v1.120.0\n"
            )

            self.assertIn("missing_service_ingress_enabled", {error.code for error in validate_inventory_tree(root)})

    def test_service_hostname_requires_ingress_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_service(root, "immich", hostname="photos.fearn.cloud", ingress_enabled=False)

            self.assertIn("service_hostname_without_ingress", {error.code for error in validate_inventory_tree(root)})

    def test_lan_only_service_ingress_hostname_must_be_explicit_fqdn_under_fleet_domain(self):
        invalid_hostnames = ["photos", "photos.example.com", "fearn.cloud", ".fearn.cloud", "photos..fearn.cloud"]
        for hostname in invalid_hostnames:
            with self.subTest(hostname=hostname), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
                self.write_fixture_service(root, "immich", hostname=hostname, ingress_enabled=True)

                self.assertIn("service_ingress_hostname_not_fleet_fqdn", {error.code for error in validate_inventory_tree(root)})

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_service(root, "immich", hostname="photos.fearn.cloud", ingress_enabled=True)

            self.assertNotIn(
                "service_ingress_hostname_not_fleet_fqdn",
                {error.code for error in validate_inventory_tree(root)},
            )

    def test_service_ingress_defaults_and_hostname_requirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            service_path = root / "inventory" / "services" / "immich.yaml"
            service_path.write_text(
                "name: immich\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 2283\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: server\n"
                "      image: ghcr.io/immich-app/immich-server:v1.120.0\n"
            )

            model = load_inventory_tree(root)

            self.assertEqual({"enabled": False}, model.services["immich"]["ingress"])
            self.assertNotIn("missing_ingress_hostname", {error.code for error in validate_inventory_tree(root)})

            service_path.write_text(service_path.read_text().replace("deploy:\n", "ingress:\n  enabled: true\ndeploy:\n"))

            self.assertIn("missing_ingress_hostname", {error.code for error in validate_inventory_tree(root)})

    def test_duplicate_hostnames_only_matter_for_ingress_enabled_services(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_service(root, "immich", hostname="photos.fearn.cloud", ingress_enabled=True)
            self.write_fixture_service(root, "photos", hostname="gallery.fearn.cloud", ingress_enabled=False)

            self.assertNotIn("duplicate_service_hostname", {error.code for error in validate_inventory_tree(root)})

            self.write_fixture_service(root, "photos", hostname="photos.fearn.cloud", ingress_enabled=True)

            self.assertIn("duplicate_service_hostname", {error.code for error in validate_inventory_tree(root)})

    def test_host_ingress_routes_require_trusted_source_range_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "hosts" / "wintermute.yaml").write_text(
                "proxmox:\n"
                "  pve_node_name: wintermute\n"
                "network:\n"
                "  management_address: 10.0.0.10\n"
                "  bridges:\n"
                "    - name: vmbr0\n"
                "      managed: false\n"
                "ingress:\n"
                "  proxmox_web_ui:\n"
                "    enabled: true\n"
                "    hostname: wintermute.fearn.cloud\n"
            )

            self.assertIn(
                "missing_host_ingress_trusted_source_ranges",
                {error.code for error in validate_inventory_tree(root)},
            )

    def test_valid_host_ingress_route_uses_operator_host_name_and_management_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "group_vars" / "all.yaml").write_text(
                "domain: fearn.cloud\n"
                "nas:\n"
                "  default_options:\n"
                "    - nfsvers=4.2\n"
                "ingress:\n"
                "  trusted_source_ranges:\n"
                "    - 10.20.0.0/24\n"
            )
            (root / "inventory" / "hosts" / "wintermute.yaml").write_text(
                "proxmox:\n"
                "  pve_node_name: pve-internal-name\n"
                "  endpoint: https://pve-api.fearn.cloud:8006\n"
                "network:\n"
                "  management_address: 10.0.0.10\n"
                "  bridges:\n"
                "    - name: vmbr0\n"
                "      managed: false\n"
                "ingress:\n"
                "  proxmox_web_ui:\n"
                "    enabled: true\n"
                "    hostname: wintermute.fearn.cloud\n"
            )

            self.assertEqual(validate_inventory_tree(root), [])

    def test_host_proxmox_endpoint_must_not_point_at_another_host_management_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "hosts" / "straylight.yaml").write_text(
                "proxmox:\n"
                "  pve_node_name: straylight\n"
                "  endpoint: https://10.0.0.12:8006\n"
                "network:\n"
                "  management_address: 10.0.0.12\n"
                "  bridges:\n"
                "    - name: vmbr0\n"
                "      managed: false\n"
            )
            (root / "inventory" / "hosts" / "neuromancer.yaml").write_text(
                "proxmox:\n"
                "  pve_node_name: neuromancer\n"
                "  endpoint: https://10.0.0.12:8006\n"
                "network:\n"
                "  management_address: 10.0.0.13\n"
                "  bridges:\n"
                "    - name: vmbr0\n"
                "      managed: false\n"
            )

            errors = validate_inventory_tree(root)

            self.assertIn("host_proxmox_endpoint_points_at_other_host", {error.code for error in errors})
            self.assertIn("duplicate_host_proxmox_endpoint", {error.code for error in errors})

    def test_acceptance_policies_must_cover_every_template_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "hosts" / "neuromancer.yaml").write_text(
                "proxmox:\n"
                "  pve_node_name: neuromancer\n"
                "  templates: [debian-13-base]\n"
                "network:\n"
                "  management_address: 10.0.0.13\n"
                "  bridges:\n"
                "    - name: vmbr0\n"
                "      managed: false\n"
            )
            (root / "inventory" / "acceptance").mkdir(exist_ok=True)
            (root / "inventory" / "acceptance" / "nfs-shared-mount.yaml").write_text(
                "dataset: acceptance-nfs-demo\n"
                "storage_by_host:\n"
                "  wintermute: fast\n"
                "vms:\n"
                "  primary:\n"
                "    address_by_host:\n"
                "      wintermute: 10.0.0.231/24\n"
            )

            errors = validate_inventory_tree(root)

            self.assertIn("missing_acceptance_policy_host_storage", {error.code for error in errors})
            self.assertIn("missing_acceptance_policy_host_address", {error.code for error in errors})

    def test_host_ingress_route_hostname_must_match_host_domain_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "group_vars" / "all.yaml").write_text(
                "domain: fearn.cloud\n"
                "nas:\n"
                "  default_options:\n"
                "    - nfsvers=4.2\n"
                "ingress:\n"
                "  trusted_source_ranges:\n"
                "    - 10.20.0.0/24\n"
            )
            (root / "inventory" / "hosts" / "wintermute.yaml").write_text(
                "proxmox:\n"
                "  pve_node_name: wintermute\n"
                "network:\n"
                "  management_address: 10.0.0.10\n"
                "  bridges:\n"
                "    - name: vmbr0\n"
                "      managed: false\n"
                "ingress:\n"
                "  proxmox_web_ui:\n"
                "    enabled: true\n"
                "    hostname: pve.fearn.cloud\n"
            )

            self.assertIn(
                "host_ingress_hostname_mismatch",
                {error.code for error in validate_inventory_tree(root)},
            )

    def test_host_ingress_route_hostname_shares_service_ingress_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "group_vars" / "all.yaml").write_text(
                "domain: fearn.cloud\n"
                "nas:\n"
                "  default_options:\n"
                "    - nfsvers=4.2\n"
                "ingress:\n"
                "  trusted_source_ranges:\n"
                "    - 10.20.0.0/24\n"
            )
            self.write_fixture_service(
                root,
                "wintermute",
                hostname="wintermute.fearn.cloud",
                ingress_enabled=True,
                port=8081,
                published_ports=["        - container: 8081\n", "          ingress: true\n"],
            )
            (root / "inventory" / "hosts" / "wintermute.yaml").write_text(
                "proxmox:\n"
                "  pve_node_name: wintermute\n"
                "network:\n"
                "  management_address: 10.0.0.10\n"
                "  bridges:\n"
                "    - name: vmbr0\n"
                "      managed: false\n"
                "ingress:\n"
                "  proxmox_web_ui:\n"
                "    enabled: true\n"
                "    hostname: wintermute.fearn.cloud\n"
            )

            self.assertIn(
                "duplicate_ingress_hostname",
                {error.code for error in validate_inventory_tree(root)},
            )

    def test_host_ingress_route_requires_management_address_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "group_vars" / "all.yaml").write_text(
                "domain: fearn.cloud\n"
                "nas:\n"
                "  default_options:\n"
                "    - nfsvers=4.2\n"
                "ingress:\n"
                "  trusted_source_ranges:\n"
                "    - 10.20.0.0/24\n"
            )
            (root / "inventory" / "hosts" / "wintermute.yaml").write_text(
                "proxmox:\n"
                "  pve_node_name: wintermute\n"
                "network:\n"
                "  bridges:\n"
                "    - name: vmbr0\n"
                "      managed: false\n"
                "ingress:\n"
                "  proxmox_web_ui:\n"
                "    enabled: true\n"
                "    hostname: wintermute.fearn.cloud\n"
            )

            self.assertIn(
                "missing_host_ingress_management_address",
                {error.code for error in validate_inventory_tree(root)},
            )

    def test_service_backend_is_singular_for_issue_07(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "services" / "immich.yaml").write_text(
                "name: immich\n"
                "backend:\n"
                "  - vm: media01\n"
                "    port: 2283\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: server\n"
                "      image: ghcr.io/immich-app/immich-server:v1.120.0\n"
            )

            self.assertIn("service_backend_not_singular", {error.code for error in validate_inventory_tree(root)})

    def test_native_service_apt_repo_reference_must_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "services" / "caddy.yaml").write_text(
                "name: caddy\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 80\n"
                "deploy:\n"
                "  type: native\n"
                "  package: caddy\n"
                "  apt_repo: missing_repo\n"
                "  service_name: caddy\n"
                "  config_files:\n"
                "    - template: Caddyfile.j2\n"
                "      dest: /etc/caddy/Caddyfile\n"
                "      mode: '0644'\n"
                "      reload_on_change: true\n"
            )

            self.assertIn("missing_native_service_apt_repo", {error.code for error in validate_inventory_tree(root)})

    def test_native_environment_secret_reference_must_be_sibling_sops_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "services" / "caddy.yaml").write_text(
                "name: caddy\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 80\n"
                "deploy:\n"
                "  type: native\n"
                "  package: caddy\n"
                "  service_name: caddy\n"
                "  environment_secrets:\n"
                "    - secret: shared.cloudflare_api_token\n"
                "      env: CLOUDFLARE_API_TOKEN\n"
                "  config_files:\n"
                "    - template: Caddyfile.j2\n"
                "      dest: /etc/caddy/Caddyfile\n"
                "      mode: '0644'\n"
                "      reload_on_change: true\n"
            )

            self.assertIn(
                "native_environment_secret_reference_not_sibling_sops_secret",
                {error.code for error in validate_inventory_tree(root)},
            )

    def test_published_ports_require_ingress_marker_and_do_not_collide_on_backend_vm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_service(root, "immich", port=2283, published_ports=["        - container: 2283\n"])

            self.assertIn("missing_ingress_published_port", {error.code for error in validate_inventory_tree(root)})

            self.write_fixture_service(
                root,
                "immich",
                port=2283,
                published_ports=["        - container: 2283\n", "          ingress: true\n"],
            )

            errors = validate_inventory_tree(root)
            self.assertNotIn("missing_ingress_published_port", {error.code for error in errors})
            self.assertEqual("127.0.0.1", load_inventory_tree(root).services["immich"]["deploy"]["containers"][0]["published_ports"][0]["bind"])
            self.assertEqual("tcp", load_inventory_tree(root).services["immich"]["deploy"]["containers"][0]["published_ports"][0]["protocol"])

            self.write_fixture_service(
                root,
                "photos",
                hostname="gallery.fearn.cloud",
                port=3000,
                published_ports=["        - host: 2283\n", "          container: 3000\n"],
            )

            self.assertIn("published_port_collision", {error.code for error in validate_inventory_tree(root)})

    def test_ingress_published_port_must_be_exactly_one_tcp_capable_backend_port(self):
        invalid_published_ports = [
            [
                "        - container: 2283\n",
                "          protocol: udp\n",
                "          ingress: true\n",
            ],
            [
                "        - container: 2283\n",
                "          ingress: true\n",
                "        - host: 2283\n",
                "          container: 8080\n",
                "          protocol: tcp_udp\n",
                "          ingress: true\n",
            ],
        ]
        for published_ports in invalid_published_ports:
            with self.subTest(published_ports=published_ports), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
                self.write_fixture_service(root, "immich", ingress_enabled=True, published_ports=published_ports)

                self.assertIn("invalid_ingress_published_port", {error.code for error in validate_inventory_tree(root)})

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_service(
                root,
                "immich",
                ingress_enabled=True,
                published_ports=[
                    "        - container: 2283\n",
                    "          protocol: tcp_udp\n",
                    "          ingress: true\n",
                ],
            )

            self.assertNotIn("invalid_ingress_published_port", {error.code for error in validate_inventory_tree(root)})

    def test_ingress_dns_target_requires_explicit_supported_dns_provider(self):
        invalid_dns_capabilities = [
            (
                "dns:\n"
                "  ingress_records:\n"
                "    enabled: true\n",
                "missing_ingress_dns_target_provider",
            ),
            (
                "dns:\n"
                "  provider: dnsmasq\n"
                "  ingress_records:\n"
                "    enabled: true\n",
                "unsupported_ingress_dns_target_provider",
            ),
        ]
        for dns_capability, expected_code in invalid_dns_capabilities:
            with self.subTest(expected_code=expected_code), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
                self.write_fixture_service(
                    root,
                    "immich",
                    ingress_enabled=False,
                    hostname=None,
                    extra_fields=dns_capability,
                )

                self.assertIn(expected_code, {error.code for error in validate_inventory_tree(root)})

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_service(
                root,
                "immich",
                ingress_enabled=False,
                hostname=None,
                extra_fields=(
                    "dns:\n"
                    "  provider: pihole\n"
                    "  ingress_records:\n"
                    "    enabled: true\n"
                ),
            )

            self.assertNotIn("missing_ingress_dns_target_provider", {error.code for error in validate_inventory_tree(root)})
            self.assertNotIn("unsupported_ingress_dns_target_provider", {error.code for error in validate_inventory_tree(root)})

    def test_tcp_udp_published_ports_collide_with_tcp_and_udp_on_same_backend_vm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_service(
                root,
                "immich",
                published_ports=["        - container: 2283\n", "          protocol: tcp_udp\n", "          ingress: true\n"],
            )
            self.write_fixture_service(
                root,
                "photos",
                hostname="gallery.fearn.cloud",
                port=3000,
                published_ports=[
                    "        - host: 2283\n",
                    "          container: 3000\n",
                    "          protocol: udp\n",
                ],
            )

            self.assertIn("published_port_collision", {error.code for error in validate_inventory_tree(root)})

    def test_image_references_must_be_pinned(self):
        unpinned_images = ["postgres", "postgres:latest"]
        for image in unpinned_images:
            with self.subTest(image=image), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
                self.write_fixture_service(root, "immich", image=image)

                self.assertIn("unpinned_service_image", {error.code for error in validate_inventory_tree(root)})

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_service(root, "immich", image="postgres@sha256:" + "a" * 64)

            self.assertNotIn("unpinned_service_image", {error.code for error in validate_inventory_tree(root)})

    def test_service_networks_share_one_backend_vm_and_alias_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_service(root, "immich", service_network="media", container_name="server")
            self.write_fixture_vm(root, "media02", 102)
            self.write_fixture_service(root, "photos", hostname="gallery.fearn.cloud", vm="media02", port=3000, service_network="media")

            errors = validate_inventory_tree(root)

            self.assertIn("service_network_spans_backend_vms", {error.code for error in errors})
            self.assertTrue(
                any(
                    error.code == "service_network_spans_backend_vms"
                    and "Service Network media spans Backend VMs media01 and media02" in error.message
                    for error in errors
                )
            )

            self.write_fixture_service(root, "photos", hostname="gallery.fearn.cloud", vm="media01", port=3000, service_network="media", container_name="server")

            errors = validate_inventory_tree(root)

            self.assertIn("container_alias_collision", {error.code for error in errors})
            self.assertTrue(
                any(
                    error.code == "container_alias_collision"
                    and "Container Alias server in Service Network media" in error.message
                    for error in errors
                )
            )

    def test_service_group_members_can_use_different_backend_vms_without_service_group_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_service(root, "immich", service_group="media")
            self.write_fixture_vm(root, "media02", 102)
            self.write_fixture_service(root, "photos", hostname="gallery.fearn.cloud", vm="media02", port=3000, service_group="media")

            self.assertNotIn("service_network_spans_backend_vms", {error.code for error in validate_inventory_tree(root)})

    def test_service_group_members_do_not_share_alias_namespace_without_service_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_service(root, "immich", service_group="media", container_name="server")
            self.write_fixture_service(root, "photos", hostname="gallery.fearn.cloud", port=3000, service_group="media", container_name="server")

            self.assertNotIn("container_alias_collision", {error.code for error in validate_inventory_tree(root)})

    def test_launchable_service_group_order_entries_must_reference_services(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_vm(
                root,
                "media01",
                101,
                launchable_service_groups=(
                    "launchable_service_groups:\n"
                    "  - name: media\n"
                    "    launch_order: [missing-service]\n"
                ),
            )

            self.assertIn("missing_launch_order_service", {error.code for error in validate_inventory_tree(root)})

    def test_launchable_service_group_order_entries_must_match_service_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_service(root, "immich", service_group="photos")
            self.write_fixture_vm(
                root,
                "media01",
                101,
                launchable_service_groups=(
                    "launchable_service_groups:\n"
                    "  - name: media\n"
                    "    launch_order: [immich]\n"
                ),
            )

            self.assertIn("launch_order_service_group_mismatch", {error.code for error in validate_inventory_tree(root)})

    def test_launchable_service_group_order_entries_must_use_declaring_backend_vm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_vm(root, "media02", 102)
            self.write_fixture_service(root, "immich", vm="media02", service_group="media")
            self.write_fixture_vm(
                root,
                "media01",
                101,
                launchable_service_groups=(
                    "launchable_service_groups:\n"
                    "  - name: media\n"
                    "    launch_order: [immich]\n"
                ),
            )

            self.assertIn("launch_order_service_backend_vm_mismatch", {error.code for error in validate_inventory_tree(root)})

    def test_launchable_service_group_order_must_match_every_group_service_on_declaring_vm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_service(root, "immich", service_group="media")
            self.write_fixture_service(root, "photos", hostname="gallery.fearn.cloud", port=3000, service_group="media")
            self.write_fixture_vm(
                root,
                "media01",
                101,
                launchable_service_groups=(
                    "launchable_service_groups:\n"
                    "  - name: media\n"
                    "    launch_order: [immich]\n"
                ),
            )

            self.assertIn("missing_launch_order_service_group_member", {error.code for error in validate_inventory_tree(root)})

            self.write_fixture_vm(
                root,
                "media01",
                101,
                launchable_service_groups=(
                    "launchable_service_groups:\n"
                    "  - name: media\n"
                    "    launch_order: [immich, immich, photos]\n"
                ),
            )

            self.assertIn("duplicate_launch_order_service", {error.code for error in validate_inventory_tree(root)})

    def test_launchable_service_group_must_be_declared_by_only_one_vm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_service(root, "immich", service_group="media")
            self.write_fixture_vm(
                root,
                "media01",
                101,
                launchable_service_groups=(
                    "launchable_service_groups:\n"
                    "  - name: media\n"
                    "    launch_order: [immich]\n"
                ),
            )
            self.write_fixture_vm(
                root,
                "media02",
                102,
                launchable_service_groups=(
                    "launchable_service_groups:\n"
                    "  - name: media\n"
                    "    launch_order: [immich]\n"
                ),
            )

            self.assertIn("duplicate_launchable_service_group", {error.code for error in validate_inventory_tree(root)})

    def test_isolated_services_have_isolated_alias_namespaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_service(root, "immich", container_name="server")
            self.write_fixture_service(root, "photos", hostname="gallery.fearn.cloud", port=3000, container_name="server")

            self.assertNotIn("container_alias_collision", {error.code for error in validate_inventory_tree(root)})

    def test_container_dependencies_must_be_same_service_and_acyclic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_service(root, "immich", depends_on=["postgres"])

            self.assertIn("missing_container_dependency", {error.code for error in validate_inventory_tree(root)})

            self.write_fixture_service(
                root,
                "immich",
                extra_containers=[
                    "    - name: postgres\n"
                    "      image: postgres:16\n"
                    "      depends_on: [server]\n"
                ],
                depends_on=["postgres"],
            )

            self.assertIn("container_dependency_cycle", {error.code for error in validate_inventory_tree(root)})

    def test_share_backed_service_volumes_must_reference_backend_vm_mount_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
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
                "        - mount: missing-media\n"
                "          source: /\n"
                "          container: /photos\n"
                "          access: read_only\n"
            )

            self.assertIn("missing_service_volume_mount", {error.code for error in validate_inventory_tree(root)})

    def test_share_backed_service_volumes_must_not_widen_mount_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            vm_path = root / "inventory" / "vms" / "media01.yaml"
            vm_path.write_text(vm_path.read_text().replace("    access: read_write\n", "    access: read_only\n"))
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
                "          source: /\n"
                "          container: /photos\n"
                "          access: read_write\n"
            )

            self.assertIn("service_volume_widens_mount_access", {error.code for error in validate_inventory_tree(root)})

    def test_share_backed_service_volume_sources_must_stay_under_mount_root(self):
        unsafe_sources = ["/mnt/pool/media", "../photos", "photos/../secrets"]
        for source in unsafe_sources:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
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
                    f"          source: {source}\n"
                    "          container: /photos\n"
                    "          access: read_only\n"
                )

                self.assertIn("unsafe_service_volume_source", {error.code for error in validate_inventory_tree(root)})

    def test_service_secret_references_must_use_file_env_and_sibling_sops_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
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
                "        - secret: admin_password\n"
                "          env: IMMICH_ADMIN_PASSWORD\n"
            )

            codes = {error.code for error in validate_inventory_tree(root)}

            self.assertIn("service_secret_reference_not_sibling_sops_secret", codes)
            self.assertIn("service_secret_env_not_file", codes)

    def test_service_environment_names_must_not_conflict_with_secret_file_env_or_fragments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            service_path = root / "inventory" / "services" / "immich.yaml"
            service_path.write_text(
                "name: immich\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 2283\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: server\n"
                "      image: ghcr.io/immich-app/immich-server:v1.120.0\n"
                "      env:\n"
                "        IMMICH_DB_PASSWORD_FILE: /tmp/plaintext\n"
                "      secrets:\n"
                "        - secret: secrets.db_password\n"
                "          env: IMMICH_DB_PASSWORD_FILE\n"
            )

            self.assertIn("service_env_conflict", {error.code for error in validate_inventory_tree(root)})

            service_path.write_text(
                service_path.read_text().replace(
                    "      env:\n"
                    "        IMMICH_DB_PASSWORD_FILE: /tmp/plaintext\n",
                    "      env:\n"
                    "        IMMICH_URL: https://photos.fearn.cloud\n",
                )
            )
            fragment_dir = root / "inventory" / "services" / "immich.quadlet.d"
            fragment_dir.mkdir()
            (fragment_dir / "server.container").write_text(
                "[Container]\n"
                "Environment=IMMICH_URL=https://override.fearn.cloud\n"
            )

            self.assertIn("service_env_conflict", {error.code for error in validate_inventory_tree(root)})

    def test_vm_placement_host_must_exist(self):
        self.assertIn("missing_vm_host", self.codes_for("inventory_invalid/missing-vm-host"))

    def test_vm_template_must_exist(self):
        self.assertIn("missing_vm_template", self.codes_for("inventory_invalid/missing-vm-template"))

    def test_vm_mount_datasets_must_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "vms" / "media01.yaml").write_text(
                "vmid: 101\n"
                "placement:\n"
                "  host: wintermute\n"
                "source:\n"
                "  template: debian-13-base\n"
                "hardware:\n"
                "  cores: 2\n"
                "  memory: 4096\n"
                "cloud_init:\n"
                "  hostname: media01\n"
                "network:\n"
                "  interfaces:\n"
                "    - bridge: vmbr0\n"
                "      address: 10.0.10.101/24\n"
                "mounts:\n"
                "  - name: media\n"
                "    dataset: missing-media\n"
                "    protocol: nfs\n"
                "    mount_point: /mnt/nas/media\n"
                "    access: read_only\n"
            )

            self.assertIn("missing_vm_mount_dataset", {error.code for error in validate_inventory_tree(root)})

    def test_vm_mount_names_must_be_unique_within_a_vm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            vm_body = (
                "vmid: 101\n"
                "placement:\n"
                "  host: wintermute\n"
                "source:\n"
                "  template: debian-13-base\n"
                "hardware:\n"
                "  cores: 2\n"
                "  memory: 4096\n"
                "cloud_init:\n"
                "  hostname: media01\n"
                "network:\n"
                "  interfaces:\n"
                "    - bridge: vmbr0\n"
                "      address: 10.0.10.101/24\n"
                "mounts:\n"
                "  - name: media\n"
                "    dataset: media\n"
                "    protocol: nfs\n"
                "    mount_point: /mnt/nas/media\n"
                "    access: read_only\n"
                "  - name: media\n"
                "    dataset: media\n"
                "    protocol: nfs\n"
                "    mount_point: /mnt/nas/media-copy\n"
                "    access: read_only\n"
            )
            (root / "inventory" / "vms" / "media01.yaml").write_text(vm_body)

            self.assertIn("duplicate_vm_mount_name", {error.code for error in validate_inventory_tree(root)})

            (root / "inventory" / "vms" / "media01.yaml").write_text(
                vm_body.replace(
                    "  - name: media\n"
                    "    dataset: media\n"
                    "    protocol: nfs\n"
                    "    mount_point: /mnt/nas/media-copy\n"
                    "    access: read_only\n",
                    "",
                )
            )
            (root / "inventory" / "vms" / "media02.yaml").write_text(
                vm_body.replace("vmid: 101", "vmid: 102")
                .replace("hostname: media01", "hostname: media02")
                .replace("address: 10.0.10.101/24", "address: 10.0.10.102/24")
                .replace(
                    "  - name: media\n"
                    "    dataset: media\n"
                    "    protocol: nfs\n"
                    "    mount_point: /mnt/nas/media-copy\n"
                    "    access: read_only\n",
                    "",
                )
            )

            errors = validate_inventory_tree(root)
            self.assertNotIn("duplicate_vm_mount_name", {error.code for error in errors})

    def test_vm_mounts_require_one_unambiguous_static_ip_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "vms" / "media01.yaml").write_text(
                "vmid: 101\n"
                "placement:\n"
                "  host: wintermute\n"
                "source:\n"
                "  template: debian-13-base\n"
                "hardware:\n"
                "  cores: 2\n"
                "  memory: 4096\n"
                "cloud_init:\n"
                "  hostname: media01\n"
                "network:\n"
                "  interfaces:\n"
                "    - bridge: vmbr0\n"
                "      address: 10.0.10.101/24\n"
                "    - bridge: vmbr0\n"
                "      address: 10.0.20.101/24\n"
                "mounts:\n"
                "  - name: media\n"
                "    dataset: media\n"
                "    protocol: nfs\n"
                "    mount_point: /mnt/nas/media\n"
                "    access: read_only\n"
            )

            self.assertIn("ambiguous_vm_mount_client_address", {error.code for error in validate_inventory_tree(root)})

    def test_vm_mount_options_must_not_contradict_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "vms" / "media01.yaml").write_text(
                "vmid: 101\n"
                "placement:\n"
                "  host: wintermute\n"
                "source:\n"
                "  template: debian-13-base\n"
                "hardware:\n"
                "  cores: 2\n"
                "  memory: 4096\n"
                "cloud_init:\n"
                "  hostname: media01\n"
                "network:\n"
                "  interfaces:\n"
                "    - bridge: vmbr0\n"
                "      address: 10.0.10.101/24\n"
                "mounts:\n"
                "  - name: media\n"
                "    dataset: media\n"
                "    protocol: nfs\n"
                "    mount_point: /mnt/nas/media\n"
                "    access: read_only\n"
                "    options_extra: [rw]\n"
            )

            self.assertIn("vm_mount_access_option_conflict", {error.code for error in validate_inventory_tree(root)})

            (root / "inventory" / "vms" / "media01.yaml").write_text(
                (root / "inventory" / "vms" / "media01.yaml")
                .read_text()
                .replace("    access: read_only\n", "    access: read_write\n")
                .replace("    options_extra: [rw]\n", "    options_extra: [ro]\n")
            )

            self.assertIn("vm_mount_access_option_conflict", {error.code for error in validate_inventory_tree(root)})

            (root / "inventory" / "vms" / "media01.yaml").write_text(
                (root / "inventory" / "vms" / "media01.yaml")
                .read_text()
                .replace("      address: 10.0.10.101/24\n", "")
                .replace("      address: 10.0.20.101/24\n", "")
            )

            self.assertIn("ambiguous_vm_mount_client_address", {error.code for error in validate_inventory_tree(root)})

    def test_vm_disks_must_use_storage_declared_by_placement_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "vms" / "media01.yaml").write_text(
                "vmid: 101\n"
                "placement:\n"
                "  host: wintermute\n"
                "source:\n"
                "  template: debian-13-base\n"
                "hardware:\n"
                "  cores: 2\n"
                "  memory: 4096\n"
                "  disks:\n"
                "    - storage: missing-store\n"
                "      size: 32G\n"
                "cloud_init:\n"
                "  hostname: media01\n"
            )

            self.assertIn("missing_host_storage", {error.code for error in validate_inventory_tree(root)})

    def test_vm_interfaces_must_use_bridges_declared_by_placement_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "vms" / "media01.yaml").write_text(
                "vmid: 101\n"
                "placement:\n"
                "  host: wintermute\n"
                "source:\n"
                "  template: debian-13-base\n"
                "hardware:\n"
                "  cores: 2\n"
                "  memory: 4096\n"
                "network:\n"
                "  interfaces:\n"
                "    - bridge: missing-bridge\n"
                "cloud_init:\n"
                "  hostname: media01\n"
            )

            self.assertIn("missing_host_bridge", {error.code for error in validate_inventory_tree(root)})

    def test_ordinary_vms_must_not_use_operational_vmids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_vm(root, "media01", 8901)

            self.assertIn("ordinary_vm_operational_vmid", {error.code for error in validate_inventory_tree(root)})

    def test_operational_vms_must_use_operational_vmids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_vm(
                root,
                "template-verify",
                8801,
                "lifecycle:\n"
                "  kind: operational\n"
                "  purpose: template-verification\n"
                "  generated: true\n",
            )

            self.assertIn("operational_vm_vmid_out_of_range", {error.code for error in validate_inventory_tree(root)})

    def test_template_vmids_are_reserved_for_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_vm(root, "media01", 9001)

            self.assertIn("vm_uses_template_vmid", {error.code for error in validate_inventory_tree(root)})

    def test_checked_in_tmp_vm_names_are_reserved_for_generated_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_vm(root, "tmp-template-verify", 101)

            self.assertIn("reserved_tmp_vm_name", {error.code for error in validate_inventory_tree(root)})

    def test_generated_tmp_operational_vm_names_are_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self.write_fixture_vm(
                root,
                "tmp-template-verify",
                8901,
                "lifecycle:\n"
                "  kind: operational\n"
                "  purpose: template-verification\n"
                "  generated: true\n",
            )

            self.assertNotIn("reserved_tmp_vm_name", {error.code for error in validate_inventory_tree(root)})

    def write_fixture_vm(self, root, name, vmid, lifecycle="", launchable_service_groups=""):
        (root / "inventory" / "vms" / f"{name}.yaml").write_text(
            f"vmid: {vmid}\n"
            f"{lifecycle}"
            "placement:\n"
            "  host: wintermute\n"
            "source:\n"
            "  template: debian-13-base\n"
            "hardware:\n"
            "  cores: 2\n"
            "  memory: 4096\n"
            "cloud_init:\n"
            f"  hostname: {name}\n"
            f"{launchable_service_groups}"
        )

    def write_fixture_service(
        self,
        root,
        name,
        hostname="photos.fearn.cloud",
        vm="media01",
        port=2283,
        image="ghcr.io/immich-app/immich-server:v1.120.0",
        ingress_enabled=True,
        service_group=None,
        service_network=None,
        container_name="server",
        published_ports=None,
        depends_on=None,
        extra_containers=None,
        extra_fields="",
    ):
        ingress = ""
        if ingress_enabled is not None:
            ingress = f"ingress:\n  enabled: {'true' if ingress_enabled else 'false'}\n"
        group = f"service_group: {service_group}\n" if service_group else ""
        network = f"service_network: {service_network}\n" if service_network else ""
        hostname_field = f"hostname: {hostname}\n" if hostname else ""
        ports = ""
        if published_ports is not None:
            ports = "      published_ports:\n" + "".join(published_ports)
        dependencies = f"      depends_on: [{', '.join(depends_on)}]\n" if depends_on else ""
        containers = (
            f"    - name: {container_name}\n"
            f"      image: {image}\n"
            f"{ports}"
            f"{dependencies}"
        )
        if extra_containers:
            containers += "".join(extra_containers)
        (root / "inventory" / "services" / f"{name}.yaml").write_text(
            f"name: {name}\n"
            f"{group}"
            f"{network}"
            f"{hostname_field}"
            "backend:\n"
            f"  vm: {vm}\n"
            f"  port: {port}\n"
            f"{ingress}"
            f"{extra_fields}"
            "deploy:\n"
            "  type: quadlet\n"
            "  containers:\n"
            f"{containers}"
        )
