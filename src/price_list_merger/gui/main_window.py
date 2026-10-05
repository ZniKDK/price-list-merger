"""Главное окно: мастер из четырёх шагов.

1. Прайсы  →  2. Колонки  →  3. Наценка  →  4. Результат

Слева — панель шагов. Внизу панели: тема оформления, папка с профилями
поставщиков и «О программе» (вместо верхнего меню, которое выбивалось
из оформления).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PyQt6.QtCore import QPoint, QSettings, Qt, QUrl
from PyQt6.QtGui import QAction, QActionGroup, QDesktopServices, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu,
    QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import APP_NAME, __version__
from ..core.exporter import export_report
from ..core.pipeline import MergeReport, SupplierSource
from ..profiles import ProfileStore, SupplierProfile
from . import animations
from .columns_page import ColumnsPage
from .files_page import FilesPage
from .result_page import ResultPage
from .settings_page import SettingsPage
from .style import C, RESOURCES, THEME_MODES, apply_theme, icon
from .widgets import Toast
from .worker import MergeWorker

STEPS = [
    ("Прайсы", "Прайсы поставщиков",
     "Добавьте прайсы в Excel или CSV. Порядок важен: артикулы и названия "
     "в итоговом прайсе берутся у поставщика, который выше в списке."),
    ("Колонки", "Сопоставление колонок",
     "Программа подобрала колонки сама — проверьте и при необходимости поправьте. "
     "Если таблица начинается не с первой строки, укажите строку заголовка."),
    ("Наценка", "Сопоставление и наценка",
     "Как искать одинаковые товары и какую наценку добавить к лучшей цене."),
    ("Результат", "Результат",
     "Итоговый прайс: лучшая цена по каждому товару и цена продажи. "
     "Зелёным отмечена минимальная цена."),
]
FILES, COLUMNS, SETTINGS, RESULT = range(4)
SIDEBAR_WIDTH = 224


class Sidebar(QFrame):
    """Панель шагов. Подсветка выбранного шага плавно переезжает между пунктами."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)

        logo = QLabel()
        pixmap = QPixmap(str(RESOURCES / "app.png"))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(
                32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            ))
        name = QLabel(APP_NAME)
        name.setObjectName("appName")
        version = QLabel(f"версия {__version__}")
        version.setObjectName("appVersion")
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(name)
        titles.addWidget(version)
        brand = QHBoxLayout()
        brand.setContentsMargins(8, 0, 0, 0)
        brand.addWidget(logo)
        brand.addLayout(titles, 1)

        # Подсветка выбранного шага — отдельная плашка под кнопками
        self.indicator = QFrame(self)
        self.indicator.setObjectName("stepIndicator")
        self.indicator.lower()

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.step_buttons: list[QPushButton] = []
        steps = QVBoxLayout()
        steps.setSpacing(4)
        for number, (title, *_rest) in enumerate(STEPS, start=1):
            button = QPushButton(f"{number}   {title}")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # без рамки фокуса
            self.group.addButton(button, number - 1)
            self.step_buttons.append(button)
            steps.addWidget(button)

        self.theme_button = self._tool_button("Тема")
        self.profiles_button = self._tool_button("Профили поставщиков")
        self.about_button = self._tool_button("О программе")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 18, 10, 14)
        layout.addLayout(brand)
        layout.addSpacing(22)
        layout.addLayout(steps)
        layout.addStretch()
        for button in (self.theme_button, self.profiles_button, self.about_button):
            layout.addWidget(button)

    def _tool_button(self, text: str) -> QPushButton:
        button = QPushButton(f"  {text}")  # пробелы — зазор между значком и текстом
        button.setProperty("kind", "tool")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return button

    def update_icons(self, theme_icon: str) -> None:
        color = C["sidebar_text"]
        self.theme_button.setIcon(icon(theme_icon, color))
        self.profiles_button.setIcon(icon("folder-open", color))
        self.about_button.setIcon(icon("info", color))

    def select(self, step: int, animate: bool = True) -> None:
        button = self.step_buttons[step]
        button.setChecked(True)
        target = button.geometry()
        if animate:
            animations.slide_to(self.indicator, target)
        else:
            self.indicator.setGeometry(target)

    def resizeEvent(self, event) -> None:  # noqa: N802 — имя задано Qt
        super().resizeEvent(event)
        checked = self.group.checkedButton()
        if checked is not None:
            self.indicator.setGeometry(checked.geometry())


class MainWindow(QMainWindow):
    def __init__(self, profiles: ProfileStore | None = None, settings: QSettings | None = None) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        app_icon = RESOURCES / "app.png"
        if app_icon.exists():
            self.setWindowIcon(QIcon(str(app_icon)))
        self.resize(1240, 780)
        self.setMinimumSize(980, 640)

        self.settings = settings or QSettings("PriceListMerger", "PriceListMerger")
        self.profiles = profiles or ProfileStore()
        self.sources: list[SupplierSource] = []
        self.report: MergeReport | None = None
        self.saved_path: Path | None = None
        self.worker: MergeWorker | None = None
        self.theme_mode = str(self.settings.value("ui/theme", "system"))

        # --- панель шагов ---
        self.sidebar = Sidebar()
        self.sidebar.group.idClicked.connect(self._step_clicked)
        self.sidebar.profiles_button.clicked.connect(self._open_profiles_folder)
        self.sidebar.about_button.clicked.connect(self._about)
        self._build_theme_menu()

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

        self.back_button = QPushButton("  Назад")
        self.back_button.clicked.connect(lambda: self.go_to(self.pages.currentIndex() - 1))
        self.next_button = QPushButton()
        self.next_button.setObjectName("primary")
        self.next_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)  # значок справа от текста
        self.next_button.clicked.connect(self._next)
        nav = QHBoxLayout()
        nav.addWidget(self.back_button)
        nav.addStretch()
        nav.addWidget(self.next_button)

        content = QVBoxLayout()
        content.setContentsMargins(24, 18, 24, 18)
        content.addWidget(self.title)
        content.addWidget(self.hint)
        content.addSpacing(10)
        content.addWidget(self.pages, 1)
        content.addSpacing(6)
        content.addLayout(nav)

        central = QWidget()
        central.setObjectName("page")
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.sidebar)
        layout.addLayout(content, 1)
        self.setCentralWidget(central)

        self.toast = Toast(central)
        self.toast.left_margin = SIDEBAR_WIDTH

        # Тема «как в системе» следит за переключением темы Windows на лету
        app = QApplication.instance()
        if app is not None:
            app.styleHints().colorSchemeChanged.connect(self._system_theme_changed)
        self.set_theme(self.theme_mode, save=False)
        self.go_to(FILES)

    # --- тема ---

    def _build_theme_menu(self) -> None:
        menu = QMenu(self)
        group = QActionGroup(menu)
        self.theme_actions: dict[str, QAction] = {}
        for mode, label, _icon in THEME_MODES:
            action = QAction(label, menu, checkable=True)
            action.triggered.connect(lambda _checked, m=mode: self.set_theme(m))
            group.addAction(action)
            menu.addAction(action)
            self.theme_actions[mode] = action
        self.theme_menu = menu
        # Меню открываем сами, над кнопкой: с setMenu Qt резервирует место
        # под стрелку и сдвигает иконку и текст относительно соседних пунктов
        button = self.sidebar.theme_button
        button.clicked.connect(
            lambda: menu.exec(button.mapToGlobal(button.rect().topLeft()) - QPoint(0, menu.sizeHint().height()))
        )

    def set_theme(self, mode: str, save: bool = True) -> None:
        """Включает тему: light, dark или system (как в Windows)."""
        app = QApplication.instance()
        if app is None:
            return
        self.theme_mode = mode
        apply_theme(app, mode)
        if save:
            self.settings.setValue("ui/theme", mode)
        for key, action in self.theme_actions.items():
            action.setChecked(key == mode)
            action.setIcon(icon(dict((m, i) for m, _l, i in THEME_MODES)[key]))
        label = dict((m, lbl) for m, lbl, _i in THEME_MODES)[mode]
        self.sidebar.theme_button.setText(f"  Тема: {label.lower()}")
        self.sidebar.update_icons(dict((m, i) for m, _l, i in THEME_MODES)[mode])
        # Иконки кнопок и ячейки с подсветкой рисуются цветами темы — обновляем
        self.files_page.update_icons()
        self.files_page.refresh()
        self.settings_page.update_icons()
        self.result_page.update_icons()
        self._update_nav()
        for widget in app.allWidgets():
            widget.update()

    def _system_theme_changed(self, _scheme) -> None:
        if self.theme_mode == "system":
            self.set_theme("system", save=False)

    # --- навигация ---

    def go_to(self, step: int) -> None:
        step = max(FILES, min(step, RESULT))
        if not self._step_allowed(step):
            self.sidebar.select(self.pages.currentIndex(), animate=False)
            return
        changed = step != self.pages.currentIndex()
        self.pages.setCurrentIndex(step)
        self.sidebar.select(step, animate=self.isVisible())
        _, title, hint = STEPS[step]
        self.title.setText(title)
        self.hint.setText(hint)
        if step == COLUMNS:
            self.columns_page.refresh()
        if changed:
            animations.fade_in(self.pages.currentWidget())
        self._update_nav()

    def _step_allowed(self, step: int) -> bool:
        if step in (COLUMNS, SETTINGS):
            return bool(self.sources)
        if step == RESULT:
            return self.report is not None or self.worker is not None
        return True

    def _step_clicked(self, step: int) -> None:
        if step == RESULT and self.report is None and self.worker is None:
            # Результата ещё нет — запускаем свод (или ведём к настройкам)
            self._next() if self.pages.currentIndex() == SETTINGS else self.go_to(SETTINGS)
            self.sidebar.select(self.pages.currentIndex())
            return
        self.go_to(step)

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
        self.back_button.setIcon(icon("arrow-left"))
        texts = {
            FILES: ("Далее", "arrow-right"), COLUMNS: ("Далее", "arrow-right"),
            SETTINGS: ("Свести прайсы", "merge"), RESULT: ("Новый свод", "rotate-ccw"),
        }
        text, icon_name = texts[step]
        self.next_button.setText(f"{text}  ")  # пробелы — зазор между текстом и значком
        self.next_button.setIcon(icon(icon_name, "#FFFFFF"))
        busy = self.worker is not None
        self.next_button.setEnabled(not busy and (step == RESULT or bool(self.sources)))
        for index, button in enumerate(self.sidebar.step_buttons):
            button.setEnabled(self._step_allowed(index) or (index == RESULT and bool(self.sources)))

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
        self.toast.show_message(f"Сохранено: {self.saved_path.name}", "Открыть", self.open_saved)

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
            f'<a href="https://github.com/ZniKDK/price-list-merger" style="color: {C["accent"]}">'
            "github.com/ZniKDK/price-list-merger</a><br>Лицензия MIT",
        )

    # --- окно ---

    def resizeEvent(self, event) -> None:  # noqa: N802 — имя задано Qt
        super().resizeEvent(event)
        self.toast.reposition()

    def showEvent(self, event) -> None:  # noqa: N802 — имя задано Qt
        super().showEvent(event)
        # Кнопки получили размеры только сейчас — ставим подсветку шага на место
        self.sidebar.select(self.pages.currentIndex(), animate=False)

    def closeEvent(self, event) -> None:  # noqa: N802 — имя задано Qt
        if self.worker is not None:
            self.worker.wait(5000)  # дождаться окончания свода, чтобы не оборвать поток
        self.settings_page.save()
        super().closeEvent(event)
