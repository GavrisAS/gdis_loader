"""Deterministic temporal and threshold rules over already-read source records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

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
    """Return whether a GDI falls after launch, retaining partial-date ambiguity."""

    if launch.precision.value == "day":
        assert launch.month is not None and launch.day is not None
        return study_date.date() >= date(launch.year, launch.month, launch.day)
    if launch.precision.value == "month":
        assert launch.month is not None
        study_period = (study_date.year, study_date.month)
        launch_period = (launch.year, launch.month)
    else:
        study_period = (study_date.year,)
        launch_period = (launch.year,)
    if study_period > launch_period:
        return True
    if study_period < launch_period:
        return False
    return None


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


def insufficient_gdi_from_bounds(bounds: GdiCountBounds) -> bool | None:
    """Resolve the 0/1 threshold when its result is stable across the bounds."""

    if bounds.definite_count >= 2:
        return False
    if bounds.possible_count <= 1:
        return True
    return None


def productivity_decline(previous_a: float, current_a: float) -> bool:
    """Apply the approved strict comparison between consecutive numeric a values."""

    return current_a > previous_a


def chlorine_growth(current: float, previous: float) -> bool:
    """Apply the approved strict chlorine level and rise thresholds."""

    return current > 2000 and current - previous > 1000


def duration_years(calculation_date: date, source_date: date) -> float:
    """Return exact elapsed days divided by 365 without hidden rounding."""

    return (calculation_date - source_date).days / 365
