"""Свод прайсов из командной строки — для автоматизации (планировщик, скрипты).

Пример:
    price-list-merger-cli demo/ЭлектроОпт.xlsx demo/СтройСнаб.csv -o итог.xlsx \\
        --markup 20 --tier 1000:15 --tier 10000:10 --round 9

Колонки подбираются автоматически или берутся из профилей поставщиков,
сохранённых в окне программы.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .core.exporter import export_report
from .core.loader import PriceListError
from .core.mapping import FIELDS
from .core.merging import MergeSettings
from .core.pipeline import SupplierSource, run_merge
from .core.pricing import ROUNDING_LABELS, MarkupTier, PricingSettings
from .profiles import ProfileStore


def plural(number: int, forms: tuple[str, str, str]) -> str:
    """Склонение после числа: plural(32, ("товар", "товара", "товаров")) → «32 товара»."""
    tail = number % 100
    if 11 <= tail <= 14:
        form = forms[2]
    elif tail % 10 == 1:
        form = forms[0]
    elif 2 <= tail % 10 <= 4:
        form = forms[1]
    else:
        form = forms[2]
    return f"{number} {form}"


def parse_tier(text: str) -> MarkupTier:
    """«1000:15» → от 1000 ₽ наценка 15%."""
    try:
        price, percent = text.replace(",", ".").split(":")
        return MarkupTier(float(price), float(percent))
    except ValueError:
        raise argparse.ArgumentTypeError(f"ступень наценки «{text}» — нужно ЦЕНА:ПРОЦЕНТ, например 1000:15")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="price-list-merger-cli",
        description="Сводит прайс-листы поставщиков в один Excel с минимальной ценой и наценкой.",
    )
    parser.add_argument("files", nargs="+", type=Path, help="прайсы: .xlsx, .xlsm, .csv")
    parser.add_argument("-o", "--output", type=Path, default=Path("свод_прайсов.xlsx"),
                        help="итоговый файл (по умолчанию свод_прайсов.xlsx)")
    parser.add_argument("--markup", type=float, default=0.0, help="наценка по умолчанию, %%")
    parser.add_argument("--tier", type=parse_tier, action="append", default=[],
                        metavar="ЦЕНА:ПРОЦЕНТ", help="ступень наценки, можно несколько раз")
    parser.add_argument("--round", dest="rounding", choices=list(ROUNDING_LABELS), default="none",
                        help="округление: none — до копеек, 1 — до рубля, 10 — до десятков, 9 — на …9")
    parser.add_argument("--no-fuzzy", action="store_true", help="не искать похожие наименования")
    parser.add_argument("--threshold", type=int, default=88,
                        help="порог похожести наименований 0–100 (по умолчанию 88)")
    parser.add_argument("--skip-out-of-stock", action="store_true",
                        help="не учитывать предложения с нулевым остатком")
    parser.add_argument("--no-profiles", action="store_true",
                        help="не использовать сохранённые профили поставщиков")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    # В консоли Windows русский текст иначе может превратиться в «кракозябры»
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    profiles = None if args.no_profiles else ProfileStore()

    try:
        sources = []
        for path in args.files:
            source = SupplierSource.from_file(path)
            profile = profiles.get(source.supplier) if profiles else None
            used_profile = bool(profile) and source.apply_saved(
                profile.mapping, profile.header_row, profile.sheet
            )
            columns = ", ".join(
                f"{field.label} = «{source.mapping[field.key]}»"
                for field in FIELDS if field.key in source.mapping
            )
            origin = "профиль" if used_profile else "автоподбор"
            print(f"{source.supplier}: строка заголовка {source.header_row + 1}, {origin}: {columns}")
            sources.append(source)

        report = run_merge(
            sources,
            MergeSettings(not args.no_fuzzy, args.threshold, args.skip_out_of_stock),
            PricingSettings(args.markup, args.tier, args.rounding),
        )
        output = export_report(report, args.output)
    except PriceListError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
    except PermissionError:
        print(f"Ошибка: нет доступа к {args.output} — возможно, файл открыт в Excel", file=sys.stderr)
        return 1

    stats = report.stats()
    products = plural(stats["products"], ("товар", "товара", "товаров"))
    offers = plural(stats["offers"], ("предложения", "предложений", "предложений"))
    print(
        f"Готово: {products} из {offers} "
        f"({stats['in_several']} — у нескольких поставщиков, отброшено строк: {stats['rejected']})."
    )
    print(f"Файл: {output.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
