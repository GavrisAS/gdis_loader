"""Independently reconcile post-launch GDI counts for a production bundle.

The script prints aggregate metrics and the four approved customer examples;
it never emits a per-well production dump.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from gdis_loader.domain.dates import effective_date
from gdis_loader.domain.models import GdiKind, MatchStatus, SourcePaths, WellEventKind
from gdis_loader.matching.lifecycle import resolve_lifecycle_stage
from gdis_loader.matching.matcher import GdiIndex, match_fund_well
from gdis_loader.matching.normalize import normalize_field_name
from gdis_loader.readers.fund import read_fund
from gdis_loader.readers.gdi import read_gdi
from gdis_loader.readers.well_history import read_well_history
from gdis_loader.transforms.gdi import collapse_exact_gdi_duplicates
from gdis_loader.validation.reconciliation import application_count_state

_VALID_KINDS = frozenset({GdiKind.ID, GdiKind.ID_KVD, GdiKind.KVD})
_CUSTOMER_WELLS = frozenset({"12", "13", "21", "22"})


def _application_counts(path: Path | None) -> dict[str, int | None]:
    if path is None:
        return {}
    workbook = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        worksheet = workbook["Данные"]
        headers = tuple(cell.value for cell in next(worksheet.iter_rows(min_row=6, max_row=6)))
        indexes = {value: index for index, value in enumerate(headers) if value is not None}
        result: dict[str, int | None] = {}
        well_index = indexes["Скважина"]
        count_index = indexes["Количество ГДИ"]
        for row in worksheet.iter_rows(min_row=7, values_only=True):
            well = row[well_index]
            if well is None:
                continue
            count = row[count_index]
            result[str(well)] = int(count) if isinstance(count, (int, float)) else None
        return result
    finally:
        workbook.close()


def reconcile(paths: SourcePaths, target_field: str, output: Path | None) -> dict[str, Any]:
    """Compare direct source counts with independently read calculator values."""

    fund = read_fund(paths.fund)
    history_result = read_well_history(paths.well_history, target_field)
    raw_records, _issues = read_gdi(paths.gdi)
    field_key = normalize_field_name(target_field)
    scoped_raw = tuple(item for item in raw_records if item.normalized_field == field_key)
    deduplicated, _duplicate_issues = collapse_exact_gdi_duplicates(scoped_raw)
    direct_index = GdiIndex(deduplicated, date.today())
    application = _application_counts(output)
    metrics: Counter[str] = Counter()
    examples: dict[str, dict[str, Any]] = {}
    eligible = tuple(
        well
        for well in fund.wells
        if well.normalized_field == field_key and well.is_rating_eligible
    )
    metrics["eligible_target_rows"] = len(eligible)
    metrics["raw_valid_gdi_source_rows"] = sum(item.gdi_kind in _VALID_KINDS for item in scoped_raw)
    metrics["deduplicated_valid_gdi_source_rows"] = sum(
        item.gdi_kind in _VALID_KINDS for item in deduplicated
    )
    metrics["exact_duplicate_rows_collapsed"] = len(scoped_raw) - len(deduplicated)
    metrics["eligible_with_resolved_lifecycle"] = 0
    metrics["eligible_with_unresolved_lifecycle"] = 0
    metrics["raw_valid_rows_same_root_field"] = 0
    metrics["raw_valid_rows_excluded_lifecycle_or_plast"] = 0
    metrics["raw_valid_rows_current_lifecycle_plast"] = 0
    metrics["deduplicated_valid_rows_current_lifecycle_plast"] = 0
    metrics["deduplicated_valid_rows_before_launch"] = 0
    metrics["deduplicated_valid_rows_after_launch"] = 0
    metrics["application_count_mismatches"] = 0

    for well in eligible:
        initial = resolve_lifecycle_stage(well, None, history_result.histories)
        match = match_fund_well(well, direct_index, history_result.histories)
        resolution = (
            resolve_lifecycle_stage(well, match.record, history_result.histories)
            if match.record is not None
            else initial
        )
        stage = resolution.stage
        root_records = tuple(
            item
            for item in scoped_raw
            if item.base_well_id == well.base_well_id and item.gdi_kind in _VALID_KINDS
        )
        metrics["raw_valid_rows_same_root_field"] += len(root_records)
        if match.status is MatchStatus.AMBIGUOUS or stage is None or resolution.issue is not None:
            metrics["eligible_with_unresolved_lifecycle"] += 1
            metrics["raw_valid_rows_excluded_lifecycle_or_plast"] += len(root_records)
            continue

        metrics["eligible_with_resolved_lifecycle"] += 1
        launch = effective_date(stage.started_at)
        current_raw: list[Any] = []
        current_deduplicated: list[Any] = []
        for record in root_records:
            record_stage = resolve_lifecycle_stage(well, record, history_result.histories)
            is_current = (
                record_stage.stage == stage
                and record_stage.issue is None
                and record.normalized_plast == stage.plast
            )
            if (
                not is_current
                and record.study_date is not None
                and record.study_date.date() < launch
                and record.normalized_plast == stage.plast
            ):
                source_identity = record.target_well_id or well.base_well_id
                stage_identity = stage.target_well_id or stage.physical_root
                is_current = (
                    stage.event_kind is WellEventKind.INITIAL
                    and source_identity == stage.physical_root
                ) or (stage.event_kind is WellEventKind.ZBS and source_identity == stage_identity)
            if is_current:
                current_raw.append(record)
        dedup_root = tuple(
            item
            for item in deduplicated
            if item.base_well_id == well.base_well_id and item.gdi_kind in _VALID_KINDS
        )
        for record in dedup_root:
            record_stage = resolve_lifecycle_stage(well, record, history_result.histories)
            if (
                record_stage.stage == stage
                and record_stage.issue is None
                and record.normalized_plast == stage.plast
            ):
                current_deduplicated.append(record)
            elif (
                record.study_date is not None
                and record.study_date.date() < launch
                and record.normalized_plast == stage.plast
            ):
                source_identity = record.target_well_id or well.base_well_id
                stage_identity = stage.target_well_id or stage.physical_root
                if (
                    stage.event_kind is WellEventKind.INITIAL
                    and source_identity == stage.physical_root
                ) or (stage.event_kind is WellEventKind.ZBS and source_identity == stage_identity):
                    current_deduplicated.append(record)

        raw_before = sum(
            record.study_date is not None and record.study_date.date() < launch
            for record in current_raw
        )
        deduplicated_before = sum(
            record.study_date is not None and record.study_date.date() < launch
            for record in current_deduplicated
        )
        deduplicated_after = sum(
            record.study_date is not None and record.study_date.date() >= launch
            for record in current_deduplicated
        )
        raw_after = sum(
            record.study_date is not None and record.study_date.date() >= launch
            for record in current_raw
        )
        excluded = len(root_records) - len(current_raw)
        metrics["raw_valid_rows_excluded_lifecycle_or_plast"] += excluded
        metrics["raw_valid_rows_current_lifecycle_plast"] += len(current_raw)
        metrics["deduplicated_valid_rows_current_lifecycle_plast"] += len(current_deduplicated)
        metrics["deduplicated_valid_rows_before_launch"] += deduplicated_before
        metrics["deduplicated_valid_rows_after_launch"] += deduplicated_after
        application_count = application.get(
            stage.target_well_id or well.target_well_id or well.raw_display
        )
        application_state = application_count_state(application_count, deduplicated_after)
        if application_state == "mismatch":
            metrics["application_count_mismatches"] += 1

        if well.base_well_id in _CUSTOMER_WELLS:
            identity = stage.target_well_id or well.target_well_id or well.raw_display
            examples[well.base_well_id] = {
                "target_identity": identity,
                "launch_date": launch.isoformat(),
                "raw_valid_current_lifecycle_plast": len(current_raw),
                "deduplicated_valid_current_lifecycle_plast": len(current_deduplicated),
                "raw_count_before_launch": raw_before,
                "deduplicated_count_before_launch": deduplicated_before,
                "raw_count_after_launch": raw_after,
                "deduplicated_count_after_launch": deduplicated_after,
                "first_post_launch_gdi_date": min(
                    (
                        record.study_date.date().isoformat()
                        for record in current_deduplicated
                        if record.study_date is not None and record.study_date.date() >= launch
                    ),
                    default=None,
                ),
                "excluded_by_lifecycle_or_plast": excluded,
                "calculator_count": application_count,
                "calculator_count_state": application_state,
                "count_matches_calculator": (
                    None if application_state == "missing" else application_state == "match"
                ),
            }

    return {
        "target_field": target_field,
        "source_rows": len(scoped_raw),
        "deduplicated_source_rows": len(deduplicated),
        "metrics": dict(sorted(metrics.items())),
        "customer_examples": examples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calculator", type=Path)
    parser.add_argument("--fund", type=Path, required=True)
    parser.add_argument("--gdi", type=Path, required=True)
    parser.add_argument("--well-history", type=Path, required=True)
    parser.add_argument("--field", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = reconcile(
        SourcePaths(
            calculator=args.calculator or Path("unused.xlsx"),
            fund=args.fund,
            gdi=args.gdi,
            lha=Path("unused.xlsm"),
            daily_report=Path("unused.xlsm"),
            well_history=args.well_history,
            research_status=Path("unused.xlsx"),
        ),
        args.field,
        args.output,
    )
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report is not None:
        args.report.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
