"""Typed domain models shared by readers, matching, and the application service."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class IssueSeverity(StrEnum):
    """Severity used for diagnostics and source validation."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class FundCategory(StrEnum):
    """Operational fund categories read from columns C, D, G, and H."""

    PRODUCING = "дающие газ"
    STOPPED_IN_REPORTING_MONTH = "остановленные в отчетном месяце"
    INACTIVE_CURRENT_YEAR = "бездействующие текущего года"
    INACTIVE_PREVIOUS_YEARS = "бездействующие прошлых лет"


class MatchStatus(StrEnum):
    """Explicit result of conservative well matching."""

    MATCHED = "MATCHED"
    NO_GDI = "NO_GDI"
    AMBIGUOUS = "AMBIGUOUS"
    INVALID_SOURCE = "INVALID_SOURCE"


CellValue = str | int | float | date | datetime | None

TARGET_FIELDS: tuple[str, ...] = (
    "Скважина",
    "Пласт",
    "Состояние",
    "Дата запуска",
    "Количество ГДИ",
    "Глубинные датчики",
    "Расходомер",
    "ГТМ",
    "Недостаточно ГДИС",
    "Снижение продуктивности",
    "Рост хлора",
    "Cl текущий",
    "Cl предыдущий",
    "Проблемы ГДМ",
    "ЛНД",
    "Последний АДД",
    "Не проведен АДД",
    "Продолжительность без ГДИ",
    "Удельное количество ГДИ",
    "ВГФ текущий",
    "ВГФ предыдущий",
    "Продолжительность без ИД",
    "Продолжительность без КВД",
    "Техническая возможность",
    "Дебит",
    "Manual μ",
)

INTENTIONALLY_BLANK_FIELDS: tuple[str, ...] = (
    "Состояние",
    "Дата запуска",
    "Количество ГДИ",
    "Глубинные датчики",
    "Расходомер",
    "ГТМ",
    "Недостаточно ГДИС",
    "Снижение продуктивности",
    "Рост хлора",
    "Проблемы ГДМ",
    "ЛНД",
    "Последний АДД",
    "Не проведен АДД",
    "Продолжительность без ГДИ",
    "Удельное количество ГДИ",
    "Продолжительность без ИД",
    "Продолжительность без КВД",
    "Техническая возможность",
    "Дебит",
    "Manual μ",
)


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """Structured origin of a value involved in a diagnostic."""

    file: str
    sheet: str | None = None
    cell: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {"file": self.file, "sheet": self.sheet, "cell": self.cell}


def source_locations(
    source_file: str, source_sheet: str | None, *cells: str | None
) -> tuple[SourceLocation, ...]:
    """Build immutable locations for the supplied source cells."""

    if not source_file:
        return ()
    return tuple(
        SourceLocation(file=source_file, sheet=source_sheet, cell=cell)
        for cell in cells
        if cell is not None
    )


@dataclass(frozen=True, slots=True)
class DiagnosticIssue:
    """One concise diagnostic item suitable for both logs and JSON."""

    code: str
    severity: IssueSeverity
    message: str
    source: str | None = None
    coordinate: str | None = None
    well_id: str | None = None
    locations: tuple[SourceLocation, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "source": self.source,
            "coordinate": self.coordinate,
            "well_id": self.well_id,
            "locations": [location.to_dict() for location in self.locations],
        }


@dataclass(frozen=True, slots=True)
class FundWell:
    """One well occurrence from the operational fund."""

    raw_display: str
    base_well_id: str | None
    field_name: str
    normalized_field: str
    object_name: str
    source_category: FundCategory
    fund_date: date
    source_row: int
    source_column: str
    object_plast_hint: str | None = None
    source_file: str = ""
    source_sheet: str | None = None
    field_cell: str | None = None
    well_cell: str | None = None
    plast_cell: str | None = None

    @property
    def locations(self) -> tuple[SourceLocation, ...]:
        """Return the fund cells that identify this occurrence."""

        cell = self.well_cell or f"{self.source_column}{self.source_row}"
        return source_locations(
            self.source_file,
            self.source_sheet,
            self.field_cell,
            self.plast_cell,
            cell,
        )


@dataclass(frozen=True, slots=True)
class FundParseResult:
    """Fund wells and diagnostics for the selected dated worksheet."""

    wells: tuple[FundWell, ...]
    fund_date: date | None
    sheet_name: str | None
    issues: tuple[DiagnosticIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class GdiRecord:
    """A row from the GDI history sheet."""

    raw_field_name: str | None
    normalized_field: str | None
    raw_well_name: str | None
    base_well_id: str | None
    raw_plast: str | None
    normalized_plast: str | None
    research_type: str | None
    study_date: datetime | None
    rfp_result: str | None
    lnd_reliability: str | None
    gtm_date: datetime | None
    source_row: int
    source_file: str = ""
    source_sheet: str | None = None
    field_cell: str | None = None
    well_cell: str | None = None
    plast_cell: str | None = None
    date_cell: str | None = None
    gtm_date_cell: str | None = None

    @property
    def locations(self) -> tuple[SourceLocation, ...]:
        """Return identity/date cells useful for matching diagnostics."""

        return source_locations(
            self.source_file,
            self.source_sheet,
            self.field_cell,
            self.well_cell,
            self.plast_cell,
            self.date_cell,
        )

    @property
    def completion_key(self) -> tuple[str | None, str | None, str | None]:
        """Values that define a distinct current completion configuration."""

        return (self.raw_well_name, self.normalized_plast, self.normalized_field)


@dataclass(frozen=True, slots=True)
class LhaRecord:
    """A LHA measurement row; each metric can independently be missing."""

    raw_field_name: str | None
    normalized_field: str | None
    raw_well_name: str | None
    base_well_id: str | None
    raw_plast: str | None
    normalized_plast: str | None
    measured_at: datetime | None
    cl_value: float | None
    vgf_value: float | None
    source_row: int
    source_file: str = ""
    source_sheet: str | None = None
    field_cell: str | None = None
    well_cell: str | None = None
    plast_cell: str | None = None
    date_cell: str | None = None
    cl_cell: str | None = None
    vgf_cell: str | None = None

    def metric_locations(self, metric: str) -> tuple[SourceLocation, ...]:
        """Return the exact measurement cell for a metric."""

        cell = self.cl_cell if metric == "cl_value" else self.vgf_cell
        return source_locations(self.source_file, self.source_sheet, cell)


@dataclass(frozen=True, slots=True)
class LhaValues:
    """Latest and previous valid measurements for the two supported metrics."""

    cl_current: float | None = None
    cl_previous: float | None = None
    vgf_current: float | None = None
    vgf_previous: float | None = None


@dataclass(frozen=True, slots=True)
class LhaSelection:
    """Selected LHA values together with source-conflict diagnostics."""

    values: LhaValues
    issues: tuple[DiagnosticIssue, ...] = ()

    @property
    def cl_current(self) -> float | None:
        return self.values.cl_current

    @property
    def cl_previous(self) -> float | None:
        return self.values.cl_previous

    @property
    def vgf_current(self) -> float | None:
        return self.values.vgf_current

    @property
    def vgf_previous(self) -> float | None:
        return self.values.vgf_previous


@dataclass(frozen=True, slots=True)
class DailyTelemetryRow:
    """Daily report row retained for a future debit aggregation rule."""

    raw_field_name: str | None
    raw_well_name: str | None
    base_well_id: str | None
    source_row: int
    daily_values: tuple[float | None, ...]
    source_file: str = ""
    source_sheet: str | None = None
    field_cell: str | None = None
    well_cell: str | None = None
    daily_cells: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Conservative result with candidate evidence for ambiguous cases."""

    status: MatchStatus
    fund_well: FundWell
    record: GdiRecord | None = None
    candidates: tuple[GdiRecord, ...] = ()
    explanation: str = ""


@dataclass(frozen=True, slots=True)
class TargetRow:
    """The complete 26-field target row, with only approved values populated."""

    well: CellValue = None
    plast: CellValue = None
    state: CellValue = None
    launch_date: CellValue = None
    gdi_count: CellValue = None
    downhole_sensors: CellValue = None
    flowmeter: CellValue = None
    gtm: CellValue = None
    insufficient_gdi: CellValue = None
    productivity_decline: CellValue = None
    chlorine_growth: CellValue = None
    cl_current: CellValue = None
    cl_previous: CellValue = None
    gdm_problems: CellValue = None
    lnd: CellValue = None
    last_add: CellValue = None
    add_not_done: CellValue = None
    duration_without_gdi: CellValue = None
    specific_gdi_count: CellValue = None
    vgf_current: CellValue = None
    vgf_previous: CellValue = None
    duration_without_id: CellValue = None
    duration_without_kvd: CellValue = None
    technical_possibility: CellValue = None
    debit: CellValue = None
    manual_mu: CellValue = None

    def as_mapping(self) -> dict[str, CellValue]:
        """Return values in the target workbook's named-column order."""

        values = (
            self.well,
            self.plast,
            self.state,
            self.launch_date,
            self.gdi_count,
            self.downhole_sensors,
            self.flowmeter,
            self.gtm,
            self.insufficient_gdi,
            self.productivity_decline,
            self.chlorine_growth,
            self.cl_current,
            self.cl_previous,
            self.gdm_problems,
            self.lnd,
            self.last_add,
            self.add_not_done,
            self.duration_without_gdi,
            self.specific_gdi_count,
            self.vgf_current,
            self.vgf_previous,
            self.duration_without_id,
            self.duration_without_kvd,
            self.technical_possibility,
            self.debit,
            self.manual_mu,
        )
        return dict(zip(TARGET_FIELDS, values, strict=True))


@dataclass(slots=True)
class LoadReport:
    """Machine-readable summary of one validation or update run.

    ``without_lha`` counts rows without selected Cl/VGF values.  It can include
    rows whose source records were found but could not be selected because of a
    diagnostic conflict; it does not prove that LHA records are physically
    absent.
    """

    timestamp: str
    app_version: str
    python_version: str
    input_paths: dict[str, str]
    fund_date: date | None = None
    fund_total: int = 0
    matched: int = 0
    no_gdi: int = 0
    ambiguous: int = 0
    invalid_source: int = 0
    with_lha_cl: int = 0
    with_lha_vgf: int = 0
    without_lha: int = 0
    rows_prepared: int = 0
    rows_written: int = 0
    warnings: list[str] = field(default_factory=list)
    issues: list[DiagnosticIssue] = field(default_factory=list)
    intentionally_blank_fields: tuple[str, ...] = INTENTIONALLY_BLANK_FIELDS
    output_path: str | None = None
    diagnostic_path: str | None = None
    log_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize without leaking Python enum/date representations."""

        result: dict[str, Any] = asdict(self)
        result["fund_date"] = self.fund_date.isoformat() if self.fund_date else None
        result["issues"] = [issue.to_dict() for issue in self.issues]
        return result


@dataclass(frozen=True, slots=True)
class SourcePaths:
    """Input and output paths shared by CLI, GUI, and application service."""

    calculator: Path
    fund: Path
    gdi: Path
    lha: Path
    daily_report: Path
    output: Path
