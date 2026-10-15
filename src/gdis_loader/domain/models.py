"""Typed domain models shared by readers, matching, and the application service."""

from __future__ import annotations

import re
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

    PRODUCING = "дающие"
    PRODUCING_GAS = "дающие газ"
    STOPPED_IN_REPORTING_MONTH = "остановленные в отчетном месяце"
    INACTIVE_CURRENT_YEAR = "бездействующие текущего года"
    INACTIVE_PREVIOUS_YEARS = "бездействующие прошлых лет"


class MatchStatus(StrEnum):
    """Explicit result of conservative well matching."""

    MATCHED = "MATCHED"
    NO_GDI = "NO_GDI"
    AMBIGUOUS = "AMBIGUOUS"
    INVALID_SOURCE = "INVALID_SOURCE"


class DatePrecision(StrEnum):
    """Known calendar precision of a source date."""

    DAY = "day"
    MONTH = "month"
    YEAR = "year"


class GdiKind(StrEnum):
    """Customer-approved top-level classification of a GDI source row."""

    ID = "ID"
    ID_KVD = "ID_KVD"
    KVD = "KVD"
    KSD = "KSD"

    @property
    def valid(self) -> bool:
        return self in {self.ID, self.ID_KVD, self.KVD, self.KSD}

    @property
    def has_id(self) -> bool:
        return self in {self.ID, self.ID_KVD}

    @property
    def has_pressure(self) -> bool:
        return self in {self.KVD, self.KSD, self.ID_KVD}

    EXCLUDED = "EXCLUDED"
    UNKNOWN = "UNKNOWN"


class WellEventKind(StrEnum):
    """Event labels stored in the well history source."""

    INITIAL = "INITIAL"
    ZBS = "ЗБС"
    PVLG = "ПВЛГ"
    PNLG = "ПНЛГ"
    PVR = "ПВР"
    KLK = "КЛК"
    OTHER = "OTHER"


CellValue = str | int | float | bool | date | datetime | None

TARGET_FIELDS: tuple[str, ...] = (
    "Скважина",
    "Пласт",
    "Состояние",
    "Дата запуска",
    "Количество ГДИ",
    "Глубинные датчики",
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
    "Последний АДД",
    "Не проведен АДД",
    "Техническая возможность",
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


@dataclass(frozen=True, slots=True)
class PartialDate:
    """Calendar date that retains the precision present in its source cell."""

    year: int
    month: int | None
    day: int | None
    precision: DatePrecision

    def __post_init__(self) -> None:
        if self.year < 1 or self.year > 9999:
            raise ValueError("year must be in the range 1..9999")
        if self.precision is DatePrecision.YEAR and (
            self.month is not None or self.day is not None
        ):
            raise ValueError("YEAR precision cannot contain month or day")
        if self.precision is DatePrecision.MONTH and (self.month is None or self.day is not None):
            raise ValueError("MONTH precision requires a month and no day")
        if self.precision is DatePrecision.DAY and (self.month is None or self.day is None):
            raise ValueError("DAY precision requires month and day")
        if self.month is not None and not 1 <= self.month <= 12:
            raise ValueError("month must be in the range 1..12")
        if self.day is not None:
            date(self.year, self.month or 1, self.day)

    def to_dict(self) -> dict[str, int | str | None]:
        return {
            "year": self.year,
            "month": self.month,
            "day": self.day,
            "precision": self.precision.value,
        }


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
    target_well_id: str | None = None
    object_plast_hint: str | None = None
    active_zbs_identities: tuple[str, ...] = ()
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

    @property
    def is_rating_eligible(self) -> bool:
        """Return the separately tracked eligibility confirmed for two groups."""

        return self.source_category in {
            FundCategory.PRODUCING,
            FundCategory.PRODUCING_GAS,
            FundCategory.STOPPED_IN_REPORTING_MONTH,
        }


@dataclass(frozen=True, slots=True)
class FundParseResult:
    """Fund wells and diagnostics for the selected dated worksheet."""

    wells: tuple[FundWell, ...]
    fund_date: date | None
    sheet_name: str | None
    issues: tuple[DiagnosticIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class WellEvent:
    """One initial commissioning or GTM event from the well history workbook."""

    field_name: str
    physical_root: str
    source_display_well: str
    plast: str | None
    event_kind: WellEventKind
    event_label: str | None
    event_date: PartialDate | None
    source_location: SourceLocation
    raw_block: tuple[CellValue, ...]
    block_number: int | None = None


@dataclass(frozen=True, slots=True)
class WellStage:
    """A lifecycle interval seeded by a confirmed boundary event."""

    field_name: str
    physical_root: str
    source_display_well: str
    target_well_id: str | None
    plast: str | None
    event_kind: WellEventKind
    started_at: PartialDate
    stage_sequence: int
    source_location: SourceLocation
    raw_block: tuple[CellValue, ...]
    parent_stage_id: int | None = None
    ordinal: int | None = None


@dataclass(frozen=True, slots=True)
class WellHistory:
    """All retained stages and source events for one well history row."""

    field_name: str
    physical_root: str
    source_display_well: str
    events: tuple[WellEvent, ...]
    stages: tuple[WellStage, ...]


@dataclass(frozen=True, slots=True)
class WellHistoryParseResult:
    """Parsed history rows, schema provenance, and date/event diagnostics."""

    histories: tuple[WellHistory, ...]
    issues: tuple[DiagnosticIssue, ...] = ()
    event_counts: dict[str, int] = field(default_factory=dict)
    date_precision_counts: dict[str, int] = field(default_factory=dict)


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
    research_type_cell: str | None = None
    date_cell: str | None = None
    gtm_date_cell: str | None = None
    target_well_id: str | None = None
    gdi_kind: GdiKind = GdiKind.UNKNOWN
    depth_raw_value: CellValue = None
    depth_value: float | None = None
    depth_cell: str | None = None
    rfp_cell: str | None = None
    lnd_reliability_cell: str | None = None
    productivity_a_raw: CellValue = None
    productivity_a_value: float | None = None
    productivity_a_cell: str | None = None
    productivity_b_raw: CellValue = None
    productivity_b_value: float | None = None
    productivity_b_cell: str | None = None
    source_rows: tuple[int, ...] = ()

    @property
    def locations(self) -> tuple[SourceLocation, ...]:
        """Return identity/date cells useful for matching diagnostics."""

        cells = (self.field_cell, self.well_cell, self.plast_cell, self.date_cell)
        if not self.source_file:
            return ()
        return tuple(
            SourceLocation(self.source_file, self.source_sheet, coordinate)
            for row in (self.source_rows or (self.source_row,))
            for cell in cells
            if (coordinate := self._cell_at_row(cell, row)) is not None
        )

    @staticmethod
    def _cell_at_row(cell: str | None, row: int) -> str | None:
        if cell is None:
            return None
        return re.sub(r"\d+$", str(row), cell)

    @property
    def completion_key(self) -> tuple[str | None, str | None, str | None]:
        """Values that define a distinct current completion configuration."""

        return (
            self.target_well_id or self.raw_well_name,
            self.normalized_plast,
            self.normalized_field,
        )

    @property
    def lnd_locations(self) -> tuple[SourceLocation, ...]:
        """Return both exact cells needed for the LND rule, including blanks."""

        if not self.source_file:
            return ()
        return tuple(
            SourceLocation(self.source_file, self.source_sheet, cell)
            for row in (self.source_rows or (self.source_row,))
            for cell in (
                self._cell_at_row(self.rfp_cell, row),
                self._cell_at_row(self.lnd_reliability_cell, row),
            )
            if cell is not None
        )


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
    target_well_id: str | None = None
    raw_cl_value: CellValue = None
    raw_vgf_value: CellValue = None

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
    cl_current_locations: tuple[SourceLocation, ...] = ()
    cl_previous_locations: tuple[SourceLocation, ...] = ()
    vgf_current_locations: tuple[SourceLocation, ...] = ()
    vgf_previous_locations: tuple[SourceLocation, ...] = ()


@dataclass(frozen=True, slots=True)
class ResearchStatusRecord:
    """One dated research row from the new GDM status workbook."""

    raw_well_name: str | None
    base_well_id: str | None
    target_well_id: str | None
    raw_plast: str | None
    normalized_plast: str | None
    research_type: str | None
    study_date: PartialDate | None
    delta_raw: CellValue
    delta_value: float | None
    delta_formula_without_cache: bool
    source_row: int
    source_file: str
    source_sheet: str
    well_cell: str
    plast_cell: str
    research_type_cell: str
    date_cell: str
    delta_cell: str

    @property
    def locations(self) -> tuple[SourceLocation, ...]:
        return source_locations(
            self.source_file,
            self.source_sheet,
            self.well_cell,
            self.plast_cell,
            self.research_type_cell,
            self.date_cell,
            self.delta_cell,
        )


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
    target_well_id: str | None = None
    field_evidence: tuple[SourceLocation, ...] = ()
    report_month: str | None = None
    field_scope_invalid: bool = False
    raw_collector_id: str | None = None


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
    """The complete 25-field target row, with only approved values populated."""

    well: CellValue = None
    plast: CellValue = None
    state: CellValue = None
    launch_date: CellValue = None
    gdi_count: CellValue = None
    downhole_sensors: CellValue = None
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
    input_paths: dict[str, str | None]
    fund_date: date | None = None
    calculation_date: date | None = None
    source_manifest: dict[str, Any] = field(default_factory=dict)
    criteria_snapshot: dict[str, Any] = field(default_factory=dict)
    config_source: str | None = None
    fund_total: int = 0
    fund_total_source: int = 0
    target_field: str | None = None
    available_fields: tuple[str, ...] = ()
    field_coverage: dict[str, dict[str, int | bool | str | None]] = field(default_factory=dict)
    target_field_fund_total: int = 0
    rating_eligible: int = 0
    rating_not_eligible: int = 0
    matched: int = 0
    no_gdi: int = 0
    ambiguous: int = 0
    invalid_source: int = 0
    with_lha_cl: int = 0
    with_lha_vgf: int = 0
    without_lha: int = 0
    rows_prepared: int = 0
    rows_written: int = 0
    well_history_records: int = 0
    well_history_gtm_events: int = 0
    well_history_event_counts: dict[str, int] = field(default_factory=dict)
    well_history_date_precision_counts: dict[str, int] = field(default_factory=dict)
    gdi_kind_counts: dict[str, int] = field(default_factory=dict)
    gdi_raw_kind_counts: dict[str, int] = field(default_factory=dict)
    gdi_raw_record_count: int = 0
    gdi_deduplicated_record_count: int = 0
    gdi_exact_duplicates_collapsed: int = 0
    gdi_nonvalid_labels: dict[str, int] = field(default_factory=dict)
    gdi_pre_launch_excluded: int = 0
    gdi_pre_launch_included: int = 0
    lnd_previous_fallbacks: int = 0
    gdi_reconciliation: list[dict[str, Any]] = field(default_factory=list)
    gdi_kind_unknown: int = 0
    gdi_count_filled: int = 0
    insufficient_gdi_yes: int = 0
    insufficient_gdi_no: int = 0
    productivity_filled: int = 0
    chlorine_growth_filled: int = 0
    duration_without_gdi_filled: int = 0
    duration_without_id_filled: int = 0
    duration_without_kvd_filled: int = 0
    specific_gdi_count_filled: int = 0
    unsuffixed_gdi_assigned: int = 0
    excluded_status_counts: dict[str, int] = field(default_factory=dict)
    field_fill_counts: dict[str, int] = field(default_factory=dict)
    gdm_rows_read: int = 0
    gdm_numeric_delta_rows: int = 0
    gdm_invalid_delta_rows: int = 0
    gdm_missing_delta_rows: int = 0
    gdm_formula_without_cached_delta_rows: int = 0
    gdm_problem_candidate_rows: int = 0
    gdm_target_candidate_rows: int = 0
    gdm_unique_candidate_identities: int = 0
    gdm_multiple_candidate_identities: int = 0
    gdm_fallback_selected: int = 0
    gdm_stale_fallback_rejected: int = 0
    gdm_filled_yes: int = 0
    gdm_filled_no: int = 0
    gdm_blank: int = 0
    gdm_rows_per_target: dict[str, int] = field(default_factory=dict)
    field_provenance: list[dict[str, Any]] = field(default_factory=list)
    lha_duplicate_resolved_max: int = 0
    launch_date_filled: int = 0
    launch_date_incomplete: int = 0
    launch_date_defaulted: int = 0
    launch_date_missing: int = 0
    lnd_true: int = 0
    lnd_false: int = 0
    lnd_unknown: int = 0
    downhole_yes: int = 0
    downhole_no: int = 0
    downhole_unknown: int = 0
    debit_filled: int = 0
    debit_blank: int = 0
    debit_valid_day_count: int = 0
    debit_report_month: str | None = None
    debit_source_sha256: str | None = None
    debit_resolved_ambiguous: int = 0
    debit_still_ambiguous: int = 0
    debit_missing_source: int = 0
    debit_no_valid_days: int = 0
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
        result["calculation_date"] = (
            self.calculation_date.isoformat() if self.calculation_date else None
        )
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
    well_history: Path
    research_status: Path
    output: Path | None = None
