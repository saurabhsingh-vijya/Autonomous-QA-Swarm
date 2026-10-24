"""Amount normalisation for transfers (fixture).

Known defect on this branch: amounts are rounded *down* instead of half-even, and amounts below
the minor unit (0.01) are accepted and silently become 0.00 (compare the design's FND-0196).
"""

from decimal import ROUND_DOWN, Decimal

MINOR_UNIT = Decimal("0.01")


def normalize_amount(value: str | Decimal) -> Decimal:
    amount = Decimal(str(value))
    if amount < 0:
        raise ValueError("amount must not be negative")
    return amount.quantize(MINOR_UNIT, rounding=ROUND_DOWN)


def transfer(amount: str | Decimal, currency: str = "EUR") -> dict[str, object]:
    normalized = normalize_amount(amount)
    return {"amount": str(normalized), "currency": currency, "status": "created"}
