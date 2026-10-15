"""Evidence from direct telemetry references; never evaluate Excel formulas."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from openpyxl.utils import get_column_letter

from gdis_loader.domain.models import SourceLocation
from gdis_loader.matching.normalize import normalize_field_name, normalize_well_id
from gdis_loader.readers.well_history import FIELD_SHEETS

_REFERENCE = re.compile(r"^='([^']+)'!\$?([A-Z]+)\$?(\d+)$")
_MONTHS = [
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]
# Exact source heading, not a substring inference from a collector number/color.
_TITLES = {
    "береговой (опорный) газовый промысел": "Береговое",
}


@dataclass(frozen=True, slots=True)
class DayContext:
    report_date: date
    field: str | None
    wells: dict[int, str]
    scopes: dict[int, tuple[str, str]]
    well_column: str
    title_cell: str
    date_cell: str


def day_contexts(workbook: Any) -> dict[str, DayContext]:
    """Inspect dated daily tabs with explicit heading and semantic well column."""
    result: dict[str, DayContext] = {}
    for name in workbook.sheetnames:
        if not re.fullmatch(r"\d{2}", name):
            continue
        rows = list(workbook[name].iter_rows(max_col=40, values_only=True))
        if len(rows) < 7:
            continue
        raw_date = str(rows[3][0] or "").strip()
        match = re.fullmatch(r"(\d{1,2})\s+([а-я]+)\s+(\d{4})\s*г\.", raw_date)
        if match is None or match[2] not in _MONTHS:
            continue
        report_date = date(int(match[3]), _MONTHS.index(match[2]) + 1, int(match[1]))
        if report_date.day != int(name):
            continue
        title = " ".join(str(rows[0][0] or "").casefold().split())
        field = _TITLES.get(title)
        if field is None and normalize_field_name(title) in {
            "береговое",
            "пырейное",
            "хадырьяхинское",
        }:
            field = title
        columns = [
            i
            for i, v in enumerate(rows[6])
            if str(v or "").casefold() == "скв." and rows[5][i] == "№"
        ]
        # The report has two well columns: main table and telemetry. Use main
        # identity only when both explicit identities agree on the referenced row.
        if not columns:
            continue
        wells: dict[int, str] = {}
        scopes: dict[int, tuple[str, str]] = {}
        active_field, active_cell = field, "A1"
        for number, row in enumerate(rows[7:], 8):
            if any(str(v or "").startswith("Итого") for v in row[:1]):
                break
            if (
                row[columns[0]] is None
                and isinstance(row[0], str)
                and row[0].strip()
                and not row[0].startswith("=")
            ):
                marker = normalize_field_name(FIELD_SHEETS.get(row[0].strip().upper(), row[0]))
                active_field = (
                    marker if marker in {"береговое", "пырейное", "хадырьяхинское"} else None
                )
                active_cell = f"A{number}"
            main_column = get_column_letter(columns[0] + 1)
            identities = {
                n.target_well_id
                for i in columns
                if row[i] is not None
                and row[i] != f"={main_column}{number}"
                and (n := normalize_well_id(row[i])).target_well_id
            }
            if len(identities) == 1:
                wells[number] = identities.pop()
                if active_field is not None:
                    scopes[number] = (active_field, active_cell)
        result[name] = DayContext(
            report_date, field, wells, scopes, get_column_letter(columns[0] + 1), "A1", "A4"
        )
    return result


def reference_evidence(
    formula: object,
    day: int,
    identity: str | None,
    contexts: dict[str, DayContext],
    source: str,
) -> tuple[str, tuple[SourceLocation, ...]] | None:
    """Accept only a direct dated same-well link with explicit field context."""
    match = _REFERENCE.fullmatch(str(formula))
    if match is None:
        return None
    sheet, _column, row = match.groups()
    context = contexts.get(sheet)
    if (
        context is None
        or int(row) not in context.scopes
        or context.report_date.day != day
        or context.wells.get(int(row)) != identity
    ):
        return None
    field, field_cell = context.scopes[int(row)]
    return field, tuple(
        SourceLocation(source, sheet, cell)
        for cell in (
            field_cell,
            context.date_cell,
            f"{context.well_column}{row}",
            f"{_column}{row}",
        )
    )
