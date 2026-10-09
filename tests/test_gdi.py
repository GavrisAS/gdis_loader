from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

from gdis_loader.readers.gdi import read_gdi
from gdis_loader.transforms.rules import downhole_condition

GDI_HEADERS = [
    "Месторождение",
    "Скважина",
    "Пласт",
    "Вид исследования",
    "Дата",
    "Выход на РФП (да/нет)",
    "Достоверность согласно ЛНД",
    "Дата проведения ГТМ",
    "Глубина записи, м",
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


def test_gdi_preserves_raw_type_classifies_unknown_and_keeps_depth_zero(tmp_path: Path) -> None:
    path = tmp_path / "gdi.xlsx"
    _write_gdi(
        path,
        [
            ["Береговое", 11, "ПК1", "КВУ", datetime(2026, 1, 1), "да", "Высокая", None, 0],
            ["Береговое", 12, "ПК1", "ИД", datetime(2026, 1, 2), "нет", None, None, "ошибка"],
        ],
    )

    records, issues = read_gdi(path)

    assert records[0].research_type == "КВУ"
    assert downhole_condition(records[0].depth_raw_value, 0.0) is False
    assert records[0].depth_raw_value == 0
    assert records[1].research_type == "ИД"
    assert downhole_condition(records[1].depth_raw_value, 0.0) is None
    unknown = next(issue for issue in issues if issue.code == "GDI_KIND_UNKNOWN")
    assert unknown.locations[0].cell == "D2"


def test_invalid_depth_has_exact_source_location(tmp_path: Path) -> None:
    path = tmp_path / "ГДИ источник.xlsx"
    _write_gdi(
        path,
        [
            [
                "Береговое",
                11,
                "ПК17-1",
                "КСД",
                datetime(2026, 1, 1),
                "да",
                "средняя",
                None,
                "не число",
            ]
        ],
    )
    records, issues = read_gdi(path)
    assert records[0].normalized_plast == "ПК17"
    assert records[0].depth_value is None
    issue = next(i for i in issues if i.code == "GDI_DEPTH_INVALID")
    assert issue.locations[0].file == str(path.resolve())
    assert issue.locations[0].sheet == "ГДИС_Сибнефтегаз в целом"
    assert issue.locations[0].cell == "I2"
