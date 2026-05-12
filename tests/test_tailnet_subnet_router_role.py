import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class TailnetSubnetRouterRoleTests(unittest.TestCase):
    def test_role_installs_tailscale_and_enables_forwarding(self):
        tasks = (REPO_ROOT / "ansible" / "roles" / "tailnet_subnet_router" / "tasks" / "main.yml").read_text()

        self.assertIn("https://pkgs.tailscale.com/stable/debian/trixie.noarmor.gpg", tasks)
        self.assertIn("URIs: https://pkgs.tailscale.com/stable/debian", tasks)
        self.assertIn("Suites: trixie", tasks)
        self.assertIn("Components: main", tasks)
        self.assertIn("Signed-By: /usr/share/keyrings/tailscale-archive-keyring.gpg", tasks)
        self.assertIn("name: tailscale", tasks)
        self.assertIn("net.ipv4.ip_forward", tasks)
        self.assertIn("net.ipv6.conf.all.forwarding", tasks)

    def test_role_reads_auth_key_from_vm_sibling_sops_file_only_for_first_enrollment(self):
        tasks = (REPO_ROOT / "ansible" / "roles" / "tailnet_subnet_router" / "tasks" / "main.yml").read_text()

        self.assertIn("{{ fortress_vm_sops_file }}", tasks)
        self.assertIn('default(\'[\\"tailnet\\"][\\"auth_key\\"][\\"value\\"]\')', tasks)
        self.assertIn("delegate_to: localhost", tasks)
        self.assertIn("no_log: true", tasks)
        self.assertIn("when: fortress_tailscale_status.rc != 0", tasks)

    def test_role_advertises_declared_routes_without_reusing_auth_key_after_enrollment(self):
        tasks = (REPO_ROOT / "ansible" / "roles" / "tailnet_subnet_router" / "tasks" / "main.yml").read_text()

        self.assertIn("--advertise-routes={{ fortress_vm.tailnet_subnet_router.advertise_routes | join(',') }}", tasks)
        self.assertIn("when: fortress_tailscale_status.rc == 0", tasks)
        self.assertIn("--accept-dns=false", tasks)
