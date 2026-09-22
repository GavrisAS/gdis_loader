"""Small PySide6 GUI; all ETL work is delegated to :mod:`gdis_loader.service`."""

from __future__ import annotations

import inspect
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
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
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
    default_output_path,
    run_update,
    run_validate,
)

LOGGER = logging.getLogger(__name__)
_ServiceAction = Callable[..., ServiceResult]

_FILE_FIELDS: tuple[tuple[str, str, str, bool], ...] = (
    ("calculator", "Калькулятор", "Excel workbook (*.xlsx);;All files (*)", False),
    ("fund", "Фонд скважин", "Excel workbook (*.xlsx);;All files (*)", False),
    ("gdi", "Сводная таблица ГДИ", "Excel workbook (*.xlsx);;All files (*)", False),
    ("lha", "База ЛХА", "Excel macro workbook (*.xlsm);;All files (*)", False),
    ("daily_report", "Суточный рапорт", "Excel macro workbook (*.xlsm);;All files (*)", False),
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
            parameters = tuple(inspect.signature(self._action).parameters.values())
            accepts_progress = (
                any(
                    parameter.kind
                    in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
                    for parameter in parameters
                )
                or len(tuple(parameters)) >= 2
            )
            result = (
                self._action(self._paths, self._report_progress)
                if accepts_progress
                else self._action(self._paths)
            )
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
        self._busy = False
        self._thread: QThread | None = None
        self._worker: _ServiceWorker | None = None
        self._operation: str | None = None
        self._last_directory = ""
        self._progress_bar: QProgressBar
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
            button = QPushButton("Обзор…")
            button.clicked.connect(lambda _checked=False, name=key: self._browse(name))
            self._buttons.append(button)
            grid.addWidget(button, row, 2)
            if is_output:
                field.setPlaceholderText("Путь файла результата .xlsx")

        actions = QHBoxLayout()
        self._validate_button = QPushButton("Проверить файлы")
        self._validate_button.clicked.connect(self._validate)
        self._update_button = QPushButton("Обновить калькулятор")
        self._update_button.clicked.connect(self._update)
        self._buttons.extend((self._validate_button, self._update_button))
        actions.addWidget(self._validate_button)
        actions.addWidget(self._update_button)
        actions.addStretch(1)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setMinimumWidth(180)
        self._progress_bar.setMaximumWidth(240)
        self._progress_bar.setTextVisible(True)
        actions.addWidget(self._progress_bar)
        outer.addLayout(actions)

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
        if name == "calculator" and not self._fields["output"].text().strip():
            self._fields["output"].setText(str(default_output_path(Path(selected))))
        self._persist_config(show_error=True)

    def _config(self) -> AppConfig:
        values = {key: self._fields[key].text().strip() for key, *_ in _FILE_FIELDS}
        return AppConfig(**values, last_directory=self._last_directory)

    def _paths(self) -> SourcePaths:
        values = self._config()
        calculator = Path(values.calculator)
        output = Path(values.output) if values.output else default_output_path(calculator)
        return SourcePaths(
            calculator=calculator,
            fund=Path(values.fund),
            gdi=Path(values.gdi),
            lha=Path(values.lha),
            daily_report=Path(values.daily_report),
            output=output,
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
        for button in self._buttons:
            button.setEnabled(not busy)

    def _set_status(self, message: str) -> None:
        self._status_box.setPlainText(message)

    def _reset_progress(self) -> None:
        self._progress_bar.setValue(0)

    @Slot(int, str)
    def _progress_changed(self, percent: int, stage: str) -> None:
        self._progress_bar.setValue(percent)
        self._set_status(f"{self._operation or 'Операция'}: {stage}")

    def _start(self, action: _ServiceAction, operation: str) -> None:
        if self._busy:
            return
        if not self._persist_config(show_error=True):
            return
        try:
            paths = self._paths()
            configure_logging(paths.output.parent / "gdis_loader.log")
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, operation, f"Не удалось подготовить запуск: {error}")
            return

        self._operation = operation
        self._reset_progress()
        self._set_busy(True)
        self._set_status(f"{operation}: чтение Excel выполняется в фоне…")
        thread = QThread(self)

        def action_with_progress(
            worker_paths: SourcePaths, progress: ProgressCallback
        ) -> ServiceResult:
            return action(worker_paths, progress=progress)

        worker = _ServiceWorker(action_with_progress, paths)
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
        self._set_status(result.summary())
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
        self._set_busy(False)

    def _validate(self) -> None:
        self._start(run_validate, "Проверка файлов")

    def _update(self) -> None:
        self._start(run_update, "Обновление данных")

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
