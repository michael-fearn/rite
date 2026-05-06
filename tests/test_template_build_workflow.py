import hashlib
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class TemplateBuildWorkflowTests(unittest.TestCase):
    def test_templates_build_rejects_undeclared_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._template_fixture(tmp)
            env = self._fake_tools(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "templates-build"), "bogus"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("Host 'bogus' is not declared", result.stderr)
            self.assertFalse(calls_log.exists())

    def test_checksum_mismatch_fails_before_customization_or_qm_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._template_fixture(tmp)
            template_yaml = root / "inventory" / "templates" / "debian-12-base.yaml"
            lines = template_yaml.read_text().splitlines()
            template_yaml.write_text(
                "\n".join(
                    "    value: " + ("b" * 128) if line.startswith("    value: ") else line
                    for line in lines
                )
                + "\n"
            )
            env = self._fake_tools(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "templates-build"), "wintermute"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("checksum mismatch", result.stderr)
            calls = calls_log.read_text()
            self.assertIn("curl", calls)
            self.assertNotIn("virt-customize", calls)
            self.assertNotIn("qm create", calls)

    def test_missing_virt_customize_fails_before_download_or_qm_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._template_fixture(tmp)
            env = self._fake_tools(root, calls_log, include_virt_customize=False)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "templates-build"), "wintermute"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("Required Template build tool 'virt-customize' is not available", result.stderr)
            calls = calls_log.read_text()
            self.assertIn("qm config 9001", calls)
            self.assertNotIn("curl", calls)
            self.assertNotIn("qm create", calls)

    def test_missing_template_vmid_builds_from_working_copy_and_marks_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._template_fixture(tmp)
            env = self._fake_tools(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "templates-build"), "wintermute"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            calls = calls_log.read_text()
            self.assertIn("curl", calls)
            self.assertIn("virt-customize --add ", calls)
            self.assertIn("--install qemu-guest-agent,sudo", calls)
            self.assertIn("--run-command systemctl enable qemu-guest-agent", calls)
            self.assertNotIn(str(root / "cache"), self._virt_customize_line(calls))
            self.assertIn("qm create 9001 --name debian-12-base --memory 2048 --cores 2", calls)
            self.assertIn("qm importdisk 9001 ", calls)
            self.assertIn(" fast", calls)
            self.assertIn("qm set 9001 --scsi1 local-lvm:cloudinit", calls)
            self.assertNotIn("--ide2 local-lvm:cloudinit", calls)
            self.assertIn("qm template 9001", calls)

    def test_cache_hit_verifies_cached_image_and_avoids_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_content = b"cached-cloud-image"
            root, calls_log = self._template_fixture(tmp, image_content=image_content)
            checksum = hashlib.sha512(image_content).hexdigest()
            cached = root / "cache" / "sha512" / f"{checksum}.qcow2"
            cached.parent.mkdir(parents=True)
            cached.write_bytes(image_content)
            env = self._fake_tools(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "templates-build"), "wintermute"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            calls = calls_log.read_text()
            self.assertNotIn("curl", calls)
            self.assertIn("virt-customize", calls)

    def test_existing_template_vmid_skips_without_download_or_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._template_fixture(tmp)
            env = self._fake_tools(root, calls_log)
            env["FORTRESS_FAKE_QM_CONFIG"] = "template"

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "templates-build"), "wintermute"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("already exists at VMID 9001; skipping", result.stdout)
            calls = calls_log.read_text()
            self.assertIn("qm config 9001", calls)
            self.assertNotIn("curl", calls)
            self.assertNotIn("virt-customize", calls)
            self.assertNotIn("qm create", calls)

    def test_existing_non_template_vmid_fails_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._template_fixture(tmp)
            env = self._fake_tools(root, calls_log)
            env["FORTRESS_FAKE_QM_CONFIG"] = "vm"

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "templates-build"), "wintermute"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("already exists but is not a Template", result.stderr)
            calls = calls_log.read_text()
            self.assertIn("qm config 9001", calls)
            self.assertNotIn("curl", calls)
            self.assertNotIn("virt-customize", calls)
            self.assertNotIn("qm template", calls)

    def test_controller_without_qm_dispatches_build_to_declared_host_over_ssh(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._template_fixture(tmp, include_host_sops=True)
            env = self._fake_tools(root, calls_log, include_qm=False)
            env["FORTRESS_TEMPLATE_CACHE"] = "/var/cache/fortress/templates"

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "templates-build"), "wintermute"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            calls = calls_log.read_text()
            self.assertIn("sops --decrypt --extract", calls)
            self.assertIn("ssh -i ", calls)
            self.assertIn("root@10.10.0.11 python3 -c", calls)
            self.assertIn("debian-12-base", (root / "remote-payload.json").read_text())
            payload = json.loads((root / "remote-payload.json").read_text())
            self.assertEqual(payload["templates"][0]["vmid"], 9001)

    def test_just_templates_build_calls_workflow_script(self):
        justfile = (REPO_ROOT / "justfile").read_text()

        self.assertIn("templates-build host:", justfile)
        self.assertIn("./scripts/templates-build {{host}}", justfile)

    def test_new_template_runbook_documents_builder_flow(self):
        content = (REPO_ROOT / "runbooks" / "new-template.md").read_text()

        self.assertIn("inventory/templates/<name>.yaml", content)
        self.assertIn("proxmox.templates", content)
        self.assertIn("just templates-build host=<name>", content)
        self.assertIn("SHA-512", content)
        self.assertIn("checksum-addressed cache", content)
        self.assertIn("already exists as a Template", content)
        self.assertIn("not a Template", content)

    def _template_fixture(self, tmp, image_content=b"cloud-image", include_host_sops=False):
        root = Path(tmp)
        inventory = root / "inventory"
        (inventory / "hosts").mkdir(parents=True)
        (inventory / "templates").mkdir()
        (inventory / "vms").mkdir()
        (inventory / "services").mkdir()
        (inventory / "group_vars").mkdir()

        checksum = hashlib.sha512(image_content).hexdigest()
        (root / "source.qcow2").write_bytes(image_content)
        (inventory / "hosts" / "wintermute.yaml").write_text(
            "proxmox:\n"
            "  pve_node_name: wintermute\n"
            "  endpoint: https://wintermute.fearn.cloud:8006\n"
            "  templates: [debian-12-base]\n"
            "network:\n"
            "  management_address: 10.10.0.11\n"
        )
        if include_host_sops:
            (inventory / "hosts" / "wintermute.sops.yaml").write_text(
                "ssh_keys:\n"
                "  bootstrap:\n"
                "    private_key: ENC[AES256_GCM,data:key,iv:iv,tag:tag,type:str]\n"
            )
        (inventory / "templates" / "debian-12-base.yaml").write_text(
            "name: debian-12-base\n"
            "vmid: 9001\n"
            "source:\n"
            f"  url: file://{root / 'source.qcow2'}\n"
            "  checksum:\n"
            "    algorithm: sha512\n"
            f"    value: {checksum}\n"
            "customize:\n"
            "  packages: [qemu-guest-agent, sudo]\n"
            "  run_commands:\n"
            "    - systemctl enable qemu-guest-agent\n"
            "hardware:\n"
            "  cores: 2\n"
            "  memory: 2048\n"
            "  bios: ovmf\n"
            "  machine: q35\n"
            "  scsi_controller: virtio-scsi-pci\n"
            "  network_model: virtio\n"
            "  agent_enabled: true\n"
            "  serial_console: true\n"
        )
        calls_log = root / "calls.log"
        return root, calls_log

    def _fake_tools(self, root, calls_log, include_qm=True, include_virt_customize=True):
        bin_dir = root / "bin"
        bin_dir.mkdir()
        tools = {
            "curl": (
                "#!/usr/bin/env bash\n"
                "printf 'curl %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  if [ \"$1\" = \"--output\" ]; then shift; output=\"$1\"; fi\n"
                "  url=\"$1\"\n"
                "  shift\n"
                "done\n"
                "cp \"${url#file://}\" \"$output\"\n"
            ),
            "ssh": (
                "#!/usr/bin/env bash\n"
                "printf 'ssh %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
                "cat > \"$FORTRESS_ROOT/remote-payload.json\"\n"
            ),
            "sops": (
                "#!/usr/bin/env bash\n"
                "printf 'sops %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
                "printf '%s\\n' 'OPENSSH PRIVATE KEY'\n"
            ),
        }
        if include_virt_customize:
            tools["virt-customize"] = (
                "#!/usr/bin/env bash\n"
                "printf 'virt-customize %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
            )
        if include_qm:
            tools["qm"] = (
                "#!/usr/bin/env bash\n"
                "printf 'qm %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
                "if [ \"$1\" = \"config\" ]; then\n"
                "  if [ \"$FORTRESS_FAKE_QM_CONFIG\" = \"template\" ]; then printf 'template: 1\\n'; exit 0; fi\n"
                "  if [ \"$FORTRESS_FAKE_QM_CONFIG\" = \"vm\" ]; then printf 'template: 0\\n'; exit 0; fi\n"
                "  exit 2\n"
                "fi\n"
            )
        for name, body in tools.items():
            tool = bin_dir / name
            tool.write_text(body)
            tool.chmod(tool.stat().st_mode | stat.S_IXUSR)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        env["FORTRESS_ROOT"] = str(root)
        env["CALLS_LOG"] = str(calls_log)
        env["FORTRESS_TEMPLATE_CACHE"] = str(root / "cache")
        return env

    def _virt_customize_line(self, calls):
        return next(line for line in calls.splitlines() if line.startswith("virt-customize "))
