"""Application service shared by the CLI and the Qt GUI."""

from __future__ import annotations

import json
import logging
import platform
import re
import tempfile
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, date, datetime, time
from pathlib import Path

from gdis_loader import __version__
from gdis_loader.config import CriteriaConfig
from gdis_loader.domain.dates import date_defaulting_rule, effective_date
from gdis_loader.domain.models import (
    DailyTelemetryRow,
    DatePrecision,
    DiagnosticIssue,
    FundCategory,
    FundParseResult,
    FundWell,
    GdiKind,
    GdiRecord,
    IssueSeverity,
    LoadReport,
    MatchStatus,
    ResearchStatusRecord,
    SourceLocation,
    SourcePaths,
    TargetRow,
    WellEventKind,
    WellHistory,
    WellHistoryParseResult,
    WellStage,
)
from gdis_loader.excel.writer import TargetWriteResult, write_target_rows
from gdis_loader.matching.lifecycle import (
    LifecycleResolution,
    assign_stage_by_date,
    resolve_lifecycle_stage,
)
from gdis_loader.matching.matcher import GdiIndex, match_all
from gdis_loader.matching.normalize import normalize_field_name, normalize_well_id
from gdis_loader.progress import ProgressCallback, ProgressUpdate
from gdis_loader.readers.daily import read_daily_report
from gdis_loader.readers.fund import read_fund
from gdis_loader.readers.gdi import read_gdi
from gdis_loader.readers.lha import LhaIndex, read_lha
from gdis_loader.readers.research_status import STATUS_SHEETS, read_research_status
from gdis_loader.readers.well_history import FIELD_SHEETS, read_well_history
from gdis_loader.transforms.aggregates import (
    chlorine_growth,
    count_gdi_since_launch,
    duration_years,
    insufficient_gdi_from_bounds,
    mean_working_day_rate,
    productivity_decline,
)
from gdis_loader.transforms.gdi import collapse_exact_gdi_duplicates
from gdis_loader.transforms.research_status import gdm_problem, select_gdm_delta
from gdis_loader.transforms.rules import (
    downhole_condition,
    lnd_condition,
    specific_gdi_count,
)
from gdis_loader.validation.sources import (
    ValidationResult,
    validate_inputs,
    validate_output_path,
)

LOGGER = logging.getLogger(__name__)


def _gdm_delta_is_missing(value: object) -> bool:
    if value is None:
        return True
    return str(value).strip() in {"", "-", "—", "–"}


class ServiceError(RuntimeError):
    """Human-readable application failure with details already in the report."""


class ServiceResult:
    """Successful service result returned to both front ends."""

    def __init__(self, report: LoadReport, output_path: Path | None = None) -> None:
        self.report = report
        self.output_path = output_path

    @property
    def error_count(self) -> int:
        return sum(issue.severity is IssueSeverity.ERROR for issue in self.report.issues)

    @property
    def warning_count(self) -> int:
        return sum(issue.severity is IssueSeverity.WARNING for issue in self.report.issues)

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0

    @property
    def has_capacity_warning(self) -> bool:
        return any(
            issue.code == "DATA_ROWS_EXCEED_CALCULATOR_FORMULA_CAPACITY"
            for issue in self.report.issues
        )

    def issue_count(self, code: str) -> int:
        """Return the number of diagnostics with the supplied code."""

        return sum(issue.code == code for issue in self.report.issues)

    def summary(self) -> str:
        report = self.report
        lines = [
            f"Скважин в фонде: {report.fund_total}",
        ]
        if report.target_field is None:
            lines.append(f"Обнаружено месторождений: {len(report.available_fields)}")
            lines.extend(f"  • {field_name}" for field_name in report.available_fields)
            for field_name in report.available_fields:
                coverage = report.field_coverage.get(field_name, {})
                history_status = (
                    "лист есть" if coverage.get("well_history_sheet_present") else "листа нет"
                )
                status_status = (
                    "лист есть" if coverage.get("research_status_sheet_present") else "листа нет"
                )
                lines.append(
                    f"Покрытие {field_name}: фонд {coverage.get('fund_rows', 0)}, "
                    f"ГДИ {coverage.get('gdi_rows', 0)}, ЛХА {coverage.get('lha_rows', 0)}, "
                    f"история: {history_status}, статус ГДМ: {status_status}"
                )
        else:
            lines.extend(
                (
                    f"Месторождение: {report.target_field}",
                    f"Фонд выбранного месторождения: {report.target_field_fund_total}",
                    f"Допущено к рейтингу: {report.rating_eligible}",
                    f"Однозначно сопоставлено: {report.matched}",
                    f"Неоднозначно: {report.ambiguous}",
                    f"Без ГДИ: {report.no_gdi}",
                    f"Без выбранных значений ЛХА: {report.without_lha}",
                    f"Подготовлено строк: {report.rows_prepared}",
                    f"Записано строк: {report.rows_written}",
                )
            )
        lines.extend((f"Ошибок: {self.error_count}", f"Предупреждений: {self.warning_count}"))
        collision_count = self.issue_count("TARGET_IDENTITY_COLLISION")
        if collision_count:
            lines.append(f"Коллизий целевой идентичности: {collision_count}")
        separator_count = self.issue_count("FUND_MISSING_SEPARATOR_NORMALIZED")
        if separator_count:
            lines.append(f"Нормализаций пропущенного разделителя фонда: {separator_count}")
        if self.has_capacity_warning:
            lines.append(
                "ВНИМАНИЕ: строки после 100 пока не рассчитываются на листах «Расчет» и «Рейтинг»."
            )
        if report.output_path:
            lines.append(f"Результат: {report.output_path}")
        if report.diagnostic_path:
            lines.append(f"Диагностика: {report.diagnostic_path}")
        return "\n".join(lines)


def _safe_field_filename(field_name: str) -> str:
    safe = re.sub(r"[/\\:*?\"<>|]+", "_", field_name.strip())
    safe = re.sub(r"[\s_]+", "_", safe).strip(" _.")
    return safe or "field"


def default_output_path(calculator: Path, field_name: str) -> Path:
    """Name a result copy after an explicitly selected canonical field."""

    suffix = calculator.suffix or ".xlsx"
    return calculator.with_name(
        f"{calculator.stem}_UPDATED_{_safe_field_filename(field_name)}{suffix}"
    )


def diagnostic_path(output: Path | None, calculator: Path | None = None) -> Path:
    if output is not None:
        return output.with_suffix(".load-report.json")
    if calculator is None:
        raise ValueError("Для валидации без результата требуется путь калькулятора.")
    return calculator.with_name(f"{calculator.stem}_validation.load-report.json")


def configure_logging(path: Path) -> Path:
    """Create one UTF-8 file handler near the selected output/config."""

    path.parent.mkdir(parents=True, exist_ok=True)
    package_logger = logging.getLogger("gdis_loader")
    package_logger.setLevel(logging.INFO)
    package_logger.propagate = False
    wanted = path.resolve()
    for handler in list(package_logger.handlers):
        if (
            isinstance(handler, logging.FileHandler)
            and Path(handler.baseFilename).resolve() == wanted
        ):
            return path
        if isinstance(handler, logging.FileHandler):
            package_logger.removeHandler(handler)
            handler.close()
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    package_logger.addHandler(handler)
    return path


def _new_report(
    paths: SourcePaths,
    calculation_date: date,
    target_field: str | None = None,
) -> LoadReport:
    return LoadReport(
        timestamp=datetime.now(UTC).isoformat(),
        app_version=__version__,
        python_version=platform.python_version(),
        input_paths={
            "calculator": str(paths.calculator.resolve()),
            "fund": str(paths.fund.resolve()),
            "gdi": str(paths.gdi.resolve()),
            "lha": str(paths.lha.resolve()),
            "daily_report": str(paths.daily_report.resolve()),
            "well_history": str(paths.well_history.resolve()),
            "research_status": str(paths.research_status.resolve()),
            "output": str(paths.output.resolve()) if paths.output is not None else None,
        },
        calculation_date=calculation_date,
        target_field=target_field,
    )


def _criteria_snapshot(
    criteria: CriteriaConfig,
    explicit_fields: frozenset[str],
    source: str | Path | None,
) -> dict[str, object]:
    values = criteria.as_dict()
    defaults = CriteriaConfig().as_dict()
    explicit = set(explicit_fields)
    return {
        "config_source": str(source) if source is not None else None,
        "values": values,
        "defaults": defaults,
        "value_origin": {name: "config" if name in explicit else "default" for name in values},
    }


def _append_issues(report: LoadReport, issues: Iterable[DiagnosticIssue]) -> None:
    for issue in issues:
        if issue in report.issues:
            continue
        report.issues.append(issue)
        if issue.code == "LHA_DUPLICATE_TIMESTAMP_RESOLVED_MAX":
            report.lha_duplicate_resolved_max += 1
        if issue.severity is IssueSeverity.WARNING:
            report.warnings.append(issue.message)
        if issue.severity is IssueSeverity.INFO:
            LOGGER.info("%s", format_diagnostic_issue(issue))
        elif issue.severity is IssueSeverity.WARNING:
            LOGGER.warning("%s", format_diagnostic_issue(issue))
        elif issue.severity is IssueSeverity.ERROR:
            LOGGER.error("%s", format_diagnostic_issue(issue))


def format_diagnostic_issue(issue: DiagnosticIssue) -> str:
    """Format one issue for a plain-text log without losing provenance."""

    if not issue.locations:
        return f"{issue.code}: {issue.message}"
    locations = "; ".join(
        "::".join(
            part for part in (location.file, location.sheet, location.cell) if part is not None
        )
        for location in issue.locations
    )
    return (
        f'{issue.severity.value.upper()} [{issue.code}] {issue.message} | locations="{locations}"'
    )


def _report_progress(progress: ProgressCallback | None, percent: int, stage: str) -> None:
    if progress is not None:
        progress(ProgressUpdate(percent, stage))


def _write_report(report: LoadReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            json.dump(report.to_dict(), temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
        Path(temporary_name).replace(path)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def _validation_failure(validation: ValidationResult) -> str:
    return "\n".join(f"- {format_diagnostic_issue(issue)}" for issue in validation.errors)


def _report_error_text(report: LoadReport) -> str:
    return "\n".join(
        f"- {format_diagnostic_issue(issue)}"
        for issue in report.issues
        if issue.severity is IssueSeverity.ERROR
    )


def _unique_locations(locations: Iterable[SourceLocation]) -> tuple[SourceLocation, ...]:
    """Keep provenance complete while avoiding repeated source addresses."""

    result: list[SourceLocation] = []
    seen: set[SourceLocation] = set()
    for location in locations:
        if location not in seen:
            result.append(location)
            seen.add(location)
    return tuple(result)


def _append_target_identity_collisions(
    evidence: Iterable[tuple[TargetRow, FundWell, GdiRecord]],
    report: LoadReport,
) -> None:
    """Report target-key collisions without changing either target value."""

    groups: defaultdict[tuple[str, str], list[tuple[TargetRow, FundWell, GdiRecord]]] = defaultdict(
        list
    )
    for target_row, fund_well, gdi_record in evidence:
        if target_row.well is None or target_row.plast is None:
            continue
        groups[(str(target_row.well), str(target_row.plast))].append(
            (target_row, fund_well, gdi_record)
        )

    for (target_well, target_plast), rows in groups.items():
        normalized_fields = {fund_well.normalized_field for _, fund_well, _ in rows}
        if len(normalized_fields) < 2:
            continue
        field_names = list(dict.fromkeys(fund_well.field_name for _, fund_well, _ in rows))
        fields_text = ", ".join(field_names)
        locations = _unique_locations(
            location
            for _, fund_well, gdi_record in rows
            for location in (*fund_well.locations, *gdi_record.locations)
        )
        _append_issues(
            report,
            (
                DiagnosticIssue(
                    code="TARGET_IDENTITY_COLLISION",
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Одинаковый целевой идентификатор «{target_well} + {target_plast}» "
                        f"относится к разным месторождениям ({fields_text}); калькулятор "
                        "не хранит месторождение отдельным полем."
                    ),
                    source="target_identity",
                    well_id=target_well,
                    locations=locations,
                ),
            ),
        )


def _launch_date_for_target(
    fund_well: FundWell,
    record: GdiRecord | None,
    histories: tuple[WellHistory, ...],
    report: LoadReport,
    resolution: LifecycleResolution | None = None,
) -> date | None:
    """Return the agreed effective launch date while reporting source precision."""

    resolution = resolution or resolve_lifecycle_stage(fund_well, record, histories)
    if resolution.issue is not None:
        report.launch_date_missing += 1
        _append_issues(report, (resolution.issue,))
        return None
    stage = resolution.stage
    if stage is None:
        report.launch_date_missing += 1
        locations = list(fund_well.locations)
        if record is not None:
            locations.extend(record.locations)
        _append_issues(
            report,
            (
                DiagnosticIssue(
                    code="WELL_HISTORY_STAGE_NOT_FOUND",
                    severity=IssueSeverity.WARNING,
                    message="Для целевой идентичности не найдена однозначная дата начала истории.",
                    source="well_history",
                    well_id=fund_well.base_well_id,
                    locations=_unique_locations(locations),
                ),
            ),
        )
        return None

    launch = stage.started_at
    effective = effective_date(launch)
    if launch.precision is not DatePrecision.DAY:
        report.launch_date_defaulted += 1
        _append_issues(
            report,
            (
                DiagnosticIssue(
                    code="LAUNCH_DATE_DEFAULTED_BY_CUSTOMER_RULE",
                    severity=IssueSeverity.INFO,
                    message=(
                        f"Источник содержит дату с точностью {launch.precision.value}; "
                        f"для расчетов использована {effective.isoformat()} "
                        "по согласованному правилу."
                    ),
                    source="well_history",
                    well_id=fund_well.base_well_id,
                    locations=(stage.source_location,),
                ),
            ),
        )
    report.launch_date_filled += 1
    return effective


def _append_field_provenance(
    report: LoadReport,
    well_id: str | None,
    field_name: str,
    locations: Iterable[SourceLocation],
    **details: object,
) -> None:
    unique = _unique_locations(locations)
    report.field_provenance.append(
        {
            "well_id": well_id,
            "field": field_name,
            "locations": [location.to_dict() for location in unique],
            "details": details,
        }
    )


def _effective_target_identity(
    fund_well: FundWell, record: GdiRecord | None, stage: WellStage | None
) -> str | None:
    if stage is not None:
        if stage.target_well_id:
            return stage.target_well_id
        if stage.event_kind is WellEventKind.INITIAL:
            return (
                fund_well.target_well_id
                or (record.target_well_id if record is not None else None)
                or stage.physical_root
            )
        if stage.event_kind is WellEventKind.ZBS:
            return f"{stage.physical_root}_ЗБС"
        if stage.event_kind in {WellEventKind.PVLG, WellEventKind.PNLG}:
            source_identity = (
                record.target_well_id if record is not None else fund_well.target_well_id
            )
            if source_identity and source_identity != stage.physical_root:
                return source_identity
            return stage.physical_root
    if record is not None:
        return record.target_well_id or record.raw_well_name
    return fund_well.target_well_id or fund_well.raw_display


def _gdi_history_for_target(
    fund_well: FundWell,
    selected: GdiRecord,
    history_records: tuple[GdiRecord, ...],
    histories: tuple[WellHistory, ...],
    selected_stage: WellStage | None,
) -> tuple[GdiRecord, ...]:
    """Return valid rows assigned to the selected lifecycle and exact plast."""

    return _gdi_history_for_stage(
        fund_well,
        history_records,
        histories,
        selected_stage,
        selected.normalized_plast,
        selected.target_well_id,
    )


def _gdi_history_for_stage(
    fund_well: FundWell,
    history_records: tuple[GdiRecord, ...],
    histories: tuple[WellHistory, ...],
    selected_stage: WellStage | None,
    normalized_plast: str | None,
    selected_identity: str | None = None,
) -> tuple[GdiRecord, ...]:
    """Return valid rows on one resolved lifecycle stage and normalized plast."""

    matching: list[GdiRecord] = []
    for record in history_records:
        if record.normalized_plast != normalized_plast:
            continue
        resolution = resolve_lifecycle_stage(fund_well, record, histories)
        if selected_stage is not None:
            if resolution.stage == selected_stage:
                matching.append(record)
        elif record.target_well_id == selected_identity:
            matching.append(record)
    return tuple(
        sorted(
            matching,
            key=lambda record: (record.study_date or datetime.min, record.source_row),
        )
    )


def _prelaunch_gdi_records_for_stage(
    fund_well: FundWell,
    records: tuple[GdiRecord, ...],
    histories: tuple[WellHistory, ...],
    stage: WellStage,
) -> tuple[GdiRecord, ...]:
    """Find same-identity/plast valid rows before the agreed launch day."""

    launch_day = effective_date(stage.started_at)
    result: list[GdiRecord] = []
    for record in records:
        if (
            record.gdi_kind not in {GdiKind.ID, GdiKind.ID_KVD, GdiKind.KVD}
            or record.normalized_plast != stage.plast
            or record.study_date is None
            or record.study_date.date() >= launch_day
        ):
            continue
        resolution = resolve_lifecycle_stage(fund_well, record, histories)
        stage_identity = stage.target_well_id or stage.physical_root
        source_identity = (
            record.target_well_id or normalize_well_id(record.raw_well_name or "").target_well_id
        )
        same_unlaunched_identity = (
            stage.event_kind is WellEventKind.INITIAL and source_identity == stage.physical_root
        ) or (stage.event_kind is WellEventKind.ZBS and source_identity == stage_identity)
        if resolution.stage == stage or (resolution.stage is None and same_unlaunched_identity):
            result.append(record)
    return tuple(result)


def _status_candidates_for_target(
    fund_well: FundWell,
    target_well_id: str,
    normalized_plast: str | None,
    lifecycle_stage: WellStage | None,
    records: tuple[ResearchStatusRecord, ...],
    histories: tuple[WellHistory, ...],
) -> tuple[tuple[ResearchStatusRecord, ...], tuple[DiagnosticIssue, ...]]:
    """Match GDM rows conservatively and retain partial-date/plast ambiguity."""

    if fund_well.base_well_id is None:
        return (), ()
    result: list[ResearchStatusRecord] = []
    issue_groups: dict[str, tuple[str, list[SourceLocation]]] = {}

    def add_issue(
        code: str,
        message: str,
        record: ResearchStatusRecord,
        extra_locations: Iterable[SourceLocation] = (),
    ) -> None:
        locations = issue_groups.setdefault(code, (message, []))[1]
        locations.extend(
            (
                *record.locations,
                *extra_locations,
            )
        )

    for record in records:
        field_name = FIELD_SHEETS.get(record.source_sheet.removeprefix("АР_таблица_"), "")
        if (
            normalize_field_name(field_name) != fund_well.normalized_field
            or record.base_well_id != fund_well.base_well_id
        ):
            continue

        exact_lifecycle_identity = (
            record.target_well_id == target_well_id and target_well_id != fund_well.base_well_id
        )
        root_only_identity = record.target_well_id == fund_well.base_well_id
        if not exact_lifecycle_identity and not root_only_identity:
            continue

        if exact_lifecycle_identity:
            if lifecycle_stage is not None:
                if record.study_date is None:
                    add_issue(
                        "WELL_HISTORY_STAGE_AMBIGUOUS",
                        "Строка статуса с lifecycle suffix без даты не может быть отнесена "
                        "к текущему этапу.",
                        record,
                        (lifecycle_stage.source_location,),
                    )
                    continue
                assignment = assign_stage_by_date(
                    physical_root=fund_well.base_well_id,
                    normalized_field=fund_well.normalized_field,
                    normalized_plast=normalized_plast or "",
                    observed_at=record.study_date,
                    histories=histories,
                    observation_location=SourceLocation(
                        record.source_file,
                        record.source_sheet,
                        record.date_cell,
                    ),
                )
                if assignment.stage != lifecycle_stage:
                    if assignment.issue is not None:
                        add_issue(
                            assignment.issue.code,
                            assignment.issue.message,
                            record,
                            assignment.issue.locations,
                        )
                    continue
            if record.normalized_plast == normalized_plast:
                result.append(record)
            elif lifecycle_stage is not None:
                add_issue(
                    "UNRESOLVED_PLAST_EQUIVALENCE",
                    "Статус ГДМ имеет ту же lifecycle identity, но другое обозначение пласта; "
                    "эквивалентность не предполагается.",
                    record,
                    (lifecycle_stage.source_location,),
                )
            continue

        observation_location = SourceLocation(
            record.source_file,
            record.source_sheet,
            record.date_cell,
        )
        if record.study_date is None:
            if lifecycle_stage is not None:
                add_issue(
                    "WELL_HISTORY_STAGE_AMBIGUOUS",
                    "Строка статуса ГДМ без даты не может быть отнесена к lifecycle-этапу.",
                    record,
                    (lifecycle_stage.source_location,),
                )
            continue

        if normalized_plast is None or record.normalized_plast != normalized_plast:
            if lifecycle_stage is None or lifecycle_stage.plast is None:
                continue
            assignment = assign_stage_by_date(
                physical_root=fund_well.base_well_id,
                normalized_field=fund_well.normalized_field,
                normalized_plast=lifecycle_stage.plast,
                observed_at=record.study_date,
                histories=histories,
                observation_location=observation_location,
            )
            if assignment.issue is not None:
                add_issue(
                    assignment.issue.code,
                    assignment.issue.message,
                    record,
                    assignment.issue.locations,
                )
            elif assignment.stage == lifecycle_stage:
                add_issue(
                    "UNRESOLVED_PLAST_EQUIVALENCE",
                    "Дата строки статуса ГДМ соответствует текущему этапу, но обозначение "
                    "пласта отличается; эквивалентность не предполагается.",
                    record,
                    (lifecycle_stage.source_location,),
                )
            continue

        assignment = assign_stage_by_date(
            physical_root=fund_well.base_well_id,
            normalized_field=fund_well.normalized_field,
            normalized_plast=normalized_plast,
            observed_at=record.study_date,
            histories=histories,
            observation_location=observation_location,
        )
        if assignment.stage is not None and assignment.stage == lifecycle_stage:
            result.append(record)
        elif assignment.issue is not None:
            add_issue(
                assignment.issue.code,
                assignment.issue.message,
                record,
                assignment.issue.locations,
            )
    issues = tuple(
        DiagnosticIssue(
            code=code,
            severity=IssueSeverity.WARNING,
            message=message,
            source="research_status",
            well_id=fund_well.base_well_id,
            locations=_unique_locations(locations),
        )
        for code, (message, locations) in issue_groups.items()
    )
    return tuple(result), issues


def _target_state(well: FundWell) -> str:
    if well.source_category in {FundCategory.PRODUCING, FundCategory.PRODUCING_GAS}:
        return "Дающие газ"
    if well.source_category is FundCategory.STOPPED_IN_REPORTING_MONTH:
        return "Остановленные в отчетном периоде"
    return ""


def _gdi_locations(record: GdiRecord, *cell_names: str) -> tuple[SourceLocation, ...]:
    return tuple(
        SourceLocation(
            record.source_file,
            record.source_sheet,
            re.sub(r"\d+$", str(row), cell),
        )
        for row in (record.source_rows or (record.source_row,))
        for name in cell_names
        if (cell := getattr(record, name)) is not None and record.source_file
    )


def _daily_record_for_target(
    fund_well: FundWell,
    target_well_id: str,
    all_fund_wells: tuple[FundWell, ...],
    daily_rows: tuple[DailyTelemetryRow, ...],
) -> tuple[DailyTelemetryRow | None, str | None]:
    """Select one daily row without joining the same number across fields."""

    source_matches = tuple(item for item in daily_rows if item.target_well_id == target_well_id)
    if not source_matches and fund_well.base_well_id is not None:
        source_matches = tuple(
            item for item in daily_rows if item.target_well_id == fund_well.base_well_id
        )
    if not source_matches:
        return None, "DEBIT_SOURCE_ROW_MISSING"

    canonical_rows = tuple(
        item
        for item in source_matches
        if item.raw_field_name
        and normalize_field_name(item.raw_field_name) == fund_well.normalized_field
    )
    if canonical_rows:
        source_matches = canonical_rows
    elif any(
        item.raw_field_name
        and normalize_field_name(item.raw_field_name)
        in {normalize_field_name(value) for value in FIELD_SHEETS.values()}
        for item in source_matches
    ):
        return None, "DEBIT_SOURCE_FIELD_MISMATCH"
    else:
        related_fields = {
            item.normalized_field
            for item in all_fund_wells
            if item.base_well_id == fund_well.base_well_id
        }
        if related_fields != {fund_well.normalized_field}:
            return None, "DEBIT_SOURCE_FIELD_AMBIGUOUS"

    if len(source_matches) != 1:
        return None, "DEBIT_SOURCE_ROW_AMBIGUOUS"
    return source_matches[0], None


def _build_target_rows(
    fund: FundParseResult,
    gdi_index: GdiIndex,
    lha_index: LhaIndex,
    report: LoadReport,
    histories: tuple[WellHistory, ...] = (),
    calculation_date: date | None = None,
    research_status: tuple[ResearchStatusRecord, ...] = (),
    criteria: CriteriaConfig | None = None,
    daily_rows: tuple[DailyTelemetryRow, ...] = (),
) -> tuple[TargetRow, ...]:
    if report.target_field is None:
        raise ValueError("Для подготовки target rows требуется выбранное месторождение.")
    criteria = criteria or CriteriaConfig()
    target_field = normalize_field_name(report.target_field)
    scoped_wells = tuple(well for well in fund.wells if well.normalized_field == target_field)
    eligible_wells = tuple(well for well in scoped_wells if well.is_rating_eligible)
    matches, match_issues = match_all(eligible_wells, gdi_index, histories)
    _append_issues(report, match_issues)
    report.fund_total_source = len(fund.wells)
    report.target_field_fund_total = len(scoped_wells)
    report.fund_total = report.fund_total_source
    report.rating_eligible = len(eligible_wells)
    report.rating_not_eligible = len(scoped_wells) - report.rating_eligible
    report.excluded_status_counts = {
        category.value: sum(
            well.source_category is category and not well.is_rating_eligible
            for well in scoped_wells
        )
        for category in FundCategory
        if any(
            well.source_category is category and not well.is_rating_eligible
            for well in scoped_wells
        )
    }
    target_rows: list[TargetRow] = []
    target_identity_evidence: list[tuple[TargetRow, FundWell, GdiRecord]] = []
    for match in matches:
        fund_well = match.fund_well
        state = _target_state(fund_well)
        if match.status is MatchStatus.MATCHED and match.record is not None:
            record = match.record
            lifecycle = resolve_lifecycle_stage(fund_well, record, histories)
            launch_date = _launch_date_for_target(
                fund_well,
                record,
                histories,
                report,
                lifecycle,
            )
            effective_identity = (
                _effective_target_identity(fund_well, record, lifecycle.stage)
                or record.target_well_id
                or record.raw_well_name
                or fund_well.raw_display
            )
            if (
                record.target_well_id == fund_well.base_well_id
                and lifecycle.stage is not None
                and lifecycle.stage.event_kind is not WellEventKind.INITIAL
            ):
                report.unsuffixed_gdi_assigned += 1
            row_provenance: dict[str, tuple[SourceLocation, ...]] = {}
            row_provenance_details: dict[str, dict[str, object]] = {}
            launch_locations = (
                (lifecycle.stage.source_location,) if lifecycle.stage is not None else ()
            )
            if launch_date is not None:
                row_provenance["Дата запуска"] = launch_locations

            history_records = _gdi_history_for_target(
                fund_well,
                record,
                gdi_index.history_for(fund_well),
                histories,
                lifecycle.stage,
            )
            launch_partial = lifecycle.stage.started_at if lifecycle.stage is not None else None
            gdi_count: int | None = None
            insufficient_value: bool | None = None
            count_bounds = None
            if launch_partial is None:
                _append_issues(
                    report,
                    (
                        DiagnosticIssue(
                            code="GDI_COUNT_LAUNCH_UNRESOLVED",
                            severity=IssueSeverity.WARNING,
                            message=(
                                "Количество ГДИ после запуска не вычислено: lifecycle-граница "
                                "не определена однозначно."
                            ),
                            source="well_history",
                            well_id=fund_well.base_well_id,
                            locations=_unique_locations((*fund_well.locations, *record.locations)),
                        ),
                    ),
                )
            else:
                count_bounds = count_gdi_since_launch(history_records, launch_partial)
                gdi_count = count_bounds.exact_count
                insufficient_value = insufficient_gdi_from_bounds(
                    count_bounds, criteria.insufficient_gdi_min_count
                )
                count_locations = tuple(
                    location
                    for gdi_record in (
                        *count_bounds.definite_records,
                        *count_bounds.ambiguous_records,
                    )
                    for location in _gdi_locations(
                        gdi_record, "well_cell", "plast_cell", "date_cell"
                    )
                )
                if gdi_count is not None:
                    assert lifecycle.stage is not None
                    report.gdi_count_filled += 1
                    report.gdi_pre_launch_excluded += len(
                        _prelaunch_gdi_records_for_stage(
                            fund_well,
                            gdi_index.history_for(fund_well),
                            histories,
                            lifecycle.stage,
                        )
                    )
                    row_provenance["Количество ГДИ"] = _unique_locations(
                        (*launch_locations, *count_locations)
                    )
                if insufficient_value is not None:
                    if insufficient_value:
                        report.insufficient_gdi_yes += 1
                    else:
                        report.insufficient_gdi_no += 1
                    row_provenance["Недостаточно ГДИС"] = _unique_locations(
                        (*launch_locations, *count_locations)
                    )
                if count_bounds.ambiguous_records:
                    ambiguity_locations = tuple(
                        location
                        for gdi_record in count_bounds.ambiguous_records
                        for location in _gdi_locations(
                            gdi_record, "well_cell", "plast_cell", "date_cell"
                        )
                    )
                    _append_issues(
                        report,
                        (
                            DiagnosticIssue(
                                code="GDI_COUNT_AMBIGUOUS_LAUNCH_PRECISION",
                                severity=IssueSeverity.WARNING,
                                message=(
                                    "Исследование находится в окне неполной даты запуска; "
                                    "точное количество ГДИ оставлено пустым."
                                ),
                                source="gdi",
                                well_id=fund_well.base_well_id,
                                locations=_unique_locations(
                                    (*launch_locations, *ambiguity_locations)
                                ),
                            ),
                        ),
                    )
                if insufficient_value is None:
                    _append_issues(
                        report,
                        (
                            DiagnosticIssue(
                                code="GDI_COUNT_AMBIGUOUS_LAUNCH_PRECISION",
                                severity=IssueSeverity.WARNING,
                                message=(
                                    "Неполная дата запуска не позволяет определить по границам, "
                                    "срабатывает ли признак «Недостаточно ГДИС»."
                                ),
                                source="gdi",
                                well_id=fund_well.base_well_id,
                                locations=_unique_locations((*launch_locations, *count_locations)),
                            ),
                        ),
                    )

            if launch_date is not None and gdi_count is not None:
                specific_value = specific_gdi_count(
                    calculation_date or report.calculation_date or fund_well.fund_date,
                    launch_date,
                    gdi_count,
                )
                if specific_value is not None:
                    report.specific_gdi_count_filled += 1
                    row_provenance["Удельное количество ГДИ"] = _unique_locations(
                        (*launch_locations, *count_locations)
                    )
                else:
                    _append_issues(
                        report,
                        (
                            DiagnosticIssue(
                                code="GDI_SPECIFIC_RATE_ZERO_COUNT",
                                severity=IssueSeverity.INFO,
                                message=(
                                    "Количество ГДИ равно нулю; удельное количество оставлено "
                                    "пустым, μi=0 не включает критерий в итоговый коэффициент."
                                ),
                                source="gdi",
                                well_id=fund_well.base_well_id,
                                locations=launch_locations,
                            ),
                        ),
                    )
            else:
                specific_value = None

            current_history = history_records
            numeric_a_records = tuple(
                item for item in current_history if item.productivity_a_value is not None
            )
            productivity_value: str | None = None
            if len(numeric_a_records) >= 2:
                previous_a, current_a = numeric_a_records[-2:]
                assert previous_a.productivity_a_value is not None
                assert current_a.productivity_a_value is not None
                productivity_value = (
                    "Да"
                    if productivity_decline(
                        previous_a.productivity_a_value,
                        current_a.productivity_a_value,
                        criteria.productivity_min_increase,
                    )
                    else "Нет"
                )
                report.productivity_filled += 1
                row_provenance["Снижение продуктивности"] = _unique_locations(
                    (
                        *_gdi_locations(previous_a, "date_cell", "productivity_a_cell"),
                        *_gdi_locations(current_a, "date_cell", "productivity_a_cell"),
                    )
                )
            else:
                history_a_locations = tuple(
                    location
                    for gdi_record in current_history[-2:]
                    for location in _gdi_locations(gdi_record, "date_cell", "productivity_a_cell")
                )
                _append_issues(
                    report,
                    (
                        DiagnosticIssue(
                            code="PRODUCTIVITY_INSUFFICIENT_A_HISTORY",
                            severity=IssueSeverity.WARNING,
                            message=(
                                "Для сравнения коэффициента a не хватает двух валидных числовых "
                                "значений текущей lifecycle-истории."
                            ),
                            source="gdi",
                            well_id=fund_well.base_well_id,
                            locations=history_a_locations,
                        ),
                    ),
                )

            lnd_value = lnd_condition(record.rfp_result, record.lnd_reliability)
            if lnd_value is None:
                report.lnd_unknown += 1
                _append_issues(
                    report,
                    (
                        DiagnosticIssue(
                            code="LND_SOURCE_INCOMPLETE",
                            severity=IssueSeverity.WARNING,
                            message=(
                                "Для признака ЛНД отсутствует или не распознано хотя бы одно "
                                "исходное значение; поле оставлено пустым."
                            ),
                            source="gdi",
                            well_id=fund_well.base_well_id,
                            locations=record.lnd_locations,
                        ),
                    ),
                )
                target_lnd = None
            else:
                target_lnd = "Да" if lnd_value else "Нет"
                row_provenance["ЛНД"] = _gdi_locations(record, "rfp_cell", "lnd_reliability_cell")
                if lnd_value:
                    report.lnd_true += 1
                else:
                    report.lnd_false += 1

            downhole_value = downhole_condition(
                record.depth_raw_value, criteria.downhole_depth_threshold_m
            )
            if downhole_value is None:
                report.downhole_unknown += 1
                _append_issues(
                    report,
                    (
                        DiagnosticIssue(
                            code="GDI_DEPTH_UNKNOWN",
                            severity=IssueSeverity.WARNING,
                            message=(
                                "Глубина записи отсутствует или не распознана; "
                                "поле «Глубинные датчики» оставлено пустым."
                            ),
                            source="gdi",
                            well_id=fund_well.base_well_id,
                            locations=(
                                SourceLocation(
                                    file=record.source_file,
                                    sheet=record.source_sheet,
                                    cell=record.depth_cell,
                                ),
                            )
                            if record.source_file and record.depth_cell
                            else (),
                        ),
                    ),
                )
                downhole_cell = None
            else:
                downhole_cell = "Да" if downhole_value else "Нет"
                row_provenance["Глубинные датчики"] = _gdi_locations(record, "depth_cell")
                if downhole_value:
                    report.downhole_yes += 1
                else:
                    report.downhole_no += 1
            lha_values = (
                lha_index.select(
                    base_well_id=fund_well.base_well_id or "",
                    normalized_field=fund_well.normalized_field,
                    normalized_plast=record.normalized_plast or "",
                    cutoff=datetime.combine(
                        calculation_date or report.calculation_date or fund_well.fund_date,
                        time.max,
                    ),
                    target_well_id=effective_identity,
                    physical_root=fund_well.base_well_id,
                    histories=histories,
                    lifecycle_stage=lifecycle.stage,
                )
                if record.normalized_plast is not None
                else None
            )
            if lha_values is not None:
                _append_issues(report, lha_values.issues)
            cl_current = lha_values.cl_current if lha_values else None
            cl_previous = lha_values.cl_previous if lha_values else None
            vgf_current = lha_values.vgf_current if lha_values else None
            vgf_previous = lha_values.vgf_previous if lha_values else None
            if cl_current is not None or cl_previous is not None:
                report.with_lha_cl += 1
            if vgf_current is not None or vgf_previous is not None:
                report.with_lha_vgf += 1
            if all(value is None for value in (cl_current, cl_previous, vgf_current, vgf_previous)):
                report.without_lha += 1
                if lha_values is None or not lha_values.issues:
                    _append_issues(
                        report,
                        (
                            DiagnosticIssue(
                                code="LHA_NOT_FOUND",
                                severity=IssueSeverity.INFO,
                                message=(
                                    "Для однозначно сопоставленной скважины не найдено "
                                    "валидной точки ЛХА."
                                ),
                                source="lha",
                                well_id=fund_well.base_well_id,
                                locations=fund_well.locations,
                            ),
                        ),
                    )

            chlorine_value: str | None = None
            if cl_current is not None and cl_previous is not None:
                chlorine_value = (
                    "Да"
                    if chlorine_growth(
                        cl_current,
                        cl_previous,
                        criteria.chlorine_current_min_mg_dm3,
                        criteria.chlorine_delta_min_mg_dm3,
                    )
                    else "Нет"
                )
                report.chlorine_growth_filled += 1
                row_provenance["Рост хлора"] = _unique_locations(
                    (
                        *lha_values.values.cl_current_locations,
                        *lha_values.values.cl_previous_locations,
                    )
                    if lha_values is not None
                    else ()
                )
            else:
                chlorine_locations = (
                    (
                        *lha_values.values.cl_current_locations,
                        *lha_values.values.cl_previous_locations,
                    )
                    if lha_values is not None
                    else ()
                )
                _append_issues(
                    report,
                    (
                        DiagnosticIssue(
                            code="CHLORINE_INSUFFICIENT_HISTORY",
                            severity=IssueSeverity.WARNING,
                            message=(
                                "Для роста хлора не хватает двух числовых точек Cl; значение "
                                "оставлено пустым."
                            ),
                            source="lha",
                            well_id=fund_well.base_well_id,
                            locations=tuple(chlorine_locations),
                        ),
                    ),
                )

            operation_date = calculation_date or report.calculation_date or fund_well.fund_date
            latest_gdi = max(
                (item for item in current_history if item.study_date is not None),
                key=lambda item: (item.study_date or datetime.min, item.source_row),
                default=None,
            )
            if latest_gdi is not None and latest_gdi.study_date is not None:
                duration_without_gdi = duration_years(operation_date, latest_gdi.study_date.date())
                report.duration_without_gdi_filled += 1
                row_provenance["Продолжительность без ГДИ"] = _gdi_locations(
                    latest_gdi, "date_cell"
                )
                duration_gdi_details = {"calculation_date": operation_date.isoformat()}
            elif launch_date is not None:
                duration_without_gdi = duration_years(operation_date, launch_date)
                report.duration_without_gdi_filled += 1
                row_provenance["Продолжительность без ГДИ"] = launch_locations
                duration_gdi_details = {
                    "calculation_date": operation_date.isoformat(),
                    "source_date": launch_date.isoformat(),
                }
            else:
                duration_without_gdi = None
                duration_gdi_details = {}
                if launch_partial is not None:
                    _append_issues(
                        report,
                        (
                            DiagnosticIssue(
                                code="NO_GDI_LAUNCH_PRECISION",
                                severity=IssueSeverity.WARNING,
                                message=(
                                    "Валидных ГДИ нет, а точность даты запуска недостаточна для "
                                    "продолжительности без ГДИ."
                                ),
                                source="well_history",
                                well_id=fund_well.base_well_id,
                                locations=launch_locations,
                            ),
                        ),
                    )

            latest_id = max(
                (
                    item
                    for item in current_history
                    if item.gdi_kind in {GdiKind.ID, GdiKind.ID_KVD} and item.study_date is not None
                ),
                key=lambda item: (item.study_date or datetime.min, item.source_row),
                default=None,
            )
            if latest_id is None or latest_id.study_date is None:
                duration_without_id = (
                    duration_years(operation_date, launch_date) if launch_date is not None else None
                )
                if duration_without_id is not None:
                    report.duration_without_id_filled += 1
                    row_provenance["Продолжительность без ИД"] = launch_locations
                _append_issues(
                    report,
                    (
                        DiagnosticIssue(
                            code="NO_ID_HISTORY_USING_LAUNCH_DATE"
                            if duration_without_id is not None
                            else "NO_ID_HISTORY_LAUNCH_UNKNOWN",
                            severity=(
                                IssueSeverity.INFO
                                if duration_without_id is not None
                                else IssueSeverity.WARNING
                            ),
                            message=(
                                "В текущей lifecycle-истории нет ИД; длительность рассчитана от "
                                "эффективной даты запуска."
                                if duration_without_id is not None
                                else "В текущей lifecycle-истории нет ИД и не определена "
                                "дата запуска."
                            ),
                            source="gdi",
                            well_id=fund_well.base_well_id,
                            locations=fund_well.locations,
                        ),
                    ),
                )
            else:
                duration_without_id = duration_years(operation_date, latest_id.study_date.date())
                report.duration_without_id_filled += 1
                row_provenance["Продолжительность без ИД"] = _gdi_locations(
                    latest_id, "date_cell", "research_type_cell"
                )
            latest_kvd = max(
                (
                    item
                    for item in current_history
                    if item.gdi_kind in {GdiKind.KVD, GdiKind.ID_KVD}
                    and item.study_date is not None
                ),
                key=lambda item: (item.study_date or datetime.min, item.source_row),
                default=None,
            )
            if latest_kvd is None or latest_kvd.study_date is None:
                duration_without_kvd = (
                    duration_years(operation_date, launch_date) if launch_date is not None else None
                )
                if duration_without_kvd is not None:
                    report.duration_without_kvd_filled += 1
                    row_provenance["Продолжительность без КВД"] = launch_locations
                _append_issues(
                    report,
                    (
                        DiagnosticIssue(
                            code="NO_KVD_HISTORY_USING_LAUNCH_DATE"
                            if duration_without_kvd is not None
                            else "NO_KVD_HISTORY_LAUNCH_UNKNOWN",
                            severity=(
                                IssueSeverity.INFO
                                if duration_without_kvd is not None
                                else IssueSeverity.WARNING
                            ),
                            message=(
                                "В текущей lifecycle-истории нет КВД; длительность рассчитана от "
                                "эффективной даты запуска."
                                if duration_without_kvd is not None
                                else "В текущей lifecycle-истории нет КВД и не определена "
                                "дата запуска."
                            ),
                            source="gdi",
                            well_id=fund_well.base_well_id,
                            locations=fund_well.locations,
                        ),
                    ),
                )
            else:
                duration_without_kvd = duration_years(operation_date, latest_kvd.study_date.date())
                report.duration_without_kvd_filled += 1
                row_provenance["Продолжительность без КВД"] = _gdi_locations(
                    latest_kvd, "date_cell", "research_type_cell"
                )

            if lha_values is not None:
                row_provenance.update(
                    {
                        field_name: locations
                        for field_name, locations in (
                            ("Cl текущий", lha_values.values.cl_current_locations),
                            ("Cl предыдущий", lha_values.values.cl_previous_locations),
                            ("ВГФ текущий", lha_values.values.vgf_current_locations),
                            ("ВГФ предыдущий", lha_values.values.vgf_previous_locations),
                        )
                        if locations
                    }
                )

            gdm_candidates, gdm_match_issues = _status_candidates_for_target(
                fund_well,
                effective_identity,
                record.normalized_plast,
                lifecycle.stage,
                research_status,
                histories,
            )
            _append_issues(report, gdm_match_issues)
            problem_candidates = tuple(
                item
                for item in gdm_candidates
                if item.delta_value is not None
                and gdm_problem(item.delta_value, criteria.gdm_abs_delta_threshold)
            )
            if gdm_candidates:
                report.gdm_rows_per_target[effective_identity] = len(gdm_candidates)
            report.gdm_target_candidate_rows += len(problem_candidates)
            gdm_selection = select_gdm_delta(gdm_candidates, criteria.gdm_fallback_max_age_days)
            gdm_value: str | None = None
            if gdm_selection.record is not None:
                selected_delta = gdm_selection.record
                assert selected_delta.delta_value is not None
                gdm_is_problem = gdm_problem(
                    selected_delta.delta_value, criteria.gdm_abs_delta_threshold
                )
                gdm_value = "Да" if gdm_is_problem else "Нет"
                if gdm_is_problem:
                    report.gdm_filled_yes += 1
                else:
                    report.gdm_filled_no += 1
                if gdm_selection.fallback:
                    report.gdm_fallback_selected += 1
                row_provenance["Проблемы ГДМ"] = selected_delta.locations
                latest_relevant = gdm_selection.latest_relevant
                row_provenance_details["Проблемы ГДМ"] = {
                    "selected_delta_cell": selected_delta.delta_cell,
                    "selected_research_date": (
                        effective_date(selected_delta.study_date).isoformat()
                        if selected_delta.study_date is not None
                        else None
                    ),
                    "selected_source_partial_date": (
                        selected_delta.study_date.to_dict()
                        if selected_delta.study_date is not None
                        else None
                    ),
                    "selection": "fallback" if gdm_selection.fallback else "latest",
                    "latest_relevant_date": (
                        effective_date(latest_relevant.study_date).isoformat()
                        if latest_relevant is not None and latest_relevant.study_date is not None
                        else None
                    ),
                    "age_days": gdm_selection.age_days,
                    "delta": selected_delta.delta_value,
                    "abs_delta_threshold": criteria.gdm_abs_delta_threshold,
                }
            else:
                report.gdm_blank += 1
                if gdm_selection.stale_age_days is not None:
                    report.gdm_stale_fallback_rejected += 1
                    code = "GDM_FALLBACK_OUTSIDE_WINDOW"
                    message = (
                        f"Ближайшая валидная Дельта старше допустимого окна: "
                        f"{gdm_selection.stale_age_days} дней."
                    )
                elif gdm_candidates:
                    code = "GDM_DELTA_MISSING_OR_INVALID"
                    message = (
                        "Для актуальных строк ГДМ нет валидной числовой Дельты в допустимом окне."
                    )
                else:
                    code = "GDM_CURRENT_HISTORY_NOT_FOUND"
                    message = "Для текущей lifecycle-истории и пласта не найден статус ГДМ."
                _append_issues(
                    report,
                    (
                        DiagnosticIssue(
                            code=code,
                            severity=IssueSeverity.WARNING,
                            message=message,
                            source="research_status",
                            well_id=fund_well.base_well_id,
                            locations=_unique_locations(
                                location for item in gdm_candidates for location in item.locations
                            ),
                        ),
                    ),
                )

            daily_item, daily_issue = _daily_record_for_target(
                fund_well,
                effective_identity,
                fund.wells,
                daily_rows,
            )
            debit_value: float | None = None
            if daily_issue is None and daily_item is not None:
                debit_value = mean_working_day_rate(daily_item.daily_values, criteria)
                valid_day_count = sum(
                    value is not None and value > criteria.gas_rate_working_day_min_rate
                    for value in daily_item.daily_values
                )
                report.debit_valid_day_count += valid_day_count
                if debit_value is None:
                    report.debit_blank += 1
                    _append_issues(
                        report,
                        (
                            DiagnosticIssue(
                                code="DEBIT_NO_VALID_WORKING_DAYS",
                                severity=IssueSeverity.WARNING,
                                message=(
                                    "В суточном рапорте нет числовых значений выше порога "
                                    "работающего дня; Дебит оставлен пустым."
                                ),
                                source="daily_report",
                                well_id=fund_well.base_well_id,
                                locations=tuple(
                                    SourceLocation(
                                        daily_item.source_file,
                                        daily_item.source_sheet,
                                        cell,
                                    )
                                    for cell in daily_item.daily_cells
                                ),
                            ),
                        ),
                    )
                else:
                    report.debit_filled += 1
                    row_provenance["Дебит"] = tuple(
                        SourceLocation(
                            daily_item.source_file,
                            daily_item.source_sheet,
                            cell,
                        )
                        for cell, value in zip(
                            daily_item.daily_cells, daily_item.daily_values, strict=False
                        )
                        if value is not None and value > criteria.gas_rate_working_day_min_rate
                    )
                    row_provenance_details["Дебит"] = {
                        "valid_working_days": valid_day_count,
                        "working_day_min_rate": criteria.gas_rate_working_day_min_rate,
                        "aggregation": "arithmetic_mean",
                    }
            else:
                report.debit_blank += 1
                code = daily_issue or "DEBIT_SOURCE_ROW_MISSING"
                _append_issues(
                    report,
                    (
                        DiagnosticIssue(
                            code=code,
                            severity=IssueSeverity.WARNING,
                            message=(
                                "Строка суточного рапорта не сопоставлена однозначно с текущей "
                                "скважиной; Дебит оставлен пустым."
                            ),
                            source="daily_report",
                            well_id=fund_well.base_well_id,
                            locations=fund_well.locations,
                        ),
                    ),
                )

            target_row = TargetRow(
                well=effective_identity,
                plast=record.normalized_plast,
                state=state,
                launch_date=launch_date,
                gdi_count=gdi_count,
                downhole_sensors=downhole_cell,
                gtm="Нет",
                insufficient_gdi=(
                    "Да"
                    if insufficient_value is True
                    else "Нет"
                    if insufficient_value is False
                    else None
                ),
                productivity_decline=productivity_value,
                chlorine_growth=chlorine_value,
                lnd=target_lnd,
                gdm_problems=gdm_value,
                cl_current=cl_current,
                cl_previous=cl_previous,
                duration_without_gdi=duration_without_gdi,
                specific_gdi_count=specific_value,
                vgf_current=vgf_current,
                vgf_previous=vgf_previous,
                duration_without_id=duration_without_id,
                duration_without_kvd=duration_without_kvd,
                debit=debit_value,
            )
            for field_name, locations in row_provenance.items():
                details: dict[str, object] = row_provenance_details.get(field_name, {})
                if field_name == "Дата запуска" and lifecycle.stage is not None:
                    source_partial = lifecycle.stage.started_at
                    details = {
                        **details,
                        "source_partial_date": source_partial.to_dict(),
                        "effective_date": launch_date.isoformat() if launch_date else None,
                        "date_defaulting_rule": date_defaulting_rule(source_partial),
                    }
                _append_field_provenance(
                    report,
                    effective_identity,
                    field_name,
                    locations,
                    calculation_date=operation_date.isoformat()
                    if field_name.startswith("Продолжительность")
                    or field_name == "Удельное количество ГДИ"
                    else None,
                    **details,
                )
            if duration_gdi_details:
                report.field_provenance.append(
                    {
                        "well_id": effective_identity,
                        "field": "Продолжительность без ГДИ",
                        "locations": [
                            location.to_dict()
                            for location in row_provenance.get("Продолжительность без ГДИ", ())
                        ],
                        "details": duration_gdi_details,
                    }
                )
            target_rows.append(target_row)
            target_identity_evidence.append((target_row, fund_well, record))
            report.matched += 1
            continue

        if match.status is MatchStatus.NO_GDI:
            report.no_gdi += 1
        elif match.status is MatchStatus.AMBIGUOUS:
            report.ambiguous += 1
        else:
            report.invalid_source += 1
        lifecycle = resolve_lifecycle_stage(fund_well, None, histories)
        launch_date = _launch_date_for_target(fund_well, None, histories, report, lifecycle)
        state = _target_state(fund_well)
        gdi_count = None
        insufficient_value: bool | None = None
        duration_without_gdi = None
        duration_without_id = None
        duration_without_kvd = None
        specific_value = None
        operation_date = calculation_date or report.calculation_date or fund_well.fund_date
        if match.status is MatchStatus.NO_GDI and lifecycle.stage is not None:
            stage_history = _gdi_history_for_stage(
                fund_well,
                gdi_index.history_for(fund_well),
                histories,
                lifecycle.stage,
                lifecycle.stage.plast,
                fund_well.target_well_id,
            )
            bounds = count_gdi_since_launch(stage_history, lifecycle.stage.started_at)
            gdi_count = bounds.exact_count
            insufficient_value = insufficient_gdi_from_bounds(
                bounds, criteria.insufficient_gdi_min_count
            )
            report.gdi_count_filled += 1
            report.gdi_pre_launch_excluded += len(
                _prelaunch_gdi_records_for_stage(
                    fund_well,
                    gdi_index.history_for(fund_well),
                    histories,
                    lifecycle.stage,
                )
            )
            if insufficient_value is True:
                report.insufficient_gdi_yes += 1
            elif insufficient_value is False:
                report.insufficient_gdi_no += 1
            for field_name in ("Количество ГДИ", "Недостаточно ГДИС"):
                _append_field_provenance(
                    report,
                    fund_well.target_well_id,
                    field_name,
                    (lifecycle.stage.source_location,),
                    calculation_date=operation_date.isoformat(),
                    definite_after_count=bounds.definite_count,
                    possible_after_count=bounds.possible_count,
                )
            latest_gdi = max(
                (item for item in stage_history if item.study_date is not None),
                key=lambda item: (item.study_date or datetime.min, item.source_row),
                default=None,
            )
            if latest_gdi is not None and latest_gdi.study_date is not None:
                duration_without_gdi = duration_years(operation_date, latest_gdi.study_date.date())
                _append_field_provenance(
                    report,
                    fund_well.target_well_id,
                    "Продолжительность без ГДИ",
                    _gdi_locations(latest_gdi, "date_cell"),
                    calculation_date=operation_date.isoformat(),
                )
                report.duration_without_gdi_filled += 1
            elif launch_date is not None:
                duration_without_gdi = duration_years(operation_date, launch_date)
                _append_field_provenance(
                    report,
                    fund_well.target_well_id,
                    "Продолжительность без ГДИ",
                    (lifecycle.stage.source_location,),
                    calculation_date=operation_date.isoformat(),
                    source_date=launch_date.isoformat(),
                )
                report.duration_without_gdi_filled += 1
            latest_id = max(
                (
                    item
                    for item in stage_history
                    if item.gdi_kind in {GdiKind.ID, GdiKind.ID_KVD} and item.study_date is not None
                ),
                key=lambda item: (item.study_date or datetime.min, item.source_row),
                default=None,
            )
            latest_kvd = max(
                (
                    item
                    for item in stage_history
                    if item.gdi_kind in {GdiKind.KVD, GdiKind.ID_KVD}
                    and item.study_date is not None
                ),
                key=lambda item: (item.study_date or datetime.min, item.source_row),
                default=None,
            )
            duration_without_id = (
                duration_years(operation_date, latest_id.study_date.date())
                if latest_id is not None and latest_id.study_date is not None
                else duration_years(operation_date, launch_date)
                if launch_date is not None
                else None
            )
            duration_without_kvd = (
                duration_years(operation_date, latest_kvd.study_date.date())
                if latest_kvd is not None and latest_kvd.study_date is not None
                else duration_years(operation_date, launch_date)
                if launch_date is not None
                else None
            )
            for field_name, latest_record, duration_value in (
                ("Продолжительность без ИД", latest_id, duration_without_id),
                ("Продолжительность без КВД", latest_kvd, duration_without_kvd),
            ):
                if duration_value is None:
                    continue
                report.duration_without_id_filled += field_name.endswith("ИД")
                report.duration_without_kvd_filled += field_name.endswith("КВД")
                _append_field_provenance(
                    report,
                    fund_well.target_well_id,
                    field_name,
                    _gdi_locations(latest_record, "date_cell", "research_type_cell")
                    if latest_record is not None
                    else (lifecycle.stage.source_location,),
                    calculation_date=operation_date.isoformat(),
                    source_date=(
                        latest_record.study_date.date().isoformat()
                        if latest_record is not None and latest_record.study_date is not None
                        else launch_date.isoformat()
                        if launch_date is not None
                        else None
                    ),
                    no_relevant_gdi_history=latest_record is None,
                )
            if duration_without_gdi is None:
                _append_issues(
                    report,
                    (
                        DiagnosticIssue(
                            code="NO_GDI_LAUNCH_PRECISION",
                            severity=IssueSeverity.WARNING,
                            message=(
                                "Валидных ГДИ нет, а точность даты запуска недостаточна для "
                                "продолжительности без ГДИ."
                            ),
                            source="well_history",
                            well_id=fund_well.base_well_id,
                            locations=(lifecycle.stage.source_location,),
                        ),
                    ),
                )
            if launch_date is not None and gdi_count == 0:
                _append_issues(
                    report,
                    (
                        DiagnosticIssue(
                            code="GDI_SPECIFIC_RATE_ZERO_COUNT",
                            severity=IssueSeverity.INFO,
                            message=(
                                "Количество ГДИ равно нулю; удельное количество оставлено пустым, "
                                "μi=0; критерий не участвует в итоговом коэффициенте λ."
                            ),
                            source="gdi",
                            well_id=fund_well.base_well_id,
                            locations=(lifecycle.stage.source_location,),
                        ),
                    ),
                )
            if launch_date is not None and gdi_count is not None and gdi_count > 0:
                specific_value = specific_gdi_count(operation_date, launch_date, gdi_count)
                if specific_value is not None:
                    report.specific_gdi_count_filled += 1
                    _append_field_provenance(
                        report,
                        fund_well.target_well_id,
                        "Удельное количество ГДИ",
                        tuple(
                            location
                            for item in bounds.definite_records
                            for location in _gdi_locations(item, "date_cell")
                        ),
                        calculation_date=operation_date.isoformat(),
                    )
        target_identity = _effective_target_identity(fund_well, None, lifecycle.stage)
        gdm_value: str | None = None
        if match.status is MatchStatus.NO_GDI and lifecycle.stage is not None:
            gdm_candidates, gdm_issues = _status_candidates_for_target(
                fund_well,
                target_identity or fund_well.target_well_id or fund_well.raw_display,
                lifecycle.stage.plast,
                lifecycle.stage,
                research_status,
                histories,
            )
            _append_issues(report, gdm_issues)
            if gdm_candidates:
                report.gdm_rows_per_target[target_identity or fund_well.raw_display] = len(
                    gdm_candidates
                )
            selection = select_gdm_delta(gdm_candidates, criteria.gdm_fallback_max_age_days)
            if selection.record is not None:
                assert selection.record.delta_value is not None
                is_problem = gdm_problem(
                    selection.record.delta_value, criteria.gdm_abs_delta_threshold
                )
                gdm_value = "Да" if is_problem else "Нет"
                report.gdm_filled_yes += int(is_problem)
                report.gdm_filled_no += int(not is_problem)
                report.gdm_fallback_selected += int(selection.fallback)
                _append_field_provenance(
                    report,
                    target_identity,
                    "Проблемы ГДМ",
                    selection.record.locations,
                    selection="fallback" if selection.fallback else "latest",
                    age_days=selection.age_days,
                    delta=selection.record.delta_value,
                    abs_delta_threshold=criteria.gdm_abs_delta_threshold,
                )
            else:
                report.gdm_blank += 1
                _append_issues(
                    report,
                    (
                        DiagnosticIssue(
                            code=(
                                "GDM_FALLBACK_OUTSIDE_WINDOW"
                                if selection.stale_age_days is not None
                                else "GDM_DELTA_MISSING_OR_INVALID"
                                if gdm_candidates
                                else "GDM_CURRENT_HISTORY_NOT_FOUND"
                            ),
                            severity=IssueSeverity.WARNING,
                            message=(
                                "Для текущей lifecycle-истории нет допустимой валидной Дельты."
                            ),
                            source="research_status",
                            well_id=fund_well.base_well_id,
                            locations=_unique_locations(
                                location for item in gdm_candidates for location in item.locations
                            ),
                        ),
                    ),
                )
        debit_value: float | None = None
        if match.status is MatchStatus.NO_GDI:
            daily_item, daily_issue = _daily_record_for_target(
                fund_well,
                target_identity or fund_well.target_well_id or fund_well.raw_display,
                fund.wells,
                daily_rows,
            )
            if daily_issue is None and daily_item is not None:
                debit_value = mean_working_day_rate(daily_item.daily_values, criteria)
                valid_day_count = sum(
                    value is not None and value > criteria.gas_rate_working_day_min_rate
                    for value in daily_item.daily_values
                )
                report.debit_valid_day_count += valid_day_count
                if debit_value is None:
                    report.debit_blank += 1
                    _append_issues(
                        report,
                        (
                            DiagnosticIssue(
                                code="DEBIT_NO_VALID_WORKING_DAYS",
                                severity=IssueSeverity.WARNING,
                                message=(
                                    "В суточном рапорте нет числовых значений выше порога "
                                    "работающего дня; Дебит оставлен пустым."
                                ),
                                source="daily_report",
                                well_id=fund_well.base_well_id,
                                locations=(
                                    SourceLocation(
                                        daily_item.source_file,
                                        daily_item.source_sheet,
                                        daily_item.well_cell,
                                    ),
                                ),
                            ),
                        ),
                    )
                else:
                    report.debit_filled += 1
            else:
                report.debit_blank += 1
        target_rows.append(
            TargetRow(
                well=fund_well.target_well_id or fund_well.raw_display,
                plast=lifecycle.stage.plast if lifecycle.stage is not None else None,
                state=state,
                launch_date=launch_date,
                gdi_count=gdi_count,
                gtm="Нет",
                gdm_problems=gdm_value,
                insufficient_gdi=(
                    "Да"
                    if insufficient_value is True
                    else "Нет"
                    if insufficient_value is False
                    else None
                ),
                duration_without_gdi=duration_without_gdi,
                duration_without_id=duration_without_id,
                duration_without_kvd=duration_without_kvd,
                debit=debit_value,
            )
        )
        _append_issues(
            report,
            (
                DiagnosticIssue(
                    code="FUND_FALLBACK",
                    severity=IssueSeverity.INFO,
                    message=(
                        f"В поле 'Скважина' сохранено исходное обозначение фонда "
                        f"{fund_well.raw_display!r}; "
                        f"статус {match.status.value}, актуальное имя из ГДИ не выбрано."
                    ),
                    source="fund",
                    well_id=fund_well.base_well_id,
                    locations=fund_well.locations,
                ),
            ),
        )
        report.without_lha += 1
    _append_target_identity_collisions(target_identity_evidence, report)
    report.rows_prepared = len(target_rows)
    report.gdm_multiple_candidate_identities = sum(
        row_count > 1 for row_count in report.gdm_rows_per_target.values()
    )
    report.gdm_unique_candidate_identities = len(report.gdm_rows_per_target)
    if target_rows:
        field_counts: defaultdict[str, int] = defaultdict(int)
        for row in target_rows:
            for name, value in row.as_mapping().items():
                if value is not None:
                    field_counts[name] += 1
        report.field_fill_counts = dict(sorted(field_counts.items()))
    if len(target_rows) > 100:
        calculator_path = report.input_paths.get("calculator")
        _append_issues(
            report,
            (
                DiagnosticIssue(
                    code="DATA_ROWS_EXCEED_CALCULATOR_FORMULA_CAPACITY",
                    severity=IssueSeverity.WARNING,
                    message=(
                        "Количество строк фонда превышает текущую расчетную емкость остальных "
                        "листов калькулятора (100)."
                    ),
                    source="calculator",
                    locations=(
                        SourceLocation(
                            file=calculator_path,
                            sheet="Расчет",
                            cell="A106:Z106",
                        ),
                    )
                    if calculator_path
                    else (),
                ),
            ),
        )
    return tuple(target_rows)


def _prepare(
    paths: SourcePaths,
    report: LoadReport,
    calculation_date: date,
    target_field: str,
    criteria: CriteriaConfig,
    progress: ProgressCallback | None = None,
) -> tuple[tuple[TargetRow, ...], FundParseResult, WellHistoryParseResult]:
    """Read the sources that currently contribute to the target row.

    Daily telemetry is read here so the approved positive-working-day mean can
    be calculated without putting aggregation logic in the reader.
    """

    _report_progress(progress, 20, "Чтение фонда скважин")
    fund = read_fund(paths.fund)
    _append_issues(report, fund.issues)
    _report_progress(progress, 30, "Чтение базы истории скважин")
    target_key = normalize_field_name(target_field)
    history_code = next(
        (
            code
            for code, field_name in FIELD_SHEETS.items()
            if normalize_field_name(field_name) == target_key
        ),
        None,
    )
    if history_code is None:
        well_history = WellHistoryParseResult(
            (),
            (
                DiagnosticIssue(
                    code="FIELD_SOURCE_SHEET_MAPPING_MISSING",
                    severity=IssueSeverity.WARNING,
                    message=f"Для месторождения {target_field!r} не настроен лист базы истории.",
                    source="well_history",
                    locations=(SourceLocation(file=str(paths.well_history.resolve())),),
                ),
            ),
        )
    else:
        well_history = read_well_history(paths.well_history, target_field)
    _append_issues(report, well_history.issues)
    report.well_history_records = len(well_history.histories)
    report.well_history_event_counts = well_history.event_counts
    report.well_history_gtm_events = sum(well_history.event_counts.values())
    report.well_history_date_precision_counts = well_history.date_precision_counts
    _report_progress(progress, 45, "Чтение истории ГДИ")
    raw_gdi_records, gdi_issues = read_gdi(paths.gdi)
    _append_issues(report, gdi_issues)
    target_field_key = normalize_field_name(target_field)
    raw_scoped_gdi = tuple(
        record for record in raw_gdi_records if record.normalized_field == target_field_key
    )
    report.gdi_raw_record_count = len(raw_scoped_gdi)
    raw_kind_counts: defaultdict[str, int] = defaultdict(int)
    nonvalid_labels: defaultdict[str, int] = defaultdict(int)
    valid_kinds = {GdiKind.ID, GdiKind.ID_KVD, GdiKind.KVD}
    for record in raw_scoped_gdi:
        raw_kind_counts[record.gdi_kind.value] += 1
        if record.gdi_kind not in valid_kinds:
            nonvalid_labels[record.research_type or "(пусто)"] += 1
    report.gdi_raw_kind_counts = dict(sorted(raw_kind_counts.items()))
    report.gdi_nonvalid_labels = dict(sorted(nonvalid_labels.items()))
    gdi_records, duplicate_issues = collapse_exact_gdi_duplicates(raw_scoped_gdi)
    _append_issues(report, duplicate_issues)
    scoped_gdi_records = gdi_records
    report.gdi_exact_duplicates_collapsed = len(raw_scoped_gdi) - len(scoped_gdi_records)
    report.gdi_deduplicated_record_count = len(scoped_gdi_records)
    gdi_counts: defaultdict[str, int] = defaultdict(int)
    for record in scoped_gdi_records:
        gdi_counts[record.gdi_kind.value] += 1
    report.gdi_kind_counts = dict(sorted(gdi_counts.items()))
    report.gdi_kind_unknown = gdi_counts[GdiKind.UNKNOWN.value]
    _report_progress(progress, 60, "Чтение базы ЛХА")
    lha_records, lha_issues = read_lha(paths.lha)
    _append_issues(report, lha_issues)
    _report_progress(progress, 68, "Чтение статуса исследований ГДМ")
    status_code = next(
        (
            code
            for code, field_name in FIELD_SHEETS.items()
            if normalize_field_name(field_name) == target_field_key
        ),
        None,
    )
    if status_code is None or status_code not in STATUS_SHEETS:
        research_status = ()
        status_issues = (
            DiagnosticIssue(
                code="FIELD_SOURCE_SHEET_MAPPING_MISSING",
                severity=IssueSeverity.WARNING,
                message=(
                    f"Для месторождения {target_field!r} не настроен лист статуса исследований."
                ),
                source="research_status",
                locations=(SourceLocation(file=str(paths.research_status.resolve())),),
            ),
        )
    else:
        research_status, status_issues = read_research_status(paths.research_status, status_code)
    _append_issues(report, status_issues)
    report.gdm_rows_read = len(research_status)
    report.gdm_numeric_delta_rows = sum(item.delta_value is not None for item in research_status)
    report.gdm_formula_without_cached_delta_rows = sum(
        item.delta_formula_without_cache for item in research_status
    )
    report.gdm_invalid_delta_rows = sum(
        item.delta_value is None
        and not item.delta_formula_without_cache
        and not _gdm_delta_is_missing(item.delta_raw)
        for item in research_status
    )
    report.gdm_missing_delta_rows = sum(
        item.delta_value is None
        and not item.delta_formula_without_cache
        and _gdm_delta_is_missing(item.delta_raw)
        for item in research_status
    )
    report.gdm_problem_candidate_rows = sum(
        item.delta_value is not None
        and gdm_problem(item.delta_value, criteria.gdm_abs_delta_threshold)
        for item in research_status
    )
    _report_progress(progress, 72, "Чтение суточного рапорта")
    daily_rows, daily_issues = read_daily_report(paths.daily_report)
    _append_issues(report, daily_issues)
    report.fund_date = fund.fund_date
    _report_progress(progress, 75, "Сопоставление жизненных циклов")
    target_rows = _build_target_rows(
        fund,
        GdiIndex(gdi_records, calculation_date),
        LhaIndex(lha_records),
        report,
        well_history.histories,
        calculation_date,
        research_status,
        criteria,
        daily_rows,
    )
    _report_progress(progress, 85, "Подготовка итоговых строк")
    return target_rows, fund, well_history


def run_validate(
    paths: SourcePaths,
    log_path: Path | None = None,
    progress: ProgressCallback | None = None,
    *,
    calculation_date: date | None = None,
) -> ServiceResult:
    """Validate schemas and discover fields without requiring a target selection."""

    _report_progress(progress, 0, "Старт проверки")
    operation_date = calculation_date or date.today()
    actual_log_path = configure_logging(log_path or paths.calculator.parent / "gdis_loader.log")
    report = _new_report(paths, operation_date)
    report.criteria_snapshot = _criteria_snapshot(CriteriaConfig(), frozenset(), None)
    report.log_path = str(actual_log_path.resolve())
    _report_progress(progress, 10, "Проверка путей и структуры файлов")
    validation = validate_inputs(paths, progress, (10, 80))
    _append_issues(report, validation.issues)
    report.available_fields = validation.available_fields
    report.field_coverage = validation.field_coverage or {}
    report.fund_total_source = sum(
        int(values.get("fund_rows", 0) or 0) for values in report.field_coverage.values()
    )
    report.fund_total = report.fund_total_source
    report.diagnostic_path = str(diagnostic_path(None, paths.calculator).resolve())
    _report_progress(progress, 90, "Валидация результата")
    _write_report(report, Path(report.diagnostic_path))
    if validation.valid and not any(
        issue.severity is IssueSeverity.ERROR for issue in report.issues
    ):
        _report_progress(progress, 100, "Проверка завершена")
    return ServiceResult(report)


def run_update(
    paths: SourcePaths,
    log_path: Path | None = None,
    progress: ProgressCallback | None = None,
    *,
    target_field: str,
    calculation_date: date | None = None,
    criteria_config: CriteriaConfig | None = None,
    config_source: str | Path | None = None,
    criteria_explicit_fields: frozenset[str] = frozenset(),
) -> ServiceResult:
    """Run the shared ETL pipeline and write a safe copy of the calculator."""

    _report_progress(progress, 0, "Старт обновления")
    operation_date = calculation_date or date.today()
    criteria = criteria_config or CriteriaConfig()
    report = _new_report(paths, operation_date, target_field.strip() or None)
    report.criteria_snapshot = _criteria_snapshot(criteria, criteria_explicit_fields, config_source)
    report.config_source = str(config_source) if config_source is not None else None
    LOGGER.info("Начало обновления; target_field=%s", target_field)
    _report_progress(progress, 10, "Проверка путей и структуры файлов")
    validation = validate_inputs(paths, progress, (10, 19))
    _append_issues(report, validation.issues)
    report.available_fields = validation.available_fields
    report.field_coverage = validation.field_coverage or {}
    if not validation.valid:
        actual_log_path = configure_logging(log_path or paths.calculator.parent / "gdis_loader.log")
        report.log_path = str(actual_log_path.resolve())
        report.diagnostic_path = str(diagnostic_path(None, paths.calculator).resolve())
        _write_report(report, Path(report.diagnostic_path))
        raise ServiceError(f"Проверка файлов не пройдена:\n{_validation_failure(validation)}")
    selected_field = next(
        (
            field_name
            for field_name in validation.available_fields
            if normalize_field_name(field_name) == normalize_field_name(target_field.strip())
        ),
        None,
    )
    if not target_field.strip() or selected_field is None:
        issue = DiagnosticIssue(
            code="FIELD_NOT_FOUND_IN_FUND",
            severity=IssueSeverity.ERROR,
            message=(
                f"Месторождение {target_field!r} отсутствует среди найденных в фонде: "
                f"{', '.join(validation.available_fields) or 'не обнаружены'}."
            ),
            source="fund",
            locations=(SourceLocation(file=str(paths.fund.resolve())),),
        )
        _append_issues(report, (issue,))
        actual_log_path = configure_logging(log_path or paths.calculator.parent / "gdis_loader.log")
        report.log_path = str(actual_log_path.resolve())
        report.diagnostic_path = str(diagnostic_path(None, paths.calculator).resolve())
        _write_report(report, Path(report.diagnostic_path))
        raise ServiceError(issue.message)
    output_path = paths.output or default_output_path(paths.calculator, selected_field)
    output_issues = validate_output_path(output_path, paths)
    if output_issues:
        raise ServiceError(
            "Путь результата не прошел проверку:\n"
            + "\n".join(f"- {format_diagnostic_issue(issue)}" for issue in output_issues)
        )
    actual_log_path = configure_logging(log_path or output_path.parent / "gdis_loader.log")
    report.log_path = str(actual_log_path.resolve())
    effective_paths = replace(paths, output=output_path)
    report.target_field = selected_field
    report.input_paths["output"] = str(output_path.resolve())
    report.diagnostic_path = str(diagnostic_path(output_path, paths.calculator).resolve())
    try:
        target_rows, _, _ = _prepare(
            effective_paths,
            report,
            operation_date,
            selected_field,
            criteria,
            progress,
        )
        if any(issue.severity is IssueSeverity.ERROR for issue in report.issues):
            _write_report(report, Path(report.diagnostic_path))
            raise ServiceError(f"Чтение источников не пройдено:\n{_report_error_text(report)}")
        _report_progress(progress, 90, "Валидация результата")
        _report_progress(progress, 95, "Запись листа Данные")
        writer_result: TargetWriteResult = write_target_rows(
            paths.calculator, output_path, target_rows
        )
        report.rows_written = writer_result.rows_written
        report.output_path = str(output_path.resolve())
        _write_report(report, Path(report.diagnostic_path))
        LOGGER.info("Обновление завершено: %s", report.output_path)
        _report_progress(progress, 100, "Обновление завершено")
        return ServiceResult(report, output_path)
    except (OSError, ValueError, KeyError, TypeError) as error:
        message = str(error)
        code = (
            "TARGET_TABLE_EXPANSION_CONFLICT"
            if "TARGET_TABLE_EXPANSION_CONFLICT" in message
            else "TARGET_WRITE_FAILED"
        )
        _append_issues(
            report,
            (
                DiagnosticIssue(
                    code=code,
                    severity=IssueSeverity.ERROR,
                    message=message,
                    source="calculator",
                    locations=(
                        SourceLocation(
                            file=str(paths.calculator.resolve()),
                            sheet="Данные",
                            cell=None,
                        ),
                    ),
                ),
            ),
        )
        _write_report(report, Path(report.diagnostic_path))
        LOGGER.exception("Обновление не выполнено")
        raise ServiceError(f"Не удалось сформировать результат: {message}") from error
