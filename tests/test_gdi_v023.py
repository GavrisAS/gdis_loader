from dataclasses import replace
from datetime import date, datetime

import pytest

from gdis_loader.domain.models import DatePrecision, GdiKind, PartialDate
from gdis_loader.matching.current_plast import resolve_current_plast
from gdis_loader.matching.lifecycle import resolve_lifecycle_stage
from gdis_loader.matching.matcher import GdiIndex, match_fund_well
from gdis_loader.matching.normalize import normalize_plast
from gdis_loader.service import _gdi_history_for_stage
from gdis_loader.transforms.aggregates import count_reconciled_gdi
from gdis_loader.transforms.gdi import classify_gdi_kind
from gdis_loader.transforms.gdi_features import downhole_sources, lnd_source, three_year_boundary
from gdis_loader.validation.gdi_audit import audit_gdi_rows
from test_current_plast import _fund, _history, _record  # ty: ignore[unresolved-import]


@pytest.mark.parametrize(
    ("raw", "kind", "id_capability", "pressure"),
    [
        ("КВД", GdiKind.KVD, False, True),
        ("КСД", GdiKind.KSD, False, True),
        ("ИД", GdiKind.ID, True, False),
        ("ИД+КВД", GdiKind.ID_KVD, True, True),
        ("КВД+ИД", GdiKind.ID_KVD, True, True),
        (" квд + ид пояснение", GdiKind.ID_KVD, True, True),
        ("КСД комментарий", GdiKind.KSD, False, True),
        ("МЗС+миниКВД", GdiKind.UNKNOWN, False, False),
    ],
)
def test_classifier_capabilities(
    raw: str, kind: GdiKind, id_capability: bool, pressure: bool
) -> None:
    actual = classify_gdi_kind(raw)
    assert actual == kind
    assert actual.has_id == id_capability
    assert actual.has_pressure == pressure
    row = replace(_record("51", datetime(2026, 1, 1)), gdi_kind=actual)
    assert count_reconciled_gdi((row,)).exact_count == int(actual.valid)


@pytest.mark.parametrize(
    ("plast", "canonical"),
    [
        ("ПК17", "ПК17"),
        ("ПК17-1", "ПК17"),
        ("ПК17-2", "ПК17"),
        ("ПК17-2-1", "ПК17"),
        ("ПК18", "ПК18"),
        ("ПК19-20", "ПК19+20"),
    ],
)
def test_plast_contract(plast: str, canonical: str) -> None:
    assert normalize_plast(plast) == canonical


@pytest.mark.parametrize(
    ("latest", "previous", "expected"),
    [
        (10, 0, True),
        (0, 10, True),
        (None, 10, True),
        (0, 0, False),
        (None, None, False),
        (-2, -1, False),
        ("invalid", 10, True),
    ],
)
def test_downhole_searches_window_not_only_latest(
    latest: object, previous: object, expected: bool
) -> None:
    records = (
        replace(_record("51", datetime(2025, 1, 1)), depth_raw_value=previous),
        replace(_record("51", datetime(2026, 1, 1)), depth_raw_value=latest),
    )
    assert bool(downhole_sources(records, date(2026, 10, 9), 0)) == expected


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        (datetime(2023, 10, 9), True),
        (datetime(2023, 10, 8), False),
        (datetime(2026, 10, 10), False),
    ],
)
def test_downhole_inclusive_calendar_boundary(when: datetime, expected: bool) -> None:
    record = replace(_record("51", when), depth_raw_value=100)
    assert bool(downhole_sources((record,), date(2026, 10, 9), 0)) == expected


def test_calendar_leap_boundary() -> None:
    assert three_year_boundary(date(2024, 2, 29)) == date(2021, 2, 28)
    assert three_year_boundary(date(2026, 10, 9)) == date(2023, 10, 9)


@pytest.mark.parametrize(
    ("latest_rfp", "latest_lnd", "previous_rfp", "previous_lnd", "source", "value"),
    [
        ("да", "высокая", "нет", "низкая", 3, False),
        (None, None, "да", "высокая", 2, False),
        ("invalid", "invalid", "нет", "высокая", 2, True),
        (None, None, None, None, None, None),
        (0, "высокая", "да", "высокая", 3, True),
    ],
)
def test_lnd_latest_then_only_previous(
    latest_rfp: object,
    latest_lnd: str | None,
    previous_rfp: object,
    previous_lnd: str | None,
    source: int | None,
    value: bool | None,
) -> None:
    records = (
        replace(_record("51", datetime(2024, 1, 1)), source_row=1, rfp_result="нет"),
        replace(
            _record("51", datetime(2025, 1, 1)),
            source_row=2,
            rfp_result=previous_rfp,
            lnd_reliability=previous_lnd,
        ),
        replace(
            _record("51", datetime(2026, 1, 1)),
            source_row=3,
            rfp_result=latest_rfp,
            lnd_reliability=latest_lnd,
        ),
    )
    selected, result, fallback = lnd_source(records)
    assert (selected.source_row if selected else None) == source
    assert result is value
    assert fallback == (source == 2)


def test_lnd_same_date_tie_break_independent_of_input_order() -> None:
    first = replace(_record("51", datetime(2026, 1, 1)), source_row=2, rfp_result="нет")
    latest = replace(first, source_row=3, rfp_result=None, lnd_reliability=None)
    assert lnd_source((latest, first)) == lnd_source((first, latest)) == (first, True, True)


@pytest.mark.parametrize("foreign", ["plast", "history"])
def test_features_cannot_borrow_foreign_history_or_plast(foreign: str) -> None:
    history = _history()
    stage = history.stages[-1]
    well = _fund("51", "ПК2")
    latest = replace(
        _record("51", datetime(2026, 1, 1), "ПК2"),
        rfp_result=None,
        lnd_reliability=None,
        depth_raw_value=0,
    )
    positive = replace(
        _record("51", datetime(2024, 1, 1), "ПК3" if foreign == "plast" else "ПК2"),
        depth_raw_value=100,
        rfp_result="нет",
    )
    if foreign == "history":
        positive = replace(positive, study_date=datetime(2023, 5, 31))
    records = _gdi_history_for_stage(well, (positive, latest), (history,), stage, "ПК2")
    assert records == (latest,)
    assert not downhole_sources(records, date(2026, 1, 1), 0)
    assert lnd_source(records) == (None, None, False)


def test_unique_summary_branch_restores_history_without_mixing_root() -> None:
    history = replace(
        _history(),
        events=(),
        stages=(
            replace(
                _history().stages[0],
                plast="ПК17",
                started_at=PartialDate(2023, 12, None, DatePrecision.MONTH),
            ),
        ),
    )
    well = _fund("51", "ПК17")
    root = _record("51", datetime(2020, 1, 1), "ПК1")
    branch = _record("51_ЗБС", datetime(2024, 1, 1), "ПК17-1")
    index = GdiIndex((root, branch), date(2026, 1, 1))
    current = resolve_current_plast(well, index, (history,))
    assert current.issue.code == "SUMMARY_GDI_CURRENT_HISTORY_INFERRED"
    assert not current.ambiguous
    match = match_fund_well(current.well, index, current.histories)
    assert match.record == branch
    stage = resolve_lifecycle_stage(current.well, None, current.histories).stage
    records = _gdi_history_for_stage(
        current.well, index.history_for(well), current.histories, stage, "ПК17"
    )
    assert records == (branch,)
    assert count_reconciled_gdi(records).exact_count == 1
    audit = audit_gdi_rows(
        current.well, index.records, current.histories, stage, date(2026, 1, 1), 0
    )
    assert [r["counted"] for r in audit] == [False, True]


@pytest.mark.parametrize(
    "conflict", ["ordinal", "interleaved_root", "annotation", "same_day_plast"]
)
def test_summary_branch_conflicts_fail_closed(conflict: str) -> None:
    history = replace(
        _history(),
        events=(),
        stages=(
            replace(
                _history().stages[0],
                plast="ПК17",
                started_at=PartialDate(2023, 12, None, DatePrecision.MONTH),
            ),
        ),
    )
    branch = _record("51_ЗБС", datetime(2024, 1, 1), "ПК17")
    other = _record("51_ЗБС2", datetime(2025, 1, 1), "ПК17")
    if conflict == "interleaved_root":
        other = _record("51", datetime(2025, 1, 1), "ПК17")
    elif conflict == "annotation":
        branch = _record("51_ЗБС_ПИЛОТ", datetime(2024, 1, 1), "ПК17")
        other = branch
    elif conflict == "same_day_plast":
        other = _record("51_ЗБС", datetime(2024, 1, 1), "ПК18")
    current = resolve_current_plast(_fund("51", "ПК17"), GdiIndex((branch, other)), (history,))
    assert current.ambiguous


@pytest.mark.parametrize("explicit", [False, True])
def test_prelaunch_unique_branch_not_arbitrary_tolerance(explicit: bool) -> None:
    history = _history()
    if explicit:
        history = replace(history, stages=history.stages[:2], events=())
        identity, plast, when = "51_ЗБС", "ПК1", datetime(2021, 3, 14)
        stage = history.stages[1]
    else:
        history = replace(history, stages=history.stages[:1], events=())
        identity, plast, when = "51", "ПК1", datetime(2009, 12, 31)
        stage = history.stages[0]
    record = _record(identity, when, plast)
    assert resolve_lifecycle_stage(_fund(identity), record, (history,)).stage == stage
    assert count_reconciled_gdi((record,)).exact_count == 1


def test_root_pre_boundary_stays_old_history() -> None:
    history = _history()
    record = _record("51", datetime(2021, 3, 14))
    assert resolve_lifecycle_stage(_fund("51"), record, (history,)).stage == history.stages[0]
    assert (
        _gdi_history_for_stage(_fund("51"), (record,), (history,), history.stages[1], "ПК1") == ()
    )


def test_explicit_zbs_cannot_cross_previous_boundary() -> None:
    history = replace(_history(), stages=_history().stages[:2], events=())
    record = _record("51_ЗБС", datetime(2009, 1, 1))
    assert resolve_lifecycle_stage(_fund("51_ЗБС"), record, (history,)).stage is None


def test_shared_plast_contract_across_count_lnd_depth_and_historical_delta() -> None:
    from gdis_loader.domain.models import FundParseResult, LoadReport
    from gdis_loader.readers.lha import LhaIndex
    from gdis_loader.service import _build_target_rows
    from test_current_plast import _status  # ty: ignore[unresolved-import]
    from test_service import (  # ty: ignore[unresolved-import]
        _fund_identity,
        _gdi_identity,
        _history_stage,
    )

    fund = replace(
        _fund_identity("Береговое"), object_name="Береговое (ПК17)", object_plast_hint="ПК17"
    )
    history = _history_stage(PartialDate(2020, 1, 1, DatePrecision.DAY))
    history = replace(history, stages=(replace(history.stages[0], plast="ПК17"),))
    previous = replace(
        _gdi_identity("Береговое", raw_plast="ПК17-1", when=datetime(2025, 1, 1), row=2),
        depth_raw_value=100,
        rfp_result="нет",
        lnd_reliability="средняя",
    )
    latest = replace(
        previous,
        raw_plast="ПК17-2",
        normalized_plast=normalize_plast("ПК17-2"),
        study_date=datetime(2026, 1, 1),
        source_row=3,
        depth_raw_value=0,
        rfp_result=None,
        lnd_reliability=None,
    )
    delta = replace(
        _status(1, 6, row=10, year=2025),
        raw_plast="ПК17-1",
        normalized_plast=normalize_plast("ПК17-1"),
    )
    invalid_latest = replace(
        delta,
        study_date=PartialDate(2026, 1, 1, DatePrecision.DAY),
        delta_value=None,
        delta_raw=None,
        source_row=11,
    )
    report = LoadReport("now", "0.23", "3.14", {}, target_field="Береговое")
    rows = _build_target_rows(
        FundParseResult((fund,), date(2026, 8, 1), "fund"),
        GdiIndex((previous, latest), date(2026, 10, 9)),
        LhaIndex(()),
        report,
        (history,),
        date(2026, 10, 9),
        (delta, invalid_latest),
    )
    assert rows[0].plast == "ПК17"
    assert rows[0].gdi_count == 2
    assert rows[0].lnd == rows[0].downhole_sensors == rows[0].gdm_problems == "Да"
    assert report.lnd_previous_fallbacks == report.gdm_fallback_selected == 1
    assert all(r["counted"] for r in report.gdi_reconciliation)


def test_summary_marker_keeps_base_launch_and_does_not_invent_date() -> None:
    initial = replace(
        _history().stages[0],
        plast="ПК17",
        started_at=PartialDate(2023, 12, None, DatePrecision.MONTH),
    )
    history = replace(_history(), stages=(initial,), events=())
    branch = _record("51_ЗБС", datetime(2023, 12, 4), "ПК17-1")
    current = resolve_current_plast(_fund("51", "ПК17"), GdiIndex((branch,)), (history,))
    stage = resolve_lifecycle_stage(current.well, None, current.histories).stage
    assert stage is not None
    assert stage.started_at == initial.started_at
    assert stage.source_location == initial.source_location
    assert stage.target_well_id == "51_ЗБС"


def test_summary_cannot_relabel_base_completion_with_conflicting_plast() -> None:
    history = replace(_history(), events=(), stages=(_history().stages[0],))
    branch = _record("51_ЗБС", datetime(2024, 1, 1), "ПК17")
    assert resolve_current_plast(_fund("51", "ПК17"), GdiIndex((branch,)), (history,)).ambiguous


@pytest.mark.parametrize(("raw", "has_id"), [("КСД", False), ("КВД+ИД", True)])
def test_new_types_drive_duration_capabilities(raw: str, has_id: bool) -> None:
    from gdis_loader.domain.models import FundParseResult, LoadReport
    from gdis_loader.readers.lha import LhaIndex
    from gdis_loader.service import _build_target_rows
    from test_service import (  # ty: ignore[unresolved-import]
        _fund_identity,
        _gdi_identity,
        _history_stage,
    )

    operation = date(2026, 10, 9)
    record = replace(
        _gdi_identity("Береговое", when=datetime(2026, 10, 1)),
        research_type=raw,
        gdi_kind=classify_gdi_kind(raw),
    )
    report = LoadReport("now", "0.23", "3.14", {}, target_field="Береговое")
    (row,) = _build_target_rows(
        FundParseResult((_fund_identity("Береговое"),), date(2026, 8, 1), "fund"),
        GdiIndex((record,), operation),
        LhaIndex(()),
        report,
        (_history_stage(PartialDate(2020, 1, 1, DatePrecision.DAY)),),
        operation,
    )
    assert row.gdi_count == 1
    assert row.duration_without_kvd == 8 / 365
    assert row.duration_without_id == (
        8 / 365 if has_id else (operation - date(2020, 1, 1)).days / 365
    )
