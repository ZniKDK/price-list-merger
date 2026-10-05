"""Короткие анимации интерфейса.

Анимации идут через QPropertyAnimation / QVariantAnimation: Qt сам плавно
меняет значение (прозрачность, положение, число) за заданное время.
Длительности маленькие (150–400 мс): программа ощущается плавной,
но не медленной.

ENABLED — общий выключатель. Когда он выключен, функции сразу ставят
конечное значение. В тестах анимации выключены.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QEasingCurve, QObject, QPropertyAnimation, QRect, QVariantAnimation
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QWidget

ENABLED = True

# Плавное замедление к концу движения — выглядит естественно
EASING = QEasingCurve.Type.OutCubic


def set_enabled(value: bool) -> None:
    global ENABLED
    ENABLED = value


def _keep(owner: QObject, name: str, animation) -> None:
    """Сохраняет анимацию в атрибуте владельца.

    Иначе Python удалит объект анимации сразу после выхода из функции,
    и она не успеет проиграться. Новая анимация того же типа
    останавливает предыдущую.
    """
    old = getattr(owner, name, None)
    if old is not None:
        old.stop()
    setattr(owner, name, animation)


def fade_in(widget: QWidget, duration: int = 200) -> None:
    """Плавное появление виджета: прозрачность 0 → 1.

    Эффект прозрачности после анимации снимаем: постоянный эффект
    замедляет отрисовку таблиц.
    """
    if not ENABLED:
        return
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(EASING)
    animation.finished.connect(lambda: widget.setGraphicsEffect(None))
    _keep(widget, "_fade_animation", animation)
    animation.start()


def slide_to(widget: QWidget, target: QRect, duration: int = 220) -> None:
    """Плавно передвигает виджет в новые координаты и размер."""
    if not ENABLED or not widget.isVisible():
        widget.setGeometry(target)
        return
    animation = QPropertyAnimation(widget, b"geometry", widget)
    animation.setDuration(duration)
    animation.setStartValue(widget.geometry())
    animation.setEndValue(target)
    animation.setEasingCurve(EASING)
    _keep(widget, "_slide_animation", animation)
    animation.start()


def count_up(owner: QObject, end: float, show: Callable[[float], None], duration: int = 500) -> None:
    """Число плавно «досчитывает» от нуля до end; show(значение) обновляет надпись."""
    if not ENABLED or end == 0:
        show(end)
        return
    animation = QVariantAnimation(owner)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(float(end))
    animation.setEasingCurve(EASING)
    animation.valueChanged.connect(show)
    # Последний кадр — точное значение, без ошибок округления
    animation.finished.connect(lambda: show(end))
    _keep(owner, "_count_animation", animation)
    animation.start()
