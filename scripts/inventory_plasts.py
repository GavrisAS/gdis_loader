"""Count plast shorthand changes across runtime sources without exporting rows."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from gdis_loader.matching.normalize import normalize_field_name, normalize_plast, normalize_well_id
from gdis_loader.readers.fund import read_fund
from gdis_loader.readers.well_history import FIELD_SHEETS

_SHORTHAND = re.compile(r"^ПК\s*-?\s*\d{2,}(?:-\d+)*-\d\+\d\??$", re.IGNORECASE)


def inventory(manifest: dict[str, Any], source_dir: Path) -> list[dict[str, Any]]:
    """Scan every worksheet; aggregate matching cells and distinct raw forms."""
    result = []
    fund_entry = next(entry for entry in manifest["sources"] if entry["role"] == "fund")
    selected_field = normalize_field_name(manifest["selected_field"])
    targets = tuple(
        well
        for well in read_fund(source_dir / fund_entry["name"]).wells
        if well.is_rating_eligible and well.normalized_field == selected_field
    )
    all_forms: set[str] = set()
    affected_roots: set[str] = set()
    for entry in manifest["sources"]:
        if entry["role"] == "generated_calculator":
            continue
        forms: Counter[str] = Counter()
        workbook = load_workbook(source_dir / entry["name"], read_only=True, data_only=True)
        try:
            for sheet in workbook:
                well_column = None
                field_column = None
                sheet_field = normalize_field_name(
                    FIELD_SHEETS.get(sheet.title.removeprefix("АР_таблица_"), "")
                )
                for row in sheet.iter_rows(values_only=True):
                    for index, value in enumerate(row):
                        if value in ("Скважина", "Номер скважины"):
                            well_column = index
                        if value == "Месторождение":
                            field_column = index
                    for value in row:
                        if isinstance(value, str) and _SHORTHAND.fullmatch(value.strip()):
                            forms[value.strip()] += 1
                            all_forms.add(value.strip())
                            field = (
                                normalize_field_name(row[field_column])
                                if field_column is not None
                                else sheet_field
                            )
                            if well_column is not None and field == selected_field:
                                root = normalize_well_id(row[well_column]).base_well_id
                                if root is not None:
                                    affected_roots.add(root)
        finally:
            workbook.close()
        result.append(
            {
                "role": entry["role"],
                "cells": sum(forms.values()),
                "distinct_raw_forms": len(forms),
                "canonical_forms": sorted(
                    {value for raw in forms if (value := normalize_plast(raw)) is not None}
                ),
            }
        )
    result.append(
        {
            "role": "aggregate",
            "distinct_raw_forms": len(all_forms),
            "distinct_changed_raw_forms": len(all_forms),
            "affected_target_wells": sum(well.base_well_id in affected_roots for well in targets),
        }
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-report", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.runtime_report.read_text(encoding="utf-8"))["source_manifest"]
    args.output.write_text(
        json.dumps(inventory(manifest, args.source_dir), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
