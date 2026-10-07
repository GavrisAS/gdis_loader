"""Helpers for comparing source counts with values in a generated workbook."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Literal

from gdis_loader.domain.models import (
    FundWell,
    GdiRecord,
    WellEventKind,
    WellHistory,
    WellStage,
)
from gdis_loader.matching.current_plast import resolve_current_plast
from gdis_loader.matching.lifecycle import attach_active_fund_branches, resolve_lifecycle_stage
from gdis_loader.matching.matcher import GdiIndex
from gdis_loader.matching.normalize import normalize_field_name


def application_count_state(
    application_count: int | None, expected_count: int
) -> Literal["missing", "match", "mismatch"]:
    """Distinguish an absent count from a numeric zero during reconciliation."""

    if application_count is None:
        return "missing"
    return "match" if application_count == expected_count else "mismatch"


def _canonical_current_identity(stage: WellStage) -> str:
    if stage.target_well_id is not None:
        return stage.target_well_id
    if stage.event_kind is WellEventKind.ZBS:
        return f"{stage.physical_root}_ЗБС"
    return stage.physical_root


def current_lifecycle_counts(
    fund_wells: Iterable[FundWell],
    histories: tuple[WellHistory, ...],
    target_field: str,
    gdi_records: Iterable[GdiRecord] = (),
    calculation_date: date | None = None,
) -> dict[str, int]:
    """Count canonical current lifecycle identities using the loader's resolver."""

    field_key = normalize_field_name(target_field)
    identities: dict[WellEventKind, set[str]] = {
        kind: set()
        for kind in (
            WellEventKind.INITIAL,
            WellEventKind.ZBS,
            WellEventKind.PVLG,
            WellEventKind.PNLG,
        )
    }
    eligible_rows = 0
    resolved_rows = 0
    ambiguous_rows = 0
    unresolved_rows = 0
    pvlg_rows = 0
    gdi_crosschecked_rows = 0
    gdi_rows = tuple(gdi_records)
    index = GdiIndex(gdi_rows, calculation_date)
    for well in attach_active_fund_branches(tuple(fund_wells)):
        if well.normalized_field != field_key or not well.is_rating_eligible:
            continue
        eligible_rows += 1
        original = resolve_lifecycle_stage(well, None, histories)
        current = resolve_current_plast(well, index, histories)
        resolution = resolve_lifecycle_stage(current.well, None, current.histories)
        stage = resolution.stage if resolution.issue is None and not current.ambiguous else None
        if stage is not None:
            resolved_rows += 1
            if original.stage is None:
                gdi_crosschecked_rows += 1
        elif resolution.issue is not None or current.ambiguous:
            ambiguous_rows += 1
        else:
            unresolved_rows += 1
        if stage is None:
            continue
        if stage.event_kind in identities:
            identities[stage.event_kind].add(_canonical_current_identity(stage))
        if stage.event_kind is WellEventKind.PVLG:
            pvlg_rows += 1

    return {
        "eligible_current_lifecycle_rows": eligible_rows,
        "resolved_current_lifecycle_rows": resolved_rows,
        "ambiguous_current_lifecycle_rows": ambiguous_rows,
        "unresolved_current_lifecycle_rows": unresolved_rows,
        "current_initial_identities": len(identities[WellEventKind.INITIAL]),
        "current_zbs_identities": len(identities[WellEventKind.ZBS]),
        "current_pvlg_identities": len(identities[WellEventKind.PVLG]),
        "current_pvlg_rows": pvlg_rows,
        "current_pnlg_identities": len(identities[WellEventKind.PNLG]),
        "gdi_crosschecked_current_lifecycle_rows": gdi_crosschecked_rows,
    }
