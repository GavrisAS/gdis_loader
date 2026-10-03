from __future__ import annotations

import ast
import html
import json
import math
import re
from collections.abc import Mapping
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.cell_range import MultiCellRange

from gdis_loader.domain.models import TargetRow
from gdis_loader.excel.template_migration import (
    CAPACITY,
    EXPECTED_CHANGED,
    GENERAL_EDITABLE,
    SOURCE_SHA256,
    _arguments,
    _mu,
    _patch_sheet,
    migrate,
    sha256,
)
from gdis_loader.excel.writer import write_target_rows

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "templates/calculator/archive/GDIS_Rating_Calculator_v0.19_pre_structural.xlsx"
CANDIDATE = ROOT / "templates/calculator/GDIS_Rating_Calculator_STRUCTURAL_v2.xlsx"


def test_reject_unexpected_source_and_never_touch_output(tmp_path: Path) -> None:
    source = tmp_path / "input.xlsx"
    source.write_bytes(b"unknown")
    output = tmp_path / "output.xlsx"
    with pytest.raises(ValueError, match="SHA"):
        migrate(source, output)
    assert source.read_bytes() == b"unknown"
    assert not output.exists()


def test_missing_branch_is_numeric_zero_and_known_no_unchanged() -> None:
    old = (
        'IF(OR(AG20="#FIELD",AG20=""),'
        'IF($B$18="IGNORE","IGNORE","Недостаточно данных"),'
        'IF(AG20="Да",1,0.1))'
    )
    new, missing = _mu(old, "AG20")
    assert new == 'IF(OR(AG20="#FIELD",AG20=""),0,IF(AG20="Да",1,0.1))'
    assert missing == 'OR(AG20="#FIELD",AG20="")'


def test_raw_blank_guard_capacity_and_namespace_preservation() -> None:
    xml = (
        '<worksheet xmlns:x14ac="urn:unchanged"><dimension ref="A1:CO119"/>'
        '<cols></cols><sheetData><row r="20"><c r="AF20"/><c r="AG20"><f>'
        "IF(1,INDEX(Данные!$A$7:$CV$106,ROW()-19,MATCH($B$9,Данные!$A$6:$CV$6,0)),0)"
        '</f></c></row><row r="119"><c r="A119"><f>Данные!A106</f></c></row>'
        '</sheetData><conditionalFormatting sqref="B20:AE119"/></worksheet>'
    )
    patched = _patch_sheet(xml, 4)
    assert 'xmlns:x14ac="urn:unchanged"' in patched
    assert 'dimension ref="A1:DT1019"' in patched
    assert 'sqref="B20:AE1019"' in patched
    assert "IF(INDEX(" in patched
    assert ')="","",INDEX(' in patched
    assert "Данные!A1006" in patched
    assert len(ET.fromstring(patched).findall(".//row")) == 902


def _evaluate(formula: str, values: Mapping[str, object]) -> object:
    """Evaluate only the emitted lambda function subset, with lazy Excel IF."""
    function = re.search(
        r"\b(IF|OR|AND|NOT|EXP|LN|MAX|MIN|ABS|LOWER|LEFT|COUNTIF|COUNT|COUNTIFS|ISNUMBER|COUNTA|MATCH|ROW|INDEX)\(",
        formula,
    )
    while function:
        args = _arguments(formula[function.end() :])
        expression = function.group(0) + ",".join(args) + ")"
        name = function.group(1)
        if name == "IF":
            result = _evaluate(args[1] if _evaluate(args[0], values) else args[2], values)
        elif name == "ROW":
            result = values["__row"]
        elif name == "COUNTIF":
            seq = values.get(args[0], [])
            assert isinstance(seq, list)
            criterion = _evaluate(args[1], values)
            if isinstance(criterion, str) and criterion.startswith(">"):
                threshold = float(criterion[1:])
                result = sum(isinstance(x, (int, float)) and x > threshold for x in seq)
            else:
                result = sum(x == criterion for x in seq)
        else:
            evaluated = [_evaluate(arg, values) for arg in args]
            if name == "OR":
                result = any(evaluated)
            elif name == "AND":
                result = all(evaluated)
            elif name == "NOT":
                result = not evaluated[0]
            elif name == "LOWER":
                result = str(evaluated[0]).lower()
            elif name == "LEFT":
                result = str(evaluated[0])[: int(str(evaluated[1]))]
            elif name == "ABS":
                result = abs(float(str(evaluated[0])))
            elif name == "MIN":
                result = min(float(str(x)) for x in evaluated)
            elif name == "ISNUMBER":
                result = isinstance(evaluated[0], (int, float))
            elif name in ("COUNT", "COUNTA"):
                seq = evaluated[0]
                assert isinstance(seq, list)
                result = sum(
                    isinstance(x, (int, float)) if name == "COUNT" else x != "" for x in seq
                )
            elif name == "COUNTIFS":
                wells, _nonblank, scores, _blank = evaluated
                assert isinstance(wells, list) and isinstance(scores, list)
                result = sum(
                    well != "" and score == "" for well, score in zip(wells, scores, strict=True)
                )
            elif name == "MATCH":
                needle, seq, _exact = evaluated
                assert isinstance(seq, list)
                result = seq.index(needle) + 1
            elif name == "INDEX":
                seq, index = evaluated
                assert isinstance(seq, list) and isinstance(index, int)
                result = seq[index - 1]
            elif name == "EXP":
                result = math.exp(float(evaluated[0]))  # ty: ignore[invalid-argument-type]
            elif name == "LN":
                result = math.log(float(evaluated[0]))  # ty: ignore[invalid-argument-type]
            else:
                result = max(evaluated)  # ty: ignore[invalid-argument-type]
        formula = formula.replace(expression, repr(result), 1)
        function = re.search(
            r"\b(IF|OR|AND|NOT|EXP|LN|MAX|MIN|ABS|LOWER|LEFT|COUNTIF|COUNT|COUNTIFS|ISNUMBER|COUNTA|MATCH|ROW|INDEX)\(",
            formula,
        )
    # Substitute cell references outside quoted string literals.
    for key in sorted(values, key=len, reverse=True):
        formula = formula.replace(key, repr(values[key]))
    formula = re.sub(r"(?<![<>!=])=(?!=)", "==", formula).replace("<>", "!=")
    formula = re.sub(
        r"('.*?'|\".*?\"|-?\d+(?:\.\d+)?)&\"\"",
        lambda m: repr(str(ast.literal_eval(m.group(1)))),
        formula,
    )
    tree = ast.parse(formula, mode="eval")

    class Concatenation(ast.NodeTransformer):
        def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
            self.generic_visit(node)
            if isinstance(node.op, ast.BitAnd):
                return ast.copy_location(
                    ast.Constant(
                        str(ast.literal_eval(node.left)) + str(ast.literal_eval(node.right))
                    ),
                    node,
                )
            return node

    tree = Concatenation().visit(tree)
    allowed = (
        ast.Expression,
        ast.Constant,
        ast.List,
        ast.Load,
        ast.BinOp,
        ast.UnaryOp,
        ast.Compare,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.USub,
        ast.Eq,
        ast.NotEq,
        ast.Gt,
        ast.GtE,
        ast.Lt,
        ast.LtE,
    )
    assert all(isinstance(node, allowed) for node in ast.walk(tree))
    return eval(compile(tree, "<golden Excel subset>", "eval"), {"__builtins__": {}}, {})


@pytest.mark.parametrize(
    "mus",
    [
        [1, 0.1, 0.7, 1, 0.1, 1, 0.8, 0.6],  # A: all remaining active known
        [None, 0.1, 0.7, 1, 0.1, 1, 0.8, 0.6],  # B
        [None, None, 0.7, 1, None, 1, 0.8, 0.6],  # C
        [0.1, None, None, None, None, None, None, None],  # D and known Нет
        [None] * 8,  # E
        [1, None, None, None, None, None, None, None],  # G known Да
    ],
)
def test_emitted_lambda_golden(mus: list[float | None]) -> None:
    xml = (
        '<worksheet><sheetData><row r="4"><c r="H4"><f>1</f></c>'
        '<c r="J4"><f>1</f></c><c r="G4"><f>1</f></c></row>'
        '<row r="103"><c r="A103"><f>1</f>'
        "</c></row></sheetData></worksheet>"
    )
    patched = ET.fromstring(_patch_sheet(xml, 5))
    formulas = {c.get("r"): c.findtext("f") for c in patched.findall(".//c")}
    values: dict[str, object] = {"$A4": "synthetic", "Настройки!$B$14": 1e-9}
    active_slots = (1, 2, 3, 4, 5, 6, 7, 9)
    weights = (0.2, 0.14, 0.12, 0.12, 0.12, 0.1, 0.1, 0.05)
    for slot in range(1, 31):
        c = get_column_letter(slot + 1)
        values[f"Критерии!{c}$6"] = 0
        values[f"Критерии!{c}20"] = 0
        values[f"Критерии!{get_column_letter(94 + slot)}20"] = 0
    for slot, mu, weight in zip(active_slots, mus, weights, strict=True):
        c = get_column_letter(slot + 1)
        values[f"Критерии!{c}$6"] = weight
        values[f"Критерии!{c}20"] = mu if mu is not None else 0
        values[f"Критерии!{get_column_letter(94 + slot)}20"] = int(mu is not None)
    values["Настройки!$B$16"] = 0
    for slot in range(1, 31):
        values[f"Критерии!{get_column_letter(slot + 1)}$7"] = "Да"
    assert _evaluate(str(formulas["G4"]), values) == sum(mu is not None for mu in mus)
    values["H4"] = _evaluate(str(formulas["H4"]), values)
    actual = _evaluate(str(formulas["J4"]), values)
    known = [(mu, weight) for mu, weight in zip(mus, weights, strict=True) if mu is not None]
    if not known:
        assert actual == ""
    else:
        expected = math.exp(sum(w * math.log(mu) for mu, w in known) / sum(w for _, w in known))
        assert actual == pytest.approx(expected)


@pytest.mark.skipif(not SOURCE.is_file(), reason="real calculator absent")
def test_real_migration_deterministic_and_exact_diff(tmp_path: Path) -> None:
    first, second = tmp_path / "first.xlsx", tmp_path / "second.xlsx"
    assert sha256(SOURCE) == SOURCE_SHA256
    backup = ROOT / "artifacts/calculator/archive/GDIS_Rating_Calculator_v0.19_pre_structural.xlsx"
    if backup.is_file():
        assert backup.read_bytes() == SOURCE.read_bytes()
    assert set(migrate(SOURCE, first)) == EXPECTED_CHANGED
    migrate(SOURCE, second)
    assert sha256(first) == sha256(second)
    # zlib output may differ across Linux/Windows; compare exact OOXML payloads.
    with ZipFile(first) as rebuilt, ZipFile(CANDIDATE) as published:
        assert rebuilt.namelist() == published.namelist()
        for name in rebuilt.namelist():
            assert rebuilt.read(name) == published.read(name), name
    assert sha256(SOURCE) == SOURCE_SHA256
    with pytest.raises(ValueError, match="separate"):
        migrate(SOURCE, first)
    with pytest.raises(ValueError, match="SHA"):
        migrate(first, tmp_path / "third.xlsx")
    with ZipFile(SOURCE) as old, ZipFile(first) as new:
        assert set(old.namelist()) - set(new.namelist()) == {"xl/calcChain.xml"}
        for name in new.namelist():
            if name not in EXPECTED_CHANGED:
                assert old.read(name) == new.read(name)
            if name.endswith(".xml"):
                root = ET.fromstring(new.read(name))
                if name.startswith("xl/worksheets/"):
                    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
                    old_styles = {
                        c.attrib["r"]: c.get("s")
                        for c in ET.fromstring(old.read(name)).iter(namespace + "c")
                    }
                    new_styles = {c.attrib["r"]: c.get("s") for c in root.iter(namespace + "c")}
                    assert all(
                        new_styles.get(cell) == style
                        or (
                            name == "xl/worksheets/sheet2.xml"
                            and (
                                cell in GENERAL_EDITABLE
                                or re.search(r"(?:28|34)$", cell)
                                or cell == "B12"
                                or cell.startswith("L")
                            )
                        )
                        for cell, style in old_styles.items()
                    )
                for element in root.iter():
                    if "sqref" in element.attrib:
                        MultiCellRange(element.attrib["sqref"])
                assert b"#REF!" not in new.read(name)
    workbook = load_workbook(first, read_only=True)
    try:
        assert workbook["Критерии"].max_row == CAPACITY + 19
        assert workbook["Критерии"].max_column == 124
        assert "IF(INDEX(" in workbook["Критерии"]["AG20"].value
        assert workbook["Данные"].max_column == 26
    finally:
        workbook.close()


@pytest.mark.skipif(not CANDIDATE.is_file(), reason="local migrated candidate absent")
def test_migrated_runtime_scope_and_contraction(tmp_path: Path) -> None:
    for count in (0, 121, CAPACITY):
        output = tmp_path / f"{count}.xlsx"
        rows = tuple(TargetRow(well=f"synthetic-{i}") for i in range(count))
        write_target_rows(CANDIDATE, output, rows)
        with ZipFile(CANDIDATE) as before, ZipFile(output) as after:
            assert before.namelist() == after.namelist()
            changes = {n for n in before.namelist() if before.read(n) != after.read(n)}
            assert changes == {"xl/worksheets/sheet3.xml", "xl/tables/table2.xml"}
            table = ET.fromstring(after.read("xl/tables/table2.xml"))
            assert table.get("ref") == f"A6:Z{6 + count}"


def test_ranking_preserves_unknown_rows_after_numeric_scores_and_ties() -> None:
    xml = (
        '<worksheet><sheetData><row r="4"><c r="A4"><f>1</f></c></row>'
        '<row r="103"><c r="A103"><f>1</f></c></row></sheetData></worksheet>'
    )
    calc = ET.fromstring(_patch_sheet(xml, 5))
    formula = calc.find(".//c[@r='O4']/f")
    assert formula is not None
    values: dict[str, object] = {
        "$A4": "unknown",
        "K4": "",
        "$J$4:$J$1003": ["", 0.5, 0.5, 0.1, ""],
        "$A$4:A4": ["unknown"],
        "$J$4:J4": [""],
    }
    assert _evaluate(str(formula.text), values) == 4
    values["$A4"], values["K4"] = "known", 2
    assert _evaluate(str(formula.text), values) == 2
    values["$A4"] = ""
    assert _evaluate(str(formula.text), values) == ""
    rank_formula = 'IF(J4="","",COUNTIF($J$4:$J$1003,">"&J4)+COUNTIF($J$4:J4,J4))'
    scores = [0.5, 0.5, 0, -0.1, ""]
    for index, expected in enumerate((1, 2, 3, 4, "")):
        context = {"J4": scores[index], "$J$4:$J$1003": scores, "$J$4:J4": scores[: index + 1]}
        assert _evaluate(rank_formula, context) == expected
    rating_xml = (
        '<worksheet><sheetData><row r="4"><c r="A4"><f>1</f></c>'
        '<c r="B4"><f>IF($A4="","",INDEX(Расчет!$A$4:$A$103,'
        "MATCH($A4,Расчет!$K$4:$K$103,0)))</f></c></row>"
        '<row r="103"><c r="A103"><f>1</f></c></row></sheetData></worksheet>'
    )
    rating = ET.fromstring(_patch_sheet(rating_xml, 6))
    context = {
        "$M4": 1,
        "Расчет!$K$4:$K$1003": ["", 1, 2],
        "Расчет!$A$4:$A$1003": ["unknown well", "known1", "known2"],
    }
    assert _evaluate(str(rating.findtext(".//c[@r='A4']/f")), context) == ""
    assert _evaluate(str(rating.findtext(".//c[@r='B4']/f")), context) == "unknown well"


def test_normalization_does_not_penalize_number_of_known_criteria() -> None:
    # Same quality with different coverage must give the same geometric mean.
    for count in (1, 6, 10):
        mus = [0.4] * count
        weights = list(range(1, count + 1))
        value = math.exp(
            sum(w * math.log(mu) for mu, w in zip(mus, weights, strict=True)) / sum(weights)
        )
        assert value == pytest.approx(0.4)


@pytest.mark.parametrize(
    "raw,kind,expected_mu,expected_mask",
    [
        ("", "YES_NO", 0, 0),
        ("Нет", "YES_NO", 0.1, 1),
        ("Да", "YES_NO", 1, 1),
        ("", "SIGMOID_INC", 0, 0),
        (0, "SIGMOID_INC", None, 1),
        (2, "SIGMOID_INC", None, 1),
        ("not numeric", "SIGMOID_INC", 0, 0),
    ],
)
def test_workbook_mu_and_mask_golden(
    raw: object, kind: str, expected_mu: float | None, expected_mask: int
) -> None:
    fixture = json.loads(
        (ROOT / "tests/fixtures/calculator_formula_v019.txt").read_text(encoding="utf-8")
    )
    cells = "".join(
        f'<c r="{cell}"><f>{html.escape(formula, quote=False)}</f></c>'
        for cell, formula in fixture.items()
    )
    xml = (
        '<worksheet><cols></cols><sheetData><row r="20">' + cells + "</row>"
        '<row r="119"><c r="A119"><f>1</f></c></row></sheetData></worksheet>'
    )
    root = ET.fromstring(_patch_sheet(xml, 4))
    values: dict[str, object] = {
        "$A20": "synthetic",
        "$B$4": "Да",
        "$B$8": kind,
        "$B$11": 1.0863013698631276,
        "$B$12": 8.25,
        "$B$13": 0,
        "$B$14": 1,
        "$B$15": 0.1,
        "$B$16": 0,
        "$B$17": 1,
        "Настройки!$B$14": 1e-9,
        "AG20": raw,
        "BL20": "",
    }
    mu = _evaluate(str(root.findtext(".//c[@r='B20']/f")), values)
    if expected_mu is None:
        assert isinstance(raw, (int, float))
        expected_mu = max(1e-9, 1 / (1 + math.exp(-8.25 * (raw - 1.0863013698631276))))
    assert mu == pytest.approx(expected_mu)
    values["B20"] = mu
    mask = _evaluate(str(root.findtext(".//c[@r='CQ20']/f")), values)
    assert mask == expected_mask


@pytest.mark.parametrize("cell", [*sorted(GENERAL_EDITABLE), "D21", "G21", "H21", "I21", "J21"])
def test_settings_editable_ooxml(cell: str) -> None:
    _assert_settings_protection(cell, locked=False)


@pytest.mark.parametrize("cell", ["B12", "L21", "L50", "D28", "G28", "D34", "G34"])
def test_settings_fixed_ooxml(cell: str) -> None:
    _assert_settings_protection(cell, locked=True)


def _assert_settings_protection(cell: str, *, locked: bool) -> None:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(CANDIDATE) as archive:
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet2.xml"))
        sheet_protection = sheet.find("m:sheetProtection", ns)
        assert sheet_protection is not None
        assert sheet_protection.get("sheet") == "1"
        node = sheet.find(f".//m:c[@r='{cell}']", ns)
        styles = ET.fromstring(archive.read("xl/styles.xml")).find("m:cellXfs", ns)
        assert styles is not None and node is not None
        style = styles[int(node.get("s", "0"))]
        protection = style.find("m:protection", ns)
        actual = protection is None or protection.get("locked", "1") == "1"
        assert actual is locked
        for row in (28, 34):
            retired = sheet.find(f"m:sheetData/m:row[@r='{row}']", ns)
            assert retired is not None
            assert retired.get("hidden") == "1"
            for item in retired:
                p = styles[int(item.get("s", "0"))].find("m:protection", ns)
                assert p is None or p.get("locked", "1") == "1"
        # Explicit clones preserve every visual style attribute/child.
        with ZipFile(SOURCE) as before:
            old_sheet = ET.fromstring(before.read("xl/worksheets/sheet2.xml"))
            old_styles = ET.fromstring(before.read("xl/styles.xml")).find("m:cellXfs", ns)
            old_cell = old_sheet.find(f".//m:c[@r='{cell}']", ns)
            if cell in GENERAL_EDITABLE or cell in {"D28", "G28", "D34", "G34"}:
                assert old_styles is not None and old_cell is not None
                old = old_styles[int(old_cell.get("s", "0"))]
                for item in (old, style):
                    item.attrib.pop("applyProtection", None)
                    p = item.find("m:protection", ns)
                    if p is not None:
                        item.remove(p)
                assert ET.tostring(old) == ET.tostring(style)
