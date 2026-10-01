"""Pure business-rule calculations that are safe to test without Excel I/O."""

from __future__ import annotations

import re
from datetime import date, datetime

from gdis_loader.readers.common import parse_number

_LOW_RELIABILITY = re.compile(r"(?:^|[^а-я])низкая(?:$|[^а-я])", re.IGNORECASE)
_KNOWN_RELIABILITY = {"низкая", "средняя", "высокая"}
_RFP_YES = {"да", "yes", "1"}
_RFP_NO = {"нет", "no", "0"}


def lnd_condition(rfp_result: object, reliability: object) -> bool | None:
    """Return true/false for the confirmed LND rule, or None if incomplete."""

    reliability_text = str(reliability).strip().casefold() if reliability is not None else ""
    rfp_text = str(rfp_result).strip().casefold() if rfp_result is not None else ""
    if _LOW_RELIABILITY.search(reliability_text):
        return True
    if rfp_text in _RFP_NO:
        return True

    reliability_known = reliability_text in _KNOWN_RELIABILITY
    rfp_known = rfp_text in (_RFP_YES | _RFP_NO)
    if reliability_known and rfp_known:
        return False
    return None


def downhole_condition(raw_depth: object) -> bool | None:
    """Return whether one study is downhole, preserving missing/invalid state."""

    depth = parse_number(raw_depth)
    return None if depth is None else depth > 0


def duration_without_gdi_years(
    calculation_date: date,
    launch_date: date,
    last_gdi_date: date | None,
) -> float:
    """Calculate the customer-confirmed interval divided by 365 days."""

    start = last_gdi_date or launch_date
    return (calculation_date - start).days / 365


def specific_gdi_count(
    calculation_date: date,
    launch_date: date,
    gdi_count: int,
) -> float | None:
    """Calculate the confirmed specific count only when count is positive."""

    if gdi_count <= 0:
        return None
    duration = (calculation_date - launch_date).days / 365
    return duration / gdi_count


def insufficient_gdi(gdi_count: int) -> bool:
    """Apply the approved 0/1 versus 2+ count threshold as a reusable helper."""

    return gdi_count <= 1


def exact_calendar_date(value: datetime | date) -> date:
    """Normalize an exact date-like value without inventing missing parts."""

    return value.date() if isinstance(value, datetime) else value
