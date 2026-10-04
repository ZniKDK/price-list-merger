"""Свод предложений разных поставщиков в общий список товаров.

Как товары находят друг друга:
1. По артикулу — после нормализации («AB-123» = «ab 123»).
2. По точному наименованию — тоже после нормализации.
3. По похожему наименованию (rapidfuzz) — если включено. Похожими
   считаются названия с оценкой не ниже порога и с одинаковыми числами
   («Кабель 3х1,5» и «Кабель 3х2,5» не склеятся, хотя буквы почти те же).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from rapidfuzz import fuzz, process

from .cleaning import OFFER_COLUMNS, name_numbers

MATCH_SKU = "артикул"
MATCH_NAME = "наименование"
MATCH_FUZZY = "похожее наименование"
MATCH_SINGLE = "только один поставщик"


@dataclass
class MergeSettings:
    """Настройки свода."""

    use_fuzzy: bool = True
    fuzzy_threshold: int = 88  # 0–100, чем выше, тем строже
    skip_out_of_stock: bool = False  # не брать цену, если остаток 0


@dataclass
class MergeResult:
    """Итог свода.

    offers — все предложения с номером группы (товара) и способом сопоставления;
    products — по строке на товар: лучшая цена и поставщик;
    suppliers — поставщики в порядке загрузки.
    """

    offers: pd.DataFrame
    products: pd.DataFrame
    suppliers: list[str]


def price_column(supplier: str) -> str:
    """Имя колонки с ценой поставщика в таблице товаров.

    Приставка нужна, чтобы поставщик с именем вроде «name» не затёр колонку.
    """
    return f"price:{supplier}"


class _Groups:
    """Группы одинаковых товаров. Хранит, кто в какой группе и чем совпал."""

    def __init__(self, size: int) -> None:
        self.group = [-1] * size
        self.match = [""] * size
        self.score = [100.0] * size
        self.members: list[list[int]] = []

    def new(self, offer: int) -> int:
        self.members.append([offer])
        self.group[offer] = len(self.members) - 1
        return self.group[offer]

    def add(self, offer: int, group: int, match: str, score: float = 100.0) -> None:
        self.members[group].append(offer)
        self.group[offer] = group
        self.match[offer] = match
        self.score[offer] = score


def merge_offers(
    offers: pd.DataFrame,
    settings: MergeSettings | None = None,
    suppliers: list[str] | None = None,
) -> MergeResult:
    """Сводит предложения всех поставщиков (одна общая таблица после очистки)."""
    settings = settings or MergeSettings()
    offers = offers.reset_index(drop=True)
    if suppliers is None:
        suppliers = list(dict.fromkeys(offers["supplier"]))
    groups = _Groups(len(offers))
    sku_keys = offers["sku_key"].tolist()
    name_keys = offers["name_key"].tolist()

    # 1. По артикулу
    by_sku: dict[str, int] = {}
    for index, key in enumerate(sku_keys):
        if not key:
            continue
        if key in by_sku:
            groups.add(index, by_sku[key], MATCH_SKU)
        else:
            by_sku[key] = groups.new(index)

    # Все названия, под которыми товар уже встречается, — по ним ищем совпадения
    group_names: dict[str, int] = {}
    for group, members in enumerate(groups.members):
        for member in members:
            if name_keys[member]:
                group_names.setdefault(name_keys[member], group)

    # 2–3. Предложения без артикула ищем по наименованию
    choices: list[str] = list(group_names)
    for index, key in enumerate(sku_keys):
        if key:
            continue
        name = name_keys[index]
        supplier = offers.at[index, "supplier"]
        group = group_names.get(name)
        if group is not None and not _has_supplier(groups, offers, group, supplier):
            groups.add(index, group, MATCH_NAME)
            continue
        found = None
        if settings.use_fuzzy and choices:
            found = _find_similar(name, choices, group_names, groups, offers, supplier, settings)
        if found is not None:
            group, score = found
            groups.add(index, group, MATCH_FUZZY, score)
        else:
            group = groups.new(index)
        if name not in group_names:
            group_names[name] = group
            choices.append(name)

    result = offers[OFFER_COLUMNS].copy()
    result["group"] = groups.group
    result["match"] = groups.match
    result["score"] = groups.score
    sizes = result.groupby("group")["supplier"].transform("nunique")
    result.loc[sizes == 1, "match"] = MATCH_SINGLE
    # Первое предложение группы получает самый надёжный из способов,
    # которыми к нему присоединились (артикул надёжнее названия)
    rank = {MATCH_SKU: 0, MATCH_NAME: 1, MATCH_FUZZY: 2}
    best_rank = result["match"].map(rank).groupby(result["group"]).transform("min")
    by_rank = {value: key for key, value in rank.items()}
    result["match"] = result["match"].where(result["match"] != "", best_rank.map(by_rank).fillna(""))

    result["usable"] = result["price"].notna()
    if settings.skip_out_of_stock:
        result["usable"] &= result["stock"].ne(0)
    result["best"] = _mark_best(result)
    return MergeResult(result, _build_products(result, suppliers), suppliers)


def _has_supplier(groups: _Groups, offers: pd.DataFrame, group: int, supplier: str) -> bool:
    """Есть ли в группе уже товар этого поставщика (два его товара не склеиваем)."""
    return any(offers.at[member, "supplier"] == supplier for member in groups.members[group])


def _find_similar(name, choices, group_names, groups, offers, supplier, settings):
    """Ищет группу с похожим названием. Возвращает (группа, оценка) или None."""
    numbers = name_numbers(name)
    # Берём несколько лучших кандидатов: первый может не подойти по числам
    candidates = process.extract(
        name, choices, scorer=fuzz.token_sort_ratio,
        score_cutoff=settings.fuzzy_threshold, limit=5,
    )
    for choice, score, _position in candidates:
        group = group_names[choice]
        if name_numbers(choice) != numbers:
            continue
        if _has_supplier(groups, offers, group, supplier):
            continue
        return group, round(score, 1)
    return None


def _mark_best(offers: pd.DataFrame) -> pd.Series:
    """Отмечает в каждой группе предложение с минимальной ценой."""
    best = pd.Series(False, index=offers.index)
    usable = offers[offers["usable"]]
    if not usable.empty:
        # При равной цене побеждает поставщик, загруженный раньше (стабильная сортировка)
        winners = usable.sort_values("price", kind="stable").groupby("group").head(1).index
        best[winners] = True
    return best


def _first_filled(values: pd.Series) -> str:
    return next((value for value in values if value), "")


def _build_products(offers: pd.DataFrame, suppliers: list[str]) -> pd.DataFrame:
    """Таблица товаров: артикул, название, цены всех поставщиков, лучшая цена."""
    rows = []
    for group, part in offers.groupby("group", sort=True):
        winner = part[part["best"]]
        row = {
            "group": group,
            # Артикул, название и единицу берём у поставщика, загруженного
            # первым: так итоговый прайс выглядит единообразно
            "sku": _first_filled(part["sku"]),
            "name": _first_filled(part["name"]),
            "unit": _first_filled(part["unit"]),
            "offers": part["supplier"].nunique(),
            "best_price": winner.iloc[0]["price"] if not winner.empty else None,
            "best_supplier": winner.iloc[0]["supplier"] if not winner.empty else "",
        }
        for supplier in suppliers:
            prices = part.loc[part["supplier"] == supplier, "price"]
            row[price_column(supplier)] = prices.min() if not prices.empty else None
        rows.append(row)
    columns = ["group", "sku", "name", "unit", "offers", "best_price", "best_supplier"]
    columns += [price_column(supplier) for supplier in suppliers]
    return pd.DataFrame(rows, columns=columns)
