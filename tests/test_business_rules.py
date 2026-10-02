from __future__ import annotations

from datetime import date

import pytest

from gdis_loader.transforms.rules import (
    downhole_condition,
    duration_without_gdi_years,
    insufficient_gdi,
    lnd_condition,
    specific_gdi_count,
)


@pytest.mark.parametrize(
    ("rfp", "reliability", "expected"),
    [
        ("да", "Низкая", True),
        ("нет", "Высокая", True),
        ("Да", "Средняя", False),
        (None, "Высокая", None),
        ("да", None, None),
        ("не распознано", "не распознано", None),
        (None, "Низкая", True),
        ("нет", None, True),
    ],
)
def test_lnd_rule_is_tri_state(rfp: object, reliability: object, expected: bool | None) -> None:
    assert lnd_condition(rfp, reliability) is expected


@pytest.mark.parametrize(
    ("depth", "expected"),
    [(25, True), (0, False), (None, None), ("ошибка", None)],
)
def test_downhole_rule_preserves_zero_and_unknown(depth: object, expected: bool | None) -> None:
    assert downhole_condition(depth, 0.0) is expected
    assert downhole_condition(depth, 25.0) is (False if depth == 25 else expected)


def test_duration_without_gdi_uses_launch_or_last_gdi_date() -> None:
    calculation = date(2026, 1, 1)
    launch = date(2020, 1, 1)
    last_gdi = date(2025, 1, 1)

    assert (
        duration_without_gdi_years(calculation, launch, None) == (calculation - launch).days / 365
    )
    assert (
        duration_without_gdi_years(calculation, launch, last_gdi)
        == (calculation - last_gdi).days / 365
    )


def test_specific_gdi_count_is_defined_only_for_positive_count() -> None:
    assert specific_gdi_count(date(2022, 1, 1), date(2020, 1, 1), 2) == 1 + 1 / 730
    assert specific_gdi_count(date(2022, 1, 1), date(2020, 1, 1), 0) is None


@pytest.mark.parametrize(("count", "expected"), [(0, True), (1, True), (2, False), (8, False)])
def test_insufficient_gdi_helper_uses_approved_threshold(count: int, expected: bool) -> None:
    assert insufficient_gdi(count, 2) is expected
