from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

import pytest

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
from gdis_loader.service import _effective_target_identity


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


def test_pvlg_keeps_separate_history_with_same_display_well_number() -> None:
    fund = _fund("051", "ПК1")
    history = (_history(),)
    before_pvlg = resolve_lifecycle_stage(fund, _record("51", datetime(2015, 5, 1), "ПК1"), history)
    after_pvlg_record = _record("51_ПВЛГ", datetime(2024, 5, 1), "ПК2")
    after_pvlg = resolve_lifecycle_stage(fund, after_pvlg_record, history)

    assert before_pvlg.stage is not None
    assert before_pvlg.stage.event_kind is WellEventKind.INITIAL
    assert after_pvlg.stage is not None
    assert after_pvlg.stage.event_kind is WellEventKind.PVLG
    assert _effective_target_identity(fund, None, before_pvlg.stage) == "51"
    assert _effective_target_identity(fund, after_pvlg_record, after_pvlg.stage) == "51"


def test_unsuffixed_gdi_after_zbs_maps_by_date_and_exact_plast() -> None:
    resolution = resolve_lifecycle_stage(
        _fund("051"), _record("51", datetime(2022, 5, 1), "ПК1"), (_history(),)
    )

    assert resolution.issue is None
    assert resolution.stage is not None
    assert resolution.stage.event_kind is WellEventKind.ZBS
    assert resolution.stage.source_location == SourceLocation("history.xlsx", "БЛУ", "I4")


def test_unsuffixed_gdi_after_effective_month_boundary_is_assigned() -> None:
    history = _history()
    stage = replace(
        history.stages[1],
        started_at=PartialDate(2021, 3, None, DatePrecision.MONTH),
    )
    modified = replace(history, stages=(history.stages[0], stage, history.stages[2]))

    resolution = resolve_lifecycle_stage(
        _fund("051"), _record("51", datetime(2021, 3, 20), "ПК1"), (modified,)
    )

    assert resolution.stage == stage
    assert resolution.issue is None


def test_plast_sublayer_normalization_allows_exact_primary_plast_match() -> None:
    resolution = resolve_lifecycle_stage(
        _fund("051"), _record("51", datetime(2022, 5, 1), "ПК1-1"), (_history(),)
    )

    assert resolution.stage is not None
    assert resolution.stage.event_kind is WellEventKind.ZBS
    assert resolution.issue is None


def test_status_partial_dates_use_agreed_effective_first_day() -> None:
    history = _history()
    location = SourceLocation("status.xlsx", "АР_таблица_БЛУ", "D12")

    after_boundary = assign_stage_by_date(
        physical_root="51",
        normalized_field="береговое",
        normalized_plast="ПК1",
        observed_at=PartialDate(2021, 4, None, DatePrecision.MONTH),
        histories=(history,),
        observation_location=location,
    )
    boundary_month = assign_stage_by_date(
        physical_root="51",
        normalized_field="береговое",
        normalized_plast="ПК1",
        observed_at=PartialDate(2021, 3, None, DatePrecision.MONTH),
        histories=(history,),
        observation_location=location,
    )

    assert after_boundary.stage is not None
    assert after_boundary.stage.event_kind is WellEventKind.ZBS
    assert after_boundary.issue is None
    assert boundary_month.stage is not None
    assert boundary_month.stage.event_kind is WellEventKind.INITIAL
    assert boundary_month.issue is None


def test_mzs_does_not_inherit_parent_launch_history() -> None:
    resolution = resolve_lifecycle_stage(
        _fund("051_МЗС"), _record("51_МЗС", datetime(2024, 5, 1)), (_history(),)
    )

    assert resolution.stage is None
    assert resolution.issue is None


def test_gs_and_mzs_only_match_their_own_history_identity() -> None:
    root_history = _history()
    branch_stage = replace(
        root_history.stages[0],
        target_well_id="51_ГС",
        source_display_well="051_ГС",
    )
    gas_history = WellHistory(
        root_history.field_name,
        root_history.physical_root,
        "051_ГС",
        root_history.events,
        (branch_stage,),
    )
    mzs_stage = replace(
        branch_stage,
        target_well_id="51_МЗС",
        source_display_well="051_МЗС",
    )
    mzs_history = replace(gas_history, source_display_well="051_МЗС", stages=(mzs_stage,))

    gas = resolve_lifecycle_stage(
        _fund("051_ГС"), _record("51_ГС", datetime(2024, 5, 1)), (root_history, gas_history)
    )
    mzs = resolve_lifecycle_stage(
        _fund("051_МЗС"), _record("51_МЗС", datetime(2024, 5, 1)), (root_history, mzs_history)
    )

    assert gas.stage == branch_stage
    assert mzs.stage == mzs_stage


def test_pvr_and_klk_do_not_create_lifecycle_boundaries() -> None:
    history = _history()
    events = tuple(
        replace(
            history.events[0],
            event_kind=kind,
            event_label=kind.value,
            event_date=PartialDate(2022 + index, 1, 1, DatePrecision.DAY),
        )
        for index, kind in enumerate((WellEventKind.PVR, WellEventKind.KLK))
    )
    modified = replace(history, events=(*history.events, *events))

    pvr = resolve_lifecycle_stage(_fund("051"), _record("51", datetime(2022, 2, 1)), (modified,))
    klk = resolve_lifecycle_stage(
        _fund("051", "ПК2"), _record("51", datetime(2024, 2, 1), "ПК2"), (modified,)
    )

    assert len(modified.stages) == 3
    assert pvr.stage == history.stages[1]
    assert klk.stage == history.stages[2]


@pytest.mark.parametrize("boundary", [WellEventKind.PVLG, WellEventKind.PNLG])
def test_current_plast_resolves_latest_pvlg_pnlg_stage_without_gdi(
    boundary: WellEventKind,
) -> None:
    history = _history()
    latest = replace(history.stages[-1], event_kind=boundary)
    modified = replace(history, stages=(*history.stages[:-1], latest))

    resolution = resolve_lifecycle_stage(_fund("051", "ПК2"), None, (modified,))

    assert resolution.issue is None
    assert resolution.stage == latest
    assert resolution.stage.event_kind is boundary


def test_current_zbs_stage_resolves_without_new_gdi() -> None:
    history = _history()
    zbs = history.stages[1]
    modified = replace(history, stages=history.stages[:2])

    resolution = resolve_lifecycle_stage(_fund("051_ЗБС", "ПК1"), None, (modified,))

    assert resolution.issue is None
    assert resolution.stage == zbs


def test_current_plast_does_not_resolve_to_previous_stage_when_latest_plast_differs() -> None:
    resolution = resolve_lifecycle_stage(_fund("051", "ПК1"), None, (_history(),))

    assert resolution.stage is None
    assert resolution.issue is not None
    assert resolution.issue.code == "WELL_HISTORY_STAGE_AMBIGUOUS"
    assert SourceLocation("history.xlsx", "БЛУ", "I5") in resolution.issue.locations


def test_real_current_stage_tie_remains_ambiguous() -> None:
    history = _history()
    competing = replace(
        history.stages[-1],
        event_kind=WellEventKind.PNLG,
        source_location=SourceLocation("history.xlsx", "БЛУ", "I6"),
    )
    modified = replace(history, stages=(*history.stages, competing))

    resolution = resolve_lifecycle_stage(_fund("051", "ПК2"), None, (modified,))

    assert resolution.stage is None
    assert resolution.issue is not None
    assert resolution.issue.code == "WELL_HISTORY_STAGE_AMBIGUOUS"
    assert SourceLocation("history.xlsx", "БЛУ", "I5") in resolution.issue.locations
    assert SourceLocation("history.xlsx", "БЛУ", "I6") in resolution.issue.locations


def test_same_month_stage_boundary_uses_first_day_defaulting() -> None:
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

    assert resolution.stage == ambiguous
    assert resolution.issue is None


def test_sequential_zbs_names_map_to_deterministic_stage_ordinals() -> None:
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

    first = resolve_lifecycle_stage(
        _fund("051_ЗБС"), _record("51_ЗБС", datetime(2021, 9, 1)), (modified,)
    )
    second = resolve_lifecycle_stage(
        _fund("051_ЗБС2"), _record("51_ЗБС2", datetime(2022, 9, 1)), (modified,)
    )

    assert first.stage == modified.stages[1]
    assert second.stage == second_zbs
    assert first.issue is None
    assert second.issue is None


def test_numbered_zbs_identity_requires_matching_stage_ordinal() -> None:
    resolution = resolve_lifecycle_stage(
        _fund("051_ЗБС2"), _record("51_ЗБС2", datetime(2024, 5, 1)), (_history(),)
    )

    assert resolution.stage is None
    assert resolution.issue is not None
    assert resolution.issue.code == "WELL_HISTORY_STAGE_NOT_FOUND"
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
