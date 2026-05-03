import argparse
import subprocess
import sys
from pathlib import Path


def check_sops_files(root):
    root = Path(root)
    failures = []
    for sops_file in sorted(root.rglob("*.sops.yaml")):
        if sops_file.name == ".sops.yaml":
            continue
        result = subprocess.run(
            ["sops", "--decrypt", str(sops_file)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            failures.append((sops_file, result.stderr.strip()))
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify every sibling SOPS File can decrypt.")
    parser.add_argument("root", nargs="?", default=".", help="repository or fixture root")
    args = parser.parse_args(argv)

    failures = check_sops_files(args.root)
    for path, stderr in failures:
        print(f"{path}: sops decrypt failed", file=sys.stderr)
        if stderr:
            print(stderr, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
