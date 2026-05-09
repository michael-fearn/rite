import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class NASTrueNASRunbookTests(unittest.TestCase):
    def test_runbook_documents_uid_gid_and_dataset_ownership_steps(self):
        runbook = (REPO_ROOT / "runbooks" / "nas-truenas.md").read_text()

        self.assertIn("UID/GID convention", runbook)
        self.assertIn("inventory/group_vars/all.yaml", runbook)
        self.assertIn("uid_gid_map", runbook)
        self.assertIn("chown", runbook)
        self.assertIn("TrueNAS", runbook)

    def test_demo_vm_declares_systemd_managed_nfs_mount(self):
        demo = (REPO_ROOT / "inventory" / "vms" / "wintermute-demo.yaml").read_text()
        dataset = (REPO_ROOT / "inventory" / "datasets" / "acceptance-nfs-demo.yaml").read_text()

        self.assertIn("mounts:", demo)
        self.assertIn("dataset: acceptance-nfs-demo", demo)
        self.assertIn("protocol: nfs", demo)
        self.assertIn("mount_point: /mnt/nfs-demo", demo)
        self.assertNotIn("dataset: test", demo)
        self.assertIn("name: acceptance-nfs-demo", dataset)
        self.assertIn("lifecycle: ephemeral", dataset)

    def test_runbook_documents_nas_credential_ceremony(self):
        runbook = (REPO_ROOT / "runbooks" / "nas-truenas.md").read_text()

        self.assertIn("NAS Credential Ceremony", runbook)
        self.assertIn("fortress-nas-reconcile", runbook)
        self.assertIn("Dataset-read", runbook)
        self.assertIn("NFS-Share-manage", runbook)
        self.assertIn("fortress-acceptance-ephemeral", runbook)
        self.assertIn("Ephemeral Dataset", runbook)
        self.assertIn("api_credentials.reconcile.value", runbook)
        self.assertIn("api_credentials.acceptance.value", runbook)
        self.assertIn("generated API key string", runbook)
        self.assertIn("ordinary Datasets", runbook)
        self.assertIn("docs/adr/0019-truenas-api-authentication-uses-operator-environment.md", runbook)

    def test_runbook_documents_live_operator_demo_checklist(self):
        runbook = (REPO_ROOT / "runbooks" / "nas-truenas.md").read_text()

        self.assertIn("Live operator demo checklist", runbook)
        self.assertIn("NAS Endpoint", runbook)
        self.assertIn("Management Address", runbook)
        self.assertIn("Share Address", runbook)
        self.assertIn("scripts/nas-reconcile-plan --live truenas", runbook)
        self.assertIn("preflight", runbook)
        self.assertIn("read-only plan", runbook)
        self.assertIn("without mutating TrueNAS", runbook)
        self.assertIn("scripts/nas-reconcile-plan --live truenas --acceptance-ephemeral-datasets --apply", runbook)
        self.assertIn("systemctl is-active mnt-nfs\\x2ddemo.mount", runbook)
        self.assertIn("findmnt /mnt/nfs-demo", runbook)
        self.assertIn(
            "scripts/nas-reconcile-plan --live truenas --acceptance-ephemeral-datasets --destroy-ephemeral-datasets --apply",
            runbook,
        )
        self.assertIn("missing SOPS material", runbook)
        self.assertIn("insufficient privilege", runbook)
