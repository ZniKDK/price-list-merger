"""Главное окно: мастер из четырёх шагов.

1. Прайсы  →  2. Колонки  →  3. Наценка  →  4. Результат
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import APP_NAME, __version__
from ..core.exporter import export_report
from ..core.pipeline import MergeReport, SupplierSource
from ..profiles import ProfileStore, SupplierProfile
from .columns_page import ColumnsPage
from .files_page import FilesPage
from .result_page import ResultPage
from .settings_page import SettingsPage
from .worker import MergeWorker

RESOURCES = Path(__file__).resolve().parent.parent / "resources"

STEPS = [
    ("1. Прайсы", "Прайсы поставщиков",
     "Добавьте прайсы в Excel или CSV. Порядок важен: артикулы и названия "
     "в итоговом прайсе берутся у поставщика, который выше в списке."),
    ("2. Колонки", "Сопоставление колонок",
     "Программа подобрала колонки сама — проверьте и при необходимости поправьте. "
     "Если таблица начинается не с первой строки, укажите строку заголовка."),
    ("3. Наценка", "Сопоставление и наценка",
     "Как искать одинаковые товары и какую наценку добавить к лучшей цене."),
    ("4. Результат", "Результат",
     "Итоговый прайс: лучшая цена по каждому товару и цена продажи. "
     "Зелёным отмечена минимальная цена."),
]
FILES, COLUMNS, SETTINGS, RESULT = range(4)


class MainWindow(QMainWindow):
    def __init__(self, profiles: ProfileStore | None = None, settings: QSettings | None = None) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        icon = RESOURCES / "app.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1200, 760)

        self.settings = settings or QSettings("PriceListMerger", "PriceListMerger")
        self.profiles = profiles or ProfileStore()
        self.sources: list[SupplierSource] = []
        self.report: MergeReport | None = None
        self.saved_path: Path | None = None
        self.worker: MergeWorker | None = None

        # --- шаги слева ---
        self.steps = QListWidget()
        self.steps.setObjectName("steps")
        self.steps.setFixedWidth(190)
        self.steps.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # без рамки фокуса вокруг шага
        for title, *_ in STEPS:
            self.steps.addItem(QListWidgetItem(title))
        self.steps.currentRowChanged.connect(self._step_clicked)

        # --- страницы ---
        self.files_page = FilesPage(self.sources, self.profiles)
        self.files_page.last_folder = self.settings.value("last_folder", str(Path.home()))
        self.files_page.changed.connect(self._sources_changed)
        self.columns_page = ColumnsPage(self.sources)
        self.columns_page.changed.connect(self._sources_changed)
        self.settings_page = SettingsPage(self.settings)
        self.result_page = ResultPage()
        self.result_page.save_requested.connect(self.save_excel)
        self.result_page.open_requested.connect(self.open_saved)

        self.pages = QStackedWidget()
        for page in (self.files_page, self.columns_page, self.settings_page, self.result_page):
            self.pages.addWidget(page)

        self.title = QLabel()
        self.title.setObjectName("title")
        self.hint = QLabel()
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)

        self.back_button = QPushButton("← Назад")
        self.back_button.clicked.connect(lambda: self.go_to(self.pages.currentIndex() - 1))
        self.next_button = QPushButton()
        self.next_button.setObjectName("primary")
        self.next_button.clicked.connect(self._next)
        nav = QHBoxLayout()
        nav.addWidget(self.back_button)
        nav.addStretch()
        nav.addWidget(self.next_button)

        content = QVBoxLayout()
        content.setContentsMargins(20, 16, 20, 16)
        content.addWidget(self.title)
        content.addWidget(self.hint)
        content.addSpacing(8)
        content.addWidget(self.pages, 1)
        content.addLayout(nav)

        central = QWidget()
        central.setObjectName("page")
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.steps)
        layout.addLayout(content, 1)
        self.setCentralWidget(central)
        self._build_menu()
        self.go_to(FILES)

    def _build_menu(self) -> None:
        help_menu = self.menuBar().addMenu("Справка")
        profiles = QAction("Папка с профилями поставщиков", self)
        profiles.triggered.connect(self._open_profiles_folder)
        about = QAction("О программе", self)
        about.triggered.connect(self._about)
        help_menu.addAction(profiles)
        help_menu.addAction(about)

    # --- навигация ---

    def go_to(self, step: int) -> None:
        step = max(FILES, min(step, RESULT))
        if not self._step_allowed(step):
            return
        self.pages.setCurrentIndex(step)
        self.steps.blockSignals(True)
        self.steps.setCurrentRow(step)
        self.steps.blockSignals(False)
        _, title, hint = STEPS[step]
        self.title.setText(title)
        self.hint.setText(hint)
        if step == COLUMNS:
            self.columns_page.refresh()
        self._update_nav()

    def _step_allowed(self, step: int) -> bool:
        if step in (COLUMNS, SETTINGS):
            return bool(self.sources)
        if step == RESULT:
            return self.report is not None or self.worker is not None
        return True

    def _step_clicked(self, step: int) -> None:
        if step == RESULT and self.report is None:
            self._next() if self.pages.currentIndex() == SETTINGS else self.go_to(SETTINGS)
            return
        self.go_to(step)
        if self.pages.currentIndex() != step:  # шаг недоступен — вернуть выделение
            self.steps.blockSignals(True)
            self.steps.setCurrentRow(self.pages.currentIndex())
            self.steps.blockSignals(False)

    def _next(self) -> None:
        step = self.pages.currentIndex()
        if step == SETTINGS:
            self.run_merge()
        elif step == RESULT:
            self.go_to(FILES)
        else:
            self.go_to(step + 1)

    def _update_nav(self) -> None:
        step = self.pages.currentIndex()
        self.back_button.setEnabled(step > FILES)
        texts = {FILES: "Далее →", COLUMNS: "Далее →", SETTINGS: "Свести прайсы", RESULT: "Новый свод"}
        self.next_button.setText(texts[step])
        busy = self.worker is not None
        self.next_button.setEnabled(not busy and (step == RESULT or bool(self.sources)))
        for index in range(self.steps.count()):
            item = self.steps.item(index)
            enabled = self._step_allowed(index) or (index == RESULT and bool(self.sources))
            flags = item.flags()
            item.setFlags(flags | Qt.ItemFlag.ItemIsEnabled if enabled else flags & ~Qt.ItemFlag.ItemIsEnabled)

    def _sources_changed(self) -> None:
        # Прайсы или колонки поменялись — старый результат больше не верен
        self.report = None
        self.saved_path = None
        self.settings.setValue("last_folder", self.files_page.last_folder)
        self.files_page.refresh()
        self._update_nav()

    # --- свод ---

    def run_merge(self) -> None:
        for index, source in enumerate(self.sources):
            problems = source.problems()
            if problems:
                QMessageBox.warning(
                    self, "Не все колонки выбраны",
                    f"Поставщик «{source.supplier}»: " + "; ".join(problems) + ".",
                )
                self.go_to(COLUMNS)
                self.columns_page.supplier_box.setCurrentIndex(index)
                return

        self.settings_page.save()
        if self.columns_page.remember.isChecked():
            for source in self.sources:
                self.profiles.save(
                    source.supplier, SupplierProfile(dict(source.mapping), source.header_row, source.sheet)
                )

        self.worker = MergeWorker(
            list(self.sources), self.settings_page.merge_settings(), self.settings_page.pricing(), self
        )
        self.worker.progress.connect(self.result_page.set_progress)
        self.worker.done.connect(self._merge_done)
        self.worker.failed.connect(self._merge_failed)
        self.worker.finished.connect(self._worker_finished)
        self.result_page.set_busy(True)
        self.go_to(RESULT)
        self.worker.start()

    def _merge_done(self, report: MergeReport) -> None:
        self.report = report
        self.saved_path = None
        self.result_page.show_report(report)

    def _merge_failed(self, message: str) -> None:
        self.result_page.set_busy(False)
        QMessageBox.critical(self, "Свод не выполнен", message)

    def _worker_finished(self) -> None:
        self.worker = None
        if self.report is None:
            self.go_to(SETTINGS)
        self._update_nav()

    # --- сохранение ---

    def save_excel(self) -> None:
        if self.report is None:
            return
        folder = self.settings.value("save_folder", self.files_page.last_folder)
        default = Path(folder) / f"Свод прайсов {date.today():%d.%m.%Y}.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить итоговый прайс", str(default), "Excel (*.xlsx)")
        if not path:
            return
        try:
            self.saved_path = export_report(self.report, path)
        except PermissionError:
            QMessageBox.warning(
                self, "Файл занят",
                "Не удалось записать файл. Возможно, он открыт в Excel — закройте его и повторите.",
            )
            return
        self.settings.setValue("save_folder", str(self.saved_path.parent))
        self.result_page.open_button.setVisible(True)
        self.statusBar().showMessage(f"Сохранено: {self.saved_path}", 8000)

    def open_saved(self) -> None:
        if self.saved_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.saved_path)))

    # --- справка ---

    def _open_profiles_folder(self) -> None:
        folder = self.profiles.path.parent
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _about(self) -> None:
        QMessageBox.about(
            self, "О программе",
            f"<b>{APP_NAME}</b> {__version__}<br><br>"
            "Сводит прайс-листы поставщиков (Excel, CSV) в один файл: находит одинаковые "
            "товары по артикулу и названию, выбирает минимальную цену и добавляет наценку.<br><br>"
            '<a href="https://github.com/ZniKDK/price-list-merger">github.com/ZniKDK/price-list-merger</a>'
            "<br>Лицензия MIT",
        )

    def closeEvent(self, event) -> None:
        if self.worker is not None:
            self.worker.wait(5000)  # дождаться окончания свода, чтобы не оборвать поток
        self.settings_page.save()
        super().closeEvent(event)
