"""Create controlled synthetic rows for native Excel's mandatory golden gate."""

import argparse
from dataclasses import replace
from pathlib import Path

from gdis_loader.domain.models import TargetRow
from gdis_loader.excel.writer import write_target_rows


def prepare(template: Path, output: Path) -> None:
    known = TargetRow(
        well="all_known",
        gtm="Нет",
        insufficient_gdi="Да",
        productivity_decline="Нет",
        chlorine_growth="Да",
        gdm_problems="Нет",
        lnd="Да",
        duration_without_gdi=365,
        specific_gdi_count=0.5,
    )
    rows = (
        known,
        replace(known, well="one_unknown", gtm=None),
        replace(known, well="multiple_unknown", gtm=None, lnd=None, chlorine_growth=None),
        TargetRow(well="one_known", gtm="Да"),
        TargetRow(well="all_unknown"),
        TargetRow(well="known_no", gtm="Нет"),
        TargetRow(well="known_yes", gtm="Да"),
    )
    write_target_rows(template, output, rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.template, args.output)
