"""Reader/validator for daily telemetry without applying a debit aggregation."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from gdis_loader.domain.models import DailyTelemetryRow, DiagnosticIssue, IssueSeverity
from gdis_loader.matching.normalize import normalize_well_id
from gdis_loader.readers.common import (
    as_text,
    coordinate,
    display_value,
    openpyxl_read_warnings,
    parse_number,
)

DAILY_SHEET = "Добыча телеметрия"
DAILY_EMPTY_ROW_LIMIT = 200


def _find_daily_header(ws: Any) -> tuple[int, tuple[object, ...]] | None:
    for row_number, row in enumerate(
        ws.iter_rows(min_row=1, max_row=20, max_col=100, values_only=True),
        1,  # type: ignore[attr-defined]
    ):
        values = tuple(row)
        labels = {text.casefold() for value in values[:2] if (text := as_text(value)) is not None}
        if {"гск", "скв."} <= labels:
            return row_number, values
    return None


def read_daily_report(
    path: Path,
) -> tuple[tuple[DailyTelemetryRow, ...], tuple[DiagnosticIssue, ...]]:
    """Read daily values and retain errors as missing, never as debit."""

    issues: list[DiagnosticIssue] = []
    with openpyxl_read_warnings() as caught:
        workbook = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    issues.extend(
        [
            DiagnosticIssue(
                code="OPENPYXL_WARNING",
                severity=IssueSeverity.WARNING,
                message=str(warning.message),
                source="daily_report",
            )
            for warning in caught
        ]
    )
    try:
        if DAILY_SHEET not in workbook.sheetnames:
            issues.append(
                DiagnosticIssue(
                    code="DAILY_SHEET_MISSING",
                    severity=IssueSeverity.ERROR,
                    message=f"В суточном рапорте отсутствует лист {DAILY_SHEET!r}.",
                    source="daily_report",
                )
            )
            return (), tuple(issues)
        worksheet = workbook[DAILY_SHEET]
        header = _find_daily_header(worksheet)
        if header is None:
            issues.append(
                DiagnosticIssue(
                    code="DAILY_HEADERS_MISSING",
                    severity=IssueSeverity.ERROR,
                    message="На листе суточного рапорта не найдены заголовки ГСК и СКВ.",
                    source="daily_report",
                )
            )
            return (), tuple(issues)
        header_row, headers = header
        day_columns: list[tuple[int, int]] = []
        for column_index, value in enumerate(headers[2:], 2):
            if isinstance(value, bool):
                continue
            try:
                day = int(value) if isinstance(value, (int, float, str)) else 0
            except TypeError, ValueError:
                continue
            if 1 <= day <= 31:
                day_columns.append((day, column_index))
        if len(day_columns) < 28:
            issues.append(
                DiagnosticIssue(
                    code="DAILY_DAY_HEADERS_INCOMPLETE",
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"На листе суточного рапорта найдено только {len(day_columns)} "
                        "дневных колонок."
                    ),
                    source="daily_report",
                )
            )
        last_column = max((column for _, column in day_columns), default=1) + 1
        rows: list[DailyTelemetryRow] = []
        blank_streak = 0
        invalid_counts: Counter[str] = Counter()
        for row_number, row in enumerate(
            worksheet.iter_rows(
                min_row=header_row + 1,
                max_row=worksheet.max_row,
                max_col=last_column,
                values_only=True,
            ),
            header_row + 1,
        ):
            values = tuple(row)
            field_value = values[0] if values else None
            well_value = values[1] if len(values) > 1 else None
            if field_value is None and well_value is None:
                blank_streak += 1
                if blank_streak >= DAILY_EMPTY_ROW_LIMIT:
                    break
                continue
            blank_streak = 0
            raw_field = as_text(field_value)
            raw_well = display_value(well_value) if well_value is not None else None
            normalized = normalize_well_id(raw_well) if raw_well is not None else None
            daily_values: list[float | None] = []
            for day, column_index in day_columns:
                raw_value = values[column_index] if column_index < len(values) else None
                parsed = parse_number(raw_value)
                if raw_value is not None and parsed is None:
                    invalid_counts["daily"] += 1
                    if invalid_counts["daily"] <= 100:
                        issues.append(
                            DiagnosticIssue(
                                code="DAILY_INVALID_VALUE",
                                severity=IssueSeverity.WARNING,
                                message=f"Значение дня {day} {raw_value!r} прочитано как пропуск.",
                                source="daily_report",
                                coordinate=coordinate(row_number, column_index),
                                well_id=normalized.base_well_id if normalized else None,
                            )
                        )
                daily_values.append(parsed)
            rows.append(
                DailyTelemetryRow(
                    raw_field_name=raw_field,
                    raw_well_name=raw_well,
                    base_well_id=normalized.base_well_id if normalized else None,
                    source_row=row_number,
                    daily_values=tuple(daily_values),
                )
            )
        if invalid_counts["daily"] > 100:
            issues.append(
                DiagnosticIssue(
                    code="DAILY_INVALID_VALUE_SUMMARY",
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"В суточном рапорте пропущено {invalid_counts['daily']} нечисловых "
                        "значений; показаны первые 100."
                    ),
                    source="daily_report",
                )
            )
        return tuple(rows), tuple(issues)
    finally:
        workbook.close()
