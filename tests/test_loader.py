"""Тесты чтения файлов."""

import pytest

from price_list_merger.core.loader import (
    PriceListError, apply_header, find_header_row, load_price_list, read_raw,
)


def test_xlsx_header_found_below_title(make_xlsx):
    path = make_xlsx("p.xlsx", [
        ["ООО Ромашка — прайс-лист"],
        [],
        ["Артикул", "Наименование", "Цена"],
        ["A-1", "Товар 1", 100],
        ["A-2", "Товар 2", 250.5],
    ])
    table = load_price_list(path)
    assert table.header_row == 2
    assert table.columns == ["Артикул", "Наименование", "Цена"]
    assert table.data["Цена"].tolist() == ["100", "250.5"]
    # Индекс — номер строки в Excel
    assert table.data.index.tolist() == [4, 5]


def test_xlsx_integer_article_without_dot_zero(make_xlsx):
    path = make_xlsx("p.xlsx", [["Артикул", "Цена"], [12345, 10]])
    table = load_price_list(path)
    assert table.data["Артикул"].iloc[0] == "12345"


def test_xlsx_picks_sheet_with_table(make_xlsx):
    path = make_xlsx(
        "p.xlsx", [["Просто текст"], ["ещё текст"]], sheet_title="Обложка",
        extra_sheets={"Прайс": [["Код", "Название", "Цена"], ["1", "A", "5"]]},
    )
    table = load_price_list(path)
    assert table.raw.sheet == "Прайс"
    assert table.raw.sheets == ["Обложка", "Прайс"]


def test_xlsx_explicit_missing_sheet(make_xlsx):
    path = make_xlsx("p.xlsx", [["Код", "Цена"]])
    with pytest.raises(PriceListError, match="нет листа"):
        read_raw(path, sheet="Нет такого")


@pytest.mark.parametrize("encoding", ["cp1251", "utf-8", "utf-8-sig"])
def test_csv_encodings(make_csv, encoding):
    path = make_csv("p.csv", [["Код", "Наименование", "Цена"], ["1", "Ёлка", "1 200,50"]],
                    encoding=encoding)
    table = load_price_list(path)
    assert table.data["Наименование"].iloc[0] == "Ёлка"
    assert table.columns[0] == "Код"  # BOM не попал в заголовок


@pytest.mark.parametrize("delimiter", [";", ",", "\t"])
def test_csv_delimiters(make_csv, delimiter):
    rows = [["Код", "Название", "Цена"], ["1", "Товар", "10"], ["2", "Товар 2", "20"]]
    table = load_price_list(make_csv("p.csv", rows, delimiter=delimiter))
    assert table.raw.delimiter == delimiter
    assert table.columns == ["Код", "Название", "Цена"]


def test_csv_multiline_cell(make_csv):
    path = make_csv("p.csv", [["Код", "Название", "Цена"], ["1", "Строка 1\nстрока 2", "10"]])
    table = load_price_list(path)
    assert len(table.data) == 1


def test_duplicate_and_empty_headers(make_xlsx):
    path = make_xlsx("p.xlsx", [["Цена", None, "Цена"], ["1", "2", "3"]])
    table = load_price_list(path, header_row=0)
    assert table.columns == ["Цена", "Колонка 2", "Цена (2)"]


def test_empty_rows_removed(make_xlsx):
    path = make_xlsx("p.xlsx", [["Код", "Цена"], ["1", "10"], [], ["2", "20"]])
    table = load_price_list(path)
    assert table.data["Код"].tolist() == ["1", "2"]


def test_header_row_not_found_falls_back_to_first_filled(make_xlsx):
    path = make_xlsx("p.xlsx", [[None], ["Колонка А", "Колонка Б"], ["1", "2"]])
    table = load_price_list(path)
    assert table.header_row == 1


def test_find_header_row_needs_two_matches(make_xlsx):
    raw = read_raw(make_xlsx("p.xlsx", [["Цена"], ["Привет", "мир"]]))
    assert find_header_row(raw.cells) is None


def test_apply_header_out_of_range(make_xlsx):
    raw = read_raw(make_xlsx("p.xlsx", [["Код", "Цена"]]))
    with pytest.raises(PriceListError):
        apply_header(raw.cells, 5)


def test_unsupported_formats(tmp_path):
    (tmp_path / "old.xls").write_bytes(b"x")
    (tmp_path / "doc.pdf").write_bytes(b"x")
    with pytest.raises(PriceListError, match=r"\.xls"):
        read_raw(tmp_path / "old.xls")
    with pytest.raises(PriceListError, match="Неподдерживаемый"):
        read_raw(tmp_path / "doc.pdf")
    with pytest.raises(PriceListError, match="не найден"):
        read_raw(tmp_path / "nope.xlsx")


def test_broken_xlsx(tmp_path):
    path = tmp_path / "broken.xlsx"
    path.write_bytes(b"not a zip")
    with pytest.raises(PriceListError, match="Не удалось открыть"):
        read_raw(path)


def test_empty_file(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_bytes(b"")
    with pytest.raises(PriceListError, match="пустой"):
        load_price_list(path)
