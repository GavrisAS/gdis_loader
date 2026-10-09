"""Resolve Summary GDI plast within a confirmed current lifecycle interval."""

from dataclasses import dataclass, replace

from gdis_loader.domain.models import (
    DiagnosticIssue,
    FundWell,
    GdiRecord,
    IssueSeverity,
    WellHistory,
    WellStage,
)
from gdis_loader.matching.lifecycle import resolve_lifecycle_stage
from gdis_loader.matching.matcher import GdiIndex
from gdis_loader.matching.summary_history import supplement_summary_history


@dataclass(frozen=True, slots=True)
class CurrentPlastResolution:
    well: FundWell
    histories: tuple[WellHistory, ...]
    issue: DiagnosticIssue
    ambiguous: bool = False
    original_history_plast: str | None = None


def _belongs_to_stage(
    well: FundWell,
    record: GdiRecord,
    stage: WellStage,
    histories: tuple[WellHistory, ...],
) -> bool:
    """Check the confirmed interval/identity before trusting observed plast."""
    probe = replace(stage, plast=record.normalized_plast)
    timeline = tuple(
        replace(history, stages=tuple(probe if item == stage else item for item in history.stages))
        for history in histories
    )
    return resolve_lifecycle_stage(well, record, timeline).stage == probe


def resolve_current_plast(
    well: FundWell, index: GdiIndex, histories: tuple[WellHistory, ...]
) -> CurrentPlastResolution:
    """Use timeline/branch constraints before selecting the newest Summary plast.

    Temporarily remove the Fund object constraint and provisionally apply the observed plast
    only for timeline assignment. All identity, ordinal, date and unresolved
    boundary checks still run through the established lifecycle resolver.
    The resulting stage is copied locally, never written into a source workbook.
    """
    histories, inferred, conflict = supplement_summary_history(
        well, index.history_for(well), histories
    )
    if conflict:
        return CurrentPlastResolution(
            well,
            histories,
            DiagnosticIssue(
                code="SUMMARY_GDI_HISTORY_AMBIGUOUS",
                severity=IssueSeverity.WARNING,
                message="Summary GDI не подтверждает единственную непротиворечивую ветку.",
                source="gdi",
                well_id=well.target_well_id,
                locations=tuple(loc for r in index.history_for(well) for loc in r.locations),
            ),
            True,
        )
    unconstrained = replace(well, object_name="", object_plast_hint=None)
    current = resolve_lifecycle_stage(unconstrained, None, histories)
    candidates = tuple(
        record
        for record in index.history_for(well)
        if current.stage is not None
        and _belongs_to_stage(unconstrained, record, current.stage, histories)
    )
    code = "SUMMARY_GDI_CURRENT_PLAST_NOT_FOUND"
    message = (
        "Нет безопасного текущего пласта из Сводной ГДИ; сохранён контракт Fund/Base fallback."
    )
    locations = well.locations
    ambiguous = False
    if candidates:
        latest_date = max(
            record.study_date for record in candidates if record.study_date is not None
        )
        latest = tuple(record for record in candidates if record.study_date == latest_date)
        plasts = {record.normalized_plast for record in latest}
        locations = tuple(dict.fromkeys(loc for record in latest for loc in record.locations))
        if len(plasts) != 1:
            code = "SUMMARY_GDI_CURRENT_PLAST_AMBIGUOUS"
            message = (
                "На последнюю дату текущей истории указаны разные пласты; assignment заблокирован."
            )
            ambiguous = True
        else:
            plast = latest[0].normalized_plast
            assert current.stage is not None
            selected = replace(current.stage, plast=plast)
            histories = tuple(
                replace(
                    history,
                    stages=tuple(
                        selected if stage == current.stage else stage for stage in history.stages
                    ),
                )
                for history in histories
            )
            well = replace(well, object_name=plast or "", object_plast_hint=plast)
            code = (
                "SUMMARY_GDI_CURRENT_HISTORY_INFERRED"
                if inferred
                else "SUMMARY_GDI_CURRENT_PLAST_SELECTED"
            )
            message = (
                "Текущий пласт выбран из последней валидной Сводной ГДИ в подтверждённой истории."
            )
    return CurrentPlastResolution(
        well,
        histories,
        DiagnosticIssue(
            code=code,
            severity=IssueSeverity.WARNING if ambiguous else IssueSeverity.INFO,
            message=message,
            source="gdi",
            well_id=well.target_well_id,
            locations=locations,
        ),
        ambiguous,
        current.stage.plast if current.stage is not None else None,
    )
