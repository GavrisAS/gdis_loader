from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

from gdis_loader.domain.models import IssueSeverity, LhaRecord
from gdis_loader.matching.normalize import normalize_field_name, normalize_plast, normalize_well_id
from gdis_loader.readers.common import parse_number
from gdis_loader.readers.lha import LhaIndex, read_lha


def _record(
    when: datetime,
    *,
    plast: str = "ПК₁",
    cl: float | None = None,
    vgf: float | None = None,
    row: int = 2,
) -> LhaRecord:
    return LhaRecord(
        raw_field_name="Береговое",
        normalized_field=normalize_field_name("Береговое"),
        raw_well_name="11",
        base_well_id=normalize_well_id("11").base_well_id,
        raw_plast=plast,
        normalized_plast=normalize_plast(plast),
        measured_at=when,
        cl_value=cl,
        vgf_value=vgf,
        source_row=row,
    )


def test_lha_selects_two_latest_points_independently_and_preserves_zero() -> None:
    index = LhaIndex(
        [
            _record(datetime(2024, 1, 1), cl=10, vgf=0, row=2),
            _record(datetime(2025, 1, 1), cl=20, vgf=None, row=3),
            _record(datetime(2026, 1, 1), cl=30, vgf=4, row=4),
            _record(datetime(2026, 2, 1), plast="ПК-19-2", cl=999, vgf=999, row=5),
        ]
    )

    result = index.select(
        base_well_id="11",
        normalized_field="береговое",
        normalized_plast="ПК1",
    )

    assert result.cl_current == 30
    assert result.cl_previous == 20
    assert result.vgf_current == 4
    assert result.vgf_previous == 0


def test_lha_single_valid_point_leaves_previous_empty() -> None:
    index = LhaIndex([_record(datetime(2026, 1, 1), cl=0, vgf=None)])

    result = index.select(
        base_well_id="11",
        normalized_field="береговое",
        normalized_plast="ПК1",
    )

    assert result.cl_current == 0
    assert result.cl_previous is None


def test_lha_errors_and_non_numeric_values_are_missing() -> None:
    assert parse_number("#DIV/0!") is None
    assert parse_number("#REF!") is None
    assert parse_number("") is None
    assert parse_number("-") is None
    assert parse_number(0) == 0


def test_lha_duplicate_timestamp_equal_values_is_one_point() -> None:
    latest = datetime(2026, 1, 2)
    index = LhaIndex(
        [
            _record(latest, cl=10, row=2),
            _record(latest, cl=10.0, row=3),
            _record(datetime(2026, 1, 1), cl=5, row=4),
        ]
    )

    result = index.select(
        base_well_id="11",
        normalized_field="береговое",
        normalized_plast="ПК1",
    )

    assert result.cl_current == 10
    assert result.cl_previous == 5
    assert result.issues == ()


def test_lha_latest_duplicate_timestamp_conflict_clears_both_values() -> None:
    latest = datetime(2026, 1, 2)
    index = LhaIndex(
        [
            _record(latest, cl=10, row=2),
            _record(latest, cl=11, row=3),
            _record(datetime(2026, 1, 1), cl=5, row=4),
        ]
    )

    result = index.select(
        base_well_id="11",
        normalized_field="береговое",
        normalized_plast="ПК1",
    )

    assert result.cl_current is None
    assert result.cl_previous is None
    assert [issue.code for issue in result.issues] == ["LHA_DUPLICATE_TIMESTAMP_CONFLICT"]
    assert "2 различных значения" in result.issues[0].message
    assert "роль current" in result.issues[0].message
    assert "10, 11" in result.issues[0].message


def test_lha_previous_duplicate_timestamp_conflict_does_not_fall_back() -> None:
    index = LhaIndex(
        [
            _record(datetime(2026, 1, 3), cl=20, row=2),
            _record(datetime(2026, 1, 2), cl=10, row=3),
            _record(datetime(2026, 1, 2), cl=11, row=4),
            _record(datetime(2026, 1, 1), cl=5, row=5),
        ]
    )

    result = index.select(
        base_well_id="11",
        normalized_field="береговое",
        normalized_plast="ПК1",
    )

    assert result.cl_current == 20
    assert result.cl_previous is None
    assert len(result.issues) == 1
    assert "роль previous" in result.issues[0].message


def test_lha_conflict_only_on_older_timestamp_is_not_reported() -> None:
    index = LhaIndex(
        [
            _record(datetime(2026, 1, 3), cl=30, row=2),
            _record(datetime(2026, 1, 2), cl=20, row=3),
            _record(datetime(2026, 1, 1), cl=10, row=4),
            _record(datetime(2026, 1, 1), cl=11, row=5),
        ]
    )

    result = index.select(
        base_well_id="11",
        normalized_field="береговое",
        normalized_plast="ПК1",
    )

    assert result.cl_current == 30
    assert result.cl_previous == 20
    assert result.issues == ()


def test_lha_latest_and_previous_conflicts_report_only_latest() -> None:
    index = LhaIndex(
        [
            _record(datetime(2026, 1, 3), cl=30, row=2),
            _record(datetime(2026, 1, 3), cl=31, row=3),
            _record(datetime(2026, 1, 2), cl=20, row=4),
            _record(datetime(2026, 1, 2), cl=21, row=5),
            _record(datetime(2026, 1, 1), cl=10, row=6),
            _record(datetime(2026, 1, 1), cl=11, row=7),
        ]
    )

    result = index.select(
        base_well_id="11",
        normalized_field="береговое",
        normalized_plast="ПК1",
    )

    assert result.cl_current is None
    assert result.cl_previous is None
    assert len(result.issues) == 1
    assert "роль current" in result.issues[0].message


def test_lha_reader_aggregates_expected_missing_values_and_notes(tmp_path: Path) -> None:
    path = tmp_path / "lha.xlsm"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "БД Сибнефтегаз"
    worksheet.append(
        [
            "Месторождение",
            "Номер скважины",
            "Пласт",
            "Дата и время исследования",
            "Данные ЛХА, CL-, мг/дм3",
            "ВГФ, г/м3",
        ]
    )
    worksheet.append(["Береговое", 11, "ПК-1", datetime(2026, 1, 1), "#DIV/0!", "-"])
    worksheet.append(["Береговое", 11, "ПК-1", datetime(2026, 1, 2), "Проба потеряна", ""])
    workbook.save(path)

    records, issues = read_lha(path)

    assert records[0].cl_value is None
    assert records[0].vgf_value is None
    assert all(issue.severity is not IssueSeverity.WARNING for issue in issues)
    assert any(issue.code == "LHA_MISSING_VALUE_SUMMARY" for issue in issues)
    assert any(
        issue.code == "LHA_INVALID_VALUE" and "Проба потеряна" in issue.message for issue in issues
    )


def test_lha_ignores_row_with_only_non_identity_value(tmp_path: Path) -> None:
    path = tmp_path / "lha.xlsm"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "БД Сибнефтегаз"
    worksheet.append(
        [
            "Месторождение",
            "Номер скважины",
            "Пласт",
            "Дата и время исследования",
            "Данные ЛХА, CL-, мг/дм3",
            "ВГФ, г/м3",
        ]
    )
    worksheet.append([None, None, None, None, 42, None])
    workbook.save(path)

    records, issues = read_lha(path)

    assert records == ()
    assert not any(issue.code.startswith("LHA_INVALID_") for issue in issues)


def test_lha_partially_filled_identity_row_keeps_diagnostics(tmp_path: Path) -> None:
    path = tmp_path / "lha.xlsm"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "БД Сибнефтегаз"
    worksheet.append(
        [
            "Месторождение",
            "Номер скважины",
            "Пласт",
            "Дата и время исследования",
            "Данные ЛХА, CL-, мг/дм3",
            "ВГФ, г/м3",
        ]
    )
    worksheet.append(["Береговое", 11, None, None, 42, None])
    workbook.save(path)

    records, issues = read_lha(path)
    codes = {issue.code for issue in issues}

    assert len(records) == 1
    assert {"LHA_INVALID_DATE", "LHA_INVALID_PLAST"} <= codes


def test_lha_metrics_have_independent_timestamp_conflicts() -> None:
    latest = datetime(2026, 1, 3)
    index = LhaIndex(
        [
            _record(latest, cl=10, vgf=100, row=2),
            _record(latest, cl=11, vgf=100, row=3),
            _record(datetime(2026, 1, 2), cl=5, vgf=50, row=4),
            _record(datetime(2026, 1, 1), vgf=40, row=5),
        ]
    )

    result = index.select(
        base_well_id="11",
        normalized_field="береговое",
        normalized_plast="ПК1",
    )

    assert result.cl_current is None
    assert result.cl_previous is None
    assert result.vgf_current == 100
    assert result.vgf_previous == 50
    assert len(result.issues) == 1


def test_lha_three_values_at_one_timestamp_are_a_conflict() -> None:
    latest = datetime(2026, 1, 3)
    index = LhaIndex(
        [
            _record(latest, cl=1, row=2),
            _record(latest, cl=2, row=3),
            _record(latest, cl=3, row=4),
        ]
    )

    result = index.select(
        base_well_id="11",
        normalized_field="береговое",
        normalized_plast="ПК1",
    )

    assert result.cl_current is None
    assert result.cl_previous is None
    assert "3 различных значения" in result.issues[0].message
