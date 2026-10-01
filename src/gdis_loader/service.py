"""Application service shared by the CLI and the Qt GUI."""

from __future__ import annotations

import json
import logging
import platform
import tempfile
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, time
from pathlib import Path

from gdis_loader import __version__
from gdis_loader.domain.models import (
    DatePrecision,
    DiagnosticIssue,
    FundParseResult,
    FundWell,
    GdiKind,
    GdiRecord,
    IssueSeverity,
    LoadReport,
    MatchStatus,
    SourceLocation,
    SourcePaths,
    TargetRow,
    WellHistory,
    WellHistoryParseResult,
)
from gdis_loader.excel.writer import TargetWriteResult, write_target_rows
from gdis_loader.matching.lifecycle import LifecycleResolution, resolve_lifecycle_stage
from gdis_loader.matching.matcher import GdiIndex, match_all
from gdis_loader.matching.normalize import normalize_field_name
from gdis_loader.progress import ProgressCallback, ProgressUpdate
from gdis_loader.readers.fund import read_fund
from gdis_loader.readers.gdi import read_gdi
from gdis_loader.readers.lha import LhaIndex, read_lha
from gdis_loader.readers.well_history import read_well_history
from gdis_loader.transforms.rules import downhole_condition, lnd_condition
from gdis_loader.validation.sources import ValidationResult, validate_inputs

LOGGER = logging.getLogger(__name__)


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
            f"Фонд Берегового: {report.target_field_fund_total}",
            f"Допущено к рейтингу по подтвержденной категории: {report.rating_eligible}",
            f"Однозначно сопоставлено: {report.matched}",
            f"Неоднозначно: {report.ambiguous}",
            f"Без ГДИ: {report.no_gdi}",
            f"Без выбранных значений ЛХА: {report.without_lha}",
            f"Подготовлено строк: {report.rows_prepared}",
            f"Записано строк: {report.rows_written}",
            f"Ошибок: {self.error_count}",
            f"Предупреждений: {self.warning_count}",
        ]
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


def default_output_path(calculator: Path) -> Path:
    return calculator.with_name(f"{calculator.stem}_UPDATED.xlsx")


def diagnostic_path(output: Path) -> Path:
    return output.with_suffix(".load-report.json")


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


def _new_report(paths: SourcePaths, calculation_date: date) -> LoadReport:
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
            "output": str(paths.output.resolve()),
        },
        calculation_date=calculation_date,
    )


def _append_issues(report: LoadReport, issues: Iterable[DiagnosticIssue]) -> None:
    for issue in issues:
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


def _build_target_rows(
    fund: FundParseResult,
    gdi_index: GdiIndex,
    lha_index: LhaIndex,
    report: LoadReport,
    histories: tuple[WellHistory, ...] = (),
    calculation_date: date | None = None,
) -> tuple[TargetRow, ...]:
    target_field = normalize_field_name(report.target_field)
    scoped_wells = tuple(well for well in fund.wells if well.normalized_field == target_field)
    matches, match_issues = match_all(scoped_wells, gdi_index, histories)
    _append_issues(report, match_issues)
    report.fund_total_source = len(fund.wells)
    report.target_field_fund_total = len(scoped_wells)
    report.fund_total = report.fund_total_source
    report.rating_eligible = sum(well.is_rating_eligible for well in scoped_wells)
    report.rating_not_eligible = len(scoped_wells) - report.rating_eligible
    target_rows: list[TargetRow] = []
    target_identity_evidence: list[tuple[TargetRow, FundWell, GdiRecord]] = []
    for match in matches:
        fund_well = match.fund_well
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
                    target_well_id=record.target_well_id,
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
            target_row = TargetRow(
                well=record.target_well_id or record.raw_well_name,
                plast=record.raw_plast,
                launch_date=launch_date,
                downhole_sensors=downhole_cell,
                gtm="Нет",
                lnd=target_lnd,
                cl_current=cl_current,
                cl_previous=cl_previous,
                vgf_current=vgf_current,
                vgf_previous=vgf_previous,
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
        launch_date = (
            _launch_date_for_target(fund_well, None, histories, report)
            if match.status is MatchStatus.NO_GDI
            else None
        )
        target_rows.append(
            TargetRow(
                well=fund_well.target_well_id or fund_well.raw_display,
                launch_date=launch_date,
                gtm="Нет",
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
    if len(target_rows) > 100:
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
                            file=report.input_paths.get("calculator", ""),
                            sheet="Расчет",
                            cell="A106:Z106",
                        ),
                    )
                    if report.input_paths.get("calculator")
                    else (),
                ),
            ),
        )
    return tuple(target_rows)


def _prepare(
    paths: SourcePaths,
    report: LoadReport,
    calculation_date: date,
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
    well_history = read_well_history(paths.well_history, report.target_field)
    _append_issues(report, well_history.issues)
    report.well_history_records = len(well_history.histories)
    report.well_history_event_counts = well_history.event_counts
    report.well_history_gtm_events = sum(well_history.event_counts.values())
    report.well_history_date_precision_counts = well_history.date_precision_counts
    _report_progress(progress, 45, "Чтение истории ГДИ")
    gdi_records, gdi_issues = read_gdi(paths.gdi)
    _append_issues(report, gdi_issues)
    target_field = normalize_field_name(report.target_field)
    scoped_gdi_records = tuple(
        record for record in gdi_records if record.normalized_field == target_field
    )
    gdi_counts: defaultdict[str, int] = defaultdict(int)
    for record in scoped_gdi_records:
        gdi_counts[record.gdi_kind.value] += 1
    report.gdi_kind_counts = dict(sorted(gdi_counts.items()))
    report.gdi_kind_unknown = gdi_counts[GdiKind.UNKNOWN.value]
    _report_progress(progress, 60, "Чтение базы ЛХА")
    lha_records, lha_issues = read_lha(paths.lha)
    _append_issues(report, lha_issues)
    report.fund_date = fund.fund_date
    _report_progress(progress, 75, "Сопоставление жизненных циклов")
    target_rows = _build_target_rows(
        fund,
        GdiIndex(gdi_records, calculation_date),
        LhaIndex(lha_records),
        report,
        well_history.histories,
        calculation_date,
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
    """Validate schemas and, when possible, prepare sources without writing Excel."""

    _report_progress(progress, 0, "Старт проверки")
    operation_date = calculation_date or date.today()
    actual_log_path = configure_logging(log_path or paths.output.parent / "gdis_loader.log")
    report = _new_report(paths, operation_date)
    report.log_path = str(actual_log_path.resolve())
    validation = validate_inputs(paths)
    _append_issues(report, validation.issues)
    _report_progress(progress, 10, "Проверка путей и структуры файлов")
    if validation.valid:
        _prepare(paths, report, operation_date, progress)
        _report_progress(progress, 90, "Валидация результата")
    report.diagnostic_path = str(diagnostic_path(paths.output).resolve())
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
    calculation_date: date | None = None,
) -> ServiceResult:
    """Run the shared ETL pipeline and write a safe copy of the calculator."""

    _report_progress(progress, 0, "Старт обновления")
    operation_date = calculation_date or date.today()
    actual_log_path = configure_logging(log_path or paths.output.parent / "gdis_loader.log")
    report = _new_report(paths, operation_date)
    report.log_path = str(actual_log_path.resolve())
    LOGGER.info("Начало обновления; output=%s", paths.output)
    validation = validate_inputs(paths)
    _append_issues(report, validation.issues)
    _report_progress(progress, 10, "Проверка путей и структуры файлов")
    report.diagnostic_path = str(diagnostic_path(paths.output).resolve())
    if not validation.valid:
        _write_report(report, Path(report.diagnostic_path))
        raise ServiceError(f"Проверка файлов не пройдена:\n{_validation_failure(validation)}")
    try:
        target_rows, _, _ = _prepare(paths, report, operation_date, progress)
        if any(issue.severity is IssueSeverity.ERROR for issue in report.issues):
            _write_report(report, Path(report.diagnostic_path))
            raise ServiceError(f"Чтение источников не пройдено:\n{_report_error_text(report)}")
        _report_progress(progress, 90, "Валидация результата")
        _report_progress(progress, 95, "Запись листа Данные")
        writer_result: TargetWriteResult = write_target_rows(
            paths.calculator, paths.output, target_rows
        )
        report.rows_written = writer_result.rows_written
        report.output_path = str(paths.output.resolve())
        _write_report(report, Path(report.diagnostic_path))
        LOGGER.info("Обновление завершено: %s", report.output_path)
        _report_progress(progress, 100, "Обновление завершено")
        return ServiceResult(report, paths.output)
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
