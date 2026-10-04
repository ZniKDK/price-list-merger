"""Шаг 2: какие колонки прайса за что отвечают.

Слева выбор поставщика и колонок, справа — сам прайс, чтобы было видно,
что выбрано. Колонки, выбранные для полей, подсвечены голубым.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
    QSpinBox, QTableView, QVBoxLayout, QWidget,
)

from ..core.loader import PriceListError
from ..core.mapping import FIELDS, guess_mapping
from ..core.pipeline import SupplierSource
from .style import MAPPED_COLOR
from .table_model import DataFrameModel

NOT_USED = "— не используется —"
PREVIEW_ROWS = 300  # больше в предпросмотре не нужно, а окно не тормозит


class ColumnsPage(QWidget):
    """Сопоставление колонок для каждого поставщика."""

    changed = pyqtSignal()

    def __init__(self, sources: list[SupplierSource], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("page")
        self.sources = sources
        self._updating = False

        self.supplier_box = QComboBox()
        self.supplier_box.currentIndexChanged.connect(self._show_source)
        self.sheet_box = QComboBox()
        self.sheet_box.currentTextChanged.connect(self._change_sheet)
        self.header_spin = QSpinBox()
        self.header_spin.setRange(1, 10_000)
        self.header_spin.setToolTip("Номер строки файла, в которой названия колонок")
        self.header_spin.valueChanged.connect(self._change_header)

        file_box = QGroupBox("Файл")
        file_form = QFormLayout(file_box)
        file_form.addRow("Поставщик:", self.supplier_box)
        file_form.addRow("Лист:", self.sheet_box)
        file_form.addRow("Строка заголовка:", self.header_spin)

        self.field_boxes: dict[str, QComboBox] = {}
        fields_box = QGroupBox("Колонки")
        fields_form = QFormLayout(fields_box)
        for field in FIELDS:
            box = QComboBox()
            box.currentIndexChanged.connect(self._change_mapping)
            self.field_boxes[field.key] = box
            label = f"{field.label}{' *' if field.required else ''}:"
            fields_form.addRow(label, box)
        hint = QLabel("* обязательно. Нужен артикул или наименование (лучше оба).")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        fields_form.addRow(hint)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.remember = QCheckBox("Запомнить колонки для этого поставщика")
        self.remember.setChecked(True)
        self.remember.setToolTip("В следующий раз прайс этого поставщика настроится сам")

        left = QVBoxLayout()
        left.addWidget(file_box)
        left.addWidget(fields_box)
        left.addWidget(self.status)
        left.addWidget(self.remember)
        left.addStretch()
        left_widget = QWidget()
        left_widget.setLayout(left)
        left_widget.setFixedWidth(340)

        self.model = DataFrameModel()
        self.preview = QTableView()
        self.preview.setModel(self.model)
        self.preview.setAlternatingRowColors(True)
        self.preview.verticalHeader().setVisible(False)  # номер строки файла — в первой колонке
        preview_title = QLabel("Предпросмотр прайса (номера строк — как в файле)")
        preview_title.setObjectName("hint")
        right = QVBoxLayout()
        right.addWidget(preview_title)
        right.addWidget(self.preview, 1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(left_widget)
        layout.addLayout(right, 1)

    # --- обновление при смене списка прайсов ---

    def refresh(self) -> None:
        current = self.supplier_box.currentIndex()
        self._updating = True
        self.supplier_box.clear()
        for source in self.sources:
            mark = "" if not source.problems() else "  ⚠"
            self.supplier_box.addItem(source.supplier + mark)
        self._updating = False
        if self.sources:
            self.supplier_box.setCurrentIndex(min(max(current, 0), len(self.sources) - 1))
        self._show_source()

    def current_source(self) -> SupplierSource | None:
        index = self.supplier_box.currentIndex()
        return self.sources[index] if 0 <= index < len(self.sources) else None

    def _show_source(self) -> None:
        if self._updating:
            return
        source = self.current_source()
        self._updating = True
        for widget in (self.sheet_box, self.header_spin, *self.field_boxes.values()):
            widget.setEnabled(source is not None)
        if source is None:
            self.model.set_frame(self.model.frame().iloc[0:0])
            self._updating = False
            self.status.clear()
            return

        self.sheet_box.clear()
        sheets = source.table.raw.sheets
        self.sheet_box.addItems(sheets or ["(CSV — один лист)"])
        self.sheet_box.setEnabled(len(sheets) > 1)
        if source.sheet:
            self.sheet_box.setCurrentText(source.sheet)
        self.header_spin.setValue(source.header_row + 1)

        columns = source.table.columns
        for key, box in self.field_boxes.items():
            box.clear()
            box.addItem(NOT_USED)
            box.addItems(columns)
            chosen = source.mapping.get(key)
            box.setCurrentIndex(columns.index(chosen) + 1 if chosen in columns else 0)
        self._updating = False
        self._update_preview()

    def _update_preview(self) -> None:
        source = self.current_source()
        if source is None:
            return
        data = source.table.data.head(PREVIEW_ROWS)
        # В заголовке колонки пишем, для какого поля она выбрана
        labels = {}
        by_column = {column: key for key, column in source.mapping.items()}
        field_labels = {field.key: field.label for field in FIELDS}
        for column in data.columns:
            key = by_column.get(column)
            labels[column] = f"{column}\n→ {field_labels[key]}" if key else column
        frame = data.copy()
        frame.insert(0, "_row", data.index)
        labels["_row"] = "Строка"
        self.model.set_frame(frame, labels)
        for position, column in enumerate(frame.columns):
            if column in by_column:
                self.model.set_column_color(position, MAPPED_COLOR)
        self.preview.resizeColumnsToContents()
        for position in range(len(frame.columns)):
            if self.preview.columnWidth(position) > 320:
                self.preview.setColumnWidth(position, 320)
        problems = source.problems()
        if problems:
            self.status.setText("⚠ " + "; ".join(problems).capitalize())
            self.status.setStyleSheet("color: #C00000;")
        else:
            self.status.setText("✓ Колонки выбраны")
            self.status.setStyleSheet("color: #2E7D32;")

    # --- изменения пользователем ---

    def _reload(self, source: SupplierSource, sheet: str | None, header_row: int | None) -> None:
        old = (source.sheet, source.header_row)
        source.sheet, source.header_row = sheet, header_row
        try:
            source.reload()
        except PriceListError as error:
            source.sheet, source.header_row = old
            source.reload()
            QMessageBox.warning(self, "Прайс", str(error))
        if not source.mapping:
            # Колонки на новом месте совсем другие — подбираем заново
            source.mapping = guess_mapping(source.table.columns)
        self._show_source()
        self.changed.emit()

    def _change_sheet(self, sheet: str) -> None:
        source = self.current_source()
        if self._updating or source is None or not source.table.raw.sheets or sheet == source.sheet:
            return
        # На другом листе шапка может быть в другой строке — ищем заново
        self._reload(source, sheet, None)

    def _change_header(self, value: int) -> None:
        source = self.current_source()
        if self._updating or source is None or value - 1 == source.header_row:
            return
        self._reload(source, source.sheet, value - 1)

    def _change_mapping(self) -> None:
        source = self.current_source()
        if self._updating or source is None:
            return
        mapping = {}
        for key, box in self.field_boxes.items():
            if box.currentIndex() > 0:
                mapping[key] = box.currentText()
        source.mapping = mapping
        self._update_preview()
        # Обновляем значок ⚠ у поставщика в списке
        mark = "" if not source.problems() else "  ⚠"
        self._updating = True
        self.supplier_box.setItemText(self.supplier_box.currentIndex(), source.supplier + mark)
        self._updating = False
        self.changed.emit()
