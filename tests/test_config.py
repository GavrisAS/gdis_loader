from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from gdis_loader.config import (
    AppConfig,
    ConfigValidationError,
    CriteriaConfig,
    load_config,
    save_config,
)


def test_missing_config_starts_with_empty_values(tmp_path: Path) -> None:
    result = load_config(tmp_path / "config.toml")

    assert result.config == AppConfig()
    assert result.warning is None


def test_criteria_config_is_an_immutable_update_snapshot() -> None:
    snapshot = CriteriaConfig(gdm_abs_delta_threshold=7.0)

    with pytest.raises(FrozenInstanceError):
        snapshot.gdm_abs_delta_threshold = 8.0  # ty: ignore[invalid-assignment]


def test_config_round_trip_preserves_unicode_and_windows_style_paths(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    config = AppConfig(
        calculator=r"C:\Данные\GDIS_Rating_Calculator_FIXED.xlsx",
        fund="/tmp/Фонд 2026.xlsx",
        gdi="Сводная таблица ГДИ.xlsx",
        lha="База ЛХА_Итог!.xlsm",
        daily_report="07.2026 рапорт.xlsm",
        well_history="База по скважинам.xlsx",
        output="Результат.xlsx",
        last_directory="C:\\Данные",
    )

    save_config(config, path)
    result = load_config(path)

    assert result.config == config


def test_config_save_uses_atomic_replace(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "config.toml"
    calls: list[tuple[str, str]] = []

    import gdis_loader.config as config_module

    real_replace = config_module.os.replace

    def record_replace(source: str, destination: str) -> None:
        calls.append((source, destination))
        real_replace(source, destination)

    monkeypatch.setattr(config_module.os, "replace", record_replace)
    save_config(AppConfig(calculator="тест.xlsx"), path)

    assert len(calls) == 1
    assert Path(calls[0][1]) == path
    assert Path(calls[0][0]).name != path.name
    assert path.read_text(encoding="utf-8").startswith("[files]")


def test_corrupt_config_is_explained_and_backed_up(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    original = "[files\ncalculator = 'broken'"
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ConfigValidationError, match="Некорректный TOML"):
        load_config(path)

    backup = next(tmp_path.glob("config.toml.corrupt-*.bak"))
    assert backup.read_text(encoding="utf-8") == original
    assert path.read_text(encoding="utf-8") == original


def test_missing_or_partial_criteria_sections_use_documented_defaults(tmp_path: Path) -> None:
    missing = load_config(tmp_path / "missing.toml")
    assert missing.config.criteria == CriteriaConfig()

    path = tmp_path / "partial.toml"
    path.write_text(
        "[criteria.insufficient_gdi]\nmin_count = 3\n[criteria.gdm]\nfallback_max_age_days = 30\n",
        encoding="utf-8",
    )
    criteria = load_config(path).config.criteria

    assert criteria.insufficient_gdi_min_count == 3
    assert criteria.gdm_fallback_max_age_days == 30
    assert criteria.chlorine_current_min_mg_dm3 == 2000.0
    assert criteria.productivity_min_increase == 0.0


@pytest.mark.parametrize(
    ("toml_value", "section", "key", "message"),
    [
        ("nan", "downhole", "depth_threshold_m", "downhole_depth_threshold_m"),
        ("inf", "chlorine_growth", "delta_min_mg_dm3", "chlorine_delta_min_mg_dm3"),
        ("-1", "gdm", "abs_delta_threshold", "gdm_abs_delta_threshold"),
        ("-1", "gas_rate", "working_day_min_rate", "gas_rate_working_day_min_rate"),
        ("-1", "productivity_decline", "min_increase", "productivity_min_increase"),
        ("0", "insufficient_gdi", "min_count", "insufficient_gdi_min_count"),
        ("1.5", "insufficient_gdi", "min_count", "insufficient_gdi_min_count"),
        ("-1", "gdm", "fallback_max_age_days", "gdm_fallback_max_age_days"),
        ('"abc"', "chlorine_growth", "current_min_mg_dm3", "chlorine_current_min_mg_dm3"),
    ],
)
def test_present_invalid_criteria_value_is_an_explicit_error(
    tmp_path: Path, toml_value: str, section: str, key: str, message: str
) -> None:
    path = tmp_path / "invalid.toml"
    path.write_text(
        f"[criteria.{section}]\n{key} = {toml_value}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match=message):
        load_config(path)


def test_invalid_criteria_error_keeps_valid_path_settings_available(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    original = (
        '[files]\ncalculator = "calc.xlsx"\nfund = "fund.xlsx"\n'
        '[ui]\nlast_directory = "source-directory"\n'
        "[criteria.gdm]\nabs_delta_threshold = -1\n"
    )
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ConfigValidationError) as captured:
        load_config(path)

    partial = captured.value.partial_config
    assert partial is not None
    assert partial.calculator == "calc.xlsx"
    assert partial.fund == "fund.xlsx"
    assert partial.last_directory == "source-directory"
    repaired = AppConfig(
        calculator=partial.calculator,
        fund=partial.fund,
        gdi=partial.gdi,
        lha=partial.lha,
        daily_report=partial.daily_report,
        well_history=partial.well_history,
        research_status=partial.research_status,
        output=partial.output,
        last_directory=partial.last_directory,
        criteria=CriteriaConfig(),
        criteria_explicit_fields=frozenset(CriteriaConfig().as_dict()),
        preserved_settings=partial.preserved_settings,
    )
    save_config(repaired, path)

    result = load_config(path).config
    assert result.calculator == "calc.xlsx"
    assert result.fund == "fund.xlsx"


def test_criteria_save_preserves_other_path_and_setting_sections(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[files]\ncalculator = "calc.xlsx"\nfund = "fund.xlsx"\n'
        '[ui]\nlast_directory = "custom"\n'
        '[other]\nkeep = "value"\n',
        encoding="utf-8",
    )
    loaded = load_config(path).config
    changed = AppConfig(
        **{
            name: getattr(loaded, name)
            for name in (
                "calculator",
                "fund",
                "gdi",
                "lha",
                "daily_report",
                "well_history",
                "research_status",
                "output",
                "last_directory",
            )
        },
        criteria=CriteriaConfig(gdm_abs_delta_threshold=7.0),
        criteria_explicit_fields=frozenset(CriteriaConfig().as_dict()),
        preserved_settings=loaded.preserved_settings,
    )

    save_config(changed, path)
    result = load_config(path).config

    assert result.calculator == "calc.xlsx"
    assert result.fund == "fund.xlsx"
    assert result.last_directory == "custom"
    assert result.preserved_settings["other"] == {"keep": "value"}
    assert result.criteria == CriteriaConfig(gdm_abs_delta_threshold=7.0)
    assert result.criteria_explicit_fields == frozenset(CriteriaConfig().as_dict())


def test_old_explicit_gdm_window_is_preserved_and_missing_uses_new_default(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[criteria.gdm]\nfallback_max_age_days = 365\n", encoding="utf-8")
    assert load_config(path).config.criteria.gdm_fallback_max_age_days == 365
    path.write_text("[criteria.gdm]\nabs_delta_threshold = 5\n", encoding="utf-8")
    assert load_config(path).config.criteria.gdm_fallback_max_age_days == 730
