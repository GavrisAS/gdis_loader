from __future__ import annotations

from datetime import date, datetime

from gdis_loader.domain.models import FundCategory, FundWell, GdiRecord, MatchStatus
from gdis_loader.matching.matcher import GdiIndex, match_fund_well
from gdis_loader.matching.normalize import normalize_field_name, normalize_plast


def _fund(*, well: str = "011", field: str = "Береговой", hint: str | None = "ПК1") -> FundWell:
    return FundWell(
        raw_display=well,
        base_well_id="11",
        field_name=field,
        normalized_field=normalize_field_name(field),
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
    )


def test_exact_single_match() -> None:
    result = match_fund_well(_fund(), GdiIndex([_record()]))

    assert result.status is MatchStatus.MATCHED
    assert result.record is not None
    assert result.record.raw_well_name == "11"


def test_latest_date_wins_for_same_completion() -> None:
    old = _record(when=datetime(2024, 1, 1))
    latest = _record(well="11_ЗБС", when=datetime(2026, 7, 20))

    result = match_fund_well(_fund(hint=None), GdiIndex([old, latest]))

    assert result.status is MatchStatus.MATCHED
    assert result.record is not None
    assert result.record.raw_well_name == "11_ЗБС"


def test_object_hint_selects_current_plast_without_fuzzy_matching() -> None:
    old_plast = _record(plast="ПК-1", when=datetime(2026, 7, 20))
    current_plast = _record(plast="ПК-19-20", when=datetime(2026, 7, 1))

    result = match_fund_well(_fund(hint="ПК19-20"), GdiIndex([old_plast, current_plast]))

    assert result.status is MatchStatus.MATCHED
    assert result.record is not None
    assert result.record.normalized_plast == "ПК19-20"


def test_same_latest_date_with_incompatible_completions_is_ambiguous() -> None:
    records = [
        _record(well="11_A", when=datetime(2026, 7, 20)),
        _record(well="11_B", plast="ПК-19-20", when=datetime(2026, 7, 20)),
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
