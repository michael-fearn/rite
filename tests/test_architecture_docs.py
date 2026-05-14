import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ArchitectureDocsTests(unittest.TestCase):
    def test_architecture_notes_describe_current_ingress_regeneration_model(self):
        content = (REPO_ROOT / "docs" / "architecture.md").read_text()

        for phrase in [
            "Service Ingress",
            "Host Ingress Routes",
            "Caddy generated-route ownership",
            "generated DNS ownership",
            "just ingress-regenerate",
            "generated Caddy routes",
            "Ingress DNS Records",
            "Ingress DNS Targets",
            "99-fortress-ingress.conf",
            "Manual Pi-hole records",
            "repo-owned Caddy package extension",
            "dns.providers.cloudflare",
            "Do not repair this durably with manual `caddy add-package`",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, content)

        self.assertNotIn("just ingress-rebuild", content)
        self.assertNotIn("All `*.fearn.cloud` DNS records resolve to this VM's IP", content)


if __name__ == "__main__":
    unittest.main()
