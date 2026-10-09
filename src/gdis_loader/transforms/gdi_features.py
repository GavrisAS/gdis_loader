"""Feature source selection over one reconciled current history/plast."""

from calendar import monthrange
from datetime import date, datetime

from gdis_loader.domain.models import GdiRecord
from gdis_loader.readers.common import parse_number
from gdis_loader.transforms.rules import lnd_condition


def ordered_history(records: tuple[GdiRecord, ...]) -> tuple[GdiRecord, ...]:
    """Chronological order with stable source-file/sheet/row tie-breaking."""
    return tuple(
        sorted(
            records,
            key=lambda r: (
                r.study_date or datetime.min,
                r.source_file,
                r.source_sheet or "",
                r.source_row,
            ),
        )
    )


def lnd_source(records: tuple[GdiRecord, ...]) -> tuple[GdiRecord | None, bool | None, bool]:
    """Use latest valid criterion inputs; inspect only the immediate predecessor."""
    ordered = ordered_history(records)
    for offset, record in enumerate(reversed(ordered[-2:])):
        value = lnd_condition(record.rfp_result, record.lnd_reliability)
        if value is not None:
            return record, value, offset == 1
    return None, None, False


def three_year_boundary(calculation_date: date) -> date:
    """Inclusive calendar-year boundary; Feb 29 clamps to Feb 28."""
    year = calculation_date.year - 3
    return calculation_date.replace(
        year=year, day=min(calculation_date.day, monthrange(year, calculation_date.month)[1])
    )


def downhole_sources(
    records: tuple[GdiRecord, ...], calculation_date: date, threshold_m: float
) -> tuple[GdiRecord, ...]:
    """Positive finite depth within the inclusive three-calendar-year window."""
    boundary = three_year_boundary(calculation_date)
    return tuple(
        r
        for r in ordered_history(records)
        if r.study_date is not None
        and boundary <= r.study_date.date() <= calculation_date
        and (depth := parse_number(r.depth_raw_value)) is not None
        and depth > max(0.0, threshold_m)
    )
