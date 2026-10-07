"""Selection rules for a current GDM delta after lifecycle matching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isfinite

from gdis_loader.domain.dates import effective_date
from gdis_loader.domain.models import ResearchStatusRecord


@dataclass(frozen=True, slots=True)
class GdmDeltaSelection:
    """Selected valid delta and the latest relevant row used as its anchor."""

    record: ResearchStatusRecord | None
    latest_relevant: ResearchStatusRecord | None
    fallback: bool = False
    age_days: int | None = None
    stale_age_days: int | None = None


def _study_day(record: ResearchStatusRecord) -> date:
    if record.study_date is None:
        raise ValueError("A dated GDM record is required for Delta selection.")
    return effective_date(record.study_date)


def select_gdm_delta(
    records: tuple[ResearchStatusRecord, ...],
    fallback_max_age_days: int,
    *,
    reference_date: date | None = None,
) -> GdmDeltaSelection:
    """Select the newest finite Delta whose age is within the inclusive window.

    The input must already be limited to the selected field, lifecycle, and
    normalized plast. Delta values are independent row comparisons and are
    never compared with each other. Production callers provide calculation date;
    omitted reference_date retains the latest-row anchor for API compatibility.
    """

    dated = tuple(
        sorted(
            (
                item
                for item in records
                if item.study_date is not None
                and (reference_date is None or _study_day(item) <= reference_date)
            ),
            key=lambda item: (_study_day(item), item.source_row),
        )
    )
    if not dated:
        return GdmDeltaSelection(None, None)
    latest = dated[-1]
    anchor = reference_date or _study_day(latest)
    valid = tuple(
        item
        for item in dated
        if item.delta_value is not None
        and isfinite(item.delta_value)
        and _study_day(item) <= anchor
    )
    if not valid:
        return GdmDeltaSelection(None, latest)
    candidate = valid[-1]
    age_days = (anchor - _study_day(candidate)).days
    if age_days > fallback_max_age_days:
        return GdmDeltaSelection(None, latest, stale_age_days=age_days)
    return GdmDeltaSelection(
        candidate,
        latest,
        fallback=candidate != latest,
        age_days=age_days,
    )


def gdm_problem(delta: float, abs_delta_threshold: float) -> bool:
    """Apply the configured strict absolute Delta threshold."""

    return abs(delta) > abs_delta_threshold


def gdm_fallback_age(latest_date: date, selected_date: date) -> int:
    """Return the nonnegative age from the selected delta to its relevant row."""

    return (latest_date - selected_date).days
