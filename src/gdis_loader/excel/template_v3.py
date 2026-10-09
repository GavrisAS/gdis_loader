"""Offline v2 → v3 migration: delete only the unused named data column."""

import hashlib
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from openpyxl.utils.cell import column_index_from_string, get_column_letter

from gdis_loader.excel.template_migration import CELL

V2_SHA256 = "645a3e5ba9303c42f441598e71fb7da261c9738789638cb5a0e7fceaf97d2578"
EXPECTED_PARTS = frozenset(
    {
        "xl/worksheets/sheet3.xml",
        "xl/tables/table2.xml",
        "xl/workbook.xml",
        "xl/worksheets/sheet2.xml",
        "xl/sharedStrings.xml",
    }
)


def shift_reference(reference: str) -> str:
    """Delete G, retaining absolute markers and rows in surviving references."""

    def shift(match: re.Match[str]) -> str:
        column = column_index_from_string(match[2])
        if column == 7:
            raise ValueError("Reference to deleted column G")
        return match[1] + get_column_letter(column - (column > 7)) + match[3]

    return re.sub(r"(\$?)([A-Z]+)(\$?\d+)", shift, reference)


def patch_data_sheet(text: str) -> str:
    """Preserve original XML syntax, extensions, styles and column semantics."""

    def cell(match: re.Match[str]) -> str:
        if match[1] == "G":
            return ""
        return match[0].replace(
            f'r="{match[1]}{match[2]}"', f'r="{shift_reference(match[1] + match[2])}"', 1
        )

    text = CELL.sub(cell, text)
    text = re.sub(
        r'\b(ref|sqref|activeCell)="([^"]+)"', lambda m: f'{m[1]}="{shift_reference(m[2])}"', text
    )
    text = text.replace('spans="1:26"', 'spans="1:25"')
    text = text.replace('activeCell="G15" sqref="G15"', 'activeCell="F15" sqref="F15"')

    def col(match: re.Match[str]) -> str:
        first, last = int(match[1]), int(match[2])
        if first == last == 7:
            return ""
        return match[0].replace(
            f'min="{first}" max="{last}"', f'min="{first - (first > 7)}" max="{last - (last >= 7)}"'
        )

    text = re.sub(r'<col min="(\d+)" max="(\d+)"[^>]*/>', col, text)
    return text


def migrate_v3(source: Path, output: Path) -> dict[str, dict[str, str]]:
    """SHA-pinned surgical migration; v2 is immutable, no calcChain creation."""
    if hashlib.sha256(source.read_bytes()).hexdigest() != V2_SHA256:
        raise ValueError("Unexpected structural v2 SHA-256")
    if source.resolve() == output.resolve() or output.exists():
        raise ValueError("Migration requires a new output file")
    with ZipFile(source) as archive:
        original = {n: archive.read(n) for n in archive.namelist()}
        patched = dict(original)
        text = original["xl/worksheets/sheet3.xml"].decode()
        # Move the view selection off the deleted column before shifting refs.
        text = text.replace('activeCell="G15" sqref="G15"', 'activeCell="F15" sqref="F15"')
        patched["xl/worksheets/sheet3.xml"] = patch_data_sheet(text).encode()
        table = original["xl/tables/table2.xml"].decode()
        table = re.sub(r'<tableColumn\b[^>]*name="Расходомер"[^>]*/>', "", table)
        table = table.replace('count="26"', 'count="25"').replace("A6:Z106", "A6:Y106")
        table = re.sub(
            r'(<tableColumn id=")(\d+)', lambda m: m[1] + str(int(m[2]) - (int(m[2]) > 7)), table
        )
        patched["xl/tables/table2.xml"] = table.encode()
        patched["xl/workbook.xml"] = original["xl/workbook.xml"].replace(
            b'<definedName name="GDIS_TEMPLATE_VERSION">2</definedName>',
            b'<definedName name="GDIS_TEMPLATE_VERSION">3</definedName>',
        )
        patched["xl/worksheets/sheet2.xml"] = (
            original["xl/worksheets/sheet2.xml"]
            .decode()
            .replace("Не используется: Расходомер; ", "Не используется: ")
            .encode()
        )
        # Preserve string indexes: erase the now-unreferenced label without
        # renumbering every other worksheet's shared-string references.
        shared = (
            original["xl/sharedStrings.xml"]
            .decode()
            .replace("<si><t>Расходомер</t></si>", "<si><t></t></si>")
        )
        shared = re.sub(r'(<sst\b[^>]*\bcount=")(\d+)', lambda m: m[1] + str(int(m[2]) - 1), shared)
        patched["xl/sharedStrings.xml"] = shared.encode()
        changed = {n for n in original if original[n] != patched[n]}
        if changed != EXPECTED_PARTS:
            raise ValueError(f"Unexpected changed parts: {changed ^ EXPECTED_PARTS}")
        for name, data in patched.items():
            if name.endswith(".xml"):
                ET.fromstring(data)
                if b"#REF!" in data:
                    raise ValueError(f"Broken reference: {name}")
        with ZipFile(output, "w") as target:
            target.comment = archive.comment
            for info in archive.infolist():
                target.writestr(info, patched[info.filename])
    return {
        n: {
            "before": hashlib.sha256(original[n]).hexdigest(),
            "after": hashlib.sha256(patched[n]).hexdigest(),
        }
        for n in sorted(changed)
    }
