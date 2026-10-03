"""Read cached native Excel results; requires prior full recalc and save."""

import argparse
import json
from pathlib import Path

from openpyxl import load_workbook


def scan(path: Path) -> list[str]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        return [
            f"{sheet.title}!{cell.coordinate}: {cell.value}"
            for sheet in workbook
            for row in sheet
            for cell in row
            if cell.data_type == "e"
        ]
    finally:
        workbook.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    args = parser.parse_args()
    errors = scan(args.workbook)
    print(json.dumps({"errors": errors, "count": len(errors)}, ensure_ascii=False, indent=2))
    raise SystemExit(bool(errors))
