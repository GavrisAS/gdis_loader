"""Command-line front end for the shared application service."""

from __future__ import annotations

import argparse
from pathlib import Path

from gdis_loader.domain.models import SourcePaths
from gdis_loader.service import ServiceError, default_output_path, run_update, run_validate


def _add_source_arguments(parser: argparse.ArgumentParser, *, output_required: bool) -> None:
    parser.add_argument("--calculator", required=True, type=Path, help="Исходный калькулятор .xlsx")
    parser.add_argument("--fund", required=True, type=Path, help="Фонд скважин .xlsx")
    parser.add_argument("--gdi", required=True, type=Path, help="Сводная таблица ГДИ .xlsx")
    parser.add_argument("--lha", required=True, type=Path, help="База ЛХА .xlsm")
    parser.add_argument("--daily-report", required=True, type=Path, help="Суточный рапорт .xlsm")
    parser.add_argument("--well-history", required=True, type=Path, help="База по скважинам .xlsx")
    parser.add_argument(
        "--output",
        required=output_required,
        type=Path,
        help="Файл результата .xlsx (для update обязателен)",
    )
    parser.add_argument("--log", type=Path, help="Путь текстового лога")


def _source_paths(namespace: argparse.Namespace) -> SourcePaths:
    if namespace.output:
        output = namespace.output
    elif namespace.command == "validate":
        output = Path("reports") / "gdis_loader-validation.xlsx"
    else:
        output = default_output_path(namespace.calculator)
    return SourcePaths(
        calculator=namespace.calculator,
        fund=namespace.fund,
        gdi=namespace.gdi,
        lha=namespace.lha,
        daily_report=namespace.daily_report,
        well_history=namespace.well_history,
        output=output,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Загрузчик данных ГДИС в калькулятор рейтингования"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser(
        "validate", help="проверить входные файлы и прочитать структуру"
    )
    _add_source_arguments(validate_parser, output_required=False)
    update_parser = subparsers.add_parser("update", help="создать копию калькулятора с данными")
    _add_source_arguments(update_parser, output_required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    paths = _source_paths(args)
    try:
        result = (
            run_validate(paths, args.log)
            if args.command == "validate"
            else run_update(paths, args.log)
        )
    except ServiceError as error:
        print(str(error))
        raise SystemExit(2) from error
    print(result.summary())
    if args.command == "validate" and result.has_errors:
        raise SystemExit(2)
