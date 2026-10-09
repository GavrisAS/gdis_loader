"""Reproducible review inventory; no production source/output workbooks."""

import hashlib
import json
import subprocess
import tomllib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]


def bundle() -> Path:
    metadata = tomllib.loads((ROOT / "docs/CALCULATOR_TEMPLATE_VERSION.toml").read_text())
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
        ROOT / "src/gdis_loader/excel/template_v3.py",
        ROOT / "tests/test_template_v3.py",
        ROOT / "docs/AUDIT_v0.23.md",
        ROOT / "docs/RELEASE_NOTES_v0.23.md",
        ROOT / "tests/test_template_migration.py",
        ROOT / "tests/test_template_capabilities.py",
        ROOT / "tests/fixtures/calculator_formula_v019.txt",
    ]
    payloads = {str(p.relative_to(ROOT)): p.read_bytes() for p in files}
    candidate = metadata["candidate"]["path"]
    rollback = "templates/calculator/archive/GDIS_Rating_Calculator_v0.19_pre_structural.xlsx"
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tags = subprocess.check_output(
        ["git", "tag", "--points-at", "HEAD"], cwd=ROOT, text=True
    ).splitlines()
    audit = {
        "loader_release_target": metadata["loader_release_target"],
        "loader_commit": commit,
        "loader_version": (
            metadata["loader_release_target"]
            if metadata["loader_release_target"] in tags
            else "unreleased"
        ),
        "calculator_template_version": metadata["calculator_template_version"],
        "calculator_template_sha256": hashlib.sha256(payloads[candidate]).hexdigest(),
        "rollback_template_version": 1,
        "rollback_template_sha256": hashlib.sha256(payloads[rollback]).hexdigest(),
        "native_excel": metadata["native_excel_acceptance"],
        "canonical": metadata["canonical"],
        "production_source_workbooks_included": False,
    }
    payloads["audit.json"] = json.dumps(audit, indent=2).encode()
    # Explicit minimal-evidence allowlist: never include production books/logs.
    for name in (
        "ooxml-diff.json",
        "structural-proof.json",
        "production-summary.json",
        "controls-reconciliation.json",
        "release-evidence.json",
        "quality-summary.json",
        "research-type-mapping.json",
        "plast-evidence.json",
        "Golden_v3_NATIVE_PENDING.xlsx",
        "Golden_v2_REFERENCE.xlsx",
        "source-preservation.json",
        "AUDIT_v0.23_FINAL.md",
        "native-smoke-report.json",
    ):
        path = ROOT / "artifacts/v0.23" / name
        if path.exists():
            payloads[name] = path.read_bytes()
    payloads["SHA256SUMS.txt"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(payloads.items())
    ).encode()
    output = ROOT / "artifacts/v0.23/GDIS_v0.23_review.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in sorted(payloads.items()):
            info = ZipInfo(name, date_time=(2026, 10, 9, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return output


if __name__ == "__main__":
    print(bundle())
