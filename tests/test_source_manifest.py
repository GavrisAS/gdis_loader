from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

from gdis_loader.source_manifest import SOURCE_FILES, build_source_manifest


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
        audit_timestamp_utc="2026-10-03T00:00:00+00:00",
        git_commit="abc123",
        release_tag="v0.15",
        python_version="3.14.0",
        calculation_date="2026-10-02",
        selected_field="Береговое",
    )
    second = build_source_manifest(
        tmp_path,
        audit_timestamp_utc="2026-10-03T00:00:00+00:00",
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
        audit_timestamp_utc="2026-10-03T00:00:00+00:00",
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
            audit_timestamp_utc="2026-10-03T00:00:00+00:00",
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
        audit_timestamp_utc="2026-10-03T00:00:00+00:00",
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
