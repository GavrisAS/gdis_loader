"""Classification helpers for raw GDI research type labels."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import replace

from gdis_loader.domain.models import (
    DiagnosticIssue,
    GdiKind,
    GdiRecord,
    IssueSeverity,
    SourceLocation,
)

_ID_TOKEN = re.compile(r"(?<![0-9А-ЯA-Z])ИД(?![0-9А-ЯA-Z])")
_PRESSURE_ONLY = re.compile(r"(?<![0-9А-ЯA-Z])(?:P|Р)\s*(?:СТ(?:АТИК[А-Я]*)?|ПЛ)(?![0-9А-ЯA-Z])")


def classify_gdi_kind(raw_value: object) -> GdiKind:
    """Classify a raw label while retaining that label on its source record.

    Only an approved marker at the start of the label is authoritative.
    Everything after a recognized marker is explanatory text.
    """

    if raw_value is None:
        return GdiKind.UNKNOWN
    text = unicodedata.normalize("NFKC", str(raw_value)).upper().strip().replace("Ё", "Е")
    text = re.sub(r"\s*([+_])\s*", r"\1", text)
    if text.startswith(("ИД+КВД", "КВД+ИД")):
        return GdiKind.ID_KVD
    if text.startswith("ИД"):
        return GdiKind.ID
    if text.startswith("КВД"):
        return GdiKind.KVD
    if text.startswith("КСД"):
        return GdiKind.KSD
    if "ОСВОЕНИЕ" in text or _PRESSURE_ONLY.search(text) is not None or text.startswith("СТАТИК"):
        return GdiKind.EXCLUDED
    return GdiKind.UNKNOWN


def _normalized_label(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip().casefold()


def gdi_fingerprint(record: GdiRecord) -> tuple[object, ...]:
    """Return business attributes only; source addresses never split duplicates."""

    return (
        record.normalized_field,
        record.target_well_id,
        record.normalized_plast,
        record.study_date,
        record.gdi_kind.value,
        _normalized_label(record.research_type),
        record.depth_raw_value,
        record.depth_value,
        record.productivity_a_raw,
        record.productivity_a_value,
        record.productivity_b_raw,
        record.productivity_b_value,
        _normalized_label(record.rfp_result),
        _normalized_label(record.lnd_reliability),
        record.gtm_date,
    )


def collapse_exact_gdi_duplicates(
    records: tuple[GdiRecord, ...],
) -> tuple[tuple[GdiRecord, ...], tuple[DiagnosticIssue, ...]]:
    """Collapse exact business duplicates, preserving every source row location."""

    groups: dict[tuple[object, ...], list[GdiRecord]] = defaultdict(list)
    for record in records:
        groups[gdi_fingerprint(record)].append(record)
    result: list[GdiRecord] = []
    issues: list[DiagnosticIssue] = []
    for duplicates in groups.values():
        duplicates.sort(key=lambda item: item.source_row)
        source_rows = tuple(
            row for item in duplicates for row in (item.source_rows or (item.source_row,))
        )
        first = duplicates[0]
        result.append(replace(first, source_rows=source_rows))
        if len(duplicates) < 2:
            continue
        locations = tuple(
            SourceLocation(first.source_file, first.source_sheet, cell)
            for row in source_rows
            for cell in (
                *(_cell_for_row(first.field_cell, row),),
                *(_cell_for_row(first.well_cell, row),),
                *(_cell_for_row(first.plast_cell, row),),
                *(_cell_for_row(first.research_type_cell, row),),
                *(_cell_for_row(first.date_cell, row),),
            )
            if cell is not None
        )
        issues.append(
            DiagnosticIssue(
                code="GDI_EXACT_DUPLICATE_COLLAPSED",
                severity=IssueSeverity.INFO,
                message=(
                    f"Схлопнуто {len(duplicates)} идентичных строк ГДИ в одну; "
                    "бизнес-атрибуты совпадают."
                ),
                source="gdi",
                well_id=first.base_well_id,
                locations=locations,
            )
        )
    result.sort(key=lambda item: item.source_row)
    return tuple(result), tuple(issues)


def _cell_for_row(cell: str | None, row: int) -> str | None:
    return re.sub(r"\d+$", str(row), cell) if cell is not None else None
