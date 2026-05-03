import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class SopsHealthCheckTests(unittest.TestCase):
    def test_health_check_decrypts_every_sibling_sops_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sops_file = root / "inventory" / "hosts" / "wintermute.sops.yaml"
            sops_file.parent.mkdir(parents=True)
            sops_file.write_text("encrypted: value\n")

            bin_dir = root / "bin"
            bin_dir.mkdir()
            log_path = root / "sops.log"
            fake_sops = bin_dir / "sops"
            fake_sops.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$*\" >> \"$SOPS_HEALTH_LOG\"\n"
                "exit 0\n"
            )
            fake_sops.chmod(fake_sops.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
            env["SOPS_HEALTH_LOG"] = str(log_path)

            result = subprocess.run(
                ["python3", "-m", "fortress_inventory.check_sops_decryptable", str(root)],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--decrypt", log_path.read_text())
            self.assertIn(str(sops_file), log_path.read_text())

    def test_health_check_reports_failed_decryption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sops_file = root / "inventory" / "hosts" / "wintermute.sops.yaml"
            sops_file.parent.mkdir(parents=True)
            sops_file.write_text("encrypted: value\n")

            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_sops = bin_dir / "sops"
            fake_sops.write_text("#!/usr/bin/env bash\nexit 1\n")
            fake_sops.chmod(fake_sops.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env['PATH']}"

            result = subprocess.run(
                ["python3", "-m", "fortress_inventory.check_sops_decryptable", str(root)],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("wintermute.sops.yaml", result.stderr)
