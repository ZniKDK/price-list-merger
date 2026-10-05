"""Шаг 4: результат свода — цифры, таблицы и сохранение в Excel."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)

from ..core.merging import MATCH_FUZZY, price_column
from ..core.pipeline import MergeReport
from . import animations
from .style import icon
from .table_model import DataFrameModel, SearchProxyModel
from .widgets import HintTableView, fit_columns

PRODUCT_HEADERS = {
    "number": "№", "sku": "Артикул", "name": "Наименование", "unit": "Ед.",
    "offers": "Поставщиков", "best_price": "Лучшая цена", "best_supplier": "Поставщик",
    "markup": "Наценка, %", "sale_price": "Цена продажи",
}
OFFER_HEADERS = {
    "number": "№ товара", "supplier": "Поставщик", "row": "Строка", "sku": "Артикул",
    "name": "Наименование", "price": "Цена", "stock": "Остаток", "match": "Сопоставлено по",
    "score": "Похожесть, %",
}
REJECTED_HEADERS = {
    "supplier": "Поставщик", "row": "Строка", "reason": "Причина", "content": "Содержимое строки",
}
# Короткие текстовые значения — по центру столбца
CENTER = {"unit", "best_supplier", "supplier", "match"}


class StatCard(QFrame):
    """Карточка с крупной цифрой и подписью."""

    def __init__(self, label: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.value = QLabel("—")
        self.value.setObjectName("statValue")
        caption = QLabel(label)
        caption.setObjectName("statLabel")
        caption.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.addWidget(self.value)
        layout.addWidget(caption)

    def set_number(self, number: int) -> None:
        # Цифра плавно «досчитывает» до итога
        animations.count_up(self, number, lambda value: self.value.setText(f"{round(value)}"))


class ResultPage(QWidget):
    save_requested = pyqtSignal()
    open_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("page")
        self.report: MergeReport | None = None

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress_text = QLabel()
        self.progress_text.setProperty("role", "muted")

        self.cards = {
            "products": StatCard("товаров в итоговом прайсе"),
            "in_several": StatCard("найдены у нескольких поставщиков"),
            "fuzzy": StatCard("сопоставлены по похожему названию"),
            "rejected": StatCard("строк отброшено (см. вкладку)"),
        }
        cards = QGridLayout()
        cards.setHorizontalSpacing(12)
        for column, card in enumerate(self.cards.values()):
            cards.addWidget(card, 0, column)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по артикулу, названию, поставщику…")
        self.search.setClearButtonEnabled(True)
        self.save_button = QPushButton("  Сохранить в Excel…")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save_requested)
        self.open_button = QPushButton("  Открыть файл")
        self.open_button.clicked.connect(self.open_requested)
        self.open_button.setVisible(False)
        toolbar = QHBoxLayout()
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.open_button)
        toolbar.addWidget(self.save_button)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.products_model = DataFrameModel(center_columns=CENTER)
        self.offers_model = DataFrameModel(
            row_color=lambda row: "best" if row["best"] else None,
            money_columns={"price"},
            center_columns=CENTER,
        )
        self.rejected_model = DataFrameModel(headers=REJECTED_HEADERS, center_columns=CENTER)
        self.proxies: list[SearchProxyModel] = []
        self.views: list[HintTableView] = []
        tabs = (
            (self.products_model, "Итог", "Свод ещё не выполнен", ""),
            (self.offers_model, "Все предложения", "Свод ещё не выполнен", ""),
            (self.rejected_model, "Отброшено", "Отброшенных строк нет",
             "Программа разобрала все строки прайсов"),
        )
        for model, title, empty_title, empty_subtitle in tabs:
            proxy = SearchProxyModel(self)
            proxy.setSourceModel(model)
            self.search.textChanged.connect(proxy.setFilterFixedString)
            view = HintTableView(empty_title, empty_subtitle)
            view.setModel(proxy)
            view.setSortingEnabled(True)
            view.setAlternatingRowColors(model is not self.offers_model)
            view.verticalHeader().setVisible(False)
            self.tabs.addTab(view, title)
            self.proxies.append(proxy)
            self.views.append(view)
        self.search.textChanged.connect(self._search_hint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.progress_text)
        layout.addWidget(self.progress)
        layout.addLayout(cards)
        layout.addSpacing(4)
        layout.addLayout(toolbar)
        layout.addWidget(self.tabs, 1)
        self.update_icons()
        self.set_busy(False)

    def update_icons(self) -> None:
        self.save_button.setIcon(icon("download", "#FFFFFF"))
        self.open_button.setIcon(icon("external-link"))
        # Значок лупы слева в поле поиска
        if not hasattr(self, "_search_action"):
            self._search_action = self.search.addAction(
                icon("search"), QLineEdit.ActionPosition.LeadingPosition
            )
        else:
            self._search_action.setIcon(icon("search"))

    def _search_hint(self, text: str) -> None:
        """При поиске пустая таблица пишет «Ничего не найдено», а не «Свод не выполнен»."""
        for index, view in enumerate(self.views):
            if text:
                view.empty_hint = ("Ничего не найдено", f"По запросу «{text}» совпадений нет")
            elif index == 2 and self.report is not None:
                view.empty_hint = ("Отброшенных строк нет", "Программа разобрала все строки прайсов")
            else:
                view.empty_hint = ("Свод ещё не выполнен", "")
            view.viewport().update()

    def set_busy(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        self.progress_text.setVisible(busy)
        self.save_button.setEnabled(not busy and self.report is not None)

    def set_progress(self, percent: int, text: str) -> None:
        self.progress.setValue(percent)
        self.progress_text.setText(text)

    def show_report(self, report: MergeReport) -> None:
        self.report = report
        stats = report.stats()
        for key, card in self.cards.items():
            card.set_number(stats[key])
        self.open_button.setVisible(False)

        # --- итог ---
        products = report.products.copy()
        products.insert(0, "number", products["group"] + 1)
        supplier_columns = [price_column(name) for name in report.suppliers]
        columns = list(PRODUCT_HEADERS) + supplier_columns
        headers = dict(PRODUCT_HEADERS)
        headers.update({price_column(name): f"Цена: {name}" for name in report.suppliers})
        money = {"best_price", "sale_price", *supplier_columns}
        self.products_model.set_frame(products[columns], headers, money)
        first_supplier_column = len(PRODUCT_HEADERS)
        for row, (best, price) in enumerate(zip(products["best_supplier"], products["best_price"])):
            if best:
                column = first_supplier_column + report.suppliers.index(best)
                self.products_model.set_cell_color(row, column, "best")
            elif price != price:  # NaN — нет ни одной годной цены
                self.products_model.set_cell_color(row, 5, "warn")

        # --- все предложения ---
        offers = report.offers.sort_values(["group", "price"], kind="stable").copy()
        offers.insert(0, "number", offers["group"] + 1)
        offers["score"] = offers["score"].where(
            (offers["match"] == MATCH_FUZZY) & (offers["score"] < 100)
        )
        self.offers_model.set_frame(offers[[*OFFER_HEADERS, "best"]].copy(), OFFER_HEADERS)
        self.rejected_model.set_frame(report.rejected[list(REJECTED_HEADERS)])
        self._search_hint(self.search.text())

        for view in self.views:
            view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
            fit_columns(view)
        # Колонку «лучшая» показываем цветом строки, а не текстом
        self.views[1].setColumnHidden(len(OFFER_HEADERS), True)
        self.tabs.setTabText(2, f"Отброшено ({len(report.rejected)})")
        animations.fade_in(self.tabs)
        self.set_busy(False)
