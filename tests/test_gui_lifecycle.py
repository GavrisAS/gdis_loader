from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6 import QtCore  # ty: ignore[unresolved-import, unused-ignore-comment]
from PySide6.QtWidgets import QApplication  # ty: ignore[unresolved-import, unused-ignore-comment]

import gdis_loader.gui.app as gui_app
from gdis_loader.config import AppConfig, CriteriaConfig, load_config, save_config
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
    criteria_button = window._criteria_button.geometry()
    update_button = window._update_button.geometry()
    progress_bar = window._progress_bar.geometry()
    central_widget = window.centralWidget()
    assert central_widget is not None
    outer_layout = central_widget.layout()
    assert outer_layout is not None
    actions_item = outer_layout.itemAt(2)
    assert actions_item is not None

    assert (
        validate_button.right()
        < combo.left()
        < combo.right()
        < criteria_button.left()
        < criteria_button.right()
        < update_button.left()
    )
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


def test_criteria_button_exists_idle_and_disables_while_busy(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    window = _window(monkeypatch)

    assert window._criteria_button.text() == "Критерии…"
    assert window._criteria_button.isEnabled()
    window._set_busy(True)
    assert not window._criteria_button.isEnabled()
    window._set_busy(False)
    assert window._criteria_button.isEnabled()
    window.close()


def test_criteria_button_opens_modal_dialog(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    opened: list[CriteriaConfig] = []

    class _CancelledDialog:
        criteria = None

        def __init__(self, criteria: CriteriaConfig, _parent: object) -> None:
            opened.append(criteria)

        def exec(self) -> int:
            return int(gui_app.QDialog.DialogCode.Rejected)

    monkeypatch.setattr(gui_app, "CriteriaDialog", _CancelledDialog)
    window = _window(monkeypatch)
    window._criteria_button.click()

    assert opened == [CriteriaConfig()]
    window.close()


def test_invalid_config_criteria_keeps_paths_and_blocks_update_until_repaired(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    class _MessageBox:
        @staticmethod
        def critical(*_args: object, **_kwargs: object) -> None:
            return None

    monkeypatch.setattr(gui_app, "QMessageBox", _MessageBox)
    path = tmp_path / "config.toml"
    original = (
        '[files]\ncalculator = "calc.xlsx"\nfund = "fund.xlsx"\n'
        "[criteria.gdm]\nabs_delta_threshold = -1\n"
    )
    path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(gui_app, "config_path", lambda: path)

    window = gui_app.LoaderWindow()
    window._available_fields = ("Береговое",)
    window._field_combo.addItem("Береговое")
    window._field_combo.setCurrentIndex(0)
    window._validation_fingerprint = window._source_fingerprint()
    window._field_selected("Береговое")

    assert window._fields["calculator"].text() == "calc.xlsx"
    assert window._fields["fund"].text() == "fund.xlsx"
    assert window._criteria_invalid
    assert not window._update_button.isEnabled()
    assert window._persist_config(show_error=False)
    assert path.read_text(encoding="utf-8") == original
    window.close()


def test_invalid_criteria_can_be_fixed_and_saved_without_revalidation(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    class _MessageBox:
        @staticmethod
        def critical(*_args: object) -> None:
            return None

    monkeypatch.setattr(gui_app, "QMessageBox", _MessageBox)
    config_file = tmp_path / "config.toml"
    config_file.write_text("[criteria.gdm]\nabs_delta_threshold = -1\n", encoding="utf-8")
    monkeypatch.setattr(gui_app, "config_path", lambda: config_file)
    window = gui_app.LoaderWindow()
    window._available_fields = ("Береговое",)
    window._field_combo.addItem("Береговое")
    window._field_combo.setCurrentIndex(0)
    window._validation_fingerprint = window._source_fingerprint()
    current_fields = window._available_fields
    current_fingerprint = window._validation_fingerprint
    window._field_selected("Береговое")

    assert window._criteria_invalid
    assert not window._update_button.isEnabled()

    class _AcceptedDialog:
        criteria = CriteriaConfig(gdm_abs_delta_threshold=7.0)

        def __init__(self, *_args: object) -> None:
            pass

        def exec(self) -> int:
            return int(gui_app.QDialog.DialogCode.Accepted)

    monkeypatch.setattr(gui_app, "CriteriaDialog", _AcceptedDialog)
    window._edit_criteria()

    assert not window._criteria_invalid
    assert window._available_fields == current_fields
    assert window._validation_fingerprint == current_fingerprint
    assert window._field_combo.currentText() == "Береговое"
    assert window._update_button.isEnabled()
    assert load_config(config_file).config.criteria.gdm_abs_delta_threshold == 7.0
    window.close()


@pytest.mark.parametrize("save_result", ["cancel", "invalid"])
def test_cancel_or_invalid_criteria_save_keeps_update_disabled(
    monkeypatch, tmp_path: Path, save_result: str
) -> None:  # type: ignore[no-untyped-def]
    class _MessageBox:
        @staticmethod
        def critical(*_args: object) -> None:
            return None

        @staticmethod
        def warning(*_args: object) -> None:
            return None

    monkeypatch.setattr(gui_app, "QMessageBox", _MessageBox)
    config_file = tmp_path / "config.toml"
    original = "[criteria.gdm]\nabs_delta_threshold = -1\n"
    config_file.write_text(original, encoding="utf-8")
    monkeypatch.setattr(gui_app, "config_path", lambda: config_file)
    window = gui_app.LoaderWindow()
    window._available_fields = ("Береговое",)
    window._field_combo.addItem("Береговое")
    window._field_combo.setCurrentIndex(0)
    window._validation_fingerprint = window._source_fingerprint()
    window._field_selected("Береговое")

    if save_result == "cancel":

        class _RejectedDialog:
            criteria = CriteriaConfig()

            def __init__(self, *_args: object) -> None:
                pass

            def exec(self) -> int:
                return int(gui_app.QDialog.DialogCode.Rejected)

        monkeypatch.setattr(gui_app, "CriteriaDialog", _RejectedDialog)
    else:

        class _InvalidSaveDialog(gui_app.CriteriaDialog):
            def exec(self) -> int:
                item = self.table.item(0, 3)
                assert item is not None
                item.setText("0")
                self._save()
                return self.result()

        monkeypatch.setattr(gui_app, "CriteriaDialog", _InvalidSaveDialog)
    window._edit_criteria()

    assert window._criteria_invalid
    assert not window._update_button.isEnabled()
    assert config_file.read_text(encoding="utf-8") == original
    window.close()


def test_criteria_dialog_is_modal_loads_values_and_only_edits_value_column() -> None:
    dialog = gui_app.CriteriaDialog(
        CriteriaConfig(chlorine_current_min_mg_dm3=2500.0, gdm_fallback_max_age_days=30)
    )

    assert dialog.isModal()
    assert dialog.table.rowCount() == 8
    assert dialog.table.columnCount() == 5
    chlorine_item = dialog.table.item(2, 3)
    assert chlorine_item is not None and chlorine_item.text() == "2500.0"
    fallback_item = dialog.table.item(6, 3)
    assert fallback_item is not None and fallback_item.text() == "30"
    for row in range(dialog.table.rowCount()):
        for column in range(dialog.table.columnCount()):
            item = dialog.table.item(row, column)
            assert item is not None
            editable = bool(item.flags() & QtCore.Qt.ItemFlag.ItemIsEditable)
            assert editable is (column == 3)
    dialog.close()


def test_criteria_defaults_button_changes_dialog_values_without_persisting() -> None:
    dialog = gui_app.CriteriaDialog(CriteriaConfig(gdm_abs_delta_threshold=9.0))

    dialog.defaults_button.click()

    value_item = dialog.table.item(5, 3)
    assert value_item is not None and value_item.text() == "5.0"
    assert dialog.criteria is None
    assert dialog.result() == int(gui_app.QDialog.DialogCode.Rejected)
    dialog.close()


def test_criteria_save_validates_and_accepts_values(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    dialog = gui_app.CriteriaDialog(CriteriaConfig())
    value_item = dialog.table.item(0, 3)
    assert value_item is not None
    value_item.setText("3")

    dialog._save()

    assert dialog.criteria is not None
    assert dialog.criteria.insufficient_gdi_min_count == 3
    assert dialog.result() == int(gui_app.QDialog.DialogCode.Accepted)
    dialog.close()


def test_criteria_invalid_value_blocks_save_and_names_parameter(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    messages: list[str] = []
    monkeypatch.setattr(
        gui_app.QMessageBox,
        "warning",
        lambda _parent, _title, message: messages.append(message),
    )
    dialog = gui_app.CriteriaDialog(CriteriaConfig())
    value_item = dialog.table.item(0, 3)
    assert value_item is not None
    value_item.setText("0")

    dialog._save()

    assert dialog.criteria is None
    assert messages and "Минимальное количество" in messages[0]
    dialog.close()


def test_criteria_save_preserves_paths_and_current_field_validation(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    config_file = tmp_path / "config.toml"
    monkeypatch.setattr(gui_app, "config_path", lambda: config_file)
    save_config(
        AppConfig(calculator="calc.xlsx", fund="fund.xlsx", research_status="status.xlsx"),
        config_file,
    )
    window = gui_app.LoaderWindow()
    window._operation_kind = "validate"
    window._active_fingerprint = window._source_fingerprint()
    window._finish_success(_result(("Береговое",)))
    window._field_combo.setCurrentIndex(0)
    assert window._update_button.isEnabled()

    class _AcceptedDialog:
        criteria = CriteriaConfig(gdm_abs_delta_threshold=7.0)

        def __init__(self, *_args: object) -> None:
            pass

        def exec(self) -> int:
            return int(gui_app.QDialog.DialogCode.Accepted)

    monkeypatch.setattr(gui_app, "CriteriaDialog", _AcceptedDialog)
    previous_fingerprint = window._validation_fingerprint

    window._edit_criteria()

    loaded = load_config(config_file).config
    assert loaded.calculator == "calc.xlsx"
    assert loaded.fund == "fund.xlsx"
    assert loaded.research_status == "status.xlsx"
    assert loaded.criteria.gdm_abs_delta_threshold == 7.0
    assert window._validation_fingerprint == previous_fingerprint
    assert window._field_combo.currentText() == "Береговое"
    assert window._update_button.isEnabled()
    window.close()


def test_criteria_cancel_does_not_persist(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    window = _window(monkeypatch)
    persistence_calls: list[bool] = []
    monkeypatch.setattr(
        window,
        "_persist_config",
        lambda **_kwargs: persistence_calls.append(True) or True,
    )

    class _CancelledDialog:
        criteria = CriteriaConfig(gdm_abs_delta_threshold=7.0)

        def __init__(self, *_args: object) -> None:
            pass

        def exec(self) -> int:
            return int(gui_app.QDialog.DialogCode.Rejected)

    monkeypatch.setattr(gui_app, "CriteriaDialog", _CancelledDialog)
    window._edit_criteria()

    assert not persistence_calls
    assert window._criteria_config.gdm_abs_delta_threshold == 5.0
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
    captured_criteria: list[CriteriaConfig] = []
    window._criteria_config = CriteriaConfig(gdm_abs_delta_threshold=7.0)

    def fake_run_update(
        _paths: SourcePaths,
        *,
        progress=None,
        target_field: str,
        **_criteria,
    ) -> ServiceResult:
        captured.append(target_field)
        captured_criteria.append(_criteria["criteria_config"])
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
    assert captured_criteria == [CriteriaConfig(gdm_abs_delta_threshold=7.0)]
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
