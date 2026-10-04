"""Очистка данных прайса.

Цены приходят в любом виде: 1234.5, «1 234,50 ₽», «1.234,50», «по запросу».
Артикулы — «AB-123», «ab 123», «АВ123» (с русскими буквами). Здесь всё
это приводится к одному виду, чтобы одинаковые товары разных поставщиков
можно было найти и сравнить.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from .mapping import NAME, PRICE, SKU, STOCK, UNIT, Mapping

# Русские буквы, которые пишутся так же, как латинские. В артикулах их
# часто путают: «АВ-100» набрано кириллицей, «AB-100» — латиницей.
_LOOKALIKES = str.maketrans("АВЕКМНОРСТУХ", "ABEKMHOPCTYX")

# Слова, означающие «товара нет»
_OUT_OF_STOCK = {"нет", "отсутствует", "нет в наличии", "под заказ", "0"}

# Колонки таблицы предложений после очистки
OFFER_COLUMNS = [
    "supplier", "row", "sku", "name", "price", "stock", "unit", "sku_key", "name_key",
]
REJECTED_COLUMNS = ["supplier", "row", "reason", "content"]


def parse_price(value: object) -> float | None:
    """Превращает цену из прайса в число. Не получилось — None.

    >>> parse_price("1 234,50 ₽")
    1234.5
    >>> parse_price("по запросу") is None
    True
    """
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        return number if number > 0 and number == number else None

    text = str(value).strip()
    if not text:
        return None
    # Оставляем только цифры, запятые, точки и минус. Пробелы (в том числе
    # неразрывные), апострофы, «руб.», «₽» — всё это разделители или мусор.
    text = re.sub(r"[^\d,.\-]", "", text)
    if not re.search(r"\d", text):
        return None
    # Минус допустим только в начале; «100-200» — это диапазон, а не цена
    if "-" in text[1:]:
        return None
    text = text.strip(".,")

    if "," in text and "." in text:
        # Десятичный разделитель — тот, что правее: «1.234,50» или «1,234.50»
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif text.count(",") > 1:
        text = text.replace(",", "")  # «1,234,567» — разделители тысяч
    elif "," in text:
        text = text.replace(",", ".")  # в России запятая — десятичная
    elif text.count(".") > 1:
        text = text.replace(".", "")  # «1.234.567»

    try:
        number = float(text)
    except ValueError:
        return None
    return round(number, 2) if number > 0 else None


def parse_stock(value: object) -> float | None:
    """Остаток на складе: число, 0 для «нет» или None, если непонятно («много»)."""
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in _OUT_OF_STOCK:
        return 0.0
    match = re.search(r"\d+(?:[.,]\d+)?", text)
    if not match:
        return None
    return float(match.group().replace(",", "."))


def normalize_sku(value: object) -> str:
    """Ключ артикула для сравнения: «ab-12.3» и «AB 123» → «AB123»."""
    text = str(value or "").upper().replace("Ё", "Е")
    text = text.translate(_LOOKALIKES)
    return re.sub(r"[^0-9A-ZА-Я]", "", text)


def normalize_name(value: object) -> str:
    """Ключ наименования для сравнения.

    «Кабель ВВГнг 3х2,5 мм²» → «кабель ввгнг 3x2.5 мм»: нижний регистр,
    «х», «*», «×» между числами → «x», десятичная запятая → точка,
    степень у единиц («мм2», «м³») и знаки препинания убраны.
    """
    text = str(value or "").lower().replace("ё", "е")
    # «мм²» и «мм2» — одна и та же единица; степень убираем,
    # иначе «2» из «мм2» попадёт в числа товара и сломает сравнение
    # (только после числа: «2,5 мм2», но не «винт M2»)
    text = re.sub(r"(\d\s*(?:мм|см|м|mm|cm|m))[²³23](?![0-9])", r"\1", text)
    text = re.sub(r"(?<=\d)\s*[xх×*]\s*(?=\d)", "x", text)
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)
    # Точку оставляем только внутри чисел, остальное — в пробелы
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)
    text = re.sub(r"[^0-9a-zа-я.]+", " ", text)
    return " ".join(text.split())


def name_numbers(name_key: str) -> tuple[str, ...]:
    """Числа из наименования: «кабель 3x2.5 100 м» → ('3', '2.5', '100').

    Нужны для защиты от ложных совпадений: «Кабель 3х1,5» и «Кабель 3х2,5»
    похожи по буквам на 95%, но это разные товары.
    """
    return tuple(sorted(re.findall(r"\d+(?:\.\d+)?", name_key)))


@dataclass
class CleanResult:
    """Итог очистки одного прайса: годные предложения и отброшенные строки."""

    offers: pd.DataFrame
    rejected: pd.DataFrame


def clean_price_table(data: pd.DataFrame, mapping: Mapping, supplier: str) -> CleanResult:
    """Берёт нужные колонки, чистит значения и отбрасывает негодные строки.

    data — таблица с заголовками (индекс — номер строки в исходном файле),
    mapping — какие колонки за что отвечают, supplier — имя поставщика.
    """

    def column(key: str) -> pd.Series:
        name = mapping.get(key)
        if name and name in data.columns:
            return data[name].astype(str).str.strip()
        return pd.Series("", index=data.index, dtype=object)

    raw_price = column(PRICE)
    offers = pd.DataFrame({
        "supplier": supplier,
        "row": data.index.astype(int),
        "sku": column(SKU),
        "name": column(NAME),
        "price": raw_price.map(parse_price),
        "stock": column(STOCK).map(parse_stock),
        "unit": column(UNIT),
    }, index=data.index)
    offers["sku_key"] = offers["sku"].map(normalize_sku)
    offers["name_key"] = offers["name"].map(normalize_name)

    rejected = []

    def reject(mask: pd.Series, reason) -> None:
        """Переносит строки из offers в список отброшенных с причиной."""
        nonlocal offers
        for index in offers.index[mask]:
            text = reason(index) if callable(reason) else reason
            content = " | ".join(value for value in data.loc[index] if value)
            rejected.append((supplier, int(index), text, content))
        offers = offers[~mask]

    no_id = (offers["sku_key"] == "") & (offers["name_key"] == "")
    reject(no_id, "нет артикула и наименования")

    def no_price_reason(index) -> str:
        if raw_price[index]:
            return f"цена не распознана: «{raw_price[index]}»"
        # Одна заполненная ячейка — обычно заголовок раздела («Кабель и провод»)
        if sum(1 for value in data.loc[index] if value) == 1:
            return "заголовок раздела (пропущен)"
        return "нет цены"

    reject(offers["price"].isna(), no_price_reason)

    # Дубли внутри одного прайса: оставляем самую низкую цену
    key = offers["sku_key"].where(offers["sku_key"] != "", "name:" + offers["name_key"])
    order = offers.assign(_key=key).sort_values(["_key", "price"], kind="stable")
    duplicate_index = order.index[order["_key"].duplicated()]
    reject(offers.index.isin(duplicate_index), "повтор товара в прайсе (оставлена меньшая цена)")

    offers = offers[OFFER_COLUMNS].sort_index().reset_index(drop=True)
    rejected_frame = pd.DataFrame(rejected, columns=REJECTED_COLUMNS, dtype=object)
    return CleanResult(offers, rejected_frame)
