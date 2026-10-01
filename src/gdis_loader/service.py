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
from gdis_loader.domain.models import (
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
from gdis_loader.matching.normalize import normalize_field_name
from gdis_loader.progress import ProgressCallback, ProgressUpdate
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
    productivity_decline,
)
from gdis_loader.transforms.rules import (
    downhole_condition,
    lnd_condition,
    specific_gdi_count,
)
from gdis_loader.validation.sources import ValidationResult, validate_inputs

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
    """Return a launch date only when lifecycle and source precision are exact."""

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
    if launch.precision is not DatePrecision.DAY:
        report.launch_date_incomplete += 1
        _append_issues(
            report,
            (
                DiagnosticIssue(
                    code="WELL_HISTORY_DATE_INCOMPLETE_PRECISION",
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Дата начала истории имеет точность {launch.precision.value}; "
                        "точная дата в лист Данные не записана."
                    ),
                    source="well_history",
                    well_id=fund_well.base_well_id,
                    locations=(stage.source_location,),
                ),
            ),
        )
        return None
    assert launch.month is not None and launch.day is not None
    report.launch_date_filled += 1
    return date(launch.year, launch.month, launch.day)


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
            return fund_well.target_well_id or stage.physical_root
        if stage.event_kind in {WellEventKind.ZBS, WellEventKind.PVLG}:
            return f"{stage.physical_root}_{stage.event_kind.value}"
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

    selected_identity = selected.target_well_id
    matching: list[GdiRecord] = []
    for record in history_records:
        if record.normalized_plast != selected.normalized_plast:
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
        SourceLocation(record.source_file, record.source_sheet, cell)
        for name in cell_names
        if (cell := getattr(record, name)) is not None and record.source_file
    )


def _build_target_rows(
    fund: FundParseResult,
    gdi_index: GdiIndex,
    lha_index: LhaIndex,
    report: LoadReport,
    histories: tuple[WellHistory, ...] = (),
    calculation_date: date | None = None,
    research_status: tuple[ResearchStatusRecord, ...] = (),
) -> tuple[TargetRow, ...]:
    if report.target_field is None:
        raise ValueError("Для подготовки target rows требуется выбранное месторождение.")
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
                insufficient_value = insufficient_gdi_from_bounds(count_bounds)
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
                    report.gdi_count_filled += 1
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

            if (
                lifecycle.stage is not None
                and lifecycle.stage.started_at.precision is DatePrecision.DAY
            ):
                stage_date = date(
                    lifecycle.stage.started_at.year,
                    lifecycle.stage.started_at.month or 1,
                    lifecycle.stage.started_at.day or 1,
                )
                if launch_date is not None and gdi_count is not None:
                    specific_value = specific_gdi_count(
                        calculation_date or report.calculation_date or fund_well.fund_date,
                        stage_date,
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
                                        "пустым, μi=0 относится к отдельной миграции формул."
                                    ),
                                    source="gdi",
                                    well_id=fund_well.base_well_id,
                                    locations=launch_locations,
                                ),
                            ),
                        )
                else:
                    specific_value = None
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

            downhole_value = downhole_condition(record.depth_raw_value)
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
                chlorine_value = "Да" if chlorine_growth(cl_current, cl_previous) else "Нет"
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
                duration_without_id = None
                _append_issues(
                    report,
                    (
                        DiagnosticIssue(
                            code="NO_ID_HISTORY",
                            severity=IssueSeverity.WARNING,
                            message="В текущей lifecycle-истории нет валидного ИД.",
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
                duration_without_kvd = None
                _append_issues(
                    report,
                    (
                        DiagnosticIssue(
                            code="NO_KVD_HISTORY",
                            severity=IssueSeverity.WARNING,
                            message="В текущей lifecycle-истории нет валидного КВД.",
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
                item for item in gdm_candidates if item.is_adaptation_problem is True
            )
            if problem_candidates:
                report.gdm_rows_per_target[effective_identity] = len(problem_candidates)
                report.gdm_target_candidate_rows += len(problem_candidates)
                locations = tuple(
                    location for item in problem_candidates for location in item.locations
                )
                row_provenance["Проблемы ГДМ"] = _unique_locations(locations)
                _append_issues(
                    report,
                    (
                        DiagnosticIssue(
                            code="GDM_CURRENT_ROW_UNRESOLVED",
                            severity=IssueSeverity.WARNING,
                            message=(
                                f"Найдено {len(problem_candidates)} строк-кандидатов "
                                "abs(Дельта)>5; значение удержано до утверждения правила "
                                "актуальной строки."
                            ),
                            source="research_status",
                            well_id=fund_well.base_well_id,
                            locations=_unique_locations(locations),
                        ),
                    ),
                )

            target_row = TargetRow(
                well=effective_identity,
                plast=record.raw_plast,
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
                cl_current=cl_current,
                cl_previous=cl_previous,
                duration_without_gdi=duration_without_gdi,
                specific_gdi_count=specific_value,
                vgf_current=vgf_current,
                vgf_previous=vgf_previous,
                duration_without_id=duration_without_id,
                duration_without_kvd=duration_without_kvd,
            )
            for field_name, locations in row_provenance.items():
                _append_field_provenance(
                    report,
                    effective_identity,
                    field_name,
                    locations,
                    calculation_date=operation_date.isoformat()
                    if field_name.startswith("Продолжительность")
                    or field_name == "Удельное количество ГДИ"
                    else None,
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
        specific_value = None
        operation_date = calculation_date or report.calculation_date or fund_well.fund_date
        if match.status is MatchStatus.NO_GDI and lifecycle.stage is not None:
            empty_history = ()
            bounds = count_gdi_since_launch(empty_history, lifecycle.stage.started_at)
            gdi_count = bounds.exact_count
            insufficient_value = insufficient_gdi_from_bounds(bounds)
            report.gdi_count_filled += 1
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
            if launch_date is not None:
                duration_without_gdi = duration_years(operation_date, launch_date)
                report.duration_without_gdi_filled += 1
                _append_field_provenance(
                    report,
                    fund_well.target_well_id,
                    "Продолжительность без ГДИ",
                    (lifecycle.stage.source_location,),
                    calculation_date=operation_date.isoformat(),
                    source_date=launch_date.isoformat(),
                )
            elif lifecycle.stage.started_at.precision is not DatePrecision.DAY:
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
            if lifecycle.stage.started_at.precision is DatePrecision.DAY and gdi_count == 0:
                _append_issues(
                    report,
                    (
                        DiagnosticIssue(
                            code="GDI_SPECIFIC_RATE_ZERO_COUNT",
                            severity=IssueSeverity.INFO,
                            message=(
                                "Количество ГДИ равно нулю; удельное количество оставлено пустым, "
                                "μi=0 относится к отдельной миграции формул."
                            ),
                            source="gdi",
                            well_id=fund_well.base_well_id,
                            locations=(lifecycle.stage.source_location,),
                        ),
                    ),
                )
        target_rows.append(
            TargetRow(
                well=fund_well.target_well_id or fund_well.raw_display,
                state=state,
                launch_date=launch_date,
                gdi_count=gdi_count,
                gtm="Нет",
                insufficient_gdi=(
                    "Да"
                    if insufficient_value is True
                    else "Нет"
                    if insufficient_value is False
                    else None
                ),
                duration_without_gdi=duration_without_gdi,
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
    progress: ProgressCallback | None = None,
) -> tuple[tuple[TargetRow, ...], FundParseResult, WellHistoryParseResult]:
    """Read the sources that currently contribute to the target row.

    The daily report is schema-validated before this function is called, but
    its day values are intentionally not read here until the debit rule is
    approved.  Keeping that reader independent makes the future change local
    and avoids turning expected daily placeholders into runtime diagnostics.
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
    gdi_records, gdi_issues = read_gdi(paths.gdi)
    _append_issues(report, gdi_issues)
    target_field_key = normalize_field_name(target_field)
    scoped_gdi_records = tuple(
        record for record in gdi_records if record.normalized_field == target_field_key
    )
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
        item.is_adaptation_problem is True for item in research_status
    )
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
    actual_log_path = configure_logging(
        log_path
        or (paths.output.parent if paths.output is not None else paths.calculator.parent)
        / "gdis_loader.log"
    )
    report = _new_report(paths, operation_date)
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
    report.diagnostic_path = str(diagnostic_path(paths.output, paths.calculator).resolve())
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
) -> ServiceResult:
    """Run the shared ETL pipeline and write a safe copy of the calculator."""

    _report_progress(progress, 0, "Старт обновления")
    operation_date = calculation_date or date.today()
    log_directory = paths.output.parent if paths.output is not None else paths.calculator.parent
    actual_log_path = configure_logging(log_path or log_directory / "gdis_loader.log")
    report = _new_report(paths, operation_date, target_field.strip() or None)
    report.log_path = str(actual_log_path.resolve())
    LOGGER.info("Начало обновления; target_field=%s", target_field)
    _report_progress(progress, 10, "Проверка путей и структуры файлов")
    validation = validate_inputs(paths, progress, (10, 19))
    _append_issues(report, validation.issues)
    report.available_fields = validation.available_fields
    report.field_coverage = validation.field_coverage or {}
    if not validation.valid:
        report.diagnostic_path = str(diagnostic_path(paths.output, paths.calculator).resolve())
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
        report.diagnostic_path = str(diagnostic_path(paths.output, paths.calculator).resolve())
        _write_report(report, Path(report.diagnostic_path))
        raise ServiceError(issue.message)
    output_path = paths.output or default_output_path(paths.calculator, selected_field)
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
