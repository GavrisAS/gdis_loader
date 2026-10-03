"""Reproducible review inventory; no production source/output workbooks."""

import hashlib
import json
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]


def bundle() -> Path:
    files = [
        *sorted((ROOT / "templates/calculator").rglob("*.xlsx")),
        *sorted((ROOT / "docs").glob("CALCULATOR_*")),
        ROOT / "docs/STRUCTURAL_CALCULATOR_MIGRATION.md",
        ROOT / "templates/calculator/SHA256SUMS.txt",
        ROOT / "templates/calculator/README.md",
        *sorted((ROOT / "scripts").glob("*calculator*.py")),
        ROOT / "scripts/prepare_excel_golden.py",
        ROOT / "scripts/scan_excel_smoke.py",
        ROOT / "src/gdis_loader/excel/template_migration.py",
        ROOT / "src/gdis_loader/excel/template_capabilities.py",
        ROOT / "tests/test_template_migration.py",
        ROOT / "tests/test_template_capabilities.py",
        ROOT / "tests/fixtures/calculator_formula_v019.txt",
    ]
    payloads = {str(p.relative_to(ROOT)): p.read_bytes() for p in files}
    candidate = "templates/calculator/GDIS_Rating_Calculator_STRUCTURAL_v2.xlsx"
    rollback = "templates/calculator/archive/GDIS_Rating_Calculator_v0.19_pre_structural.xlsx"
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tags = subprocess.check_output(
        ["git", "tag", "--points-at", "HEAD"], cwd=ROOT, text=True
    ).splitlines()
    audit = {
        "loader_release_target": "0.21",
        "loader_commit": commit,
        "loader_version": "0.21" if "v0.21" in tags else "unreleased",
        "calculator_template_version": 2,
        "calculator_template_sha256": hashlib.sha256(payloads[candidate]).hexdigest(),
        "rollback_template_version": 1,
        "rollback_template_sha256": hashlib.sha256(payloads[rollback]).hexdigest(),
        "native_excel": "PENDING",
        "canonical": False,
        "production_source_workbooks_included": False,
    }
    payloads["audit.json"] = json.dumps(audit, indent=2).encode()
    for name in ("structural-proof.json", "formula-map.json", "Golden_native_PENDING.xlsx"):
        path = ROOT / "artifacts/calculator/final" / name
        if path.exists():
            payloads[name] = path.read_bytes()
    payloads["SHA256SUMS.txt"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(payloads.items())
    ).encode()
    output = ROOT / "artifacts/calculator/Calculator_structural_v2_final_review.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in sorted(payloads.items()):
            info = ZipInfo(name, date_time=(2026, 10, 3, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return output


if __name__ == "__main__":
    print(bundle())
