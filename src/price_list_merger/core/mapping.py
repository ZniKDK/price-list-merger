"""Сопоставление колонок прайса с полями программы.

У каждого поставщика колонки называются по-своему: «Артикул», «Код товара»,
«Арт.»; «Цена, руб.», «Стоимость», «Опт». Здесь собраны синонимы и функция,
которая по заголовкам сама угадывает, какая колонка за что отвечает.
Пользователь потом может поправить выбор в окне программы.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Поля, которые программа понимает. Порядок важен: так они идут в интерфейсе.
SKU = "sku"
NAME = "name"
PRICE = "price"
STOCK = "stock"
UNIT = "unit"


@dataclass(frozen=True)
class Field:
    """Описание поля: ключ, подпись для пользователя и синонимы заголовков."""

    key: str
    label: str
    synonyms: tuple[str, ...]
    required: bool = False


FIELDS: tuple[Field, ...] = (
    Field(SKU, "Артикул", (
        "артикул", "арт", "код", "код товара", "артикул поставщика",
        "код номенклатуры", "sku", "article", "art", "part number", "pn",
        "каталожный номер",
    )),
    Field(NAME, "Наименование", (
        "наименование", "название", "наименование товара", "товар",
        "номенклатура", "описание", "name", "product", "title",
    )),
    Field(PRICE, "Цена", (
        "цена", "стоимость", "цена руб", "цена с ндс", "опт", "оптовая цена",
        "цена опт", "price", "cost", "руб",
    ), required=True),
    Field(STOCK, "Остаток", (
        "остаток", "наличие", "кол во", "количество", "склад", "в наличии",
        "stock", "qty", "quantity",
    )),
    Field(UNIT, "Ед. изм.", (
        "ед", "ед изм", "единица", "единица измерения", "unit", "уп",
    )),
)

FIELD_BY_KEY = {field.key: field for field in FIELDS}

# Ключ — поле программы, значение — название колонки в файле поставщика.
Mapping = dict[str, str]


def normalize_header(text: object) -> str:
    """Приводит заголовок к простому виду для сравнения.

    «Цена, руб.» → «цена руб», «Кол-во» → «кол во», «Ед. изм.» → «ед изм».
    """
    value = str(text).lower().replace("ё", "е")
    # Всё, что не буква и не цифра, превращаем в пробел
    value = re.sub(r"[^0-9a-zа-я]+", " ", value)
    return value.strip()


def header_score(header: object, field: Field) -> int:
    """Насколько заголовок похож на поле: 0 — не похож, до 100 — точное совпадение."""
    norm = normalize_header(header)
    if not norm:
        return 0
    best = 0
    for index, synonym in enumerate(field.synonyms):
        if norm == synonym:
            # Синонимы в начале списка — самые типичные, они важнее
            # («Наименование» лучше «Описания», если в файле есть обе колонки)
            return 100 - index
        words = norm.split()
        # Синоним — первое слово заголовка («Цена опт», «Артикул поставщика»)
        if words and words[0] == synonym:
            best = max(best, 80)
        # Синоним целиком встречается среди слов («Розничная цена»)
        elif f" {synonym} " in f" {norm} ":
            best = max(best, 60)
    return best


def guess_mapping(columns: list[str]) -> Mapping:
    """Угадывает сопоставление колонок по заголовкам.

    Одна колонка не может достаться двум полям: сначала раздаём самые
    уверенные совпадения, потом остальные.
    """
    candidates = []
    for field in FIELDS:
        for column in columns:
            score = header_score(column, field)
            if score:
                candidates.append((score, field.key, column))
    # Сначала лучшие совпадения; при равенстве — та колонка, что левее
    candidates.sort(key=lambda item: (-item[0], columns.index(item[2])))

    mapping: Mapping = {}
    used_columns: set[str] = set()
    for _score, key, column in candidates:
        if key in mapping or column in used_columns:
            continue
        mapping[key] = column
        used_columns.add(column)
    return mapping


def mapping_problems(mapping: Mapping) -> list[str]:
    """Проверяет сопоставление и возвращает список понятных ошибок."""
    problems = []
    if not mapping.get(PRICE):
        problems.append("не выбрана колонка с ценой")
    if not mapping.get(SKU) and not mapping.get(NAME):
        problems.append("нужна колонка с артикулом или наименованием")
    chosen = [column for column in mapping.values() if column]
    if len(chosen) != len(set(chosen)):
        problems.append("одна колонка выбрана для нескольких полей")
    return problems


def count_header_matches(row: list[object]) -> int:
    """Сколько ячеек строки похожи на заголовки полей (для поиска шапки)."""
    matches = 0
    for cell in row:
        if any(header_score(cell, field) >= 60 for field in FIELDS):
            matches += 1
    return matches
