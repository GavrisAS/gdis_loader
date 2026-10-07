"""Persistent, atomic application configuration."""

from __future__ import annotations

import logging
import math
import os
import shutil
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict, cast

import tomli_w

LOGGER = logging.getLogger(__name__)
CONFIG_FILENAME = "config.toml"


class _CriteriaValues(TypedDict):
    insufficient_gdi_min_count: int
    productivity_min_increase: float
    chlorine_current_min_mg_dm3: float
    chlorine_delta_min_mg_dm3: float
    downhole_depth_threshold_m: float
    gdm_abs_delta_threshold: float
    gdm_fallback_max_age_days: int
    gas_rate_working_day_min_rate: float


@dataclass(frozen=True, slots=True)
class CriteriaConfig:
    """Immutable numeric thresholds used by one update operation."""

    insufficient_gdi_min_count: int = 2
    productivity_min_increase: float = 0.0
    chlorine_current_min_mg_dm3: float = 2000.0
    chlorine_delta_min_mg_dm3: float = 1000.0
    downhole_depth_threshold_m: float = 0.0
    gdm_abs_delta_threshold: float = 5.0
    gdm_fallback_max_age_days: int = 730
    gas_rate_working_day_min_rate: float = 0.0

    def __post_init__(self) -> None:
        integer_fields = {
            "insufficient_gdi_min_count": 1,
            "gdm_fallback_max_age_days": 0,
        }
        for name, minimum in integer_fields.items():
            value = getattr(self, name)
            if type(value) is not int or value < minimum:
                raise ConfigValidationError(f"{name}: требуется целое число >= {minimum}.")
        numeric_fields = {
            "productivity_min_increase": 0.0,
            "chlorine_current_min_mg_dm3": 0.0,
            "chlorine_delta_min_mg_dm3": 0.0,
            "downhole_depth_threshold_m": 0.0,
            "gdm_abs_delta_threshold": 0.0,
            "gas_rate_working_day_min_rate": 0.0,
        }
        for name, minimum in numeric_fields.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ConfigValidationError(f"{name}: требуется конечное число >= {minimum}.")
            if not math.isfinite(float(value)) or value < minimum:
                raise ConfigValidationError(f"{name}: требуется конечное число >= {minimum}.")

    def as_dict(self) -> dict[str, int | float]:
        return {
            "insufficient_gdi_min_count": self.insufficient_gdi_min_count,
            "productivity_min_increase": self.productivity_min_increase,
            "chlorine_current_min_mg_dm3": self.chlorine_current_min_mg_dm3,
            "chlorine_delta_min_mg_dm3": self.chlorine_delta_min_mg_dm3,
            "downhole_depth_threshold_m": self.downhole_depth_threshold_m,
            "gdm_abs_delta_threshold": self.gdm_abs_delta_threshold,
            "gdm_fallback_max_age_days": self.gdm_fallback_max_age_days,
            "gas_rate_working_day_min_rate": self.gas_rate_working_day_min_rate,
        }


class ConfigValidationError(ValueError):
    """A present config value cannot be safely applied."""

    def __init__(self, message: str, *, partial_config: AppConfig | None = None) -> None:
        super().__init__(message)
        self.partial_config = partial_config


@dataclass(slots=True)
class AppConfig:
    """Last selected user paths and a small amount of UI state."""

    calculator: str = ""
    fund: str = ""
    gdi: str = ""
    lha: str = ""
    daily_report: str = ""
    well_history: str = ""
    research_status: str = ""
    output: str = ""
    last_directory: str = ""
    criteria: CriteriaConfig = field(default_factory=CriteriaConfig)
    criteria_explicit_fields: frozenset[str] = field(
        default_factory=frozenset, compare=False, repr=False
    )
    preserved_settings: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


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
        raise ConfigValidationError("секции [files] и [ui] должны быть таблицами")
    partial_config = AppConfig(
        calculator=_as_nonempty_string(files.get("calculator", "")),
        fund=_as_nonempty_string(files.get("fund", "")),
        gdi=_as_nonempty_string(files.get("gdi", "")),
        lha=_as_nonempty_string(files.get("lha", "")),
        daily_report=_as_nonempty_string(files.get("daily_report", "")),
        well_history=_as_nonempty_string(files.get("well_history", "")),
        research_status=_as_nonempty_string(files.get("research_status", "")),
        output=_as_nonempty_string(files.get("output", "")),
        last_directory=_as_nonempty_string(ui.get("last_directory", "")),
        preserved_settings=data,
    )
    criteria_data = data.get("criteria", {})
    if not isinstance(criteria_data, dict):
        raise ConfigValidationError(
            "секция [criteria] должна быть таблицей",
            partial_config=partial_config,
        )
    defaults = CriteriaConfig()
    values = defaults.as_dict()
    explicit_fields: set[str] = set()
    section_fields = {
        "insufficient_gdi": {"min_count": "insufficient_gdi_min_count"},
        "productivity_decline": {"min_increase": "productivity_min_increase"},
        "chlorine_growth": {
            "current_min_mg_dm3": "chlorine_current_min_mg_dm3",
            "delta_min_mg_dm3": "chlorine_delta_min_mg_dm3",
        },
        "downhole": {"depth_threshold_m": "downhole_depth_threshold_m"},
        "gdm": {
            "abs_delta_threshold": "gdm_abs_delta_threshold",
            "fallback_max_age_days": "gdm_fallback_max_age_days",
        },
        "gas_rate": {"working_day_min_rate": "gas_rate_working_day_min_rate"},
    }
    for section_name, fields in section_fields.items():
        section = criteria_data.get(section_name, {})
        if not isinstance(section, dict):
            raise ConfigValidationError(
                f"[criteria.{section_name}] должна быть таблицей",
                partial_config=partial_config,
            )
        for config_key, attribute in fields.items():
            if config_key in section:
                values[attribute] = section[config_key]
                explicit_fields.add(attribute)
    try:
        criteria = CriteriaConfig(
            insufficient_gdi_min_count=cast(int, values["insufficient_gdi_min_count"]),
            productivity_min_increase=values["productivity_min_increase"],
            chlorine_current_min_mg_dm3=values["chlorine_current_min_mg_dm3"],
            chlorine_delta_min_mg_dm3=values["chlorine_delta_min_mg_dm3"],
            downhole_depth_threshold_m=values["downhole_depth_threshold_m"],
            gdm_abs_delta_threshold=values["gdm_abs_delta_threshold"],
            gdm_fallback_max_age_days=cast(int, values["gdm_fallback_max_age_days"]),
            gas_rate_working_day_min_rate=values["gas_rate_working_day_min_rate"],
        )
    except ConfigValidationError as error:
        raise ConfigValidationError(str(error), partial_config=partial_config) from error
    return AppConfig(
        calculator=partial_config.calculator,
        fund=partial_config.fund,
        gdi=partial_config.gdi,
        lha=partial_config.lha,
        daily_report=partial_config.daily_report,
        well_history=partial_config.well_history,
        research_status=partial_config.research_status,
        output=partial_config.output,
        last_directory=partial_config.last_directory,
        criteria=criteria,
        criteria_explicit_fields=frozenset(explicit_fields),
        preserved_settings=data,
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
    except OSError as error:
        raise ConfigValidationError(f"Не удалось прочитать config.toml: {error}") from error
    except tomllib.TOMLDecodeError as error:
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
        backup_note = f" Резервная копия: {backup}." if backup is not None else ""
        raise ConfigValidationError(
            f"Некорректный TOML в config.toml: {error}.{backup_note}"
        ) from error


def _config_mapping(config: AppConfig) -> dict[str, Any]:
    import copy

    mapping: dict[str, Any] = copy.deepcopy(config.preserved_settings)
    files = mapping.get("files", {})
    ui = mapping.get("ui", {})
    if not isinstance(files, dict):
        files = {}
    if not isinstance(ui, dict):
        ui = {}
    files.update(
        {
            "calculator": config.calculator,
            "fund": config.fund,
            "gdi": config.gdi,
            "lha": config.lha,
            "daily_report": config.daily_report,
            "well_history": config.well_history,
            "research_status": config.research_status,
            "output": config.output,
        }
    )
    ui["last_directory"] = config.last_directory
    mapping["files"] = files
    mapping["ui"] = ui

    criteria = mapping.get("criteria", {})
    if not isinstance(criteria, dict):
        criteria = {}
    field_locations = {
        "insufficient_gdi_min_count": ("insufficient_gdi", "min_count"),
        "productivity_min_increase": ("productivity_decline", "min_increase"),
        "chlorine_current_min_mg_dm3": ("chlorine_growth", "current_min_mg_dm3"),
        "chlorine_delta_min_mg_dm3": ("chlorine_growth", "delta_min_mg_dm3"),
        "downhole_depth_threshold_m": ("downhole", "depth_threshold_m"),
        "gdm_abs_delta_threshold": ("gdm", "abs_delta_threshold"),
        "gdm_fallback_max_age_days": ("gdm", "fallback_max_age_days"),
        "gas_rate_working_day_min_rate": ("gas_rate", "working_day_min_rate"),
    }
    values = config.criteria.as_dict()
    for attribute, (section_name, key) in field_locations.items():
        section = criteria.get(section_name, {})
        if not isinstance(section, dict):
            section = {}
        if attribute in config.criteria_explicit_fields:
            section[key] = values[attribute]
        else:
            section.pop(key, None)
        if section:
            criteria[section_name] = section
        elif section_name in criteria:
            del criteria[section_name]
    if criteria:
        mapping["criteria"] = criteria
    else:
        mapping.pop("criteria", None)
    return mapping


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
