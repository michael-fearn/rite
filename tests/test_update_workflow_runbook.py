import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class UpdateWorkflowRunbookTests(unittest.TestCase):
    def test_runbook_documents_scoped_update_workflows(self):
        runbook = REPO_ROOT / "runbooks" / "update-workflows.md"

        self.assertTrue(runbook.is_file())
        content = runbook.read_text()
        expected_phrases = [
            "Host Update",
            "just host-update <host>",
            "just host-update <host> --reboot",
            "runs Host Configure first",
            "updates only the selected Host",
            "impacted dependents",
            "Ordinary VMs impacted on Host",
            "Resident Services impacted through those VMs",
            "Type `reboot <host>`",
            "starts the same ordinary VMs it shut down",
            "does not run Template Update",
            "does not update VMs or Services implicitly",
            "VM Update",
            "just vm-update <vm>",
            "runs VM Configure first",
            "updates only the selected VM",
            "Resident fortress-managed Services on VM",
            "Type `reboot <vm>`",
            "restores the same resident fortress-managed Services it stopped",
            "does not run Template Update",
            "Template Update",
            "just template-update host=<host> template=<template>",
            "just template-update host=all template=<template>",
            "one selected Host copy",
            "explicit all-Hosts mode",
            "lineage report",
            "existing VMs are not changed",
            "Template Verification",
            "temporary Template Verification VM",
            "Service Update",
            "just service-update <service>",
            "just service-update <service> auto_confirm=true",
            "runs Service Deploy first",
            "declared runtime references",
            "updates only the named Service",
            "does not restart Service Group peers implicitly",
            "all fortress-owned units for the named Service reach active state",
            "There is no Service Group Update workflow",
        ]

        for phrase in expected_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, content)

    def test_runbook_language_stays_aligned_with_glossary_and_adr(self):
        content = (REPO_ROOT / "runbooks" / "update-workflows.md").read_text()

        for phrase in [
            "Update is routine in-place advancement within the current compatibility band",
            "Upgrade is reserved for version-boundary or migration-bearing advancement",
            "package removals",
            "release transitions",
            "database migrations",
            "application breaking migrations",
            "Host Configure",
            "VM Configure",
            "package-manager-neutral domain concepts",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, content)

        self.assertNotRegex(content, re.compile(r"(?<!Host )(?<!VM )\bConfigure\b"))
        self.assertNotIn("Host Upgrade", content)
        self.assertNotIn("VM Upgrade", content)
        self.assertNotIn("Template Upgrade", content)
        self.assertNotIn("Service Upgrade", content)


if __name__ == "__main__":
    unittest.main()
