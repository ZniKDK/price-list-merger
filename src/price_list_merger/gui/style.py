"""Оформление окна: светлая тема, синий акцент как у шапки итогового Excel."""

from PyQt6.QtGui import QColor

ACCENT = "#2F5597"
BEST_COLOR = QColor("#C6EFCE")  # зелёный — лучшая цена (как в Excel)
WARN_COLOR = QColor("#FFEB9C")  # жёлтый — требует внимания
ERROR_COLOR = QColor("#F8CBAD")  # красный — ошибка
MAPPED_COLOR = QColor("#DDEBF7")  # голубой — колонка выбрана для поля

STYLESHEET = f"""
QWidget {{
    font-size: 10pt;
}}
QMainWindow, QWidget#page {{
    background: #F7F8FA;
}}
QListWidget#steps {{
    background: #1F3864;
    border: none;
    color: #D6DCE5;
    padding-top: 12px;
    font-size: 11pt;
}}
QListWidget#steps::item {{
    padding: 12px 16px;
    border-left: 4px solid transparent;
}}
QListWidget#steps::item:selected {{
    background: #2F5597;
    color: white;
    border-left: 4px solid #8FAADC;
}}
QListWidget#steps::item:disabled {{
    color: #6F7F99;
}}
QLabel#title {{
    font-size: 15pt;
    font-weight: 600;
    color: #1F3864;
}}
QLabel#hint {{
    color: #595959;
}}
QLabel#statValue {{
    font-size: 20pt;
    font-weight: 600;
    color: {ACCENT};
}}
QLabel#statLabel {{
    color: #595959;
}}
QFrame#card {{
    background: white;
    border: 1px solid #D9D9D9;
    border-radius: 6px;
}}
QLabel#empty {{
    color: #7F7F7F;
    font-size: 11pt;
    border: 2px dashed #BFBFBF;
    border-radius: 8px;
    padding: 32px;
    background: white;
}}
QGroupBox {{
    background: white;
    border: 1px solid #D9D9D9;
    border-radius: 6px;
    margin-top: 14px;
    padding: 12px 10px 10px 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #1F3864;
}}
QPushButton {{
    padding: 6px 14px;
    border: 1px solid #BFBFBF;
    border-radius: 4px;
    background: white;
}}
QPushButton:hover {{
    background: #EEF3FB;
}}
QPushButton:disabled {{
    color: #A6A6A6;
}}
QPushButton#primary {{
    background: {ACCENT};
    color: white;
    border: 1px solid {ACCENT};
    font-weight: 600;
}}
QPushButton#primary:hover {{
    background: #3A66B0;
}}
QPushButton#primary:disabled {{
    background: #A6B8D9;
    border-color: #A6B8D9;
}}
QTableView, QTableWidget {{
    background: white;
    gridline-color: #E7E6E6;
    selection-background-color: #BDD7EE;
    selection-color: black;
}}
QHeaderView::section {{
    background: #EDF1F7;
    padding: 4px 6px;
    border: none;
    border-right: 1px solid #D9D9D9;
    border-bottom: 1px solid #D9D9D9;
    font-weight: 600;
}}
"""


def apply_theme(app) -> None:
    """Включает светлую тему независимо от темы Windows.

    Без этого при тёмной теме Windows часть текста становится белой
    на белом фоне: таблица стилей задаёт светлый фон, а палитра — тёмная.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QPalette

    app.setStyle("Fusion")
    hints = app.styleHints()
    if hasattr(hints, "setColorScheme"):  # Qt 6.8+
        hints.setColorScheme(Qt.ColorScheme.Light)
    palette = QPalette()
    role = QPalette.ColorRole
    colors = {
        role.Window: "#F7F8FA", role.WindowText: "#1F1F1F", role.Base: "#FFFFFF",
        role.AlternateBase: "#F3F6FA", role.Text: "#1F1F1F", role.Button: "#FFFFFF",
        role.ButtonText: "#1F1F1F", role.Highlight: "#BDD7EE", role.HighlightedText: "#000000",
        role.ToolTipBase: "#FFFFE1", role.ToolTipText: "#1F1F1F", role.PlaceholderText: "#8C8C8C",
        role.Link: ACCENT,
    }
    for color_role, color in colors.items():
        palette.setColor(color_role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, role.Text, QColor("#A6A6A6"))
    palette.setColor(QPalette.ColorGroup.Disabled, role.ButtonText, QColor("#A6A6A6"))
    palette.setColor(QPalette.ColorGroup.Disabled, role.WindowText, QColor("#A6A6A6"))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
