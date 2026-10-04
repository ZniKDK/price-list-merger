"""Сделать иконку программы: src/price_list_merger/resources/app.ico и app.png.

Рисунок: два прайса (листа) сводятся в один, на итоговом листе зелёным
отмечена строка с лучшей ценой. Синий фон — как шапка итогового Excel.

Запуск: python tools/make_icon.py
"""

import sys
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src" / "price_list_merger" / "resources"
ACCENT = "#2F5597"
BEST = "#5CB85C"


def sheet(painter: QPainter, rect: QRectF, size: int, best_row: int | None = None) -> None:
    """Лист прайса: белый прямоугольник со строками-полосками."""
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("white"))
    painter.drawRoundedRect(rect, size * 0.03, size * 0.03)
    rows = 4
    margin = rect.width() * 0.14
    step = (rect.height() - 2 * margin) / rows
    for row in range(rows):
        top = rect.top() + margin + row * step + step * 0.25
        line = QRectF(rect.left() + margin, top, rect.width() - 2 * margin, step * 0.5)
        painter.setBrush(QColor(BEST if row == best_row else "#BDD7EE"))
        painter.drawRoundedRect(line, step * 0.15, step * 0.15)


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(ACCENT))
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)

    # Два маленьких листа слева — прайсы поставщиков
    small_w, small_h = size * 0.26, size * 0.32
    sheet(painter, QRectF(size * 0.10, size * 0.14, small_w, small_h), size)
    sheet(painter, QRectF(size * 0.10, size * 0.54, small_w, small_h), size)
    # Стрелки к итоговому листу
    pen = QPen(QColor("white"), size * 0.035)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(int(size * 0.39), int(size * 0.30), int(size * 0.50), int(size * 0.44))
    painter.drawLine(int(size * 0.39), int(size * 0.70), int(size * 0.50), int(size * 0.56))
    # Итоговый лист справа, лучшая цена — зелёная строка
    sheet(painter, QRectF(size * 0.52, size * 0.20, size * 0.38, size * 0.60), size, best_row=1)
    painter.end()
    return image


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 — нужен для отрисовки
    TARGET.mkdir(parents=True, exist_ok=True)
    # Qt записывает в ICO одно изображение; Windows масштабирует его сам,
    # поэтому берём самый крупный размер — так иконка чёткая везде
    if not render(256).save(str(TARGET / "app.ico"), "ICO"):
        raise SystemExit("Не удалось сохранить иконку")
    render(256).save(str(TARGET / "app.png"), "PNG")
    print("Готово:", TARGET / "app.ico")


if __name__ == "__main__":
    main()
