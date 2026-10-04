"""Тесты наценки и округления."""

import pytest

from price_list_merger.core.pricing import (
    ROUND_NINE, ROUND_NONE, ROUND_RUBLE, ROUND_TEN, MarkupTier, PricingSettings,
    apply_markup, round_price,
)


@pytest.mark.parametrize("value, rounding, expected", [
    (123.456, ROUND_NONE, 123.46),
    (123.01, ROUND_RUBLE, 124.0),
    (123.0, ROUND_RUBLE, 123.0),
    (121.0, ROUND_TEN, 130.0),
    (120.0, ROUND_TEN, 120.0),
    (1231.0, ROUND_NINE, 1239.0),
    (1239.0, ROUND_NINE, 1239.0),
    (1239.5, ROUND_NINE, 1249.0),
    (1240.0, ROUND_NINE, 1249.0),
    (5.0, ROUND_NINE, 9.0),
])
def test_round_price(value, rounding, expected):
    assert round_price(value, rounding) == expected


def test_round_up_ignores_float_noise():
    # 1000 * 1.2 в двоичной арифметике — 1199.9999999999998
    assert round_price(1000 * 1.2, ROUND_RUBLE) == 1200.0


def test_flat_markup():
    settings = PricingSettings(percent=20)
    assert apply_markup(100.0, settings) == 120.0
    assert apply_markup(None, settings) is None
    assert apply_markup(float("nan"), settings) is None


def test_tiers():
    settings = PricingSettings(
        percent=30, tiers=[MarkupTier(10000, 10), MarkupTier(1000, 20)], rounding=ROUND_RUBLE,
    )
    assert settings.percent_for(500) == 30
    assert settings.percent_for(1000) == 20
    assert settings.percent_for(9999.99) == 20
    assert settings.percent_for(10000) == 10
    assert apply_markup(500.0, settings) == 650.0
    assert apply_markup(2000.0, settings) == 2400.0
    assert apply_markup(20000.0, settings) == 22000.0


def test_zero_markup_keeps_price():
    assert apply_markup(99.99, PricingSettings()) == 99.99
