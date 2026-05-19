import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ArchitectureDocsTests(unittest.TestCase):
    def test_architecture_notes_describe_operator_workflow_runner_seam(self):
        content = (REPO_ROOT / "docs" / "architecture.md").read_text()

        for phrase in [
            "Operator Workflow Plan",
            "Operator Workflow Runner",
            "fortress_workflows.vm_lifecycle",
            "fortress_workflows.service_launch",
            "fortress_workflows.service_group_launch",
            "fortress_workflows.host_readiness",
            "fortress_workflows.instrumentation_convergence",
            "fortress_workflows.runner",
            "plan builders own domain-specific ceremony rules",
            "runner owns execution mechanics",
            "confirmation gates",
            "stop versus continue failure policy",
            "streaming prefix output",
            "captured tails",
            "standardized failure detail",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, content)

        for path in [
            REPO_ROOT / "scripts" / "vm-up",
            REPO_ROOT / "scripts" / "service-launch",
            REPO_ROOT / "scripts" / "service-group-launch",
            REPO_ROOT / "scripts" / "host-up",
            REPO_ROOT / "scripts" / "instrumentation-converge",
        ]:
            with self.subTest(path=path):
                script = path.read_text()
                self.assertNotIn("def run_phase", script)
                self.assertNotIn("def phase_detail", script)

    def test_architecture_notes_observability_is_current_workflow_scope(self):
        content = (REPO_ROOT / "docs" / "architecture.md").read_text()

        for phrase in [
            "Instrumentation Convergence",
            "Service Deploy remains scoped to the named Service",
            "Observability refresh",
            "Monitoring / observability baseline",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, content)

        self.assertNotIn("Monitoring / observability — out of scope for v1", content)

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
