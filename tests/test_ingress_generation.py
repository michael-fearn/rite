import shutil
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from fortress_ingress.generate import (
    GENERATED_CADDY_ROUTES_PATH,
    build_caddy_route_model,
    ingress_dns_targets,
    render_caddy_routes,
    render_ingress_dns_record_sets,
)
from fortress_inventory.model import load_inventory_tree


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"


class IngressGenerationTests(unittest.TestCase):
    def test_route_model_combines_service_and_host_routes_ordered_by_hostname(self):
        model = load_inventory_tree(REPO_ROOT)

        route_model = build_caddy_route_model(model)

        hostnames = [route["hostname"] for route in route_model["routes"]]
        self.assertEqual(sorted(hostnames), hostnames)
        self.assertIn("dns-primary.fearn.cloud", hostnames)
        self.assertIn("wintermute.fearn.cloud", hostnames)
        self.assertEqual("10.40.0.16", route_model["ingress_address"])

    def test_generated_routes_are_import_file_content_with_letsencrypt_dns_tls(self):
        caddy_routes = render_caddy_routes(load_inventory_tree(REPO_ROOT))

        self.assertNotIn("admin {$CADDY_ADMIN}", caddy_routes)
        self.assertIn("dns-primary.fearn.cloud {\n\ttls {\n\t\tdns cloudflare {$CLOUDFLARE_API_TOKEN}\n\t}", caddy_routes)
        self.assertIn("\treverse_proxy http://10.40.0.11:8080", caddy_routes)
        self.assertNotIn("handle_path", caddy_routes)
        self.assertNotIn("uri strip_prefix", caddy_routes)

    def test_route_model_requires_unambiguous_static_ipv4_addresses(self):
        cases = []

        ingress_model = deepcopy(load_inventory_tree(REPO_ROOT))
        ingress_model.vms["internal-ingress-vm"]["network"]["interfaces"] = []
        cases.append(("ingress", ingress_model, "Ingress VM internal-ingress-vm"))

        backend_model = deepcopy(load_inventory_tree(REPO_ROOT))
        backend_model.vms["dns-primary-vm"]["network"]["interfaces"].append(
            {"bridge": "vmbr0", "address": "10.40.0.111/24"}
        )
        cases.append(("backend", backend_model, "Backend VM dns-primary-vm"))

        host_model = deepcopy(load_inventory_tree(REPO_ROOT))
        del host_model.hosts["wintermute"]["network"]["management_address"]
        cases.append(("host", host_model, "Host Ingress Route wintermute"))

        for name, model, expected_message in cases:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, expected_message):
                    build_caddy_route_model(model)

    def test_service_hostname_without_enabled_ingress_does_not_render_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            service_path = root / "inventory" / "services" / "immich.yaml"
            service_path.write_text(service_path.read_text().replace("ingress:\n  enabled: true\n", ""))

            caddy_routes = render_caddy_routes(load_inventory_tree(root))

            self.assertNotIn("photos.fearn.cloud {", caddy_routes)

    def test_host_ingress_route_is_limited_to_inventory_trusted_source_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self._write_internal_ingress(root)
            (root / "inventory" / "group_vars" / "all.yaml").write_text(
                "domain: fearn.cloud\n"
                "nas:\n"
                "  default_options:\n"
                "    - nfsvers=4.2\n"
                "ingress:\n"
                "  trusted_source_ranges:\n"
                "    - 10.20.0.0/24\n"
                "    - 100.64.0.0/10\n"
            )
            (root / "inventory" / "hosts" / "wintermute.yaml").write_text(
                "proxmox:\n"
                "  pve_node_name: wintermute\n"
                "network:\n"
                "  management_address: 10.0.0.10\n"
                "ingress:\n"
                "  proxmox_web_ui:\n"
                "    enabled: true\n"
                "    hostname: wintermute.fearn.cloud\n"
            )

            caddy_routes = render_caddy_routes(load_inventory_tree(root))

            self.assertIn("wintermute.fearn.cloud {", caddy_routes)
            self.assertIn("@trusted remote_ip 10.20.0.0/24 100.64.0.0/10", caddy_routes)
            self.assertIn("handle @trusted {\n\t\treverse_proxy http://10.0.0.10:8006\n\t}", caddy_routes)
            self.assertIn("respond 403", caddy_routes)
            self.assertIn("photos.fearn.cloud {", caddy_routes)
            self.assertNotIn("@trusted remote_ip 10.0.10.101", caddy_routes)

    def test_host_ingress_route_targets_management_address_not_proxmox_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self._write_internal_ingress(root)
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
                "ingress:\n"
                "  proxmox_web_ui:\n"
                "    enabled: true\n"
                "    hostname: wintermute.fearn.cloud\n"
            )

            caddy_routes = render_caddy_routes(load_inventory_tree(root))

            self.assertIn("reverse_proxy http://10.0.0.10:8006", caddy_routes)
            self.assertNotIn("pve-api.fearn.cloud", caddy_routes)
            self.assertNotIn("pve-internal-name.fearn.cloud", caddy_routes)

    def test_ingress_regenerate_command_prints_trusted_host_routes(self):
        result = subprocess.run(
            [str(REPO_ROOT / "scripts" / "ingress-regenerate"), "--print"],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("admin {$CADDY_ADMIN}", result.stdout)
        self.assertIn("wintermute.fearn.cloud {", result.stdout)
        self.assertIn("@trusted remote_ip 10.20.0.0/24", result.stdout)

    def test_ingress_regenerate_pushes_generated_files_and_reloads_targets_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(REPO_ROOT / "inventory", root / "inventory")
            calls_log = root / "calls.log"
            self._write_fake_vm_shell(root, calls_log)

            result = self._run_ingress_regenerate(root)

            self.assertEqual(result.returncode, 0, result.stderr)
            calls = calls_log.read_text().splitlines()
            self.assertEqual(
                [
                    "vm-shell internal-ingress-vm -- sudo install -D -m 0644 /dev/stdin /etc/caddy/fortress/generated-routes.caddy",
                    "stdin: auth.fearn.cloud {",
                    "vm-shell internal-ingress-vm -- sudo systemctl reload caddy",
                    "vm-shell dns-primary-vm -- sudo install -D -m 0644 /dev/stdin /etc/dnsmasq.d/99-fortress-ingress.conf",
                    "stdin: # Generated by fortress ingress regeneration. Do not edit by hand.",
                    "vm-shell dns-primary-vm -- sudo podman exec fortress-dns-primary-pihole pihole reloaddns",
                ],
                calls,
            )

    def test_dns_primary_is_web_ui_route_and_ingress_dns_target(self):
        model = load_inventory_tree(REPO_ROOT)

        caddy_routes = render_caddy_routes(model)
        targets = ingress_dns_targets(model)

        self.assertIn("dns-primary.fearn.cloud {", caddy_routes)
        self.assertIn("reverse_proxy http://10.40.0.11:8080", caddy_routes)
        self.assertEqual(["dns-primary"], [target["service"] for target in targets])
        self.assertEqual("dns-primary-vm", targets[0]["backend_vm"])
        self.assertEqual("pihole", targets[0]["provider"])

        published_ports = model.services["dns-primary"]["deploy"]["containers"][0]["published_ports"]
        self.assertIn(
            {"bind": "10.40.0.11", "host": 53, "container": 53, "protocol": "tcp_udp"},
            published_ports,
        )
        self.assertIn(
            {"bind": "0.0.0.0", "host": 8080, "container": 80, "ingress": True, "protocol": "tcp"},
            published_ports,
        )

    def test_ingress_dns_targets_are_selected_from_dns_service_declarations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "vms" / "dns-primary-vm.yaml").write_text(
                "vmid: 1001\n"
                "placement:\n"
                "  host: wintermute\n"
                "source:\n"
                "  template: debian-13-base\n"
                "network:\n"
                "  interfaces:\n"
                "    - bridge: vmbr0\n"
                "      address: 10.40.0.11/24\n"
            )
            (root / "inventory" / "services" / "dns-target.yaml").write_text(
                "name: dns-target\n"
                "dns:\n"
                "  provider: pihole\n"
                "  ingress_records:\n"
                "    enabled: true\n"
                "backend:\n"
                "  vm: media01\n"
                "  port: 8080\n"
                "ingress:\n"
                "  enabled: false\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: pihole\n"
                "      image: docker.io/pihole/pihole:2025.05.0\n"
            )

            targets = ingress_dns_targets(load_inventory_tree(root))

            self.assertEqual(["dns-target"], [target["service"] for target in targets])
            self.assertEqual("media01", targets[0]["backend_vm"])

    def test_ingress_dns_record_set_renders_declared_routes_to_ingress_address_only(self):
        record_sets = render_ingress_dns_record_sets(load_inventory_tree(REPO_ROOT))

        self.assertEqual(["dns-primary"], [record_set["service"] for record_set in record_sets])
        self.assertEqual("/etc/dnsmasq.d/99-fortress-ingress.conf", record_sets[0]["path"])
        self.assertEqual("replace", record_sets[0]["write_mode"])
        self.assertEqual(
            [
                "# Generated by fortress ingress regeneration. Do not edit by hand.",
                "address=/auth.fearn.cloud/10.40.0.16",
                "address=/dns-primary.fearn.cloud/10.40.0.16",
                "address=/files.fearn.cloud/10.40.0.16",
                "address=/forgejo.fearn.cloud/10.40.0.16",
                "address=/grafana.fearn.cloud/10.40.0.16",
                "address=/headscale.fearn.cloud/10.40.0.16",
                "address=/molly.fearn.cloud/10.40.0.16",
                "address=/neuromancer.fearn.cloud/10.40.0.16",
                "address=/straylight.fearn.cloud/10.40.0.16",
                "address=/wintermute.fearn.cloud/10.40.0.16",
            ],
            record_sets[0]["content"].splitlines(),
        )
        self.assertNotIn("*.", record_sets[0]["content"])
        self.assertNotIn("internal-ingress", record_sets[0]["content"])
        self.assertNotIn("10.40.0.11", record_sets[0]["content"])

    def test_ingress_dns_record_set_is_rendered_for_each_declared_dns_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self._write_internal_ingress(root)
            (root / "inventory" / "hosts" / "wintermute.yaml").write_text(
                "proxmox:\n"
                "  pve_node_name: wintermute\n"
                "network:\n"
                "  management_address: 10.0.0.10\n"
            )
            (root / "inventory" / "vms" / "dns-secondary-vm.yaml").write_text(
                "vmid: 1007\n"
                "placement:\n"
                "  host: wintermute\n"
                "source:\n"
                "  template: debian-13-base\n"
                "network:\n"
                "  interfaces:\n"
                "    - bridge: vmbr0\n"
                "      address: 10.40.0.18/24\n"
            )
            (root / "inventory" / "services" / "dns-primary.yaml").write_text(
                "name: dns-primary\n"
                "dns:\n"
                "  provider: pihole\n"
                "  ingress_records:\n"
                "    enabled: true\n"
                "backend:\n"
                "  vm: dns-primary-vm\n"
                "  port: 8080\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: pihole\n"
                "      image: docker.io/pihole/pihole:2025.05.0\n"
            )
            (root / "inventory" / "services" / "dns-secondary.yaml").write_text(
                "name: dns-secondary\n"
                "dns:\n"
                "  provider: pihole\n"
                "  ingress_records:\n"
                "    enabled: true\n"
                "backend:\n"
                "  vm: dns-secondary-vm\n"
                "  port: 8080\n"
                "deploy:\n"
                "  type: quadlet\n"
                "  containers:\n"
                "    - name: pihole\n"
                "      image: docker.io/pihole/pihole:2025.05.0\n"
            )

            record_sets = render_ingress_dns_record_sets(load_inventory_tree(root))

            self.assertEqual(["dns-primary", "dns-secondary"], [record_set["service"] for record_set in record_sets])
            self.assertEqual(
                {"/etc/dnsmasq.d/99-fortress-ingress.conf"},
                {record_set["path"] for record_set in record_sets},
            )
            self.assertEqual(1, len({record_set["content"] for record_set in record_sets}))
            self.assertIn("address=/photos.fearn.cloud/10.40.0.16", record_sets[0]["content"])
            self.assertNotIn("10.40.0.18", record_sets[0]["content"])

    def test_ingress_regenerate_pushes_dns_records_to_each_declared_dns_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            self._write_internal_ingress(root)
            (root / "inventory" / "vms" / "dns-primary-vm.yaml").write_text(
                "vmid: 1001\n"
                "placement:\n"
                "  host: wintermute\n"
                "source:\n"
                "  template: debian-13-base\n"
                "network:\n"
                "  interfaces:\n"
                "    - bridge: vmbr0\n"
                "      address: 10.40.0.11/24\n"
            )
            (root / "inventory" / "vms" / "dns-secondary-vm.yaml").write_text(
                "vmid: 1007\n"
                "placement:\n"
                "  host: wintermute\n"
                "source:\n"
                "  template: debian-13-base\n"
                "network:\n"
                "  interfaces:\n"
                "    - bridge: vmbr0\n"
                "      address: 10.40.0.18/24\n"
            )
            (root / "inventory" / "services" / "dns-primary.yaml").write_text(
                self._pihole_dns_target_service_yaml("dns-primary", "dns-primary-vm")
            )
            (root / "inventory" / "services" / "dns-secondary.yaml").write_text(
                self._pihole_dns_target_service_yaml("dns-secondary", "dns-secondary-vm")
            )
            calls_log = root / "calls.log"
            self._write_fake_vm_shell(root, calls_log)

            result = self._run_ingress_regenerate(root)

            self.assertEqual(result.returncode, 0, result.stderr)
            calls = calls_log.read_text()
            self.assertIn(
                "vm-shell dns-primary-vm -- sudo install -D -m 0644 /dev/stdin /etc/dnsmasq.d/99-fortress-ingress.conf\n",
                calls,
            )
            self.assertIn(
                "vm-shell dns-secondary-vm -- sudo install -D -m 0644 /dev/stdin /etc/dnsmasq.d/99-fortress-ingress.conf\n",
                calls,
            )
            self.assertIn(
                "vm-shell dns-primary-vm -- sudo podman exec fortress-dns-primary-pihole pihole reloaddns\n",
                calls,
            )
            self.assertIn(
                "vm-shell dns-secondary-vm -- sudo podman exec fortress-dns-secondary-pihole pihole reloaddns\n",
                calls,
            )

    def test_ingress_regenerate_validates_inventory_before_pushes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(REPO_ROOT / "inventory", root / "inventory")
            (root / "inventory" / "services" / "dns-primary.yaml").write_text(
                "name: dns-primary\nhostname: dns-primary.fearn.cloud\n"
            )
            calls_log = root / "calls.log"
            self._write_fake_vm_shell(root, calls_log)

            result = self._run_ingress_regenerate(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(calls_log.exists())
            self.assertIn("ingress", result.stderr)

    def test_ingress_regenerate_exits_nonzero_when_targeted_reload_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(REPO_ROOT / "inventory", root / "inventory")
            calls_log = root / "calls.log"
            self._write_fake_vm_shell(root, calls_log)

            result = self._run_ingress_regenerate(root, fail_on="systemctl reload caddy")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("failed: reload Caddy on internal-ingress-vm", result.stderr)

    def test_ingress_regenerate_exits_nonzero_when_targeted_push_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(REPO_ROOT / "inventory", root / "inventory")
            calls_log = root / "calls.log"
            self._write_fake_vm_shell(root, calls_log)

            result = self._run_ingress_regenerate(root, fail_on=GENERATED_CADDY_ROUTES_PATH)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("failed: push Caddy routes to internal-ingress-vm", result.stderr)
            self.assertNotIn("systemctl reload caddy", calls_log.read_text())

    def _write_internal_ingress(self, root):
        (root / "inventory" / "vms" / "internal-ingress-vm.yaml").write_text(
            "vmid: 1006\n"
            "placement:\n"
            "  host: wintermute\n"
            "source:\n"
            "  template: debian-13-base\n"
            "network:\n"
            "  interfaces:\n"
            "    - bridge: vmbr0\n"
            "      address: 10.40.0.16/24\n"
        )
        (root / "inventory" / "services" / "internal-ingress.yaml").write_text(
            "name: internal-ingress\n"
            "backend:\n"
            "  vm: internal-ingress-vm\n"
            "  port: 443\n"
            "ingress:\n"
            "  enabled: false\n"
            "deploy:\n"
            "  type: native\n"
            "  package: caddy\n"
            "  service_name: caddy\n"
        )

    def _pihole_dns_target_service_yaml(self, service_name, vm_name):
        return (
            f"name: {service_name}\n"
            "dns:\n"
            "  provider: pihole\n"
            "  ingress_records:\n"
            "    enabled: true\n"
            "backend:\n"
            f"  vm: {vm_name}\n"
            "  port: 8080\n"
            "deploy:\n"
            "  type: quadlet\n"
            "  containers:\n"
            "    - name: pihole\n"
            "      image: docker.io/pihole/pihole:2025.05.0\n"
        )

    def _run_ingress_regenerate(self, root, fail_on=""):
        env = {
            "FORTRESS_ROOT": str(root),
            "CALLS_LOG": str(root / "calls.log"),
            "FORTRESS_FAKE_VM_SHELL_FAIL_ON": fail_on,
        }
        return subprocess.run(
            [str(REPO_ROOT / "scripts" / "ingress-regenerate")],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def _write_fake_vm_shell(self, root, calls_log):
        scripts = root / "scripts"
        scripts.mkdir(exist_ok=True)
        fake = scripts / "vm-shell"
        fake.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'vm-shell %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
            "stdin=$(cat)\n"
            "if [ -n \"$stdin\" ]; then printf 'stdin: %s\\n' \"$(printf '%s' \"$stdin\" | sed -n '1p')\" >> \"$CALLS_LOG\"; fi\n"
            "if [ -n \"$FORTRESS_FAKE_VM_SHELL_FAIL_ON\" ]; then\n"
            "  case \" $* \" in *\"$FORTRESS_FAKE_VM_SHELL_FAIL_ON\"*) exit 42 ;; esac\n"
            "fi\n"
        )
        fake.chmod(fake.stat().st_mode | 0o100)
