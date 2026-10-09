from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

import gdis_loader.service as service
from gdis_loader.config import CriteriaConfig
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
    LhaRecord,
    LoadReport,
    PartialDate,
    ResearchStatusRecord,
    SourceLocation,
    SourcePaths,
    WellEventKind,
    WellHistory,
    WellHistoryParseResult,
    WellStage,
)
from gdis_loader.excel.writer import TargetWriteResult
from gdis_loader.matching.matcher import GdiIndex
from gdis_loader.matching.normalize import normalize_field_name, normalize_plast, normalize_well_id
from gdis_loader.readers.lha import LhaIndex
from gdis_loader.service import (
    ServiceResult,
    _append_issues,
    _build_target_rows,
    _effective_target_identity,
    _source_lookup_identity,
    default_output_path,
    run_validate,
)
from gdis_loader.validation.sources import ValidationResult


def _paths(tmp_path: Path) -> SourcePaths:
    return SourcePaths(
        calculator=tmp_path / "calculator.xlsx",
        fund=tmp_path / "fund.xlsx",
        gdi=tmp_path / "gdi.xlsx",
        lha=tmp_path / "lha.xlsm",
        daily_report=tmp_path / "daily.xlsm",
        well_history=tmp_path / "well_history.xlsx",
        research_status=tmp_path / "research_status.xlsx",
        output=tmp_path / "result.xlsx",
    )


def _stub_empty_update(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        service,
        "validate_inputs",
        lambda _paths, *_args: ValidationResult((), ("Пырейное",)),
    )
    monkeypatch.setattr(service, "read_fund", lambda _path: FundParseResult((), None, None))
    monkeypatch.setattr(service, "read_gdi", lambda _path: ((), ()))
    monkeypatch.setattr(service, "read_lha", lambda _path: ((), ()))
    monkeypatch.setattr(service, "read_daily_report", lambda _path: ((), ()))
    monkeypatch.setattr(service, "read_research_status", lambda *_args: ((), ()))
    monkeypatch.setattr(service, "read_well_history", lambda *_args: WellHistoryParseResult(()))
    monkeypatch.setattr(service, "_build_target_rows", lambda *_args: ())


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


def test_validate_ignores_output_path_and_does_not_create_its_directory(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    output_directory = tmp_path / "not-created"
    paths = replace(_paths(tmp_path), output=output_directory / "invalid.csv")
    monkeypatch.setattr(
        service,
        "validate_inputs",
        lambda *_args: ValidationResult((), ("Береговое",), {"Береговое": {"fund_rows": 1}}),
    )

    result = run_validate(paths, tmp_path / "validate.log")

    assert not result.has_errors
    assert result.report.available_fields == ("Береговое",)
    assert not output_directory.exists()


def test_update_rejects_output_before_creating_path_side_effects(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    _stub_empty_update(monkeypatch)
    output_directory = tmp_path / "not-created"
    log_path = output_directory / "update.log"
    paths = replace(_paths(tmp_path), output=output_directory / "bad.csv")

    with pytest.raises(service.ServiceError, match="Путь результата"):
        service.run_update(paths, log_path, target_field="Пырейное")

    assert not output_directory.exists()


def test_default_output_name_is_field_specific_and_safe(tmp_path: Path) -> None:
    calculator = tmp_path / "GDIS_Rating_Calculator_FIXED.xlsx"

    assert default_output_path(calculator, "Береговое") == tmp_path / (
        "GDIS_Rating_Calculator_FIXED_UPDATED_Береговое.xlsx"
    )
    assert default_output_path(calculator, "Пырейное") == tmp_path / (
        "GDIS_Rating_Calculator_FIXED_UPDATED_Пырейное.xlsx"
    )
    assert default_output_path(calculator, "ЛУ / тест:  вопрос") == tmp_path / (
        "GDIS_Rating_Calculator_FIXED_UPDATED_ЛУ_тест_вопрос.xlsx"
    )
    assert default_output_path(calculator, 'ЛУ/\\:*?"<>| test') == tmp_path / (
        "GDIS_Rating_Calculator_FIXED_UPDATED_ЛУ_test.xlsx"
    )


def test_update_generates_field_specific_path_only_when_output_is_blank(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    _stub_empty_update(monkeypatch)
    monkeypatch.setattr(
        service,
        "write_target_rows",
        lambda _source, output, _rows: TargetWriteResult(output, 0),
    )
    paths = replace(_paths(tmp_path), output=None)

    result = service.run_update(paths, target_field="Пырейное")

    expected = tmp_path / "calculator_UPDATED_Пырейное.xlsx"
    assert result.output_path == expected
    assert result.report.output_path == str(expected.resolve())
    assert Path(result.report.diagnostic_path or "") == expected.with_suffix(".load-report.json")


def test_update_keeps_explicit_output_path_without_field_suffix(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    _stub_empty_update(monkeypatch)
    monkeypatch.setattr(
        service,
        "write_target_rows",
        lambda _source, output, _rows: TargetWriteResult(output, 0),
    )
    explicit = tmp_path / "custom-result.xlsx"
    paths = replace(_paths(tmp_path), output=explicit)

    result = service.run_update(paths, target_field="Пырейное")

    assert result.output_path == explicit
    assert result.report.output_path == str(explicit.resolve())


def test_json_report_preserves_explicit_criteria_snapshot(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _stub_empty_update(monkeypatch)
    monkeypatch.setattr(
        service,
        "write_target_rows",
        lambda _source, output, _rows: TargetWriteResult(output, 0),
    )
    criteria = CriteriaConfig(
        insufficient_gdi_min_count=3,
        productivity_min_increase=0.25,
        chlorine_current_min_mg_dm3=2100.0,
        chlorine_delta_min_mg_dm3=1100.0,
        downhole_depth_threshold_m=50.0,
        gdm_abs_delta_threshold=7.0,
        gdm_fallback_max_age_days=30,
        gas_rate_working_day_min_rate=10.0,
    )
    criteria_fields = frozenset(criteria.as_dict())
    config_source = tmp_path / "config.toml"

    result = service.run_update(
        _paths(tmp_path),
        target_field="Пырейное",
        criteria_config=criteria,
        config_source=config_source,
        criteria_explicit_fields=criteria_fields,
    )

    expected_snapshot = {
        "config_source": str(config_source),
        "values": criteria.as_dict(),
        "defaults": CriteriaConfig().as_dict(),
        "value_origin": {name: "config" for name in criteria.as_dict()},
    }
    assert result.report.criteria_snapshot == expected_snapshot
    report_path = Path(result.report.diagnostic_path or "")
    serialized_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert serialized_report["criteria_snapshot"] == expected_snapshot


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
    assert "После 100 строки" in summary
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
        target_field="Береговое",
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
        target_field=field,
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
        target_field="Береговое",
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
        target_field="Береговое",
    )

    _build_target_rows(
        FundParseResult(fund_wells, date(2026, 8, 1), "01.08.2026"),
        GdiIndex(gdi_records),
        LhaIndex([]),
        report,
    )

    assert report.target_field_fund_total == 1
    assert not any(issue.code == "TARGET_IDENTITY_COLLISION" for issue in report.issues)


def test_only_confirmed_producing_and_current_period_stopped_rows_are_written() -> None:
    categories = (
        FundCategory.PRODUCING,
        FundCategory.PRODUCING_GAS,
        FundCategory.STOPPED_IN_REPORTING_MONTH,
        FundCategory.INACTIVE_CURRENT_YEAR,
        FundCategory.INACTIVE_PREVIOUS_YEARS,
    )
    wells = tuple(
        replace(
            _fund_identity("Береговое", raw_well=str(index), base_well_id=str(index), row=index),
            source_category=category,
        )
        for index, category in enumerate(categories, 1)
    )
    report = LoadReport("now", "0.1", "3.14", {}, target_field="Береговое")

    rows = _build_target_rows(
        FundParseResult(wells, date(2026, 8, 1), "01.08.2026"),
        GdiIndex(()),
        LhaIndex(()),
        report,
    )

    assert report.target_field_fund_total == 5
    assert report.rating_eligible == 3
    assert report.rating_not_eligible == 2
    assert len(rows) == 3
    assert [row.state for row in rows] == [
        "Дающие газ",
        "Дающие газ",
        "Остановленные в отчетном периоде",
    ]


def test_no_gdi_with_day_launch_writes_zero_count_and_duration_with_provenance() -> None:
    fund_well = _fund_identity("Береговое")
    launch = PartialDate(2020, 1, 1, DatePrecision.DAY)
    report = LoadReport("now", "0.1", "3.14", {}, target_field="Береговое")
    calculation = date(2026, 10, 1)

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex(()),
        LhaIndex(()),
        report,
        (_history_stage(launch),),
        calculation,
    )

    assert rows[0].gdi_count == 0
    assert rows[0].insufficient_gdi == "Да"
    assert rows[0].duration_without_gdi == (calculation - date(2020, 1, 1)).days / 365
    assert rows[0].duration_without_id == rows[0].duration_without_gdi
    assert rows[0].duration_without_kvd == rows[0].duration_without_gdi
    assert rows[0].specific_gdi_count is None
    assert rows[0].downhole_sensors is None
    assert rows[0].productivity_decline is None
    assert rows[0].lnd is None
    assert report.gdi_count_filled == 1
    assert report.insufficient_gdi_yes == 1
    zero_count_issue = next(
        issue for issue in report.issues if issue.code == "GDI_SPECIFIC_RATE_ZERO_COUNT"
    )
    assert "μi должен быть 0" in zero_count_issue.message
    assert "должен быть исключён из итогового λ" in zero_count_issue.message
    assert "пока не обеспечивают это поведение полностью" in zero_count_issue.message
    assert "критерий не участвует" not in zero_count_issue.message
    count_provenance = next(
        item for item in report.field_provenance if item["field"] == "Количество ГДИ"
    )
    assert count_provenance["locations"] == [SourceLocation("history.xlsx", "БЛУ", "C3").to_dict()]


@pytest.mark.parametrize(
    ("boundary", "fund_identity"),
    (
        (WellEventKind.PVLG, "22"),
        (WellEventKind.PNLG, "22"),
        (WellEventKind.ZBS, "22_ЗБС"),
    ),
)
def test_zero_gdi_current_lifecycle_uses_launch_and_independent_sources(
    boundary: WellEventKind,
    fund_identity: str,
) -> None:
    fund_well = replace(
        _fund_identity("Береговое", raw_well=fund_identity),
        object_plast_hint="ПК2",
    )
    initial_history = _history_stage(PartialDate(2020, 1, 1, DatePrecision.DAY))
    pvlg = replace(
        initial_history.stages[0],
        target_well_id="22_ЗБС" if boundary is WellEventKind.ZBS else "22",
        plast="ПК2",
        event_kind=boundary,
        started_at=PartialDate(2023, 6, 1, DatePrecision.DAY),
        stage_sequence=1,
        source_location=SourceLocation("history.xlsx", "БЛУ", "O3"),
    )
    history = replace(initial_history, stages=(initial_history.stages[0], pvlg))
    old_gdi = _gdi_identity(
        "Береговое",
        raw_well="22",
        raw_plast="ПК1",
        when=datetime(2022, 5, 1),
    )
    lha_records = tuple(
        LhaRecord(
            raw_field_name="Береговое",
            normalized_field=normalize_field_name("Береговое"),
            raw_well_name="22",
            base_well_id="22",
            target_well_id="22",
            raw_plast="ПК2",
            normalized_plast="ПК2",
            measured_at=when,
            cl_value=chlorine,
            vgf_value=vgf,
            source_row=index,
            source_file="lha.xlsm",
            source_sheet="БД Сибнефтегаз",
            date_cell=f"D{index}",
            cl_cell=f"E{index}",
            vgf_cell=f"F{index}",
        )
        for index, (when, chlorine, vgf) in enumerate(
            (
                (datetime(2024, 6, 1), 2000.0, 30.0),
                (datetime(2025, 6, 1), 4000.0, 40.0),
            ),
            start=2,
        )
    )
    status = ResearchStatusRecord(
        raw_well_name="22",
        base_well_id="22",
        target_well_id="22",
        raw_plast="ПК2",
        normalized_plast="ПК2",
        research_type="ИД",
        study_date=PartialDate(2026, 9, None, DatePrecision.MONTH),
        delta_raw=0,
        delta_value=0.0,
        delta_formula_without_cache=False,
        source_row=12,
        source_file="status.xlsx",
        source_sheet="АР_таблица_БЛУ",
        well_cell="A12",
        plast_cell="B12",
        research_type_cell="C12",
        date_cell="D12",
        delta_cell="J12",
    )
    daily = DailyTelemetryRow(
        raw_field_name="Береговое",
        raw_well_name="22",
        base_well_id="22",
        target_well_id="22",
        source_row=10,
        daily_values=(0.0, 1.0, 2.0),
        source_file="daily.xlsm",
        source_sheet="07.2026",
        well_cell="A10",
        daily_cells=("B10", "C10", "D10"),
    )
    report = LoadReport("now", "0.1", "3.14", {}, target_field="Береговое")
    calculation = date(2026, 10, 1)

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex((old_gdi,)),
        LhaIndex(lha_records),
        report,
        (history,),
        calculation,
        (status,),
        daily_rows=(daily,),
    )

    assert report.no_gdi == 1
    assert report.ambiguous == 0
    assert rows[0].well == ("22_ЗБС" if boundary is WellEventKind.ZBS else "22")
    assert rows[0].plast == "ПК2"
    assert rows[0].launch_date == date(2023, 6, 1)
    assert rows[0].gdi_count == 0
    assert rows[0].insufficient_gdi == "Да"
    assert rows[0].duration_without_gdi == (calculation - date(2023, 6, 1)).days / 365
    assert rows[0].duration_without_id == rows[0].duration_without_gdi
    assert rows[0].duration_without_kvd == rows[0].duration_without_gdi
    assert rows[0].specific_gdi_count is None
    assert rows[0].lnd is None
    assert rows[0].downhole_sensors is None
    assert rows[0].productivity_decline is None
    assert rows[0].cl_current == 4000.0
    assert rows[0].cl_previous == 2000.0
    assert rows[0].chlorine_growth == "Да"
    assert rows[0].vgf_current == 40.0
    assert rows[0].vgf_previous == 30.0
    assert rows[0].gdm_problems == "Нет"
    assert rows[0].debit == 1.5
    debit_provenance = next(item for item in report.field_provenance if item["field"] == "Дебит")
    assert debit_provenance["details"]["aggregation"] == "arithmetic_mean"
    assert debit_provenance["details"]["valid_working_days"] == 2

    missing_report = LoadReport("now", "0.1", "3.14", {}, target_field="Береговое")
    missing_rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex((old_gdi,)),
        LhaIndex(lha_records),
        missing_report,
        (history,),
        calculation,
        (status,),
        daily_rows=(),
    )
    assert missing_rows[0].debit is None
    assert missing_report.debit_blank == 1
    assert any(issue.code == "DEBIT_SOURCE_ROW_MISSING" for issue in missing_report.issues)


@pytest.mark.parametrize(
    ("kind", "source_identity"),
    (
        (WellEventKind.PVLG, "54_ПВЛГ"),
        (WellEventKind.PNLG, "54_ПНЛГ"),
        (WellEventKind.PVLG, "54"),
    ),
)
def test_pvlg_and_pnlg_target_identity_uses_physical_root(
    kind: WellEventKind, source_identity: str
) -> None:
    normalized = normalize_well_id(source_identity)
    fund_well = replace(
        _fund_identity("Береговое", raw_well=source_identity, base_well_id="54"),
        target_well_id=normalized.target_well_id,
    )
    record = _gdi_identity(
        "Береговое", raw_well=source_identity, base_well_id="54", raw_plast="ПК2"
    )
    stage = WellStage(
        field_name="Береговое",
        physical_root="54",
        source_display_well="054",
        target_well_id="54",
        plast="ПК2",
        event_kind=kind,
        started_at=PartialDate(2023, 6, 1, DatePrecision.DAY),
        stage_sequence=1,
        source_location=SourceLocation("history.xlsx", "БЛУ", "I4"),
        raw_block=(),
    )

    assert _effective_target_identity(fund_well, record, stage) == "54"
    assert _source_lookup_identity(fund_well, record, stage) == (
        source_identity if source_identity != "54" else "54"
    )


def test_zbs_target_suffix_and_gs_mzs_identities_are_unchanged() -> None:
    fund_well = _fund_identity("Береговое", raw_well="54", base_well_id="54")
    zbs = WellStage(
        field_name="Береговое",
        physical_root="54",
        source_display_well="054",
        target_well_id="54_ЗБС2",
        plast="ПК2",
        event_kind=WellEventKind.ZBS,
        started_at=PartialDate(2023, 6, 1, DatePrecision.DAY),
        stage_sequence=2,
        source_location=SourceLocation("history.xlsx", "БЛУ", "I4"),
        raw_block=(),
    )
    assert _effective_target_identity(fund_well, None, zbs) == "54_ЗБС2"

    for identity in ("54_ГС", "54_МЗС"):
        normalized = normalize_well_id(identity)
        fund_variant = replace(
            _fund_identity("Береговое", raw_well=identity, base_well_id="54"),
            target_well_id=normalized.target_well_id,
        )
        record = _gdi_identity("Береговое", raw_well=identity, base_well_id="54")
        assert _effective_target_identity(fund_variant, record, None) == identity


def test_pvlg_without_gdi_uses_root_for_target_and_suffix_for_lookup() -> None:
    fund_well = replace(
        _fund_identity("Береговое", raw_well="54_ПВЛГ", base_well_id="54"),
        target_well_id="54_ПВЛГ",
        object_plast_hint="ПК2",
    )
    history = _history_stage(PartialDate(2023, 6, 1, DatePrecision.DAY), kind=WellEventKind.PVLG)
    stage = replace(
        history.stages[0],
        physical_root="54",
        source_display_well="054",
        target_well_id="54",
        plast="ПК2",
    )
    history = replace(history, physical_root="54", source_display_well="054", stages=(stage,))
    report = LoadReport("now", "0.1", "3.14", {}, target_field="Береговое")

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex(()),
        LhaIndex(()),
        report,
        (history,),
    )

    assert rows[0].well == "54"
    assert _source_lookup_identity(fund_well, None, stage) == "54_ПВЛГ"


def test_no_gdi_with_month_launch_uses_first_day_and_duration() -> None:
    fund_well = _fund_identity("Береговое")
    report = LoadReport("now", "0.1", "3.14", {}, target_field="Береговое")

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex(()),
        LhaIndex(()),
        report,
        (_history_stage(PartialDate(2020, 7, None, DatePrecision.MONTH)),),
        date(2026, 10, 1),
    )

    assert rows[0].launch_date == date(2020, 7, 1)
    assert rows[0].duration_without_gdi == (date(2026, 10, 1) - date(2020, 7, 1)).days / 365


@pytest.mark.parametrize("boundary", [WellEventKind.PVLG, WellEventKind.PNLG])
def test_pvlg_and_pnlg_start_new_history_without_changing_well_number(
    boundary: WellEventKind,
) -> None:
    fund_well = replace(_fund_identity("Береговое"), object_plast_hint="ПК2")
    initial = _history_stage(PartialDate(2020, 1, 1, DatePrecision.DAY))
    event_stage = replace(
        initial.stages[0],
        target_well_id="22",
        plast="ПК2",
        event_kind=boundary,
        started_at=PartialDate(2023, 6, None, DatePrecision.MONTH),
        stage_sequence=1,
        source_location=SourceLocation("history.xlsx", "БЛУ", "O3"),
    )
    history = replace(initial, stages=(initial.stages[0], event_stage))
    record = _gdi_identity(
        "Береговое",
        raw_plast="ПК2",
        when=datetime(2023, 6, 15),
    )
    report = LoadReport("now", "0.1", "3.14", {}, target_field="Береговое")

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex((record,)),
        LhaIndex(()),
        report,
        (history,),
        date(2026, 10, 1),
    )

    assert rows[0].well == "22"
    assert rows[0].plast == "ПК2"
    assert rows[0].launch_date == date(2023, 6, 1)


def test_gdm_status_row_fills_problem_flag_from_latest_valid_delta() -> None:
    fund_well = _fund_identity("Береговое")
    gdi_record = replace(_gdi_identity("Береговое", when=datetime(2025, 1, 1)), source_row=200)
    initial_history = _history_stage(PartialDate(2020, 1, 1, DatePrecision.DAY))
    zbs_stage = replace(
        initial_history.stages[0],
        target_well_id=None,
        event_kind=WellEventKind.ZBS,
        started_at=PartialDate(2023, 6, 1, DatePrecision.DAY),
        stage_sequence=1,
        source_location=SourceLocation("history.xlsx", "БЛУ", "I3"),
    )
    history = replace(initial_history, stages=(initial_history.stages[0], zbs_stage))
    status_record = ResearchStatusRecord(
        raw_well_name="22",
        base_well_id="22",
        target_well_id="22",
        raw_plast="ПК-1",
        normalized_plast="ПК1",
        research_type="ИД",
        study_date=PartialDate(2025, 1, None, DatePrecision.MONTH),
        delta_raw=6.0,
        delta_value=6.0,
        delta_formula_without_cache=False,
        source_row=12,
        source_file="status.xlsx",
        source_sheet="АР_таблица_БЛУ",
        well_cell="A12",
        plast_cell="B12",
        research_type_cell="C12",
        date_cell="D12",
        delta_cell="J12",
    )
    report = LoadReport("now", "0.1", "3.14", {}, target_field="Береговое")

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex((gdi_record,)),
        LhaIndex(()),
        report,
        (history,),
        date(2026, 10, 1),
        (status_record,),
    )

    assert rows[0].gdm_problems == "Да"
    assert rows[0].well == "22_ЗБС"
    assert report.gdm_rows_per_target == {"22_ЗБС": 1}
    assert report.gdm_unique_candidate_identities == 1
    assert report.gdm_multiple_candidate_identities == 0
    provenance = next(item for item in report.field_provenance if item["field"] == "Проблемы ГДМ")
    assert (
        SourceLocation("status.xlsx", "АР_таблица_БЛУ", "J12").to_dict() in provenance["locations"]
    )


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
        target_field="Береговое",
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
    report = LoadReport("now", "0.1", "3.14", {}, target_field="Береговое")

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


def test_id_kvd_counts_once_and_updates_both_duration_groups() -> None:
    fund_well = _fund_identity("Береговое")
    record = replace(
        _gdi_identity("Береговое", when=datetime(2025, 3, 1)),
        gdi_kind=GdiKind.ID_KVD,
        productivity_a_value=1.25,
        productivity_a_cell="AA100",
        source_row=100,
    )
    report = LoadReport("now", "0.1", "3.14", {}, target_field="Береговое")
    operation_date = date(2026, 10, 1)

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex((record,)),
        LhaIndex(()),
        report,
        (_history_stage(PartialDate(2020, 1, 1, DatePrecision.DAY)),),
        operation_date,
    )

    assert rows[0].gdi_count == 1
    assert rows[0].insufficient_gdi == "Да"
    assert rows[0].duration_without_id == (operation_date - date(2025, 3, 1)).days / 365
    assert rows[0].duration_without_kvd == rows[0].duration_without_id
    assert report.duration_without_id_filled == 1
    assert report.duration_without_kvd_filled == 1


def test_duration_without_missing_gdi_class_stays_blank_with_diagnostic() -> None:
    fund_well = _fund_identity("Береговое")
    record = replace(
        _gdi_identity("Береговое", when=datetime(2025, 3, 1)),
        gdi_kind=GdiKind.KVD,
    )
    report = LoadReport("now", "0.1", "3.14", {}, target_field="Береговое")
    calculation = date(2026, 10, 1)

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex((record,)),
        LhaIndex(()),
        report,
        (_history_stage(PartialDate(2020, 1, 1, DatePrecision.DAY)),),
        calculation,
    )

    assert rows[0].duration_without_id == (calculation - date(2020, 1, 1)).days / 365
    assert rows[0].duration_without_kvd == (calculation - date(2025, 3, 1)).days / 365
    assert any(issue.code == "NO_ID_HISTORY_USING_LAUNCH_DATE" for issue in report.issues)


def test_productivity_uses_last_two_numeric_coefficients_and_records_provenance() -> None:
    fund_well = _fund_identity("Береговое")
    previous = replace(
        _gdi_identity("Береговое", when=datetime(2025, 1, 1), row=100),
        productivity_a_value=0.8,
        productivity_a_cell="AA100",
        source_row=100,
    )
    current = replace(
        _gdi_identity("Береговое", when=datetime(2025, 2, 1), row=101),
        productivity_a_value=0.9,
        productivity_a_cell="AA101",
        source_row=101,
    )
    report = LoadReport("now", "0.1", "3.14", {}, target_field="Береговое")

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex((previous, current)),
        LhaIndex(()),
        report,
        (_history_stage(PartialDate(2020, 1, 1, DatePrecision.DAY)),),
        date(2026, 10, 1),
    )

    assert rows[0].productivity_decline == "Да"
    provenance = next(
        item for item in report.field_provenance if item["field"] == "Снижение продуктивности"
    )
    assert [location["cell"] for location in provenance["locations"]] == [
        "E100",
        "AA100",
        "E101",
        "AA101",
    ]


def test_productivity_ignores_newer_non_gdi_a_and_injects_minimum_increase() -> None:
    fund_well = _fund_identity("Береговое")
    previous = replace(
        _gdi_identity("Береговое", when=datetime(2025, 1, 1), row=100),
        productivity_a_value=0.8,
        productivity_a_cell="AA100",
        source_row=100,
    )
    current = replace(
        _gdi_identity("Береговое", when=datetime(2025, 2, 1), row=101),
        productivity_a_value=0.9,
        productivity_a_cell="AA101",
        source_row=101,
    )
    non_gdi = replace(
        _gdi_identity("Береговое", when=datetime(2025, 3, 1), row=102),
        gdi_kind=GdiKind.EXCLUDED,
        productivity_a_value=100.0,
        productivity_a_cell="AA102",
        source_row=102,
    )
    report = LoadReport("now", "0.1", "3.14", {}, target_field="Береговое")

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex((previous, current, non_gdi)),
        LhaIndex(()),
        report,
        (_history_stage(PartialDate(2020, 1, 1, DatePrecision.DAY)),),
        date(2026, 10, 1),
        criteria=CriteriaConfig(productivity_min_increase=0.11),
    )

    assert rows[0].productivity_decline == "Нет"
    provenance = next(
        item for item in report.field_provenance if item["field"] == "Снижение продуктивности"
    )
    assert "AA102" not in {location["cell"] for location in provenance["locations"]}


@pytest.mark.parametrize(
    ("current", "previous", "expected"),
    [
        (3001.0, 2000.0, "Да"),
        (2000.0, 0.0, "Нет"),
        (3000.0, 2000.0, "Нет"),
        (1500.0, 2600.0, "Нет"),
        (3001.0, None, None),
    ],
)
def test_chlorine_growth_is_strict_and_requires_two_values(
    current: float, previous: float | None, expected: str | None
) -> None:
    fund_well = _fund_identity("Береговое")
    gdi_record = _gdi_identity("Береговое")
    lha_records: list[LhaRecord] = []
    if previous is not None:
        lha_records.append(
            LhaRecord(
                raw_field_name="Береговое",
                normalized_field="береговое",
                raw_well_name="22",
                base_well_id="22",
                raw_plast="ПК1",
                normalized_plast="ПК1",
                measured_at=datetime(2024, 1, 1),
                cl_value=previous,
                vgf_value=None,
                source_row=10,
                source_file="lha.xlsm",
                source_sheet="БД Сибнефтегаз",
                cl_cell="U10",
            )
        )
    lha_records.append(
        LhaRecord(
            raw_field_name="Береговое",
            normalized_field="береговое",
            raw_well_name="22",
            base_well_id="22",
            raw_plast="ПК1",
            normalized_plast="ПК1",
            measured_at=datetime(2024, 2, 1),
            cl_value=current,
            vgf_value=None,
            source_row=11,
            source_file="lha.xlsm",
            source_sheet="БД Сибнефтегаз",
            cl_cell="U11",
        )
    )
    report = LoadReport("now", "0.1", "3.14", {}, target_field="Береговое")

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex((gdi_record,)),
        LhaIndex(lha_records),
        report,
        (_history_stage(PartialDate(2020, 1, 1, DatePrecision.DAY)),),
    )

    assert rows[0].chlorine_growth == expected
    if expected is None:
        assert any(issue.code == "CHLORINE_INSUFFICIENT_HISTORY" for issue in report.issues)
    else:
        provenance = next(item for item in report.field_provenance if item["field"] == "Рост хлора")
        assert {location["cell"] for location in provenance["locations"]} == {"U10", "U11"}


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
    report = LoadReport("now", "0.1", "3.14", {}, target_field="Береговое")

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


def test_lnd_unknown_stays_blank_and_depth_without_evidence_is_no() -> None:
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
    report = LoadReport("now", "0.1", "3.14", {}, target_field="Береговое")

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex((record,)),
        LhaIndex(()),
        report,
        (_history_stage(PartialDate(2020, 1, 1, DatePrecision.DAY)),),
    )

    assert rows[0].lnd is None
    assert rows[0].downhole_sensors == "Нет"
    assert report.lnd_unknown == 1
    assert report.downhole_no == 1
    lnd_issue = next(issue for issue in report.issues if issue.code == "LND_SOURCE_INCOMPLETE")
    assert lnd_issue.locations == (
        SourceLocation("gdi.xlsx", "ГДИС_Сибнефтегаз в целом", "AU100"),
        SourceLocation("gdi.xlsx", "ГДИС_Сибнефтегаз в целом", "AW100"),
    )
    depth_provenance = next(p for p in report.field_provenance if p["field"] == "Глубинные датчики")
    assert any(loc["cell"] == "N100" for loc in depth_provenance["locations"])


def test_month_precision_launch_is_defaulted_with_exact_provenance() -> None:
    fund_well = _fund_identity("Береговое")
    record = replace(_gdi_identity("Береговое"), date_cell="E100")
    report = LoadReport("now", "0.1", "3.14", {}, target_field="Береговое")

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex((record,)),
        LhaIndex(()),
        report,
        (_history_stage(PartialDate(2020, 7, None, DatePrecision.MONTH)),),
    )

    assert rows[0].launch_date == date(2020, 7, 1)
    assert report.launch_date_defaulted == 1
    provenance = next(item for item in report.field_provenance if item["field"] == "Дата запуска")
    assert provenance["locations"] == [SourceLocation("history.xlsx", "БЛУ", "C3").to_dict()]
    assert provenance["details"]["source_partial_date"] == {
        "year": 2020,
        "month": 7,
        "day": None,
        "precision": "month",
    }
    assert provenance["details"]["date_defaulting_rule"] == "month_to_first_day"


def test_same_month_launch_and_gdi_uses_effective_launch_date() -> None:
    fund_well = _fund_identity("Береговое")
    record = replace(
        _gdi_identity("Береговое", when=datetime(2023, 6, 15)),
        date_cell="E100",
    )
    history = _history_stage(PartialDate(2023, 6, None, DatePrecision.MONTH))
    report = LoadReport("now", "0.1", "3.14", {}, target_field="Береговое")

    rows = _build_target_rows(
        FundParseResult((fund_well,), date(2026, 8, 1), "01.08.2026"),
        GdiIndex((record,)),
        LhaIndex(()),
        report,
        (history,),
    )

    assert rows[0].launch_date == date(2023, 6, 1)
    assert rows[0].gdi_count == 1


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


@pytest.mark.parametrize("gdi_status", ["MATCHED", "NO_GDI", "AMBIGUOUS"])
def test_independent_sources_use_lifecycle_not_gdi_status(monkeypatch, gdi_status: str) -> None:  # type: ignore[no-untyped-def]
    from gdis_loader.domain.models import MatchResult, MatchStatus

    well = _fund_identity("Береговое")
    history = _history_stage(PartialDate(2020, 1, 1, DatePrecision.DAY))
    record = _gdi_identity("Береговое")
    status = MatchStatus(gdi_status)
    monkeypatch.setattr(
        service,
        "match_all",
        lambda *_args: (
            (
                MatchResult(
                    status=status,
                    fund_well=well,
                    record=record if status is MatchStatus.MATCHED else None,
                ),
            ),
            (),
        ),
    )
    daily = DailyTelemetryRow(
        raw_field_name="Береговое",
        raw_well_name="22",
        base_well_id="22",
        target_well_id="22",
        source_row=2,
        daily_values=(1.0, 3.0),
        source_file="daily.xlsm",
        source_sheet="daily",
        well_cell="A2",
        daily_cells=("B2", "C2"),
    )
    delta = ResearchStatusRecord(
        raw_well_name="22",
        base_well_id="22",
        target_well_id="22",
        raw_plast="ПК1",
        normalized_plast="ПК1",
        research_type="ИД",
        study_date=PartialDate(2026, 7, 1, DatePrecision.DAY),
        delta_raw=0,
        delta_value=0.0,
        delta_formula_without_cache=False,
        source_row=2,
        source_file="status.xlsx",
        source_sheet="АР_таблица_БЛУ",
        well_cell="A2",
        plast_cell="B2",
        research_type_cell="C2",
        date_cell="D2",
        delta_cell="J2",
    )
    report = LoadReport("now", "0.1", "3.14", {}, target_field="Береговое")
    lha = LhaRecord(
        raw_field_name="Береговое",
        normalized_field=normalize_field_name("Береговое"),
        raw_well_name="22",
        base_well_id="22",
        target_well_id="22",
        raw_plast="ПК1",
        normalized_plast="ПК1",
        measured_at=datetime(2026, 6, 1),
        cl_value=1234.0,
        vgf_value=45.0,
        source_row=2,
        source_file="lha.xlsm",
        source_sheet="lha",
        date_cell="D2",
        cl_cell="E2",
        vgf_cell="F2",
    )
    rows = _build_target_rows(
        FundParseResult((well,), date(2026, 8, 1), "fund"),
        GdiIndex((record,)),
        LhaIndex((lha,)),
        report,
        (history,),
        date(2026, 10, 3),
        (delta,),
        daily_rows=(daily,),
    )
    assert rows[0].debit == 2.0
    assert rows[0].gdm_problems == "Нет"

    assert rows[0].cl_current == 1234.0
    assert rows[0].vgf_current == 45.0
