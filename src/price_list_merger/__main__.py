"""Запуск окна программы: python -m price_list_merger [файлы прайсов…]

Файлы, переданные при запуске (например, перетащенные на значок программы),
сразу добавляются в список. Свод из командной строки — модуль cli.py.
"""

import sys
from pathlib import Path


def main() -> int:
    from PyQt6.QtWidgets import QApplication

    from .gui.main_window import MainWindow
    from .gui.style import apply_theme

    app = QApplication(sys.argv)
    apply_theme(app)
    window = MainWindow()
    window.show()
    files = [Path(arg) for arg in sys.argv[1:] if Path(arg).is_file()]
    if files:
        window.files_page.add_files(files)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
