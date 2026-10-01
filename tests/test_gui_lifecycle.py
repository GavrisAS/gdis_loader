from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication  # ty: ignore[unresolved-import, unused-ignore-comment]

import gdis_loader.gui.app as gui_app
from gdis_loader.domain.models import LoadReport, SourcePaths
from gdis_loader.progress import ProgressUpdate
from gdis_loader.service import ServiceResult


def _result() -> ServiceResult:
    return ServiceResult(
        LoadReport(
            timestamp="now",
            app_version="0.1",
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
        well_history=tmp_path / "well_history.xlsx",
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


def test_worker_progress_signal_updates_bar_and_reset_starts_at_zero(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    window = _window(monkeypatch)
    worker = gui_app._ServiceWorker(lambda _paths: _result(), _paths(tmp_path))
    worker.progress_changed.connect(window._progress_changed)
    window._operation = "Проверка файлов"

    worker._report_progress(ProgressUpdate(45, "Чтение ГДИ"))
    assert window._progress_bar.value() == 45

    window._progress_bar.setValue(83)
    window._reset_progress()
    assert window._progress_bar.value() == 0
    window.close()


def test_progress_bar_starts_after_update_button_and_reaches_right_edge(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    window = _window(monkeypatch)
    app = QApplication.instance()
    assert app is not None
    window.resize(820, 520)
    window.show()
    app.processEvents()

    validate_button = window._validate_button.geometry()
    update_button = window._update_button.geometry()
    progress_bar = window._progress_bar.geometry()
    button_gap = update_button.left() - validate_button.right() - 1
    progress_gap = progress_bar.left() - update_button.right() - 1
    central_widget = window.centralWidget()
    assert central_widget is not None
    outer_layout = central_widget.layout()
    assert outer_layout is not None
    actions_item = outer_layout.itemAt(1)
    assert actions_item is not None

    assert progress_gap == button_gap
    assert progress_bar.right() == actions_item.geometry().right()
    window.close()


@pytest.mark.parametrize(
    ("method_name", "operation"),
    (("_validate", "Проверка файлов"), ("_update", "Обновление данных")),
)
def test_start_resets_progress_when_config_persist_fails(
    monkeypatch, method_name: str, operation: str
) -> None:  # type: ignore[no-untyped-def]
    window = _window(monkeypatch)
    window._progress_bar.setValue(100)
    monkeypatch.setattr(window, "_persist_config", lambda **_kwargs: False)

    getattr(window, method_name)()

    assert window._progress_bar.value() == 0
    assert not window._busy
    assert window._thread is None
    assert window._operation is None
    assert operation not in window._status_box.toPlainText()
    window.close()


def test_start_resets_progress_when_log_preparation_fails(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class _MessageBox:
        @staticmethod
        def critical(*_args: object, **_kwargs: object) -> None:
            return None

    def _raise_path_error() -> SourcePaths:
        raise OSError("не удалось подготовить путь")

    monkeypatch.setattr(gui_app, "QMessageBox", _MessageBox)
    window = _window(monkeypatch)
    window._progress_bar.setValue(100)
    monkeypatch.setattr(window, "_persist_config", lambda **_kwargs: True)
    monkeypatch.setattr(window, "_paths", _raise_path_error)

    window._start(lambda _paths: _result(), "Проверка файлов")

    assert window._progress_bar.value() == 0
    assert not window._busy
    assert window._thread is None
    assert window._operation is None
    window.close()


def test_status_bar_contains_only_runtime_version(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    window = _window(monkeypatch)

    assert window.statusBar().currentMessage() == "Версия 0.1"
    assert "Александр Гаврись" not in window.statusBar().currentMessage()
    window.close()


def test_well_history_has_browse_field_and_persists_selected_path(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    selected = str(tmp_path / "База по скважинам.xlsx")
    persisted = []
    monkeypatch.setattr(
        gui_app.QFileDialog,
        "getOpenFileName",
        lambda *_args: (selected, "Excel workbook (*.xlsx)"),
    )
    monkeypatch.setattr(gui_app, "save_config", lambda config, _path: persisted.append(config))
    window = _window(monkeypatch)

    assert "well_history" in window._fields
    window._browse("well_history")

    assert window._fields["well_history"].text() == selected
    assert len(persisted) == 1
    assert persisted[0].well_history == selected
    window.close()
