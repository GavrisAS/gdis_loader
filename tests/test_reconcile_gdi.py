from __future__ import annotations

import pytest

from gdis_loader.validation.reconciliation import application_count_state


@pytest.mark.parametrize(
    ("application_count", "expected_count", "state"),
    (
        (0, 1, "mismatch"),
        (0, 0, "match"),
        (None, 0, "missing"),
    ),
)
def test_application_count_state_preserves_numeric_zero(
    application_count: int | None,
    expected_count: int,
    state: str,
) -> None:
    assert application_count_state(application_count, expected_count) == state
