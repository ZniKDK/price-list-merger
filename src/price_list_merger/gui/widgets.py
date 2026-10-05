"""Общие виджеты окна: таблицы, выпадающий список, уведомление.

Здесь собраны исправления типичных проблем интерфейса:
- прокрутка таблиц плавная и по пикселям, а не рывками по строке;
- пустая таблица показывает бледную подсказку, а не голый белый прямоугольник;
- обрезанный текст ячейки виден целиком во всплывающей подсказке;
- ширина столбца не меньше заголовка (Qt не учитывает отступы из QSS);
- выпадающий список раскрывается плавно.
"""

from __future__ import annotations

from collections.abc import Callable
from html import escape

from PyQt6.QtCore import (
    QEvent, QObject, QPoint, QPropertyAnimation, QRect, Qt, QTimer,
)
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import (
    QAbstractItemView, QAbstractScrollArea, QComboBox, QFrame, QGraphicsOpacityEffect,
    QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableView, QTableWidget, QToolTip, QWidget,
)

from . import animations
from .style import C

MAX_COLUMN_WIDTH = 380  # шире столбец не растягиваем, остальное — в подсказке


def wrapped_tip(text: str) -> str:
    """Подсказка с переносом строк.

    Простой текст Qt показывает одной строкой во всю ширину экрана,
    а форматированный (HTML) — переносит. Спецсимволы экранируем.
    """
    return f"<p style='white-space: pre-wrap'>{escape(text)}</p>"


# ----------------------------------------------------------------------
# Плавная прокрутка колёсиком
# ----------------------------------------------------------------------

class SmoothScroller(QObject):
    """Плавная прокрутка колёсиком мыши для любой области прокрутки.

    Обычно Qt прокручивает рывками по три строки. Здесь каждый щелчок
    колеса задаёт цель, а полоса прокрутки плавно «доезжает» до неё.
    Несколько быстрых щелчков складываются. Тачпад даёт точные пиксели —
    их применяем сразу, без анимации.
    """

    STEP = 90  # пикселей за один щелчок колеса
    DURATION = 220  # мс

    def __init__(self, area: QAbstractScrollArea) -> None:
        super().__init__(area)
        self.area = area
        self._animation: QPropertyAnimation | None = None
        self._target = 0
        area.viewport().installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 — имя задано Qt
        if event.type() != QEvent.Type.Wheel:
            return False
        angle = event.angleDelta()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        sideways = angle.y() == 0 or shift
        bar = self.area.horizontalScrollBar() if sideways else self.area.verticalScrollBar()
        if bar.maximum() == 0:
            return False
        pixels = event.pixelDelta()
        if not pixels.isNull():  # тачпад: движение уже плавное
            delta = pixels.x() if (sideways and pixels.x()) else pixels.y()
            bar.setValue(bar.value() - delta)
            return True
        notches = (angle.y() or angle.x()) / 120
        running = (
            self._animation is not None
            and self._animation.state() == QPropertyAnimation.State.Running
        )
        start = self._target if running else bar.value()
        self._target = max(bar.minimum(), min(bar.maximum(), round(start - notches * self.STEP)))
        if not animations.ENABLED:
            bar.setValue(self._target)
            return True
        if self._animation is not None:
            self._animation.stop()
        self._animation = QPropertyAnimation(bar, b"value", self)
        self._animation.setDuration(self.DURATION)
        self._animation.setStartValue(bar.value())
        self._animation.setEndValue(self._target)
        self._animation.setEasingCurve(animations.EASING)
        self._animation.start()
        return True


# ----------------------------------------------------------------------
# Таблицы
# ----------------------------------------------------------------------

def paint_empty_hint(viewport: QWidget, title: str, subtitle: str = "") -> None:
    """Рисует подсказку по центру пустой таблицы — бледно, на фоне."""
    painter = QPainter(viewport)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    color = QColor(C["text2"])
    color.setAlpha(150)  # полупрозрачный: текст «растворён» в фоне
    painter.setPen(color)
    rect = viewport.rect()
    font = QFont(painter.font())
    font.setPointSize(14)
    font.setWeight(QFont.Weight.Bold)
    painter.setFont(font)
    title_rect = QRect(rect.left(), rect.center().y() - 34, rect.width(), 34)
    painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, title)
    if subtitle:
        font.setPointSize(10)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.drawText(
            QRect(rect.left() + 20, rect.center().y() + 4, rect.width() - 40, 44),
            Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap,
            subtitle,
        )
    painter.end()


def setup_table(table: QAbstractItemView) -> None:
    """Общие настройки таблиц: прокрутка по пикселям, плавное колесо, сетка."""
    table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setShowGrid(True)
    table.setWordWrap(False)
    table.setTextElideMode(Qt.TextElideMode.ElideRight)
    table.verticalHeader().setDefaultSectionSize(30)
    header = table.horizontalHeader()
    header.setHighlightSections(False)
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
    SmoothScroller(table)


def fit_columns(table: QTableView, max_width: int = MAX_COLUMN_WIDTH) -> None:
    """Ширина столбцов по содержимому, но не уже заголовка и не шире max_width.

    Qt считает ширину заголовка без отступов из QSS и без жирного шрифта,
    поэтому длинные заголовки («Поставщиков») обрезались. Считаем сами.
    """
    table.resizeColumnsToContents()
    header = table.horizontalHeader()
    bold = QFont(table.font())
    bold.setWeight(QFont.Weight.DemiBold)
    metrics = QFontMetrics(bold)
    model = table.model()
    for column in range(header.count()):
        text = str(model.headerData(column, Qt.Orientation.Horizontal) or "")
        longest_line = max((metrics.horizontalAdvance(line) for line in text.split("\n")), default=0)
        # 16 — отступы из QSS, ещё 18 — место под стрелку сортировки
        need = longest_line + 34
        width = max(table.columnWidth(column) + 12, need)
        table.setColumnWidth(column, min(width, max(max_width, need)))


class _ElidedTips:
    """Подсказка с полным текстом — только для ячеек, где текст обрезан."""

    def show_cell_tip(self, view: QAbstractItemView, event) -> bool:
        index = view.indexAt(event.pos())
        if not index.isValid():
            QToolTip.hideText()
            return True
        rect = view.visualRect(index)
        own_tip = index.data(Qt.ItemDataRole.ToolTipRole)
        if own_tip:  # у ячейки своя подсказка (например, полный путь к файлу)
            QToolTip.showText(event.globalPos(), wrapped_tip(str(own_tip)), view, rect)
            return True
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        needed = view.fontMetrics().horizontalAdvance(text) + 16  # 16 — отступы ячейки
        if text and needed > rect.width():
            QToolTip.showText(event.globalPos(), wrapped_tip(text), view, rect)
        elif view.toolTip():
            QToolTip.showText(event.globalPos(), view.toolTip(), view)  # общая подсказка таблицы
        else:
            QToolTip.hideText()
        return True


class HintTableView(QTableView, _ElidedTips):
    """Таблица для моделей: подсказка на пустом фоне и полный текст обрезанных ячеек."""

    def __init__(self, title: str = "Здесь пока пусто", subtitle: str = "", parent=None) -> None:
        super().__init__(parent)
        self.empty_hint = (title, subtitle)
        setup_table(self)

    def paintEvent(self, event) -> None:  # noqa: N802 — имя задано Qt
        super().paintEvent(event)
        model = self.model()
        if model is None or model.rowCount() == 0:
            paint_empty_hint(self.viewport(), *self.empty_hint)

    def viewportEvent(self, event) -> bool:  # noqa: N802 — имя задано Qt
        if event.type() == QEvent.Type.ToolTip:
            return self.show_cell_tip(self, event)
        return super().viewportEvent(event)


class HintTableWidget(QTableWidget, _ElidedTips):
    """То же для QTableWidget (таблицы с редактируемыми ячейками)."""

    def __init__(self, rows: int, columns: int, title: str = "Здесь пока пусто",
                 subtitle: str = "", parent=None) -> None:
        super().__init__(rows, columns, parent)
        self.empty_hint = (title, subtitle)
        setup_table(self)

    def paintEvent(self, event) -> None:  # noqa: N802 — имя задано Qt
        super().paintEvent(event)
        if self.rowCount() == 0:
            paint_empty_hint(self.viewport(), *self.empty_hint)

    def viewportEvent(self, event) -> bool:  # noqa: N802 — имя задано Qt
        if event.type() == QEvent.Type.ToolTip:
            return self.show_cell_tip(self, event)
        return super().viewportEvent(event)


def stretch_column(table: QTableView, column: int) -> None:
    """Один столбец занимает всё свободное место, остальные — по содержимому."""
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)


# ----------------------------------------------------------------------
# Выпадающий список с плавным раскрытием
# ----------------------------------------------------------------------

class AnimatedComboBox(QComboBox):
    """Выпадающий список, который открывается плавно: проявляется
    и «разворачивается» вниз (или вверх, если открылся над полем)."""

    def showPopup(self) -> None:  # noqa: N802 — имя задано Qt
        super().showPopup()
        if not animations.ENABLED:
            return
        popup = self.view().window()  # окошко со списком вариантов
        end = popup.geometry()
        above = end.top() < self.mapToGlobal(QPoint(0, 0)).y()
        start = QRect(end)
        start.setHeight(max(1, end.height() // 3))
        if above:  # открылся вверх — разворачиваем от нижнего края
            start.moveBottom(end.bottom())
        popup.setWindowOpacity(0.0)
        self._roll = QPropertyAnimation(popup, b"geometry", self)
        self._roll.setDuration(170)
        self._roll.setStartValue(start)
        self._roll.setEndValue(end)
        self._roll.setEasingCurve(animations.EASING)
        self._fade = QPropertyAnimation(popup, b"windowOpacity", self)
        self._fade.setDuration(150)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._roll.start()
        self._fade.start()


# ----------------------------------------------------------------------
# Уведомление внизу окна
# ----------------------------------------------------------------------

class Toast(QFrame):
    """Всплывающее уведомление: «Сохранено: Свод.xlsx» [Открыть].

    Висит поверх содержимого, выезжает снизу, через несколько секунд тает.
    Кнопка действия необязательна.
    """

    left_margin = 0  # ширина боковой панели — уведомление центрируется правее

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 10, 10)
        layout.setSpacing(12)
        self.text = QLabel()
        self.action = QPushButton()
        self.action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action.clicked.connect(self._on_action)
        layout.addWidget(self.text)
        layout.addWidget(self.action)
        self._callback: Callable[[], None] | None = None
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self.hide()

    def show_message(self, text: str, action_text: str = "",
                     callback: Callable[[], None] | None = None, timeout: int = 5000) -> None:
        self.text.setText(text)
        self._callback = callback
        self.action.setVisible(bool(action_text and callback))
        self.action.setText(action_text)
        self.adjustSize()
        end = self._home()
        self.show()
        self.raise_()  # поверх остальных виджетов окна
        if animations.ENABLED:
            self._animate(b"opacity", self._effect, 0.0, 1.0, 180)
            self._animate(b"pos", self, end + QPoint(0, 16), end, 220)
        else:
            self._effect.setOpacity(1.0)
            self.move(end)
        self._timer.start(timeout)

    def _home(self) -> QPoint:
        parent = self.parentWidget()
        area = parent.width() - self.left_margin
        return QPoint(self.left_margin + (area - self.width()) // 2, parent.height() - self.height() - 70)

    def reposition(self) -> None:
        if self.isVisible():
            self.move(self._home())

    def dismiss(self) -> None:
        if not self.isVisible():
            return
        if animations.ENABLED:
            fade = self._animate(b"opacity", self._effect, 1.0, 0.0, 250)
            fade.finished.connect(self.hide)
        else:
            self.hide()

    def _on_action(self) -> None:
        callback = self._callback
        self.dismiss()
        if callback is not None:
            callback()

    def _animate(self, prop: bytes, target, start, end, duration) -> QPropertyAnimation:
        animation = QPropertyAnimation(target, prop, self)
        animation.setDuration(duration)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setEasingCurve(animations.EASING)
        setattr(self, f"_anim_{prop.decode()}", animation)  # чтобы не удалил сборщик мусора
        animation.start()
        return animation


def set_role(label: QLabel, role: str) -> None:
    """Меняет «роль» подписи (ok, error, muted) — цвет берётся из темы.

    Цвет нельзя задавать прямо в setStyleSheet виджета: при смене темы
    он бы остался старым. Роль — это свойство, по которому QSS выбирает цвет.
    """
    label.setProperty("role", role)
    label.style().unpolish(label)
    label.style().polish(label)
