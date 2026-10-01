from __future__ import annotations

import pytest

from gdis_loader.matching.normalize import normalize_plast, normalize_well_id


@pytest.mark.parametrize(
    ("value", "expected_root", "expected_target"),
    [
        ("011", "11", "11"),
        (11, "11", "11"),
        (11.0, "11", "11"),
        ("11_ЗБС", "11", "11_ЗБС"),
        ("011_ЗБС 3", "11", "11_ЗБС 3"),
        ("10501_збс(ГС1+ГС2)", "10501", "10501_ЗБС(ГС1+ГС2)"),
        ("10304_МЗС", "10304", "10304_МЗС"),
        ("54 ГС", "54", "54_ГС"),
    ],
)
def test_well_id_keeps_root_and_lifecycle_identity(
    value: object, expected_root: str, expected_target: str
) -> None:
    normalized = normalize_well_id(value)
    assert normalized.base_well_id == expected_root
    assert normalized.target_well_id == expected_target


def test_unknown_underscore_suffix_is_not_deleted() -> None:
    normalized = normalize_well_id("011_OTHER")
    assert normalized.base_well_id == "11"
    assert normalized.target_well_id == "11_OTHER"


def test_non_numeric_source_identifier_is_preserved() -> None:
    normalized = normalize_well_id("Р-183")
    assert normalized.base_well_id == normalized.target_well_id == "Р-183"


def test_mzs_zbs_and_pvlg_are_distinct_target_identities_with_shared_root() -> None:
    for root, variant in (("10403", "МЗС"), ("51", "ЗБС"), ("54", "ПВЛГ")):
        parent = normalize_well_id(root)
        child = normalize_well_id(f"0{root}_{variant}")
        assert parent.target_well_id != child.target_well_id
        assert child.base_well_id == parent.base_well_id
        assert child.target_well_id == f"{root}_{variant}"


def test_sequential_zbs_suffix_is_preserved_without_assuming_event_number() -> None:
    normalized = normalize_well_id("051_ЗБС2")

    assert normalized.base_well_id == "51"
    assert normalized.target_well_id == "51_ЗБС2"
    assert normalized.recognized_variant is None


@pytest.mark.parametrize("value", ["ПК₁", "ПК-1", "ПК 1"])
def test_plast_cosmetic_variants_match(value: str) -> None:
    assert normalize_plast(value) == "ПК1"


def test_plast_numeric_components_remain_significant() -> None:
    assert normalize_plast("ПК-19-2") == normalize_plast("ПК19(2)")
    assert normalize_plast("ПК-19-2") != normalize_plast("ПК19-20")


def test_actual_lha_superscript_plast_is_supported() -> None:
    assert normalize_plast("ПК₁₉²") == "ПК19-2"
