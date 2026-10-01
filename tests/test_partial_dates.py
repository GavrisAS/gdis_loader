from __future__ import annotations

from datetime import datetime

import pytest

from gdis_loader.domain.dates import (
    definitely_after,
    definitely_before,
    overlaps_same_precision_window,
    parse_partial_date,
)
from gdis_loader.domain.models import DatePrecision, PartialDate


@pytest.mark.parametrize(
    ("raw", "number_format", "expected"),
    [
        (3.2002, "General", PartialDate(2002, 3, None, DatePrecision.MONTH)),
        (8.2023, "General", PartialDate(2023, 8, None, DatePrecision.MONTH)),
        (7.202, "0.0000", PartialDate(2020, 7, None, DatePrecision.MONTH)),
        (
            datetime(2025, 9, 16),
            "dd.mm.yyyy",
            PartialDate(2025, 9, 16, DatePrecision.DAY),
        ),
        (2015, "General", PartialDate(2015, None, None, DatePrecision.YEAR)),
    ],
)
def test_partial_date_retains_source_precision(
    raw: object, number_format: str, expected: PartialDate
) -> None:
    assert parse_partial_date(raw, number_format) == expected


@pytest.mark.parametrize("raw", [13.2020, 0.2020, 7.202, "13.2020", "7.202"])
def test_invalid_or_under_precision_month_year_is_not_guessed(raw: object) -> None:
    assert parse_partial_date(raw, "General") is None


def test_exact_gdi_date_is_definitely_after_prior_month_but_same_month_is_ambiguous() -> None:
    launch = PartialDate(2023, 6, None, DatePrecision.MONTH)
    later = datetime(2023, 8, 15)
    same_month = datetime(2023, 6, 15)

    assert definitely_after(later, launch)
    assert not definitely_before(later, launch)
    assert overlaps_same_precision_window(same_month, launch)
    assert not definitely_after(same_month, launch)


def test_two_partial_months_are_not_ordered_when_the_windows_overlap() -> None:
    june = PartialDate(2023, 6, None, DatePrecision.MONTH)
    same_june = PartialDate(2023, 6, None, DatePrecision.MONTH)
    july = PartialDate(2023, 7, None, DatePrecision.MONTH)

    assert overlaps_same_precision_window(june, same_june)
    assert definitely_before(june, july)
