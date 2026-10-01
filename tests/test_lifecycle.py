from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

from gdis_loader.domain.models import (
    DatePrecision,
    FundCategory,
    FundWell,
    GdiKind,
    GdiRecord,
    PartialDate,
    SourceLocation,
    WellEvent,
    WellEventKind,
    WellHistory,
    WellStage,
)
from gdis_loader.matching.lifecycle import assign_stage_by_date, resolve_lifecycle_stage
from gdis_loader.matching.normalize import normalize_field_name, normalize_plast, normalize_well_id


def _fund(identity: str, plast: str = "ПК1") -> FundWell:
    normalized = normalize_well_id(identity)
    return FundWell(
        raw_display=identity,
        base_well_id=normalized.base_well_id,
        target_well_id=normalized.target_well_id,
        field_name="Береговое",
        normalized_field=normalize_field_name("Береговое"),
        object_name=f"Береговое ({plast})",
        source_category=FundCategory.PRODUCING,
        fund_date=date(2026, 8, 1),
        source_row=3,
        source_column="C",
        object_plast_hint=normalize_plast(plast),
        source_file="fund.xlsx",
        source_sheet="01.08.2026",
        well_cell="C3",
    )


def _record(identity: str, when: datetime, plast: str = "ПК1") -> GdiRecord:
    normalized = normalize_well_id(identity)
    return GdiRecord(
        raw_field_name="Береговое",
        normalized_field=normalize_field_name("Береговое"),
        raw_well_name=identity,
        base_well_id=normalized.base_well_id,
        target_well_id=normalized.target_well_id,
        raw_plast=plast,
        normalized_plast=normalize_plast(plast),
        research_type="ИД",
        study_date=when,
        rfp_result="да",
        lnd_reliability="Высокая",
        gtm_date=None,
        source_row=10,
        source_file="gdi.xlsx",
        source_sheet="ГДИ",
        date_cell="E10",
        gdi_kind=GdiKind.ID,
    )


def _stage(kind: WellEventKind, start: PartialDate, plast: str, row: int) -> WellStage:
    return WellStage(
        field_name="Береговое",
        physical_root="51",
        source_display_well="051",
        target_well_id=None,
        plast=normalize_plast(plast),
        event_kind=kind,
        started_at=start,
        stage_sequence=row - 3,
        source_location=SourceLocation("history.xlsx", "БЛУ", f"I{row}"),
        raw_block=(),
    )


def _history() -> WellHistory:
    stages = (
        _stage(WellEventKind.INITIAL, PartialDate(2010, 1, 1, DatePrecision.DAY), "ПК1", 3),
        _stage(WellEventKind.ZBS, PartialDate(2021, 3, 15, DatePrecision.DAY), "ПК1", 4),
        _stage(WellEventKind.PVLG, PartialDate(2023, 6, 1, DatePrecision.DAY), "ПК2", 5),
    )
    events = tuple(
        WellEvent(
            field_name=stage.field_name,
            physical_root=stage.physical_root,
            source_display_well=stage.source_display_well,
            plast=stage.plast,
            event_kind=stage.event_kind,
            event_label=stage.event_kind.value,
            event_date=stage.started_at,
            source_location=stage.source_location,
            raw_block=(),
        )
        for stage in stages
    )
    return WellHistory("Береговое", "51", "051", events, stages)


def test_zbs_and_pvlg_resolve_to_distinct_launch_stages() -> None:
    history = (_history(),)

    zbs = resolve_lifecycle_stage(
        _fund("051_ЗБС"), _record("51_ЗБС", datetime(2022, 5, 1)), history
    )
    pvlg = resolve_lifecycle_stage(
        _fund("051_ПВЛГ", "ПК2"),
        _record("51_ПВЛГ", datetime(2024, 5, 1), "ПК2"),
        history,
    )

    assert zbs.stage is not None
    assert zbs.stage.event_kind is WellEventKind.ZBS
    assert zbs.stage.started_at == PartialDate(2021, 3, 15, DatePrecision.DAY)
    assert pvlg.stage is not None
    assert pvlg.stage.event_kind is WellEventKind.PVLG
    assert pvlg.stage.started_at == PartialDate(2023, 6, 1, DatePrecision.DAY)


def test_mzs_does_not_inherit_parent_launch_history() -> None:
    resolution = resolve_lifecycle_stage(
        _fund("051_МЗС"), _record("51_МЗС", datetime(2024, 5, 1)), (_history(),)
    )

    assert resolution.stage is None
    assert resolution.issue is None


def test_missing_gdi_does_not_assign_base_well_after_lifecycle_boundary() -> None:
    resolution = resolve_lifecycle_stage(_fund("051"), None, (_history(),))

    assert resolution.stage is None
    assert resolution.issue is not None
    assert resolution.issue.code == "WELL_HISTORY_STAGE_AMBIGUOUS"
    assert SourceLocation("history.xlsx", "БЛУ", "I4") in resolution.issue.locations


def test_same_month_stage_boundary_returns_provenance_rich_ambiguity() -> None:
    history = _history()
    ambiguous = replace(
        history.stages[1],
        started_at=PartialDate(2023, 6, None, DatePrecision.MONTH),
        source_location=SourceLocation("history.xlsx", "БЛУ", "O4"),
    )
    modified = WellHistory(
        history.field_name,
        history.physical_root,
        history.source_display_well,
        history.events,
        (history.stages[0], ambiguous),
    )

    resolution = resolve_lifecycle_stage(
        _fund("051_ЗБС"), _record("51_ЗБС", datetime(2023, 6, 15)), (modified,)
    )

    assert resolution.stage is None
    assert resolution.issue is not None
    assert resolution.issue.code == "WELL_HISTORY_STAGE_AMBIGUOUS"
    assert SourceLocation("gdi.xlsx", "ГДИ", "E10") in resolution.issue.locations
    assert SourceLocation("history.xlsx", "БЛУ", "O4") in resolution.issue.locations


def test_sequential_zbs_names_remain_ambiguous_without_customer_rule() -> None:
    history = _history()
    second_zbs = _stage(
        WellEventKind.ZBS,
        PartialDate(2022, 7, 1, DatePrecision.DAY),
        "ПК1",
        6,
    )
    modified = WellHistory(
        history.field_name,
        history.physical_root,
        history.source_display_well,
        history.events,
        (*history.stages[:2], second_zbs),
    )

    resolution = resolve_lifecycle_stage(
        _fund("051_ЗБС"), _record("51_ЗБС", datetime(2023, 7, 1)), (modified,)
    )

    assert resolution.stage is None
    assert resolution.issue is not None
    assert resolution.issue.code == "WELL_HISTORY_STAGE_AMBIGUOUS"
    assert SourceLocation("history.xlsx", "БЛУ", "I4") in resolution.issue.locations
    assert SourceLocation("history.xlsx", "БЛУ", "I6") in resolution.issue.locations


def test_numbered_zbs_identity_is_not_assigned_to_an_event_automatically() -> None:
    resolution = resolve_lifecycle_stage(
        _fund("051_ЗБС2"), _record("51_ЗБС2", datetime(2024, 5, 1)), (_history(),)
    )

    assert resolution.stage is None
    assert resolution.issue is not None
    assert resolution.issue.code == "WELL_HISTORY_STAGE_AMBIGUOUS"
    assert SourceLocation("history.xlsx", "БЛУ", "I4") in resolution.issue.locations


def test_lha_old_plast_does_not_cross_a_confirmed_plast_transfer() -> None:
    resolution = assign_stage_by_date(
        physical_root="51",
        normalized_field="береговое",
        normalized_plast="ПК1",
        observed_at=datetime(2024, 5, 1),
        histories=(_history(),),
        observation_location=SourceLocation("lha.xlsm", "БД Сибнефтегаз", "D9"),
    )

    assert resolution.stage is None
    assert resolution.issue is None
