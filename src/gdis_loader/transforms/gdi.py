"""Classification helpers for raw GDI research type labels."""

from __future__ import annotations

import re
import unicodedata

from gdis_loader.domain.models import GdiKind

_ID_TOKEN = re.compile(r"(?<![0-9А-ЯA-Z])ИД(?![0-9А-ЯA-Z])")
_PRESSURE_ONLY = re.compile(r"(?<![0-9А-ЯA-Z])(?:P|Р)\s*(?:СТ(?:АТИК[А-Я]*)?|ПЛ)(?![0-9А-ЯA-Z])")


def classify_gdi_kind(raw_value: object) -> GdiKind:
    """Classify a raw label while retaining that label on its source record.

    Explanatory text can follow a recognized abbreviation. A combined ID/KVD
    label is detected before either individual kind. Pressure-only and
    development labels are excluded unless the same label explicitly includes
    an approved GDI kind.
    """

    if raw_value is None:
        return GdiKind.UNKNOWN
    text = unicodedata.normalize("NFKC", str(raw_value)).upper().strip()
    text = text.replace("Ё", "Е")
    text = re.sub(r"\s+", " ", text)
    has_id = _ID_TOKEN.search(text) is not None
    # KВД is a stable marker inside source labels such as ``КВДгл`` and
    # ``миниКВД``. The full marker avoids false positives such as ``КВУ``.
    has_kvd = "КВД" in text
    if has_id and has_kvd:
        return GdiKind.ID_KVD
    if has_id:
        return GdiKind.ID
    if has_kvd:
        return GdiKind.KVD
    if "ОСВОЕНИЕ" in text or _PRESSURE_ONLY.search(text) is not None:
        return GdiKind.EXCLUDED
    return GdiKind.UNKNOWN
