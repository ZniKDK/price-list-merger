"""Наценка и округление цены продажи.

Наценка задаётся одним процентом или «лесенкой» по диапазонам закупочной
цены: на дешёвые товары процент обычно выше, на дорогие — ниже.
Округление всегда вверх, чтобы оно не съедало наценку.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

# Способы округления: ключ — подпись для пользователя
ROUND_NONE = "none"  # до копеек
ROUND_RUBLE = "1"  # до целого рубля
ROUND_TEN = "10"  # до десятков
ROUND_NINE = "9"  # «красивая» цена: …9 (1 239, 499)

ROUNDING_LABELS = {
    ROUND_NONE: "до копеек",
    ROUND_RUBLE: "до рубля",
    ROUND_TEN: "до 10 рублей",
    ROUND_NINE: "на …9 (1 239 ₽)",
}


@dataclass(frozen=True)
class MarkupTier:
    """Ступень наценки: для закупочной цены от min_price (включительно)."""

    min_price: float
    percent: float


@dataclass
class PricingSettings:
    """Настройки наценки.

    percent — наценка по умолчанию; tiers — ступени (если заданы, они
    важнее процента по умолчанию для цен выше своей границы).
    """

    percent: float = 0.0
    tiers: list[MarkupTier] = field(default_factory=list)
    rounding: str = ROUND_NONE

    def percent_for(self, price: float) -> float:
        """Процент наценки для данной закупочной цены."""
        percent = self.percent
        for tier in sorted(self.tiers, key=lambda item: item.min_price):
            if price >= tier.min_price:
                percent = tier.percent
        return percent


def round_price(value: float, rounding: str) -> float:
    """Округляет цену вверх по выбранному способу."""
    # Decimal убирает «хвосты» вроде 1199.9999999 перед округлением вверх
    value = float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    if rounding == ROUND_RUBLE:
        return float(math.ceil(value))
    if rounding == ROUND_TEN:
        return float(math.ceil(value / 10) * 10)
    if rounding == ROUND_NINE:
        # Ближайшее сверху число, оканчивающееся на 9: 1231 → 1239, 1240 → 1249
        whole = math.ceil(value)
        return float(whole + (9 - whole % 10) % 10)
    return value


def apply_markup(price: float | None, settings: PricingSettings) -> float | None:
    """Цена продажи: закупочная цена + наценка, с округлением."""
    if price is None or price != price:  # нет цены или NaN
        return None
    percent = settings.percent_for(price)
    return round_price(price * (1 + percent / 100), settings.rounding)
