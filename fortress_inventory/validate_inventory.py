import argparse
import sys

from .validate import validate_inventory_tree


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate fortress Inventory cross-file rules.")
    parser.add_argument("root", nargs="?", default=".", help="repository or fixture root")
    parser.add_argument(
        "--allow-ephemeral-datasets",
        action="store_true",
        help="allow lifecycle: ephemeral for Acceptance Test inventory",
    )
    args = parser.parse_args(argv)

    errors = validate_inventory_tree(args.root, allow_ephemeral_datasets=args.allow_ephemeral_datasets)
    for error in errors:
        print(f"{error.path}: {error.code}: {error.message}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
