"""Create a privacy-safe hash manifest for a production audit run."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SOURCE_FILES: tuple[tuple[str, str], ...] = (
    ("calculator", "GDIS_Rating_Calculator_FIXED.xlsx"),
    ("fund", "Фонд 2026 на 01.08.2026.xlsx"),
    ("gdi", "Сводная таблица ГДИ.xlsx"),
    ("lha", "База ЛХА_Итог!.xlsm"),
    ("well_history", "База по скважинам.xlsx"),
    ("research_status", "Статус исследований_2026.xlsx"),
    ("daily_report", "07.2026 Cуточный рапорт БГП_полный.xlsm"),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_value(root: Path, *args: str) -> str | None:
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        check=False,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def _file_entry(role: str, name: str, path: Path) -> dict[str, Any]:
    entry: dict[str, Any] = {"role": role, "name": name}
    if not path.is_file():
        entry.update({"status": "not_available", "size_bytes": None, "sha256": None})
        return entry
    entry.update(
        {
            "status": "available",
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
    )
    return entry


def build_source_manifest(
    root: Path,
    *,
    audit_timestamp_utc: str | None = None,
    git_commit: str | None = None,
    release_tag: str | None = None,
    python_version: str | None = None,
    calculation_date: str | None = None,
    selected_field: str | None = None,
    generated_calculator: Path | None = None,
) -> dict[str, Any]:
    """Return ordered metadata and file digests without copying source bytes."""

    resolved_root = root.resolve()
    sources = [
        _file_entry(role, name, resolved_root / "data" / name) for role, name in SOURCE_FILES
    ]
    if generated_calculator is not None:
        sources.append(
            _file_entry(
                "generated_calculator",
                generated_calculator.name,
                generated_calculator,
            )
        )
    timestamp = audit_timestamp_utc or datetime.now(UTC).isoformat(timespec="seconds")
    commit = (
        git_commit if git_commit is not None else _git_value(resolved_root, "rev-parse", "HEAD")
    )
    tag = release_tag
    if tag is None:
        tag = _git_value(resolved_root, "describe", "--tags", "--exact-match")
        if tag is None:
            tag = _git_value(resolved_root, "describe", "--tags", "--abbrev=0")
    return {
        "manifest_version": 1,
        "audit_timestamp_utc": timestamp,
        "git_commit": commit,
        "release_tag": tag,
        "python_version": python_version or platform.python_version(),
        "calculation_date": calculation_date,
        "selected_field": selected_field,
        "sources": sources,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--calculation-date")
    parser.add_argument("--selected-field")
    parser.add_argument("--generated-calculator", type=Path)
    args = parser.parse_args()
    manifest = build_source_manifest(
        args.root,
        calculation_date=args.calculation_date,
        selected_field=args.selected_field,
        generated_calculator=args.generated_calculator,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0
