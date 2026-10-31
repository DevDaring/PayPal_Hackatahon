"""Adapter registry. Tests replace adapters through `set_adapter` rather than monkeypatching HTTP."""

from __future__ import annotations

from ..config import get_settings
from ..errors import AppError
from .base import PaymentProvider

_adapters: dict[str, PaymentProvider] = {}


def get_adapter(kind: str) -> PaymentProvider:
    if kind in _adapters:
        return _adapters[kind]
    if kind == "sandbox":
        if not get_settings().paypal_credentials_present:
            raise AppError("MERCHANT_UNCONFIGURED", "PayPal sandbox credentials are not configured on the server.", 409)
        from .sandbox import PayPalSandbox

        _adapters[kind] = PayPalSandbox()
    elif kind == "simulated":
        from .simulated import SimulatedPayPal

        _adapters[kind] = SimulatedPayPal()
    else:
        raise AppError("MERCHANT_UNCONFIGURED", "No payment adapter is configured for this merchant.", 409)
    return _adapters[kind]


def set_adapter(kind: str, adapter: PaymentProvider | None) -> None:
    if adapter is None:
        _adapters.pop(kind, None)
    else:
        _adapters[kind] = adapter
