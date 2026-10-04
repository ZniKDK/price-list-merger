"""Весь процесс целиком: файлы → очистка → свод → наценка.

Этим модулем пользуются и окно программы, и командная строка.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .cleaning import OFFER_COLUMNS, REJECTED_COLUMNS, clean_price_table
from .loader import PriceListError, PriceTable, load_price_list
from .mapping import Mapping, guess_mapping, mapping_problems
from .merging import MATCH_FUZZY, MergeResult, MergeSettings, merge_offers
from .pricing import PricingSettings, apply_markup

# Функция «сообщить о ходе работы»: доля выполненного (0–1) и текст
Progress = Callable[[float, str], None]


@dataclass
class SupplierSource:
    """Прайс одного поставщика и настройки его чтения."""

    path: Path
    supplier: str
    sheet: str | None = None
    header_row: int | None = None  # None — найти автоматически
    mapping: Mapping = field(default_factory=dict)
    table: PriceTable | None = None  # прочитанный файл (кэш)

    @classmethod
    def from_file(cls, path: str | Path, supplier: str | None = None) -> SupplierSource:
        """Читает файл и угадывает колонки. Имя поставщика по умолчанию — имя файла."""
        path = Path(path)
        source = cls(path=path, supplier=supplier or path.stem)
        source.reload()
        source.mapping = guess_mapping(source.table.columns)
        return source

    def reload(self) -> PriceTable:
        """Перечитывает файл (например, после смены листа или строки заголовка)."""
        self.table = load_price_list(self.path, self.sheet, self.header_row)
        self.sheet = self.table.raw.sheet
        self.header_row = self.table.header_row
        # Колонки, которых больше нет после перечитывания, из сопоставления убираем
        self.mapping = {
            key: column for key, column in self.mapping.items() if column in self.table.columns
        }
        return self.table

    def problems(self) -> list[str]:
        return mapping_problems(self.mapping)


@dataclass
class MergeReport:
    """Результат: свод, наценка и статистика для отчёта."""

    merge: MergeResult
    products: pd.DataFrame  # товары с ценой продажи
    rejected: pd.DataFrame  # отброшенные строки с причинами
    pricing: PricingSettings
    rows_read: dict[str, int]  # сколько строк прочитано у каждого поставщика

    @property
    def offers(self) -> pd.DataFrame:
        return self.merge.offers

    @property
    def suppliers(self) -> list[str]:
        return self.merge.suppliers

    def stats(self) -> dict[str, int]:
        """Цифры для итоговой сводки в окне программы и в Excel."""
        products = self.products
        offers = self.offers
        return {
            "suppliers": len(self.suppliers),
            "rows": sum(self.rows_read.values()),
            "offers": len(offers),
            "products": len(products),
            "in_several": int((products["offers"] > 1).sum()),
            # Товары, в которых хотя бы одно предложение найдено по похожему названию
            "fuzzy": int(offers.loc[offers["match"] == MATCH_FUZZY, "group"].nunique()),
            "rejected": len(self.rejected),
            "without_price": int(products["best_price"].isna().sum()),
        }


def run_merge(
    sources: list[SupplierSource],
    merge_settings: MergeSettings | None = None,
    pricing: PricingSettings | None = None,
    progress: Progress | None = None,
) -> MergeReport:
    """Сводит прайсы. Ошибки в настройках — PriceListError с понятным текстом."""
    merge_settings = merge_settings or MergeSettings()
    pricing = pricing or PricingSettings()
    report = progress or (lambda share, text: None)

    if not sources:
        raise PriceListError("Не загружено ни одного прайса")
    names = [source.supplier.strip() for source in sources]
    if any(not name for name in names):
        raise PriceListError("У каждого прайса должно быть имя поставщика")
    if len(set(names)) != len(names):
        raise PriceListError("Имена поставщиков повторяются — переименуйте их")
    for source in sources:
        problems = source.problems()
        if problems:
            raise PriceListError(f"{source.supplier}: " + "; ".join(problems))

    offer_parts, rejected_parts, rows_read = [], [], {}
    for number, source in enumerate(sources):
        report(number / (len(sources) + 1), f"Обработка: {source.supplier}")
        table = source.table or source.reload()
        cleaned = clean_price_table(table.data, source.mapping, source.supplier.strip())
        offer_parts.append(cleaned.offers)
        rejected_parts.append(cleaned.rejected)
        rows_read[source.supplier.strip()] = len(table.data)

    report(len(sources) / (len(sources) + 1), "Сопоставление товаров")
    offers = _concat(offer_parts, OFFER_COLUMNS)
    rejected = _concat(rejected_parts, REJECTED_COLUMNS)
    merge = merge_offers(offers, merge_settings, names)

    products = merge.products.copy()
    products["markup"] = products["best_price"].map(
        lambda price: pricing.percent_for(price) if pd.notna(price) else None
    )
    products["sale_price"] = products["best_price"].map(lambda price: apply_markup(price, pricing))
    report(1.0, "Готово")
    return MergeReport(merge, products, rejected, pricing, rows_read)


def _concat(parts: list[pd.DataFrame], columns: list[str]) -> pd.DataFrame:
    """Склеивает таблицы; пустые пропускает (pandas предупреждает о них)."""
    parts = [part for part in parts if not part.empty]
    if not parts:
        return pd.DataFrame(columns=columns)
    return pd.concat(parts, ignore_index=True)
