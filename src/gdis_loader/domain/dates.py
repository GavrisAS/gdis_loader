"""Lossless partial calendar dates and conservative temporal comparisons."""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from gdis_loader.domain.models import DatePrecision, PartialDate

_YEAR_ONLY = re.compile(r"^(\d{4})$")
_MONTH_YEAR = re.compile(r"^(\d{1,2})[./](\d{4})$")
_FORMAT_DECIMALS = re.compile(r"0\.([0#]+)")


def parse_partial_date(value: object, number_format: str = "General") -> PartialDate | None:
    """Parse Excel date cells without manufacturing a day for partial dates.

    Numeric month/year cells are read as ``M.YYYY``. For formatted numeric
    cells, the decimal places from ``number_format`` determine the displayed
    year digits (for example, 7.202 with ``0.0000`` is 7.2020).
    """

    if isinstance(value, datetime):
        return PartialDate(value.year, value.month, value.day, DatePrecision.DAY)
    if isinstance(value, date):
        return PartialDate(value.year, value.month, value.day, DatePrecision.DAY)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            number = Decimal(str(value))
        except InvalidOperation:
            return None
        if not number.is_finite():
            return None
        if number == number.to_integral_value():
            year = int(number)
            return _make_partial_date(year, None, None, DatePrecision.YEAR)
        format_match = _FORMAT_DECIMALS.search(number_format)
        exponent = number.as_tuple().exponent
        places = (
            len(format_match.group(1))
            if format_match
            else max(0, -exponent)
            if isinstance(exponent, int)
            else 0
        )
        displayed = number.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
        month_part, _, year_part = f"{displayed:.{places}f}".partition(".")
        if not year_part:
            return None
        return _month_year(int(month_part), year_part)

    text = str(value).strip()
    year_match = _YEAR_ONLY.fullmatch(text)
    if year_match:
        return _make_partial_date(int(year_match.group(1)), None, None, DatePrecision.YEAR)
    month_match = _MONTH_YEAR.fullmatch(text)
    if month_match:
        return _month_year(int(month_match.group(1)), month_match.group(2))
    for pattern in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, pattern)
            return PartialDate(parsed.year, parsed.month, parsed.day, DatePrecision.DAY)
        except ValueError:
            continue
    return None


def _make_partial_date(
    year: int,
    month: int | None,
    day: int | None,
    precision: DatePrecision,
) -> PartialDate | None:
    if year < 1 or year > 9999:
        return None
    try:
        return PartialDate(year, month, day, precision)
    except ValueError:
        return None


def _month_year(month: int, year_digits: str) -> PartialDate | None:
    if len(year_digits) != 4:
        return None
    return _make_partial_date(int(year_digits), month, None, DatePrecision.MONTH)


DateLike = PartialDate | date | datetime


def date_window(value: DateLike) -> tuple[datetime, datetime]:
    """Return the earliest/latest exact instants represented by a date value."""

    if isinstance(value, PartialDate):
        if value.precision is DatePrecision.YEAR:
            assert value.month is None
            return (
                datetime(value.year, 1, 1),
                datetime(value.year, 12, 31, 23, 59, 59, 999999),
            )
        if value.precision is DatePrecision.MONTH:
            assert value.month is not None
            last_day = calendar.monthrange(value.year, value.month)[1]
            return (
                datetime(value.year, value.month, 1),
                datetime(value.year, value.month, last_day, 23, 59, 59, 999999),
            )
        assert value.month is not None and value.day is not None
        exact = datetime(value.year, value.month, value.day)
        return exact, exact.replace(hour=23, minute=59, second=59, microsecond=999999)
    if isinstance(value, datetime):
        return value, value
    exact = datetime.combine(value, time.min)
    return exact, exact.replace(hour=23, minute=59, second=59, microsecond=999999)


def definitely_before(left: DateLike, right: DateLike) -> bool:
    """Return true only if every instant in left precedes every instant in right."""

    _, left_end = date_window(left)
    right_start, _ = date_window(right)
    return left_end < right_start


def definitely_after(left: DateLike, right: DateLike) -> bool:
    """Return true only if every instant in left follows every instant in right."""

    left_start, _ = date_window(left)
    _, right_end = date_window(right)
    return left_start > right_end


def overlaps_same_precision_window(left: DateLike, right: DateLike) -> bool:
    """Return true when source precision does not establish a strict order."""

    return not definitely_before(left, right) and not definitely_after(left, right)
