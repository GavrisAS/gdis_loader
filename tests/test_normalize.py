from __future__ import annotations

import pytest

from gdis_loader.matching.normalize import normalize_plast, normalize_well_id


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("011", "11"),
        (11, "11"),
        (11.0, "11"),
        ("11_ЗБС", "11"),
        ("011_ЗБС 3", "11"),
        ("10501_збс(ГС1+ГС2)", "10501"),
        ("10304_МЗС", "10304"),
        ("54 ГС", "54"),
    ],
)
def test_well_id_real_variants(value: object, expected: str) -> None:
    assert normalize_well_id(value).base_well_id == expected


def test_unknown_underscore_suffix_is_not_deleted() -> None:
    assert normalize_well_id("11_OTHER").base_well_id == "11_OTHER"


def test_non_numeric_source_identifier_is_preserved() -> None:
    assert normalize_well_id("Р-183").base_well_id == "Р-183"


@pytest.mark.parametrize("value", ["ПК₁", "ПК-1", "ПК 1"])
def test_plast_cosmetic_variants_match(value: str) -> None:
    assert normalize_plast(value) == "ПК1"


def test_plast_numeric_components_remain_significant() -> None:
    assert normalize_plast("ПК-19-2") == normalize_plast("ПК19(2)")
    assert normalize_plast("ПК-19-2") != normalize_plast("ПК19-20")


def test_actual_lha_superscript_plast_is_supported() -> None:
    assert normalize_plast("ПК₁₉²") == "ПК19-2"
