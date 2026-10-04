"""Чтение прайс-листов из Excel (.xlsx) и CSV.

Прайсы поставщиков редко бывают «чистыми»: сверху логотип и название
фирмы, заголовок таблицы на пятой строке, CSV в кодировке Windows-1251
с точкой с запятой. Поэтому файл сначала читается целиком как текст
без заголовка, а строка-шапка ищется автоматически.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .mapping import count_header_matches

EXCEL_EXTENSIONS = {".xlsx", ".xlsm"}
CSV_EXTENSIONS = {".csv", ".txt"}
SUPPORTED_EXTENSIONS = EXCEL_EXTENSIONS | CSV_EXTENSIONS

# Кодировки, которые пробуем по очереди. utf-8-sig понимает и файлы с BOM.
CSV_ENCODINGS = ("utf-8-sig", "cp1251")
CSV_DELIMITERS = ";,\t|"

# В скольких первых строках ищем шапку таблицы
HEADER_SCAN_ROWS = 30


class PriceListError(Exception):
    """Файл не удалось прочитать — текст ошибки показывается пользователю."""


@dataclass
class RawTable:
    """Файл, прочитанный «как есть»: все ячейки — строки, без заголовка."""

    path: Path
    cells: pd.DataFrame
    sheet: str | None = None
    sheets: list[str] = field(default_factory=list)
    encoding: str | None = None
    delimiter: str | None = None


def read_raw(path: str | Path, sheet: str | None = None) -> RawTable:
    """Читает файл без заголовка. Для Excel можно указать лист."""
    path = Path(path)
    if not path.exists():
        raise PriceListError(f"Файл не найден: {path}")
    ext = path.suffix.lower()
    if ext in EXCEL_EXTENSIONS:
        return _read_excel(path, sheet)
    if ext in CSV_EXTENSIONS:
        return _read_csv(path)
    if ext == ".xls":
        raise PriceListError(
            "Старый формат .xls не поддерживается. Откройте файл в Excel "
            "и сохраните как .xlsx."
        )
    raise PriceListError(f"Неподдерживаемый формат файла: {path.suffix}")


def _read_excel(path: Path, sheet: str | None) -> RawTable:
    try:
        book = pd.ExcelFile(path, engine="openpyxl")
    except Exception as error:  # повреждённый файл, чужой формат и т. п.
        raise PriceListError(f"Не удалось открыть Excel-файл {path.name}: {error}") from error
    with book:
        sheets = [str(name) for name in book.sheet_names]
        if sheet is None:
            sheet = _pick_sheet(book, sheets)
        elif sheet not in sheets:
            raise PriceListError(f"В файле {path.name} нет листа «{sheet}»")
        cells = book.parse(sheet, header=None, dtype=object)
    return RawTable(path, _to_text(cells), sheet=sheet, sheets=sheets)


def _pick_sheet(book: pd.ExcelFile, sheets: list[str]) -> str:
    """Выбирает лист с прайсом: первый, на котором нашлась шапка таблицы."""
    for name in sheets:
        preview = book.parse(name, header=None, dtype=object, nrows=HEADER_SCAN_ROWS)
        if find_header_row(_to_text(preview)) is not None:
            return name
    return sheets[0]


def _read_csv(path: Path) -> RawTable:
    data = path.read_bytes()
    text, encoding = _decode(data, path)
    delimiter = _detect_delimiter(text)
    # StringIO, а не splitlines: в кавычках бывают переносы строк
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    width = max((len(row) for row in rows), default=0)
    # Строки разной длины дополняем пустыми ячейками до общей ширины
    rows = [row + [""] * (width - len(row)) for row in rows]
    cells = pd.DataFrame(rows, dtype=object)
    return RawTable(path, _to_text(cells), encoding=encoding, delimiter=delimiter)


def _decode(data: bytes, path: Path) -> tuple[str, str]:
    """Подбирает кодировку CSV: сначала UTF-8, потом Windows-1251."""
    for encoding in CSV_ENCODINGS:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise PriceListError(f"Не удалось определить кодировку файла {path.name}")


def _detect_delimiter(text: str) -> str:
    """Определяет разделитель CSV по первым строкам."""
    sample = "\n".join(text.splitlines()[:50])
    try:
        return csv.Sniffer().sniff(sample, delimiters=CSV_DELIMITERS).delimiter
    except csv.Error:
        # Sniffer не уверен — берём символ, который встречается чаще всего
        counts = {char: sample.count(char) for char in CSV_DELIMITERS}
        best = max(counts, key=counts.get)
        return best if counts[best] else ";"


def _to_text(cells: pd.DataFrame) -> pd.DataFrame:
    """Превращает все ячейки в строки; пустые ячейки — в пустую строку.

    Целые числа из Excel приходят как 12345.0 — убираем лишний «.0»,
    иначе артикул 12345 превратится в «12345.0».
    """

    def convert(value: object) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()

    result = cells.map(convert).astype(object)
    result.columns = range(result.shape[1])
    return result.reset_index(drop=True)


def find_header_row(cells: pd.DataFrame) -> int | None:
    """Ищет строку-шапку: ту, где больше всего ячеек похожи на заголовки.

    Возвращает номер строки (с нуля) или None, если ничего похожего нет.
    """
    best_row, best_matches = None, 0
    for index in range(min(HEADER_SCAN_ROWS, len(cells))):
        matches = count_header_matches(list(cells.iloc[index]))
        if matches > best_matches:
            best_row, best_matches = index, matches
    # Одно совпадение — слишком мало, это может быть случайная ячейка
    return best_row if best_matches >= 2 else None


def first_filled_row(cells: pd.DataFrame) -> int:
    """Номер первой строки, в которой заполнено хотя бы две ячейки."""
    for index in range(len(cells)):
        if sum(1 for value in cells.iloc[index] if value) >= 2:
            return index
    return 0


def apply_header(cells: pd.DataFrame, header_row: int) -> pd.DataFrame:
    """Делает строку header_row (с нуля) заголовком, данные — всё, что ниже.

    Пустые заголовки получают имя «Колонка N», повторяющиеся — номер,
    чтобы каждая колонка была уникальной.
    """
    if header_row < 0 or header_row >= len(cells):
        raise PriceListError("Строка заголовка за пределами таблицы")
    names: list[str] = []
    for position, value in enumerate(cells.iloc[header_row], start=1):
        name = str(value).strip() or f"Колонка {position}"
        base, suffix = name, 2
        while name in names:
            name = f"{base} ({suffix})"
            suffix += 1
        names.append(name)
    data = cells.iloc[header_row + 1:].copy()
    data.columns = names
    # Индекс — номер строки в исходном файле (с единицы, как в Excel),
    # чтобы в отчёте можно было написать «строка 17» и её было легко найти
    data.index = data.index + 1
    # Совсем пустые строки (разделители между разделами прайса) не нужны
    filled = (data != "").any(axis=1)
    return data[filled]


@dataclass
class PriceTable:
    """Прайс, готовый к сопоставлению: колонки с заголовками и данные."""

    raw: RawTable
    header_row: int
    data: pd.DataFrame

    @property
    def columns(self) -> list[str]:
        return [str(column) for column in self.data.columns]


def load_price_list(
    path: str | Path,
    sheet: str | None = None,
    header_row: int | None = None,
) -> PriceTable:
    """Читает прайс и находит шапку (если header_row не задан вручную)."""
    raw = read_raw(path, sheet)
    if raw.cells.empty:
        raise PriceListError(f"Файл {Path(path).name} пустой")
    if header_row is None:
        header_row = find_header_row(raw.cells)
        if header_row is None:
            header_row = first_filled_row(raw.cells)
    return PriceTable(raw, header_row, apply_header(raw.cells, header_row))
