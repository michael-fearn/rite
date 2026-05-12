import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class HostConfigureWorkflowTests(unittest.TestCase):
    def test_host_configure_requires_tags_and_prints_all_tags_command(self):
        result = subprocess.run(
            [str(REPO_ROOT / "scripts" / "host-configure"), "wintermute"],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("tags are required", result.stderr)
        self.assertIn("just host-configure host=wintermute tags=proxmox_repos,system_hygiene,proxmox_network,proxmox_users,gpu_passthrough", result.stderr)

    def test_host_configure_rejects_unknown_tags(self):
        result = subprocess.run(
            [str(REPO_ROOT / "scripts" / "host-configure"), "wintermute", "bogus"],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown Host Configure tag: bogus", result.stderr)

    def test_token_noop_when_sops_already_has_tofu_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._configure_fixture(tmp)
            (root / "inventory" / "hosts" / "wintermute.sops.yaml").write_text(
                "ssh_keys:\n"
                "  bootstrap:\n"
                "    private_key: old\n"
                "pve_tokens:\n"
                "  tofu:\n"
                "    user: tofu@pve\n"
                "    token_id: tofu\n"
                "    value: existing-secret\n"
            )
            env = self._fake_tools(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "host-configure"), "wintermute", "proxmox_users"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            calls = calls_log.read_text()
            self.assertNotIn("pveum", calls)
            self.assertNotIn("host-token-create.yml", calls)
            self.assertIn("ansible-playbook", calls)

    def test_token_merge_preserves_bootstrap_ssh_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._configure_fixture(tmp)
            (root / "inventory" / "hosts" / "wintermute.sops.yaml").write_text(
                "ssh_keys:\n"
                "  bootstrap:\n"
                "    private_key: old\n"
            )
            env = self._fake_tools(root, calls_log)

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "host-configure"), "wintermute", "proxmox_users"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            content = (root / "inventory" / "hosts" / "wintermute.sops.yaml").read_text()
            self.assertIn("ssh_keys:", content)
            self.assertIn("  bootstrap:", content)
            self.assertIn("private_key: old", content)
            self.assertIn("pve_tokens:", content)
            self.assertIn("  tofu:", content)
            self.assertIn("value: generated-secret", content)
            calls = calls_log.read_text()
            self.assertIn("host-token-create.yml", calls)
            self.assertNotIn("pveum", calls)

    def test_token_creation_rolls_back_when_sops_write_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, calls_log = self._configure_fixture(tmp)
            (root / "inventory" / "hosts" / "wintermute.sops.yaml").write_text(
                "ssh_keys:\n"
                "  bootstrap:\n"
                "    private_key: old\n"
            )
            env = self._fake_tools(root, calls_log)
            env["FORTRESS_FAKE_SOPS_FAIL"] = "1"

            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "host-configure"), "wintermute", "proxmox_users"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            calls = calls_log.read_text()
            self.assertIn("host-token-create.yml", calls)
            self.assertIn("host-token-rollback.yml", calls)
            self.assertNotIn("host-configure.yml", calls)

    def test_just_host_configure_calls_workflow_script(self):
        justfile = (REPO_ROOT / "justfile").read_text()

        self.assertIn('host-configure host tags=""', justfile)
        self.assertIn('./scripts/host-configure {{host}} "{{tags}}"', justfile)

    def test_host_configure_playbook_has_independently_tagged_roles_and_no_reboot(self):
        playbook = (REPO_ROOT / "ansible" / "playbooks" / "host-configure.yml").read_text()

        for tag in (
            "proxmox_repos",
            "system_hygiene",
            "proxmox_network",
            "proxmox_users",
            "gpu_passthrough",
        ):
            self.assertIn(f"role: {tag}", playbook)
            self.assertIn(f"tags: [{tag}]", playbook)
            self.assertTrue((REPO_ROOT / "ansible" / "roles" / tag / "tasks" / "main.yml").is_file())

        self.assertIn("host_configure_reboot_required", playbook)
        self.assertNotIn("ansible.builtin.reboot", playbook)

    def test_system_hygiene_installs_template_builder_host_tools(self):
        tasks = (REPO_ROOT / "ansible" / "roles" / "system_hygiene" / "tasks" / "main.yml").read_text()

        self.assertIn("libguestfs-tools", tasks)
        self.assertIn("/var/lib/vz/snippets", tasks)
        self.assertIn("pvesm set local --content", tasks)
        self.assertIn(",snippets,", tasks)

    def test_proxmox_users_applies_acl_roles_to_token_principals(self):
        tasks = (REPO_ROOT / "ansible" / "roles" / "proxmox_users" / "tasks" / "main.yml").read_text()

        self.assertIn("subelements('tokens', skip_missing=True)", tasks)
        self.assertIn("pveum acl modify / --tokens {{ item.0.name }}!{{ item.1.id }} --roles {{ item.1.roles | join(',') }}", tasks)
        self.assertIn("changed_when: false", tasks)

    def test_new_host_runbook_documents_configure_step(self):
        content = (REPO_ROOT / "runbooks" / "new-host.md").read_text()

        self.assertIn("just host-configure host=<name> tags=", content)
        self.assertIn("Host Configure does not create or register storage", content)
        self.assertIn("managed: true", content)
        self.assertIn("never reboots the Host automatically", content)

    def _configure_fixture(self, tmp):
        root = Path(tmp)
        host_dir = root / "inventory" / "hosts"
        host_dir.mkdir(parents=True)
        (host_dir / "wintermute.yaml").write_text(
            "proxmox:\n"
            "  pve_node_name: wintermute\n"
            "  users:\n"
            "    - name: tofu@pve\n"
            "      roles: [PVEVMAdmin]\n"
            "      tokens:\n"
            "        - id: tofu\n"
            "          roles: [PVEVMAdmin]\n"
            "network:\n"
            "  management_address: 10.0.0.10\n"
        )
        calls_log = root / "calls.log"
        return root, calls_log

    def _fake_tools(self, root, calls_log):
        bin_dir = root / "bin"
        bin_dir.mkdir()
        for name, body in {
            "ansible-playbook": (
                "#!/usr/bin/env bash\n"
                "printf 'ansible-playbook %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
                "if [[ \"$*\" == *host-token-create.yml* ]]; then\n"
                "  while [ \"$#\" -gt 0 ]; do\n"
                "    if [ \"$1\" = \"--extra-vars\" ]; then shift; extra_vars=\"$1\"; fi\n"
                "    shift\n"
                "  done\n"
                "  python3 - \"$extra_vars\" <<'PY'\n"
                "import json, sys\n"
                "Path = __import__('pathlib').Path\n"
                "Path(json.loads(sys.argv[1])['token_output_file']).write_text('generated-secret')\n"
                "PY\n"
                "fi\n"
            ),
            "sops": (
                "#!/usr/bin/env bash\n"
                "printf 'sops %s\\n' \"$*\" >> \"$CALLS_LOG\"\n"
                "if [ \"$1\" = \"--decrypt\" ]; then cat \"$2\"; exit 0; fi\n"
                "if [ -n \"$FORTRESS_FAKE_SOPS_FAIL\" ]; then exit 1; fi\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  if [ \"$1\" = \"--output\" ]; then shift; output=\"$1\"; fi\n"
                "  input=\"$1\"\n"
                "  shift\n"
                "done\n"
                "cp \"$input\" \"$output\"\n"
            ),
        }.items():
            tool = bin_dir / name
            tool.write_text(body)
            tool.chmod(tool.stat().st_mode | stat.S_IXUSR)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        env["FORTRESS_ROOT"] = str(root)
        env["CALLS_LOG"] = str(calls_log)
        return env
