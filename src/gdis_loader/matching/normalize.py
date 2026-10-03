"""Conservative, testable normalization helpers for wells, fields, and plastics."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_SPACE_RE = re.compile(r"\s+")
_NUMERIC_RE = re.compile(r"^(?P<digits>\d+)(?:\.0+)?$")
_WELL_VARIANT_RE = re.compile(
    r"^(?P<number>\d+)[ _-]*(?P<family>ЗБС|ПВЛГ|ПНЛГ|ПВР|КЛК|МЗС|ГС)"
    r"(?P<tail>(?:\s*\d+)?(?:$|[ _(\-].*))$",
    re.IGNORECASE,
)
_UNDERSCORE_SUFFIX_RE = re.compile(r"^(?P<number>\d+)\s*_\s*(?P<suffix>.+)$")
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
    ordinal: int | None = None
    annotation: str | None = None

    @property
    def separate_identity(self) -> bool:
        """GS/MZS never share the mother-well identity."""
        return self.recognized_variant in {"ГС", "МЗС"}


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
    variant = _WELL_VARIANT_RE.fullmatch(upper)
    if variant is not None:
        number = str(int(variant.group("number")))
        family = variant.group("family")
        tail = variant.group("tail").strip()
        explicit = re.fullmatch(r"\d*", tail)
        ordinal = (int(tail) if tail else 1) if explicit is not None else None
        annotation = None if explicit is not None else tail.strip(" _-")
        suffix = family
        if explicit is not None:
            if tail and (family != "ЗБС" or ordinal != 1):
                suffix += str(ordinal)
        elif annotation:
            suffix += annotation if annotation.startswith("(") else "_" + annotation
        return NormalizedWell(
            raw=raw,
            base_well_id=number,
            target_well_id=f"{number}_{suffix}",
            recognized_variant=family,
            ordinal=ordinal,
            annotation=annotation,
        )
    suffix_match = _UNDERSCORE_SUFFIX_RE.fullmatch(upper)
    if suffix_match is not None:
        number = str(int(suffix_match.group("number")))
        return NormalizedWell(
            raw=raw,
            base_well_id=number,
            target_well_id=f"{number}_{suffix_match.group('suffix').strip()}",
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
    """Canonicalize primary plast numbers and discard subordinate suffixes.

    A one-digit hyphen component is a sublayer (``ПК17-2-1`` -> ``ПК17``).
    A two-or-more digit hyphen component is a second primary plast
    (``ПК19-20`` -> ``ПК19+20``). Comma/plus separated values are parsed one
    primary at a time and returned in stable numeric order.
    """

    if value is None:
        return None
    text = _clean_text(value)
    if not text:
        return None
    text = unicodedata.normalize("NFKC", _replace_plast_digits(text)).upper()
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    text = _SPACE_RE.sub(" ", text)
    text = re.sub(r"\s*([,+/()\-])\s*", r"\1", text)
    text = _PLAST_PREFIX_RE.sub(r"\g<prefix>", text)
    text = _PLAST_SPACE_RE.sub(r"\g<prefix>", text)
    if text.startswith("ПК"):
        primary = _primary_pc_numbers(text)
        if primary:
            ordered = sorted(set(primary))
            return "ПК" + "+".join(str(number) for number in ordered)
    parenthesized = _PLAST_PAREN_RE.fullmatch(text)
    if parenthesized is not None:
        text = f"{parenthesized.group('prefix')}{parenthesized.group('base')}"
    return text


def _primary_pc_numbers(text: str) -> list[int]:
    numbers: list[int] = []
    for component in re.split(r"[+,]", text):
        match = re.match(r"^(?:ПК)?(?P<primary>\d+)(?P<tail>.*)$", component)
        if match is None:
            continue
        numbers.append(int(match.group("primary")))
        tail = match.group("tail")
        composite = re.match(r"^-(?P<primary>\d{2,})(?:-|$)", tail)
        if composite is not None:
            numbers.append(int(composite.group("primary")))
    return numbers


def extract_exact_plast_hint(object_name: str) -> str | None:
    """Extract only a clearly named ПК object from a fund group label."""

    from gdis_loader.matching.fund_scope import parse_fund_object_scope

    return parse_fund_object_scope(object_name).exact_plast
