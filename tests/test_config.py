from __future__ import annotations

from pathlib import Path

from gdis_loader.config import AppConfig, load_config, save_config


def test_missing_config_starts_with_empty_values(tmp_path: Path) -> None:
    result = load_config(tmp_path / "config.toml")

    assert result.config == AppConfig()
    assert result.warning is None


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

    result = load_config(path)

    assert result.warning is not None
    assert result.config == AppConfig()
    assert result.corrupt_backup is not None
    assert result.corrupt_backup.read_text(encoding="utf-8") == original
    assert path.read_text(encoding="utf-8") == original
