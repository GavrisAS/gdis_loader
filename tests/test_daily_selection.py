from __future__ import annotations

from datetime import date

from gdis_loader.domain.models import DailyTelemetryRow, FundCategory, FundWell
from gdis_loader.matching.normalize import normalize_field_name
from gdis_loader.service import _daily_record_for_target


def _fund(field: str, *, number: str = "22") -> FundWell:
    return FundWell(
        raw_display=number,
        base_well_id=number,
        target_well_id=number,
        field_name=field,
        normalized_field=normalize_field_name(field),
        object_name=field,
        source_category=FundCategory.PRODUCING,
        fund_date=date(2026, 8, 1),
        source_row=1,
        source_column="C",
    )


def _daily(
    number: str,
    field: str | None,
    *,
    row: int,
    value: float,
) -> DailyTelemetryRow:
    return DailyTelemetryRow(
        raw_field_name=field,
        raw_well_name=number,
        base_well_id=number,
        target_well_id=number,
        source_row=row,
        daily_values=(value,),
        source_file="daily.xlsm",
        source_sheet="Добыча телеметрия",
        field_cell=f"A{row}",
        well_cell=f"B{row}",
    )


def test_daily_selection_requires_same_well_and_selected_field() -> None:
    fund = _fund("Береговое")
    correct = _daily("22", "Береговое", row=10, value=100.0)
    wrong_field = _daily("22", "Пырейное", row=11, value=1000.0)
    wrong_well = _daily("23", "Береговое", row=12, value=2000.0)

    selected, issue = _daily_record_for_target(
        fund,
        "22",
        (fund,),
        (correct, wrong_field, wrong_well),
    )

    assert selected == correct
    assert issue is None


def test_daily_row_without_field_is_ambiguous_when_root_exists_in_two_fields() -> None:
    beregovoe = _fund("Береговое")
    pyreinoe = _fund("Пырейное")
    unspecified_field_row = _daily("22", None, row=10, value=100.0)

    selected, issue = _daily_record_for_target(
        beregovoe,
        "22",
        (beregovoe, pyreinoe),
        (unspecified_field_row,),
    )

    assert selected is None
    assert issue == "DEBIT_SOURCE_FIELD_AMBIGUOUS"


def test_conflicting_candidates_within_same_field_remain_blank() -> None:
    fund = _fund("Береговое")
    rows = (_daily("22", "Береговое", row=10, value=1), _daily("22", "Береговое", row=11, value=2))
    for candidates in (rows, rows[::-1]):
        selected, issue = _daily_record_for_target(fund, "22", (fund,), candidates)
        assert selected is None and issue == "DEBIT_SOURCE_ROW_AMBIGUOUS"


def test_suffix_mismatch_does_not_use_another_branch() -> None:
    fund = _fund("Береговое")
    for target in ("22_ЗБС", "22_ГС", "22_МЗС", "22_UNKNOWN"):
        wrong = _daily("22_ЗБС2", "Береговое", row=10, value=99)
        selected, issue = _daily_record_for_target(fund, target, (fund,), (wrong,))
        assert selected is None and issue == "DEBIT_SOURCE_ROW_MISSING"
    mother = _daily("22", "Береговое", row=11, value=99)
    for target in ("22_ГС", "22_МЗС", "22_UNKNOWN"):
        assert _daily_record_for_target(fund, target, (fund,), (mother,))[0] is None


def test_unproven_dated_scope_never_uses_unique_fund_as_field_evidence() -> None:
    from dataclasses import replace

    fund = _fund("Береговое")
    unknown = replace(_daily("22", None, row=10, value=99), field_scope_invalid=True)
    assert _daily_record_for_target(fund, "22", (fund,), (unknown,)) == (
        None,
        "DEBIT_SOURCE_FIELD_UNPROVEN",
    )


def test_multiple_current_fund_identities_forbid_mother_fallback() -> None:
    from dataclasses import replace

    fund = _fund("Береговое")
    branch = replace(fund, target_well_id="22_ЗБС")
    mother = _daily("22", "Береговое", row=10, value=99)
    assert _daily_record_for_target(branch, "22_ЗБС", (fund, branch), (mother,))[0] is None


def test_exact_lifecycle_source_is_rejected_if_branch_started_after_report_month() -> None:
    from dataclasses import replace

    from gdis_loader.domain.dates import PartialDate
    from gdis_loader.domain.models import (
        DatePrecision,
        SourceLocation,
        WellEventKind,
        WellStage,
    )

    fund = _fund("Береговое", number="22_ЗБС")
    source = _daily("22_ЗБС", "Береговое", row=10, value=99)
    stage = WellStage(
        field_name="Береговое",
        physical_root="22",
        source_display_well="22",
        target_well_id="22_ЗБС",
        plast="ПК1",
        event_kind=WellEventKind.ZBS,
        started_at=PartialDate(2026, 10, None, DatePrecision.MONTH),
        stage_sequence=1,
        source_location=SourceLocation("history.xlsx", "БЛУ", "I22"),
        raw_block=(),
    )
    source = replace(source, report_month="2026-09")

    selected, issue = _daily_record_for_target(fund, "22_ЗБС", (fund,), (source,), stage=stage)

    assert selected is None
    assert issue == "DEBIT_SOURCE_LIFECYCLE_PERIOD_MISMATCH"
