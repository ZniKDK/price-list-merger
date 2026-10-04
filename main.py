"""Точка входа для PyInstaller и запуска из PyCharm (Run 'main').

Обычный запуск из консоли: python -m price_list_merger
"""

import sys
from pathlib import Path

# Чтобы работало без установки пакета: добавляем папку src в пути поиска
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from price_list_merger.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
