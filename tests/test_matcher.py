from __future__ import annotations

from datetime import date, datetime

from gdis_loader.domain.models import (
    DatePrecision,
    FundCategory,
    FundWell,
    GdiKind,
    GdiRecord,
    MatchStatus,
    PartialDate,
    SourceLocation,
    WellEventKind,
    WellHistory,
    WellStage,
)
from gdis_loader.matching.matcher import GdiIndex, match_fund_well
from gdis_loader.matching.normalize import normalize_field_name, normalize_plast, normalize_well_id


def _fund(*, well: str = "011", field: str = "Береговой", hint: str | None = "ПК1") -> FundWell:
    return FundWell(
        raw_display=well,
        base_well_id="11",
        field_name=field,
        normalized_field=normalize_field_name(field),
        target_well_id=normalize_well_id(well).target_well_id,
        object_name=f"{field} ({hint or 'АТ8-9'})",
        source_category=FundCategory.PRODUCING,
        fund_date=date(2026, 8, 1),
        source_row=12,
        source_column="C",
        object_plast_hint=hint,
    )


def _record(
    *,
    well: str = "11",
    plast: str = "ПК-1",
    when: datetime = datetime(2026, 7, 1),
    field: str = "Береговое",
) -> GdiRecord:
    return GdiRecord(
        raw_field_name=field,
        normalized_field=normalize_field_name(field),
        raw_well_name=well,
        base_well_id="11",
        raw_plast=plast,
        normalized_plast=normalize_plast(plast),
        research_type="ИД+КВД",
        study_date=when,
        rfp_result=None,
        lnd_reliability=None,
        gtm_date=None,
        source_row=2,
        target_well_id=normalize_well_id(well).target_well_id,
        gdi_kind=GdiKind.ID_KVD,
    )


def test_exact_single_match() -> None:
    result = match_fund_well(_fund(), GdiIndex([_record()]))

    assert result.status is MatchStatus.MATCHED
    assert result.record is not None
    assert result.record.raw_well_name == "11"


def test_latest_date_wins_for_same_completion() -> None:
    old = _record(when=datetime(2024, 1, 1))
    latest = _record(well="11_ЗБС", when=datetime(2026, 7, 20))

    result = match_fund_well(_fund(well="011_ЗБС", hint=None), GdiIndex([old, latest]))

    assert result.status is MatchStatus.MATCHED
    assert result.record is not None
    assert result.record.raw_well_name == "11_ЗБС"


def test_parent_does_not_match_a_gdi_zbs_lifecycle_by_physical_root() -> None:
    result = match_fund_well(
        _fund(well="011", hint=None),
        GdiIndex([_record(well="11_ЗБС")]),
    )

    assert result.status is MatchStatus.AMBIGUOUS


def test_base_fund_resolves_zbs_gdi_only_through_confirmed_history() -> None:
    stage = WellStage(
        field_name="Береговое",
        physical_root="11",
        source_display_well="011",
        target_well_id=None,
        plast="ПК1",
        event_kind=WellEventKind.ZBS,
        started_at=PartialDate(2025, 1, 10, DatePrecision.DAY),
        stage_sequence=1,
        source_location=SourceLocation("history.xlsx", "БЛУ", "I8"),
        raw_block=(),
    )
    history = WellHistory("Береговое", "11", "011", (), (stage,))

    result = match_fund_well(
        _fund(well="011", hint=None),
        GdiIndex([_record(well="11_ЗБС", when=datetime(2026, 7, 20))]),
        (history,),
    )

    assert result.status is MatchStatus.MATCHED
    assert result.record is not None
    assert result.record.target_well_id == "11_ЗБС"


def test_gdi_cutoff_uses_injected_calculation_date() -> None:
    after_fund = _record(when=datetime(2026, 8, 20))

    assert match_fund_well(_fund(), GdiIndex([after_fund])).status is MatchStatus.NO_GDI
    assert (
        match_fund_well(_fund(), GdiIndex([after_fund], date(2026, 8, 31))).status
        is MatchStatus.MATCHED
    )


def test_object_hint_selects_current_plast_without_fuzzy_matching() -> None:
    old_plast = _record(plast="ПК-1", when=datetime(2026, 7, 20))
    current_plast = _record(plast="ПК-19-20", when=datetime(2026, 7, 1))

    result = match_fund_well(_fund(hint="ПК19-20"), GdiIndex([old_plast, current_plast]))

    assert result.status is MatchStatus.MATCHED
    assert result.record is not None
    assert result.record.normalized_plast == "ПК19-20"


def test_same_latest_date_with_incompatible_completions_is_ambiguous() -> None:
    records = [
        _record(well="11", plast="ПК-1", when=datetime(2026, 7, 20)),
        _record(well="11", plast="ПК-19-20", when=datetime(2026, 7, 20)),
    ]

    result = match_fund_well(_fund(hint=None), GdiIndex(records))

    assert result.status is MatchStatus.AMBIGUOUS
    assert len(result.candidates) == 2
    assert "несколько" in result.explanation


def test_no_gdi_and_different_field_do_not_match() -> None:
    assert match_fund_well(_fund(), GdiIndex([])).status is MatchStatus.NO_GDI
    assert (
        match_fund_well(_fund(), GdiIndex([_record(field="Пырейное")])).status is MatchStatus.NO_GDI
    )
