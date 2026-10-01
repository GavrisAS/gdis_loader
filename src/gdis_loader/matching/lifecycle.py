"""Conservative assignment of GDI rows to confirmed well-history stages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from gdis_loader.domain.dates import (
    definitely_after,
    overlaps_same_precision_window,
)
from gdis_loader.domain.models import (
    DiagnosticIssue,
    FundWell,
    GdiRecord,
    IssueSeverity,
    SourceLocation,
    WellEventKind,
    WellHistory,
    WellStage,
)
from gdis_loader.matching.normalize import normalize_field_name, normalize_well_id


@dataclass(frozen=True, slots=True)
class LifecycleResolution:
    """A stage assignment plus any provenance-rich ambiguity diagnostic."""

    stage: WellStage | None
    issue: DiagnosticIssue | None = None


def _variant_kind(identity: str) -> str | None:
    return normalize_well_id(identity).recognized_variant


def _has_unconfirmed_sequential_zbs_name(identity: str) -> bool:
    normalized = normalize_well_id(identity)
    if normalized.base_well_id is None or normalized.target_well_id is None:
        return False
    prefix = f"{normalized.base_well_id}_"
    if not normalized.target_well_id.startswith(prefix):
        return False
    return re.fullmatch(r"ЗБС\s*\d+", normalized.target_well_id[len(prefix) :]) is not None


def _record_identity(record: GdiRecord | None, fund_well: FundWell) -> str:
    if record is not None:
        return (
            record.target_well_id
            or normalize_well_id(record.raw_well_name or "").target_well_id
            or ""
        )
    return fund_well.target_well_id or normalize_well_id(fund_well.raw_display).target_well_id or ""


def _stage_kind_for_variant(variant: str | None) -> WellEventKind | None:
    if variant == "ЗБС":
        return WellEventKind.ZBS
    if variant == "ПВЛГ":
        return WellEventKind.PVLG
    if variant is None:
        return WellEventKind.INITIAL
    return None


def _issue(
    code: str,
    message: str,
    fund_well: FundWell,
    record: GdiRecord | None,
    stages: tuple[WellStage, ...],
) -> DiagnosticIssue:
    locations = list(fund_well.locations)
    if record is not None and record.source_file and record.source_sheet and record.date_cell:
        locations.append(SourceLocation(record.source_file, record.source_sheet, record.date_cell))
    locations.extend(stage.source_location for stage in stages)
    unique = tuple(dict.fromkeys(locations))
    return DiagnosticIssue(
        code=code,
        severity=IssueSeverity.WARNING,
        message=message,
        source="well_history",
        well_id=fund_well.base_well_id,
        locations=unique,
    )


def resolve_lifecycle_stage(
    fund_well: FundWell,
    record: GdiRecord | None,
    histories: tuple[WellHistory, ...],
) -> LifecycleResolution:
    """Assign a source identity to one confirmed lifecycle interval.

    The physical root is used only to find candidate history rows. Target
    identity, field, plast, and (when available) the study timestamp must then
    agree before a stage is selected.
    """

    matching_histories = tuple(
        history
        for history in histories
        if history.physical_root == fund_well.base_well_id
        and normalize_field_name(history.field_name) == fund_well.normalized_field
    )
    if not matching_histories:
        return LifecycleResolution(None)
    if len(matching_histories) > 1:
        stages = tuple(stage for history in matching_histories for stage in history.stages)
        issue = _issue(
            "WELL_HISTORY_STAGE_AMBIGUOUS",
            "Для физического корня найдены несколько строк истории в том же месторождении.",
            fund_well,
            record,
            stages,
        )
        return LifecycleResolution(None, issue)

    history = matching_histories[0]
    identity = _record_identity(record, fund_well)
    if _has_unconfirmed_sequential_zbs_name(identity):
        zbs_stages = tuple(
            stage for stage in history.stages if stage.event_kind is WellEventKind.ZBS
        )
        return LifecycleResolution(
            None,
            _issue(
                "WELL_HISTORY_STAGE_AMBIGUOUS",
                "Номер ЗБС в обозначении не сопоставляется с событием без правила именования.",
                fund_well,
                record,
                zbs_stages,
            ),
        )
    variant = _variant_kind(identity)
    expected_kind = _stage_kind_for_variant(variant)
    if expected_kind is None:
        return LifecycleResolution(None)

    plast = record.normalized_plast if record is not None else fund_well.object_plast_hint
    stages = tuple(
        stage
        for stage in history.stages
        if stage.event_kind is expected_kind and (plast is None or stage.plast == plast)
    )
    unresolved_events = tuple(
        event
        for event in history.events
        if event.event_kind in {WellEventKind.ZBS, WellEventKind.PVLG} and event.event_date is None
    )
    if unresolved_events:
        locations = list(fund_well.locations)
        if record is not None and record.source_file and record.source_sheet and record.date_cell:
            locations.append(
                SourceLocation(record.source_file, record.source_sheet, record.date_cell)
            )
        locations.extend(event.source_location for event in unresolved_events)
        return LifecycleResolution(
            None,
            DiagnosticIssue(
                code="WELL_HISTORY_STAGE_AMBIGUOUS",
                severity=IssueSeverity.WARNING,
                message="Дата подтвержденной границы жизненного цикла не распознана.",
                source="well_history",
                well_id=fund_well.base_well_id,
                locations=tuple(dict.fromkeys(locations)),
            ),
        )

    if record is None and variant is None:
        known_boundaries = tuple(
            event
            for event in history.events
            if event.event_kind in {WellEventKind.ZBS, WellEventKind.PVLG}
        )
        if known_boundaries:
            locations = [*fund_well.locations]
            locations.extend(event.source_location for event in known_boundaries)
            return LifecycleResolution(
                None,
                DiagnosticIssue(
                    code="WELL_HISTORY_STAGE_AMBIGUOUS",
                    severity=IssueSeverity.WARNING,
                    message=(
                        "Без актуальной записи ГДИ нельзя определить, относится ли фондовая "
                        "identity к материнской скважине или к последующему этапу."
                    ),
                    source="well_history",
                    well_id=fund_well.base_well_id,
                    locations=tuple(dict.fromkeys(locations)),
                ),
            )

    if record is None or record.study_date is None:
        stages = tuple(
            stage
            for stage in history.stages
            if stage.event_kind is expected_kind and (plast is None or stage.plast == plast)
        )
        if not stages:
            return LifecycleResolution(None)
        if len(stages) != 1:
            return LifecycleResolution(
                None,
                _issue(
                    "WELL_HISTORY_STAGE_AMBIGUOUS",
                    "Для обозначения скважины подходит несколько событий одного типа.",
                    fund_well,
                    record,
                    stages,
                ),
            )
        return LifecycleResolution(stages[0])

    study_date = record.study_date
    all_stages = history.stages
    overlapping = tuple(
        stage
        for stage in all_stages
        if overlaps_same_precision_window(study_date, stage.started_at)
    )
    if overlapping:
        return LifecycleResolution(
            None,
            _issue(
                "WELL_HISTORY_STAGE_AMBIGUOUS",
                "Дата ГДИ и дата начала этапа пересекаются по точности; порядок неизвестен.",
                fund_well,
                record,
                overlapping,
            ),
        )

    preceding = tuple(
        stage for stage in all_stages if definitely_after(study_date, stage.started_at)
    )
    if not preceding:
        return LifecycleResolution(None)
    latest = tuple(
        stage
        for stage in preceding
        if not any(
            other is not stage and definitely_after(other.started_at, stage.started_at)
            for other in preceding
        )
    )
    if len(latest) != 1:
        return LifecycleResolution(
            None,
            _issue(
                "WELL_HISTORY_STAGE_AMBIGUOUS",
                "Несколько подтвержденных этапов могут предшествовать этой записи ГДИ.",
                fund_well,
                record,
                latest or preceding,
            ),
        )
    selected = latest[0]
    if variant == "ЗБС":
        preceding_zbs = tuple(
            stage
            for stage in preceding
            if stage.event_kind is WellEventKind.ZBS and stage.plast == selected.plast
        )
        if len(preceding_zbs) > 1:
            return LifecycleResolution(
                None,
                _issue(
                    "WELL_HISTORY_STAGE_AMBIGUOUS",
                    (
                        "До даты ГДИ произошло несколько ЗБС; правило имени "
                        "последовательной ЗБС не подтверждено."
                    ),
                    fund_well,
                    record,
                    preceding_zbs,
                ),
            )
    if selected.event_kind is not expected_kind or (plast is not None and selected.plast != plast):
        return LifecycleResolution(
            None,
            _issue(
                "WELL_HISTORY_STAGE_AMBIGUOUS",
                "Идентификатор и пласт ГДИ не соответствуют последнему этапу истории.",
                fund_well,
                record,
                (selected,),
            ),
        )
    return LifecycleResolution(selected)


def assign_stage_by_date(
    *,
    physical_root: str,
    normalized_field: str,
    normalized_plast: str,
    observed_at: datetime,
    histories: tuple[WellHistory, ...],
    observation_location: SourceLocation,
) -> LifecycleResolution:
    """Assign an unsuffixed source row to a unique confirmed lifecycle stage.

    Physical root only locates possible history rows. Field, plast, exact
    observation timestamp, and the confirmed event timeline decide whether a
    stage can be selected. An observation in a partial-date boundary window
    remains unresolved.
    """

    candidates = tuple(
        history
        for history in histories
        if history.physical_root == physical_root
        and normalize_field_name(history.field_name) == normalized_field
    )
    if len(candidates) != 1:
        relevant_stages = tuple(stage for history in candidates for stage in history.stages)
        return LifecycleResolution(
            None,
            _timestamp_issue(
                "Для физического корня не найдена единственная строка истории.",
                observation_location,
                relevant_stages,
            ),
        )

    history = candidates[0]
    exact_observation = observed_at.date()
    unresolved_boundaries = tuple(
        event
        for event in history.events
        if event.event_kind in {WellEventKind.ZBS, WellEventKind.PVLG} and event.event_date is None
    )
    all_stages = history.stages
    overlaps = tuple(
        stage
        for stage in all_stages
        if overlaps_same_precision_window(exact_observation, stage.started_at)
    )
    if overlaps:
        return LifecycleResolution(
            None,
            _timestamp_issue(
                "Время наблюдения ЛХА совпадает с неполной датой границы жизненного цикла.",
                observation_location,
                overlaps,
            ),
        )
    preceding = tuple(
        stage for stage in all_stages if definitely_after(exact_observation, stage.started_at)
    )
    if unresolved_boundaries:
        return LifecycleResolution(
            None,
            _timestamp_issue(
                "Дата одной из подтвержденных границ жизненного цикла не распознана.",
                observation_location,
                preceding,
                tuple(event.source_location for event in unresolved_boundaries),
            ),
        )
    if not preceding:
        return LifecycleResolution(None)
    latest = tuple(
        stage
        for stage in preceding
        if not any(
            other is not stage and definitely_after(other.started_at, stage.started_at)
            for other in preceding
        )
    )
    if len(latest) != 1:
        return LifecycleResolution(
            None,
            _timestamp_issue(
                "Для timestamp ЛХА подходят несколько этапов истории.",
                observation_location,
                latest or preceding,
            ),
        )
    selected = latest[0]
    if selected.plast != normalized_plast:
        return LifecycleResolution(None)
    return LifecycleResolution(selected)


def _timestamp_issue(
    message: str,
    observation_location: SourceLocation,
    stages: tuple[WellStage, ...],
    extra_locations: tuple[SourceLocation, ...] = (),
) -> DiagnosticIssue:
    return DiagnosticIssue(
        code="WELL_HISTORY_STAGE_AMBIGUOUS",
        severity=IssueSeverity.WARNING,
        message=message,
        source="well_history",
        locations=tuple(
            dict.fromkeys(
                (
                    observation_location,
                    *(stage.source_location for stage in stages),
                    *extra_locations,
                )
            )
        ),
    )
