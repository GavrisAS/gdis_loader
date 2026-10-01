from __future__ import annotations

from pathlib import Path

import pytest

import gdis_loader.cli as cli
from gdis_loader.domain.models import DiagnosticIssue, IssueSeverity, LoadReport
from gdis_loader.service import ServiceResult


def test_validate_parser_accepts_log_path() -> None:
    args = cli.build_parser().parse_args(
        [
            "validate",
            "--calculator",
            "calculator.xlsx",
            "--fund",
            "fund.xlsx",
            "--gdi",
            "gdi.xlsx",
            "--lha",
            "lha.xlsm",
            "--daily-report",
            "daily.xlsm",
            "--well-history",
            "well-history.xlsx",
            "--log",
            "custom.log",
        ]
    )

    assert args.log == Path("custom.log")


def test_cli_validate_returns_nonzero_for_error_result(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    report = LoadReport(
        timestamp="now",
        app_version="0.1",
        python_version="3.14.0",
        input_paths={},
    )
    report.issues.append(
        DiagnosticIssue(
            code="TEST_ERROR",
            severity=IssueSeverity.ERROR,
            message="ошибка",
        )
    )
    captured: dict[str, Path | None] = {}

    def fake_validate(_paths, log_path):  # type: ignore[no-untyped-def]
        captured["log"] = log_path
        return ServiceResult(report)

    monkeypatch.setattr(cli, "run_validate", fake_validate)
    with pytest.raises(SystemExit) as raised:
        cli.main(
            [
                "validate",
                "--calculator",
                "calculator.xlsx",
                "--fund",
                "fund.xlsx",
                "--gdi",
                "gdi.xlsx",
                "--lha",
                "lha.xlsm",
                "--daily-report",
                "daily.xlsm",
                "--well-history",
                "well-history.xlsx",
                "--log",
                "custom.log",
            ]
        )

    assert raised.value.code == 2
    assert captured["log"] == Path("custom.log")
    assert "Ошибок: 1" in capsys.readouterr().out
