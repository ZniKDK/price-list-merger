"""Шаг 3: настройки сопоставления и наценки.

Настройки запоминаются между запусками (QSettings — в реестре Windows,
раздел программы), чтобы не вводить наценку каждый раз заново.
"""

from __future__ import annotations

import json

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QPushButton, QSlider, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..core.merging import MergeSettings
from ..core.pricing import ROUND_NINE, ROUNDING_LABELS, MarkupTier, PricingSettings, apply_markup
from .style import icon
from .table_model import format_value
from .widgets import AnimatedComboBox, HintTableWidget

EXAMPLE_PRICES = (85.0, 1234.0, 15_490.0)


class SettingsPage(QWidget):
    def __init__(self, settings: QSettings, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("page")
        self.settings = settings

        # --- сопоставление ---
        self.fuzzy = QCheckBox("Искать похожие наименования, если артикулов нет")
        self.fuzzy.setToolTip("«Кабель ВВГнг 3х2,5» и «ВВГнг кабель 3*2.5 мм2» будут считаться одним товаром")
        self.threshold = QSlider(Qt.Orientation.Horizontal)
        self.threshold.setRange(70, 100)
        self.threshold_label = QLabel()
        self.threshold_label.setMinimumWidth(40)  # ширина под «100%»: ползунок не прыгает
        self.threshold.valueChanged.connect(
            lambda value: self.threshold_label.setText(f"{value}%")
        )
        self.fuzzy.toggled.connect(self.threshold.setEnabled)
        self.skip_empty = QCheckBox("Не брать цену, если товара нет в наличии (остаток 0)")

        threshold_row = QHBoxLayout()
        threshold_row.addWidget(QLabel("мягче"))
        threshold_row.addWidget(self.threshold, 1)
        threshold_row.addWidget(QLabel("строже"))
        threshold_row.addWidget(self.threshold_label)

        match_box = QGroupBox("Сопоставление товаров")
        match_layout = QVBoxLayout(match_box)
        match_layout.addWidget(QLabel("Сначала товары сравниваются по артикулу, затем по наименованию."))
        match_layout.addWidget(self.fuzzy)
        match_layout.addWidget(QLabel("Порог похожести наименований:"))
        match_layout.addLayout(threshold_row)
        match_layout.addWidget(self.skip_empty)

        # --- наценка ---
        self.percent = QDoubleSpinBox()
        self.percent.setRange(-99, 1000)
        self.percent.setDecimals(1)
        self.percent.setSuffix(" %")
        self.rounding = AnimatedComboBox()
        for key, label in ROUNDING_LABELS.items():
            self.rounding.addItem(label, key)

        self.tiers = HintTableWidget(0, 2, "Ступеней нет", "Наценка одна для всех товаров")
        self.tiers.setHorizontalHeaderLabels(["Закупка от, ₽", "Наценка, %"])
        self.tiers.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tiers.verticalHeader().setVisible(False)
        self.tiers.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tiers.setFixedHeight(170)
        self.add_tier_button = QPushButton("  Добавить ступень")
        self.add_tier_button.clicked.connect(lambda: self._add_tier(1000, self.percent.value()))
        self.remove_tier_button = QPushButton("  Убрать")
        self.remove_tier_button.clicked.connect(self._remove_tier)
        tier_buttons = QHBoxLayout()
        tier_buttons.addWidget(self.add_tier_button)
        tier_buttons.addWidget(self.remove_tier_button)
        self.update_icons()
        tier_buttons.addStretch()

        self.example = QLabel()
        self.example.setProperty("role", "muted")
        self.example.setWordWrap(True)

        markup_box = QGroupBox("Наценка")
        markup_form = QFormLayout(markup_box)
        markup_form.addRow("Наценка по умолчанию:", self.percent)
        markup_form.addRow(QLabel("Ступени — другая наценка для дорогих товаров (необязательно):"))
        markup_form.addRow(self.tiers)
        markup_form.addRow(tier_buttons)
        markup_form.addRow("Округление цены продажи:", self.rounding)
        markup_form.addRow(self.example)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        column_left = QVBoxLayout()
        column_left.addWidget(match_box)
        column_left.addStretch()
        column_right = QVBoxLayout()
        column_right.addWidget(markup_box)
        column_right.addStretch()
        layout.addLayout(column_left, 1)
        layout.addLayout(column_right, 1)

        self.load()
        for signal in (self.percent.valueChanged, self.rounding.currentIndexChanged, self.tiers.itemChanged):
            signal.connect(self._update_example)
        self._update_example()

    def update_icons(self) -> None:
        self.add_tier_button.setIcon(icon("plus"))
        self.remove_tier_button.setIcon(icon("trash-2"))

    # --- ступени ---

    def _add_tier(self, price: float, percent: float) -> None:
        row = self.tiers.rowCount()
        self.tiers.insertRow(row)
        for column, value in enumerate((price, percent)):
            item = QTableWidgetItem(f"{value:g}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tiers.setItem(row, column, item)
        self._update_example()

    def _remove_tier(self) -> None:
        rows = sorted({index.row() for index in self.tiers.selectedIndexes()}, reverse=True)
        for row in rows or [self.tiers.rowCount() - 1]:
            if row >= 0:
                self.tiers.removeRow(row)
        self._update_example()

    def _read_tiers(self) -> list[MarkupTier]:
        """Ступени из таблицы; строки с ошибками (не числа) пропускаем."""
        tiers = []
        for row in range(self.tiers.rowCount()):
            try:
                price = float(self.tiers.item(row, 0).text().replace(",", ".").replace(" ", ""))
                percent = float(self.tiers.item(row, 1).text().replace(",", "."))
            except (AttributeError, ValueError):
                continue
            tiers.append(MarkupTier(price, percent))
        return tiers

    # --- значения для свода ---

    def merge_settings(self) -> MergeSettings:
        return MergeSettings(self.fuzzy.isChecked(), self.threshold.value(), self.skip_empty.isChecked())

    def pricing(self) -> PricingSettings:
        return PricingSettings(self.percent.value(), self._read_tiers(), self.rounding.currentData())

    def _update_example(self) -> None:
        pricing = self.pricing()
        parts = [
            f"{format_value(price, money=True)} → {format_value(apply_markup(price, pricing), money=True)} ₽"
            for price in EXAMPLE_PRICES
        ]
        self.example.setText("Пример: " + ";  ".join(parts))

    # --- запоминание между запусками ---

    def load(self) -> None:
        s = self.settings
        self.fuzzy.setChecked(s.value("merge/fuzzy", True, type=bool))
        self.threshold.setValue(s.value("merge/threshold", MergeSettings().fuzzy_threshold, type=int))
        self.threshold_label.setText(f"{self.threshold.value()}%")
        self.threshold.setEnabled(self.fuzzy.isChecked())
        self.skip_empty.setChecked(s.value("merge/skip_out_of_stock", False, type=bool))
        self.percent.setValue(s.value("pricing/percent", 20.0, type=float))
        index = self.rounding.findData(s.value("pricing/rounding", ROUND_NINE))
        self.rounding.setCurrentIndex(max(index, 0))
        try:
            tiers = json.loads(s.value("pricing/tiers", "[[10000, 12]]"))
            for price, percent in tiers:
                self._add_tier(float(price), float(percent))
        except (TypeError, ValueError):
            pass

    def save(self) -> None:
        s = self.settings
        s.setValue("merge/fuzzy", self.fuzzy.isChecked())
        s.setValue("merge/threshold", self.threshold.value())
        s.setValue("merge/skip_out_of_stock", self.skip_empty.isChecked())
        s.setValue("pricing/percent", self.percent.value())
        s.setValue("pricing/rounding", self.rounding.currentData())
        tiers = [[tier.min_price, tier.percent] for tier in self._read_tiers()]
        s.setValue("pricing/tiers", json.dumps(tiers))
