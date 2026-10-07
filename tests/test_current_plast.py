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
    ResearchStatusRecord,
    SourceLocation,
    WellEvent,
    WellEventKind,
    WellHistory,
    WellStage,
)
from gdis_loader.matching.current_plast import resolve_current_plast
from gdis_loader.matching.matcher import GdiIndex, match_fund_well
from gdis_loader.matching.normalize import normalize_field_name, normalize_plast, normalize_well_id
from gdis_loader.service import _gdi_history_for_stage


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
        target_well_id=("51_ЗБС2" if row == 6 else "51_ЗБС")
        if kind in {WellEventKind.ZBS, WellEventKind.PVLG, WellEventKind.PNLG}
        else "51",
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


def _status(
    day: int,
    delta: float | None,
    *,
    row: int,
    research_type: str = "ИД",
    month: int = 1,
    year: int = 2026,
) -> ResearchStatusRecord:
    return ResearchStatusRecord(
        raw_well_name="22",
        base_well_id="22",
        target_well_id="22",
        raw_plast="ПК1",
        normalized_plast="ПК1",
        research_type=research_type,
        study_date=PartialDate(year, month, day, DatePrecision.DAY),
        delta_raw=delta,
        delta_value=delta,
        delta_formula_without_cache=False,
        source_row=row,
        source_file="status.xlsx",
        source_sheet="АР_таблица_БЛУ",
        well_cell=f"A{row}",
        plast_cell=f"B{row}",
        research_type_cell=f"C{row}",
        date_cell=f"D{row}",
        delta_cell=f"J{row}",
    )


@pytest.mark.parametrize("kind", [WellEventKind.INITIAL, WellEventKind.ZBS, WellEventKind.PVLG])
def test_summary_overrides_stale_fund_and_base_within_current_history(kind: WellEventKind) -> None:
    history = _history()
    stage = next(s for s in history.stages if s.event_kind is kind)
    history = replace(
        history, stages=tuple(s for s in history.stages if s.stage_sequence <= stage.stage_sequence)
    )
    well = _fund(stage.target_well_id or "51", "ПК1")
    records = (
        _record(stage.target_well_id or "51", datetime(2025, 1, 1), "ПК3"),
        _record(stage.target_well_id or "51", datetime(2026, 1, 1), "ПК3"),
        _record("51", datetime(2011, 1, 1), "ПК1"),
    )
    index = GdiIndex(records)
    current = resolve_current_plast(well, index, (history,))
    assert current.issue.code == "SUMMARY_GDI_CURRENT_PLAST_SELECTED"
    assert current.well.object_plast_hint == "ПК3"
    match = match_fund_well(current.well, index, current.histories)
    assert match.record == records[1]
    stage = current.histories[0].stages[-1]
    assert (
        _gdi_history_for_stage(current.well, records, current.histories, stage, "ПК3")
        == records[:2]
    )


def test_equal_latest_plasts_are_ambiguous() -> None:
    records = (
        _record("51_ЗБС", datetime(2026, 1, 1), "ПК3"),
        _record("51_ЗБС", datetime(2026, 1, 1), "ПК4"),
    )
    current = resolve_current_plast(_fund("51_ЗБС"), GdiIndex(records), (_history(),))
    assert current.ambiguous
    assert current.issue.code == "SUMMARY_GDI_CURRENT_PLAST_AMBIGUOUS"


def test_no_summary_preserves_diagnosed_fallback() -> None:
    well = _fund("51_ЗБС", "ПК2")
    history = _history()
    current = resolve_current_plast(well, GdiIndex(()), (history,))
    assert current.well == well
    assert current.histories == (history,)
    assert current.issue.code == "SUMMARY_GDI_CURRENT_PLAST_NOT_FOUND"


def test_previous_lifecycle_cannot_supply_current_plast() -> None:
    old = _record("51", datetime(2011, 1, 1), "ПК9")
    current = resolve_current_plast(_fund("51_ЗБС", "ПК2"), GdiIndex((old,)), (_history(),))
    assert current.issue.code == "SUMMARY_GDI_CURRENT_PLAST_NOT_FOUND"


def test_canonical_plast_is_shared_by_count_and_historical_delta() -> None:
    from datetime import date

    from gdis_loader.domain.models import FundParseResult, LoadReport
    from gdis_loader.readers.lha import LhaIndex
    from gdis_loader.service import _build_target_rows

    well = _fund("51_ЗБС", "ПК1")
    history = _history()
    records = (
        _record("51_ЗБС", datetime(2025, 1, 1), "ПК3"),
        _record("51_ЗБС", datetime(2026, 1, 1), "ПК3"),
    )
    valid = replace(
        _status(1, 0.0, row=1, year=2025),
        raw_well_name="51_ЗБС",
        target_well_id="51_ЗБС",
        base_well_id="51",
        normalized_plast="ПК3",
        raw_plast="ПК3",
    )
    assert valid.study_date is not None
    invalid = replace(
        valid,
        delta_value=None,
        delta_raw="-",
        study_date=replace(valid.study_date, year=2026),
        source_row=2,
    )
    other = replace(
        valid,
        normalized_plast="ПК1",
        study_date=replace(valid.study_date, year=2026),
        source_row=3,
        delta_value=100.0,
    )
    report = LoadReport("now", "0.22", "3.14", {}, target_field="Береговое")
    rows = _build_target_rows(
        FundParseResult((well,), well.fund_date, "fund"),
        GdiIndex(records),
        LhaIndex(()),
        report,
        (history,),
        date(2026, 8, 1),
        (other, invalid, valid),
    )
    assert rows[0].plast == "ПК3"
    assert rows[0].gdi_count == 2
    assert rows[0].gdm_problems == "Нет"
    assert report.gdm_fallback_selected == 1
    assert any(i.code == "GDM_DIFFERENT_PLAST_REJECTED" for i in report.issues)


def test_ambiguous_summary_blocks_plast_sensitive_outputs() -> None:
    from datetime import date

    from gdis_loader.domain.models import FundParseResult, LoadReport
    from gdis_loader.readers.lha import LhaIndex
    from gdis_loader.service import _build_target_rows

    well = _fund("51_ЗБС")
    records = (
        _record("51_ЗБС", datetime(2026, 1, 1), "ПК3"),
        _record("51_ЗБС", datetime(2026, 1, 1), "ПК4"),
    )
    report = LoadReport("now", "0.22", "3.14", {}, target_field="Береговое")
    rows = _build_target_rows(
        FundParseResult((well,), well.fund_date, "fund"),
        GdiIndex(records),
        LhaIndex(()),
        report,
        (_history(),),
        date(2026, 8, 1),
    )
    assert report.ambiguous == 1
    assert rows[0].plast is None
    assert rows[0].gdi_count is None
    assert rows[0].gdm_problems is None


def test_summary_resolves_missing_base_stage_plast() -> None:
    history = _history()
    history = replace(
        history,
        stages=tuple(
            replace(s, plast=None) if s == history.stages[-1] else s for s in history.stages
        ),
    )
    record = _record("51_ЗБС", datetime(2026, 1, 1), "ПК3")
    current = resolve_current_plast(_fund("51_ЗБС"), GdiIndex((record,)), (history,))
    assert current.well.object_plast_hint == "ПК3"
    assert current.histories[0].stages[-1].plast == "ПК3"
    assert current.original_history_plast is None
