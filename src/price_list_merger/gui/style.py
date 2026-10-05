"""Оформление: светлая и тёмная темы, таблица стилей (QSS), иконки.

QSS — это «CSS для Qt»: те же селекторы и свойства, только для виджетов.
Цвета текущей темы лежат в словаре C. При смене темы словарь
перезаполняется, таблица стилей собирается заново, а таблицы берут
цвета подсветки из C в момент отрисовки — поэтому окно перекрашивается
целиком, без пересоздания экранов.

Кроме QSS программа задаёт палитру Qt (QPalette): по ней рисуются окна
сообщений и стандартные элементы. Без неё Windows в тёмном режиме
подмешивает свои цвета, и текст сливается с фоном.

Иконки — набор Lucide (лицензия ISC, resources/icons/LICENSE-lucide.txt).
"""

from __future__ import annotations

import tempfile
from functools import cache
from pathlib import Path

from PyQt6.QtCore import QByteArray, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

RESOURCES = Path(__file__).resolve().parent.parent / "resources"

LIGHT = {
    "bg": "#F5F6F8",            # фон окна
    "surface": "#FFFFFF",       # карточки, таблицы, поля ввода
    "hover": "#EEF2F8",         # подсветка при наведении
    "border": "#E2E5EA",        # тонкие рамки и линии таблиц
    "border_strong": "#C9CFD8",  # рамки полей ввода и кнопок
    "track": "#E4E8EE",         # дорожка ползунка и прогресса
    "alt_row": "#F8FAFC",       # чередование строк таблицы
    "header": "#EEF2F7",        # шапка таблицы
    "text": "#1F2328",          # основной текст
    "text2": "#5F6B7A",         # второстепенный текст
    "accent": "#2F5597",        # главный цвет — как шапка итогового Excel
    "accent_hover": "#3A66B0",
    "accent_bg": "#E3ECF9",     # фон выбранного элемента
    "accent_text": "#1F3F7A",
    "sidebar": "#1F3864",       # панель шагов
    "sidebar_text": "#C9D3E3",
    "sidebar_muted": "#6F7F99",  # недоступный шаг
    "sidebar_active": "#FFFFFF",
    "sidebar_indicator": "#2F5597",
    "sidebar_hover": "#2A4675",
    "ok_text": "#1E7B45",
    "error_text": "#B42318",
    # Подсветка ячеек (те же смыслы, что в Excel)
    "best_bg": "#C6EFCE", "best_text": "#145A32",      # лучшая цена
    "warn_bg": "#FFEB9C", "warn_text": "#6B5000",      # нет годной цены
    "error_bg": "#F8D3C5", "error_text_cell": "#8B1E1E",  # ошибка в настройке
    "mapped_bg": "#DDEBF7", "mapped_text": "#1F2328",  # колонка выбрана для поля
    "tooltip_bg": "#1F2328",
    "tooltip_text": "#FFFFFF",
    "toast_link": "#9CC0FF",    # кнопка в уведомлении (на тёмном фоне)
}

DARK = {
    "bg": "#15171C",
    "surface": "#1E2128",
    "hover": "#2A2F39",
    "border": "#2E333D",
    "border_strong": "#3E4450",
    "track": "#2E333D",
    "alt_row": "#22262E",
    "header": "#252A33",
    "text": "#E6E8EB",
    "text2": "#9AA3B2",
    "accent": "#4C8DFF",
    "accent_hover": "#6A9FFF",
    "accent_bg": "#1E3256",
    "accent_text": "#A9C7FF",
    "sidebar": "#101217",
    "sidebar_text": "#AEB6C4",
    "sidebar_muted": "#4E5562",
    "sidebar_active": "#FFFFFF",
    "sidebar_indicator": "#1E3256",
    "sidebar_hover": "#1B1F27",
    "ok_text": "#6FD39C",
    "error_text": "#FF8A80",
    "best_bg": "#1D4A31", "best_text": "#A8E6C0",
    "warn_bg": "#4A3B12", "warn_text": "#F2D27A",
    "error_bg": "#4A2224", "error_text_cell": "#FFB3B3",
    "mapped_bg": "#1E3256", "mapped_text": "#D6E4FF",
    "tooltip_bg": "#E6E8EB",
    "tooltip_text": "#15171C",
    "toast_link": "#1F3F7A",
}

# Цвета текущей темы. Один и тот же словарь на всё время работы:
# при смене темы меняется его содержимое (см. apply_theme)
C = dict(LIGHT)

# Режимы темы: (ключ, подпись, иконка)
THEME_MODES = [
    ("light", "Светлая", "sun"),
    ("dark", "Тёмная", "moon"),
    ("system", "Как в системе", "monitor"),
]


def is_dark() -> bool:
    return C["bg"] == DARK["bg"]


def cell_colors(kind: str) -> tuple[QColor, QColor]:
    """Фон и цвет текста подсвеченной ячейки: kind — best, warn, error, mapped."""
    text_key = "error_text_cell" if kind == "error" else f"{kind}_text"
    return QColor(C[f"{kind}_bg"]), QColor(C[text_key])


def _svg_text(name: str, color: str) -> str:
    """SVG-иконка Lucide с подменой currentColor на нужный цвет."""
    path = RESOURCES / "icons" / f"{name}.svg"
    return path.read_text(encoding="utf-8").replace("currentColor", color)


def icon_file(name: str, color: str) -> str:
    """Путь к перекрашенной иконке-файлу — для QSS (url(...)).

    QSS умеет брать картинки только из файлов, поэтому складываем
    перекрашенные копии во временную папку системы.
    """
    folder = Path(tempfile.gettempdir()) / "price-list-merger-icons"
    folder.mkdir(exist_ok=True)
    path = folder / f"{name}-{color.lstrip('#')}.svg"
    if not path.exists():
        path.write_text(_svg_text(name, color), encoding="utf-8")
    return path.as_posix()  # QSS понимает только прямые слэши


@cache  # каждую иконку нужного цвета рисуем один раз
def icon(name: str, color: str | None = None, size: int = 18) -> QIcon:
    """Иконка Lucide нужного цвета (по умолчанию — цвет основного текста).

    Рисуем с запасом по чёткости (×2), чтобы на экранах с масштабом 150%
    иконка не была размытой.
    """
    svg = _svg_text(name, color or C["text"])
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(QSize(size * 2, size * 2))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def build_style() -> str:
    """Собирает таблицу стилей QSS из цветов текущей темы."""
    down = icon_file("chevron-down", C["text2"])
    up = icon_file("chevron-up", C["text2"])
    check = icon_file("check", "#FFFFFF")
    return f"""
QWidget {{ color: {C['text']}; font-size: 10pt; }}
QMainWindow, QDialog, QMessageBox, QWidget#page, QStackedWidget {{
    background: {C['bg']}; }}

/* --- панель шагов --- */
QFrame#sidebar {{ background: {C['sidebar']}; }}
QLabel#appName {{ color: {C['sidebar_active']}; font-size: 12pt; font-weight: 600; }}
QLabel#appVersion {{ color: {C['sidebar_muted']}; font-size: 9pt; }}
QFrame#sidebar QPushButton {{ text-align: left; padding: 10px 14px; border: none;
    border-radius: 6px; background: transparent; color: {C['sidebar_text']};
    font-size: 10.5pt; }}
QFrame#sidebar QPushButton:hover {{ background: {C['sidebar_hover']}; }}
QFrame#sidebar QPushButton:checked {{ color: {C['sidebar_active']}; font-weight: 600;
    background: transparent; }}
QFrame#sidebar QPushButton:disabled {{ color: {C['sidebar_muted']}; }}
QFrame#sidebar QPushButton[kind="tool"] {{ font-size: 9.5pt; padding: 7px 14px; }}
QFrame#sidebar QPushButton::menu-indicator {{ image: none; width: 0; }}
QFrame#stepIndicator {{ background: {C['sidebar_indicator']}; border-radius: 6px;
    border-left: 3px solid {C['accent_hover']}; }}

/* --- заголовки и подписи --- */
QLabel#title {{ font-size: 16pt; font-weight: 600; }}
QLabel#hint, QLabel[role="muted"] {{ color: {C['text2']}; }}
QLabel[role="ok"] {{ color: {C['ok_text']}; }}
QLabel[role="error"] {{ color: {C['error_text']}; }}
QLabel#statValue {{ font-size: 20pt; font-weight: 600; color: {C['accent']}; }}
QLabel#statLabel {{ color: {C['text2']}; }}
QLabel#empty {{ color: {C['text2']}; font-size: 11pt; border: 2px dashed {C['border_strong']};
    border-radius: 10px; padding: 32px; background: {C['surface']}; }}

QFrame#card {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 10px; }}
QGroupBox {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 10px;
    margin-top: 14px; padding: 14px 12px 12px 12px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {C['accent_text']};
    background: transparent; }}
QGroupBox QLabel, QGroupBox QCheckBox {{ font-weight: normal; }}

/* --- уведомление --- */
QFrame#toast {{ background: {C['tooltip_bg']}; border-radius: 8px; }}
QFrame#toast QLabel {{ color: {C['tooltip_text']}; }}
QFrame#toast QPushButton {{ color: {C['toast_link']}; background: transparent; border: none;
    font-weight: 600; padding: 2px 6px; }}

/* --- кнопки --- */
QPushButton {{ background: {C['surface']}; color: {C['text']}; border: 1px solid {C['border_strong']};
    border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ background: {C['hover']}; }}
QPushButton:pressed {{ background: {C['border']}; }}
QPushButton:disabled {{ color: {C['text2']}; background: {C['bg']}; border-color: {C['border']}; }}
QPushButton#primary {{ background: {C['accent']}; color: white; border: none; font-weight: 600;
    padding: 7px 18px; }}
QPushButton#primary:hover {{ background: {C['accent_hover']}; }}
QPushButton#primary:disabled {{ background: {C['border_strong']}; color: {C['bg']}; }}

/* --- поля ввода --- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: {C['surface']}; color: {C['text']};
    border: 1px solid {C['border_strong']}; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {C['accent']}; selection-color: white; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {C['accent']}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {C['text2']};
    background: {C['bg']}; border-color: {C['border']}; }}
QComboBox {{ padding-right: 28px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right;
    width: 26px; border: none; }}
QComboBox::down-arrow {{ image: url({down}); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ background: {C['surface']}; color: {C['text']};
    border: 1px solid {C['border']}; outline: 0; padding: 4px;
    selection-background-color: {C['accent_bg']}; selection-color: {C['accent_text']}; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 24px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::down-button {{ subcontrol-origin: border; width: 22px; border: none;
    background: transparent; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-position: top right; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-position: bottom right; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({up}); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({down}); width: 10px; height: 10px; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {C['border_strong']};
    border-radius: 4px; background: {C['surface']}; }}
QCheckBox::indicator:hover {{ border-color: {C['accent']}; }}
QCheckBox::indicator:checked {{ background: {C['accent']}; border-color: {C['accent']};
    image: url({check}); }}
QCheckBox::indicator:disabled {{ background: {C['bg']}; border-color: {C['border']}; }}

QSlider::groove:horizontal {{ height: 4px; background: {C['track']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {C['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -7px 0;
    background: {C['surface']}; border: 2px solid {C['accent']}; border-radius: 9px; }}
QSlider::sub-page:horizontal:disabled {{ background: {C['border_strong']}; }}
QSlider::handle:horizontal:disabled {{ border-color: {C['border_strong']}; }}

/* --- таблицы --- */
QTableView, QTableWidget {{ background: {C['surface']}; alternate-background-color: {C['alt_row']};
    border: 1px solid {C['border']}; border-radius: 8px; gridline-color: {C['border']};
    selection-background-color: {C['accent_bg']}; selection-color: {C['text']}; outline: 0; }}
QTableView::item {{ padding: 0 8px; }}
QHeaderView::section {{ background: {C['header']}; color: {C['text2']}; padding: 6px 8px;
    border: none; border-right: 1px solid {C['border']}; border-bottom: 1px solid {C['border']};
    font-weight: 600; }}
QHeaderView::section:hover {{ color: {C['text']}; }}
QTableCornerButton::section {{ background: {C['header']}; border: none; }}
QHeaderView::up-arrow {{ image: url({up}); width: 10px; height: 10px; }}
QHeaderView::down-arrow {{ image: url({down}); width: 10px; height: 10px; }}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {C['text2']}; padding: 7px 14px;
    border: none; border-bottom: 2px solid transparent; }}
QTabBar::tab:hover {{ color: {C['text']}; }}
QTabBar::tab:selected {{ color: {C['accent_text']}; border-bottom: 2px solid {C['accent']};
    font-weight: 600; }}

/* --- полосы прокрутки --- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {C['border_strong']}; border-radius: 3px; min-height: 32px; }}
QScrollBar::handle:horizontal {{ background: {C['border_strong']}; border-radius: 3px; min-width: 32px; }}
QScrollBar::handle:hover {{ background: {C['text2']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QProgressBar {{ border: none; background: {C['track']}; border-radius: 3px;
    max-height: 6px; min-height: 6px; }}
QProgressBar::chunk {{ background: {C['accent']}; border-radius: 3px; }}

QMenu {{ background: {C['surface']}; color: {C['text']}; border: 1px solid {C['border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {C['accent_bg']}; color: {C['accent_text']}; }}
QMenu::item:checked {{ color: {C['accent_text']}; font-weight: 600; }}
QMenu::icon {{ padding-left: 6px; }}
QMenu::separator {{ height: 1px; background: {C['border']}; margin: 4px 8px; }}
QToolTip {{ background: {C['tooltip_bg']}; color: {C['tooltip_text']}; border: none; padding: 5px 8px; }}
"""


def make_palette() -> QPalette:
    """Палитра Qt в цветах текущей темы — для окон сообщений и стандартных элементов."""
    palette = QPalette()
    role = QPalette.ColorRole
    colors = {
        role.Window: C["bg"], role.WindowText: C["text"], role.Base: C["surface"],
        role.AlternateBase: C["alt_row"], role.Text: C["text"], role.Button: C["surface"],
        role.ButtonText: C["text"], role.Highlight: C["accent"], role.HighlightedText: "#FFFFFF",
        role.ToolTipBase: C["tooltip_bg"], role.ToolTipText: C["tooltip_text"],
        role.PlaceholderText: C["text2"], role.Link: C["accent"], role.Mid: C["border_strong"],
    }
    for color_role, color in colors.items():
        palette.setColor(color_role, QColor(color))
    # Неактивные элементы — приглушённым цветом
    for color_role in (role.Text, role.WindowText, role.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, color_role, QColor(C["text2"]))
    return palette


def system_is_dark(app: QApplication) -> bool:
    """Включена ли тёмная тема в Windows."""
    return app.styleHints().colorScheme() == Qt.ColorScheme.Dark


def apply_theme(app: QApplication, mode: str = "system") -> str:
    """Включает тему для всего приложения. Возвращает 'light' или 'dark'.

    mode — 'light', 'dark' или 'system' (как в Windows).
    """
    hints = app.styleHints()
    if mode == "system":
        # Сбрасываем свой выбор: Qt снова следит за темой Windows
        # (и сообщит сигналом colorSchemeChanged, если её переключат)
        if hasattr(hints, "unsetColorScheme"):
            hints.unsetColorScheme()
        resolved = "dark" if system_is_dark(app) else "light"
    else:
        resolved = mode
        # Qt 6.8+: заодно перекрашивает заголовок окна Windows в цвет темы
        if hasattr(hints, "setColorScheme"):
            hints.setColorScheme(Qt.ColorScheme.Dark if resolved == "dark" else Qt.ColorScheme.Light)

    C.clear()
    C.update(DARK if resolved == "dark" else LIGHT)
    icon.cache_clear()  # иконки рисуются цветом темы — перерисовать
    # Fusion — встроенный стиль Qt: одинаково выглядит везде и хорошо дружит с QSS
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setPalette(make_palette())
    app.setStyleSheet(build_style())
    return resolved
