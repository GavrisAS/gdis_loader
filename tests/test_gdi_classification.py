from __future__ import annotations

import pytest

from gdis_loader.domain.models import GdiKind
from gdis_loader.transforms.gdi import classify_gdi_kind


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ИД", GdiKind.ID),
        (" ид  ", GdiKind.ID),
        ("ИД (индикаторная диаграмма)", GdiKind.ID),
        ("ИД+КВД", GdiKind.ID_KVD),
        ("ИД+КВД во время ПГИ", GdiKind.ID_KVD),
        ("ИД+КВДсм НКТ", GdiKind.ID_KVD),
        ("ИД+КВД освоение", GdiKind.ID_KVD),
        ("КВД", GdiKind.KVD),
        ("КВД статика", GdiKind.KVD),
        ("КВДстатика", GdiKind.KVD),
        ("КВДгл", GdiKind.KVD),
        ("КВД глубинн", GdiKind.KVD),
        ("КВД при ПГИ", GdiKind.KVD),
        ("КВД+КСД", GdiKind.KVD),
        ("миниКВД", GdiKind.KVD),
        ("КВД (MDT)", GdiKind.KVD),
        ("Освоение", GdiKind.EXCLUDED),
        ("Замер Рпл", GdiKind.EXCLUDED),
        ("Pст", GdiKind.EXCLUDED),
        ("Рстатика, запуск в экспл", GdiKind.EXCLUDED),
        ("ПГИ", GdiKind.UNKNOWN),
        ("КВУ", GdiKind.UNKNOWN),
        ("длит.остановка", GdiKind.UNKNOWN),
        ("МЗС+миниКВД", GdiKind.KVD),
        (None, GdiKind.UNKNOWN),
    ],
)
def test_gdi_classifier_handles_variations_without_losing_raw_label(
    raw: object, expected: GdiKind
) -> None:
    assert classify_gdi_kind(raw) is expected
