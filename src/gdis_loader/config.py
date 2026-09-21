"""Persistent, atomic application configuration."""

from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import tomli_w

LOGGER = logging.getLogger(__name__)
CONFIG_FILENAME = "config.toml"


@dataclass(slots=True)
class AppConfig:
    """Last selected user paths and a small amount of UI state."""

    calculator: str = ""
    fund: str = ""
    gdi: str = ""
    lha: str = ""
    daily_report: str = ""
    output: str = ""
    last_directory: str = ""


@dataclass(frozen=True, slots=True)
class ConfigLoadResult:
    """Configuration plus a user-visible warning, if one was needed."""

    config: AppConfig
    warning: str | None = None
    corrupt_backup: Path | None = None


def repository_root(start: Path | None = None) -> Path:
    """Find the repository by walking from this package, not from cwd."""

    origin = (start or Path(__file__)).resolve()
    origin = origin if origin.is_dir() else origin.parent
    for candidate in (origin, *origin.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return origin


def config_path() -> Path:
    """Return the config location for source and frozen/PyInstaller runs."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / CONFIG_FILENAME
    return repository_root() / CONFIG_FILENAME


def _as_nonempty_string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _config_from_mapping(data: dict[str, Any]) -> AppConfig:
    files = data.get("files", {})
    ui = data.get("ui", {})
    if not isinstance(files, dict) or not isinstance(ui, dict):
        raise ValueError("секции [files] и [ui] должны быть таблицами")
    return AppConfig(
        calculator=_as_nonempty_string(files.get("calculator", "")),
        fund=_as_nonempty_string(files.get("fund", "")),
        gdi=_as_nonempty_string(files.get("gdi", "")),
        lha=_as_nonempty_string(files.get("lha", "")),
        daily_report=_as_nonempty_string(files.get("daily_report", "")),
        output=_as_nonempty_string(files.get("output", "")),
        last_directory=_as_nonempty_string(ui.get("last_directory", "")),
    )


def load_config(path: Path | None = None) -> ConfigLoadResult:
    """Load config, preserving a damaged TOML file and explaining the issue."""

    target = path or config_path()
    if not target.exists():
        return ConfigLoadResult(config=AppConfig())
    try:
        with target.open("rb") as stream:
            data = tomllib.load(stream)
        return ConfigLoadResult(config=_config_from_mapping(data))
    except (OSError, tomllib.TOMLDecodeError, TypeError, ValueError) as error:
        backup: Path | None = None
        try:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = target.with_name(f"{target.name}.corrupt-{stamp}.bak")
            counter = 1
            while backup.exists():
                backup = target.with_name(f"{target.name}.corrupt-{stamp}-{counter}.bak")
                counter += 1
            shutil.copy2(target, backup)
        except OSError as backup_error:
            LOGGER.warning(
                "Не удалось сохранить резервную копию поврежденного config: %s", backup_error
            )
        warning = f"Не удалось прочитать config.toml: {error}. Запущены пустые настройки."
        LOGGER.warning("%s", warning)
        return ConfigLoadResult(config=AppConfig(), warning=warning, corrupt_backup=backup)


def _config_mapping(config: AppConfig) -> dict[str, dict[str, str]]:
    return {
        "files": {
            "calculator": config.calculator,
            "fund": config.fund,
            "gdi": config.gdi,
            "lha": config.lha,
            "daily_report": config.daily_report,
            "output": config.output,
        },
        "ui": {"last_directory": config.last_directory},
    }


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    """Atomically save config using a sibling temporary file and replace."""

    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as stream:
            temporary_name = stream.name
            stream.write(tomli_w.dumps(_config_mapping(config)).encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, target)
    except OSError:
        if temporary_name:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                LOGGER.warning("Не удалось удалить временный config %s", temporary_name)
        raise
    return target
