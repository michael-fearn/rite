import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class NewVMRunbookTests(unittest.TestCase):
    def test_runbook_documents_new_vm_lifecycle(self):
        runbook = REPO_ROOT / "runbooks" / "new-vm.md"

        self.assertTrue(runbook.is_file())
        content = runbook.read_text()
        expected_phrases = [
            "inventory/vms/<vm>.yaml",
            "Prepare refuses to run when inventory/vms/<vm>.sops.yaml already contains VM SSH key material",
            "public key is plaintext in inventory/vms/<vm>.yaml",
            "private key is encrypted in inventory/vms/<vm>.sops.yaml",
            "just vm-up vm=<name>",
            "Type `apply <name>`",
            "just vm-up vm=<name> auto_confirm=true",
            "skips only the `apply <name>` prompt",
            "Configure waits for cloud-init to complete",
            "just vm-destroy vm=<name>",
            "refuses while any Service Backend references the VM",
            "deletes inventory/vms/<vm>.sops.yaml",
            "just vm-destroy vm=<name> delete_vm_yaml=true",
            "It does not remove Service yamls or parent directories",
            "AFK agent must stop and alert the maintainer",
            "real Host access",
            "destructive approval",
            "manual intervention",
        ]

        for phrase in expected_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, content)


if __name__ == "__main__":
    unittest.main()
