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

        self.assertIn("nfs_mounts:", demo)
        self.assertIn("export: test", demo)
        self.assertIn("mount_point: /mnt/test", demo)
