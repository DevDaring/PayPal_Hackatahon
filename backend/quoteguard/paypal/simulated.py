"""Explicitly labelled simulated provider.

Used by automated tests and by Demo Lab scenarios that need a captured payment without a
human buyer login. It mimics PayPal's order lifecycle and PayPal-Request-Id idempotency,
keeps state in PostgreSQL, and is never presented as a real sandbox transaction.
"""

from __future__ import annotations

import secrets
import time

from sqlalchemy import select

from .. import timeutil
from ..db import session_scope
from ..models import SimulatedProviderOrder
from .base import PaymentProvider, ProviderError, ProviderResult


def _id(prefix: str) -> str:
    return prefix + secrets.token_hex(8).upper()


class SimulatedPayPal(PaymentProvider):
    name = "simulated"

    def _view(self, o: SimulatedProviderOrder) -> dict:
        body = dict(o.body)
        body["id"], body["status"] = o.id, o.status
        if o.status in ("APPROVED", "COMPLETED"):
            body["payer"] = {"payer_id": "SIMBUYER0001"}
        pu = dict(body["purchase_units"][0])
        if o.capture_id:
            pu["payments"] = {"captures": [{"id": o.capture_id, "status": "COMPLETED", "amount": pu["amount"], "final_capture": True}]}
        body["purchase_units"] = [pu]
        return body

    def create_order(self, body: dict, request_id: str) -> ProviderResult:
        t0 = time.monotonic()
        with session_scope() as db:
            existing = db.execute(select(SimulatedProviderOrder).where(SimulatedProviderOrder.create_request_id == request_id)).scalar_one_or_none()
            if existing:
                return ProviderResult(self._view(existing), 200, int((time.monotonic() - t0) * 1000), "SIM-DEBUG")
            pu = dict(body["purchase_units"][0])
            pu.setdefault("payee", {"merchant_id": "SIMULATED-MERCHANT"})
            o = SimulatedProviderOrder(id=_id("SIM"), create_request_id=request_id, status="CREATED", body={"intent": body["intent"], "purchase_units": [pu]}, refunds=[], created_at=timeutil.now())
            db.add(o)
            db.flush()
            return ProviderResult(self._view(o), 201, int((time.monotonic() - t0) * 1000), "SIM-DEBUG")

    def approve(self, order_id: str) -> None:
        """Stands in for buyer approval in the PayPal UI. Only reachable from labelled flows."""
        with session_scope() as db:
            o = db.get(SimulatedProviderOrder, order_id, with_for_update=True, populate_existing=True)
            if o and o.status == "CREATED":
                o.status = "APPROVED"

    def get_order(self, order_id: str) -> ProviderResult:
        with session_scope() as db:
            o = db.get(SimulatedProviderOrder, order_id)
            if o is None:
                raise ProviderError("RESOURCE_NOT_FOUND", "Order not found", 404)
            return ProviderResult(self._view(o), 200, 3, "SIM-DEBUG")

    def capture_order(self, order_id: str, request_id: str) -> ProviderResult:
        with session_scope() as db:
            o = db.get(SimulatedProviderOrder, order_id, with_for_update=True, populate_existing=True)
            if o is None:
                raise ProviderError("RESOURCE_NOT_FOUND", "Order not found", 404)
            if o.capture_request_id == request_id and o.status == "COMPLETED":
                return ProviderResult(self._view(o), 200, 4, "SIM-DEBUG", {"idempotent_replay": True})
            if o.status == "COMPLETED":
                raise ProviderError("ORDER_ALREADY_CAPTURED", "Order already captured.", 422)
            if o.status != "APPROVED":
                raise ProviderError("ORDER_NOT_APPROVED", "Payer has not approved the order.", 422)
            o.status, o.capture_request_id, o.capture_id = "COMPLETED", request_id, _id("SIMCAP")
            o.captured_at = timeutil.now()
            o.capture_calls += 1
            db.flush()
            return ProviderResult(self._view(o), 201, 5, "SIM-DEBUG")

    def get_capture(self, capture_id: str) -> ProviderResult:
        with session_scope() as db:
            o = db.execute(select(SimulatedProviderOrder).where(SimulatedProviderOrder.capture_id == capture_id)).scalar_one_or_none()
            if o is None:
                raise ProviderError("RESOURCE_NOT_FOUND", "Capture not found", 404)
            amt = o.body["purchase_units"][0]["amount"]
            return ProviderResult({"id": capture_id, "status": "COMPLETED", "amount": {"value": amt["value"], "currency_code": amt["currency_code"]}}, 200, 3)

    def refund_capture(self, capture_id: str, amount: str, currency: str, request_id: str, note: str) -> ProviderResult:
        with session_scope() as db:
            o = db.execute(select(SimulatedProviderOrder).where(SimulatedProviderOrder.capture_id == capture_id).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
            if o is None:
                raise ProviderError("RESOURCE_NOT_FOUND", "Capture not found", 404)
            for r in o.refunds:
                if r["request_id"] == request_id:
                    return ProviderResult({"id": r["id"], "status": "COMPLETED", "amount": {"value": r["amount"], "currency_code": currency}}, 200, 3)
            ref = {"id": _id("SIMREF"), "amount": amount, "request_id": request_id}
            o.refunds = [*o.refunds, ref]
            return ProviderResult({"id": ref["id"], "status": "COMPLETED", "amount": {"value": amount, "currency_code": currency}}, 201, 4)

    def verify_webhook(self, headers: dict, event: dict, webhook_id: str) -> str:
        # Simulated deliveries are never accepted as provider-signed events.
        return "FAILURE"
