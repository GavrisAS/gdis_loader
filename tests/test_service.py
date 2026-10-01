from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

from gdis_loader.domain.models import (
    DatePrecision,
    DiagnosticIssue,
    FundCategory,
    FundParseResult,
    FundWell,
    GdiKind,
    GdiRecord,
    IssueSeverity,
    LhaRecord,
    LoadReport,
    PartialDate,
    SourceLocation,
    SourcePaths,
    WellEventKind,
    WellHistory,
    WellStage,
)
from gdis_loader.matching.matcher import GdiIndex
from gdis_loader.matching.normalize import normalize_field_name, normalize_plast, normalize_well_id
from gdis_loader.readers.lha import LhaIndex
from gdis_loader.service import ServiceResult, _append_issues, _build_target_rows, run_validate


def _paths(tmp_path: Path) -> SourcePaths:
    return SourcePaths(
        calculator=tmp_path / "calculator.xlsx",
        fund=tmp_path / "fund.xlsx",
        gdi=tmp_path / "gdi.xlsx",
        lha=tmp_path / "lha.xlsm",
        daily_report=tmp_path / "daily.xlsm",
        well_history=tmp_path / "well_history.xlsx",
        output=tmp_path / "result.xlsx",
    )


def _fund_identity(
    field: str,
    *,
    raw_well: str = "022",
    base_well_id: str = "22",
    row: int = 12,
) -> FundWell:
    return FundWell(
        raw_display=raw_well,
        base_well_id=base_well_id,
        field_name=field,
        normalized_field=normalize_field_name(field),
        object_name=f"{field} (ПК-1)",
        source_category=FundCategory.PRODUCING,
        fund_date=date(2026, 8, 1),
        source_row=row,
        source_column="C",
        object_plast_hint="ПК1",
        source_file="fund.xlsx",
        source_sheet="01.08.2026",
        field_cell=f"A{row - 1}",
        well_cell=f"C{row}",
        plast_cell=f"B{row - 1}",
    )


def _gdi_identity(
    field: str,
    *,
    raw_well: str = "22",
    base_well_id: str = "22",
    raw_plast: str = "ПК-1",
    when: datetime = datetime(2026, 7, 1),
    row: int = 100,
) -> GdiRecord:
    return GdiRecord(
        raw_field_name=field,
        normalized_field=normalize_field_name(field),
        raw_well_name=raw_well,
        base_well_id=base_well_id,
        raw_plast=raw_plast,
        normalized_plast=normalize_plast(raw_plast),
        research_type="ИД",
        study_date=when,
        rfp_result=None,
        lnd_reliability=None,
        gtm_date=None,
        source_row=row,
        target_well_id=normalize_well_id(raw_well).target_well_id,
        gdi_kind=GdiKind.ID_KVD,
        source_file="gdi.xlsx",
        source_sheet="ГДИС_Сибнефтегаз в целом",
        field_cell=f"A{row}",
        well_cell=f"B{row}",
        plast_cell=f"C{row}",
        date_cell=f"E{row}",
    )


def _history_stage(
    start: PartialDate, *, kind: WellEventKind = WellEventKind.INITIAL
) -> WellHistory:
    location = SourceLocation(
        "history.xlsx", "БЛУ", "C3" if kind is WellEventKind.INITIAL else "I3"
    )
    stage = WellStage(
        field_name="Береговое",
        physical_root="22",
        source_display_well="022",
        target_well_id="22" if kind is WellEventKind.INITIAL else None,
        plast="ПК1",
        event_kind=kind,
        started_at=start,
        stage_sequence=0 if kind is WellEventKind.INITIAL else 1,
        source_location=location,
        raw_block=(),
    )
    return WellHistory(
        field_name="Береговое",
        physical_root="22",
        source_display_well="022",
        events=(),
        stages=(stage,),
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
        app_version="0.1",
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


def test_summary_calls_out_new_identity_diagnostics() -> None:
    issues = [
        DiagnosticIssue(
            code="TARGET_IDENTITY_COLLISION",
            severity=IssueSeverity.WARNING,
            message="collision",
        ),
        DiagnosticIssue(
            code="UNCONFIRMED_WELL_VARIANT_MZS",
            severity=IssueSeverity.WARNING,
            message="mzs",
        ),
        DiagnosticIssue(
            code="FUND_MISSING_SEPARATOR_NORMALIZED",
            severity=IssueSeverity.INFO,
            message="separator",
        ),
    ]
    report = LoadReport(
        timestamp="now",
        app_version="0.1",
        python_version="3.14",
        input_paths={},
        issues=issues,
        warnings=[issue.message for issue in issues if issue.severity is IssueSeverity.WARNING],
    )

    summary = ServiceResult(report).summary()

    assert "Коллизий целевой идентичности: 1" in summary
    assert "МЗС" not in summary
    assert "Нормализаций пропущенного разделителя фонда: 1" in summary


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
        app_version="0.1",
        python_version="3.14.0",
        input_paths={},
    )

    _append_issues(report, (warning, info))

    assert report.warnings == [warning.message]
    assert len(report.warnings) == sum(
        issue.severity is IssueSeverity.WARNING for issue in report.issues
    )


def test_lha_duplicate_timestamp_uses_max_without_not_found_issue() -> None:
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
        target_well_id="11",
        gdi_kind=GdiKind.ID,
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
        app_version="0.1",
        python_version="3.14.0",
        input_paths={},
    )

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex([gdi_record]),
        lha_index,
        report,
    )

    assert rows[0].cl_current == 11
    assert report.without_lha == 0
    assert any(issue.code == "LHA_DUPLICATE_TIMESTAMP_RESOLVED_MAX" for issue in report.issues)
    assert not any(issue.code == "LHA_DUPLICATE_TIMESTAMP_CONFLICT" for issue in report.issues)
    assert not any(issue.code == "LHA_NOT_FOUND" for issue in report.issues)


def test_target_scope_excludes_other_fields_before_collision_checks() -> None:
    fund_wells = (
        _fund_identity("Береговое", row=12),
        _fund_identity("Пырейное", row=21),
    )
    gdi_records = (
        _gdi_identity("Береговое", row=113),
        _gdi_identity("Пырейное", row=1955),
    )
    report = LoadReport(
        timestamp="now",
        app_version="0.1",
        python_version="3.14",
        input_paths={},
    )

    rows = _build_target_rows(
        FundParseResult(fund_wells, date(2026, 8, 1), "01.08.2026"),
        GdiIndex(gdi_records),
        LhaIndex([]),
        report,
    )

    assert len(rows) == 1
    assert rows[0].well == "22"
    assert report.target_field_fund_total == 1
    assert not any(issue.code == "TARGET_IDENTITY_COLLISION" for issue in report.issues)


def test_target_scope_keeps_only_beregovoe_rows() -> None:
    fund_wells = (
        _fund_identity("Береговое", row=12),
        _fund_identity("Пырейное", row=21),
    )
    gdi_records = (
        _gdi_identity("Береговое", row=113),
        _gdi_identity("Пырейное", raw_well="22_ЗБС", row=1955),
    )
    report = LoadReport(
        timestamp="now",
        app_version="0.1",
        python_version="3.14",
        input_paths={},
    )

    _build_target_rows(
        FundParseResult(fund_wells, date(2026, 8, 1), "01.08.2026"),
        GdiIndex(gdi_records),
        LhaIndex([]),
        report,
    )

    assert report.target_field_fund_total == 1
    assert not any(issue.code == "TARGET_IDENTITY_COLLISION" for issue in report.issues)


def test_mzs_is_a_distinct_target_identity_from_parent() -> None:
    fund_well = _fund_identity(
        "Береговое",
        raw_well="10403",
        base_well_id="10403",
        row=16,
    )
    old = _gdi_identity(
        "Береговое",
        raw_well="10403_МЗС",
        base_well_id="10403",
        when=datetime(2025, 11, 1),
        row=1500,
    )
    latest = _gdi_identity(
        "Береговое",
        raw_well="10403_МЗС",
        base_well_id="10403",
        when=datetime(2025, 11, 5),
        row=1591,
    )
    report = LoadReport(
        timestamp="now",
        app_version="0.1",
        python_version="3.14",
        input_paths={},
    )

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex((old, latest)),
        LhaIndex([]),
        report,
    )

    assert rows[0].well == "10403"
    assert report.ambiguous == 1
    assert report.no_gdi == 0
    assert not any(issue.code == "UNCONFIRMED_WELL_VARIANT_MZS" for issue in report.issues)


def test_confirmed_launch_lnd_depth_and_temporary_gtm_are_written() -> None:
    fund_well = _fund_identity("Береговое")
    record = replace(
        _gdi_identity("Береговое"),
        rfp_result="да",
        lnd_reliability="Высокая",
        depth_raw_value=0,
        depth_value=0.0,
        rfp_cell="AU100",
        lnd_reliability_cell="AW100",
        depth_cell="N100",
    )
    report = LoadReport("now", "0.1", "3.14", {})

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex((record,)),
        LhaIndex(()),
        report,
        (_history_stage(PartialDate(2020, 1, 1, DatePrecision.DAY)),),
        date(2026, 10, 1),
    )

    assert rows[0].launch_date == date(2020, 1, 1)
    assert rows[0].gtm == "Нет"
    assert rows[0].lnd == "Нет"
    assert rows[0].downhole_sensors == "Нет"
    assert report.launch_date_filled == 1
    assert report.lnd_false == 1
    assert report.downhole_no == 1


def test_lnd_positive_condition_succeeds_when_second_value_is_missing() -> None:
    fund_well = _fund_identity("Береговое")
    record = replace(
        _gdi_identity("Береговое"),
        rfp_result="нет",
        lnd_reliability=None,
        depth_raw_value=2,
        depth_value=2.0,
        rfp_cell="AU100",
        lnd_reliability_cell="AW100",
        depth_cell="N100",
    )
    report = LoadReport("now", "0.1", "3.14", {})

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex((record,)),
        LhaIndex(()),
        report,
        (_history_stage(PartialDate(2020, 1, 1, DatePrecision.DAY)),),
    )

    assert rows[0].lnd == "Да"
    assert rows[0].downhole_sensors == "Да"
    assert report.lnd_true == 1
    assert report.lnd_unknown == 0


def test_lnd_and_depth_unknowns_stay_blank_with_source_cells() -> None:
    fund_well = _fund_identity("Береговое")
    record = replace(
        _gdi_identity("Береговое"),
        rfp_result="да",
        lnd_reliability=None,
        depth_raw_value=None,
        depth_value=None,
        rfp_cell="AU100",
        lnd_reliability_cell="AW100",
        depth_cell="N100",
    )
    report = LoadReport("now", "0.1", "3.14", {})

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex((record,)),
        LhaIndex(()),
        report,
        (_history_stage(PartialDate(2020, 1, 1, DatePrecision.DAY)),),
    )

    assert rows[0].lnd is None
    assert rows[0].downhole_sensors is None
    assert report.lnd_unknown == 1
    assert report.downhole_unknown == 1
    lnd_issue = next(issue for issue in report.issues if issue.code == "LND_SOURCE_INCOMPLETE")
    depth_issue = next(issue for issue in report.issues if issue.code == "GDI_DEPTH_UNKNOWN")
    assert lnd_issue.locations == (
        SourceLocation("gdi.xlsx", "ГДИС_Сибнефтегаз в целом", "AU100"),
        SourceLocation("gdi.xlsx", "ГДИС_Сибнефтегаз в целом", "AW100"),
    )
    assert depth_issue.locations == (
        SourceLocation("gdi.xlsx", "ГДИС_Сибнефтегаз в целом", "N100"),
    )


def test_month_precision_launch_stays_blank_with_exact_provenance() -> None:
    fund_well = _fund_identity("Береговое")
    record = replace(_gdi_identity("Береговое"), date_cell="E100")
    report = LoadReport("now", "0.1", "3.14", {})

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex((record,)),
        LhaIndex(()),
        report,
        (_history_stage(PartialDate(2020, 7, None, DatePrecision.MONTH)),),
    )

    assert rows[0].launch_date is None
    assert report.launch_date_incomplete == 1
    issue = next(
        issue for issue in report.issues if issue.code == "WELL_HISTORY_DATE_INCOMPLETE_PRECISION"
    )
    assert issue.locations == (SourceLocation("history.xlsx", "БЛУ", "C3"),)


def test_same_month_launch_and_gdi_is_lifecycle_ambiguous() -> None:
    fund_well = _fund_identity("Береговое")
    record = replace(
        _gdi_identity("Береговое", when=datetime(2023, 6, 15)),
        date_cell="E100",
    )
    history = _history_stage(PartialDate(2023, 6, None, DatePrecision.MONTH))
    report = LoadReport("now", "0.1", "3.14", {})

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex((record,)),
        LhaIndex(()),
        report,
        (history,),
    )

    assert rows[0].launch_date is None
    issue = next(issue for issue in report.issues if issue.code == "WELL_HISTORY_STAGE_AMBIGUOUS")
    assert SourceLocation("history.xlsx", "БЛУ", "C3") in issue.locations
    assert SourceLocation("gdi.xlsx", "ГДИС_Сибнефтегаз в целом", "E100") in issue.locations


def test_info_issue_is_logged_at_info_level(caplog) -> None:  # type: ignore[no-untyped-def]
    issue = DiagnosticIssue(
        code="TEST_INFO",
        severity=IssueSeverity.INFO,
        message="тестовая информация",
    )
    report = LoadReport(
        timestamp="now",
        app_version="0.1",
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
