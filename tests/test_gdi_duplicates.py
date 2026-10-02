from __future__ import annotations

from datetime import datetime

from gdis_loader.domain.models import GdiKind, GdiRecord
from gdis_loader.transforms.gdi import collapse_exact_gdi_duplicates


def _record(
    *,
    row: int,
    depth: float | None = 100.0,
    reliability: str | None = "Высокая",
    a_value: float | None = 0.8,
) -> GdiRecord:
    return GdiRecord(
        raw_field_name="Береговое",
        normalized_field="береговое",
        raw_well_name="322",
        base_well_id="322",
        raw_plast="ПК-1",
        normalized_plast="ПК1",
        research_type="ИД",
        study_date=datetime(2021, 4, 12),
        rfp_result="да",
        lnd_reliability=reliability,
        gtm_date=None,
        source_row=row,
        source_file="gdi.xlsx",
        source_sheet="ГДИС",
        field_cell=f"A{row}",
        well_cell=f"B{row}",
        plast_cell=f"C{row}",
        research_type_cell=f"D{row}",
        date_cell=f"E{row}",
        gdi_kind=GdiKind.ID,
        depth_raw_value=depth,
        depth_value=depth,
        depth_cell=f"N{row}",
        lnd_reliability_cell=f"AW{row}",
        productivity_a_raw=a_value,
        productivity_a_value=a_value,
        productivity_a_cell=f"AA{row}",
    )


def test_exact_gdi_duplicate_collapses_and_merges_source_provenance() -> None:
    collapsed, issues = collapse_exact_gdi_duplicates((_record(row=8), _record(row=9)))

    assert len(collapsed) == 1
    assert collapsed[0].source_rows == (8, 9)
    assert {location.cell for location in collapsed[0].locations} == {
        "A8",
        "B8",
        "C8",
        "E8",
        "A9",
        "B9",
        "C9",
        "E9",
    }
    assert len(issues) == 1
    assert issues[0].code == "GDI_EXACT_DUPLICATE_COLLAPSED"
    assert len(issues[0].locations) == 10


def test_depth_or_lnd_differences_remain_distinct_business_records() -> None:
    records = (
        _record(row=8),
        _record(row=9, depth=101.0),
        _record(row=10, reliability="Низкая"),
    )

    collapsed, issues = collapse_exact_gdi_duplicates(records)

    assert len(collapsed) == 3
    assert issues == ()
