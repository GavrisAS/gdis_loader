"""Deterministic temporal and threshold rules over already-read source records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from gdis_loader.config import CriteriaConfig
from gdis_loader.domain.models import GdiRecord


@dataclass(frozen=True, slots=True)
class GdiCountBounds:
    """Definite and possible counts in a reconciled current history."""

    definite_count: int
    possible_count: int
    definite_records: tuple[GdiRecord, ...]
    ambiguous_records: tuple[GdiRecord, ...]

    @property
    def exact_count(self) -> int | None:
        return self.definite_count if not self.ambiguous_records else None


def count_reconciled_gdi(records: tuple[GdiRecord, ...]) -> GdiCountBounds:
    """Count valid, dated rows already assigned to current identity/history/plast.

    Base launch is chronology evidence; applicability is decided by lifecycle
    reconciliation before this pure aggregation. Combined rows count once.
    """
    valid = tuple(r for r in records if r.gdi_kind.valid and r.study_date is not None)
    return GdiCountBounds(len(valid), len(valid), valid, ())


def insufficient_gdi_from_bounds(bounds: GdiCountBounds, min_count: int) -> bool | None:
    """Resolve the 0/1 threshold when its result is stable across the bounds."""

    if bounds.definite_count >= min_count:
        return False
    if bounds.possible_count < min_count:
        return True
    return None


def productivity_decline(previous_a: float, current_a: float, min_increase: float) -> bool:
    """Apply the approved strict comparison between consecutive numeric a values."""

    return current_a - previous_a > min_increase


def chlorine_growth(
    current: float,
    previous: float,
    current_min: float,
    delta_min: float,
) -> bool:
    """Apply the approved strict chlorine level and rise thresholds."""

    return current > current_min and current - previous > delta_min


def duration_years(calculation_date: date, source_date: date) -> float:
    """Return exact elapsed days divided by 365 without hidden rounding."""

    return (calculation_date - source_date).days / 365


def mean_working_day_rate(
    values: tuple[float | None, ...], criteria: CriteriaConfig
) -> float | None:
    """Average only finite parsed daily values strictly above the configured floor."""

    selected = tuple(
        value
        for value in values
        if value is not None and value > criteria.gas_rate_working_day_min_rate
    )
    return sum(selected) / len(selected) if selected else None
