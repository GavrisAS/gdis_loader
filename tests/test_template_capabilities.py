from pathlib import Path
from zipfile import ZipFile

import pytest

from gdis_loader.excel.template_capabilities import detect_template_capabilities

ROOT = Path(__file__).parents[1] / "templates/calculator"


@pytest.mark.parametrize(
    ("version", "rows", "warning"),
    [
        (1, 100, False),
        (1, 101, True),
        (2, 100, False),
        (2, 101, False),
        (2, 1000, False),
        (2, 1001, True),
    ],
)
def test_capacity_boundaries(version: int, rows: int, warning: bool) -> None:
    path = ROOT / (
        "GDIS_Rating_Calculator_STRUCTURAL_v2.xlsx"
        if version == 2
        else "archive/GDIS_Rating_Calculator_v0.19_pre_structural.xlsx"
    )
    capabilities = detect_template_capabilities(path)
    assert capabilities.schema_version == version
    assert capabilities.calculation_capacity == (1000 if version == 2 else 100)
    assert capabilities.supports_missing_exclusion == (version == 2)
    assert capabilities.exceeds_capacity(rows) is warning


def test_unknown_capacity(tmp_path: Path) -> None:
    path = tmp_path / "unknown.xlsx"
    with ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook/>")
    assert detect_template_capabilities(path).calculation_capacity is None


def test_fixed_settings() -> None:
    from openpyxl import load_workbook

    workbook = load_workbook(ROOT / "GDIS_Rating_Calculator_STRUCTURAL_v2.xlsx")
    try:
        settings = workbook["Настройки"]
        assert settings.protection.sheet
        for cell in ["B12", *[f"L{row}" for row in range(21, 51)]]:
            assert settings[cell].value == "Не учитывать" or cell in {"L28", "L34"}
            assert settings[cell].protection.locked
            assert all(
                cell not in validation for validation in settings.data_validations.dataValidation
            )
        assert not settings["D21"].protection.locked
        assert settings.row_dimensions[28].hidden
        assert settings.row_dimensions[34].hidden
    finally:
        workbook.close()


@pytest.mark.parametrize(
    ("version", "rows", "warning"),
    [
        (1, 100, False),
        (1, 101, True),
        (2, 100, False),
        (2, 101, False),
        (2, 1000, False),
        (2, 1001, True),
    ],
)
def test_writer_capacity_warning(version: int, rows: int, warning: bool, tmp_path: Path) -> None:
    from gdis_loader.domain.models import TargetRow
    from gdis_loader.excel.writer import write_target_rows

    source = ROOT / (
        "GDIS_Rating_Calculator_STRUCTURAL_v2.xlsx"
        if version == 2
        else "archive/GDIS_Rating_Calculator_v0.19_pre_structural.xlsx"
    )
    result = write_target_rows(
        source, tmp_path / "output.xlsx", (TargetRow(well=str(i)) for i in range(rows))
    )
    assert ("DATA_ROWS_EXCEED_CALCULATOR_FORMULA_CAPACITY" in result.warnings) is warning
    assert set(result.changed_entries) == {"xl/worksheets/sheet3.xml", "xl/tables/table2.xml"}


def test_diagnostic_template_aware() -> None:
    from gdis_loader.domain.models import LoadReport
    from gdis_loader.service import _missing_policy_diagnostic

    report = LoadReport("now", "0.20", "3.14", {})
    report.input_paths["calculator"] = str(ROOT / "GDIS_Rating_Calculator_STRUCTURAL_v2.xlsx")
    assert _missing_policy_diagnostic(report) == ""
    report.input_paths["calculator"] = str(
        ROOT / "archive/GDIS_Rating_Calculator_v0.19_pre_structural.xlsx"
    )
    assert "пока не обеспечивают" in _missing_policy_diagnostic(report)
