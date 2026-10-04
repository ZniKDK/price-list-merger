"""Модель таблицы Qt поверх pandas.DataFrame.

QTableView не умеет показывать DataFrame напрямую — ему нужна «модель»,
которая отвечает на вопросы «сколько строк?», «что в ячейке?», «какой цвет?».
"""

from __future__ import annotations

import numbers
from collections.abc import Callable

import numpy as np
import pandas as pd
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PyQt6.QtGui import QBrush, QColor

# Функция «какой фон у строки»: получает строку DataFrame, возвращает цвет или None
RowColor = Callable[[pd.Series], QColor | None]


def is_number(value: object) -> bool:
    """Число ли это (включая числа numpy), но не True/False и не NaN."""
    return isinstance(value, numbers.Real) and not isinstance(value, (bool, np.bool_)) and value == value


def format_value(value: object, money: bool = False) -> str:
    """Текст ячейки: деньги с пробелами между разрядами, пустое — пусто."""
    if value is None:
        return ""
    if isinstance(value, (bool, np.bool_)):
        return "да" if value else ""
    if isinstance(value, float):
        if value != value:  # NaN
            return ""
        if money:
            return f"{value:,.2f}".replace(",", " ").replace(".", ",")
        return f"{value:g}"
    return str(value)


class DataFrameModel(QAbstractTableModel):
    """Показывает DataFrame. Заголовки можно переименовать, строки — подсветить."""

    def __init__(
        self,
        frame: pd.DataFrame | None = None,
        headers: dict[str, str] | None = None,
        money_columns: set[str] | None = None,
        row_color: RowColor | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._frame = pd.DataFrame()
        self._headers = headers or {}
        self._money = money_columns or set()
        self._row_color = row_color
        self._cell_colors: dict[tuple[int, int], QColor] = {}
        self._column_colors: dict[int, QColor] = {}
        if frame is not None:
            self.set_frame(frame)

    def set_frame(
        self,
        frame: pd.DataFrame,
        header_labels: dict[str, str] | None = None,
        money_columns: set[str] | None = None,
    ) -> None:
        self.beginResetModel()
        self._frame = frame.reset_index(drop=True)
        if header_labels is not None:
            self._headers = header_labels
        if money_columns is not None:
            self._money = money_columns
        self._cell_colors = {}
        self._column_colors = {}
        self.endResetModel()

    def frame(self) -> pd.DataFrame:
        return self._frame

    def set_cell_color(self, row: int, column: int, color: QColor) -> None:
        self._cell_colors[(row, column)] = color

    def set_column_color(self, column: int, color: QColor) -> None:
        self._column_colors[column] = color
        self.dataChanged.emit(self.index(0, column), self.index(self.rowCount() - 1, column))

    # --- обязательные методы модели Qt ---

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._frame)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._frame.columns)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, column = index.row(), index.column()
        name = self._frame.columns[column]
        value = self._frame.iat[row, column]
        if role == Qt.ItemDataRole.DisplayRole:
            return format_value(value, money=name in self._money)
        if role == Qt.ItemDataRole.UserRole:
            # Для сортировки: числа сравниваем как числа, а не как текст
            if is_number(value):
                return float(value)
            return format_value(value).lower()
        if role == Qt.ItemDataRole.TextAlignmentRole and is_number(value):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.BackgroundRole:
            color = self._cell_colors.get((row, column), self._column_colors.get(column))
            if color is None and self._row_color is not None:
                color = self._row_color(self._frame.iloc[row])
            return QBrush(color) if color is not None else None
        return None

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            name = str(self._frame.columns[section])
            return self._headers.get(name, name)
        return str(section + 1)


class SearchProxyModel(QSortFilterProxyModel):
    """Поиск по всем колонкам и сортировка по числам (а не по тексту)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSortRole(Qt.ItemDataRole.UserRole)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(-1)  # искать во всех колонках

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        a = left.data(Qt.ItemDataRole.UserRole)
        b = right.data(Qt.ItemDataRole.UserRole)
        # Пустые значения всегда в конце, числа с текстом не сравниваем
        if type(a) is not type(b):
            return isinstance(a, float)
        return a < b
