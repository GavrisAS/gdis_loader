from __future__ import annotations

from datetime import date

import pytest

from gdis_loader.domain.models import (
    DatePrecision,
    FundCategory,
    FundWell,
    PartialDate,
    ResearchStatusRecord,
    SourceLocation,
    WellEventKind,
    WellHistory,
    WellStage,
)
from gdis_loader.matching.normalize import normalize_field_name, normalize_well_id
from gdis_loader.service import (
    _effective_target_identity,
    _source_lookup_identity,
    _status_candidates_for_target,
)
from gdis_loader.transforms.research_status import select_gdm_delta


def _stage(kind: WellEventKind, identity: str, start: date, row: int, plast: str) -> WellStage:
    return WellStage(
        field_name="Береговое",
        physical_root="22",
        source_display_well="022",
        target_well_id=identity,
        plast=plast,
        event_kind=kind,
        started_at=PartialDate(start.year, start.month, start.day, DatePrecision.DAY),
        stage_sequence=row,
        source_location=SourceLocation("history.xlsx", "БЛУ", f"I{row}"),
        raw_block=(),
    )


def _status(
    well: str,
    plast: str,
    kind: str,
    observed: date,
    delta: float,
    row: int,
) -> ResearchStatusRecord:
    identity = normalize_well_id(well)
    return ResearchStatusRecord(
        raw_well_name=well,
        base_well_id=identity.base_well_id,
        target_well_id=identity.target_well_id,
        raw_plast=plast,
        normalized_plast=plast,
        research_type=kind,
        study_date=PartialDate(observed.year, observed.month, observed.day, DatePrecision.DAY),
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


def test_gdm_uses_current_lifecycle_and_plast_but_all_research_types() -> None:
    initial = _stage(WellEventKind.INITIAL, "22", date(2020, 1, 1), 3, "ПК1")
    zbs = _stage(WellEventKind.ZBS, "22_ЗБС", date(2023, 6, 1), 4, "ПК1")
    history = WellHistory("Береговое", "22", "022", (), (initial, zbs))
    fund_well = FundWell(
        raw_display="22_ЗБС",
        base_well_id="22",
        target_well_id="22_ЗБС",
        field_name="Береговое",
        normalized_field=normalize_field_name("Береговое"),
        object_name="Береговое (ПК1)",
        source_category=FundCategory.PRODUCING,
        fund_date=date(2026, 8, 1),
        source_row=7,
        source_column="C",
        object_plast_hint="ПК1",
    )
    old_lifecycle = _status("22_ЗБС", "ПК1", "ИД", date(2022, 12, 1), 100.0, 10)
    current_other_type = _status("22", "ПК1", "Освоение", date(2024, 1, 1), 6.0, 11)
    other_plast = _status("22", "ПК2", "КВД", date(2025, 1, 1), 100.0, 12)

    selected, issues = _status_candidates_for_target(
        fund_well,
        "22_ЗБС",
        "ПК1",
        zbs,
        (old_lifecycle, current_other_type, other_plast),
        (history,),
    )

    assert selected == (current_other_type,)
    assert any(issue.code == "UNRESOLVED_PLAST_EQUIVALENCE" for issue in issues)
    result = select_gdm_delta(selected, fallback_max_age_days=365)
    assert result.record == current_other_type
    assert result.record.research_type == "Освоение"


def test_pvlg_source_suffix_keeps_gdm_lookup_on_pvlg_history() -> None:
    initial = _stage(WellEventKind.INITIAL, "22", date(2020, 1, 1), 3, "ПК1")
    pvlg = _stage(WellEventKind.PVLG, "22", date(2023, 6, 1), 4, "ПК2")
    pnlg = _stage(WellEventKind.PNLG, "22", date(2025, 1, 1), 5, "ПК2")
    history = WellHistory("Береговое", "22", "022", (), (initial, pvlg, pnlg))
    fund_well = FundWell(
        raw_display="22_ПВЛГ",
        base_well_id="22",
        target_well_id="22_ПВЛГ",
        field_name="Береговое",
        normalized_field=normalize_field_name("Береговое"),
        object_name="Береговое (ПК2)",
        source_category=FundCategory.PRODUCING,
        fund_date=date(2026, 8, 1),
        source_row=7,
        source_column="C",
        object_plast_hint="ПК2",
    )
    display_identity = _effective_target_identity(fund_well, None, pvlg)
    lookup_identity = _source_lookup_identity(fund_well, None, pvlg)
    pvlg_status = _status("22_ПВЛГ", "ПК2", "ИД", date(2024, 1, 1), 6.0, 10)
    root_only_status = _status("22", "ПК2", "Освоение", date(2024, 2, 1), 7.0, 11)
    later_history_status = _status("22_ПВЛГ", "ПК2", "ИД", date(2025, 7, 1), 100.0, 12)

    selected, issues = _status_candidates_for_target(
        fund_well,
        lookup_identity or "",
        "ПК2",
        pvlg,
        (pvlg_status, root_only_status, later_history_status),
        (history,),
    )

    assert display_identity == "22"
    assert lookup_identity == "22_ПВЛГ"
    assert selected == (pvlg_status, root_only_status)
    assert not issues


def test_explicit_gdm_ordinal_is_not_blocked_by_newer_sibling() -> None:
    first = _stage(WellEventKind.ZBS, "22_ЗБС", date(2021, 1, 1), 4, "ПК15")
    second = _stage(WellEventKind.ZBS, "22_ЗБС2", date(2022, 1, 1), 5, "ПК16")
    history = WellHistory("Береговое", "22", "022", (), (first, second))
    fund = FundWell(
        raw_display="22_ЗБС",
        base_well_id="22",
        target_well_id="22_ЗБС",
        field_name="Береговое",
        normalized_field=normalize_field_name("Береговое"),
        object_name="Береговой (ПК9-17)",
        source_category=FundCategory.PRODUCING,
        fund_date=date(2026, 8, 1),
        source_row=2,
        source_column="C",
    )
    delta = _status("22_ЗБС", "ПК15", "ИД", date(2024, 1, 1), 0.0, 10)
    selected, issues = _status_candidates_for_target(
        fund, "22_ЗБС", "ПК15", first, (delta,), (history,)
    )
    assert selected == (delta,)
    assert not issues


def test_no_separator_gdm_identity_recovers_nearest_valid_delta() -> None:
    from dataclasses import replace

    from gdis_loader.transforms.research_status import gdm_problem

    initial = _stage(WellEventKind.INITIAL, "22", date(2020, 1, 1), 3, "ПК1")
    zbs = _stage(WellEventKind.ZBS, "22_ЗБС", date(2022, 12, 1), 4, "ПК1")
    history = WellHistory("Береговое", "22", "022", (), (initial, zbs))
    fund = FundWell(
        raw_display="22_ЗБС",
        base_well_id="22",
        target_well_id="22_ЗБС",
        field_name="Береговое",
        normalized_field="береговое",
        object_name="Береговое (ПК1)",
        source_category=FundCategory.PRODUCING,
        fund_date=date(2026, 8, 1),
        source_row=7,
        source_column="C",
        object_plast_hint="ПК1",
    )
    older = _status("22_ЗБС", "ПК1", "КВД", date(2024, 3, 15), -0.44, 10)
    nearest = _status("22збс", "ПК1", "КВД", date(2025, 2, 28), -1.35, 11)
    latest = replace(
        _status("22", "ПК1", "КВД", date(2025, 8, 30), 0, 12), delta_raw=None, delta_value=None
    )
    candidates, issues = _status_candidates_for_target(
        fund,
        "22_ЗБС",
        "ПК1",
        zbs,
        (older, nearest, latest),
        (history,),
    )
    assert not issues
    selected = select_gdm_delta(candidates, fallback_max_age_days=365)
    assert selected.record == nearest
    assert selected.latest_relevant == latest
    assert selected.age_days == 183
    assert selected.fallback
    assert selected.record.delta_value is not None
    assert not gdm_problem(selected.record.delta_value, abs_delta_threshold=5)


@pytest.mark.parametrize(
    "well,eligible",
    [
        ("22_ЗБС", False),
        ("22_ЗБС1", False),
        ("22_ЗБС2", False),
        ("22_ЗБС3", True),
        ("22_ЗБС_МГРП", True),
        ("22збс_МГРП", True),
        ("22_ГС", False),
        ("22_МЗС", False),
    ],
)
def test_gdm_family_resolution_preserves_explicit_ordinals(well: str, eligible: bool) -> None:
    stages = tuple(
        _stage(
            WellEventKind.ZBS, "22_ЗБС" + (str(i) if i > 1 else ""), date(2020 + i, 1, 1), i, "ПК19"
        )
        for i in range(1, 4)
    )
    history = WellHistory("Береговое", "22", "022", (), stages)
    fund = FundWell(
        "22_ЗБС3",
        "22",
        "Береговое",
        "береговое",
        "Береговое (ПК19)",
        FundCategory.PRODUCING,
        date(2026, 8, 1),
        7,
        "C",
        target_well_id="22_ЗБС3",
        object_plast_hint="ПК19",
    )
    row = _status(well, "ПК19", "КВД", date(2024, 1, 1), 0.0, 10)
    candidates, _ = _status_candidates_for_target(
        fund, "22_ЗБС3", "ПК19", stages[-1], (row,), (history,)
    )
    assert bool(candidates) == eligible
    if eligible:
        assert select_gdm_delta(candidates, fallback_max_age_days=365).record == row


def test_10201_annotated_gdm_resolves_zbs3_and_inherited_pvlg() -> None:
    from dataclasses import replace

    first = replace(
        _stage(WellEventKind.ZBS, "10201_ЗБС", date(2023, 1, 1), 1, "ПК19"), physical_root="10201"
    )
    second = replace(
        first,
        target_well_id="10201_ЗБС2",
        stage_sequence=2,
        started_at=PartialDate(2024, 1, 1, DatePrecision.DAY),
    )
    third = replace(
        second,
        target_well_id="10201_ЗБС3",
        stage_sequence=3,
        started_at=PartialDate(2025, 1, 1, DatePrecision.DAY),
    )
    pvlg = replace(
        third,
        event_kind=WellEventKind.PVLG,
        stage_sequence=4,
        started_at=PartialDate(2026, 1, 1, DatePrecision.DAY),
    )
    history = WellHistory("Береговое", "10201", "10201", (), (first, second, third, pvlg))
    fund = FundWell(
        "10201_ЗБС3",
        "10201",
        "Береговое",
        "береговое",
        "Береговое (ПК19)",
        FundCategory.PRODUCING,
        date(2026, 8, 1),
        7,
        "C",
        target_well_id="10201_ЗБС3",
        object_plast_hint="ПК19",
    )
    before = _status("10201_ЗБС_МГРП", "ПК19", "КВД", date(2025, 6, 1), 6, 10)
    after = _status("10201збс_МГРП", "ПК19", "КВД", date(2026, 6, 1), 0, 11)
    for stage, expected in ((third, before), (pvlg, after)):
        candidates, _ = _status_candidates_for_target(
            fund, "10201_ЗБС3", "ПК19", stage, (before, after), (history,)
        )
        assert candidates == (expected,)
        assert select_gdm_delta(candidates, fallback_max_age_days=365).record == expected
