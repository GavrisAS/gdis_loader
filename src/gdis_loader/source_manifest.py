"""Create a privacy-safe hash manifest for a production audit run."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any

from gdis_loader.config import CriteriaConfig, config_path, load_config
from gdis_loader.domain.models import SourcePaths

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
    try:
        result = subprocess.run(
            ("git", "-C", str(root), *args),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def _file_entry(role: str, name: str, path: Path) -> dict[str, Any]:
    entry: dict[str, Any] = {"role": role, "name": PureWindowsPath(name).name}
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
    paths: SourcePaths | None = None,
    criteria: CriteriaConfig | None = None,
    criteria_explicit_fields: frozenset[str] = frozenset(),
    audit_timestamp_utc: str | None = None,
    git_commit: str | None = None,
    release_tag: str | None = None,
    python_version: str | None = None,
    calculation_date: str | None = None,
    selected_field: str | None = None,
    generated_calculator: Path | None = None,
) -> dict[str, Any]:
    """Return ordered metadata and file digests without copying source bytes."""

    criteria = criteria or CriteriaConfig()
    resolved_root = root.resolve()
    sources = []
    for role, _canonical_name in SOURCE_FILES:
        path = getattr(paths, role) if paths is not None else None
        sources.append(
            _file_entry(role, path.name, path)
            if path is not None
            else {
                "role": role,
                "name": None,
                "status": "not_selected",
                "size_bytes": None,
                "sha256": None,
            }
        )
    if generated_calculator is not None:
        sources.append(
            _file_entry(
                "generated_calculator",
                generated_calculator.name,
                generated_calculator,
            )
        )
    timestamp = audit_timestamp_utc or datetime.now(UTC).isoformat(timespec="seconds")
    if getattr(sys, "frozen", False):
        try:
            build = importlib.import_module("gdis_loader._build_version")
        except ModuleNotFoundError:
            build = None
        git_commit = git_commit or getattr(build, "BUILD_COMMIT", None)
        release_tag = release_tag or (f"v{build.BUILD_VERSION}" if build is not None else None)
    commit = (
        git_commit
        if git_commit is not None
        else (
            None
            if getattr(sys, "frozen", False)
            else _git_value(resolved_root, "rev-parse", "HEAD")
        )
    )
    tag = release_tag
    if tag is None and not getattr(sys, "frozen", False):
        tag = _git_value(resolved_root, "describe", "--tags", "--exact-match")
        if tag is None:
            tag = _git_value(resolved_root, "describe", "--tags", "--abbrev=0")
    return {
        "manifest_version": 2,
        "audit_timestamp_utc": timestamp,
        "git_commit": commit,
        "release_tag": tag,
        "python_version": python_version or platform.python_version(),
        "calculation_date": calculation_date,
        "selected_field": selected_field,
        "sources": sources,
        "criteria": criteria_snapshot(criteria),
        "criteria_source": (
            "defaults"
            if not criteria_explicit_fields
            else "config"
            if criteria_explicit_fields == frozenset(criteria.as_dict())
            else "mixed"
        ),
    }


def criteria_snapshot(criteria: CriteriaConfig) -> dict[str, dict[str, int | float]]:
    """Serialize only approved numeric criteria, without user config or paths."""
    return {
        "insufficient_gdi": {"min_count": criteria.insufficient_gdi_min_count},
        "productivity_decline": {"min_increase": criteria.productivity_min_increase},
        "chlorine_growth": {
            "current_min_mg_dm3": criteria.chlorine_current_min_mg_dm3,
            "delta_min_mg_dm3": criteria.chlorine_delta_min_mg_dm3,
        },
        "downhole": {"depth_threshold_m": criteria.downhole_depth_threshold_m},
        "gdm": {
            "abs_delta_threshold": criteria.gdm_abs_delta_threshold,
            "fallback_max_age_days": criteria.gdm_fallback_max_age_days,
        },
        "gas_rate": {"working_day_min_rate": criteria.gas_rate_working_day_min_rate},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--runtime-report", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--calculation-date")
    parser.add_argument("--selected-field")
    parser.add_argument("--generated-calculator", type=Path)
    args = parser.parse_args()
    if args.runtime_report is not None:
        manifest = json.loads(args.runtime_report.read_text(encoding="utf-8"))["source_manifest"]
        manifest["git_commit"] = _git_value(args.root, "rev-parse", "HEAD")
        manifest["release_tag"] = _git_value(args.root, "describe", "--tags", "--exact-match")
    else:
        loaded = load_config(args.config or config_path()).config
        selected = {role: getattr(loaded, role) for role, _name in SOURCE_FILES}
        runtime_paths = SourcePaths(**{role: Path(value) for role, value in selected.items()})
        manifest = build_source_manifest(
            args.root,
            paths=runtime_paths,
            criteria=loaded.criteria,
            criteria_explicit_fields=loaded.criteria_explicit_fields,
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
