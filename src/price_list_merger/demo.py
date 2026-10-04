"""Генератор демонстрационных прайсов.

Три вымышленных поставщика электротоваров, у каждого свой формат —
как в жизни:
- «ЭлектроОпт» (.xlsx): шапка с названием фирмы, таблица с 5-й строки,
  цены числами, есть разделы и пустые строки;
- «СтройСнаб» (.csv, Windows-1251, «;»): артикулы в другом написании,
  цены текстом «1 234,50», остаток словами;
- «ТехноМаркет» (.xlsx): артикулов нет совсем, названия чуть отличаются,
  цены вида «1 299 ₽», несколько строк «по запросу».

Все названия фирм и цены выдуманы. Запуск: python -m price_list_merger.demo
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

# Каталог: артикул, наименование, единица, базовая цена
CATALOG = [
    ("VVG-325", "Кабель ВВГнг-LS 3х2,5 мм²", "м", 98.0),
    ("VVG-315", "Кабель ВВГнг-LS 3х1,5 мм²", "м", 64.0),
    ("VVG-525", "Кабель ВВГнг-LS 5х2,5 мм²", "м", 165.0),
    ("PVS-375", "Провод ПВС 3х0,75 мм²", "м", 41.0),
    ("PVS-315", "Провод ПВС 3х1,5 мм²", "м", 72.0),
    ("AV-1P16", "Автоматический выключатель 1P 16А C", "шт", 189.0),
    ("AV-1P25", "Автоматический выключатель 1P 25А C", "шт", 195.0),
    ("AV-3P32", "Автоматический выключатель 3P 32А C", "шт", 720.0),
    ("UZO-2P40", "УЗО 2P 40А 30мА", "шт", 1450.0),
    ("DIF-1P16", "Дифавтомат 1P+N 16А 30мА", "шт", 1690.0),
    ("ROZ-2Z", "Розетка двойная с заземлением белая", "шт", 245.0),
    ("ROZ-1Z", "Розетка одинарная с заземлением белая", "шт", 159.0),
    ("VYK-1", "Выключатель одноклавишный белый", "шт", 129.0),
    ("VYK-2", "Выключатель двухклавишный белый", "шт", 169.0),
    ("KOR-20", "Гофротруба ПВХ 20 мм", "м", 12.5),
    ("KOR-25", "Гофротруба ПВХ 25 мм", "м", 17.0),
    ("KAB-16", "Кабель-канал 16х16 мм", "м", 38.0),
    ("KAB-40", "Кабель-канал 40х25 мм", "м", 86.0),
    ("SHR-12", "Щит распределительный на 12 модулей", "шт", 980.0),
    ("SHR-24", "Щит распределительный на 24 модуля", "шт", 1750.0),
    ("LED-A60-10", "Лампа светодиодная A60 10 Вт E27", "шт", 79.0),
    ("LED-A60-15", "Лампа светодиодная A60 15 Вт E27", "шт", 105.0),
    ("LED-PNL-36", "Панель светодиодная 36 Вт 595х595", "шт", 1190.0),
    ("PRJ-50", "Прожектор светодиодный 50 Вт IP65", "шт", 890.0),
    ("UDL-3", "Удлинитель 3 розетки 3 м", "шт", 420.0),
    ("UDL-5", "Удлинитель 5 розеток 5 м", "шт", 690.0),
    ("IZL-19", "Изолента ПВХ 19 мм синяя", "шт", 45.0),
    ("KLM-222", "Клемма соединительная 2-проводная", "шт", 14.0),
    ("KLM-223", "Клемма соединительная 3-проводная", "шт", 18.0),
    ("STB-500", "Стабилизатор напряжения 500 ВА", "шт", 3290.0),
]

# Как «СтройСнаб» пишет артикулы: строчными, через пробел, иногда
# с русскими буквами вместо латинских («КАВ-16» набран кириллицей)
_STROYSNAB_SKU = {"VVG-325": "vvg 325", "AV-1P16": "av 1p16", "ROZ-2Z": "roz2z", "KAB-16": "КАВ-16"}

# Как «ТехноМаркет» переименовывает товары (артикулов у него нет)
_TECHNO_NAMES = {
    "Кабель ВВГнг-LS 3х2,5 мм²": "ВВГнг-LS кабель 3*2.5 мм2",
    "Провод ПВС 3х1,5 мм²": "Провод ПВС 3x1.5",
    "Автоматический выключатель 1P 16А C": "Выключатель автоматический 1P 16А C",
    "Розетка двойная с заземлением белая": "Розетка двойная белая с заземлением",
    "Лампа светодиодная A60 10 Вт E27": "Лампа LED A60 10 Вт E27",
    "Удлинитель 3 розетки 3 м": "Удлинитель на 3 розетки, 3 м",
}


def _price(base: float, rng: random.Random) -> float:
    """Цена поставщика: базовая ± 12%."""
    return round(base * rng.uniform(0.88, 1.12), 2)


def _money_text(value: float) -> str:
    """1234.5 → «1 234,50» — так цены часто выгружают из 1С."""
    whole, cents = f"{value:.2f}".split(".")
    groups = f"{int(whole):,}".replace(",", " ")
    return f"{groups},{cents}"


def write_elektroopt(path: Path, rng: random.Random) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "Прайс"
    sheet.append(["ЭлектроОпт — оптовый склад электротоваров (вымышленная компания)"])
    sheet["A1"].font = Font(bold=True, size=14)
    sheet.append(["Прайс-лист действителен на текущую неделю. Цены в рублях с НДС."])
    sheet.append([])
    sheet.append([])
    sheet.append(["Артикул", "Наименование товара", "Ед.", "Цена, руб.", "Остаток"])
    for cell in sheet[5]:
        cell.font = Font(bold=True)
    sections = {0: "Кабель и провод", 5: "Автоматика", 11: "Электроустановочные изделия"}
    for index, (sku, name, unit, base) in enumerate(CATALOG[:24]):
        if index in sections:
            sheet.append([])
            sheet.append([None, sections[index]])
        stock = rng.choice([0, 3, 12, 50, 120, 400])
        sheet.append([sku, name, unit, _price(base, rng), stock])
    sheet.column_dimensions["B"].width = 45
    book.save(path)


def write_stroysnab(path: Path, rng: random.Random) -> None:
    rows = [["Код товара", "Номенклатура", "Цена", "Наличие"]]
    for sku, name, _unit, base in CATALOG[:18] + CATALOG[24:]:
        code = _STROYSNAB_SKU.get(sku, sku.lower())
        stock = rng.choice(["есть", "нет", "много", "15", "под заказ"])
        # «²» в Windows-1251 нет — 1С в таких выгрузках пишет «мм2»
        rows.append([code, name.replace("²", "2"), _money_text(_price(base, rng)), stock])
    # Типичные «грязные» строки: без цены и повтор товара
    rows.append(["DOST-1", "Доставка по городу", "", ""])
    rows.append(["kor-20", "Гофротруба ПВХ 20 мм (бухта)", _money_text(11.9), "есть"])
    with path.open("w", encoding="cp1251", newline="") as file:
        csv.writer(file, delimiter=";").writerows(rows)


def write_technomarket(path: Path, rng: random.Random) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "Товары"
    sheet.append(["Название", "Стоимость (₽)", "Кол-во"])
    for _sku, name, _unit, base in CATALOG[::2] + [CATALOG[3], CATALOG[5]]:
        title = _TECHNO_NAMES.get(name, name)
        price = "по запросу" if base > 3000 else f"{_money_text(_price(base, rng))[:-3]} ₽"
        sheet.append([title, price, rng.choice([1, 5, 20, 100])])
    sheet.append(["Кабель ВВГнг-LS 3х1,5 мм² (бухта 100 м)", "6 100 ₽", 4])
    book.save(path)


DEMO_FILES = {
    "ЭлектроОпт.xlsx": write_elektroopt,
    "СтройСнаб.csv": write_stroysnab,
    "ТехноМаркет.xlsx": write_technomarket,
}


def create_demo_files(folder: str | Path, seed: int = 2026) -> list[Path]:
    """Создаёт демо-прайсы в папке и возвращает пути к ним."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)  # одинаковый seed — одинаковые файлы
    paths = []
    for name, writer in DEMO_FILES.items():
        path = folder / name
        writer(path, rng)
        paths.append(path)
    return paths


def main() -> None:
    folder = Path(__file__).resolve().parents[2] / "demo"
    for path in create_demo_files(folder):
        print(f"Создан {path}")


if __name__ == "__main__":
    main()
