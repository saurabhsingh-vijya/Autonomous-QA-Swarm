"""Amount normalisation for transfers (fixture). Fixed: half-even rounding, sub-unit rejected."""

from decimal import ROUND_HALF_EVEN, Decimal

MINOR_UNIT = Decimal("0.01")


def normalize_amount(value: str | Decimal) -> Decimal:
    amount = Decimal(str(value))
    if amount < 0:
        raise ValueError("amount must not be negative")
    if amount != 0 and amount < MINOR_UNIT:
        raise ValueError("amount is below the minor unit")
    return amount.quantize(MINOR_UNIT, rounding=ROUND_HALF_EVEN)


def transfer(amount: str | Decimal, currency: str = "EUR") -> dict[str, object]:
    normalized = normalize_amount(amount)
    return {"amount": str(normalized), "currency": currency, "status": "created"}
