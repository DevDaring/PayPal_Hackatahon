"""Money helpers. Decimal only; floats are rejected so rounding can never creep in."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
SUPPORTED_CHECKOUT_CURRENCIES = {"USD"}


def to_money(value) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, float):
        raise TypeError("floating point money is not accepted; pass a string or Decimal")
    if isinstance(value, Decimal):
        d = value
    else:
        text = str(value).strip().replace(",", "")
        text = re.sub(r"^(US\$|USD|\$|€|£|₹|INR|EUR|GBP)\s*", "", text, flags=re.I)
        text = re.sub(r"\s*(USD|INR|EUR|GBP)$", "", text, flags=re.I)
        try:
            d = Decimal(text)
        except InvalidOperation:
            return None
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(d: Decimal | None) -> str | None:
    return None if d is None else str(d.quantize(CENT, rounding=ROUND_HALF_UP))


def to_minor_units(d: Decimal) -> int:
    return int((d.quantize(CENT) * 100).to_integral_value())
