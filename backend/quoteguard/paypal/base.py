"""Provider adapter contract. Payment services depend on this, never on raw HTTP."""

from __future__ import annotations

from dataclasses import dataclass, field


class ProviderError(Exception):
    """A definite provider rejection (4xx with a body)."""

    def __init__(self, code: str, message: str, http_status: int | None = None, debug_id: str | None = None, body: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.debug_id = debug_id
        self.body = body or {}


class ProviderAmbiguous(Exception):
    """Timeout, connection reset or 5xx: the call may or may not have taken effect."""

    def __init__(self, message: str, http_status: int | None = None):
        super().__init__(message)
        self.http_status = http_status


@dataclass
class ProviderResult:
    body: dict
    http_status: int
    latency_ms: int
    debug_id: str | None = None
    meta: dict = field(default_factory=dict)


class PaymentProvider:
    name = "base"

    def create_order(self, body: dict, request_id: str) -> ProviderResult:  # pragma: no cover - interface
        raise NotImplementedError

    def get_order(self, order_id: str) -> ProviderResult:  # pragma: no cover
        raise NotImplementedError

    def capture_order(self, order_id: str, request_id: str) -> ProviderResult:  # pragma: no cover
        raise NotImplementedError

    def get_capture(self, capture_id: str) -> ProviderResult:  # pragma: no cover
        raise NotImplementedError

    def refund_capture(self, capture_id: str, amount: str, currency: str, request_id: str, note: str) -> ProviderResult:  # pragma: no cover
        raise NotImplementedError

    def verify_webhook(self, headers: dict, event: dict, webhook_id: str) -> str:  # pragma: no cover
        """Return 'SUCCESS' or 'FAILURE'. Raise ProviderAmbiguous on transient errors."""
        raise NotImplementedError


def order_summary(body: dict) -> dict:
    """Redacted, non-PII view of an order for storage and display."""
    pu = (body.get("purchase_units") or [{}])[0]
    captures = ((pu.get("payments") or {}).get("captures")) or []
    return {
        "id": body.get("id"),
        "status": body.get("status"),
        "amount": pu.get("amount", {}).get("value"),
        "currency": pu.get("amount", {}).get("currency_code"),
        "payee_merchant_id": (pu.get("payee") or {}).get("merchant_id"),
        "custom_id": pu.get("custom_id"),
        "invoice_id": pu.get("invoice_id"),
        "payer_id": (body.get("payer") or {}).get("payer_id"),
        "captures": [
            {"id": c.get("id"), "status": c.get("status"), "amount": (c.get("amount") or {}).get("value"), "currency": (c.get("amount") or {}).get("currency_code"), "final_capture": c.get("final_capture")}
            for c in captures
        ],
    }
