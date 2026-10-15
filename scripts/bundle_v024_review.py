"""Build a public-safe review bundle from source, tests, and sanitized evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "docs/RELEASE_NOTES_v0.24.md",
    "docs/AUDIT_v0.24_RELEASE.md",
    "docs/AUDIT_v0.24_AH.md",
    "docs/SOURCE_NOTES.md",
    "src/gdis_loader/domain/models.py",
    "src/gdis_loader/readers/daily.py",
    "src/gdis_loader/readers/daily_context.py",
    "src/gdis_loader/source_manifest.py",
    "src/gdis_loader/service.py",
    "tests/test_daily_context.py",
    "tests/test_daily_reader.py",
    "tests/test_daily_selection.py",
    "scripts/audit_v024.py",
    "templates/calculator/SHA256SUMS.txt",
    "docs/CALCULATOR_TEMPLATE_VERSION.toml",
    "pyproject.toml",
    "uv.lock",
)


def bundle(version: str, output: Path) -> Path:
    if not version.count(".") == 1 or not all(part.isdigit() for part in version.split(".")):
        raise ValueError("version must be MAJOR.MINOR")
    payloads = {name: (ROOT / name).read_bytes() for name in FILES}
    commit = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=ROOT, text=True).strip()
    metadata = {
        "version": version,
        "commit": commit,
        "production_workbooks_included": False,
        "row_level_production_data_included": False,
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in payloads.items()},
    }
    payloads["BUILD_EVIDENCE.json"] = json.dumps(metadata, ensure_ascii=False, indent=2).encode()
    payloads["SHA256SUMS.txt"] = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n"
        for name, content in sorted(payloads.items())
    ).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in sorted(payloads.items()):
            info = ZipInfo(name, date_time=(2026, 10, 15, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    with ZipFile(output) as archive:
        forbidden = [
            name
            for name in archive.namelist()
            if name.lower().endswith((".xlsx", ".xlsm", ".xls", ".pptx", ".docx"))
            and name != "templates/calculator/SHA256SUMS.txt"
        ]
        if forbidden:
            output.unlink(missing_ok=True)
            raise ValueError(f"Review bundle contains workbook files: {forbidden}")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(bundle(args.version, args.output))
