"""Скриншоты окна для README: проходит все шаги мастера на демо-прайсах
в светлой и тёмной теме.

Профили и настройки — во временной папке, настоящие не трогаются.
Запуск: python tools/screenshots.py  →  docs/screenshots/light/*.png и dark/*.png
"""

import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from price_list_merger.gui import animations
from price_list_merger.gui.main_window import COLUMNS, SETTINGS, MainWindow
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


def capture(app: QApplication, theme: str) -> None:
    """Проходит мастер в одной теме и сохраняет скриншоты в docs/screenshots/<тема>."""
    folder = OUTPUT / theme
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        settings = QSettings(str(Path(temp) / "settings.ini"), QSettings.Format.IniFormat)
        settings.setValue("ui/theme", theme)
        window = MainWindow(ProfileStore(Path(temp) / "profiles.json"), settings)
        window.resize(1280, 780)
        window.show()

        def shot(name: str) -> None:
            app.processEvents()
            window.grab().save(str(folder / f"{name}.png"))
            print("Скриншот:", theme, name)

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


def main() -> None:
    app = QApplication(sys.argv)
    animations.set_enabled(False)  # снимаем конечное состояние, а не середину анимации
    for theme in ("light", "dark"):
        capture(app, theme)


if __name__ == "__main__":
    main()
