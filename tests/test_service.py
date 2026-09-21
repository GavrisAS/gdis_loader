from __future__ import annotations

import logging
from pathlib import Path

from gdis_loader.domain.models import DiagnosticIssue, IssueSeverity, LoadReport, SourcePaths
from gdis_loader.service import ServiceResult, _append_issues, run_validate


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
        warnings=[issue.code],
    )

    result = ServiceResult(report)
    summary = result.summary()

    assert not result.has_errors
    assert result.warning_count == 1
    assert result.has_capacity_warning
    assert "Предупреждений: 1" in summary
    assert "строки после 100" in summary


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
