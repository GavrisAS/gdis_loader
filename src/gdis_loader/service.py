"""Application service shared by the CLI and the Qt GUI."""

from __future__ import annotations

import json
import logging
import platform
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from gdis_loader import __version__
from gdis_loader.domain.models import (
    DiagnosticIssue,
    FundParseResult,
    IssueSeverity,
    LoadReport,
    MatchStatus,
    SourcePaths,
    TargetRow,
)
from gdis_loader.excel.writer import TargetWriteResult, write_target_rows
from gdis_loader.matching.matcher import GdiIndex, match_all
from gdis_loader.readers.fund import read_fund
from gdis_loader.readers.gdi import read_gdi
from gdis_loader.readers.lha import LhaIndex, read_lha
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

    def summary(self) -> str:
        report = self.report
        lines = [
            f"Скважин в фонде: {report.fund_total}",
            f"Однозначно сопоставлено: {report.matched}",
            f"Неоднозначно: {report.ambiguous}",
            f"Без ГДИ: {report.no_gdi}",
            f"Без ЛХА: {report.without_lha}",
            f"Подготовлено строк: {report.rows_prepared}",
            f"Записано строк: {report.rows_written}",
            f"Ошибок: {self.error_count}",
            f"Предупреждений: {self.warning_count}",
        ]
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


def _new_report(paths: SourcePaths) -> LoadReport:
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
            "output": str(paths.output.resolve()),
        },
    )


def _append_issues(report: LoadReport, issues: Iterable[DiagnosticIssue]) -> None:
    for issue in issues:
        report.issues.append(issue)
        if issue.severity is IssueSeverity.WARNING:
            report.warnings.append(issue.message)
        if issue.severity is IssueSeverity.INFO:
            LOGGER.info("%s: %s", issue.code, issue.message)
        elif issue.severity is IssueSeverity.WARNING:
            LOGGER.warning("%s: %s", issue.code, issue.message)
        elif issue.severity is IssueSeverity.ERROR:
            LOGGER.error("%s: %s", issue.code, issue.message)


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
    return "\n".join(f"- {issue.message}" for issue in validation.errors)


def _report_error_text(report: LoadReport) -> str:
    return "\n".join(
        f"- {issue.message}" for issue in report.issues if issue.severity is IssueSeverity.ERROR
    )


def _build_target_rows(
    fund: FundParseResult,
    gdi_index: GdiIndex,
    lha_index: LhaIndex,
    report: LoadReport,
) -> tuple[TargetRow, ...]:
    matches, match_issues = match_all(fund.wells, gdi_index)
    _append_issues(report, match_issues)
    report.fund_total = len(fund.wells)
    target_rows: list[TargetRow] = []
    for match in matches:
        fund_well = match.fund_well
        if match.status is MatchStatus.MATCHED and match.record is not None:
            record = match.record
            lha_values = (
                lha_index.select(
                    base_well_id=fund_well.base_well_id or "",
                    normalized_field=fund_well.normalized_field,
                    normalized_plast=record.normalized_plast or "",
                    cutoff=datetime.combine(fund_well.fund_date, datetime.max.time()),
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
                        ),
                    ),
                )
            target_rows.append(
                TargetRow(
                    well=record.raw_well_name,
                    plast=record.raw_plast,
                    cl_current=cl_current,
                    cl_previous=cl_previous,
                    vgf_current=vgf_current,
                    vgf_previous=vgf_previous,
                )
            )
            report.matched += 1
            continue

        if match.status is MatchStatus.NO_GDI:
            report.no_gdi += 1
        elif match.status is MatchStatus.AMBIGUOUS:
            report.ambiguous += 1
        else:
            report.invalid_source += 1
        target_rows.append(TargetRow(well=fund_well.raw_display))
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
                ),
            ),
        )
        report.without_lha += 1
    report.rows_prepared = len(target_rows)
    if len(target_rows) > 100:
        report.warnings.append("DATA_ROWS_EXCEED_CALCULATOR_FORMULA_CAPACITY")
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
                ),
            ),
        )
    return tuple(target_rows)


def _prepare(
    paths: SourcePaths, report: LoadReport
) -> tuple[tuple[TargetRow, ...], FundParseResult]:
    """Read the sources that currently contribute to the v0.1 target row.

    The daily report is schema-validated before this function is called, but
    its day values are intentionally not read here until the debit rule is
    approved.  Keeping that reader independent makes the future change local
    and avoids turning expected daily placeholders into runtime diagnostics.
    """

    fund = read_fund(paths.fund)
    _append_issues(report, fund.issues)
    gdi_records, gdi_issues = read_gdi(paths.gdi)
    _append_issues(report, gdi_issues)
    lha_records, lha_issues = read_lha(paths.lha)
    _append_issues(report, lha_issues)
    report.fund_date = fund.fund_date
    target_rows = _build_target_rows(fund, GdiIndex(gdi_records), LhaIndex(lha_records), report)
    return target_rows, fund


def run_validate(paths: SourcePaths, log_path: Path | None = None) -> ServiceResult:
    """Validate schemas and, when possible, prepare v0.1 sources without writing Excel."""

    actual_log_path = configure_logging(log_path or paths.output.parent / "gdis_loader.log")
    report = _new_report(paths)
    report.log_path = str(actual_log_path.resolve())
    validation = validate_inputs(paths)
    _append_issues(report, validation.issues)
    if validation.valid:
        _prepare(paths, report)
    report.diagnostic_path = str(diagnostic_path(paths.output).resolve())
    _write_report(report, Path(report.diagnostic_path))
    return ServiceResult(report)


def run_update(paths: SourcePaths, log_path: Path | None = None) -> ServiceResult:
    """Run the shared ETL pipeline and write a safe copy of the calculator."""

    actual_log_path = configure_logging(log_path or paths.output.parent / "gdis_loader.log")
    report = _new_report(paths)
    report.log_path = str(actual_log_path.resolve())
    LOGGER.info("Начало обновления; output=%s", paths.output)
    validation = validate_inputs(paths)
    _append_issues(report, validation.issues)
    report.diagnostic_path = str(diagnostic_path(paths.output).resolve())
    if not validation.valid:
        _write_report(report, Path(report.diagnostic_path))
        raise ServiceError(f"Проверка файлов не пройдена:\n{_validation_failure(validation)}")
    try:
        target_rows, _ = _prepare(paths, report)
        if any(issue.severity is IssueSeverity.ERROR for issue in report.issues):
            _write_report(report, Path(report.diagnostic_path))
            raise ServiceError(f"Чтение источников не пройдено:\n{_report_error_text(report)}")
        writer_result: TargetWriteResult = write_target_rows(
            paths.calculator, paths.output, target_rows
        )
        report.rows_written = writer_result.rows_written
        for warning in writer_result.warnings:
            if warning not in report.warnings:
                report.warnings.append(warning)
        report.output_path = str(paths.output.resolve())
        _write_report(report, Path(report.diagnostic_path))
        LOGGER.info("Обновление завершено: %s", report.output_path)
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
                ),
            ),
        )
        _write_report(report, Path(report.diagnostic_path))
        LOGGER.exception("Обновление не выполнено")
        raise ServiceError(f"Не удалось сформировать результат: {message}") from error
