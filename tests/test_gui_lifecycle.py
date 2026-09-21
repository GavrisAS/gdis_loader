from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PySide6.QtWidgets import QApplication  # ty: ignore[unresolved-import, unused-ignore-comment]

import gdis_loader.gui.app as gui_app
from gdis_loader.domain.models import LoadReport, SourcePaths
from gdis_loader.service import ServiceResult


def _result() -> ServiceResult:
    return ServiceResult(
        LoadReport(
            timestamp="now",
            app_version="0.1.0",
            python_version="3.14.0",
            input_paths={},
        )
    )


def _paths(tmp_path: Path) -> SourcePaths:
    return SourcePaths(
        calculator=tmp_path / "calculator.xlsx",
        fund=tmp_path / "fund.xlsx",
        gdi=tmp_path / "gdi.xlsx",
        lha=tmp_path / "lha.xlsm",
        daily_report=tmp_path / "daily.xlsm",
        output=tmp_path / "result.xlsx",
    )


def _window(monkeypatch) -> gui_app.LoaderWindow:  # type: ignore[no-untyped-def]
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(gui_app, "config_path", lambda: Path("config.toml"))
    window = gui_app.LoaderWindow()
    assert app is not None
    return window


def test_worker_result_does_not_release_busy_before_thread_finished(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    window = _window(monkeypatch)
    thread = gui_app.QThread(window)
    worker = gui_app._ServiceWorker(lambda _paths: _result(), _paths(tmp_path))
    window._thread = thread
    window._worker = worker
    window._operation = "Проверка файлов"
    window._set_busy(True)

    window._finish_success(_result())

    assert window._busy
    assert window._thread is thread
    assert all(not button.isEnabled() for button in window._buttons)

    window._start(lambda _paths: _result(), "Повторная операция")

    assert window._thread is thread
    assert window._operation == "Проверка файлов"

    window._thread_finished(thread)

    assert not window._busy
    assert window._thread is None
    assert window._worker is None
    assert all(button.isEnabled() for button in window._buttons)
    window.close()


def test_stale_thread_cannot_clear_new_operation(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    window = _window(monkeypatch)
    old_thread = gui_app.QThread(window)
    new_thread = gui_app.QThread(window)
    new_worker = gui_app._ServiceWorker(lambda _paths: _result(), _paths(tmp_path))
    window._thread = new_thread
    window._worker = new_worker
    window._set_busy(True)

    window._thread_finished(old_thread)

    assert window._busy
    assert window._thread is new_thread
    assert window._worker is new_worker
    window._thread_finished(new_thread)
    window.close()


def test_worker_error_stays_busy_until_thread_finished(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    class _MessageBox:
        @staticmethod
        def critical(*_args: object, **_kwargs: object) -> None:
            return None

    monkeypatch.setattr(gui_app, "QMessageBox", _MessageBox)
    window = _window(monkeypatch)
    thread = gui_app.QThread(window)
    worker = gui_app._ServiceWorker(lambda _paths: _result(), _paths(tmp_path))
    window._thread = thread
    window._worker = worker
    window._operation = "Обновление данных"
    window._set_busy(True)

    window._finish_error("ошибка")

    assert window._busy
    assert window._thread is thread
    window._thread_finished(thread)
    assert not window._busy
    window.close()
