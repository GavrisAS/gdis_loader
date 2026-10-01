from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication  # ty: ignore[unresolved-import, unused-ignore-comment]

import gdis_loader.gui.app as gui_app
from gdis_loader.domain.models import DiagnosticIssue, IssueSeverity, LoadReport, SourcePaths
from gdis_loader.progress import ProgressUpdate
from gdis_loader.service import ServiceResult


def _result(fields: tuple[str, ...] = ()) -> ServiceResult:
    return ServiceResult(
        LoadReport(
            timestamp="now",
            app_version="0.1",
            python_version="3.14.0",
            input_paths={},
            available_fields=fields,
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
        research_status=tmp_path / "research_status.xlsx",
        output=tmp_path / "result.xlsx",
    )


def _window(monkeypatch) -> gui_app.LoaderWindow:  # type: ignore[no-untyped-def]
    app = QApplication.instance() or QApplication([])
    isolated_config = Path("/tmp") / f"gdis-loader-gui-test-{id(monkeypatch)}.toml"
    monkeypatch.setattr(gui_app, "config_path", lambda: isolated_config)
    window = gui_app.LoaderWindow()
    assert app is not None
    return window


def test_worker_result_does_not_release_busy_before_thread_finished(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    window = _window(monkeypatch)
    thread = gui_app.QThread(window)
    worker = gui_app._ServiceWorker(lambda _paths, _progress: _result(), _paths(tmp_path))
    window._thread = thread
    window._worker = worker
    window._operation = "Проверка файлов"
    window._set_busy(True)

    window._finish_success(_result())

    assert window._busy
    assert window._thread is thread
    assert all(not button.isEnabled() for button in window._buttons)

    window._start(
        lambda _paths, _progress: _result(),
        "Повторная операция",
        operation_kind="validate",
    )

    assert window._thread is thread
    assert window._operation == "Проверка файлов"

    window._thread_finished(thread)

    assert not window._busy
    assert window._thread is None
    assert window._worker is None
    assert window._validate_button.isEnabled()
    assert not window._update_button.isEnabled()
    assert all(button.isEnabled() for button in window._browse_buttons)
    window.close()


def test_stale_thread_cannot_clear_new_operation(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    window = _window(monkeypatch)
    old_thread = gui_app.QThread(window)
    new_thread = gui_app.QThread(window)
    new_worker = gui_app._ServiceWorker(lambda _paths, _progress: _result(), _paths(tmp_path))
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
    worker = gui_app._ServiceWorker(lambda _paths, _progress: _result(), _paths(tmp_path))
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
    worker = gui_app._ServiceWorker(lambda _paths, _progress: _result(), _paths(tmp_path))
    worker.progress_changed.connect(window._progress_changed)
    window._operation = "Проверка файлов"

    worker._report_progress(ProgressUpdate(45, "Чтение ГДИ"))
    assert window._progress_bar.value() == 45

    window._progress_bar.setValue(83)
    window._reset_progress()
    assert window._progress_bar.value() == 0
    window.close()


def test_progress_bar_uses_full_width_row_below_actions(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    window = _window(monkeypatch)
    app = QApplication.instance()
    assert app is not None
    window.resize(820, 520)
    window.show()
    app.processEvents()

    validate_button = window._validate_button.geometry()
    combo = window._field_combo.geometry()
    update_button = window._update_button.geometry()
    progress_bar = window._progress_bar.geometry()
    central_widget = window.centralWidget()
    assert central_widget is not None
    outer_layout = central_widget.layout()
    assert outer_layout is not None
    actions_item = outer_layout.itemAt(2)
    assert actions_item is not None

    assert validate_button.right() < combo.left() < combo.right() < update_button.left()
    assert progress_bar.left() == outer_layout.contentsMargins().left()
    assert progress_bar.right() == (
        central_widget.width() - outer_layout.contentsMargins().right() - 1
    )
    assert progress_bar.top() > actions_item.geometry().bottom()
    assert window._status_box.geometry().top() > progress_bar.bottom()
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
    if method_name == "_update":
        window._available_fields = ("Береговое",)
        window._field_combo.addItem("Береговое")
        window._field_combo.setCurrentIndex(0)
        window._validation_fingerprint = window._source_fingerprint()
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

    window._start(
        lambda _paths, _progress: _result(),
        "Проверка файлов",
        operation_kind="validate",
    )

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


def test_initial_field_selection_controls_are_disabled(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    window = _window(monkeypatch)

    assert not window._field_combo.isEnabled()
    assert window._field_combo.currentIndex() == -1
    assert not window._update_button.isEnabled()

    window.close()


def test_validation_populates_fields_without_selecting_one(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    window = _window(monkeypatch)
    window._operation_kind = "validate"
    window._active_fingerprint = window._source_fingerprint()

    window._finish_success(_result(("Береговое", "Пырейное")))

    assert window._field_combo.isEnabled()
    assert window._available_fields == ("Береговое", "Пырейное")
    assert window._field_combo.currentIndex() == -1
    assert not window._update_button.isEnabled()

    window.close()


def test_successful_validation_with_no_fields_keeps_controls_disabled(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    window = _window(monkeypatch)
    window._operation_kind = "validate"
    window._active_fingerprint = window._source_fingerprint()

    window._finish_success(_result())

    assert not window._field_combo.isEnabled()
    assert window._field_combo.count() == 0
    assert not window._update_button.isEnabled()
    assert "не обнаружены" in window._status_box.toPlainText()
    window.close()


def test_revalidation_clears_previous_fields_before_start(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    window = _window(monkeypatch)
    window._operation_kind = "validate"
    window._active_fingerprint = window._source_fingerprint()
    window._finish_success(_result(("Береговое",)))
    window._field_combo.setCurrentIndex(0)
    assert window._update_button.isEnabled()
    monkeypatch.setattr(window, "_start", lambda *_args, **_kwargs: None)

    window._validate()

    assert window._field_combo.count() == 0
    assert not window._field_combo.isEnabled()
    assert window._field_combo.currentIndex() == -1
    assert not window._update_button.isEnabled()
    window.close()


def test_field_selection_enables_update_and_clearing_disables_it(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    window = _window(monkeypatch)
    window._operation_kind = "validate"
    window._active_fingerprint = window._source_fingerprint()
    window._finish_success(_result(("Береговое", "Пырейное")))

    window._field_combo.setCurrentIndex(0)
    assert window._update_button.isEnabled()
    window._field_combo.setCurrentIndex(-1)
    assert not window._update_button.isEnabled()

    window.close()


@pytest.mark.parametrize(
    "source_key",
    ("calculator", "fund", "gdi", "lha", "daily_report", "well_history", "research_status"),
)
def test_path_changes_invalidate_fields_but_output_change_does_not(
    monkeypatch, source_key: str
) -> None:  # type: ignore[no-untyped-def]
    window = _window(monkeypatch)
    window._operation_kind = "validate"
    window._active_fingerprint = window._source_fingerprint()
    window._finish_success(_result(("Береговое",)))
    window._field_combo.setCurrentIndex(0)
    assert window._update_button.isEnabled()

    window._fields["output"].setText("new-result.xlsx")
    assert window._field_combo.isEnabled()
    assert window._field_combo.currentText() == "Береговое"
    assert window._update_button.isEnabled()

    window._fields[source_key].setText(f"changed-{source_key}.xlsx")
    assert not window._field_combo.isEnabled()
    assert window._field_combo.count() == 0
    assert not window._update_button.isEnabled()
    assert window._validation_fingerprint is None

    window.close()


def test_validation_failure_leaves_selection_disabled(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class _MessageBox:
        @staticmethod
        def critical(*_args: object, **_kwargs: object) -> None:
            return None

    monkeypatch.setattr(gui_app, "QMessageBox", _MessageBox)
    window = _window(monkeypatch)
    window._operation_kind = "validate"
    window._active_fingerprint = window._source_fingerprint()
    window._finish_success(_result(("Береговое",)))
    window._field_combo.setCurrentIndex(0)
    assert window._update_button.isEnabled()

    error_result = _result(("Береговое",))
    error_result.report.issues.append(
        DiagnosticIssue(
            code="PATH_NOT_FOUND",
            severity=IssueSeverity.ERROR,
            message="missing",
        )
    )
    window._operation_kind = "validate"
    window._finish_success(error_result)

    assert not window._field_combo.isEnabled()
    assert window._field_combo.count() == 0
    assert not window._update_button.isEnabled()

    window.close()


def test_update_passes_exactly_selected_field_to_service(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    window = _window(monkeypatch)
    window._available_fields = ("Пырейное",)
    window._field_combo.addItem("Пырейное")
    window._validation_fingerprint = window._source_fingerprint()
    window._field_combo.setCurrentIndex(0)
    captured: list[str] = []

    def fake_run_update(
        _paths: SourcePaths,
        *,
        progress=None,
        target_field: str,
    ) -> ServiceResult:
        captured.append(target_field)
        return _result()

    monkeypatch.setattr(gui_app, "run_update", fake_run_update)
    actions = []
    monkeypatch.setattr(
        window,
        "_start",
        lambda action, _operation, **_kwargs: actions.append(action),
    )

    window._update()
    assert len(actions) == 1
    actions[0](_paths(Path("/tmp")), lambda _update: None)

    assert captured == ["Пырейное"]
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
