"""Generate local SHA metadata, exact formula diff, and relationship evidence."""

from __future__ import annotations

import argparse
import json
import posixpath
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from openpyxl.worksheet.cell_range import MultiCellRange

from gdis_loader.excel.template_migration import (
    CAPACITY,
    EXPECTED_CHANGED,
    SOURCE_SHA256,
    TEMPLATE_VERSION,
    sha256,
)

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _formulas(data: bytes) -> dict[str, str | None]:
    root = ET.fromstring(data)
    return {
        c.attrib["r"]: c.findtext("m:f", namespaces=NS)
        for c in root.findall(".//m:c", NS)
        if c.find("m:f", NS) is not None
    }


def report(source: Path, backup: Path, candidate: Path, directory: Path) -> None:
    assert sha256(source) == SOURCE_SHA256
    assert source.read_bytes() == backup.read_bytes()
    changes = {}
    relationships = 0
    max_formula = 0
    with ZipFile(source) as before, ZipFile(candidate) as after:
        names = set(after.namelist())
        assert set(before.namelist()) - names == {"xl/calcChain.xml"}
        assert not names - set(before.namelist())
        for name in before.namelist():
            if name not in names:
                changes[name] = {"action": "removed"}
            elif before.read(name) != after.read(name):
                item = {}
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
                    old_root, new_root = (
                        ET.fromstring(before.read(name)),
                        ET.fromstring(after.read(name)),
                    )
                    tag = f"{{{NS['m']}}}c"
                    old_styles = {c.attrib["r"]: c.get("s") for c in old_root.iter(tag)}
                    new_styles = {c.attrib["r"]: c.get("s") for c in new_root.iter(tag)}
                    assert all(
                        new_styles.get(cell) == style
                        or (
                            name == "xl/worksheets/sheet2.xml"
                            and (cell == "B12" or cell.startswith("L"))
                            and new_styles.get(cell) == "0"
                        )
                        for cell, style in old_styles.items()
                    )
                    old, new = _formulas(before.read(name)), _formulas(after.read(name))
                    item = {
                        "formula_changes": {
                            cell: {"old": old.get(cell), "new": f}
                            for cell, f in new.items()
                            if old.get(cell) != f
                        },
                        "removed_formula_cells": sorted(old.keys() - new.keys()),
                    }
                changes[name] = item
        assert set(changes) == EXPECTED_CHANGED
        for name in sorted(names):
            if name.endswith(".rels"):
                parent = posixpath.dirname(posixpath.dirname(name)) if name != "_rels/.rels" else ""
                for rel in ET.fromstring(after.read(name)):
                    if rel.get("TargetMode") == "External":
                        continue
                    target = rel.attrib["Target"]
                    resolved = (
                        posixpath.normpath(posixpath.join(parent, target))
                        if not target.startswith("/")
                        else target[1:]
                    )
                    assert resolved in names, (name, resolved)
                    relationships += 1
            if name.endswith(".xml"):
                root = ET.fromstring(after.read(name))
                for element in root.iter():
                    if "sqref" in element.attrib:
                        MultiCellRange(element.attrib["sqref"])
                    if element.tag.endswith("}sqref") and element.text:
                        MultiCellRange(element.text)
                assert b"#REF!" not in after.read(name)
                for formula in root.iter(f"{{{NS['m']}}}f"):
                    max_formula = max(max_formula, len(formula.text or ""))
        assert max_formula <= 8192
    directory.mkdir(parents=True, exist_ok=True)
    metadata = {
        "calculator_template_version": TEMPLATE_VERSION,
        "capacity": CAPACITY,
        "loader_baseline": "v0.19",
        "baseline_commit": "934c005100ac8289957e816cba2f8a2b55914152",
        "source": {"path": str(source), "size": source.stat().st_size, "sha256": sha256(source)},
        "backup": {"path": str(backup), "sha256": sha256(backup), "byte_identity": True},
        "candidate": {
            "path": str(candidate),
            "size": candidate.stat().st_size,
            "sha256": sha256(candidate),
        },
    }
    proof = {
        "unexpected_parts": 0,
        "unexpected_cell_style_changes": 0,
        "changed_entries": sorted(changes),
        "orphan_relationships": 0,
        "relationships_checked": relationships,
        "max_formula_length": max_formula,
        "broken_ref_text": 0,
    }
    for name, value in (
        ("template-version.json", metadata),
        ("formula-map.json", changes),
        ("structural-proof.json", proof),
    ):
        (directory / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps({"metadata": metadata, "proof": proof}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "backup", "candidate", "directory"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    report(args.source, args.backup, args.candidate, args.directory)
