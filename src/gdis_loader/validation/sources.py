"""Input-path and workbook-schema validation performed before ETL."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from gdis_loader.domain.models import (
    TARGET_FIELDS,
    DiagnosticIssue,
    IssueSeverity,
    SourceLocation,
    SourcePaths,
)
from gdis_loader.readers.common import normalized_header, openpyxl_read_warnings
from gdis_loader.readers.daily import DAILY_SHEET, _find_daily_header
from gdis_loader.readers.fund import DATE_SHEET_RE
from gdis_loader.readers.gdi import GDI_HEADER_ALIASES, GDI_SHEET
from gdis_loader.readers.gdi import _find_header as find_gdi_header
from gdis_loader.readers.lha import LHA_HEADER_ALIASES, LHA_SHEET
from gdis_loader.readers.lha import _find_header as find_lha_header


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """All validation findings, not just the first failure."""

    issues: tuple[DiagnosticIssue, ...]

    @property
    def errors(self) -> tuple[DiagnosticIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is IssueSeverity.ERROR)

    @property
    def warnings(self) -> tuple[DiagnosticIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is IssueSeverity.WARNING)

    @property
    def valid(self) -> bool:
        return not self.errors


def _path_issue(path: Path, code: str, message: str) -> DiagnosticIssue:
    return DiagnosticIssue(
        code=code,
        severity=IssueSeverity.ERROR,
        message=message,
        source=str(path),
        locations=(SourceLocation(file=str(path.resolve())),),
    )


def _check_path(path: Path, expected_suffixes: set[str], label: str) -> list[DiagnosticIssue]:
    issues: list[DiagnosticIssue] = []
    if not str(path):
        issues.append(_path_issue(path, "PATH_EMPTY", f"Не задан путь: {label}."))
        return issues
    if not path.exists():
        issues.append(_path_issue(path, "PATH_NOT_FOUND", f"Файл {label} не существует: {path}."))
        return issues
    if not path.is_file():
        issues.append(
            _path_issue(path, "PATH_NOT_FILE", f"Путь {label} не является файлом: {path}.")
        )
    if path.suffix.casefold() not in expected_suffixes:
        suffixes = ", ".join(sorted(expected_suffixes))
        issues.append(
            _path_issue(
                path, "PATH_EXTENSION", f"Файл {label} должен иметь расширение {suffixes}: {path}."
            )
        )
    try:
        with path.open("rb"):
            pass
    except OSError as error:
        issues.append(
            _path_issue(path, "PATH_UNREADABLE", f"Файл {label} недоступен для чтения: {error}.")
        )
    return issues


def _load_schema(
    path: Path,
    label: str,
    checker: Callable[[Any, Path, list[DiagnosticIssue]], None],
    *,
    read_only: bool = True,
) -> list[DiagnosticIssue]:
    issues: list[DiagnosticIssue] = []
    try:
        with openpyxl_read_warnings() as caught:
            workbook = load_workbook(path, read_only=read_only, data_only=False, keep_links=False)
        issues.extend(
            [
                DiagnosticIssue(
                    code="OPENPYXL_WARNING",
                    severity=IssueSeverity.WARNING,
                    message=str(warning.message),
                    source=label,
                    locations=(SourceLocation(file=str(path.resolve())),),
                )
                for warning in caught
            ]
        )
        try:
            checker(workbook, path, issues)
        finally:
            workbook.close()
    except (OSError, InvalidFileException, KeyError, TypeError, ValueError) as error:
        issues.append(
            DiagnosticIssue(
                code="WORKBOOK_OPEN_FAILED",
                severity=IssueSeverity.ERROR,
                message=f"Не удалось открыть {label}: {error}.",
                source=str(path),
                locations=(SourceLocation(file=str(path.resolve())),),
            )
        )
    return issues


def _check_calculator(workbook: Any, path: Path, issues: list[DiagnosticIssue]) -> None:
    sheetnames = workbook.sheetnames  # type: ignore[attr-defined]
    if "Данные" not in sheetnames:
        issues.append(
            DiagnosticIssue(
                code="CALCULATOR_DATA_SHEET_MISSING",
                severity=IssueSeverity.ERROR,
                message="В калькуляторе отсутствует лист 'Данные'.",
                source="calculator",
                locations=(SourceLocation(file=str(path.resolve()), sheet="Данные"),),
            )
        )
        return
    worksheet = workbook["Данные"]  # type: ignore[index]
    headers = tuple(cell.value for cell in worksheet[6])
    header_map = {
        normalized_header(value): index for index, value in enumerate(headers) if value is not None
    }
    missing = [name for name in TARGET_FIELDS if normalized_header(name) not in header_map]
    if missing:
        issues.append(
            DiagnosticIssue(
                code="CALCULATOR_HEADERS_MISSING",
                severity=IssueSeverity.ERROR,
                message=f"В строке 6 калькулятора отсутствуют заголовки: {', '.join(missing)}.",
                source="calculator",
                locations=(SourceLocation(file=str(path.resolve()), sheet="Данные"),),
            )
        )
    if "tblData" not in worksheet.tables:
        issues.append(
            DiagnosticIssue(
                code="CALCULATOR_TABLE_MISSING",
                severity=IssueSeverity.ERROR,
                message="На листе 'Данные' отсутствует таблица tblData.",
                source="calculator",
                locations=(SourceLocation(file=str(path.resolve()), sheet="Данные"),),
            )
        )


def _check_fund(workbook: Any, path: Path, issues: list[DiagnosticIssue]) -> None:
    dated = [
        str(worksheet.title).strip()
        for worksheet in workbook.worksheets  # type: ignore[attr-defined]
        if DATE_SHEET_RE.fullmatch(str(worksheet.title).strip())
        and not str(worksheet.title).strip().upper().startswith("RSPN")
    ]
    if not dated:
        issues.append(
            DiagnosticIssue(
                code="FUND_DATE_SHEET_NOT_FOUND",
                severity=IssueSeverity.ERROR,
                message="В фонде отсутствует подходящий датированный лист.",
                source="fund",
                locations=(SourceLocation(file=str(path.resolve())),),
            )
        )


def _check_gdi(workbook: Any, path: Path, issues: list[DiagnosticIssue]) -> None:
    if GDI_SHEET not in workbook.sheetnames:  # type: ignore[attr-defined]
        issues.append(
            DiagnosticIssue(
                code="GDI_SHEET_MISSING",
                severity=IssueSeverity.ERROR,
                message=f"В книге ГДИ отсутствует лист {GDI_SHEET!r}.",
                source="gdi",
                locations=(SourceLocation(file=str(path.resolve()), sheet=GDI_SHEET),),
            )
        )
        return
    if find_gdi_header(workbook[GDI_SHEET]) is None:  # type: ignore[index]
        aliases = ", ".join(GDI_HEADER_ALIASES)
        issues.append(
            DiagnosticIssue(
                code="GDI_HEADERS_MISSING",
                severity=IssueSeverity.ERROR,
                message=f"На листе ГДИ не найдены обязательные заголовки: {aliases}.",
                source="gdi",
                locations=(SourceLocation(file=str(path.resolve()), sheet=GDI_SHEET),),
            )
        )


def _check_lha(workbook: Any, path: Path, issues: list[DiagnosticIssue]) -> None:
    if LHA_SHEET not in workbook.sheetnames:  # type: ignore[attr-defined]
        issues.append(
            DiagnosticIssue(
                code="LHA_SHEET_MISSING",
                severity=IssueSeverity.ERROR,
                message=f"В книге ЛХА отсутствует лист {LHA_SHEET!r}.",
                source="lha",
                locations=(SourceLocation(file=str(path.resolve()), sheet=LHA_SHEET),),
            )
        )
        return
    if find_lha_header(workbook[LHA_SHEET]) is None:  # type: ignore[index]
        aliases = ", ".join(LHA_HEADER_ALIASES)
        issues.append(
            DiagnosticIssue(
                code="LHA_HEADERS_MISSING",
                severity=IssueSeverity.ERROR,
                message=f"На листе ЛХА не найдены обязательные заголовки: {aliases}.",
                source="lha",
                locations=(SourceLocation(file=str(path.resolve()), sheet=LHA_SHEET),),
            )
        )


def _check_daily(workbook: Any, path: Path, issues: list[DiagnosticIssue]) -> None:
    if DAILY_SHEET not in workbook.sheetnames:  # type: ignore[attr-defined]
        issues.append(
            DiagnosticIssue(
                code="DAILY_SHEET_MISSING",
                severity=IssueSeverity.ERROR,
                message=f"В суточном рапорте отсутствует лист {DAILY_SHEET!r}.",
                source="daily_report",
                locations=(SourceLocation(file=str(path.resolve()), sheet=DAILY_SHEET),),
            )
        )
        return
    if _find_daily_header(workbook[DAILY_SHEET]) is None:  # type: ignore[index]
        issues.append(
            DiagnosticIssue(
                code="DAILY_HEADERS_MISSING",
                severity=IssueSeverity.ERROR,
                message="На листе суточного рапорта не найдены заголовки ГСК и СКВ.",
                source="daily_report",
                locations=(SourceLocation(file=str(path.resolve()), sheet=DAILY_SHEET),),
            )
        )


def validate_inputs(paths: SourcePaths) -> ValidationResult:
    """Validate all paths and workbook schemas in one pass of findings."""

    issues: list[DiagnosticIssue] = []
    source_specs = (
        (paths.calculator, {".xlsx"}, "калькулятор", _check_calculator),
        (paths.fund, {".xlsx"}, "фонд скважин", _check_fund),
        (paths.gdi, {".xlsx"}, "сводная таблица ГДИ", _check_gdi),
        (paths.lha, {".xlsm"}, "база ЛХА", _check_lha),
        (paths.daily_report, {".xlsm"}, "суточный рапорт", _check_daily),
    )
    for path, suffixes, label, checker in source_specs:
        path_issues = _check_path(path, suffixes, label)
        issues.extend(path_issues)
        if not any(issue.severity is IssueSeverity.ERROR for issue in path_issues):
            issues.extend(_load_schema(path, label, checker, read_only=label != "калькулятор"))

    if paths.output.suffix.casefold() != ".xlsx":
        issues.append(
            _path_issue(
                paths.output, "OUTPUT_EXTENSION", "Путь результата должен иметь расширение .xlsx."
            )
        )
    if paths.output.resolve() == paths.calculator.resolve():
        issues.append(
            _path_issue(
                paths.output,
                "OUTPUT_EQUALS_INPUT",
                (
                    "Результат не может совпадать с исходным калькулятором; исходный "
                    "файл защищен от перезаписи."
                ),
            )
        )
    if not paths.output.parent.exists():
        issues.append(
            _path_issue(
                paths.output.parent, "OUTPUT_DIRECTORY_MISSING", "Каталог результата не существует."
            )
        )
    return ValidationResult(tuple(issues))
