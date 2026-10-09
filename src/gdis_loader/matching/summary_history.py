"""Conservative missing-branch evidence from valid Summary GDI observations."""

from dataclasses import replace

from gdis_loader.domain.dates import effective_date
from gdis_loader.domain.models import (
    FundWell,
    GdiRecord,
    WellEventKind,
    WellHistory,
)
from gdis_loader.matching.fund_scope import parse_fund_object_scope
from gdis_loader.matching.normalize import normalize_field_name, normalize_well_id


def supplement_summary_history(
    well: FundWell, records: tuple[GdiRecord, ...], histories: tuple[WellHistory, ...]
) -> tuple[tuple[WellHistory, ...], bool, bool]:
    """Infer only a unique explicit ZBS branch missing from an initial-only Base.

    No ordinal is invented, no dated or undated Base boundary is replaced.
    Root observations must precede all branch observations. Independent GS/MZS
    identities do not supply evidence for the mother well. The matching Base
    completion supplies the launch date; Summary supplies
    its explicit identity marker, never an invented physical launch date.
    """
    relevant = tuple(
        h
        for h in histories
        if h.physical_root == well.base_well_id
        and normalize_field_name(h.field_name) == well.normalized_field
        and normalize_well_id(h.source_display_well).target_well_id == well.base_well_id
    )
    if len(relevant) != 1:
        return histories, False, False
    history = relevant[0]
    if len(history.stages) != 1 or history.stages[0].event_kind is not WellEventKind.INITIAL:
        return histories, False, False
    if any(
        e.event_kind in {WellEventKind.ZBS, WellEventKind.PVLG, WellEventKind.PNLG}
        for e in history.events
    ):
        return histories, False, False
    fund_identity = normalize_well_id(well.target_well_id or well.raw_display)
    if fund_identity.recognized_variant not in {None, "ЗБС"}:
        return histories, False, False
    branches = tuple(
        r for r in records if normalize_well_id(r.target_well_id or "").recognized_variant == "ЗБС"
    )
    identities = {r.target_well_id for r in branches}
    if not identities:
        return histories, False, False
    # Even an out-of-scope rival branch prevents evidence-only assignment.
    if len(identities) != 1 or len(well.active_zbs_identities) > 1:
        return histories, False, True
    identity = next(iter(identities))
    parsed = normalize_well_id(identity or "")
    if parsed.ordinal is None or parsed.ordinal != 1:
        return histories, False, True
    if fund_identity.recognized_variant == "ЗБС" and fund_identity.target_well_id != identity:
        return histories, False, True
    dated = tuple(r for r in branches if r.study_date is not None)
    if not dated:
        return histories, False, False
    first = min(dated, key=lambda r: (r.study_date, r.source_row))
    last_date = max(r.study_date for r in dated if r.study_date is not None)
    latest_plasts = {r.normalized_plast for r in dated if r.study_date == last_date}
    scope = parse_fund_object_scope(well.object_name)
    if (
        len(latest_plasts) != 1
        or not scope.compatible(next(iter(latest_plasts)))
        or history.stages[0].plast != next(iter(latest_plasts))
    ):
        return histories, False, True
    assert first.study_date is not None
    if first.study_date.date() > well.fund_date:
        return histories, False, True
    # No interleaving with root history, no unrecognized lifecycle labels.
    for r in records:
        marker = normalize_well_id(r.target_well_id or "")
        if marker.recognized_variant in {"ГС", "МЗС"}:
            continue
        if r.target_well_id == identity:
            continue
        if r.target_well_id != well.base_well_id:
            return histories, False, True
        if r.study_date is not None and (
            r.study_date >= first.study_date
            or r.study_date.date() >= effective_date(history.stages[0].started_at)
        ):
            return histories, False, True
    stage = replace(
        history.stages[0], target_well_id=identity, event_kind=WellEventKind.ZBS, ordinal=1
    )
    supplemented = replace(history, stages=(stage,))
    return tuple(supplemented if h == history else h for h in histories), True, False
