"""One applicability contract for all current-history GDI-derived features."""

from datetime import date

from gdis_loader.domain.models import FundWell, GdiRecord, WellHistory, WellStage
from gdis_loader.matching.lifecycle import resolve_lifecycle_stage
from gdis_loader.transforms.gdi_features import ordered_history


def current_gdi_history(
    well: FundWell,
    records: tuple[GdiRecord, ...],
    histories: tuple[WellHistory, ...],
    stage: WellStage | None,
    plast: str | None,
    identity: str | None = None,
    calculation_date: date | None = None,
) -> tuple[GdiRecord, ...]:
    """Field/root, valid type/date, cutoff, canonical plast and resolved history.

    No launch filter is reapplied after lifecycle assignment. Identity-only
    fallback is retained for legacy callers with no available Base stage;
    downstream count remains unresolved when launch/current stage is unknown.
    """
    return ordered_history(
        tuple(
            record
            for record in records
            if record.base_well_id == well.base_well_id
            and record.normalized_field == well.normalized_field
            and record.gdi_kind.valid
            and record.study_date is not None
            and (calculation_date is None or record.study_date.date() <= calculation_date)
            and record.normalized_plast == plast
            and (
                resolve_lifecycle_stage(well, record, histories).stage == stage
                if stage is not None
                else identity is not None and record.target_well_id == identity
            )
        )
    )
