import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fortress_nas.truenas_client import (
    MANAGEMENT_API_REACHABILITY,
    NAS_RECONCILE_CREDENTIAL_AUTHENTICATION,
    NFS_SHARE_READ,
    LiveTrueNasClient,
    TrueNasCapabilityError,
)
from fortress_nas.reconcile import build_nas_reconcile_plan, load_reality
from fortress_nas.truenas_reality import load_live_truenas_reality
from fortress_inventory.model import load_inventory_tree


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"


class NasReconcilePlanTests(unittest.TestCase):
    def test_just_nas_reconcile_plan_calls_workflow_script(self):
        justfile = (REPO_ROOT / "justfile").read_text()

        self.assertIn("nas-reconcile-plan reality_json:", justfile)
        self.assertIn("./scripts/nas-reconcile-plan --reality-json {{reality_json}}", justfile)
        self.assertIn("nas-reconcile reality_json confirm_disruptive_mount_changes=", justfile)
        self.assertIn("--apply --confirm-disruptive-mount-changes", justfile)
        self.assertIn("nas-reconcile-live-plan endpoint:", justfile)
        self.assertIn("./scripts/nas-reconcile-plan --live {{endpoint}}", justfile)
        self.assertIn("nas-reconcile-live endpoint confirm_disruptive_mount_changes=", justfile)
        self.assertIn("--live {{endpoint}} --apply --confirm-disruptive-mount-changes", justfile)

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
                    "management_address": "10.0.10.10",
                    "share_address": "10.0.20.10",
                },
            )

    def test_live_plan_requires_named_nas_endpoint_before_loading_reality(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            endpoint_path = root / "inventory" / "nas" / "truenas.yaml"
            endpoint_path.unlink()

            result = self._run_live_reconcile(root, "truenas")

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("NAS Endpoint truenas is not declared in Inventory", result.stderr)
            self.assertIn("inventory/nas/truenas.yaml", result.stderr)

    def test_live_plan_requires_endpoint_sibling_sops_file_before_loading_reality(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)

            result = self._run_live_reconcile(root, "truenas")

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("NAS Endpoint Sibling SOPS File is required", result.stderr)
            self.assertIn("inventory/nas/truenas.sops.yaml", result.stderr)

    def test_live_plan_uses_internal_reconcile_token_env_when_endpoint_has_no_api_token_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            endpoint_path = root / "inventory" / "nas" / "truenas.yaml"
            self.assertNotIn("api_token_env", endpoint_path.read_text())
            (root / "inventory" / "nas" / "truenas.sops.yaml").write_text(
                "api_credentials:\n  reconcile:\n    value: super-secret-token\n"
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
            env_log = root / "live-env.log"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_sops = bin_dir / "sops"
            fake_sops.write_text("#!/usr/bin/env bash\nprintf 'super-secret-token\\n'\n")
            fake_sops.chmod(fake_sops.stat().st_mode | stat.S_IXUSR)

            result = self._run_live_reconcile(
                root,
                "truenas",
                extra_env={
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                    "FORTRESS_FAKE_TRUENAS_REALITY_JSON": str(reality_path),
                    "FORTRESS_FAKE_TRUENAS_ENV_LOG": str(env_log),
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(env_log.read_text(), "FORTRESS_NAS_RECONCILE_TRUENAS_TOKEN=super-secret-token\n")
            self.assertNotIn("FORTRESS_NAS_RECONCILE_TRUENAS_TOKEN", result.stdout)
            self.assertNotIn("super-secret-token", result.stdout)
            self.assertNotIn("super-secret-token", result.stderr)
            plan = json.loads(result.stdout)
            self.assertNotIn("api_token_env", plan["connection"]["truenas"])
            self.assertEqual(
                plan["connection"]["truenas"]["credential_source"],
                "inventory/nas/truenas.sops.yaml:api_credentials.reconcile.value",
            )
            self.assertEqual(plan["connection"]["truenas"]["credentials"], "operator_environment")

    def test_live_plan_reports_failed_sops_extraction_without_printing_credential(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "nas" / "truenas.sops.yaml").write_text("encrypted\n")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_sops = bin_dir / "sops"
            fake_sops.write_text(
                "#!/usr/bin/env bash\n"
                "printf 'super-secret-token should stay hidden\\n' >&2\n"
                "exit 1\n"
            )
            fake_sops.chmod(fake_sops.stat().st_mode | stat.S_IXUSR)

            result = self._run_live_reconcile(root, "truenas", extra_env={"PATH": f"{bin_dir}:{os.environ['PATH']}"})

            self.assertEqual(result.returncode, 1)
            self.assertIn("failed to decrypt NAS Reconcile Credential", result.stderr)
            self.assertIn("inventory/nas/truenas.sops.yaml", result.stderr)
            self.assertNotIn("super-secret-token", result.stderr)

    def test_live_plan_exports_reconcile_credential_only_to_child_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "nas" / "truenas.sops.yaml").write_text("encrypted\n")
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
            env_log = root / "live-env.log"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_sops = bin_dir / "sops"
            fake_sops.write_text("#!/usr/bin/env bash\nprintf 'super-secret-token\\n'\n")
            fake_sops.chmod(fake_sops.stat().st_mode | stat.S_IXUSR)

            result = self._run_live_reconcile(
                root,
                "truenas",
                extra_env={
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                    "FORTRESS_FAKE_TRUENAS_REALITY_JSON": str(reality_path),
                    "FORTRESS_FAKE_TRUENAS_ENV_LOG": str(env_log),
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("super-secret-token", result.stdout)
            self.assertNotIn("super-secret-token", result.stderr)
            self.assertEqual(env_log.read_text(), "FORTRESS_NAS_RECONCILE_TRUENAS_TOKEN=super-secret-token\n")
            plan = json.loads(result.stdout)
            self.assertTrue(plan["read_only"])
            self.assertEqual(
                plan["connection"]["truenas"]["credential_source"],
                "inventory/nas/truenas.sops.yaml:api_credentials.reconcile.value",
            )
            self.assertEqual(plan["connection"]["truenas"]["credentials"], "operator_environment")

    def test_live_apply_creates_missing_fortress_owned_nfs_share_through_truenas_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "nas" / "truenas.sops.yaml").write_text("encrypted\n")
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
            apply_log = root / "live-apply.jsonl"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_sops = bin_dir / "sops"
            fake_sops.write_text("#!/usr/bin/env bash\nprintf 'super-secret-token\\n'\n")
            fake_sops.chmod(fake_sops.stat().st_mode | stat.S_IXUSR)

            result = self._run_live_reconcile(
                root,
                "truenas",
                "--apply",
                extra_env={
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                    "FORTRESS_FAKE_TRUENAS_REALITY_JSON": str(reality_path),
                    "FORTRESS_FAKE_TRUENAS_APPLY_LOG": str(apply_log),
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertNotIn("api_operations", output)
            self.assertEqual(
                [json.loads(line) for line in apply_log.read_text().splitlines()],
                [
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
                    }
                ],
            )

    def test_live_apply_reexecs_into_selected_runtime_before_opening_apply_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "nas" / "truenas.sops.yaml").write_text("encrypted\n")
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
            apply_log = root / "live-apply.jsonl"
            runtime_log = root / "runtime.log"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_sops = bin_dir / "sops"
            fake_sops.write_text("#!/usr/bin/env bash\nprintf 'super-secret-token\\n'\n")
            fake_sops.chmod(fake_sops.stat().st_mode | stat.S_IXUSR)
            fake_python = bin_dir / "fortress-python"
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$*\" >> \"$FORTRESS_RUNTIME_LOG\"\n"
                f"exec {sys.executable} \"$@\"\n"
            )
            fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)

            result = self._run_live_reconcile(
                root,
                "truenas",
                "--apply",
                extra_env={
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                    "FORTRESS_PYTHON": str(fake_python),
                    "FORTRESS_RUNTIME_LOG": str(runtime_log),
                    "FORTRESS_FAKE_TRUENAS_REALITY_JSON": str(reality_path),
                    "FORTRESS_FAKE_TRUENAS_APPLY_LOG": str(apply_log),
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("scripts/nas-reconcile-plan", runtime_log.read_text())
            self.assertTrue(apply_log.is_file())

    def test_live_acceptance_apply_uses_acceptance_credential_for_ephemeral_dataset_and_share(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "nas" / "truenas.sops.yaml").write_text("encrypted\n")
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
            apply_log = root / "live-apply.jsonl"
            env_log = root / "live-env.log"
            sops_log = root / "sops.log"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_sops = bin_dir / "sops"
            fake_sops.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$*\" >> \"$SOPS_LOG\"\n"
                "case \"$*\" in\n"
                "  *'acceptance'* ) printf 'acceptance-secret-token\\n' ;;\n"
                "  * ) printf 'reconcile-secret-token\\n' ;;\n"
                "esac\n"
            )
            fake_sops.chmod(fake_sops.stat().st_mode | stat.S_IXUSR)

            result = self._run_live_reconcile(
                root,
                "truenas",
                "--apply",
                "--acceptance-ephemeral-datasets",
                extra_env={
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                    "SOPS_LOG": str(sops_log),
                    "FORTRESS_FAKE_TRUENAS_REALITY_JSON": str(reality_path),
                    "FORTRESS_FAKE_TRUENAS_ENV_LOG": str(env_log),
                    "FORTRESS_FAKE_TRUENAS_APPLY_LOG": str(apply_log),
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('["api_credentials"]["acceptance"]["value"]', sops_log.read_text())
            self.assertEqual(
                env_log.read_text(),
                "FORTRESS_NAS_ACCEPTANCE_TRUENAS_TOKEN=acceptance-secret-token\n",
            )
            plan = json.loads(result.stdout)
            self.assertEqual(
                plan["connection"]["truenas"]["credential_source"],
                "inventory/nas/truenas.sops.yaml:api_credentials.acceptance.value",
            )
            self.assertNotIn("acceptance-secret-token", result.stdout)
            self.assertNotIn("reconcile-secret-token", result.stdout)
            self.assertEqual(
                [json.loads(line) for line in apply_log.read_text().splitlines()],
                [
                    {
                        "method": "create_dataset",
                        "dataset": {
                            "name": "acceptance-media",
                            "path": "/mnt/pool/fortress-acceptance/media",
                            "lifecycle": "ephemeral",
                            "fortress_marker": "fortress:ephemeral-dataset:acceptance-media",
                        },
                    },
                    {
                        "method": "create_nfs_share",
                        "share": {
                            "name": "fortress-nfs-acceptance-media-read-write",
                            "path": "/mnt/pool/fortress-acceptance/media",
                            "protocol": "nfs",
                            "access": "read_write",
                            "clients": ["10.0.10.101"],
                            "maproot_user": "root",
                            "maproot_group": "root",
                            "fortress_owned": True,
                            "fortress_marker": "fortress:nfs-share:fortress-nfs-acceptance-media-read-write",
                        },
                    },
                ],
            )

    def test_live_apply_updates_and_deletes_fortress_owned_nfs_shares_through_truenas_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "nas" / "truenas.sops.yaml").write_text("encrypted\n")
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
                            },
                            {
                                "name": "fortress-nfs-archive-read-only",
                                "path": "/mnt/pool/archive",
                                "access": "read_only",
                                "clients": ["10.0.10.101"],
                                "fortress_marker": "fortress:nfs-share:fortress-nfs-archive-read-only",
                            },
                        ],
                    }
                )
            )
            apply_log = root / "live-apply.jsonl"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_sops = bin_dir / "sops"
            fake_sops.write_text("#!/usr/bin/env bash\nprintf 'super-secret-token\\n'\n")
            fake_sops.chmod(fake_sops.stat().st_mode | stat.S_IXUSR)

            result = self._run_live_reconcile(
                root,
                "truenas",
                "--apply",
                extra_env={
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                    "FORTRESS_FAKE_TRUENAS_REALITY_JSON": str(reality_path),
                    "FORTRESS_FAKE_TRUENAS_APPLY_LOG": str(apply_log),
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                [json.loads(line) for line in apply_log.read_text().splitlines()],
                [
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
                    {
                        "method": "delete_nfs_share",
                        "share": "fortress-nfs-archive-read-only",
                    },
                ],
            )

    def test_live_apply_stops_on_first_truenas_write_failure_and_uses_forward_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "nas" / "truenas.sops.yaml").write_text("encrypted\n")
            initial_reality_path = root / "initial-truenas-reality.json"
            initial_reality_path.write_text(
                json.dumps(
                    {
                        "datasets": [
                            {"path": "/mnt/pool/media", "owner": {"uid": 1000, "gid": 1000}},
                        ],
                        "nfs_shares": [
                            {
                                "name": "fortress-nfs-archive-read-only",
                                "path": "/mnt/pool/archive",
                                "access": "read_only",
                                "clients": ["10.0.10.101"],
                                "fortress_marker": "fortress:nfs-share:fortress-nfs-archive-read-only",
                            },
                        ],
                    }
                )
            )
            retry_reality_path = root / "retry-truenas-reality.json"
            retry_reality_path.write_text(
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
                                "fortress_marker": "fortress:nfs-share:fortress-nfs-media-read-write",
                            },
                            {
                                "name": "fortress-nfs-archive-read-only",
                                "path": "/mnt/pool/archive",
                                "access": "read_only",
                                "clients": ["10.0.10.101"],
                                "fortress_marker": "fortress:nfs-share:fortress-nfs-archive-read-only",
                            },
                        ],
                    }
                )
            )
            apply_log = root / "live-apply.jsonl"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_sops = bin_dir / "sops"
            fake_sops.write_text("#!/usr/bin/env bash\nprintf 'super-secret-token\\n'\n")
            fake_sops.chmod(fake_sops.stat().st_mode | stat.S_IXUSR)
            fake_env = {
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "FORTRESS_FAKE_TRUENAS_REALITY_JSON": str(initial_reality_path),
                "FORTRESS_FAKE_TRUENAS_APPLY_LOG": str(apply_log),
                "FORTRESS_FAKE_TRUENAS_FAIL_METHOD": "delete_nfs_share",
            }

            failed = self._run_live_reconcile(root, "truenas", "--apply", extra_env=fake_env)

            self.assertEqual(failed.returncode, 1)
            self.assertEqual(failed.stdout, "")
            self.assertIn("delete_nfs_share", failed.stderr)
            self.assertIn("fortress-nfs-archive-read-only", failed.stderr)
            self.assertNotIn("rollback", failed.stderr.lower())
            self.assertEqual(
                [json.loads(line) for line in apply_log.read_text().splitlines()],
                [
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
                    }
                ],
            )

            retry = self._run_live_reconcile(
                root,
                "truenas",
                extra_env={
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                    "FORTRESS_FAKE_TRUENAS_REALITY_JSON": str(retry_reality_path),
                },
            )

            self.assertEqual(retry.returncode, 0, retry.stderr)
            retry_plan = json.loads(retry.stdout)
            self.assertIn(
                {
                    "code": "stale_fortress_owned_share",
                    "share": "fortress-nfs-archive-read-only",
                    "path": "/mnt/pool/archive",
                    "message": "Fortress-owned NFS Share fortress-nfs-archive-read-only is no longer desired",
                },
                retry_plan["share_findings"],
            )

    def test_live_plan_reports_preflight_capability_failure_without_printing_credential(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "nas" / "truenas.sops.yaml").write_text("encrypted\n")
            reality_path = root / "truenas-reality.json"
            reality_path.write_text(json.dumps({"datasets": [], "nfs_shares": []}))
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_sops = bin_dir / "sops"
            fake_sops.write_text("#!/usr/bin/env bash\nprintf 'super-secret-token\\n'\n")
            fake_sops.chmod(fake_sops.stat().st_mode | stat.S_IXUSR)

            result = self._run_live_reconcile(
                root,
                "truenas",
                extra_env={
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                    "FORTRESS_FAKE_TRUENAS_REALITY_JSON": str(reality_path),
                    "FORTRESS_FAKE_TRUENAS_PREFLIGHT_FAILURE": (
                        "TrueNAS preflight failed: Dataset read failed for super-secret-token"
                    ),
                },
            )

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("Dataset read", result.stderr)
            self.assertIn("failed to load live TrueNAS reality", result.stderr)
            self.assertNotIn("super-secret-token", result.stderr)

    def test_live_plan_reports_missing_truenas_api_client_runtime_without_printing_credential(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            (root / "inventory" / "nas" / "truenas.sops.yaml").write_text("encrypted\n")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_sops = bin_dir / "sops"
            fake_sops.write_text("#!/usr/bin/env bash\nprintf 'super-secret-token\\n'\n")
            fake_sops.chmod(fake_sops.stat().st_mode | stat.S_IXUSR)
            fake_python = bin_dir / "python-no-site"
            fake_python.write_text(f"#!/usr/bin/env bash\nexec {sys.executable} -S \"$@\"\n")
            fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)

            result = self._run_live_reconcile(
                root,
                "truenas",
                extra_env={
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                    "FORTRESS_PYTHON": str(fake_python),
                },
            )

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("failed to load live TrueNAS reality", result.stderr)
            self.assertIn("truenas_api_client", result.stderr)
            self.assertIn("/opt/fortress-python/bin/python3", result.stderr)
            self.assertIn("scripts/setup/install-toolchain.sh", result.stderr)
            self.assertNotIn("super-secret-token", result.stderr)

    def test_live_reality_module_reports_missing_truenas_api_client_runtime(self):
        env = os.environ.copy()
        env["FORTRESS_NAS_RECONCILE_TRUENAS_TOKEN"] = "super-secret-token"
        env["PYTHONPATH"] = str(REPO_ROOT)

        result = subprocess.run(
            [
                sys.executable,
                "-S",
                "-m",
                "fortress_nas.truenas_reality",
                "truenas",
                "127.0.0.1",
                "FORTRESS_NAS_RECONCILE_TRUENAS_TOKEN",
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("TrueNAS preflight failed for NAS Endpoint truenas", result.stderr)
        self.assertIn("truenas_api_client", result.stderr)
        self.assertIn("/opt/fortress-python/bin/python3", result.stderr)
        self.assertIn("scripts/setup/install-toolchain.sh", result.stderr)
        self.assertNotIn("super-secret-token", result.stderr)

    def test_live_truenas_adapter_runs_non_mutating_preflight_before_loading_reality(self):
        raw_client = FakeTrueNasRawClient(
            responses={
                "core.ping": "pong",
                "pool.dataset.query": [
                    {"id": "pool/media", "mountpoint": {"value": "/mnt/pool/media"}},
                ],
                "sharing.nfs.query": [
                    {
                        "id": 7,
                        "comment": "fortress-nfs-media-read-write",
                        "paths": ["/mnt/pool/media"],
                        "hosts": ["10.0.10.101"],
                    }
                ],
                "filesystem.stat": {"uid": 1000, "gid": 1000},
            }
        )

        reality = load_live_truenas_reality(
            "10.0.10.10",
            "operator:super-secret-token",
            client_factory=FakeTrueNasClientFactory(raw_client),
        )

        self.assertEqual(
            raw_client.operations[2:6],
            [
                ("login_with_api_key", "operator", "super-secret-token"),
                ("call", "core.ping", ()),
                ("call", "pool.dataset.query", ([], {"limit": 1})),
                ("call", "sharing.nfs.query", ([], {"limit": 1})),
            ],
        )
        self.assertNotIn("create", str(raw_client.operations))
        self.assertNotIn("update", str(raw_client.operations))
        self.assertNotIn("delete", str(raw_client.operations))
        self.assertEqual(
            reality,
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
                    }
                ],
                "previous_mounts": [],
            },
        )

    def test_live_truenas_adapter_authenticates_jsonrpc_client_with_api_key_call(self):
        raw_client = FakeTrueNasJsonRpcClient(
            responses={
                "auth.login_with_api_key": True,
                "core.ping": "pong",
                "pool.dataset.query": [],
                "sharing.nfs.query": [],
            }
        )

        reality = load_live_truenas_reality(
            "10.0.10.10",
            "operator:super-secret-token",
            client_factory=FakeTrueNasClientFactory(raw_client),
        )

        self.assertEqual(
            raw_client.operations[0:6],
            [
                ("connect", "wss://10.0.10.10/api/current", {"verify_ssl": True}),
                ("enter", None, ()),
                ("call", "auth.login_with_api_key", ("super-secret-token",)),
                ("call", "core.ping", ()),
                ("call", "pool.dataset.query", ([], {"limit": 1})),
                ("call", "sharing.nfs.query", ([], {"limit": 1})),
            ],
        )
        self.assertEqual(reality, {"datasets": [], "nfs_shares": [], "previous_mounts": []})

    def test_live_truenas_adapter_can_disable_tls_certificate_verification(self):
        raw_client = FakeTrueNasJsonRpcClient(
            responses={
                "auth.login_with_api_key": True,
                "core.ping": "pong",
                "pool.dataset.query": [],
                "sharing.nfs.query": [],
            }
        )

        load_live_truenas_reality(
            "10.0.10.10",
            "super-secret-token",
            client_factory=FakeTrueNasClientFactory(raw_client),
            tls_verify=False,
        )

        self.assertEqual(
            raw_client.operations[0],
            ("connect", "wss://10.0.10.10/api/current", {"verify_ssl": False}),
        )

    def test_live_truenas_adapter_names_jsonrpc_invalid_credential_without_printing_it(self):
        raw_client = FakeTrueNasJsonRpcClient(
            responses={"auth.login_with_api_key": False},
        )

        with self.assertRaises(TrueNasCapabilityError) as raised:
            with LiveTrueNasClient.connect(
                "10.0.10.10",
                "operator:super-secret-token",
                client_class=FakeRawClientClass(raw_client),
            ):
                pass

        self.assertEqual(raised.exception.capability, NAS_RECONCILE_CREDENTIAL_AUTHENTICATION)
        self.assertIn("Invalid API key", str(raised.exception))
        self.assertNotIn("super-secret-token", str(raised.exception))

    def test_live_truenas_adapter_names_failed_preflight_capability_without_credential(self):
        raw_client = FakeTrueNasRawClient(
            responses={"core.ping": "pong"},
            failures={"sharing.nfs.query": RuntimeError("denied super-secret-token")},
        )

        with self.assertRaises(TrueNasCapabilityError) as raised:
            load_live_truenas_reality(
                "10.0.10.10",
                "operator:super-secret-token",
                client_factory=FakeTrueNasClientFactory(raw_client),
            )

        self.assertEqual(raised.exception.capability, NFS_SHARE_READ)
        self.assertIn("NFS Share read", str(raised.exception))
        self.assertNotIn("super-secret-token", str(raised.exception))
        self.assertEqual(
            raw_client.operations[2:6],
            [
                ("login_with_api_key", "operator", "super-secret-token"),
                ("call", "core.ping", ()),
                ("call", "pool.dataset.query", ([], {"limit": 1})),
                ("call", "sharing.nfs.query", ([], {"limit": 1})),
            ],
        )

    def test_live_truenas_adapter_preserves_fortress_owned_nfs_share_marker(self):
        raw_client = FakeTrueNasRawClient(
            responses={
                "core.ping": "pong",
                "pool.dataset.query": [],
                "sharing.nfs.query": [
                    {
                        "id": 7,
                        "comment": "fortress:nfs-share:fortress-nfs-media-read-write",
                        "paths": ["/mnt/pool/media"],
                        "hosts": ["10.0.10.101"],
                    }
                ],
            }
        )

        reality = load_live_truenas_reality(
            "10.0.10.10",
            "operator:super-secret-token",
            client_factory=FakeTrueNasClientFactory(raw_client),
        )

        self.assertEqual(
            reality["nfs_shares"],
            [
                {
                    "name": "fortress-nfs-media-read-write",
                    "path": "/mnt/pool/media",
                    "access": "read_write",
                    "clients": ["10.0.10.101"],
                    "fortress_marker": "fortress:nfs-share:fortress-nfs-media-read-write",
                }
            ],
        )

    def test_live_truenas_adapter_writes_nfs_shares_with_fortress_marker_payload(self):
        raw_client = FakeTrueNasRawClient(
            responses={
                "core.ping": "pong",
                "sharing.nfs.query": [
                    {
                        "id": 7,
                        "comment": "fortress:nfs-share:fortress-nfs-media-read-write",
                    },
                    {
                        "id": 8,
                        "comment": "fortress:nfs-share:fortress-nfs-archive-read-only",
                    },
                ],
                "sharing.nfs.create": {"id": 9},
                "sharing.nfs.update": {"id": 7},
                "sharing.nfs.delete": True,
            }
        )
        desired = {
            "name": "fortress-nfs-media-read-write",
            "path": "/mnt/pool/media",
            "protocol": "nfs",
            "access": "read_write",
            "clients": ["10.0.10.101"],
            "fortress_owned": True,
            "fortress_marker": "fortress:nfs-share:fortress-nfs-media-read-write",
        }

        with LiveTrueNasClient.connect(
            "10.0.10.10",
            "operator:super-secret-token",
            client_class=FakeRawClientClass(raw_client),
        ) as client:
            client.create_nfs_share(desired)
            client.update_nfs_share("fortress-nfs-media-read-write", desired)
            client.delete_nfs_share("fortress-nfs-archive-read-only")

        self.assertEqual(
            raw_client.operations[4:],
            [
                (
                    "call",
                    "sharing.nfs.create",
                    (
                        {
                            "path": "/mnt/pool/media",
                            "comment": "fortress:nfs-share:fortress-nfs-media-read-write",
                            "ro": False,
                            "hosts": ["10.0.10.101"],
                            "enabled": True,
                        },
                    ),
                ),
                ("call", "sharing.nfs.query", ()),
                (
                    "call",
                    "sharing.nfs.update",
                    (
                        7,
                        {
                            "path": "/mnt/pool/media",
                            "comment": "fortress:nfs-share:fortress-nfs-media-read-write",
                            "ro": False,
                            "hosts": ["10.0.10.101"],
                            "enabled": True,
                        },
                    ),
                ),
                ("call", "sharing.nfs.query", ()),
                ("call", "sharing.nfs.delete", (8,)),
                ("exit", None, ()),
            ],
        )

    def test_live_truenas_adapter_applies_ephemeral_dataset_writes(self):
        raw_client = FakeTrueNasRawClient(responses={"core.ping": "pong"})
        dataset = {
            "name": "acceptance-media",
            "path": "/mnt/pool/fortress-acceptance/media",
            "lifecycle": "ephemeral",
            "fortress_marker": "fortress:ephemeral-dataset:acceptance-media",
        }

        with LiveTrueNasClient.connect(
            "10.0.10.10",
            "operator:super-secret-token",
            client_class=FakeRawClientClass(raw_client),
        ) as client:
            client.create_dataset(dataset)
            client.delete_dataset("acceptance-media", "/mnt/pool/fortress-acceptance/media")

        self.assertEqual(
            raw_client.operations[4:],
            [
                (
                    "call",
                    "pool.dataset.create",
                    (
                        {
                            "name": "pool/fortress-acceptance/media",
                            "type": "FILESYSTEM",
                            "comments": "fortress:ephemeral-dataset:acceptance-media",
                            "create_ancestors": True,
                        },
                    ),
                ),
                (
                    "call",
                    "pool.dataset.delete",
                    (
                        "pool/fortress-acceptance/media",
                        {"recursive": False, "force": False},
                    ),
                ),
                ("exit", None, ()),
            ],
        )

    def test_live_reality_reads_fortress_ephemeral_dataset_marker(self):
        raw_client = FakeTrueNasRawClient(
            responses={
                "core.ping": "pong",
                "pool.dataset.query": [
                    {
                        "id": "pool/fortress-acceptance/media",
                        "mountpoint": {"value": "/mnt/pool/fortress-acceptance/media"},
                        "comments": {
                            "value": "fortress:ephemeral-dataset:acceptance-media",
                        },
                    },
                ],
                "sharing.nfs.query": [],
                "filesystem.stat": {"uid": 0, "gid": 0},
            }
        )

        live_reality = load_live_truenas_reality(
            "10.0.10.10",
            "operator:super-secret-token",
            client_factory=FakeTrueNasClientFactory(raw_client),
        )

        self.assertIn(
            {
                "path": "/mnt/pool/fortress-acceptance/media",
                "owner": {"uid": 0, "gid": 0},
                "fortress_marker": "fortress:ephemeral-dataset:acceptance-media",
            },
            live_reality["datasets"],
        )

    def test_live_reality_reads_fortress_ephemeral_dataset_marker_from_user_properties(self):
        raw_client = FakeTrueNasRawClient(
            responses={
                "core.ping": "pong",
                "pool.dataset.query": [
                    {
                        "id": "pool/fortress-acceptance/media",
                        "mountpoint": "/mnt/pool/fortress-acceptance/media",
                        "user_properties": {
                            "comments": {
                                "value": "fortress:ephemeral-dataset:acceptance-media",
                            },
                        },
                    },
                ],
                "sharing.nfs.query": [],
                "filesystem.stat": {"uid": 0, "gid": 0},
            }
        )

        live_reality = load_live_truenas_reality(
            "10.0.10.10",
            "operator:super-secret-token",
            client_factory=FakeTrueNasClientFactory(raw_client),
        )

        self.assertIn(
            {
                "path": "/mnt/pool/fortress-acceptance/media",
                "owner": {"uid": 0, "gid": 0},
                "fortress_marker": "fortress:ephemeral-dataset:acceptance-media",
            },
            live_reality["datasets"],
        )

    def test_live_reality_reports_drifted_fortress_owned_nfs_share_in_read_only_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            inventory = load_inventory_tree(root)
            raw_client = FakeTrueNasRawClient(
                responses={
                    "core.ping": "pong",
                    "pool.dataset.query": [
                        {"id": "pool/media", "mountpoint": {"value": "/mnt/pool/media"}},
                    ],
                    "sharing.nfs.query": [
                        {
                            "id": 7,
                            "comment": "fortress:nfs-share:fortress-nfs-media-read-write",
                            "paths": ["/mnt/pool/media"],
                            "hosts": ["10.0.10.199"],
                        }
                    ],
                    "filesystem.stat": {"uid": 1000, "gid": 1000},
                }
            )
            live_reality = load_live_truenas_reality(
                "10.0.10.10",
                "operator:super-secret-token",
                client_factory=FakeTrueNasClientFactory(raw_client),
            )

            plan = build_nas_reconcile_plan(inventory, load_reality(live_reality))

            self.assertIn(
                {
                    "code": "drifted_fortress_owned_share",
                    "share": "fortress-nfs-media-read-write",
                    "path": "/mnt/pool/media",
                    "expected": {
                        "access": "read_write",
                        "clients": ["10.0.10.101"],
                        "fortress_marker": "fortress:nfs-share:fortress-nfs-media-read-write",
                    },
                    "actual": {
                        "access": "read_write",
                        "clients": ["10.0.10.199"],
                        "fortress_marker": "fortress:nfs-share:fortress-nfs-media-read-write",
                    },
                    "message": "Fortress-owned NFS Share fortress-nfs-media-read-write has drifted",
                },
                plan["share_findings"],
            )

    def test_live_reality_blocks_unmanaged_overlapping_nfs_share_in_read_only_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            inventory = load_inventory_tree(root)
            raw_client = FakeTrueNasRawClient(
                responses={
                    "core.ping": "pong",
                    "pool.dataset.query": [
                        {"id": "pool/media", "mountpoint": {"value": "/mnt/pool/media"}},
                    ],
                    "sharing.nfs.query": [
                        {
                            "id": 8,
                            "comment": "manual-media-share",
                            "paths": ["/mnt/pool/media"],
                            "hosts": ["10.0.10.101"],
                        }
                    ],
                    "filesystem.stat": {"uid": 1000, "gid": 1000},
                }
            )
            live_reality = load_live_truenas_reality(
                "10.0.10.10",
                "operator:super-secret-token",
                client_factory=FakeTrueNasClientFactory(raw_client),
            )

            plan = build_nas_reconcile_plan(inventory, load_reality(live_reality))

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

    def test_live_truenas_adapter_names_invalid_credential_without_printing_it(self):
        raw_client = FakeTrueNasRawClient(
            responses={},
            failures={"login_with_api_key": RuntimeError("bad super-secret-token")},
        )

        with self.assertRaises(TrueNasCapabilityError) as raised:
            with LiveTrueNasClient.connect(
                "10.0.10.10",
                "operator:super-secret-token",
                client_class=FakeRawClientClass(raw_client),
            ):
                pass

        self.assertEqual(raised.exception.capability, NAS_RECONCILE_CREDENTIAL_AUTHENTICATION)
        self.assertNotIn("super-secret-token", str(raised.exception))

    def test_live_truenas_adapter_names_connection_failure(self):
        raw_client = FakeTrueNasRawClient(responses={})
        raw_client.enter_failure = RuntimeError("network unavailable")

        with self.assertRaises(TrueNasCapabilityError) as raised:
            with LiveTrueNasClient.connect(
                "10.0.10.10",
                "operator:super-secret-token",
                client_class=FakeRawClientClass(raw_client),
            ):
                pass

        self.assertEqual(raised.exception.capability, MANAGEMENT_API_REACHABILITY)
        self.assertIn("network unavailable", str(raised.exception))

    def test_inline_connection_secrets_are_still_redacted_from_plan_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "inventory_valid", root, dirs_exist_ok=True)
            nas_endpoint = root / "inventory" / "nas" / "truenas.yaml"
            nas_endpoint.write_text(
                nas_endpoint.read_text().replace(
                    "share_address: 10.0.20.10\n",
                    "share_address: 10.0.20.10\n"
                    "api_token: super-secret-token\n",
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
            self.assertEqual(plan["connection"]["truenas"]["credentials"], "redacted")

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
                    "maproot_user": "root",
                    "maproot_group": "root",
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
                        "maproot_user": "root",
                        "maproot_group": "root",
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

    def _run_live_reconcile(self, root, endpoint, *args, extra_env=None):
        env = os.environ.copy()
        env["FORTRESS_ROOT"] = str(root)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [str(REPO_ROOT / "scripts" / "nas-reconcile-plan"), "--live", endpoint, *args],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )


class FakeTrueNasClientFactory:
    def __init__(self, raw_client):
        self._raw_client = raw_client

    def connect(self, management_address, credential, **kwargs):
        return LiveTrueNasClient.connect(
            management_address,
            credential,
            client_class=FakeRawClientClass(self._raw_client),
            tls_verify=kwargs.get("tls_verify", True),
        )


class FakeRawClientClass:
    def __init__(self, raw_client):
        self._raw_client = raw_client

    def __call__(self, uri, **kwargs):
        self._raw_client.operations.append(("connect", uri, kwargs))
        return self._raw_client


class FakeTrueNasRawClient:
    def __init__(self, responses, failures=None):
        self.responses = responses
        self.failures = failures or {}
        self.operations = []

    def __enter__(self):
        self.operations.append(("enter", None, ()))
        if hasattr(self, "enter_failure"):
            raise self.enter_failure
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.operations.append(("exit", None, ()))

    def login_with_api_key(self, username, key):
        self.operations.append(("login_with_api_key", username, key))
        failure = self.failures.get("login_with_api_key")
        if failure:
            raise failure

    def call(self, method, *args):
        self.operations.append(("call", method, args))
        failure = self.failures.get(method)
        if failure:
            raise failure
        return self.responses.get(method, [])


class FakeTrueNasJsonRpcClient(FakeTrueNasRawClient):
    login_with_api_key = None
