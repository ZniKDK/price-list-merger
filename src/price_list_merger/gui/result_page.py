"""Шаг 4: результат свода — цифры, таблицы и сохранение в Excel."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
    QTableView, QTabWidget, QVBoxLayout, QWidget,
)

from ..core.merging import MATCH_FUZZY, price_column
from ..core.pipeline import MergeReport
from .style import BEST_COLOR, WARN_COLOR
from .table_model import DataFrameModel, SearchProxyModel

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
        layout.addWidget(self.value)
        layout.addWidget(caption)


class ResultPage(QWidget):
    save_requested = pyqtSignal()
    open_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("page")
        self.report: MergeReport | None = None

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress_text = QLabel()
        self.progress_text.setObjectName("hint")

        self.cards = {
            "products": StatCard("товаров в итоговом прайсе"),
            "in_several": StatCard("найдены у нескольких поставщиков"),
            "fuzzy": StatCard("сопоставлены по похожему названию"),
            "rejected": StatCard("строк отброшено (см. вкладку)"),
        }
        cards = QGridLayout()
        for column, card in enumerate(self.cards.values()):
            cards.addWidget(card, 0, column)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по артикулу, названию, поставщику…")
        self.search.setClearButtonEnabled(True)
        self.save_button = QPushButton("Сохранить в Excel…")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save_requested)
        self.open_button = QPushButton("Открыть файл")
        self.open_button.clicked.connect(self.open_requested)
        self.open_button.setVisible(False)
        toolbar = QHBoxLayout()
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.save_button)
        toolbar.addWidget(self.open_button)

        self.tabs = QTabWidget()
        self.products_model = DataFrameModel(row_color=None)
        self.offers_model = DataFrameModel(
            row_color=lambda row: BEST_COLOR if row["best"] else None,
            money_columns={"price"},
        )
        self.rejected_model = DataFrameModel(headers=REJECTED_HEADERS)
        self.proxies = []
        for model, title in (
            (self.products_model, "Итог"),
            (self.offers_model, "Все предложения"),
            (self.rejected_model, "Отброшено"),
        ):
            proxy = SearchProxyModel(self)
            proxy.setSourceModel(model)
            self.search.textChanged.connect(proxy.setFilterFixedString)
            view = QTableView()
            view.setModel(proxy)
            view.setSortingEnabled(True)
            view.setAlternatingRowColors(model is self.rejected_model)
            view.verticalHeader().setVisible(False)
            self.tabs.addTab(view, title)
            self.proxies.append(proxy)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.progress_text)
        layout.addWidget(self.progress)
        layout.addLayout(cards)
        layout.addLayout(toolbar)
        layout.addWidget(self.tabs, 1)
        self.set_busy(False)

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
            card.value.setText(str(stats[key]))
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
                self.products_model.set_cell_color(row, column, BEST_COLOR)
            elif price != price:  # NaN — нет ни одной годной цены
                self.products_model.set_cell_color(row, 5, WARN_COLOR)

        # --- все предложения ---
        offers = report.offers.sort_values(["group", "price"], kind="stable").copy()
        offers.insert(0, "number", offers["group"] + 1)
        offers["score"] = offers["score"].where(
            (offers["match"] == MATCH_FUZZY) & (offers["score"] < 100)
        )
        self.offers_model.set_frame(offers[[*OFFER_HEADERS, "best"]].copy(), OFFER_HEADERS)
        self.rejected_model.set_frame(report.rejected[list(REJECTED_HEADERS)])

        for index in range(self.tabs.count()):
            view = self.tabs.widget(index)
            view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
            view.resizeColumnsToContents()
            for column in range(view.model().columnCount()):
                view.setColumnWidth(column, min(view.columnWidth(column), 380))
        # Колонку «лучшая» показываем цветом строки, а не текстом
        offers_view = self.tabs.widget(1)
        offers_view.setColumnHidden(len(OFFER_HEADERS), True)
        self.tabs.setTabText(2, f"Отброшено ({len(report.rejected)})")
        self.set_busy(False)
