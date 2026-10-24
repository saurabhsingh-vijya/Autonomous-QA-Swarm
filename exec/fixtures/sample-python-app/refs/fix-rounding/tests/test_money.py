from decimal import Decimal

import pytest

from app.money import normalize_amount, transfer


def test_two_decimals_pass_through():
    assert normalize_amount("250.00") == Decimal("250.00")


def test_rounds_half_even():
    # Banker's rounding: 2.675 -> 2.68
    assert normalize_amount("2.675") == Decimal("2.68")


def test_rejects_sub_minor_unit_amount():
    with pytest.raises(ValueError):
        normalize_amount("0.005")


def test_negative_amount_rejected():
    with pytest.raises(ValueError):
        normalize_amount("-1")


def test_transfer_returns_created():
    assert transfer("10.50")["status"] == "created"
