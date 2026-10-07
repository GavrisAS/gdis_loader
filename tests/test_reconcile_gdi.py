from __future__ import annotations

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
    WellEventKind,
    WellHistory,
    WellStage,
)
from gdis_loader.matching.normalize import normalize_field_name
from gdis_loader.validation.reconciliation import (
    application_count_state,
    current_lifecycle_counts,
)


@pytest.mark.parametrize(
    ("application_count", "expected_count", "state"),
    (
        (0, 1, "mismatch"),
        (0, 0, "match"),
        (None, 0, "missing"),
    ),
)
def test_application_count_state_preserves_numeric_zero(
    application_count: int | None,
    expected_count: int,
    state: str,
) -> None:
    assert application_count_state(application_count, expected_count) == state


def test_current_pvlg_count_uses_unique_fund_history_identities_without_gdi() -> None:
    roots = ("54", "10803", "10601")
    wells = tuple(
        FundWell(
            raw_display=root,
            base_well_id=root,
            field_name="Береговое",
            normalized_field=normalize_field_name("Береговое"),
            object_name="Береговое (ПК2)",
            source_category=FundCategory.PRODUCING,
            fund_date=date(2026, 8, 1),
            source_row=index,
            source_column="C",
            object_plast_hint="ПК2",
        )
        for index, root in enumerate((*roots, roots[0]), start=3)
    )
    histories = tuple(
        WellHistory(
            field_name="Береговое",
            physical_root=root,
            source_display_well=root,
            events=(),
            stages=(
                WellStage(
                    field_name="Береговое",
                    physical_root=root,
                    source_display_well=root,
                    target_well_id=None,
                    plast="ПК2",
                    event_kind=WellEventKind.PVLG,
                    started_at=PartialDate(2023, 6, 1, DatePrecision.DAY),
                    stage_sequence=1,
                    source_location=SourceLocation("history.xlsx", "БЛУ", f"O{index}"),
                    raw_block=(),
                ),
            ),
        )
        for index, root in enumerate(roots, start=3)
    )

    counts = current_lifecycle_counts(wells, histories, "Береговое")

    assert counts["current_pvlg_identities"] == 3
    assert counts["current_pvlg_rows"] == 4
    assert counts["resolved_current_lifecycle_rows"] == 4


def test_current_pvlg_crosscheck_counts_roots_and_excludes_old_zbs_identity() -> None:
    roots = ("54", "10803", "10601", "10302")
    fund_wells = tuple(
        FundWell(
            raw_display=root,
            base_well_id=root,
            field_name="Береговое",
            normalized_field=normalize_field_name("Береговое"),
            object_name="Береговое (ПК9+17)",
            source_category=FundCategory.PRODUCING,
            fund_date=date(2026, 8, 1),
            source_row=index,
            source_column="C",
            object_plast_hint="ПК9+17",
        )
        for index, root in enumerate(roots, start=3)
    )
    histories = tuple(
        WellHistory(
            field_name="Береговое",
            physical_root=root,
            source_display_well=root,
            events=(),
            stages=(
                WellStage(
                    field_name="Береговое",
                    physical_root=root,
                    source_display_well=root,
                    target_well_id=root,
                    plast="ПК1",
                    event_kind=WellEventKind.INITIAL,
                    started_at=PartialDate(2010, 1, 1, DatePrecision.DAY),
                    stage_sequence=0,
                    source_location=SourceLocation("history.xlsx", "БЛУ", f"C{index}"),
                    raw_block=(),
                ),
                WellStage(
                    field_name="Береговое",
                    physical_root=root,
                    source_display_well=root,
                    target_well_id=None,
                    plast="ПК14",
                    event_kind=WellEventKind.PVLG,
                    started_at=PartialDate(2024, 1, 1, DatePrecision.DAY),
                    stage_sequence=1,
                    source_location=SourceLocation("history.xlsx", "БЛУ", f"O{index}"),
                    raw_block=(),
                ),
            ),
        )
        for index, root in enumerate(roots, start=3)
    )
    gdi_records = tuple(
        GdiRecord(
            raw_field_name="Береговое",
            normalized_field=normalize_field_name("Береговое"),
            raw_well_name=(root if root != "10302" else "10302_ЗБС"),
            base_well_id=root,
            raw_plast="ПК14",
            normalized_plast="ПК14",
            research_type="КВД",
            study_date=datetime(2025, 1, 1),
            rfp_result=None,
            lnd_reliability=None,
            gtm_date=None,
            source_row=index,
            target_well_id=(root if root != "10302" else "10302_ЗБС"),
            gdi_kind=GdiKind.KVD,
        )
        for index, root in enumerate(roots, start=100)
    )

    counts = current_lifecycle_counts(
        fund_wells,
        histories,
        "Береговое",
        gdi_records,
        date(2026, 10, 2),
    )

    assert counts["current_pvlg_identities"] == 3
    assert counts["current_pvlg_rows"] == 3
    assert counts["gdi_crosschecked_current_lifecycle_rows"] == 3
    assert counts["ambiguous_current_lifecycle_rows"] == 1
    assert counts["resolved_current_lifecycle_rows"] == 3
