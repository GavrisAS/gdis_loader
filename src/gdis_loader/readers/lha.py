"""Streaming reader and index for the large LHA workbook."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from gdis_loader.domain.models import (
    DiagnosticIssue,
    IssueSeverity,
    LhaRecord,
    LhaSelection,
    LhaValues,
)
from gdis_loader.matching.normalize import normalize_field_name, normalize_plast, normalize_well_id
from gdis_loader.readers.common import (
    as_text,
    coordinate,
    display_value,
    index_headers,
    is_missing_measurement,
    openpyxl_read_warnings,
    parse_datetime,
    parse_number,
    row_is_empty,
    row_value,
)

LHA_SHEET = "БД Сибнефтегаз"
LHA_EMPTY_IDENTITY_LIMIT = 2_000
LHA_HEADER_ALIASES: dict[str, set[str]] = {
    "field": {"Месторождение"},
    "well": {"Номер скважины"},
    "plast": {"Пласт"},
    "measured_at": {"Дата и время исследования"},
    "cl": {
        "Данные ЛХА, CL-, мг/дм3",
        "Данные ЛХА, CL-, мг/дм³",
    },
    "vgf": {"ВГФ, г/м3", "ВГФ, г/м³"},
}


def _find_header(ws: Any) -> tuple[int, tuple[object, ...]] | None:
    for row_number, row in enumerate(
        ws.iter_rows(min_row=1, max_row=40, max_col=100, values_only=True),
        1,  # type: ignore[attr-defined]
    ):
        values = tuple(row)
        if len(index_headers(values, LHA_HEADER_ALIASES)) == len(LHA_HEADER_ALIASES):
            return row_number, values
    return None


class LhaIndex:
    """One-pass index grouped by physical well, field, and exact normalized plast."""

    def __init__(self, records: Iterable[LhaRecord]) -> None:
        grouped: defaultdict[tuple[str, str | None, str], list[LhaRecord]] = defaultdict(list)
        for record in records:
            if (
                record.base_well_id is None
                or record.normalized_plast is None
                or record.measured_at is None
            ):
                continue
            if record.cl_value is None and record.vgf_value is None:
                continue
            grouped[(record.base_well_id, record.normalized_field, record.normalized_plast)].append(
                record
            )
        self._by_key = {key: tuple(items) for key, items in grouped.items()}

    def select(
        self,
        *,
        base_well_id: str,
        normalized_field: str,
        normalized_plast: str,
        cutoff: datetime | None = None,
    ) -> LhaSelection:
        """Select the last two distinct timestamps independently for Cl and VGF.

        Rows with the same timestamp are first collapsed by metric.  Equal
        numeric values are one point; different values are an unresolved
        source conflict and never get ordered by ``source_row``.
        """

        exact = self._by_key.get((base_well_id, normalized_field, normalized_plast), ())
        if not exact:
            # A few legacy LHA rows have no field value.  They can be used only
            # when no field-qualified row exists; rows from another field never
            # cross the boundary.
            exact = self._by_key.get((base_well_id, None, normalized_plast), ())
        eligible = [
            record
            for record in exact
            if cutoff is None or (record.measured_at is not None and record.measured_at <= cutoff)
        ]

        cl_current, cl_previous, cl_issues = _select_metric(
            eligible,
            metric="cl_value",
            metric_label="Cl",
            base_well_id=base_well_id,
            normalized_field=normalized_field,
            normalized_plast=normalized_plast,
        )
        vgf_current, vgf_previous, vgf_issues = _select_metric(
            eligible,
            metric="vgf_value",
            metric_label="ВГФ",
            base_well_id=base_well_id,
            normalized_field=normalized_field,
            normalized_plast=normalized_plast,
        )
        return LhaSelection(
            values=LhaValues(cl_current, cl_previous, vgf_current, vgf_previous),
            issues=(*cl_issues, *vgf_issues),
        )


@dataclass(frozen=True, slots=True)
class _MetricPoint:
    measured_at: datetime
    value: float | None
    values: tuple[float, ...]
    distinct_values: int


def _select_metric(
    records: Iterable[LhaRecord],
    *,
    metric: str,
    metric_label: str,
    base_well_id: str,
    normalized_field: str,
    normalized_plast: str,
) -> tuple[float | None, float | None, tuple[DiagnosticIssue, ...]]:
    values_by_timestamp: defaultdict[datetime, set[float]] = defaultdict(set)
    for record in records:
        measured_at = record.measured_at
        value = getattr(record, metric)
        if measured_at is not None and value is not None:
            values_by_timestamp[measured_at].add(value)

    points = tuple(
        _MetricPoint(
            measured_at=measured_at,
            value=next(iter(values)) if len(values) == 1 else None,
            values=tuple(sorted(values)),
            distinct_values=len(values),
        )
        for measured_at, values in sorted(
            values_by_timestamp.items(), key=lambda item: item[0], reverse=True
        )
    )
    if not points:
        return None, None, ()
    if points[0].distinct_values > 1:
        return (
            None,
            None,
            (
                _duplicate_timestamp_issue(
                    points[0],
                    metric_label=metric_label,
                    role="current",
                    base_well_id=base_well_id,
                    normalized_field=normalized_field,
                    normalized_plast=normalized_plast,
                ),
            ),
        )
    current = points[0].value
    previous = None
    if len(points) <= 1:
        return current, previous, ()
    if points[1].distinct_values > 1:
        return (
            current,
            None,
            (
                _duplicate_timestamp_issue(
                    points[1],
                    metric_label=metric_label,
                    role="previous",
                    base_well_id=base_well_id,
                    normalized_field=normalized_field,
                    normalized_plast=normalized_plast,
                ),
            ),
        )
    previous = points[1].value
    return current, previous, ()


def _duplicate_timestamp_issue(
    point: _MetricPoint,
    *,
    metric_label: str,
    role: str,
    base_well_id: str,
    normalized_field: str,
    normalized_plast: str,
) -> DiagnosticIssue:
    values = ", ".join(f"{value:g}" for value in point.values[:5])
    if len(point.values) > 5:
        values += ", …"
    return DiagnosticIssue(
        code="LHA_DUPLICATE_TIMESTAMP_CONFLICT",
        severity=IssueSeverity.WARNING,
        message=(
            f"ЛХА: скважина {base_well_id!r}, месторождение {normalized_field!r}, "
            f"пласт {normalized_plast!r}, метрика {metric_label}, роль {role}: "
            f"timestamp {point.measured_at.isoformat(sep=' ')} содержит "
            f"{point.distinct_values} различных значения ({values}); значение не выбирается."
        ),
        source="lha",
        well_id=base_well_id,
    )


def read_lha(path: Path) -> tuple[tuple[LhaRecord, ...], tuple[DiagnosticIssue, ...]]:
    """Read the relevant columns and stop after a long empty identity tail."""

    issues: list[DiagnosticIssue] = []
    with openpyxl_read_warnings() as caught:
        workbook = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    issues.extend(
        [
            DiagnosticIssue(
                code="OPENPYXL_WARNING",
                severity=IssueSeverity.WARNING,
                message=str(warning.message),
                source="lha",
            )
            for warning in caught
        ]
    )
    try:
        if LHA_SHEET not in workbook.sheetnames:
            issues.append(
                DiagnosticIssue(
                    code="LHA_SHEET_MISSING",
                    severity=IssueSeverity.ERROR,
                    message=f"В книге ЛХА отсутствует лист {LHA_SHEET!r}.",
                    source="lha",
                )
            )
            return (), tuple(issues)
        worksheet = workbook[LHA_SHEET]
        header = _find_header(worksheet)
        if header is None:
            issues.append(
                DiagnosticIssue(
                    code="LHA_HEADERS_MISSING",
                    severity=IssueSeverity.ERROR,
                    message="На листе ЛХА не найдены все обязательные заголовки.",
                    source="lha",
                )
            )
            return (), tuple(issues)
        header_row, headers = header
        columns = index_headers(headers, LHA_HEADER_ALIASES)
        last_column = max(columns.values()) + 1
        records: list[LhaRecord] = []
        blank_identity_streak = 0
        invalid_value_counts: defaultdict[str, int] = defaultdict(int)
        invalid_value_samples: defaultdict[str, list[str]] = defaultdict(list)
        missing_value_counts: defaultdict[str, int] = defaultdict(int)
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
            identity_values = tuple(
                row_value(values, columns, name)
                for name in ("field", "well", "plast", "measured_at")
            )
            if row_is_empty(identity_values):
                blank_identity_streak += 1
                if blank_identity_streak >= LHA_EMPTY_IDENTITY_LIMIT:
                    break
                continue
            blank_identity_streak = 0

            raw_field_value = row_value(values, columns, "field")
            raw_well_value = row_value(values, columns, "well")
            raw_plast_value = row_value(values, columns, "plast")
            raw_date_value = row_value(values, columns, "measured_at")
            raw_field = as_text(raw_field_value)
            raw_well = display_value(raw_well_value) if raw_well_value is not None else None
            raw_plast = as_text(raw_plast_value)
            normalized_well = normalize_well_id(raw_well) if raw_well is not None else None
            measured_at = parse_datetime(raw_date_value)
            if measured_at is None:
                issues.append(
                    DiagnosticIssue(
                        code="LHA_INVALID_DATE",
                        severity=IssueSeverity.WARNING,
                        message=(
                            f"Некорректная дата/время ЛХА: {raw_date_value!r}; "
                            "точка не используется."
                        ),
                        source="lha",
                        coordinate=coordinate(row_number, columns["measured_at"]),
                        well_id=normalized_well.base_well_id if normalized_well else None,
                    )
                )
            if normalized_well is None or normalized_well.base_well_id is None:
                issues.append(
                    DiagnosticIssue(
                        code="LHA_INVALID_WELL",
                        severity=IssueSeverity.WARNING,
                        message="В строке ЛХА отсутствует или не распознан номер скважины.",
                        source="lha",
                        coordinate=coordinate(row_number, columns["well"]),
                    )
                )
            normalized_plast = normalize_plast(raw_plast)
            if normalized_plast is None:
                issues.append(
                    DiagnosticIssue(
                        code="LHA_INVALID_PLAST",
                        severity=IssueSeverity.WARNING,
                        message=(
                            "В строке ЛХА отсутствует обозначение пласта; точная связь невозможна."
                        ),
                        source="lha",
                        coordinate=coordinate(row_number, columns["plast"]),
                        well_id=normalized_well.base_well_id if normalized_well else None,
                    )
                )
            cl_raw = row_value(values, columns, "cl")
            vgf_raw = row_value(values, columns, "vgf")
            cl_value = parse_number(cl_raw)
            vgf_value = parse_number(vgf_raw)
            for semantic_name, raw_value, parsed_value in (
                ("cl", cl_raw, cl_value),
                ("vgf", vgf_raw, vgf_value),
            ):
                if raw_value is not None and parsed_value is None:
                    if is_missing_measurement(raw_value):
                        missing_value_counts[semantic_name] += 1
                    else:
                        invalid_value_counts[semantic_name] += 1
                        if len(invalid_value_samples[semantic_name]) < 3:
                            invalid_value_samples[semantic_name].append(repr(raw_value))
            records.append(
                LhaRecord(
                    raw_field_name=raw_field,
                    normalized_field=normalize_field_name(raw_field)
                    if raw_field is not None
                    else None,
                    raw_well_name=raw_well,
                    base_well_id=normalized_well.base_well_id if normalized_well else None,
                    raw_plast=raw_plast,
                    normalized_plast=normalized_plast,
                    measured_at=measured_at,
                    cl_value=cl_value,
                    vgf_value=vgf_value,
                    source_row=row_number,
                )
            )
        for semantic_name, count in missing_value_counts.items():
            issues.append(
                DiagnosticIssue(
                    code="LHA_MISSING_VALUE_SUMMARY",
                    severity=IssueSeverity.INFO,
                    message=(
                        f"В ЛХА для {semantic_name.upper()} пропущено {count} пустых, "
                        "placeholder- или Excel error-значений; они считаются отсутствующими."
                    ),
                    source="lha",
                )
            )
        for semantic_name, count in invalid_value_counts.items():
            samples = ", ".join(invalid_value_samples[semantic_name])
            issues.append(
                DiagnosticIssue(
                    code="LHA_INVALID_VALUE",
                    severity=IssueSeverity.INFO,
                    message=(
                        f"В ЛХА для {semantic_name.upper()} найдено {count} содержательных "
                        f"нечисловых значений; они прочитаны как пропуски. Примеры: {samples}."
                    ),
                    source="lha",
                )
            )
        return tuple(records), tuple(issues)
    finally:
        workbook.close()
