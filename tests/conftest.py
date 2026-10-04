"""Общие заготовки для тестов."""

import csv

import pytest
from openpyxl import Workbook

from price_list_merger.demo import create_demo_files


@pytest.fixture
def make_xlsx(tmp_path):
    """Создаёт .xlsx из списка строк: make_xlsx("a.xlsx", [[...], [...]])."""

    def factory(name, rows, sheet_title="Лист1", extra_sheets=None):
        book = Workbook()
        sheet = book.active
        sheet.title = sheet_title
        for row in rows:
            sheet.append(row)
        for title, extra_rows in (extra_sheets or {}).items():
            extra = book.create_sheet(title)
            for row in extra_rows:
                extra.append(row)
        path = tmp_path / name
        book.save(path)
        return path

    return factory


@pytest.fixture
def make_csv(tmp_path):
    """Создаёт CSV в нужной кодировке и с нужным разделителем."""

    def factory(name, rows, encoding="utf-8", delimiter=";"):
        path = tmp_path / name
        with path.open("w", encoding=encoding, newline="") as file:
            csv.writer(file, delimiter=delimiter).writerows(rows)
        return path

    return factory


@pytest.fixture
def demo_files(tmp_path):
    """Три демо-прайса: ЭлектроОпт, СтройСнаб, ТехноМаркет."""
    return create_demo_files(tmp_path / "demo")
