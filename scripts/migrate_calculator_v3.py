"""Create a new structural v3 candidate from the immutable accepted v2."""

import argparse
import json
from pathlib import Path

from gdis_loader.excel.template_v3 import migrate_v3

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--diff", type=Path)
    args = parser.parse_args()
    encoded = json.dumps(migrate_v3(args.source, args.output), indent=2)
    if args.diff:
        args.diff.write_text(encoded + "\n")
    print(encoded)
