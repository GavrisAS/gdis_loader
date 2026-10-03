from __future__ import annotations

import pytest

from gdis_loader.matching.fund_scope import parse_fund_object_scope
from gdis_loader.matching.normalize import extract_exact_plast_hint, normalize_plast


@pytest.mark.parametrize(
    "label,bounds", [("Береговой (ПК9-17)", (9, 17)), ("Береговой (ПК19-20)", (19, 20))]
)
def test_fund_range(label: str, bounds: tuple[int, int]) -> None:
    scope = parse_fund_object_scope(label)
    assert scope.plast_range == bounds
    assert scope.exact_plast is None
    assert extract_exact_plast_hint(label) is None


@pytest.mark.parametrize(
    "bounds,plast,expected",
    [
        ("9-17", "ПК17", True),
        ("9-17", "ПК14", True),
        ("9-17", "ПК14+15", True),
        ("9-17", "ПК19", False),
        ("19-20", "ПК19+20", True),
        ("19-20", "ПК18+19", False),
    ],
)
def test_membership(bounds: str, plast: str, expected: bool) -> None:
    assert parse_fund_object_scope(f"Береговой (ПК{bounds})").compatible(plast) is expected


def test_exact_parser_context_is_separate() -> None:
    assert normalize_plast("ПК19-20") == "ПК19+20"
    assert parse_fund_object_scope("Береговой (ПК19-20)").plast_range == (19, 20)
    assert normalize_plast("ПК19-20") == "ПК19+20"
