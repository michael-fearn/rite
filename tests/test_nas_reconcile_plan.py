import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"


class NasReconcilePlanTests(unittest.TestCase):
    def test_just_nas_reconcile_plan_calls_workflow_script(self):
        justfile = (REPO_ROOT / "justfile").read_text()

        self.assertIn("nas-reconcile-plan reality_json:", justfile)
        self.assertIn("./scripts/nas-reconcile-plan --reality-json {{reality_json}}", justfile)
        self.assertIn("nas-reconcile reality_json confirm_disruptive_mount_changes=", justfile)
        self.assertIn("--apply --confirm-disruptive-mount-changes", justfile)

    def test_operator_command_reports_missing_adopted_dataset_without_mutating_truenas(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(json.dumps({"datasets": [], "nfs_shares": []}))
            env = os.environ.copy()
            env["FORTRESS_ROOT"] = str(root)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "nas-reconcile-plan"), "--reality-json", str(reality_path)],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1, result.stderr)
            plan = json.loads(result.stdout)
            self.assertTrue(plan["read_only"])
            self.assertIn("write_actions", plan)
            self.assertEqual(plan["write_actions"], [])
            self.assertIn(
                {
                    "code": "missing_dataset",
                    "dataset": "media",
                    "path": "/mnt/pool/media",
                    "message": "Adopted Dataset media is missing at /mnt/pool/media",
                },
                plan["dataset_findings"],
            )

    def test_plan_reports_adopted_dataset_owner_drift_without_repairing_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(
                json.dumps(
                    {
                        "datasets": [
                            {"path": "/mnt/pool/media", "owner": {"uid": 2000, "gid": 3000}},
                        ],
                        "nfs_shares": [],
                    }
                )
            )

            plan = self._run_plan(root, reality_path)

            self.assertEqual(plan["write_actions"], [])
            self.assertIn(
                {
                    "code": "dataset_owner_drift",
                    "dataset": "media",
                    "path": "/mnt/pool/media",
                    "expected": {"uid": 1000, "gid": 1000},
                    "actual": {"uid": 2000, "gid": 3000},
                    "message": "Adopted Dataset media root owner is 2000:3000, expected 1000:1000",
                },
                plan["dataset_findings"],
            )

    def test_plan_derives_desired_nfs_share_and_reports_missing_share(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(
                json.dumps(
                    {
                        "datasets": [
                            {"path": "/mnt/pool/media", "owner": {"uid": 1000, "gid": 1000}},
                        ],
                        "nfs_shares": [],
                    }
                )
            )

            plan = self._run_plan(root, reality_path)

            desired = {
                "name": "fortress-nfs-media-read-write",
                "dataset": "media",
                "path": "/mnt/pool/media",
                "protocol": "nfs",
                "access": "read_write",
                "clients": ["10.0.10.101"],
            }
            self.assertIn(desired, plan["desired_nfs_shares"])
            self.assertIn(
                {
                    "code": "missing_share",
                    "share": "fortress-nfs-media-read-write",
                    "dataset": "media",
                    "path": "/mnt/pool/media",
                    "message": "Desired NFS Share fortress-nfs-media-read-write is missing",
                },
                plan["share_findings"],
            )

    def test_plan_reports_stale_fortress_owned_share_without_deleting_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(
                json.dumps(
                    {
                        "datasets": [
                            {"path": "/mnt/pool/media", "owner": {"uid": 1000, "gid": 1000}},
                        ],
                        "nfs_shares": [
                            {
                                "name": "fortress-nfs-media-read-write",
                                "path": "/mnt/pool/media",
                                "fortress_owned": True,
                            },
                            {
                                "name": "fortress-nfs-archive-read-only",
                                "path": "/mnt/pool/archive",
                                "fortress_owned": True,
                            },
                        ],
                    }
                )
            )

            plan = self._run_plan(root, reality_path)

            self.assertEqual(plan["write_actions"], [])
            self.assertIn(
                {
                    "code": "stale_fortress_owned_share",
                    "share": "fortress-nfs-archive-read-only",
                    "path": "/mnt/pool/archive",
                    "message": "Fortress-owned NFS Share fortress-nfs-archive-read-only is no longer desired",
                },
                plan["share_findings"],
            )

    def test_unmanaged_share_overlap_blocks_the_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(
                json.dumps(
                    {
                        "datasets": [
                            {"path": "/mnt/pool/media", "owner": {"uid": 1000, "gid": 1000}},
                        ],
                        "nfs_shares": [
                            {
                                "name": "manual-media-share",
                                "path": "/mnt/pool/media",
                                "fortress_owned": False,
                            }
                        ],
                    }
                )
            )

            plan = self._run_plan(root, reality_path)

            self.assertTrue(plan["blocked"])
            self.assertIn(
                {
                    "code": "unmanaged_share_overlap",
                    "share": "manual-media-share",
                    "dataset": "media",
                    "path": "/mnt/pool/media",
                    "message": "Unmanaged NFS Share manual-media-share overlaps desired Dataset media",
                },
                plan["share_findings"],
            )

    def test_connection_settings_are_reported_without_secret_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            group_vars = root / "inventory" / "group_vars" / "all.yaml"
            group_vars.write_text(
                group_vars.read_text().replace(
                    "      address: 10.0.20.10\n",
                    "      address: 10.0.20.10\n"
                    "      api_token_env: TRUENAS_API_TOKEN\n"
                    "      api_token: super-secret-token\n",
                )
            )
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(
                json.dumps(
                    {
                        "datasets": [
                            {"path": "/mnt/pool/media", "owner": {"uid": 1000, "gid": 1000}},
                        ],
                        "nfs_shares": [],
                    }
                )
            )
            env = os.environ.copy()
            env["FORTRESS_ROOT"] = str(root)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "nas-reconcile-plan"), "--reality-json", str(reality_path)],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertNotIn("super-secret-token", result.stdout)
            plan = json.loads(result.stdout)
            self.assertEqual(
                plan["connection"]["truenas"],
                {
                    "address": "10.0.20.10",
                    "api_token_env": "TRUENAS_API_TOKEN",
                    "credentials": "redacted",
                },
            )

    def test_apply_creates_missing_fortress_owned_nfs_share_with_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(
                json.dumps(
                    {
                        "datasets": [
                            {"path": "/mnt/pool/media", "owner": {"uid": 1000, "gid": 1000}},
                        ],
                        "nfs_shares": [],
                    }
                )
            )

            result = self._run_reconcile(root, reality_path, "--apply")

            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertFalse(output["read_only"])
            self.assertEqual(output["rollback_actions"], [])
            self.assertIn(
                {
                    "action": "create_nfs_share",
                    "share": {
                        "name": "fortress-nfs-media-read-write",
                        "path": "/mnt/pool/media",
                        "protocol": "nfs",
                        "access": "read_write",
                        "clients": ["10.0.10.101"],
                        "fortress_owned": True,
                        "fortress_marker": "fortress:nfs-share:fortress-nfs-media-read-write",
                    },
                },
                output["write_actions"],
            )
            self.assertIn(
                {
                    "method": "create_nfs_share",
                    "share": {
                        "name": "fortress-nfs-media-read-write",
                        "path": "/mnt/pool/media",
                        "protocol": "nfs",
                        "access": "read_write",
                        "clients": ["10.0.10.101"],
                        "fortress_owned": True,
                        "fortress_marker": "fortress:nfs-share:fortress-nfs-media-read-write",
                    },
                },
                output["api_operations"],
            )

    def test_apply_updates_drifted_fortress_owned_nfs_share(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(
                json.dumps(
                    {
                        "datasets": [
                            {"path": "/mnt/pool/media", "owner": {"uid": 1000, "gid": 1000}},
                        ],
                        "nfs_shares": [
                            {
                                "name": "fortress-nfs-media-read-write",
                                "path": "/mnt/pool/media",
                                "access": "read_write",
                                "clients": ["10.0.10.199"],
                                "fortress_owned": True,
                            }
                        ],
                    }
                )
            )

            result = self._run_reconcile(root, reality_path, "--apply")

            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertIn(
                {
                    "action": "update_nfs_share",
                    "share": "fortress-nfs-media-read-write",
                    "desired": {
                        "name": "fortress-nfs-media-read-write",
                        "path": "/mnt/pool/media",
                        "protocol": "nfs",
                        "access": "read_write",
                        "clients": ["10.0.10.101"],
                        "fortress_owned": True,
                        "fortress_marker": "fortress:nfs-share:fortress-nfs-media-read-write",
                    },
                },
                output["write_actions"],
            )
            self.assertIn(
                {
                    "method": "update_nfs_share",
                    "share": "fortress-nfs-media-read-write",
                    "desired": {
                        "name": "fortress-nfs-media-read-write",
                        "path": "/mnt/pool/media",
                        "protocol": "nfs",
                        "access": "read_write",
                        "clients": ["10.0.10.101"],
                        "fortress_owned": True,
                        "fortress_marker": "fortress:nfs-share:fortress-nfs-media-read-write",
                    },
                },
                output["api_operations"],
            )

    def test_apply_recognizes_durable_marker_as_fortress_ownership(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(
                json.dumps(
                    {
                        "datasets": [
                            {"path": "/mnt/pool/media", "owner": {"uid": 1000, "gid": 1000}},
                        ],
                        "nfs_shares": [
                            {
                                "name": "fortress-nfs-media-read-write",
                                "path": "/mnt/pool/media",
                                "access": "read_write",
                                "clients": ["10.0.10.199"],
                                "fortress_marker": "fortress:nfs-share:fortress-nfs-media-read-write",
                            }
                        ],
                    }
                )
            )

            result = self._run_reconcile(root, reality_path, "--apply")

            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertIn(
                {
                    "method": "update_nfs_share",
                    "share": "fortress-nfs-media-read-write",
                    "desired": {
                        "name": "fortress-nfs-media-read-write",
                        "path": "/mnt/pool/media",
                        "protocol": "nfs",
                        "access": "read_write",
                        "clients": ["10.0.10.101"],
                        "fortress_owned": True,
                        "fortress_marker": "fortress:nfs-share:fortress-nfs-media-read-write",
                    },
                },
                output["api_operations"],
            )

    def test_apply_deletes_stale_fortress_owned_nfs_share(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(
                json.dumps(
                    {
                        "datasets": [
                            {"path": "/mnt/pool/media", "owner": {"uid": 1000, "gid": 1000}},
                        ],
                        "nfs_shares": [
                            {
                                "name": "fortress-nfs-media-read-write",
                                "path": "/mnt/pool/media",
                                "access": "read_write",
                                "clients": ["10.0.10.101"],
                                "fortress_owned": True,
                                "fortress_marker": "fortress:nfs-share:fortress-nfs-media-read-write",
                            },
                            {
                                "name": "fortress-nfs-archive-read-only",
                                "path": "/mnt/pool/archive",
                                "access": "read_only",
                                "clients": ["10.0.10.101"],
                                "fortress_owned": True,
                                "fortress_marker": "fortress:nfs-share:fortress-nfs-archive-read-only",
                            },
                        ],
                    }
                )
            )

            result = self._run_reconcile(root, reality_path, "--apply")

            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertIn(
                {
                    "action": "delete_nfs_share",
                    "share": "fortress-nfs-archive-read-only",
                    "path": "/mnt/pool/archive",
                },
                output["write_actions"],
            )
            self.assertIn(
                {
                    "method": "delete_nfs_share",
                    "share": "fortress-nfs-archive-read-only",
                },
                output["api_operations"],
            )

    def test_apply_refuses_to_mutate_unmanaged_share_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(
                json.dumps(
                    {
                        "datasets": [
                            {"path": "/mnt/pool/media", "owner": {"uid": 1000, "gid": 1000}},
                        ],
                        "nfs_shares": [
                            {
                                "name": "manual-media-share",
                                "path": "/mnt/pool/media",
                                "access": "read_only",
                                "clients": ["10.0.10.101"],
                                "fortress_owned": False,
                            }
                        ],
                    }
                )
            )

            result = self._run_reconcile(root, reality_path, "--apply")

            self.assertEqual(result.returncode, 1, result.stderr)
            output = json.loads(result.stdout)
            self.assertTrue(output["blocked"])
            self.assertEqual(output["write_actions"], [])
            self.assertEqual(output["api_operations"], [])

    def test_apply_requires_confirmation_for_disruptive_mount_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(
                json.dumps(
                    {
                        "datasets": [
                            {"path": "/mnt/pool/media", "owner": {"uid": 1000, "gid": 1000}},
                        ],
                        "nfs_shares": [],
                        "previous_mounts": [
                            {
                                "vm": "media01",
                                "name": "media",
                                "dataset": "media",
                                "access": "read_only",
                                "mount_point": "/mnt/nas/old-media",
                            },
                            {
                                "vm": "media01",
                                "name": "archive",
                                "dataset": "archive",
                                "access": "read_only",
                                "mount_point": "/mnt/nas/archive",
                            },
                        ],
                    }
                )
            )

            blocked_result = self._run_reconcile(root, reality_path, "--apply")

            self.assertEqual(blocked_result.returncode, 1, blocked_result.stderr)
            blocked = json.loads(blocked_result.stdout)
            self.assertTrue(blocked["confirmation_required"])
            self.assertEqual(blocked["write_actions"], [])
            self.assertEqual(
                blocked["preflight_findings"],
                [
                    {
                        "code": "mount_removed",
                        "vm": "media01",
                        "mount": "archive",
                        "dataset": "archive",
                        "message": "Mount archive on VM media01 was removed",
                    },
                    {
                        "code": "mount_access_changed",
                        "vm": "media01",
                        "mount": "media",
                        "previous": "read_only",
                        "current": "read_write",
                        "message": "Mount media on VM media01 access changed from read_only to read_write",
                    },
                    {
                        "code": "mount_point_changed",
                        "vm": "media01",
                        "mount": "media",
                        "previous": "/mnt/nas/old-media",
                        "current": "/mnt/nas/media",
                        "message": "Mount media on VM media01 mount_point changed from /mnt/nas/old-media to /mnt/nas/media",
                    },
                ],
            )

            confirmed_result = self._run_reconcile(
                root,
                reality_path,
                "--apply",
                "--confirm-disruptive-mount-changes",
            )

            self.assertEqual(confirmed_result.returncode, 0, confirmed_result.stderr)
            confirmed = json.loads(confirmed_result.stdout)
            self.assertFalse(confirmed["confirmation_required"])
            self.assertIn(
                {
                    "method": "create_nfs_share",
                    "share": {
                        "name": "fortress-nfs-media-read-write",
                        "path": "/mnt/pool/media",
                        "protocol": "nfs",
                        "access": "read_write",
                        "clients": ["10.0.10.101"],
                        "fortress_owned": True,
                        "fortress_marker": "fortress:nfs-share:fortress-nfs-media-read-write",
                    },
                },
                confirmed["api_operations"],
            )

    def test_acceptance_apply_creates_missing_ephemeral_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "datasets" / "media.yaml").write_text(
                "name: acceptance-media\n"
                "nas: truenas\n"
                "path: /mnt/pool/fortress-acceptance/media\n"
                "lifecycle: ephemeral\n"
            )
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(json.dumps({"datasets": [], "nfs_shares": []}))

            result = self._run_reconcile(
                root,
                reality_path,
                "--apply",
                "--acceptance-ephemeral-datasets",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertIn(
                {
                    "action": "create_dataset",
                    "dataset": {
                        "name": "acceptance-media",
                        "path": "/mnt/pool/fortress-acceptance/media",
                        "lifecycle": "ephemeral",
                        "fortress_marker": "fortress:ephemeral-dataset:acceptance-media",
                    },
                },
                output["write_actions"],
            )
            self.assertIn(
                {
                    "method": "create_dataset",
                    "dataset": {
                        "name": "acceptance-media",
                        "path": "/mnt/pool/fortress-acceptance/media",
                        "lifecycle": "ephemeral",
                        "fortress_marker": "fortress:ephemeral-dataset:acceptance-media",
                    },
                },
                output["api_operations"],
            )

    def test_acceptance_apply_derives_share_for_ephemeral_dataset_mount(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "datasets" / "media.yaml").write_text(
                "name: acceptance-media\n"
                "nas: truenas\n"
                "path: /mnt/pool/fortress-acceptance/media\n"
                "lifecycle: ephemeral\n"
            )
            vm_path = root / "inventory" / "vms" / "media01.yaml"
            vm_path.write_text(vm_path.read_text().replace("dataset: media\n", "dataset: acceptance-media\n"))
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(
                json.dumps(
                    {
                        "datasets": [
                            {
                                "path": "/mnt/pool/fortress-acceptance/media",
                                "fortress_marker": "fortress:ephemeral-dataset:acceptance-media",
                            }
                        ],
                        "nfs_shares": [],
                    }
                )
            )

            result = self._run_reconcile(
                root,
                reality_path,
                "--apply",
                "--acceptance-ephemeral-datasets",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertIn(
                {
                    "name": "fortress-nfs-acceptance-media-read-write",
                    "dataset": "acceptance-media",
                    "path": "/mnt/pool/fortress-acceptance/media",
                    "protocol": "nfs",
                    "access": "read_write",
                    "clients": ["10.0.10.101"],
                },
                output["desired_nfs_shares"],
            )
            self.assertIn(
                {
                    "method": "create_nfs_share",
                    "share": {
                        "name": "fortress-nfs-acceptance-media-read-write",
                        "path": "/mnt/pool/fortress-acceptance/media",
                        "protocol": "nfs",
                        "access": "read_write",
                        "clients": ["10.0.10.101"],
                        "fortress_owned": True,
                        "fortress_marker": "fortress:nfs-share:fortress-nfs-acceptance-media-read-write",
                    },
                },
                output["api_operations"],
            )

    def test_ordinary_apply_does_not_create_ephemeral_dataset_or_share(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "datasets" / "media.yaml").write_text(
                "name: acceptance-media\n"
                "nas: truenas\n"
                "path: /mnt/pool/fortress-acceptance/media\n"
                "lifecycle: ephemeral\n"
            )
            vm_path = root / "inventory" / "vms" / "media01.yaml"
            vm_path.write_text(vm_path.read_text().replace("dataset: media\n", "dataset: acceptance-media\n"))
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(json.dumps({"datasets": [], "nfs_shares": []}))

            result = self._run_reconcile(root, reality_path, "--apply")

            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertEqual(output["write_actions"], [])
            self.assertEqual(output["api_operations"], [])
            self.assertEqual(output["desired_nfs_shares"], [])

    def test_acceptance_cleanup_deletes_only_marked_ephemeral_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "datasets" / "media.yaml").write_text(
                "name: acceptance-media\n"
                "nas: truenas\n"
                "path: /mnt/pool/fortress-acceptance/media\n"
                "lifecycle: ephemeral\n"
            )
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(
                json.dumps(
                    {
                        "datasets": [
                            {
                                "path": "/mnt/pool/fortress-acceptance/media",
                                "fortress_marker": "fortress:ephemeral-dataset:acceptance-media",
                            }
                        ],
                        "nfs_shares": [],
                    }
                )
            )

            result = self._run_reconcile(
                root,
                reality_path,
                "--apply",
                "--acceptance-ephemeral-datasets",
                "--destroy-ephemeral-datasets",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertIn(
                {
                    "action": "delete_dataset",
                    "dataset": "acceptance-media",
                    "path": "/mnt/pool/fortress-acceptance/media",
                },
                output["write_actions"],
            )
            self.assertIn(
                {
                    "method": "delete_dataset",
                    "dataset": "acceptance-media",
                    "path": "/mnt/pool/fortress-acceptance/media",
                },
                output["api_operations"],
            )

    def test_acceptance_cleanup_deletes_fortress_owned_share_for_ephemeral_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "datasets" / "media.yaml").write_text(
                "name: acceptance-media\n"
                "nas: truenas\n"
                "path: /mnt/pool/fortress-acceptance/media\n"
                "lifecycle: ephemeral\n"
            )
            vm_path = root / "inventory" / "vms" / "media01.yaml"
            vm_path.write_text(vm_path.read_text().replace("dataset: media\n", "dataset: acceptance-media\n"))
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(
                json.dumps(
                    {
                        "datasets": [
                            {
                                "path": "/mnt/pool/fortress-acceptance/media",
                                "fortress_marker": "fortress:ephemeral-dataset:acceptance-media",
                            }
                        ],
                        "nfs_shares": [
                            {
                                "name": "fortress-nfs-acceptance-media-read-write",
                                "path": "/mnt/pool/fortress-acceptance/media",
                                "fortress_marker": "fortress:nfs-share:fortress-nfs-acceptance-media-read-write",
                            }
                        ],
                    }
                )
            )

            result = self._run_reconcile(
                root,
                reality_path,
                "--apply",
                "--acceptance-ephemeral-datasets",
                "--destroy-ephemeral-datasets",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertIn(
                {
                    "method": "delete_nfs_share",
                    "share": "fortress-nfs-acceptance-media-read-write",
                },
                output["api_operations"],
            )

    def test_acceptance_cleanup_refuses_unmanaged_share_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "datasets" / "media.yaml").write_text(
                "name: acceptance-media\n"
                "nas: truenas\n"
                "path: /mnt/pool/fortress-acceptance/media\n"
                "lifecycle: ephemeral\n"
            )
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(
                json.dumps(
                    {
                        "datasets": [
                            {
                                "path": "/mnt/pool/fortress-acceptance/media",
                                "fortress_marker": "fortress:ephemeral-dataset:acceptance-media",
                            }
                        ],
                        "nfs_shares": [
                            {
                                "name": "manual-acceptance-media",
                                "path": "/mnt/pool/fortress-acceptance/media",
                            }
                        ],
                    }
                )
            )

            result = self._run_reconcile(
                root,
                reality_path,
                "--apply",
                "--acceptance-ephemeral-datasets",
                "--destroy-ephemeral-datasets",
            )

            self.assertEqual(result.returncode, 1, result.stderr)
            output = json.loads(result.stdout)
            self.assertTrue(output["blocked"])
            self.assertEqual(output["write_actions"], [])
            self.assertEqual(output["api_operations"], [])
            self.assertIn(
                {
                    "code": "unmanaged_share_overlap",
                    "share": "manual-acceptance-media",
                    "dataset": "acceptance-media",
                    "path": "/mnt/pool/fortress-acceptance/media",
                    "message": "Unmanaged NFS Share manual-acceptance-media overlaps Ephemeral Dataset acceptance-media",
                },
                output["share_findings"],
            )

    def test_acceptance_cleanup_reports_unmarked_ephemeral_dataset_without_deleting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "datasets" / "media.yaml").write_text(
                "name: acceptance-media\n"
                "nas: truenas\n"
                "path: /mnt/pool/fortress-acceptance/media\n"
                "lifecycle: ephemeral\n"
            )
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(
                json.dumps(
                    {
                        "datasets": [{"path": "/mnt/pool/fortress-acceptance/media"}],
                        "nfs_shares": [],
                    }
                )
            )

            result = self._run_reconcile(
                root,
                reality_path,
                "--apply",
                "--acceptance-ephemeral-datasets",
                "--destroy-ephemeral-datasets",
            )

            self.assertEqual(result.returncode, 1, result.stderr)
            output = json.loads(result.stdout)
            self.assertTrue(output["blocked"])
            self.assertEqual(output["write_actions"], [])
            self.assertEqual(output["api_operations"], [])
            self.assertIn(
                {
                    "code": "unmarked_ephemeral_dataset",
                    "dataset": "acceptance-media",
                    "path": "/mnt/pool/fortress-acceptance/media",
                    "message": (
                        "Ephemeral Dataset acceptance-media at /mnt/pool/fortress-acceptance/media "
                        "is not marked as fortress-created; leaving it behind"
                    ),
                },
                output["dataset_findings"],
            )

    def _run_plan(self, root, reality_path):
        result = self._run_reconcile(root, reality_path)
        self.assertIn(result.returncode, {0, 1}, result.stderr)
        return json.loads(result.stdout)

    def _run_reconcile(self, root, reality_path, *args):
        env = os.environ.copy()
        env["FORTRESS_ROOT"] = str(root)
        return subprocess.run(
            [str(REPO_ROOT / "scripts" / "nas-reconcile-plan"), "--reality-json", str(reality_path), *args],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
