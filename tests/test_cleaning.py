"""Тесты очистки данных."""

import pandas as pd
import pytest

from price_list_merger.core.cleaning import (
    clean_price_table, name_numbers, normalize_name, normalize_sku, parse_price, parse_stock,
)
from price_list_merger.core.mapping import NAME, PRICE, SKU, STOCK


@pytest.mark.parametrize("value, expected", [
    ("1234.5", 1234.5),
    ("1 234,50", 1234.5),
    ("1 234,50 ₽", 1234.5),  # неразрывный пробел
    ("1.234,50", 1234.5),
    ("1,234.50", 1234.5),
    ("1,234,567", 1234567.0),
    ("1.234.567", 1234567.0),
    ("руб. 99", 99.0),
    ("от 150 руб.", 150.0),
    ("12,3456", 12.35),
    (250, 250.0),
    (99.999, 99.999),
])
def test_parse_price_valid(value, expected):
    assert parse_price(value) == pytest.approx(expected)


@pytest.mark.parametrize("value", [
    None, "", "по запросу", "звоните", "0", "-5", "100-200", float("nan"), 0, True,
])
def test_parse_price_invalid(value):
    assert parse_price(value) is None


@pytest.mark.parametrize("value, expected", [
    ("15", 15.0), (">10", 10.0), ("2,5", 2.5), ("нет", 0.0), ("Под заказ", 0.0),
    ("много", None), ("", None), (None, None),
])
def test_parse_stock(value, expected):
    assert parse_stock(value) == expected


@pytest.mark.parametrize("value, expected", [
    ("AB-123", "AB123"),
    ("ab 12.3", "AB123"),
    ("АВ-123", "AB123"),  # русские А и В
    ("КАВ-16", "KAB16"),
    ("  x/y_z ", "XYZ"),
    ("", ""),
    (None, ""),
])
def test_normalize_sku(value, expected):
    assert normalize_sku(value) == expected


@pytest.mark.parametrize("value, expected", [
    ("Кабель ВВГнг 3х2,5 мм²", "кабель ввгнг 3x2.5 мм"),
    ("ВВГнг кабель 3*2.5 мм2", "ввгнг кабель 3x2.5 мм"),
    ("Плитка 30 × 30 см, 1 м²", "плитка 30x30 см 1 м"),
    ("Винт M2 DIN", "винт m2 din"),
    ("Ёлка. Новая!", "елка новая"),
])
def test_normalize_name(value, expected):
    assert normalize_name(value) == expected


def test_name_numbers():
    assert name_numbers("кабель 3x2.5 мм 100 м") == ("100", "2.5", "3")
    assert name_numbers("кабель 3x1.5") != name_numbers("кабель 3x2.5")


def _table(rows, columns=("Код", "Название", "Цена", "Наличие"), start=2):
    """Таблица как после чтения файла: всё строки, индекс — номер строки."""
    frame = pd.DataFrame(rows, columns=list(columns), dtype=object)
    frame.index = range(start, start + len(rows))
    return frame


MAPPING = {SKU: "Код", NAME: "Название", PRICE: "Цена", STOCK: "Наличие"}


def test_clean_keeps_good_rows():
    data = _table([["a-1", "Товар", "1 000,00", "5"], ["B2", "Другой", "50", ""]])
    result = clean_price_table(data, MAPPING, "Поставщик")
    offers = result.offers
    assert offers["price"].tolist() == [1000.0, 50.0]
    assert offers["sku_key"].tolist() == ["A1", "B2"]
    assert offers["row"].tolist() == [2, 3]
    assert offers["supplier"].unique().tolist() == ["Поставщик"]
    assert offers["stock"].iloc[0] == 5.0
    assert result.rejected.empty


def test_clean_rejects_with_reasons():
    data = _table([
        ["", "", "100", ""],  # ни артикула, ни названия
        ["A1", "Товар", "", ""],  # нет цены
        ["A2", "Товар 2", "по запросу", ""],  # цена текстом
        ["", "Кабель и провод", "", ""],  # заголовок раздела
    ])
    result = clean_price_table(data, MAPPING, "П")
    assert result.offers.empty
    reasons = dict(zip(result.rejected["row"], result.rejected["reason"]))
    assert reasons[2] == "нет артикула и наименования"
    assert reasons[3] == "нет цены"
    assert reasons[4] == "цена не распознана: «по запросу»"
    assert reasons[5] == "заголовок раздела (пропущен)"


def test_clean_duplicates_keep_lowest_price():
    data = _table([
        ["A-1", "Товар", "120", ""],
        ["a1", "Товар (упак.)", "100", ""],
        ["", "Без артикула", "10", ""],
        ["", "без  артикула", "9", ""],
    ])
    result = clean_price_table(data, MAPPING, "П")
    assert sorted(result.offers["price"].tolist()) == [9.0, 100.0]
    assert result.rejected["row"].tolist() == [2, 4]
    assert result.rejected["reason"].str.startswith("повтор товара").all()


def test_clean_without_optional_columns():
    data = _table([["Товар", "10"]], columns=("Название", "Цена"))
    result = clean_price_table(data, {NAME: "Название", PRICE: "Цена"}, "П")
    assert result.offers["sku"].tolist() == [""]
    assert pd.isna(result.offers["stock"].iloc[0])
