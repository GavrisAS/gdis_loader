from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import gdis_loader.service as service
from gdis_loader.domain.models import (
    DiagnosticIssue,
    FundParseResult,
    IssueSeverity,
    SourcePaths,
    WellHistoryParseResult,
)
from gdis_loader.excel.writer import TargetWriteResult
from gdis_loader.progress import ProgressUpdate
from gdis_loader.validation.sources import ValidationResult


def _paths(tmp_path: Path) -> SourcePaths:
    return SourcePaths(
        calculator=tmp_path / "calculator.xlsx",
        fund=tmp_path / "fund.xlsx",
        gdi=tmp_path / "gdi.xlsx",
        lha=tmp_path / "lha.xlsm",
        daily_report=tmp_path / "daily.xlsm",
        well_history=tmp_path / "well_history.xlsx",
        research_status=tmp_path / "research_status.xlsx",
        output=tmp_path / "result.xlsx",
    )


def _stub_pipeline(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        service,
        "validate_inputs",
        lambda _paths, *_args: ValidationResult((), ("Береговое",)),
    )
    monkeypatch.setattr(
        service,
        "read_fund",
        lambda _path: FundParseResult((), None, None),
    )
    monkeypatch.setattr(service, "read_gdi", lambda _path: ((), ()))
    monkeypatch.setattr(service, "read_lha", lambda _path: ((), ()))
    monkeypatch.setattr(service, "read_daily_report", lambda _path: ((), ()))
    monkeypatch.setattr(service, "read_research_status", lambda *_args: ((), ()))
    monkeypatch.setattr(service, "read_well_history", lambda *_args: WellHistoryParseResult(()))
    monkeypatch.setattr(service, "_build_target_rows", lambda *_args: ())


def test_validate_progress_is_monotonic_and_reaches_completion(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _stub_pipeline(monkeypatch)
    updates: list[ProgressUpdate] = []

    service.run_validate(_paths(tmp_path), progress=updates.append)

    assert [update.percent for update in updates] == [0, 10, 90, 100]
    assert all(left.percent <= right.percent for left, right in pairwise(updates))
    assert updates[-1].stage == "Проверка завершена"


def test_update_progress_reports_writer_checkpoint_and_completion(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    _stub_pipeline(monkeypatch)
    monkeypatch.setattr(
        service,
        "write_target_rows",
        lambda _source, output, _rows: TargetWriteResult(output, 0),
    )
    updates: list[ProgressUpdate] = []

    service.run_update(
        _paths(tmp_path),
        target_field="Береговое",
        progress=updates.append,
    )

    assert [update.percent for update in updates] == [
        0,
        10,
        20,
        30,
        45,
        60,
        68,
        72,
        75,
        85,
        90,
        95,
        100,
    ]
    assert updates[-2].stage == "Запись листа Данные"
    assert updates[-1].stage == "Обновление завершено"


def test_validate_error_does_not_report_completion(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        service,
        "validate_inputs",
        lambda _paths, *_args: ValidationResult(
            (
                DiagnosticIssue(
                    code="TEST_ERROR",
                    severity=IssueSeverity.ERROR,
                    message="ошибка",
                ),
            )
        ),
    )
    updates: list[ProgressUpdate] = []

    result = service.run_validate(_paths(tmp_path), progress=updates.append)

    assert result.has_errors
    assert [update.percent for update in updates] == [0, 10, 90]
