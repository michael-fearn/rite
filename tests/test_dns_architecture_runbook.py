import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class DNSArchitectureRunbookTests(unittest.TestCase):
    def test_runbook_documents_dns_architecture_and_operator_validation(self):
        runbook = REPO_ROOT / "runbooks" / "dns-architecture.md"

        self.assertTrue(runbook.is_file())
        content = runbook.read_text()
        expected_phrases = [
            "Pi-hole + Unbound DNS architecture",
            "two-container Quadlet Service",
            "dns-primary-vm",
            "10.40.0.11",
            "VLAN 40",
            "inventory/vms/dns-primary-vm.yaml",
            "inventory/services/dns-primary.yaml",
            "inventory/services/dns-primary.sops.yaml",
            "scripts/vm-up dns-primary-vm",
            "scripts/service-deploy dns-primary",
            "TCP and UDP port 53",
            "WEBPASSWORD_FILE",
            "env_value: secret_name",
            "secret name",
            "secrets.web_api_password.value",
            "FTLCONF_dns_upstreams: unbound",
            "FTLCONF_dns_listeningMode: all",
            "/srv/services/dns-primary/pihole/etc-pihole",
            "/srv/services/dns-primary/unbound",
            "dig @10.40.0.11 example.com A",
            "just acceptance-dns-primary internal=internal-ingress.fearn.cloud",
            "Guest must not use internal DNS",
            "DNS-001-ALLOW-INTERNAL-RESOLUTION",
            "DNS-003-ALLOW-DNS-UPSTREAM",
        ]

        for phrase in expected_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, content)

    def test_runbook_names_the_generated_quadlet_artifacts(self):
        content = (REPO_ROOT / "runbooks" / "dns-architecture.md").read_text()

        self.assertIn("fortress-group-dns-primary.network", content)
        self.assertIn("fortress-dns-primary-pihole.container", content)
        self.assertIn("fortress-dns-primary-unbound.container", content)
        self.assertIn("fortress-dns-primary-pihole.service", content)
        self.assertIn("fortress-dns-primary-unbound.service", content)

    def test_dns_primary_service_secret_sibling_sops_file_is_structured_and_encrypted(self):
        sops_file = REPO_ROOT / "inventory" / "services" / "dns-primary.sops.yaml"

        self.assertTrue(sops_file.is_file())
        content = sops_file.read_text()
        for phrase in [
            "secrets:",
            "web_api_password:",
            "created:",
            "version:",
            "value:",
            "sops:",
            "ENC[AES256_GCM",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, content)


if __name__ == "__main__":
    unittest.main()
