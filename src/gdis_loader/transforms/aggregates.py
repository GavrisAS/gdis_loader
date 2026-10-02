"""Deterministic temporal and threshold rules over already-read source records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from gdis_loader.config import CriteriaConfig
from gdis_loader.domain.dates import effective_date
from gdis_loader.domain.models import GdiKind, GdiRecord, PartialDate

_VALID_GDI_KINDS = frozenset({GdiKind.ID, GdiKind.ID_KVD, GdiKind.KVD})


@dataclass(frozen=True, slots=True)
class GdiCountBounds:
    """Definite and possible valid GDI counts after a launch date."""

    definite_count: int
    possible_count: int
    definite_records: tuple[GdiRecord, ...]
    ambiguous_records: tuple[GdiRecord, ...]

    @property
    def exact_count(self) -> int | None:
        return self.definite_count if not self.ambiguous_records else None


def _study_after_launch(study_date: datetime, launch: PartialDate) -> bool | None:
    """Compare against the agreed effective date for DAY, MONTH, or YEAR."""

    return study_date.date() >= effective_date(launch)


def count_gdi_since_launch(records: tuple[GdiRecord, ...], launch: PartialDate) -> GdiCountBounds:
    """Count valid GDI records after launch or return bounds for partial dates."""

    definite: list[GdiRecord] = []
    ambiguous: list[GdiRecord] = []
    for record in records:
        if record.gdi_kind not in _VALID_GDI_KINDS or record.study_date is None:
            continue
        relation = _study_after_launch(record.study_date, launch)
        if relation is True:
            definite.append(record)
        elif relation is None:
            ambiguous.append(record)
    return GdiCountBounds(
        definite_count=len(definite),
        possible_count=len(definite) + len(ambiguous),
        definite_records=tuple(definite),
        ambiguous_records=tuple(ambiguous),
    )


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
