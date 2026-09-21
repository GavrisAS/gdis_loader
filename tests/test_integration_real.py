from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

import pytest

from gdis_loader.domain.models import SourcePaths
from gdis_loader.matching.normalize import normalize_plast, normalize_well_id
from gdis_loader.readers.lha import LhaIndex, read_lha
from gdis_loader.service import run_update

DATA_ROOT = Path(__file__).parents[1] / "data"
REAL_FILES = (
    DATA_ROOT / "GDIS_Rating_Calculator_FIXED.xlsx",
    DATA_ROOT / "Фонд 2026 на 01.08.2026.xlsx",
    DATA_ROOT / "Сводная таблица ГДИ.xlsx",
    DATA_ROOT / "База ЛХА_Итог!.xlsm",
    DATA_ROOT / "07.2026 Cуточный рапорт БГП_полный.xlsm",
)


@pytest.mark.skipif(
    not all(path.is_file() for path in REAL_FILES), reason="real data files are not present"
)
def test_real_bundle_update(tmp_path: Path) -> None:
    output = tmp_path / "GDIS_Rating_Calculator_UPDATED.xlsx"
    paths = SourcePaths(
        calculator=REAL_FILES[0],
        fund=REAL_FILES[1],
        gdi=REAL_FILES[2],
        lha=REAL_FILES[3],
        daily_report=REAL_FILES[4],
        output=output,
    )

    result = run_update(paths, tmp_path / "loader.log")

    assert result.report.fund_total == 129
    assert result.report.matched == 128
    assert result.report.no_gdi == 1
    assert result.report.ambiguous == 0
    assert result.report.rows_written == 129
    assert not any(issue.code.startswith("DAILY_") for issue in result.report.issues)
    assert not any(
        issue.code == "LHA_INVALID_VALUE" and issue.severity.value == "warning"
        for issue in result.report.issues
    )
    assert output.is_file()
    assert output.with_suffix(".load-report.json").is_file()
    with ZipFile(output) as archive:
        table_xml = archive.read("xl/tables/table2.xml").decode("utf-8")
        sheet_xml = archive.read("xl/worksheets/sheet3.xml").decode("utf-8")
    assert 'ref="A6:Z135"' in table_xml
    assert 'sqref="A7:A135"' in sheet_xml
    assert 'mc:Ignorable="x14ac"' in sheet_xml
    assert "xmlns:x14ac=" in sheet_xml

    with ZipFile(REAL_FILES[0]) as source_archive, ZipFile(output) as output_archive:
        changed_entries = {
            name
            for name in source_archive.namelist()
            if source_archive.read(name) != output_archive.read(name)
        }
    assert changed_entries == {"xl/worksheets/sheet3.xml", "xl/tables/table2.xml"}


@pytest.mark.skipif(
    not all(path.is_file() for path in REAL_FILES), reason="real data files are not present"
)
def test_real_lha_duplicate_timestamps_never_use_source_row_order() -> None:
    records, _ = read_lha(REAL_FILES[3])
    index = LhaIndex(records)
    cases = (
        ("212", "Береговое", "ПК-1", "cl_value", "2021-10-16 00:00"),
        ("11301", "Береговое", "ПК-15", "cl_value", "2022-07-20 00:00"),
        ("021", "Пырейное", "ПК-1", "cl_value", "2024-05-17 15:00"),
        ("323", "Хадырьяхинское", "ПК-1", "cl_value", "2024-03-24 05:40"),
        ("113", "Хадырьяхинское", "ПК-20-3", "cl_value", "2024-04-18 21:00"),
        ("212", "Береговое", "ПК-1", "vgf_value", "2021-10-16 00:00"),
        ("331", "Береговое", "ПК-1", "vgf_value", "2021-12-02 21:00"),
        ("323", "Хадырьяхинское", "ПК-1", "vgf_value", "2024-03-24 05:40"),
        ("113", "Хадырьяхинское", "ПК-20-3", "vgf_value", "2024-04-18 21:00"),
    )
    for raw_well, field, plast, metric, timestamp in cases:
        base_well_id = normalize_well_id(raw_well).base_well_id
        normalized_field = field.casefold()
        normalized_plast = normalize_plast(plast)
        when = datetime.fromisoformat(timestamp)
        matching = [
            record
            for record in records
            if record.base_well_id == base_well_id
            and record.normalized_field == normalized_field
            and record.normalized_plast == normalized_plast
            and record.measured_at == when
            and getattr(record, metric) is not None
        ]
        assert matching, (raw_well, field, plast, metric, timestamp)
        selection = index.select(
            base_well_id=base_well_id or "",
            normalized_field=normalized_field,
            normalized_plast=normalized_plast or "",
            cutoff=datetime.max,
        )
        metric_label = "Cl" if metric == "cl_value" else "ВГФ"
        metric_issues = [issue for issue in selection.issues if metric_label in issue.message]
        values_by_timestamp: dict[datetime, set[float]] = {}
        for record in records:
            value = getattr(record, metric)
            measured_at = record.measured_at
            if (
                record.base_well_id == base_well_id
                and record.normalized_field == normalized_field
                and record.normalized_plast == normalized_plast
                and measured_at is not None
                and value is not None
            ):
                values_by_timestamp.setdefault(measured_at, set()).add(value)
        points = sorted(values_by_timestamp.items(), reverse=True)
        expected_role = None
        if points and len(points[0][1]) > 1:
            expected_role = "current"
        elif len(points) > 1 and len(points[1][1]) > 1:
            expected_role = "previous"
        assert len(metric_issues) == (1 if expected_role else 0)
        if expected_role:
            assert f"роль {expected_role}" in metric_issues[0].message
            assert timestamp in metric_issues[0].message
        if expected_role == "current":
            assert (
                selection.cl_current is None
                if metric == "cl_value"
                else selection.vgf_current is None
            )
            assert (
                selection.cl_previous is None
                if metric == "cl_value"
                else selection.vgf_previous is None
            )
        elif expected_role == "previous":
            assert (
                selection.cl_current is not None
                if metric == "cl_value"
                else selection.vgf_current is not None
            )
            assert (
                selection.cl_previous is None
                if metric == "cl_value"
                else selection.vgf_previous is None
            )
        else:
            assert points[0][0] == when
            assert (
                selection.cl_current == next(iter(points[0][1]))
                if metric == "cl_value"
                else selection.vgf_current == next(iter(points[0][1]))
            )
            if len(points) > 1:
                assert (
                    selection.cl_previous == next(iter(points[1][1]))
                    if metric == "cl_value"
                    else selection.vgf_previous == next(iter(points[1][1]))
                )
