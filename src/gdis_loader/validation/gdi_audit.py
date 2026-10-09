"""Minimal per-source-row evidence using the production lifecycle decisions."""

from datetime import date
from typing import Any

from gdis_loader.domain.dates import effective_date
from gdis_loader.domain.models import DiagnosticIssue, FundWell, GdiRecord, WellHistory, WellStage
from gdis_loader.matching.gdi_history import current_gdi_history
from gdis_loader.matching.lifecycle import resolve_lifecycle_stage
from gdis_loader.matching.normalize import normalize_well_id
from gdis_loader.transforms.gdi_features import downhole_sources, lnd_source


def audit_gdi_rows(
    well: FundWell,
    records: tuple[GdiRecord, ...],
    histories: tuple[WellHistory, ...],
    stage: WellStage | None,
    calculation_date: date,
    depth_threshold_m: float,
    issues: tuple[DiagnosticIssue, ...] = (),
) -> list[dict[str, Any]]:
    """Explain every candidate, including invalid labels and collapsed duplicates."""
    candidates = tuple(
        r
        for r in records
        if r.base_well_id == well.base_well_id and r.normalized_field == well.normalized_field
    )
    selected = (
        current_gdi_history(
            well,
            candidates,
            histories,
            stage,
            stage.plast if stage else None,
            calculation_date=calculation_date,
        )
        if stage is not None
        else ()
    )
    depths = downhole_sources(selected, calculation_date, depth_threshold_m)
    lnd, _, previous = lnd_source(selected)
    launch = effective_date(stage.started_at) if stage else None
    result: list[dict[str, Any]] = []
    for r in candidates:
        assigned = resolve_lifecycle_stage(well, r, histories)
        day = r.study_date.date() if r.study_date is not None else None
        reason = (
            "INVALID_TYPE"
            if not r.gdi_kind.valid
            else "MISSING_DATE"
            if day is None
            else "FUTURE_DATE"
            if day > calculation_date
            else "UNRESOLVED_CURRENT_HISTORY"
            if stage is None
            else "DIFFERENT_PLAST"
            if r.normalized_plast != stage.plast
            else "DIFFERENT_OR_UNRESOLVED_HISTORY"
            if assigned.stage != stage
            else None
        )
        relation = (
            "unknown"
            if launch is None or day is None
            else "before"
            if day < launch
            else "equal"
            if day == launch
            else "after"
        )
        for offset, source_row in enumerate(r.source_rows or (r.source_row,)):
            codes = {assigned.issue.code} if assigned.issue else set()
            for issue in issues:
                if (
                    issue.code.startswith("SUMMARY_GDI_")
                    and normalize_well_id(issue.well_id or "").base_well_id == well.base_well_id
                ):
                    codes.add(issue.code)
                if any(
                    loc.file == r.source_file
                    and loc.sheet == r.source_sheet
                    and loc.cell is not None
                    and loc.cell.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ") == str(source_row)
                    for loc in issue.locations
                ):
                    codes.add(issue.code)
            if reason is None and relation == "before":
                codes.add("GDI_PRE_LAUNCH_CURRENT_BRANCH_INCLUDED")
            duplicate = offset > 0
            result.append(
                {
                    "field": well.normalized_field,
                    "target_well": stage.target_well_id if stage else well.target_well_id,
                    "raw_well": r.raw_well_name,
                    "canonical_well": r.target_well_id,
                    "source_file": r.source_file,
                    "source_sheet": r.source_sheet,
                    "source_row": source_row,
                    "raw_plast": r.raw_plast,
                    "canonical_plast": r.normalized_plast,
                    "research_date": day.isoformat() if day else None,
                    "raw_research_type": r.research_type,
                    "canonical_research_type": r.gdi_kind.value,
                    "valid_type": r.gdi_kind.valid,
                    "candidate_history": assigned.stage.stage_sequence if assigned.stage else None,
                    "candidate_identity": assigned.stage.target_well_id if assigned.stage else None,
                    "selected_current_history": stage is not None and assigned.stage == stage,
                    "launch_date": launch.isoformat() if launch else None,
                    "launch_relation": relation,
                    "counted": reason is None and not duplicate,
                    "exclusion_reason": "EXACT_DUPLICATE" if duplicate else reason,
                    "inclusion_reason": (
                        "CURRENT_BRANCH_LAUNCH_DISAGREEMENT"
                        if relation == "before"
                        else "CURRENT_HISTORY_PLAST"
                    )
                    if reason is None
                    else None,
                    "used_for_downhole": r in depths and not duplicate,
                    "used_for_lnd_latest": r == lnd and not previous and not duplicate,
                    "used_for_lnd_previous": r == lnd and previous and not duplicate,
                    "diagnostic_codes": sorted(codes),
                }
            )
    return result
