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
