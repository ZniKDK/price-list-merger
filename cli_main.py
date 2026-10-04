"""Точка входа консольной версии для PyInstaller (PriceListMerger-cli.exe).

Обычный запуск из консоли: python -m price_list_merger.cli
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from price_list_merger.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
