from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

from gdis_loader.domain.models import (
    DiagnosticIssue,
    FundCategory,
    FundParseResult,
    FundWell,
    GdiRecord,
    IssueSeverity,
    LhaRecord,
    LoadReport,
    SourcePaths,
)
from gdis_loader.matching.matcher import GdiIndex
from gdis_loader.matching.normalize import normalize_field_name, normalize_plast
from gdis_loader.readers.lha import LhaIndex
from gdis_loader.service import ServiceResult, _append_issues, _build_target_rows, run_validate


def _paths(tmp_path: Path) -> SourcePaths:
    return SourcePaths(
        calculator=tmp_path / "calculator.xlsx",
        fund=tmp_path / "fund.xlsx",
        gdi=tmp_path / "gdi.xlsx",
        lha=tmp_path / "lha.xlsm",
        daily_report=tmp_path / "daily.xlsm",
        output=tmp_path / "result.xlsx",
    )


def test_validate_does_not_claim_that_rows_were_written(tmp_path: Path) -> None:
    result = run_validate(_paths(tmp_path), tmp_path / "validate.log")

    assert result.has_errors
    assert result.report.rows_prepared == 0
    assert result.report.rows_written == 0
    assert not (tmp_path / "result.xlsx").exists()
    assert Path(result.report.diagnostic_path or "").is_file()


def test_service_result_exposes_errors_and_capacity_warning() -> None:
    issue = DiagnosticIssue(
        code="DATA_ROWS_EXCEED_CALCULATOR_FORMULA_CAPACITY",
        severity=IssueSeverity.WARNING,
        message="После 100 строки расчетные листы не расширены.",
        source="calculator",
    )
    report = LoadReport(
        timestamp="2026-09-21T00:00:00+00:00",
        app_version="0.1.0",
        python_version="3.14.0",
        input_paths={},
        fund_total=129,
        rows_prepared=129,
        issues=[issue],
        warnings=[issue.message],
    )

    result = ServiceResult(report)
    summary = result.summary()

    assert not result.has_errors
    assert result.warning_count == 1
    assert result.has_capacity_warning
    assert "Предупреждений: 1" in summary
    assert "строки после 100" in summary
    assert len(report.warnings) == result.warning_count


def test_warning_list_contains_only_warning_messages() -> None:
    warning = DiagnosticIssue(
        code="TEST_WARNING",
        severity=IssueSeverity.WARNING,
        message="тестовое предупреждение",
    )
    info = DiagnosticIssue(
        code="TEST_INFO",
        severity=IssueSeverity.INFO,
        message="тестовая информация",
    )
    report = LoadReport(
        timestamp="now",
        app_version="0.1.0",
        python_version="3.14.0",
        input_paths={},
    )

    _append_issues(report, (warning, info))

    assert report.warnings == [warning.message]
    assert len(report.warnings) == sum(
        issue.severity is IssueSeverity.WARNING for issue in report.issues
    )


def test_lha_not_found_is_not_added_for_selection_conflict() -> None:
    field = "Береговое"
    plast = "ПК1"
    fund_well = FundWell(
        raw_display="11",
        base_well_id="11",
        field_name=field,
        normalized_field=normalize_field_name(field),
        object_name=f"{field} ({plast})",
        source_category=FundCategory.PRODUCING,
        fund_date=date(2026, 8, 1),
        source_row=2,
        source_column="C",
        object_plast_hint=plast,
    )
    gdi_record = GdiRecord(
        raw_field_name=field,
        normalized_field=normalize_field_name(field),
        raw_well_name="11",
        base_well_id="11",
        raw_plast=plast,
        normalized_plast=normalize_plast(plast),
        research_type="ИД",
        study_date=datetime(2026, 7, 1),
        rfp_result=None,
        lnd_reliability=None,
        gtm_date=None,
        source_row=2,
    )
    latest = datetime(2026, 7, 2)
    lha_index = LhaIndex(
        [
            LhaRecord(
                raw_field_name=field,
                normalized_field=normalize_field_name(field),
                raw_well_name="11",
                base_well_id="11",
                raw_plast=plast,
                normalized_plast=normalize_plast(plast),
                measured_at=latest,
                cl_value=10,
                vgf_value=None,
                source_row=2,
            ),
            LhaRecord(
                raw_field_name=field,
                normalized_field=normalize_field_name(field),
                raw_well_name="11",
                base_well_id="11",
                raw_plast=plast,
                normalized_plast=normalize_plast(plast),
                measured_at=latest,
                cl_value=11,
                vgf_value=None,
                source_row=3,
            ),
        ]
    )
    report = LoadReport(
        timestamp="now",
        app_version="0.1.0",
        python_version="3.14.0",
        input_paths={},
    )

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex([gdi_record]),
        lha_index,
        report,
    )

    assert rows[0].cl_current is None
    assert report.without_lha == 1
    assert any(issue.code == "LHA_DUPLICATE_TIMESTAMP_CONFLICT" for issue in report.issues)
    assert not any(issue.code == "LHA_NOT_FOUND" for issue in report.issues)


def test_info_issue_is_logged_at_info_level(caplog) -> None:  # type: ignore[no-untyped-def]
    issue = DiagnosticIssue(
        code="TEST_INFO",
        severity=IssueSeverity.INFO,
        message="тестовая информация",
    )
    report = LoadReport(
        timestamp="now",
        app_version="0.1.0",
        python_version="3.14.0",
        input_paths={},
    )
    logger = logging.getLogger("gdis_loader.service")
    old_level = logger.level
    old_propagate = logger.propagate
    logger.addHandler(caplog.handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        _append_issues(report, (issue,))
    finally:
        logger.removeHandler(caplog.handler)
        logger.setLevel(old_level)
        logger.propagate = old_propagate

    assert [(record.levelno, record.message) for record in caplog.records] == [
        (logging.INFO, "TEST_INFO: тестовая информация")
    ]
