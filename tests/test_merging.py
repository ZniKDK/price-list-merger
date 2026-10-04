"""Тесты свода предложений."""

import pandas as pd

from price_list_merger.core.cleaning import OFFER_COLUMNS, normalize_name, normalize_sku
from price_list_merger.core.merging import (
    MATCH_FUZZY, MATCH_NAME, MATCH_SINGLE, MATCH_SKU, MergeSettings, merge_offers, price_column,
)


def offers(*rows):
    """Предложения: (поставщик, артикул, название, цена[, остаток])."""
    records = []
    for number, row in enumerate(rows, start=2):
        supplier, sku, name, price, *rest = row
        records.append({
            "supplier": supplier, "row": number, "sku": sku, "name": name, "price": price,
            "stock": rest[0] if rest else None, "unit": "",
            "sku_key": normalize_sku(sku), "name_key": normalize_name(name),
        })
    return pd.DataFrame(records, columns=OFFER_COLUMNS)


def groups_of(result):
    """Группы как множества (поставщик, название) — удобно сравнивать."""
    return sorted(
        sorted(zip(part["supplier"], part["name"]))
        for _, part in result.offers.groupby("group")
    )


def test_match_by_sku_ignores_spelling():
    result = merge_offers(offers(
        ("А", "AB-1", "Товар", 100),
        ("Б", "ab 1", "Совсем другое название", 90),
        ("В", "АВ1", "", 95),  # русские буквы
    ))
    assert len(result.products) == 1
    product = result.products.iloc[0]
    assert product["best_price"] == 90
    assert product["best_supplier"] == "Б"
    assert product["offers"] == 3
    assert set(result.offers["match"]) == {MATCH_SKU}
    assert product[price_column("А")] == 100


def test_match_by_exact_name_without_sku():
    result = merge_offers(offers(
        ("А", "X1", "Розетка двойная белая", 200),
        ("Б", "", "Розетка  двойная, белая", 180),
    ))
    assert len(result.products) == 1
    assert result.offers["match"].tolist() == [MATCH_NAME, MATCH_NAME]


def test_fuzzy_match_word_order():
    result = merge_offers(offers(
        ("А", "VVG", "Кабель ВВГнг 3х2,5 мм²", 100),
        ("Б", "", "ВВГнг кабель 3*2.5 мм2", 95),
    ))
    assert len(result.products) == 1
    assert MATCH_FUZZY in set(result.offers["match"])


def test_fuzzy_does_not_merge_different_numbers():
    result = merge_offers(offers(
        ("А", "", "Кабель ВВГнг 3х2,5", 100),
        ("Б", "", "Кабель ВВГнг 3х1,5", 70),
    ))
    assert len(result.products) == 2
    assert set(result.offers["match"]) == {MATCH_SINGLE}


def test_fuzzy_can_be_disabled():
    data = offers(("А", "", "Кабель ВВГнг 3х2,5 мм²", 100), ("Б", "", "ВВГнг кабель 3*2.5", 95))
    assert len(merge_offers(data, MergeSettings(use_fuzzy=False)).products) == 2
    assert len(merge_offers(data, MergeSettings(fuzzy_threshold=60)).products) == 1


def test_same_supplier_items_not_merged_by_name():
    result = merge_offers(offers(
        ("А", "", "Лампа 10 Вт E27 тёплая", 80),
        ("А", "", "Лампа 10 Вт E27 тёплый", 85),
    ))
    assert len(result.products) == 2


def test_skip_out_of_stock():
    data = offers(("А", "S1", "Товар", 50, 0.0), ("Б", "S1", "Товар", 60, 3.0))
    assert merge_offers(data).products.iloc[0]["best_supplier"] == "А"
    result = merge_offers(data, MergeSettings(skip_out_of_stock=True))
    assert result.products.iloc[0]["best_supplier"] == "Б"
    assert result.offers["best"].tolist() == [False, True]


def test_no_usable_offer_leaves_best_empty():
    data = offers(("А", "S1", "Товар", 50, 0.0))
    product = merge_offers(data, MergeSettings(skip_out_of_stock=True)).products.iloc[0]
    assert pd.isna(product["best_price"])
    assert product["best_supplier"] == ""


def test_tie_goes_to_first_supplier():
    result = merge_offers(offers(("А", "S1", "Т", 100), ("Б", "S1", "Т", 100)))
    assert result.products.iloc[0]["best_supplier"] == "А"


def test_product_fields_from_first_supplier():
    result = merge_offers(offers(("А", "S-1", "Название А", 100), ("Б", "s1", "Название Б", 50)))
    product = result.products.iloc[0]
    assert product["sku"] == "S-1"
    assert product["name"] == "Название А"


def test_suppliers_order_kept():
    result = merge_offers(offers(("Я", "1", "Т", 1), ("А", "2", "Т2", 1)), suppliers=["Я", "А"])
    assert result.suppliers == ["Я", "А"]
    assert list(result.products.columns[-2:]) == [price_column("Я"), price_column("А")]


def test_empty_offers():
    result = merge_offers(offers(), suppliers=["А"])
    assert result.products.empty
    assert result.offers.empty
