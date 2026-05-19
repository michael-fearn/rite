import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class InstrumentationRunbookTests(unittest.TestCase):
    def test_runbook_documents_instrumentation_convergence_workflow(self):
        runbook = REPO_ROOT / "runbooks" / "instrumentation.md"

        self.assertTrue(runbook.is_file())
        content = runbook.read_text()
        for phrase in [
            "just instrumentation-converge",
            "applies enabled VM-level Instrumentation across ordinary VMs",
            "runs VM Configure for each ordinary VM with Instrumentation enabled",
            "then runs Service Update for the Observability Service",
            "path for applying Instrumentation to existing VMs and Services",
            "skips inventory-declared VMs that are absent from the live Host",
            "omitted from the generated Observability Service configuration during that convergence run",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, content)

    def test_runbook_documents_vm_baseline_collectors_and_opt_out(self):
        content = (REPO_ROOT / "runbooks" / "instrumentation.md").read_text()

        for phrase in [
            "ordinary VMs are instrumented by default",
            "instrumentation.enabled: false",
            "opts one ordinary VM out of baseline VM-level Instrumentation",
            "baseline collector set is node exporter for system metrics and Grafana Alloy for VM logs",
            "VM Configure installs and enables the baseline collectors",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, content)

    def test_runbook_documents_service_telemetry_targets(self):
        content = (REPO_ROOT / "runbooks" / "instrumentation.md").read_text()

        for phrase in [
            "instrumentation.telemetry_targets",
            "prometheus_metrics",
            "http_probe",
            "published_port",
            "first-pass Telemetry Targets are collected through VM-reachable Published Ports",
            "scheme defaults to http",
            "prometheus_metrics path defaults to /metrics",
            "http_probe path defaults to /",
            "targets the Backend VM static IP and Published Port rather than the Service Ingress hostname",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, content)

    def test_runbook_documents_service_deploy_boundary_and_deferred_profiles(self):
        content = (REPO_ROOT / "runbooks" / "instrumentation.md").read_text()

        for phrase in [
            "Service Deploy remains scoped to the named Service",
            "does not refresh the Observability VM",
            "Service Launch refreshes the Observability VM",
            "Service Group Launch refreshes the Observability VM",
            "collector profiles are deferred",
            "future VM-level Instrumentation declaration",
            "applied to existing VMs through Instrumentation Convergence",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, content)

    def test_runbook_documents_generated_observability_views(self):
        content = (REPO_ROOT / "runbooks" / "instrumentation.md").read_text()

        for phrase in [
            "Generated Observability Views are derived from Instrumentation",
            "refreshed through `just instrumentation-converge`",
            "single Rite-owned generated Grafana folder",
            "Operator edits to generated views are not preserved",
            "automatic `vm_baseline` view for each included ordinary VM",
            "explicit Service-level `prometheus_generic` view",
            "applies to the Service Instrumentation declaration as a whole, not to one Telemetry Target",
            "uses Grafana file provisioning rather than the Grafana HTTP API",
            "docs/adr/0033-grafana-observability-views-use-file-provisioning.md",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, content)


if __name__ == "__main__":
    unittest.main()
