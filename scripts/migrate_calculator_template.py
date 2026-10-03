"""One-shot offline migration; the loader never invokes this script."""

import argparse
from pathlib import Path

from gdis_loader.excel.template_migration import migrate, sha256

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print("\n".join(migrate(args.source, args.output)))
    print("SHA-256:", sha256(args.output))
