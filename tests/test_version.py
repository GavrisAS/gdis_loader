from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from gdis_loader import SOURCE_VERSION
from gdis_loader.versioning import next_version, parse_project_version, parse_release_tag


def test_project_version_is_strictly_two_component() -> None:
    assert parse_project_version("0.1") == (0, 1)
    assert parse_project_version("1.38") == (1, 38)
    assert parse_project_version("12.104") == (12, 104)


def test_source_version_matches_project_version() -> None:
    with (Path(__file__).parents[1] / "pyproject.toml").open("rb") as stream:
        project_version = str(tomllib.load(stream)["project"]["version"])

    assert project_version == SOURCE_VERSION
    assert parse_project_version(SOURCE_VERSION) == parse_project_version(project_version)


@pytest.mark.parametrize(
    "version",
    ["0.1.0", "v0.1", "1", "1.2.3", "1.2rc1", " 0.1", "0.1 "],
)
def test_project_version_rejects_patch_prefix_and_suffix(version: str) -> None:
    with pytest.raises(ValueError):
        parse_project_version(version)


def test_release_tag_parser_is_strict() -> None:
    assert parse_release_tag("v0.1") == (0, 1)
    assert parse_release_tag("v12.104") == (12, 104)
    for tag in ("v0.1.0", "0.1", "v1", "v1.2.3", "v1.2rc1"):
        assert parse_release_tag(tag) is None


def test_next_version_increments_single_digit_minor() -> None:
    assert next_version(["v0.1"], "0.1") == "v0.2"
    assert next_version(["v0.9"], "0.1") == "v0.10"


def test_next_version_increments_multi_digit_minor() -> None:
    assert next_version(["v0.10"], "0.1") == "v0.11"
    assert next_version(["v0.99"], "0.1") == "v0.100"


def test_next_version_uses_global_minor_floor_across_majors() -> None:
    assert next_version(["v1.100", "v2.5"], "2.5") == "v2.101"


def test_next_version_preserves_minor_counter_after_manual_major_change() -> None:
    assert next_version(["v0.37"], "1.37") == "v1.38"


def test_next_version_ignores_non_release_tags() -> None:
    assert next_version(["v0.1.0", "release-1", "foo"], "0.1") == "v0.2"


def test_next_version_falls_back_to_project_version_without_tags() -> None:
    assert next_version([], "0.1") == "v0.2"


@pytest.mark.parametrize("version", ["0.1.0", "v0.1", "1", "1.2.3", "1.2rc1"])
def test_next_version_rejects_patch_project_version(version: str) -> None:
    with pytest.raises(ValueError):
        next_version([], version)
