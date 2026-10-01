"""Small PySide6 GUI; all ETL work is delegated to :mod:`gdis_loader.service`."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore  # ty: ignore[unresolved-import, unused-ignore-comment]
from PySide6.QtCore import (  # ty: ignore[unresolved-import, unused-ignore-comment]
    QObject,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtWidgets import (  # ty: ignore[unresolved-import, unused-ignore-comment]
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from PySide6.QtGui import QCloseEvent  # ty: ignore[unresolved-import, unused-ignore-comment]

from gdis_loader import __version__
from gdis_loader.config import AppConfig, config_path, load_config, save_config
from gdis_loader.domain.models import SourcePaths
from gdis_loader.progress import ProgressCallback, ProgressUpdate
from gdis_loader.service import (
    ServiceError,
    ServiceResult,
    configure_logging,
    run_update,
    run_validate,
)

LOGGER = logging.getLogger(__name__)
_ServiceAction = Callable[[SourcePaths, ProgressCallback], ServiceResult]

_FILE_FIELDS: tuple[tuple[str, str, str, bool], ...] = (
    ("calculator", "Калькулятор", "Excel workbook (*.xlsx);;All files (*)", False),
    ("fund", "Фонд скважин", "Excel workbook (*.xlsx);;All files (*)", False),
    ("gdi", "Сводная таблица ГДИ", "Excel workbook (*.xlsx);;All files (*)", False),
    ("lha", "База ЛХА", "Excel macro workbook (*.xlsm);;All files (*)", False),
    ("daily_report", "Суточный рапорт", "Excel macro workbook (*.xlsm);;All files (*)", False),
    ("well_history", "База по скважинам", "Excel workbook (*.xlsx);;All files (*)", False),
    (
        "research_status",
        "Статус исследований",
        "Excel workbook (*.xlsx);;All files (*)",
        False,
    ),
    ("output", "Результат", "Excel workbook (*.xlsx);;All files (*)", True),
)


class _ServiceWorker(QObject):
    """QObject living in a QThread and never touching GUI widgets."""

    finished = Signal(object)
    failed = Signal(str)
    progress_changed = Signal(int, str)

    def __init__(self, action: _ServiceAction, paths: SourcePaths) -> None:
        super().__init__()
        self._action = action
        self._paths = paths

    @Slot()
    def run(self) -> None:
        try:
            result = self._action(self._paths, self._report_progress)
        except ServiceError as error:
            self.failed.emit(str(error))
        except Exception:
            LOGGER.exception("Неожиданная ошибка GUI-задачи")
            self.failed.emit("Неожиданная ошибка. Подробности записаны в лог-файл.")
        else:
            self.finished.emit(result)

    def _report_progress(self, update: ProgressUpdate) -> None:
        self.progress_changed.emit(update.percent, update.stage)


class LoaderWindow(QMainWindow):
    """Thin view/controller for selecting paths and invoking the service."""

    _thread_finished_signal = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("gdis_loader — загрузчик данных ГДИС")
        self.setMinimumSize(820, 520)
        self._fields: dict[str, QLineEdit] = {}
        self._buttons: list[QPushButton] = []
        self._browse_buttons: list[QPushButton] = []
        self._busy = False
        self._thread: QThread | None = None
        self._worker: _ServiceWorker | None = None
        self._operation: str | None = None
        self._operation_kind: str | None = None
        self._operation_field: str | None = None
        self._last_directory = ""
        self._available_fields: tuple[str, ...] = ()
        self._validation_fingerprint: tuple[str, ...] | None = None
        self._active_fingerprint: tuple[str, ...] | None = None
        self._progress_bar: QProgressBar
        self._field_combo: QComboBox
        self._thread_finished_signal.connect(self._thread_finished)
        self._build_ui()

        loaded = load_config(config_path())
        self._apply_config(loaded.config)
        if loaded.warning:
            QTimer.singleShot(
                0,
                lambda warning=loaded.warning: QMessageBox.warning(
                    self, "Конфигурация", warning or ""
                ),
            )
            self._set_status(loaded.warning)

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage(f"Версия {__version__}")
        outer = QVBoxLayout(central)
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        outer.addLayout(grid)

        for row, (key, label, _file_filter, is_output) in enumerate(_FILE_FIELDS):
            grid.addWidget(QLabel(label), row, 0)
            field = QLineEdit()
            field.setClearButtonEnabled(True)
            self._fields[key] = field
            grid.addWidget(field, row, 1)
            if not is_output:
                field.textChanged.connect(self._input_path_changed)
            button = QPushButton("Обзор…")
            button.clicked.connect(lambda _checked=False, name=key: self._browse(name))
            self._buttons.append(button)
            self._browse_buttons.append(button)
            grid.addWidget(button, row, 2)
            if is_output:
                field.setPlaceholderText("Путь файла результата .xlsx")

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        outer.addWidget(separator)

        actions = QHBoxLayout()
        self._validate_button = QPushButton("Проверить файлы")
        self._validate_button.clicked.connect(self._validate)
        self._field_combo = QComboBox()
        self._field_combo.setPlaceholderText("Месторождение…")
        self._field_combo.setEnabled(False)
        self._field_combo.currentTextChanged.connect(self._field_selected)
        self._update_button = QPushButton("Обновить калькулятор")
        self._update_button.clicked.connect(self._update)
        self._update_button.setEnabled(False)
        self._buttons.extend((self._validate_button, self._update_button))
        actions.addWidget(self._validate_button)
        actions.addWidget(self._field_combo, 1)
        actions.addWidget(self._update_button)
        outer.addLayout(actions)

        progress_separator = QFrame()
        progress_separator.setFrameShape(QFrame.Shape.HLine)
        progress_separator.setFrameShadow(QFrame.Shadow.Sunken)
        outer.addWidget(progress_separator)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._progress_bar.setTextVisible(True)
        outer.addWidget(self._progress_bar)

        outer.addWidget(QLabel("Статус"))
        self._status_box = QPlainTextEdit()
        self._status_box.setReadOnly(True)
        self._status_box.setMinimumHeight(180)
        outer.addWidget(self._status_box, 1)
        self._set_status("Готово. Выберите входные файлы.")

    def _apply_config(self, config: AppConfig) -> None:
        for key, *_ in _FILE_FIELDS:
            self._fields[key].setText(getattr(config, key))
        self._last_directory = config.last_directory

    def _initial_directory(self, name: str) -> str:
        current = self._fields[name].text().strip()
        if current:
            return str(Path(current).parent)
        if self._last_directory:
            return self._last_directory
        return ""

    def _browse(self, name: str) -> None:
        _, label, file_filter, is_output = next(spec for spec in _FILE_FIELDS if spec[0] == name)
        initial_directory = self._initial_directory(name)
        if is_output:
            selected, _ = QFileDialog.getSaveFileName(
                self,
                "Выберите файл результата",
                initial_directory,
                file_filter,
            )
        else:
            selected, _ = QFileDialog.getOpenFileName(
                self,
                f"Выберите: {label}",
                initial_directory,
                file_filter,
            )
        if not selected:
            return
        self._fields[name].setText(selected)
        self._last_directory = str(Path(selected).parent)
        self._persist_config(show_error=True)

    def _config(self) -> AppConfig:
        values = {key: self._fields[key].text().strip() for key, *_ in _FILE_FIELDS}
        return AppConfig(**values, last_directory=self._last_directory)

    def _paths(self) -> SourcePaths:
        values = self._config()
        return SourcePaths(
            calculator=Path(values.calculator),
            fund=Path(values.fund),
            gdi=Path(values.gdi),
            lha=Path(values.lha),
            daily_report=Path(values.daily_report),
            well_history=Path(values.well_history),
            research_status=Path(values.research_status),
            output=Path(values.output) if values.output else None,
        )

    def _source_fingerprint(self) -> tuple[str, ...]:
        return tuple(
            str(Path(self._fields[key].text().strip()).expanduser().resolve(strict=False))
            if self._fields[key].text().strip()
            else ""
            for key, *_ in _FILE_FIELDS
            if key != "output"
        )

    def _clear_available_fields(self) -> None:
        self._available_fields = ()
        self._field_combo.blockSignals(True)
        self._field_combo.clear()
        self._field_combo.setCurrentIndex(-1)
        self._field_combo.blockSignals(False)
        self._field_combo.setEnabled(False)
        self._update_button.setEnabled(False)

    def _invalidate_validation(self) -> None:
        self._validation_fingerprint = None
        self._clear_available_fields()

    def _input_path_changed(self, _text: str) -> None:
        if (
            self._validation_fingerprint is not None
            and self._source_fingerprint() != self._validation_fingerprint
        ):
            self._invalidate_validation()
            self._set_status("Пути входных файлов изменились. Снова нажмите «Проверить файлы».")

    def _field_selected(self, field_name: str) -> None:
        valid = (
            bool(field_name)
            and self._validation_fingerprint is not None
            and self._source_fingerprint() == self._validation_fingerprint
            and field_name in self._available_fields
        )
        self._update_button.setEnabled(valid and not self._busy)
        if valid:
            self._set_status(
                f"Обнаружено месторождений: {len(self._available_fields)}\nВыбрано: {field_name}"
            )

    def _persist_config(self, *, show_error: bool) -> bool:
        try:
            save_config(self._config(), config_path())
        except OSError as error:
            if show_error:
                QMessageBox.critical(
                    self,
                    "Конфигурация",
                    f"Не удалось сохранить настройки: {error}",
                )
            return False
        return True

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for button in self._browse_buttons:
            button.setEnabled(not busy)
        for field in self._fields.values():
            field.setEnabled(not busy)
        self._validate_button.setEnabled(not busy)
        if busy:
            self._field_combo.setEnabled(False)
            self._update_button.setEnabled(False)
            return
        validation_current = (
            self._validation_fingerprint is not None
            and self._source_fingerprint() == self._validation_fingerprint
        )
        self._field_combo.setEnabled(validation_current and bool(self._available_fields))
        self._update_button.setEnabled(
            validation_current
            and bool(self._field_combo.currentText())
            and self._field_combo.currentText() in self._available_fields
        )

    def _set_status(self, message: str) -> None:
        self._status_box.setPlainText(message)

    def _reset_progress(self) -> None:
        self._progress_bar.setValue(0)

    @Slot(int, str)
    def _progress_changed(self, percent: int, stage: str) -> None:
        self._progress_bar.setValue(percent)
        self._set_status(f"{self._operation or 'Операция'}: {stage}")

    def _start(
        self,
        action: _ServiceAction,
        operation: str,
        *,
        operation_kind: str,
        target_field: str | None = None,
    ) -> None:
        if self._busy:
            return
        self._operation = operation
        self._operation_kind = operation_kind
        self._operation_field = target_field
        self._reset_progress()
        if not self._persist_config(show_error=True):
            self._operation = None
            self._operation_kind = None
            self._operation_field = None
            return
        try:
            paths = self._paths()
            log_directory = (
                paths.output.parent if paths.output is not None else paths.calculator.parent
            )
            configure_logging(log_directory / "gdis_loader.log")
        except (OSError, ValueError) as error:
            self._operation = None
            self._operation_kind = None
            self._operation_field = None
            QMessageBox.critical(self, operation, f"Не удалось подготовить запуск: {error}")
            return

        self._set_busy(True)
        self._set_status(
            f"{operation}: {target_field}\nЧтение Excel выполняется в фоне…"
            if target_field
            else f"{operation}: чтение Excel выполняется в фоне…"
        )
        thread = QThread(self)
        worker = _ServiceWorker(action, paths)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress_changed.connect(self._progress_changed)
        worker.finished.connect(self._finish_success)
        worker.failed.connect(self._finish_error)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(
            lambda finished_thread=thread: self._thread_finished_signal.emit(finished_thread)
        )
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot(object)
    def _finish_success(self, result: ServiceResult) -> None:
        if not result.has_errors:
            self._progress_bar.setValue(100)
        if self._operation_kind == "validate":
            if result.has_errors:
                self._invalidate_validation()
            else:
                self._available_fields = result.report.available_fields
                self._validation_fingerprint = self._active_fingerprint
                self._field_combo.blockSignals(True)
                self._field_combo.clear()
                self._field_combo.addItems(list(self._available_fields))
                self._field_combo.setCurrentIndex(-1)
                self._field_combo.blockSignals(False)
                self._field_combo.setEnabled(bool(self._available_fields))
                self._update_button.setEnabled(False)
        self._set_status(result.summary())
        if self._operation_kind == "validate" and not result.has_errors:
            if self._available_fields:
                self._status_box.appendPlainText("Выберите одно месторождение для обновления.")
            else:
                self._status_box.appendPlainText("В текущем фонде месторождения не обнаружены.")
        if result.has_errors:
            QMessageBox.critical(self, self._operation or "Ошибка", result.summary())
        elif self._operation == "Обновление данных" and result.has_capacity_warning:
            QMessageBox.warning(
                self,
                "Расчетная емкость",
                "Строки после 100 записаны только на лист «Данные» и пока "
                "не рассчитываются на листах «Расчет» и «Рейтинг».\n\n" + result.summary(),
            )

    @Slot(str)
    def _finish_error(self, message: str) -> None:
        if self._operation_kind == "validate":
            self._invalidate_validation()
        self._set_status(message)
        QMessageBox.critical(self, self._operation or "Ошибка", message)

    @Slot(object)
    def _thread_finished(self, finished_thread: QThread) -> None:
        """Release only the operation whose thread emitted ``finished``."""

        if self._thread is not finished_thread:
            return
        self._thread = None
        self._worker = None
        self._operation = None
        self._operation_kind = None
        self._operation_field = None
        self._active_fingerprint = None
        self._set_busy(False)

    def _validate(self) -> None:
        self._invalidate_validation()
        self._active_fingerprint = self._source_fingerprint()

        def validate_action(paths: SourcePaths, progress: ProgressCallback) -> ServiceResult:
            return run_validate(paths, progress=progress)

        self._start(
            validate_action,
            "Проверка файлов",
            operation_kind="validate",
        )

    def _update(self) -> None:
        field_name = self._field_combo.currentText()
        if (
            not field_name
            or self._validation_fingerprint is None
            or self._source_fingerprint() != self._validation_fingerprint
        ):
            self._update_button.setEnabled(False)
            self._set_status("Сначала проверьте файлы и выберите месторождение.")
            return

        def update_action(paths: SourcePaths, progress: ProgressCallback) -> ServiceResult:
            return run_update(paths, progress=progress, target_field=field_name)

        self._start(
            update_action,
            "Обновление данных",
            operation_kind="update",
            target_field=field_name,
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._busy:
            event.ignore()
            return
        self._persist_config(show_error=False)
        event.accept()


def smoke_test(expected_version: str | None = None) -> int:
    """Import the frozen runtime's critical modules without creating a window."""

    from openpyxl import load_workbook  # noqa: F401

    from gdis_loader import __version__
    from gdis_loader.excel.writer import write_target_rows  # noqa: F401
    from gdis_loader.service import ServiceResult, run_update, run_validate  # noqa: F401

    if expected_version is not None and __version__ != expected_version:
        raise RuntimeError(
            f"Встроенная версия {__version__!r} не совпадает с ожидаемой {expected_version!r}."
        )

    location = config_path()
    if not isinstance(location, Path) or not location.parent.is_dir():
        raise RuntimeError(f"Недоступен каталог config.toml: {location}")
    if getattr(sys, "frozen", False):
        executable_directory = Path(sys.executable).resolve().parent
        if location.parent != executable_directory:
            raise RuntimeError("В frozen-режиме config.toml должен находиться рядом с EXE.")
    if sys.stdout is not None:
        print(f"GDIS Data Loader {__version__} — PySide6 Qt {QtCore.qVersion()} smoke-test passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--smoke-test" in arguments:
        expected_version: str | None = None
        if "--expected-version" in arguments:
            index = arguments.index("--expected-version")
            if index + 1 >= len(arguments):
                raise SystemExit("--expected-version requires a value")
            expected_version = arguments[index + 1]
        return smoke_test(expected_version)
    app = QApplication([sys.argv[0], *arguments])
    window = LoaderWindow()
    window.show()
    return app.exec()
