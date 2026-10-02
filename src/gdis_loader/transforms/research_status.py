"""Selection rules for a current GDM delta after lifecycle matching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

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
    records: tuple[ResearchStatusRecord, ...], fallback_max_age_days: int
) -> GdmDeltaSelection:
    """Select the latest valid delta or an in-window prior valid row.

    The input must already be limited to the selected field, lifecycle, and
    normalized plast. Delta values are independent row comparisons and are
    never compared with each other.
    """

    dated = tuple(
        sorted(
            (
                item
                for item in records
                if item.study_date is not None and effective_date(item.study_date) is not None
            ),
            key=lambda item: (_study_day(item), item.source_row),
        )
    )
    if not dated:
        return GdmDeltaSelection(None, None)
    latest = dated[-1]
    if latest.delta_value is not None:
        return GdmDeltaSelection(latest, latest)

    assert latest.study_date is not None
    latest_date = effective_date(latest.study_date)
    previous_valid = tuple(item for item in dated[:-1] if item.delta_value is not None)
    if not previous_valid:
        return GdmDeltaSelection(None, latest)
    candidate = previous_valid[-1]
    assert candidate.study_date is not None
    candidate_date = effective_date(candidate.study_date)
    age_days = (latest_date - candidate_date).days
    if age_days <= fallback_max_age_days:
        return GdmDeltaSelection(candidate, latest, fallback=True, age_days=age_days)
    return GdmDeltaSelection(None, latest, stale_age_days=age_days)


def gdm_problem(delta: float, abs_delta_threshold: float) -> bool:
    """Apply the configured strict absolute Delta threshold."""

    return abs(delta) > abs_delta_threshold


def gdm_fallback_age(latest_date: date, selected_date: date) -> int:
    """Return the nonnegative age from the selected delta to its relevant row."""

    return (latest_date - selected_date).days
