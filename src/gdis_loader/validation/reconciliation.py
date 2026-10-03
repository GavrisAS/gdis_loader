"""Helpers for comparing source counts with values in a generated workbook."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Literal

from gdis_loader.domain.dates import effective_calendar_date
from gdis_loader.domain.models import (
    FundWell,
    GdiKind,
    GdiRecord,
    WellEventKind,
    WellHistory,
    WellStage,
)
from gdis_loader.matching.lifecycle import resolve_lifecycle_stage
from gdis_loader.matching.normalize import normalize_field_name, normalize_well_id


def application_count_state(
    application_count: int | None, expected_count: int
) -> Literal["missing", "match", "mismatch"]:
    """Distinguish an absent count from a numeric zero during reconciliation."""

    if application_count is None:
        return "missing"
    return "match" if application_count == expected_count else "mismatch"


def _canonical_current_identity(stage: WellStage) -> str:
    if stage.event_kind in {WellEventKind.PVLG, WellEventKind.PNLG}:
        return stage.physical_root
    if stage.target_well_id is not None:
        return stage.target_well_id
    if stage.event_kind is WellEventKind.ZBS:
        return f"{stage.physical_root}_ЗБС"
    return stage.physical_root


def _latest_timeline_stage(
    well: FundWell,
    histories: tuple[WellHistory, ...],
) -> WellStage | None:
    """Find a unique latest boundary stage without applying fund plast."""

    if well.base_well_id is None:
        return None
    normalized_identity = normalize_well_id(well.target_well_id or well.raw_display)
    matches = tuple(
        history
        for history in histories
        if history.physical_root == well.base_well_id
        and normalize_field_name(history.field_name) == well.normalized_field
    )
    if normalized_identity.recognized_variant in {"МЗС", "ГС"} or (
        normalized_identity.target_well_id != normalized_identity.base_well_id
        and normalized_identity.recognized_variant is None
    ):
        matches = tuple(
            history
            for history in matches
            if normalize_well_id(history.source_display_well).target_well_id
            == normalized_identity.target_well_id
        )
    else:
        root_histories = tuple(
            history
            for history in matches
            if normalize_well_id(history.source_display_well).target_well_id
            == normalized_identity.base_well_id
        )
        if root_histories:
            matches = root_histories
    if len(matches) != 1:
        return None

    stages = tuple(
        stage
        for stage in matches[0].stages
        if effective_calendar_date(stage.started_at) <= well.fund_date
    )
    if not stages:
        return None
    latest_date = max(effective_calendar_date(stage.started_at) for stage in stages)
    latest = tuple(
        stage for stage in stages if effective_calendar_date(stage.started_at) == latest_date
    )
    if well.object_plast_hint is not None:
        plast_matches = tuple(stage for stage in latest if stage.plast == well.object_plast_hint)
        if len(plast_matches) == 1:
            return plast_matches[0]
    if len(latest) == 1:
        return latest[0]
    if all(stage.event_kind is WellEventKind.ZBS for stage in latest):
        return max(latest, key=lambda stage: stage.stage_sequence)
    return None


def current_lifecycle_counts(
    fund_wells: Iterable[FundWell],
    histories: tuple[WellHistory, ...],
    target_field: str,
    gdi_records: Iterable[GdiRecord] = (),
    calculation_date: date | None = None,
) -> dict[str, int]:
    """Count current lifecycle identities and strict fund/history resolution.

    Direct resolution uses fund plast and history. If those conflict, a valid
    GDI row may cross-check the already unique latest boundary stage; it does
    not change the loader's fund-plast eligibility decision. PVLG and PNLG
    identities use the physical root because those events retain display number.
    """

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
    for well in fund_wells:
        if well.normalized_field != field_key or not well.is_rating_eligible:
            continue
        eligible_rows += 1
        resolution = resolve_lifecycle_stage(well, None, histories)
        stage = resolution.stage if resolution.issue is None else None
        if stage is not None:
            resolved_rows += 1
        elif resolution.issue is not None:
            ambiguous_rows += 1
        else:
            unresolved_rows += 1
        if stage is None:
            boundary_stage = _latest_timeline_stage(well, histories)
            if boundary_stage is not None:
                evidence = tuple(
                    record
                    for record in gdi_rows
                    if record.base_well_id == well.base_well_id
                    and record.normalized_field == well.normalized_field
                    and record.gdi_kind in {GdiKind.ID, GdiKind.ID_KVD, GdiKind.KVD}
                    and record.study_date is not None
                    and record.study_date.date() <= (calculation_date or well.fund_date)
                    and (record_stage := resolve_lifecycle_stage(well, record, histories)).stage
                    == boundary_stage
                    and record_stage.issue is None
                )
                if evidence:
                    stage = boundary_stage
                    gdi_crosschecked_rows += 1
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
