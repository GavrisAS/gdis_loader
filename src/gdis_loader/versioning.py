"""Calculate the next two-component release version from git tags."""

from __future__ import annotations

import argparse
import re
import subprocess
import tomllib
from collections.abc import Iterable, Sequence
from pathlib import Path

_RELEASE_TAG = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)$")
_PROJECT_VERSION = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)(?:\.\d+)?(?:[-+].*)?$")


def parse_release_tag(tag: str) -> tuple[int, int] | None:
    """Return numeric ``(major, minor)`` for a strict release tag."""

    match = _RELEASE_TAG.fullmatch(tag)
    if match is None:
        return None
    return int(match.group("major")), int(match.group("minor"))


def parse_project_version(version: str) -> tuple[int, int]:
    """Return the logical two-component version from a PEP 440-like value."""

    match = _PROJECT_VERSION.fullmatch(version.strip())
    if match is None:
        raise ValueError(f"Project version is not numeric MAJOR.MINOR: {version!r}")
    return int(match.group("major")), int(match.group("minor"))


def release_versions(tags: Iterable[str]) -> tuple[tuple[int, int], ...]:
    """Keep only strict release tags and compare their components numerically."""

    return tuple(version for tag in tags if (version := parse_release_tag(tag)) is not None)


def next_version(tags: Iterable[str], project_version: str) -> str:
    """Return the next ``vMAJOR.MINOR`` without changing the repository."""

    project_major, project_minor = parse_project_version(project_version)
    versions = release_versions(tags)
    if versions:
        latest_major, latest_minor = max(versions)
        # A manually changed project major is allowed to move the next release
        # forward, while the largest observed minor remains the monotonic floor.
        major = max(latest_major, project_major)
        minor = max(latest_minor, project_minor)
    else:
        major, minor = project_major, project_minor
    return f"v{major}.{minor + 1}"


def _git_tags() -> tuple[str, ...]:
    completed = subprocess.run(
        ["git", "tag", "--list"],
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(line for line in completed.stdout.splitlines() if line)


def _project_version(path: Path) -> str:
    with path.open("rb") as stream:
        metadata = tomllib.load(stream)
    return str(metadata["project"]["version"])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=Path("pyproject.toml"),
        help="project metadata file used when no release tags exist",
    )
    args = parser.parse_args(argv)
    print(next_version(_git_tags(), _project_version(args.pyproject)))
    return 0
