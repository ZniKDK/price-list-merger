"""Шаг 1: список прайсов поставщиков."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QStackedLayout, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.loader import SUPPORTED_EXTENSIONS, PriceListError
from ..core.pipeline import SupplierSource
from ..profiles import ProfileStore
from .style import ERROR_COLOR

FILE_FILTER = "Прайс-листы (*.xlsx *.xlsm *.csv *.txt);;Все файлы (*.*)"
COLUMNS = ["Поставщик", "Файл", "Лист", "Строк", "Колонки"]


class FilesPage(QWidget):
    """Добавление, удаление и порядок прайсов; имя поставщика можно изменить."""

    changed = pyqtSignal()  # список или имена поставщиков изменились

    def __init__(self, sources: list[SupplierSource], profiles: ProfileStore, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("page")
        self.sources = sources
        self.profiles = profiles
        self.last_folder = str(Path.home())
        self.setAcceptDrops(True)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(self._rename)
        self.table.itemSelectionChanged.connect(self._update_buttons)

        self.empty = QLabel(
            "Перетащите сюда прайсы поставщиков (.xlsx, .csv)\n"
            "или нажмите «Добавить файлы».\n\n"
            "Хотите сначала посмотреть, как это работает? Нажмите «Демо-прайсы»."
        )
        self.empty.setObjectName("empty")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.stack = QStackedLayout()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.table)

        self.add_button = QPushButton("Добавить файлы…")
        self.add_button.clicked.connect(self.choose_files)
        self.demo_button = QPushButton("Демо-прайсы")
        self.demo_button.setToolTip("Три вымышленных поставщика с прайсами в разных форматах")
        self.demo_button.clicked.connect(self.load_demo)
        self.remove_button = QPushButton("Убрать")
        self.remove_button.clicked.connect(self.remove_selected)
        self.up_button = QPushButton("↑")
        self.up_button.setToolTip("Выше: артикулы и названия в итоге берутся у первого поставщика")
        self.up_button.clicked.connect(lambda: self.move_selected(-1))
        self.down_button = QPushButton("↓")
        self.down_button.clicked.connect(lambda: self.move_selected(1))

        buttons = QHBoxLayout()
        for button in (self.add_button, self.demo_button):
            buttons.addWidget(button)
        buttons.addStretch()
        for button in (self.up_button, self.down_button, self.remove_button):
            buttons.addWidget(button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(buttons)
        layout.addLayout(self.stack, 1)
        self.refresh()

    # --- добавление файлов ---

    def choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Прайсы поставщиков", self.last_folder, FILE_FILTER)
        if paths:
            self.last_folder = str(Path(paths[0]).parent)
            self.add_files([Path(path) for path in paths])

    def load_demo(self) -> None:
        from ..demo import DEMO_FILES, create_demo_files

        # Демо-файлы создаём в папке пользователя, рядом с профилями
        folder = self.profiles.path.parent / "demo"
        demo_paths = create_demo_files(folder)
        self.add_files([path for path in demo_paths if path.name in DEMO_FILES])

    def add_files(self, paths: list[Path]) -> None:
        errors = []
        loaded = {source.path.resolve() for source in self.sources}
        for path in paths:
            if path.resolve() in loaded:
                continue  # этот файл уже в списке
            try:
                source = SupplierSource.from_file(path, self._unique_name(path.stem))
            except PriceListError as error:
                errors.append(str(error))
                continue
            profile = self.profiles.get(source.supplier)
            if profile:
                source.apply_saved(profile.mapping, profile.header_row, profile.sheet)
            self.sources.append(source)
            loaded.add(path.resolve())
        self.refresh()
        self.changed.emit()
        if errors:
            QMessageBox.warning(self, "Не все файлы прочитаны", "\n\n".join(errors))

    def _unique_name(self, name: str) -> str:
        names = {source.supplier for source in self.sources}
        candidate, number = name, 2
        while candidate in names:
            candidate = f"{name} ({number})"
            number += 1
        return candidate

    # --- перетаскивание файлов мышью ---

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        paths = [path for path in paths if path.suffix.lower() in SUPPORTED_EXTENSIONS | {".xls"}]
        if paths:
            self.add_files(paths)

    # --- список ---

    def selected_row(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def remove_selected(self) -> None:
        row = self.selected_row()
        if row >= 0:
            del self.sources[row]
            self.refresh()
            self.changed.emit()

    def move_selected(self, step: int) -> None:
        row = self.selected_row()
        target = row + step
        if row < 0 or not 0 <= target < len(self.sources):
            return
        self.sources[row], self.sources[target] = self.sources[target], self.sources[row]
        self.refresh()
        self.table.selectRow(target)
        self.changed.emit()

    def refresh(self) -> None:
        """Перерисовывает таблицу по списку sources."""
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.sources))
        for row, source in enumerate(self.sources):
            problems = source.problems()
            cells = [
                source.supplier,
                str(source.path),
                source.sheet or "—",
                str(len(source.table.data)) if source.table is not None else "",
                "готово" if not problems else "нужно выбрать: " + "; ".join(problems),
            ]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column != 0:  # редактировать можно только имя поставщика
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == 4 and problems:
                    item.setBackground(ERROR_COLOR)
                self.table.setItem(row, column, item)
        self.table.blockSignals(False)
        self.stack.setCurrentWidget(self.table if self.sources else self.empty)
        self._update_buttons()

    def _rename(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        source = self.sources[item.row()]
        name = item.text().strip()
        others = {s.supplier for s in self.sources if s is not source}
        if not name or name in others:
            QMessageBox.warning(self, "Имя поставщика", "Имя не может быть пустым или повторяться.")
            self.refresh()
            return
        source.supplier = name
        self.changed.emit()

    def _update_buttons(self) -> None:
        row = self.selected_row()
        self.remove_button.setEnabled(row >= 0)
        self.up_button.setEnabled(row > 0)
        self.down_button.setEnabled(0 <= row < len(self.sources) - 1)
