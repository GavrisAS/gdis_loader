"""Helpers for comparing source counts with values in a generated workbook."""

from __future__ import annotations

from typing import Literal


def application_count_state(
    application_count: int | None, expected_count: int
) -> Literal["missing", "match", "mismatch"]:
    """Distinguish an absent count from a numeric zero during reconciliation."""

    if application_count is None:
        return "missing"
    return "match" if application_count == expected_count else "mismatch"
