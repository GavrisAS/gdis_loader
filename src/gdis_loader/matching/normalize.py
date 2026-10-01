"""Conservative, testable normalization helpers for wells, fields, and plastics."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_SPACE_RE = re.compile(r"\s+")
_NUMERIC_RE = re.compile(r"^(?P<digits>\d+)(?:\.0+)?$")
_KNOWN_VARIANT_RE = re.compile(r"^(ЗБС|ПВЛГ|КЛК|МЗС|ГС)(?:$|[ _(\-](?!\d).*)$", re.IGNORECASE)
_UNDERSCORE_SUFFIX_RE = re.compile(r"^(?P<number>\d+)\s*_\s*(?P<suffix>.+)$")
_SPACE_VARIANT_RE = re.compile(
    r"^(?P<number>\d+)\s+(?P<suffix>(?:ЗБС|ПВЛГ|КЛК|МЗС|ГС)(?=$|[\s_\d(]).*)$",
    re.IGNORECASE,
)
_GAS_BRANCH_RE = re.compile(r"^(?P<number>\d+)\s+ГС(?:$|[\s_(\d]).*$", re.IGNORECASE)
_PLAST_PREFIX_RE = re.compile(r"^(?P<prefix>[А-ЯA-Z]+)\s*-\s*(?=\d)")
_PLAST_SPACE_RE = re.compile(r"^(?P<prefix>[А-ЯA-Z]+)\s+(?=\d)")
_PLAST_PAREN_RE = re.compile(r"^(?P<prefix>[А-ЯA-Z]+)(?P<base>\d+)[(/](?P<part>\d+)\)?$")

_SUBSCRIPT_DIGITS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_SUPERSCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


@dataclass(frozen=True, slots=True)
class NormalizedWell:
    """Physical root and distinct normalized target/lifecycle identity."""

    raw: str
    base_well_id: str | None
    target_well_id: str | None = None
    recognized_variant: str | None = None


def _clean_text(value: object) -> str:
    text = str(value).replace("\u00a0", " ").strip()
    return _SPACE_RE.sub(" ", text)


def _numeric_text(text: str) -> str | None:
    match = _NUMERIC_RE.fullmatch(text)
    if match is None:
        return None
    return str(int(match.group("digits")))


def normalize_well_id(value: object) -> NormalizedWell:
    """Normalize leading zeroes while keeping target identities distinct.

    ``base_well_id`` is the numeric physical root used only for lineage
    searches. ``target_well_id`` retains every suffix, including ЗБС, ПВЛГ,
    КЛК, МЗС, and unfamiliar suffixes. Matching must use the latter.
    """

    raw = _clean_text(value)
    if not raw:
        return NormalizedWell(raw=raw, base_well_id=None, target_well_id=None)

    numeric = _numeric_text(raw)
    if numeric is not None:
        return NormalizedWell(raw=raw, base_well_id=numeric, target_well_id=numeric)

    upper = raw.upper()
    variant = _SPACE_VARIANT_RE.fullmatch(upper)
    suffix_match = _UNDERSCORE_SUFFIX_RE.fullmatch(upper)
    if variant is not None or suffix_match is not None:
        match = variant or suffix_match
        assert match is not None
        number = str(int(match.group("number")))
        suffix = match.group("suffix").strip()
        canonical_suffix = _SPACE_RE.sub(" ", suffix)
        known_variant = _KNOWN_VARIANT_RE.match(canonical_suffix)
        return NormalizedWell(
            raw=raw,
            base_well_id=number,
            target_well_id=f"{number}_{canonical_suffix}",
            recognized_variant=known_variant.group(1).upper() if known_variant else None,
        )

    # Keep nonnumeric identifiers whole. The old gas-branch spelling is
    # normalized as a distinct target identity while retaining its root.
    gas_branch = _GAS_BRANCH_RE.fullmatch(upper)
    if gas_branch is not None:
        number = str(int(gas_branch.group("number")))
        return NormalizedWell(
            raw=raw,
            base_well_id=number,
            target_well_id=f"{number}_ГС",
            recognized_variant="ГС",
        )
    return NormalizedWell(raw=raw, base_well_id=upper, target_well_id=upper)


_FIELD_ALIASES = {
    "береговой": "береговое",
    "береговое": "береговое",
    "пырейный": "пырейное",
    "пырейное": "пырейное",
    "хадырьяхинский": "хадырьяхинское",
    "хадырьяхинское": "хадырьяхинское",
}


def normalize_field_name(value: object) -> str:
    """Normalize only explicit field aliases and harmless whitespace/case."""

    text = _clean_text(value).casefold()
    return _FIELD_ALIASES.get(text, text)


def _replace_plast_digits(text: str) -> str:
    result: list[str] = []
    for character in text:
        if character in "₀₁₂₃₄₅₆₇₈₉":
            result.append(character.translate(_SUBSCRIPT_DIGITS))
        elif character in "⁰¹²³⁴⁵⁶⁷⁸⁹":
            # Actual LHA data uses ПК₁₉²; the superscript denotes the
            # sub-object and is therefore an explicit hyphenated component.
            result.append("-" + character.translate(_SUPERSCRIPT_DIGITS))
        else:
            result.append(character)
    return "".join(result)


def normalize_plast(value: object) -> str | None:
    """Canonicalize cosmetic plastic spelling without collapsing objects.

    ``ПК1``, ``ПК-1``, ``ПК 1`` and ``ПК₁`` become ``ПК1``.  Hyphens between
    numeric components remain significant, so ``ПК-19-2`` and ``ПК19-20``
    remain different values.
    """

    if value is None:
        return None
    text = _clean_text(value)
    if not text:
        return None
    text = _replace_plast_digits(text)
    text = unicodedata.normalize("NFKC", text).upper()
    text = text.replace("–", "-").replace("—", "-")
    text = _SPACE_RE.sub(" ", text)
    text = re.sub(r"\s*([\-+/()])\s*", r"\1", text)
    text = _PLAST_PREFIX_RE.sub(r"\g<prefix>", text)
    text = _PLAST_SPACE_RE.sub(r"\g<prefix>", text)
    parenthesized = _PLAST_PAREN_RE.fullmatch(text)
    if parenthesized is not None:
        text = (
            f"{parenthesized.group('prefix')}{parenthesized.group('base')}"
            f"-{parenthesized.group('part')}"
        )
    return text


def extract_exact_plast_hint(object_name: str) -> str | None:
    """Extract only a clearly named ПК object from a fund group label."""

    match = re.search(r"\((?P<plast>[^()]*)\)", object_name)
    if match is None:
        return None
    candidate = normalize_plast(match.group("plast"))
    if candidate is None or not re.fullmatch(r"ПК\d+(?:-\d+)*", candidate):
        return None
    return candidate
