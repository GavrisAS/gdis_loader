from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from gdis_loader.readers.gdi import read_gdi

GDI_HEADERS = [
    "Месторождение",
    "Скважина",
    "Пласт",
    "Вид исследования",
    "Дата",
    "Выход на РФП (да/нет)",
    "Достоверность согласно ЛНД",
    "Дата проведения ГТМ",
]


def _write_gdi(path: Path, rows: list[list[object]]) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "ГДИС_Сибнефтегаз в целом"
    worksheet.append(GDI_HEADERS)
    for row in rows:
        worksheet.append(row)
    workbook.save(path)


def test_gdi_ignores_row_with_only_non_identity_value(tmp_path: Path) -> None:
    path = tmp_path / "gdi.xlsx"
    _write_gdi(path, [[None, None, None, 123, None, None, None, None]])

    records, issues = read_gdi(path)

    assert records == ()
    assert not any(issue.code.startswith("GDI_INVALID_") for issue in issues)
    assert not any(issue.code == "GDI_MISSING_DATE" for issue in issues)


def test_gdi_partially_filled_identity_row_keeps_diagnostics(tmp_path: Path) -> None:
    path = tmp_path / "gdi.xlsx"
    _write_gdi(path, [["Береговое", 11, None, None, None, None, None, None]])

    records, issues = read_gdi(path)
    codes = {issue.code for issue in issues}

    assert len(records) == 1
    assert {"GDI_INVALID_PLAST", "GDI_MISSING_DATE"} <= codes
