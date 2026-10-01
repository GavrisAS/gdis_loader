"""Conservative GDI matching by physical well, field, object, and date."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, time

from gdis_loader.domain.models import (
    DiagnosticIssue,
    FundWell,
    GdiKind,
    GdiRecord,
    IssueSeverity,
    MatchResult,
    MatchStatus,
    WellHistory,
    WellStage,
)
from gdis_loader.matching.lifecycle import resolve_lifecycle_stage
from gdis_loader.matching.normalize import normalize_well_id

RATING_GDI_KINDS = frozenset({GdiKind.ID, GdiKind.ID_KVD, GdiKind.KVD})


class GdiIndex:
    """Index valid GDI records once; no source workbook is reread per well."""

    def __init__(self, records: Iterable[GdiRecord], calculation_date: date | None = None) -> None:
        self._calculation_date = calculation_date
        grouped: defaultdict[str, list[GdiRecord]] = defaultdict(list)
        by_root: defaultdict[str, list[GdiRecord]] = defaultdict(list)
        for record in records:
            if record.gdi_kind not in RATING_GDI_KINDS:
                continue
            target_id = record.target_well_id or (
                normalize_well_id(record.raw_well_name).target_well_id
                if record.raw_well_name is not None
                else None
            )
            if (
                target_id is not None
                and record.normalized_field is not None
                and record.normalized_plast is not None
                and record.study_date is not None
            ):
                grouped[target_id].append(record)
                physical_root = record.base_well_id or normalize_well_id(target_id).base_well_id
                if physical_root is not None:
                    by_root[physical_root].append(record)
        self._by_target_identity = {key: tuple(items) for key, items in grouped.items()}
        self._by_physical_root = {key: tuple(items) for key, items in by_root.items()}

    def history_for(self, fund_well: FundWell) -> tuple[GdiRecord, ...]:
        """Return all valid history rows for this root and field before cutoff."""

        if fund_well.base_well_id is None:
            return ()
        cutoff_day = self._calculation_date or fund_well.fund_date
        cutoff = datetime.combine(cutoff_day, time.max)
        return tuple(
            record
            for record in self._by_physical_root.get(fund_well.base_well_id, ())
            if record.normalized_field == fund_well.normalized_field
            and record.study_date is not None
            and record.study_date <= cutoff
        )

    def candidates_for(
        self,
        fund_well: FundWell,
        histories: tuple[WellHistory, ...] = (),
    ) -> tuple[GdiRecord, ...]:
        """Return field-qualified records relevant on the fund date."""

        target_id = (
            fund_well.target_well_id or normalize_well_id(fund_well.raw_display).target_well_id
        )
        if target_id is None:
            return ()
        cutoff_day = self._calculation_date or fund_well.fund_date
        cutoff = datetime.combine(cutoff_day, time.max)
        exact = tuple(
            record
            for record in self._by_target_identity.get(target_id, ())
            if record.normalized_field == fund_well.normalized_field
            and record.study_date is not None
            and record.study_date <= cutoff
        )
        if target_id != fund_well.base_well_id:
            root_only = tuple(
                record
                for record in self._by_physical_root.get(fund_well.base_well_id or "", ())
                if record.target_well_id == fund_well.base_well_id
                and record.normalized_field == fund_well.normalized_field
                and record.study_date is not None
                and record.study_date <= cutoff
            )
            if fund_well.object_plast_hint is not None:
                root_only = tuple(
                    record
                    for record in root_only
                    if record.normalized_plast == fund_well.object_plast_hint
                )
            resolved = tuple(
                record
                for record in root_only
                if (resolution := resolve_lifecycle_stage(fund_well, record, histories)).stage
                is not None
                and _stage_target_identity(resolution.stage) == target_id
            )
            return tuple(dict.fromkeys((*exact, *resolved)))

        lineage = tuple(
            record
            for record in self._by_physical_root.get(fund_well.base_well_id or "", ())
            if record.normalized_field == fund_well.normalized_field
            and record.study_date is not None
            and record.study_date <= cutoff
        )
        if fund_well.object_plast_hint is not None:
            hinted = tuple(
                record
                for record in lineage
                if record.normalized_plast == fund_well.object_plast_hint
            )
            if hinted:
                lineage = hinted
        lineage = _latest_by_identity_and_plast(lineage)
        exact_lineage = tuple(record for record in lineage if record.target_well_id == target_id)
        accepted_exact = tuple(
            record
            for record in exact_lineage
            if not (
                (resolution := resolve_lifecycle_stage(fund_well, record, histories)).issue
                is not None
                and resolution.stage is None
            )
        )
        resolved_suffixes = tuple(
            record
            for record in lineage
            if record.target_well_id != target_id
            and resolve_lifecycle_stage(fund_well, record, histories).stage is not None
        )
        return tuple(dict.fromkeys((*accepted_exact, *resolved_suffixes)))

    def lineage_candidates_for(self, fund_well: FundWell) -> tuple[GdiRecord, ...]:
        """Return root-related candidates for a provenance-rich ambiguity."""

        if fund_well.base_well_id is None:
            return ()
        cutoff_day = self._calculation_date or fund_well.fund_date
        cutoff = datetime.combine(cutoff_day, time.max)
        lineage = tuple(
            record
            for record in self._by_physical_root.get(fund_well.base_well_id, ())
            if record.normalized_field == fund_well.normalized_field
            and record.study_date is not None
            and record.study_date <= cutoff
        )
        if fund_well.object_plast_hint is not None:
            hinted = tuple(
                record
                for record in lineage
                if record.normalized_plast == fund_well.object_plast_hint
            )
            if hinted:
                lineage = hinted
        return _latest_by_identity_and_plast(lineage)


def _latest_by_identity_and_plast(records: tuple[GdiRecord, ...]) -> tuple[GdiRecord, ...]:
    """Keep the newest date per source identity/plast before lineage checks."""

    groups: defaultdict[tuple[str | None, str | None], list[GdiRecord]] = defaultdict(list)
    for record in records:
        groups[(record.target_well_id, record.normalized_plast)].append(record)
    latest_records: list[GdiRecord] = []
    for grouped in groups.values():
        latest_date = max(record.study_date for record in grouped if record.study_date is not None)
        latest_records.extend(record for record in grouped if record.study_date == latest_date)
    return tuple(latest_records)


def _stage_target_identity(stage: WellStage) -> str | None:
    """Return an established identity or its event-based stage label."""

    target_well_id = stage.target_well_id
    if target_well_id:
        return target_well_id
    if stage.event_kind.value == "INITIAL":
        return stage.physical_root
    if stage.event_kind.value in {"ЗБС", "ПВЛГ"}:
        return f"{stage.physical_root}_{stage.event_kind.value}"
    return None


def match_fund_well(
    fund_well: FundWell,
    gdi_index: GdiIndex,
    histories: tuple[WellHistory, ...] = (),
) -> MatchResult:
    """Resolve one fund well without choosing among equal latest candidates."""

    if fund_well.base_well_id is None:
        return MatchResult(
            status=MatchStatus.INVALID_SOURCE,
            fund_well=fund_well,
            explanation="Номер скважины фонда не удалось нормализовать.",
        )
    candidates = gdi_index.candidates_for(fund_well, histories)
    if not candidates:
        lineage = gdi_index.lineage_candidates_for(fund_well)
        unresolved_variants = tuple(
            record
            for record in lineage
            if record.target_well_id != fund_well.target_well_id
            or (
                histories
                and resolve_lifecycle_stage(fund_well, record, histories).issue is not None
            )
        )
        if unresolved_variants:
            return MatchResult(
                status=MatchStatus.AMBIGUOUS,
                fund_well=fund_well,
                candidates=unresolved_variants,
                explanation=(
                    "Найдено обозначение с тем же физическим корнем, но его жизненный цикл "
                    "не удалось однозначно связать с текущей записью фонда."
                ),
            )
        return MatchResult(
            status=MatchStatus.NO_GDI,
            fund_well=fund_well,
            explanation="Релевантная запись ГДИ для этого номера и месторождения не найдена.",
        )

    if fund_well.object_plast_hint is not None:
        hinted = tuple(
            record
            for record in candidates
            if record.normalized_plast == fund_well.object_plast_hint
        )
        if hinted:
            candidates = hinted

    latest_date = max(record.study_date for record in candidates if record.study_date is not None)
    latest = tuple(record for record in candidates if record.study_date == latest_date)
    distinct: dict[tuple[str | None, str | None, str | None], GdiRecord] = {}
    for record in latest:
        target_id = record.target_well_id or (
            normalize_well_id(record.raw_well_name).target_well_id
            if record.raw_well_name is not None
            else None
        )
        distinct.setdefault((target_id, record.normalized_plast, record.normalized_field), record)
    distinct_records = tuple(distinct.values())
    if len(distinct_records) != 1:
        candidate_text = "; ".join(
            f"{record.raw_well_name!r}/{record.raw_plast!r}" for record in distinct_records
        )
        return MatchResult(
            status=MatchStatus.AMBIGUOUS,
            fund_well=fund_well,
            candidates=distinct_records,
            explanation=(
                f"На максимальную дату {latest_date:%d.%m.%Y} осталось несколько несовместимых "
                f"конфигураций: {candidate_text}."
            ),
        )
    return MatchResult(
        status=MatchStatus.MATCHED,
        fund_well=fund_well,
        record=distinct_records[0],
        candidates=distinct_records,
        explanation=f"Однозначная запись ГДИ на дату {latest_date:%d.%m.%Y}.",
    )


def match_all(
    fund_wells: Iterable[FundWell],
    gdi_index: GdiIndex,
    histories: tuple[WellHistory, ...] = (),
) -> tuple[tuple[MatchResult, ...], tuple[DiagnosticIssue, ...]]:
    """Match the full fund and emit concise diagnostics for non-matches."""

    results: list[MatchResult] = []
    issues: list[DiagnosticIssue] = []
    for fund_well in fund_wells:
        result = match_fund_well(fund_well, gdi_index, histories)
        results.append(result)
        if result.status is MatchStatus.AMBIGUOUS:
            lifecycle_issues = tuple(
                resolution.issue
                for record in result.candidates
                if (resolution := resolve_lifecycle_stage(fund_well, record, histories)).issue
                is not None
            )
            issues.extend(lifecycle_issues)
            issues.append(
                DiagnosticIssue(
                    code="GDI_AMBIGUOUS_MATCH",
                    severity=IssueSeverity.WARNING,
                    message=result.explanation,
                    source="gdi",
                    well_id=fund_well.base_well_id,
                    locations=(
                        *fund_well.locations,
                        *(
                            location
                            for record in result.candidates
                            for location in record.locations
                        ),
                    ),
                )
            )
        elif result.status is MatchStatus.NO_GDI:
            issues.append(
                DiagnosticIssue(
                    code="GDI_NOT_FOUND",
                    severity=IssueSeverity.INFO,
                    message=result.explanation,
                    source="gdi",
                    well_id=fund_well.base_well_id,
                    locations=fund_well.locations,
                )
            )
        elif result.status is MatchStatus.INVALID_SOURCE:
            issues.append(
                DiagnosticIssue(
                    code="GDI_INVALID_FUND_KEY",
                    severity=IssueSeverity.ERROR,
                    message=result.explanation,
                    source="fund",
                    well_id=fund_well.base_well_id,
                    locations=fund_well.locations,
                )
            )
    return tuple(results), tuple(issues)
