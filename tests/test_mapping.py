"""Тесты автоподбора колонок."""

import pytest

from price_list_merger.core.mapping import (
    FIELD_BY_KEY, NAME, PRICE, SKU, STOCK, UNIT,
    guess_mapping, header_score, mapping_problems, normalize_header,
)


@pytest.mark.parametrize("text, expected", [
    ("Цена, руб.", "цена руб"),
    ("Кол-во", "кол во"),
    ("  Ед. изм. ", "ед изм"),
    ("Наименование (ёмкость)", "наименование емкость"),
])
def test_normalize_header(text, expected):
    assert normalize_header(text) == expected


def test_guess_mapping_typical_headers():
    columns = ["Артикул", "Наименование товара", "Ед.", "Цена, руб.", "Остаток"]
    assert guess_mapping(columns) == {
        SKU: "Артикул", NAME: "Наименование товара", UNIT: "Ед.",
        PRICE: "Цена, руб.", STOCK: "Остаток",
    }


def test_guess_mapping_other_wording():
    columns = ["Код товара", "Номенклатура", "Стоимость (₽)", "Кол-во"]
    mapping = guess_mapping(columns)
    assert mapping[SKU] == "Код товара"
    assert mapping[NAME] == "Номенклатура"
    assert mapping[PRICE] == "Стоимость (₽)"
    assert mapping[STOCK] == "Кол-во"


def test_guess_mapping_prefers_typical_synonym():
    # Есть и «Описание», и «Наименование» — наименование важнее
    mapping = guess_mapping(["Описание", "Наименование", "Цена"])
    assert mapping[NAME] == "Наименование"


def test_guess_mapping_one_column_one_field():
    mapping = guess_mapping(["Цена", "Цена опт"])
    assert list(mapping.values()).count("Цена") == 1


def test_guess_mapping_ignores_unknown_columns():
    assert guess_mapping(["Фото", "Колонка 3"]) == {}


def test_header_score_partial_match():
    price = FIELD_BY_KEY[PRICE]
    assert header_score("Цена закупки", price) == 80
    assert header_score("Розничная цена", price) == 60
    assert header_score("Фото", price) == 0


def test_mapping_problems():
    assert mapping_problems({SKU: "A", PRICE: "B"}) == []
    assert "не выбрана колонка с ценой" in mapping_problems({SKU: "A"})
    assert "нужна колонка с артикулом или наименованием" in mapping_problems({PRICE: "B"})
    assert "одна колонка выбрана для нескольких полей" in mapping_problems(
        {SKU: "A", NAME: "A", PRICE: "B"}
    )
