"""Read-only OOXML inventory; never serialize workbook source values."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def audit(source: Path, destination: Path) -> None:
    result: dict[str, object] = {
        "basename": source.name,
        "size": source.stat().st_size,
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }
    with ZipFile(source) as archive:
        parts = {}
        for name in archive.namelist():
            data = archive.read(name)
            item: dict[str, object] = {
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            if name.endswith(".xml") or name.endswith(".rels"):
                root = ET.fromstring(data)
                if "worksheets/sheet" in name:
                    formulas = {
                        c.attrib["r"]: f.text
                        for c in root.findall(".//m:c", NS)
                        if (f := c.find("m:f", NS)) is not None
                    }
                    item["formulas"] = formulas
                    item["formula_columns"] = sorted(
                        {"".join(filter(str.isalpha, c)) for c in formulas}
                    )
                    item["cached_formula_cells"] = [
                        c.attrib["r"]
                        for c in root.findall(".//m:c", NS)
                        if c.find("m:f", NS) is not None and c.find("m:v", NS) is not None
                    ]
                    for tag in (
                        "dimension",
                        "cols",
                        "mergeCells",
                        "conditionalFormatting",
                        "dataValidations",
                        "sheetViews",
                        "pageMargins",
                        "pageSetup",
                        "printOptions",
                        "tableParts",
                        "extLst",
                    ):
                        item[tag] = [
                            ET.tostring(e, encoding="unicode") for e in root.findall(f"m:{tag}", NS)
                        ]
                    item["hidden_rows"] = [
                        r.attrib for r in root.findall(".//m:row", NS) if r.get("hidden") == "1"
                    ]
                elif name in ("xl/workbook.xml", "xl/_rels/workbook.xml.rels") or any(
                    token in name for token in ("tables/", "charts/", ".rels", "customXml", "pivot")
                ):
                    item["xml"] = data.decode("utf-8")
                item["extensions"] = [
                    e.tag for e in root.iter() if "2009/9" in e.tag or "2009/" in e.tag
                ]
            parts[name] = item
        result["parts"] = parts
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    audit(args.source, args.destination)
