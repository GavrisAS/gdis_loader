from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from gdis_loader.readers.daily import read_daily_report


def test_daily_reader_keeps_valid_values_and_ignores_ref(tmp_path: Path) -> None:
    path = tmp_path / "daily.xlsm"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Добыча телеметрия"
    worksheet.append(["ГСК", "СКВ.", 1, 2, 3])
    worksheet.append([1, 11, 10, 0, "#REF!"])
    workbook.save(path)

    rows, issues = read_daily_report(path)

    assert len(rows) == 1
    assert rows[0].daily_values == (10.0, 0.0, None)
    assert any(issue.code == "DAILY_INVALID_VALUE" for issue in issues)
