"""Conservative assignment of GDI rows to confirmed well-history stages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from gdis_loader.domain.dates import (
    effective_calendar_date,
)
from gdis_loader.domain.models import (
    DiagnosticIssue,
    FundWell,
    GdiRecord,
    IssueSeverity,
    PartialDate,
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


def _zbs_ordinal(identity: str) -> int:
    normalized = normalize_well_id(identity)
    if normalized.base_well_id is None or normalized.target_well_id is None:
        return 1
    suffix = normalized.target_well_id.removeprefix(f"{normalized.base_well_id}_")
    match = re.fullmatch(r"ЗБС\s*(\d*)", suffix)
    return int(match.group(1)) if match is not None and match.group(1) else 1


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
    if variant == "ПНЛГ":
        return WellEventKind.PNLG
    if variant in {None, "МЗС", "ГС"}:
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


def _assign_unsuffixed_record_by_timeline(
    fund_well: FundWell,
    record: GdiRecord,
    history: WellHistory,
) -> LifecycleResolution:
    """Assign a root-only GDI label to one exact-plast stage by its date."""

    if record.study_date is None:
        return LifecycleResolution(None)
    unresolved_events = tuple(
        event
        for event in history.events
        if event.event_kind in {WellEventKind.ZBS, WellEventKind.PVLG, WellEventKind.PNLG}
        and event.event_date is None
    )
    if unresolved_events:
        locations = [*fund_well.locations, *record.locations]
        locations.extend(event.source_location for event in unresolved_events)
        return LifecycleResolution(
            None,
            DiagnosticIssue(
                code="WELL_HISTORY_STAGE_AMBIGUOUS",
                severity=IssueSeverity.WARNING,
                message="Дата подтвержденной lifecycle-границы не распознана.",
                source="well_history",
                well_id=fund_well.base_well_id,
                locations=tuple(dict.fromkeys(locations)),
            ),
        )

    study_day = effective_calendar_date(record.study_date)
    preceding = tuple(
        stage for stage in history.stages if study_day >= effective_calendar_date(stage.started_at)
    )
    if not preceding:
        return LifecycleResolution(None)
    latest = tuple(
        stage
        for stage in preceding
        if not any(
            other is not stage
            and effective_calendar_date(other.started_at)
            > effective_calendar_date(stage.started_at)
            for other in preceding
        )
    )
    if len(latest) != 1:
        return LifecycleResolution(
            None,
            _issue(
                "WELL_HISTORY_STAGE_AMBIGUOUS",
                "Для даты root-only ГДИ подходят несколько lifecycle-этапов.",
                fund_well,
                record,
                latest or preceding,
            ),
        )
    stage = latest[0]
    if record.normalized_plast is None or stage.plast != record.normalized_plast:
        return LifecycleResolution(
            None,
            _issue(
                "UNRESOLVED_PLAST_EQUIVALENCE",
                (
                    "Пласт root-only ГДИ не совпадает с пластом последнего этапа; "
                    "эквивалентность не предполагается."
                ),
                fund_well,
                record,
                (stage,),
            ),
        )
    return LifecycleResolution(stage)


def _resolve_current_fund_stage(
    fund_well: FundWell,
    record: GdiRecord | None,
    history: WellHistory,
    *,
    expected_kind: WellEventKind | None = None,
    zbs_ordinal: int | None = None,
) -> LifecycleResolution:
    """Resolve the fund's current stage from its plast and confirmed timeline."""

    eligible = tuple(
        stage
        for stage in history.stages
        if effective_calendar_date(stage.started_at) <= fund_well.fund_date
    )
    if not eligible:
        return LifecycleResolution(None)

    latest_date = max(effective_calendar_date(stage.started_at) for stage in eligible)
    latest = tuple(
        stage for stage in eligible if effective_calendar_date(stage.started_at) == latest_date
    )
    if expected_kind is not None:
        latest = tuple(stage for stage in latest if stage.event_kind is expected_kind)
    if zbs_ordinal is not None:
        zbs_stages = tuple(
            stage for stage in history.stages if stage.event_kind is WellEventKind.ZBS
        )
        if zbs_ordinal > len(zbs_stages):
            return LifecycleResolution(
                None,
                _issue(
                    "WELL_HISTORY_STAGE_NOT_FOUND",
                    (
                        f"Для обозначения ЗБС{zbs_ordinal if zbs_ordinal > 1 else ''} "
                        "нет этапа в истории."
                    ),
                    fund_well,
                    record,
                    zbs_stages,
                ),
            )
        named_stage = zbs_stages[zbs_ordinal - 1]
        latest = tuple(stage for stage in latest if stage == named_stage)

    plast = fund_well.object_plast_hint
    if plast is not None:
        latest = tuple(stage for stage in latest if stage.plast == plast)

    # Sequential ZBS stages receive stable ordinals from the history reader.
    # When same-day ZBS events otherwise tie, the latest confirmed ordinal is
    # the current branch. Ties across different boundary kinds remain ambiguous.
    if len(latest) > 1 and all(stage.event_kind is WellEventKind.ZBS for stage in latest):
        latest = (max(latest, key=lambda stage: stage.stage_sequence),)

    if len(latest) == 1:
        return LifecycleResolution(latest[0])

    ambiguity_candidates = latest or tuple(
        stage for stage in eligible if effective_calendar_date(stage.started_at) == latest_date
    )
    return LifecycleResolution(
        None,
        _issue(
            "WELL_HISTORY_STAGE_AMBIGUOUS",
            (
                "Текущий пласт фонда не соответствует единственному последнему lifecycle-этапу; "
                "предыдущая история не используется."
                if not latest
                else "Для текущего состояния фонда остаются несколько совместимых этапов истории."
            ),
            fund_well,
            record,
            ambiguity_candidates,
        ),
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

    identity = _record_identity(record, fund_well)
    variant = _variant_kind(identity)
    normalized_identity = normalize_well_id(identity)
    matching_histories = tuple(
        history
        for history in histories
        if history.physical_root == fund_well.base_well_id
        and normalize_field_name(history.field_name) == fund_well.normalized_field
    )
    if variant in {"МЗС", "ГС"} or (
        normalized_identity.target_well_id != normalized_identity.base_well_id and variant is None
    ):
        matching_histories = tuple(
            history
            for history in matching_histories
            if normalize_well_id(history.source_display_well).target_well_id
            == normalized_identity.target_well_id
        )
    else:
        root_histories = tuple(
            history
            for history in matching_histories
            if normalize_well_id(history.source_display_well).target_well_id
            == normalized_identity.base_well_id
        )
        if root_histories:
            matching_histories = root_histories
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
    expected_kind = _stage_kind_for_variant(variant)
    if expected_kind is None and variant not in {"ПВР", "КЛК"}:
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
        if event.event_kind in {WellEventKind.ZBS, WellEventKind.PVLG, WellEventKind.PNLG}
        and event.event_date is None
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

    if record is None and variant in {None, "ПВЛГ", "ПНЛГ", "ПВР", "КЛК"}:
        return _resolve_current_fund_stage(
            fund_well,
            record,
            history,
            expected_kind=(expected_kind if variant in {"ПВЛГ", "ПНЛГ"} else None),
        )

    if record is None and variant == "ЗБС":
        return _resolve_current_fund_stage(
            fund_well,
            record,
            history,
            expected_kind=WellEventKind.ZBS,
            zbs_ordinal=_zbs_ordinal(identity),
        )

    if variant in {None, "ПВР", "КЛК"} and record is not None and record.study_date is not None:
        return _assign_unsuffixed_record_by_timeline(fund_well, record, history)

    if record is None or record.study_date is None:
        if variant in {"ПВР", "КЛК"}:
            candidates = tuple(
                stage for stage in history.stages if plast is None or stage.plast == plast
            )
            if not candidates:
                return LifecycleResolution(None)
            latest_start = max(
                (
                    stage.started_at.year,
                    stage.started_at.month or 1,
                    stage.started_at.day or 1,
                )
                for stage in candidates
            )
            latest_candidates = tuple(
                stage
                for stage in candidates
                if (
                    stage.started_at.year,
                    stage.started_at.month or 1,
                    stage.started_at.day or 1,
                )
                == latest_start
            )
            if len(latest_candidates) == 1:
                return LifecycleResolution(latest_candidates[0])
            return LifecycleResolution(
                None,
                _issue(
                    "WELL_HISTORY_STAGE_AMBIGUOUS",
                    "Для текущего пласта найдено несколько равнодатных этапов истории.",
                    fund_well,
                    record,
                    latest_candidates,
                ),
            )
        stages = tuple(
            stage
            for stage in history.stages
            if stage.event_kind is expected_kind and (plast is None or stage.plast == plast)
        )
        if variant == "ЗБС":
            all_zbs = tuple(
                sorted(
                    (stage for stage in history.stages if stage.event_kind is WellEventKind.ZBS),
                    key=lambda stage: (
                        stage.started_at.year,
                        stage.started_at.month or 1,
                        stage.started_at.day or 1,
                        stage.stage_sequence,
                    ),
                )
            )
            ordinal = _zbs_ordinal(identity)
            if ordinal <= len(all_zbs):
                selected_zbs = all_zbs[ordinal - 1]
                return LifecycleResolution(
                    selected_zbs if plast is None or selected_zbs.plast == plast else None,
                    None
                    if plast is None or selected_zbs.plast == plast
                    else _issue(
                        "UNRESOLVED_PLAST_EQUIVALENCE",
                        "Этап ЗБС имеет другое обозначение текущего пласта.",
                        fund_well,
                        record,
                        (selected_zbs,),
                    ),
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
    study_day = effective_calendar_date(study_date)
    preceding = tuple(
        stage for stage in all_stages if study_day >= effective_calendar_date(stage.started_at)
    )
    if not preceding:
        return LifecycleResolution(None)
    latest = tuple(
        stage
        for stage in preceding
        if not any(
            other is not stage
            and effective_calendar_date(other.started_at)
            > effective_calendar_date(stage.started_at)
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
        all_zbs = tuple(
            sorted(
                (stage for stage in all_stages if stage.event_kind is WellEventKind.ZBS),
                key=lambda stage: (
                    stage.started_at.year,
                    stage.started_at.month or 1,
                    stage.started_at.day or 1,
                    stage.stage_sequence,
                ),
            )
        )
        ordinal = _zbs_ordinal(identity)
        if ordinal > len(all_zbs):
            return LifecycleResolution(
                None,
                _issue(
                    "WELL_HISTORY_STAGE_NOT_FOUND",
                    f"Для обозначения ЗБС{ordinal if ordinal > 1 else ''} нет этапа в истории.",
                    fund_well,
                    record,
                    all_zbs,
                ),
            )
        named_stage = all_zbs[ordinal - 1]
        if named_stage not in preceding:
            return LifecycleResolution(None)
        later_boundaries = tuple(
            stage
            for stage in preceding
            if stage is not named_stage
            and effective_calendar_date(stage.started_at)
            > effective_calendar_date(named_stage.started_at)
        )
        if later_boundaries:
            return LifecycleResolution(
                None,
                _issue(
                    "WELL_HISTORY_STAGE_AMBIGUOUS",
                    "Дата ГДИ относится к периоду после более поздней lifecycle-границы.",
                    fund_well,
                    record,
                    (named_stage, *later_boundaries),
                ),
            )
        selected = named_stage
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
    observed_at: datetime | PartialDate,
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
        and normalize_well_id(history.source_display_well).target_well_id == physical_root
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
    observation_date = effective_calendar_date(observed_at)
    unresolved_boundaries = tuple(
        event
        for event in history.events
        if event.event_kind in {WellEventKind.ZBS, WellEventKind.PVLG, WellEventKind.PNLG}
        and event.event_date is None
    )
    all_stages = history.stages
    preceding = tuple(
        stage
        for stage in all_stages
        if observation_date >= effective_calendar_date(stage.started_at)
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
            other is not stage
            and effective_calendar_date(other.started_at)
            > effective_calendar_date(stage.started_at)
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
