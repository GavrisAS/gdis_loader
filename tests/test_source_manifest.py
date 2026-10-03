from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

from gdis_loader.config import CriteriaConfig
from gdis_loader.domain.models import SourcePaths
from gdis_loader.source_manifest import SOURCE_FILES, build_source_manifest


def _runtime_paths(root: Path) -> SourcePaths:
    return SourcePaths(**{role: root / "data" / name for role, name in SOURCE_FILES})


def test_source_manifest_hashes_fixture_file_and_uses_deterministic_order(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    payload = b"synthetic workbook fixture payload"
    for _role, name in SOURCE_FILES:
        (data_dir / name).write_bytes(payload)

    first = build_source_manifest(
        tmp_path,
        paths=_runtime_paths(tmp_path),
        run_timestamp_utc="2026-10-03T00:00:00+00:00",
        git_commit="abc123",
        release_tag="v0.15",
        python_version="3.14.0",
        calculation_date="2026-10-02",
        selected_field="Береговое",
    )
    second = build_source_manifest(
        tmp_path,
        paths=_runtime_paths(tmp_path),
        run_timestamp_utc="2026-10-03T00:00:00+00:00",
        git_commit="abc123",
        release_tag="v0.15",
        python_version="3.14.0",
        calculation_date="2026-10-02",
        selected_field="Береговое",
    )

    assert first == second
    assert [entry["role"] for entry in first["sources"]] == [role for role, _name in SOURCE_FILES]
    assert first["sources"][0]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert first["sources"][0]["size_bytes"] == len(payload)


def test_source_manifest_records_missing_inputs_without_invented_hashes(tmp_path: Path) -> None:
    manifest = build_source_manifest(
        tmp_path,
        paths=_runtime_paths(tmp_path),
        run_timestamp_utc="2026-10-03T00:00:00+00:00",
        git_commit="abc123",
        release_tag="v0.15",
        python_version="3.14.0",
    )

    assert all(
        item["status"] == "not_available" and item["size_bytes"] is None and item["sha256"] is None
        for item in manifest["sources"]
    )


def test_manifest_contains_only_metadata_not_source_bytes_or_absolute_paths(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    payload = b"DO-NOT-COPY-PRODUCTION-BYTES"
    (data_dir / SOURCE_FILES[0][1]).write_bytes(payload)

    encoded = json.dumps(
        build_source_manifest(
            tmp_path,
            paths=_runtime_paths(tmp_path),
            run_timestamp_utc="2026-10-03T00:00:00+00:00",
            git_commit="abc123",
            release_tag="v0.15",
            python_version="3.14.0",
        ),
        ensure_ascii=False,
    )

    assert payload.decode() not in encoded
    assert str(tmp_path.resolve()) not in encoded
    assert "username" not in encoded.lower()


def test_generated_calculator_is_hashed_without_being_included(tmp_path: Path) -> None:
    generated = tmp_path / "GDIS_result.xlsx"
    payload = b"synthetic generated workbook"
    generated.write_bytes(payload)

    manifest = build_source_manifest(
        tmp_path,
        paths=_runtime_paths(tmp_path),
        run_timestamp_utc="2026-10-03T00:00:00+00:00",
        git_commit="abc123",
        release_tag="v0.15",
        python_version="3.14.0",
        generated_calculator=generated,
    )
    entry = manifest["sources"][-1]

    assert entry == {
        "role": "generated_calculator",
        "name": "GDIS_result.xlsx",
        "status": "available",
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


@pytest.mark.skipif(os.name == "nt", reason="The audit packager is a Bash script.")
def test_audit_includes_manifest_and_excludes_workbooks_and_user_config(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "audit-output"
    environment = {
        **os.environ,
        "GDIS_AUDIT_OUTPUT_DIR": str(output_dir),
        "GDIS_AUDIT_CALCULATION_DATE": "2026-10-02",
        "GDIS_AUDIT_SELECTED_FIELD": "Береговое",
    }
    subprocess.run(
        ["bash", "scripts/make_audit.sh"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    archives = tuple(output_dir.glob("*.tar.xz"))
    assert len(archives) == 1

    with tarfile.open(archives[0], mode="r:xz") as archive:
        members = tuple(member.name.removeprefix("./") for member in archive.getmembers())
        file_names = {Path(name).name for name in members if not name.endswith("/")}
        assert "SOURCE_MANIFEST.json" in file_names
        assert "config.example.toml" in file_names
        assert "config.toml" not in file_names
        assert not any(name == ".env" or name.startswith(".env.") for name in file_names)
        assert not any(name.endswith((".xlsx", ".xlsm", ".xls")) for name in file_names)
        manifest_member = next(
            member
            for member in archive.getmembers()
            if member.name.removeprefix("./") == "SOURCE_MANIFEST.json"
        )
        manifest_file = archive.extractfile(manifest_member)
        assert manifest_file is not None
        manifest = json.load(manifest_file)
        assert manifest["calculation_date"] == "2026-10-02"
        assert manifest["selected_field"] == "Береговое"
        assert [item["role"] for item in manifest["sources"]] == [
            role for role, _name in SOURCE_FILES
        ]


def test_runtime_custom_file_overrides_neighbor_and_serializes_criteria(tmp_path: Path) -> None:
    from dataclasses import replace

    paths = _runtime_paths(tmp_path)
    paths.calculator.parent.mkdir()
    paths.calculator.write_bytes(b"old canonical bytes")
    selected = tmp_path / "custom chosen.xlsx"
    selected.write_bytes(b"actual selected bytes")
    criteria = CriteriaConfig(gdm_abs_delta_threshold=7.0)
    manifest = build_source_manifest(
        tmp_path,
        paths=replace(paths, calculator=selected),
        criteria=criteria,
        criteria_explicit_fields=frozenset({"gdm_abs_delta_threshold"}),
    )
    assert manifest["sources"][0]["name"] == selected.name
    assert manifest["sources"][0]["sha256"] == hashlib.sha256(selected.read_bytes()).hexdigest()
    assert manifest["criteria"]["gdm"]["abs_delta_threshold"] == 7.0
    assert manifest["criteria_source"] == "mixed"
    assert str(tmp_path) not in json.dumps(manifest)
    defaults = build_source_manifest(tmp_path, paths=paths)
    assert defaults["criteria"]["insufficient_gdi"]["min_count"] == 2
    assert defaults["criteria_source"] == "defaults"


def test_windows_path_is_never_serialized_as_an_absolute_name(tmp_path: Path) -> None:
    from dataclasses import replace

    paths = replace(_runtime_paths(tmp_path), fund=Path(r"C:\Users\private\custom fund.xlsx"))
    manifest = build_source_manifest(tmp_path, paths=paths)
    entry = next(item for item in manifest["sources"] if item["role"] == "fund")
    assert entry["name"] == "custom fund.xlsx"
    assert r"C:\Users" not in json.dumps(manifest)


def test_manifest_works_without_git_executable(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import gdis_loader.source_manifest as module

    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("git is not installed")

    monkeypatch.setattr(module.subprocess, "run", unavailable)
    manifest = build_source_manifest(tmp_path, paths=_runtime_paths(tmp_path))
    assert manifest["runtime_git_commit"] is None
    assert manifest["runtime_release_tag"] is None


def test_frozen_manifest_uses_embedded_metadata_without_git(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import sys
    from types import ModuleType

    import gdis_loader.source_manifest as module

    build = ModuleType("gdis_loader._build_version")
    build.BUILD_VERSION = "0.16"  # ty: ignore[unresolved-attribute]
    build.BUILD_COMMIT = "abcdef"  # ty: ignore[unresolved-attribute]
    monkeypatch.setitem(sys.modules, "gdis_loader._build_version", build)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        module, "_git_value", lambda *_args: pytest.fail("frozen app must not run git")
    )
    manifest = build_source_manifest(tmp_path, paths=_runtime_paths(tmp_path))
    assert manifest["runtime_git_commit"] == "abcdef"
    assert manifest["runtime_release_tag"] == "v0.16"


@pytest.mark.parametrize("runtime_commit,status", [("abc", "matched"), (None, "unknown")])
def test_audit_preserves_run_and_separates_creation_metadata(
    runtime_commit: str | None,
    status: str,
) -> None:
    from gdis_loader.source_manifest import attach_audit_provenance

    runtime = {
        "runtime_git_commit": runtime_commit,
        "runtime_release_tag": None,
        "run_timestamp_utc": "run-time",
        "sources": [],
        "criteria": {},
    }
    original = json.loads(json.dumps(runtime))
    audited = attach_audit_provenance(
        runtime, git_commit="abc", release_tag="v0.17", timestamp_utc="audit-time"
    )
    assert runtime == original
    assert audited["run_timestamp_utc"] == "run-time"
    assert audited["audit_timestamp_utc"] == "audit-time"
    assert audited["runtime_git_commit"] == runtime_commit
    assert audited["audit_git_commit"] == "abc"
    assert audited["runtime_commit_status"] == status
    assert audited["runtime_release_status"] == "unknown"


@pytest.mark.parametrize("commit,tag", [("other", None), ("abc", "v0.16")])
def test_audit_rejects_mixed_runtime_revision(commit: str, tag: str | None) -> None:
    from gdis_loader.source_manifest import AuditProvenanceError, attach_audit_provenance

    runtime = {"runtime_git_commit": commit, "runtime_release_tag": tag}
    original = dict(runtime)
    with pytest.raises(AuditProvenanceError):
        attach_audit_provenance(runtime, git_commit="abc", release_tag="v0.17")
    assert runtime == original


def test_audit_validates_legacy_runtime_commit_without_replacing_it() -> None:
    from gdis_loader.source_manifest import AuditProvenanceError, attach_audit_provenance

    with pytest.raises(AuditProvenanceError):
        attach_audit_provenance({"git_commit": "old"}, git_commit="new", release_tag=None)


def test_audit_matching_release_tag() -> None:
    from gdis_loader.source_manifest import attach_audit_provenance

    result = attach_audit_provenance(
        {"runtime_git_commit": "abc", "runtime_release_tag": "v0.17"},
        git_commit="abc",
        release_tag="v0.17",
    )
    assert result["runtime_release_tag"] == result["audit_release_tag"] == "v0.17"
    assert result["runtime_release_status"] == "matched"


def test_legacy_run_timestamp_is_preserved_during_schema_upgrade() -> None:
    from gdis_loader.source_manifest import attach_audit_provenance

    runtime = {
        "manifest_version": 2,
        "audit_timestamp_utc": "old-run-time",
        "git_commit": "abc",
        "release_tag": "v0.17",
    }
    result = attach_audit_provenance(
        runtime, git_commit="abc", release_tag="v0.17", timestamp_utc="new-audit-time"
    )
    assert runtime["audit_timestamp_utc"] == "old-run-time"
    assert result["run_timestamp_utc"] == "old-run-time"
    assert result["audit_timestamp_utc"] == "new-audit-time"
    assert result["runtime_git_commit"] == result["git_commit"] == "abc"


def test_manifest_cli_mismatch_fails_before_writing_output(tmp_path: Path) -> None:
    report = tmp_path / "runtime.json"
    output = tmp_path / "manifest.json"
    report.write_text(json.dumps({"source_manifest": {"runtime_git_commit": "other-run"}}))
    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/source_manifest.py",
            "--runtime-report",
            str(report),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Runtime commit differs" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("mutation", ["unchanged", "modified", "same_name", "missing"])
def test_audit_rehashes_runtime_sources(tmp_path: Path, mutation: str) -> None:
    from gdis_loader.source_manifest import AuditProvenanceError, revalidate_sources

    path = tmp_path / "source.xlsx"
    path.write_bytes(b"original")
    manifest = build_source_manifest(tmp_path, paths=_runtime_paths(tmp_path))
    import hashlib

    manifest["sources"] = [
        {
            "role": "fund",
            "name": path.name,
            "size_bytes": 8,
            "sha256": hashlib.sha256(b"original").hexdigest(),
            "status": "available",
        }
    ]
    if mutation == "modified":
        path.write_bytes(b"changed!")
    elif mutation == "same_name":
        neighbor = tmp_path / "neighbor"
        neighbor.mkdir()
        path = neighbor / path.name
        path.write_bytes(b"different")
    elif mutation == "missing":
        path.unlink()
    if mutation == "unchanged":
        result = revalidate_sources(manifest, {"fund": str(path)})
        assert result["source_revalidation_status"] == "revalidated"
        assert str(tmp_path) not in json.dumps(result)
        assert "revalidation_status" not in manifest["sources"][0]
    else:
        with pytest.raises(AuditProvenanceError):
            revalidate_sources(manifest, {"fund": str(path)})
        if mutation == "missing":
            result = revalidate_sources(manifest, {"fund": str(path)}, strict=False)
            assert result["sources"][0]["revalidation_status"] == "unavailable"
            assert result["source_revalidation_status"] == "not_revalidated"


@pytest.mark.parametrize(
    "mutation",
    ["unchanged", "modified", "same_name", "missing_path", "missing_file", "missing_entry"],
)
def test_audit_rehashes_generated_calculator(tmp_path: Path, mutation: str) -> None:
    from gdis_loader.source_manifest import AuditProvenanceError, revalidate_generated_calculator

    path = tmp_path / "private" / "output.xlsx"
    path.parent.mkdir()
    path.write_bytes(b"original")
    manifest = build_source_manifest(tmp_path, generated_calculator=path)
    reference = str(path)
    if mutation == "modified":
        path.write_bytes(b"changed!")
    elif mutation == "same_name":
        neighbor = tmp_path / path.name
        neighbor.write_bytes(b"changed!")
        reference = str(neighbor)
    elif mutation == "missing_path":
        reference = None
    elif mutation == "missing_file":
        path.unlink()
    elif mutation == "missing_entry":
        manifest["sources"] = []
    if mutation == "unchanged":
        result = revalidate_generated_calculator(manifest, reference)
        assert result["manifest_version"] == 4
        assert result["generated_calculator_revalidation_status"] == "revalidated"
        assert result["sources"][-1]["revalidation_status"] == "matched"
        assert str(tmp_path) not in json.dumps(result)
        assert "private" not in json.dumps(result)
        assert "revalidation_status" not in manifest["sources"][-1]
    else:
        with pytest.raises(AuditProvenanceError):
            revalidate_generated_calculator(manifest, reference)
