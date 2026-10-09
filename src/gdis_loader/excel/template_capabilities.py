"""Read-only template compatibility; never modifies the package."""

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from openpyxl.utils.cell import range_boundaries


@dataclass(slots=True, frozen=True)
class CalculatorTemplateCapabilities:
    schema_version: int | None = None
    calculation_capacity: int | None = None
    supports_missing_exclusion: bool = False
    supports_removed_criteria_model: bool = False

    def exceeds_capacity(self, rows: int) -> bool:
        return self.calculation_capacity is not None and rows > self.calculation_capacity


def detect_template_capabilities(path: Path) -> CalculatorTemplateCapabilities:
    """Require agreeing calculation/rating tables; unknown stays explicit."""
    try:
        with ZipFile(path) as archive:
            capacities = {}
            for name in archive.namelist():
                if name.startswith("xl/tables/") and name.endswith(".xml"):
                    table = ET.fromstring(archive.read(name))
                    if table.get("name") in {"tblCalculation", "tblRating"}:
                        _, start, _, end = range_boundaries(table.attrib["ref"])
                        capacities[table.attrib["name"]] = end - start
            if len(capacities) != 2 or len(set(capacities.values())) != 1:
                return CalculatorTemplateCapabilities()
            capacity = next(iter(capacities.values()))
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            version = next(
                (
                    int(e.text or "0")
                    for e in workbook.iter()
                    if e.get("name") == "GDIS_TEMPLATE_VERSION"
                ),
                1,
            )
            marker = version in {2, 3}
            return CalculatorTemplateCapabilities(
                schema_version=version,
                calculation_capacity=capacity,
                supports_missing_exclusion=marker,
                supports_removed_criteria_model=marker,
            )
    except OSError, BadZipFile, ET.ParseError, KeyError, ValueError:
        return CalculatorTemplateCapabilities()
