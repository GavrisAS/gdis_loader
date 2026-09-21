"""Conservative GDI matching by physical well, field, object, and date."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, time

from gdis_loader.domain.models import (
    DiagnosticIssue,
    FundWell,
    GdiRecord,
    IssueSeverity,
    MatchResult,
    MatchStatus,
)


class GdiIndex:
    """Index valid GDI records once; no source workbook is reread per well."""

    def __init__(self, records: Iterable[GdiRecord]) -> None:
        grouped: defaultdict[str, list[GdiRecord]] = defaultdict(list)
        for record in records:
            if (
                record.base_well_id is not None
                and record.normalized_field is not None
                and record.normalized_plast is not None
                and record.study_date is not None
            ):
                grouped[record.base_well_id].append(record)
        self._by_base_well = {key: tuple(items) for key, items in grouped.items()}

    def candidates_for(self, fund_well: FundWell) -> tuple[GdiRecord, ...]:
        """Return field-qualified records relevant on the fund date."""

        if fund_well.base_well_id is None:
            return ()
        cutoff = datetime.combine(fund_well.fund_date, time.max)
        return tuple(
            record
            for record in self._by_base_well.get(fund_well.base_well_id, ())
            if record.normalized_field == fund_well.normalized_field
            and record.study_date is not None
            and record.study_date <= cutoff
        )


def match_fund_well(fund_well: FundWell, gdi_index: GdiIndex) -> MatchResult:
    """Resolve one fund well without choosing among equal latest candidates."""

    if fund_well.base_well_id is None:
        return MatchResult(
            status=MatchStatus.INVALID_SOURCE,
            fund_well=fund_well,
            explanation="Номер скважины фонда не удалось нормализовать.",
        )
    candidates = gdi_index.candidates_for(fund_well)
    if not candidates:
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
        distinct.setdefault(record.completion_key, record)
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
) -> tuple[tuple[MatchResult, ...], tuple[DiagnosticIssue, ...]]:
    """Match the full fund and emit concise diagnostics for non-matches."""

    results: list[MatchResult] = []
    issues: list[DiagnosticIssue] = []
    for fund_well in fund_wells:
        result = match_fund_well(fund_well, gdi_index)
        results.append(result)
        if result.status is MatchStatus.AMBIGUOUS:
            issues.append(
                DiagnosticIssue(
                    code="GDI_AMBIGUOUS_MATCH",
                    severity=IssueSeverity.WARNING,
                    message=result.explanation,
                    source="gdi",
                    well_id=fund_well.base_well_id,
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
                )
            )
    return tuple(results), tuple(issues)
