from __future__ import annotations

from gdis_loader.versioning import next_version


def test_next_version_increments_single_digit_minor() -> None:
    assert next_version(["v0.1"], "0.1.0") == "v0.2"
    assert next_version(["v0.9"], "0.1.0") == "v0.10"


def test_next_version_increments_multi_digit_minor() -> None:
    assert next_version(["v0.10"], "0.1.0") == "v0.11"
    assert next_version(["v0.99"], "0.1.0") == "v0.100"
    assert next_version(["v1.99"], "0.1.0") == "v1.100"


def test_next_version_ignores_non_release_tags() -> None:
    assert next_version(["v0.1.0", "release-1", "foo"], "0.1.0") == "v0.2"


def test_next_version_falls_back_to_project_version_without_tags() -> None:
    assert next_version([], "0.1.0") == "v0.2"


def test_next_version_preserves_minor_counter_after_manual_major_change() -> None:
    assert next_version(["v0.37"], "1.0.0") == "v1.38"


def test_next_version_uses_numeric_tag_order_and_monotonic_minor() -> None:
    assert next_version(["v0.9", "v0.10", "v0.99"], "0.1.0") == "v0.100"
