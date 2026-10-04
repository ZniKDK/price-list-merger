"""Скриншоты окна для README: проходит все шаги мастера на демо-прайсах.

Профили и настройки — во временной папке, настоящие не трогаются.
Запуск: python tools/screenshots.py  →  docs/screenshots/*.png
"""

import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from price_list_merger.gui.main_window import COLUMNS, SETTINGS, MainWindow
from price_list_merger.gui.style import apply_theme
from price_list_merger.profiles import ProfileStore

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "screenshots"


def wait_for(app: QApplication, condition, timeout_ms: int = 20000) -> None:
    """Крутит цикл событий, пока condition() не станет истинным."""
    import time

    deadline = time.monotonic() + timeout_ms / 1000
    while not condition():
        if time.monotonic() > deadline:
            raise TimeoutError("окно не ответило вовремя")
        app.processEvents()
        time.sleep(0.01)


def main() -> None:
    app = QApplication(sys.argv)
    apply_theme(app)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp:
        settings = QSettings(str(Path(temp) / "settings.ini"), QSettings.Format.IniFormat)
        window = MainWindow(ProfileStore(Path(temp) / "profiles.json"), settings)
        window.resize(1280, 780)
        window.show()

        def shot(name: str) -> None:
            app.processEvents()
            window.grab().save(str(OUTPUT / f"{name}.png"))
            print("Скриншот:", name)

        shot("0-start")
        window.files_page.load_demo()
        shot("1-files")
        window.go_to(COLUMNS)
        window.columns_page.supplier_box.setCurrentIndex(0)
        shot("2-columns")
        window.go_to(SETTINGS)
        shot("3-settings")
        window.run_merge()
        wait_for(app, lambda: window.report is not None and window.worker is None)
        shot("4-result")
        window.result_page.tabs.setCurrentIndex(1)
        shot("5-offers")
        window.close()


if __name__ == "__main__":
    main()
