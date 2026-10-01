from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zipfile import ZipFile

import pytest

from gdis_loader.domain.models import IssueSeverity, SourcePaths
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
    DATA_ROOT / "Ответы на вопросы" / "2026-09-30_ответы_v1" / "База по скважинам.xlsx",
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
        well_history=REAL_FILES[5],
        output=output,
    )

    result = run_update(paths, tmp_path / "loader.log", calculation_date=date(2026, 10, 1))

    assert result.report.calculation_date == date(2026, 10, 1)
    assert result.report.fund_total_source == 129
    assert result.report.fund_total == 129
    assert result.report.target_field == "Береговое"
    assert result.report.target_field_fund_total == result.report.rows_prepared
    assert result.report.rows_written == result.report.rows_prepared
    assert (
        result.report.rating_eligible + result.report.rating_not_eligible
        == result.report.rows_prepared
    )
    assert result.report.well_history_records > 0
    assert result.report.well_history_gtm_events > 0
    assert result.report.gdi_kind_counts
    assert not any(issue.severity is IssueSeverity.ERROR for issue in result.report.issues)
    assert not any(
        issue.code == "LHA_DUPLICATE_TIMESTAMP_CONFLICT" for issue in result.report.issues
    )
    assert not any(issue.code == "UNCONFIRMED_WELL_VARIANT_MZS" for issue in result.report.issues)
    assert all(
        issue.severity is IssueSeverity.INFO and issue.locations
        for issue in result.report.issues
        if issue.code == "LHA_DUPLICATE_TIMESTAMP_RESOLVED_MAX"
    )
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
    table_end = 6 + result.report.rows_written
    assert f'ref="A6:Z{table_end}"' in table_xml
    assert f'sqref="A7:A{table_end}"' in sheet_xml
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
def test_real_lha_duplicate_timestamps_choose_max_independent_of_source_row_order() -> None:
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
        target_well_id = normalize_well_id(raw_well).target_well_id
        selection = index.select(
            base_well_id=base_well_id or "",
            normalized_field=normalized_field,
            normalized_plast=normalized_plast or "",
            cutoff=datetime.max,
            target_well_id=target_well_id,
        )
        reversed_selection = LhaIndex(reversed(records)).select(
            base_well_id=base_well_id or "",
            normalized_field=normalized_field,
            normalized_plast=normalized_plast or "",
            cutoff=datetime.max,
            target_well_id=target_well_id,
        )
        assert selection.values == reversed_selection.values
        assert not any(
            issue.code == "LHA_DUPLICATE_TIMESTAMP_CONFLICT" for issue in selection.issues
        )
        resolved = [
            issue
            for issue in selection.issues
            if issue.code == "LHA_DUPLICATE_TIMESTAMP_RESOLVED_MAX" and timestamp in issue.message
        ]
        if resolved:
            assert all(
                issue.severity is IssueSeverity.INFO and issue.locations for issue in resolved
            )
