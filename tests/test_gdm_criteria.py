from __future__ import annotations

from gdis_loader.config import CriteriaConfig
from gdis_loader.domain.models import DatePrecision, PartialDate, ResearchStatusRecord
from gdis_loader.transforms.research_status import gdm_problem, select_gdm_delta


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


def test_gdm_positive_negative_and_zero_delta_are_all_valid() -> None:
    records = (
        _status(1, 6.0, row=1),
        _status(2, -6.0, row=2),
        _status(3, 0.0, row=3),
    )

    selected = select_gdm_delta(records, fallback_max_age_days=365)

    assert selected.record == records[-1]
    assert selected.record.delta_value == 0.0
    assert gdm_problem(6.0, 5.0)
    assert gdm_problem(-6.0, 5.0)
    assert not gdm_problem(0.0, 5.0)
    assert not gdm_problem(5.0, 5.0)


def test_gdm_latest_invalid_uses_nearest_valid_without_delta_trend() -> None:
    older = _status(1, 100.0, row=1, research_type="ИД")
    latest_invalid = _status(2, None, row=2, research_type="Освоение")

    selection = select_gdm_delta((older, latest_invalid), fallback_max_age_days=365)

    assert selection.record == older
    assert selection.latest_relevant == latest_invalid
    assert selection.fallback
    assert selection.age_days == 1
    assert selection.record is not None
    assert selection.record.delta_value is not None
    assert gdm_problem(selection.record.delta_value, 5.0)


def test_gdm_fallback_window_is_inclusive_and_configurable() -> None:
    valid = _status(1, 6.0, row=1, year=2025)
    invalid = _status(1, None, row=2, year=2026)

    default_selection = select_gdm_delta(
        (valid, invalid), CriteriaConfig().gdm_fallback_max_age_days
    )
    narrow_selection = select_gdm_delta(
        (valid, invalid), CriteriaConfig(gdm_fallback_max_age_days=30).gdm_fallback_max_age_days
    )

    assert default_selection.record == valid
    assert default_selection.age_days == 365
    assert narrow_selection.record is None
    assert narrow_selection.stale_age_days == 365


def test_gdm_fallback_366_days_old_is_inside_two_year_default_window() -> None:
    old = _status(31, 6.0, row=1, month=12, year=2024)
    latest_invalid = _status(1, None, row=2, month=1, year=2026)

    selection = select_gdm_delta(
        (old, latest_invalid), fallback_max_age_days=CriteriaConfig().gdm_fallback_max_age_days
    )

    assert selection.record == old
    assert selection.age_days == 366


def test_two_year_window_inclusive_and_single_old_numeric_rejected() -> None:
    from datetime import date, timedelta

    anchor = date(2026, 8, 1)
    for age, accepted in ((730, True), (731, False)):
        day = anchor - timedelta(days=age)
        record = _status(day.day, 0.0, row=1, month=day.month, year=day.year)
        selected = select_gdm_delta((record,), 730, reference_date=anchor)
        assert (selected.record is not None) is accepted


def test_two_year_historical_search_skips_invalid_rows() -> None:
    from datetime import date

    old = _status(1, -6.0, row=1, year=2024, month=8)
    middle = _status(1, None, row=2, year=2025, month=8)
    latest = _status(1, None, row=3, year=2026, month=7)
    selected = select_gdm_delta((latest, old, middle), 730, reference_date=date(2026, 7, 1))
    assert selected.record == old
    assert selected.fallback


def test_nonfinite_delta_is_invalid_and_future_is_excluded() -> None:
    from datetime import date

    old = _status(1, 0.0, row=1, year=2025)
    records = (old, _status(1, float("nan"), row=2), _status(2, 8.0, row=3))
    assert select_gdm_delta(records, 730, reference_date=date(2026, 1, 1)).record == old
