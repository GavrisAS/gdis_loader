from __future__ import annotations

from datetime import datetime

import pytest

from gdis_loader.config import CriteriaConfig
from gdis_loader.domain.models import GdiKind, GdiRecord
from gdis_loader.transforms.aggregates import (
    GdiCountBounds,
    chlorine_growth,
    count_reconciled_gdi,
    insufficient_gdi_from_bounds,
    mean_working_day_rate,
    productivity_decline,
)


def _record(
    when: datetime,
    kind: GdiKind = GdiKind.ID,
    *,
    row: int = 1,
) -> GdiRecord:
    return GdiRecord(
        raw_field_name="Береговое",
        normalized_field="береговое",
        raw_well_name="22",
        base_well_id="22",
        raw_plast="ПК1",
        normalized_plast="ПК1",
        research_type=kind.value,
        study_date=when,
        rfp_result=None,
        lnd_reliability=None,
        gtm_date=None,
        source_row=row,
        gdi_kind=kind,
    )


def test_gdi_count_uses_only_approved_kinds_and_keeps_id_kvd_as_one_row() -> None:
    records = (
        _record(datetime(2023, 4, 10), row=1),
        _record(datetime(2023, 5, 10), GdiKind.ID_KVD, row=2),
        _record(datetime(2023, 6, 10), GdiKind.KVD, row=3),
        _record(datetime(2023, 7, 10), GdiKind.EXCLUDED, row=4),
        _record(datetime(2023, 8, 10), GdiKind.UNKNOWN, row=5),
    )

    bounds = count_reconciled_gdi(records)

    assert bounds.definite_count == 3
    assert bounds.possible_count == 3
    assert bounds.exact_count == 3
    assert len(bounds.ambiguous_records) == 0
    assert insufficient_gdi_from_bounds(bounds, 2) is False


@pytest.mark.parametrize(("count", "expected_insufficient"), [(0, True), (1, False), (2, False)])
def test_aggregation_does_not_reapply_launch_cutoff(
    count: int, expected_insufficient: bool
) -> None:
    records = (
        _record(datetime(2023, 5, 9), row=1),
        *(
            _record(datetime(2023, 6, day), row=index + 2)
            for index, day in enumerate(range(1, count + 1))
        ),
        _record(datetime(2023, 6, 15), GdiKind.EXCLUDED, row=8),
        _record(datetime(2023, 6, 16), GdiKind.UNKNOWN, row=9),
    )

    bounds = count_reconciled_gdi(records)

    assert bounds.exact_count == count + 1
    assert insufficient_gdi_from_bounds(bounds, 2) is expected_insufficient


@pytest.mark.parametrize(
    ("definite", "possible", "expected"),
    [(0, 0, True), (1, 1, True), (2, 2, False), (2, 4, False), (1, 2, None)],
)
def test_insufficient_gdi_bounds_resolve_only_when_threshold_is_stable(
    definite: int,
    possible: int,
    expected: bool | None,
) -> None:
    bounds = GdiCountBounds(definite, possible, (), ())

    assert insufficient_gdi_from_bounds(bounds, 2) is expected


def test_productivity_and_chlorine_comparisons_use_strict_customer_thresholds() -> None:
    assert productivity_decline(1.0, 1.1, 0.0)
    assert not productivity_decline(1.0, 1.1, 0.11)
    assert not productivity_decline(1.0, 1.0, 0.0)
    assert not productivity_decline(1.1, 1.0, 0.0)

    assert chlorine_growth(2001, 1000, 2000, 1000)
    assert not chlorine_growth(2500, 1000, 2500, 1000)
    assert not chlorine_growth(3000, 2000, 2000, 1000)
    assert not chlorine_growth(2500, 2600, 2000, 1000)


def test_mean_working_day_rate_excludes_zero_negative_missing_and_configured_floor() -> None:
    values = (10.0, 0.0, -5.0, None, 30.0)
    assert mean_working_day_rate(values, CriteriaConfig()) == 20.0
    criteria = CriteriaConfig(gas_rate_working_day_min_rate=15.0)
    assert mean_working_day_rate(values, criteria) == 30.0
    assert mean_working_day_rate((0.0, -1.0, None), CriteriaConfig()) is None
    assert mean_working_day_rate(values, CriteriaConfig(gas_rate_working_day_min_rate=30.0)) is None
