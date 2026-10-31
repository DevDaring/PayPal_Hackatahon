"""PayPal webhooks: durable receipt → verification → idempotent processing in the worker."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .. import jobs, timeutil
from ..config import get_settings
from ..models import PaymentOperation, WebhookEvent
from ..paypal import get_adapter
from ..paypal.base import ProviderAmbiguous, ProviderError
from . import payments

HEADER_KEYS = ("paypal-auth-algo", "paypal-cert-url", "paypal-transmission-id", "paypal-transmission-sig", "paypal-transmission-time")
HANDLED = {"CHECKOUT.ORDER.APPROVED", "CHECKOUT.ORDER.COMPLETED", "PAYMENT.CAPTURE.COMPLETED", "PAYMENT.CAPTURE.PENDING", "PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.DECLINED", "PAYMENT.CAPTURE.REFUNDED", "PAYMENT.CAPTURE.REVERSED"}


def receive(db: Session, headers: dict, raw: bytes) -> tuple[int, str]:
    """Store first, acknowledge fast. Nothing here mutates payment state."""
    if len(raw) > 256 * 1024:
        return 413, "too large"
    try:
        event = json.loads(raw)
        event_id = str(event["id"])[:80]
    except (ValueError, KeyError, TypeError):
        return 400, "malformed"
    h = {k.lower(): v for k, v in headers.items() if k.lower() in HEADER_KEYS}
    resource = event.get("resource") or {}
    stmt = insert(WebhookEvent).values(
        id=uuid.uuid4(), provider_event_id=event_id, event_type=str(event.get("event_type", ""))[:80], resource_type=str(event.get("resource_type", ""))[:60],
        resource_id=str(resource.get("id", ""))[:80], headers=h, raw_body=raw.decode("utf-8", "replace"), verification="pending", processing="pending", received_at=timeutil.now(),
    ).on_conflict_do_nothing(index_elements=[WebhookEvent.provider_event_id]).returning(WebhookEvent.id)
    inserted = db.execute(stmt).scalar_one_or_none()
    if inserted is None:
        return 200, "duplicate"
    jobs.enqueue(db, "process_webhook", {"webhook_event_id": inserted}, dedupe_key=f"webhook:{inserted}", max_attempts=8)
    return 200, "accepted"


def _related_order_and_capture(event: dict) -> tuple[str | None, str | None]:
    r = event.get("resource") or {}
    et = event.get("event_type", "")
    if et.startswith("CHECKOUT.ORDER"):
        return r.get("id"), None
    related = ((r.get("supplementary_data") or {}).get("related_ids") or {})
    return related.get("order_id"), r.get("id")


def process(db_factory, webhook_event_id: str) -> None:
    s = get_settings()
    with db_factory() as db:
        we = db.get(WebhookEvent, uuid.UUID(webhook_event_id), with_for_update=True)
        if we is None or we.processing in ("applied", "ignored"):
            return
        we.attempts += 1
        headers, raw = dict(we.headers), we.raw_body
    event = json.loads(raw)
    # 1) Verify authenticity with PayPal before any business transition.
    if not s.PAYPAL_WEBHOOK_ID or not s.paypal_credentials_present:
        verdict = "FAILURE"
    else:
        try:
            verdict = get_adapter("sandbox").verify_webhook(headers, event, s.PAYPAL_WEBHOOK_ID)
        except ProviderAmbiguous:
            with db_factory() as db:
                db.get(WebhookEvent, uuid.UUID(webhook_event_id)).verification = "error"
            raise  # transient: job retries with backoff
        except ProviderError:
            verdict = "FAILURE"
    if verdict != "SUCCESS":
        with db_factory() as db:
            we = db.get(WebhookEvent, uuid.UUID(webhook_event_id))
            we.verification, we.processing, we.outcome, we.processed_at = "invalid", "ignored", "Signature verification failed; no state changed.", timeutil.now()
        return
    # 2) Map to a known operation; unrelated events never touch state.
    order_id, capture_id = _related_order_and_capture(event)
    with db_factory() as db:
        we = db.get(WebhookEvent, uuid.UUID(webhook_event_id))
        we.verification = "verified"
        conds = [PaymentOperation.provider_order_id == order_id] if order_id else []
        if capture_id:
            conds.append(PaymentOperation.provider_capture_id == capture_id)
        op = db.execute(select(PaymentOperation).where(or_(*conds), PaymentOperation.adapter == "sandbox")).scalar_one_or_none() if conds else None
        if op is None or event.get("event_type") not in HANDLED:
            we.processing, we.outcome, we.processed_at = "ignored", ("Unrelated to any QuoteGuard payment." if op is None else "Event type not used."), timeutil.now()
            return
        if op.merchant_id and ((event.get("resource") or {}).get("payee") or {}).get("merchant_id") not in (None, op.merchant_id):
            we.processing, we.outcome, we.processed_at = "ignored", "Payee does not match the expected merchant.", timeutil.now()
            return
        we.operation_id = op.id
        op_id = op.id
    # 3) Never apply the event body directly: fetch authoritative state (handles reordering).
    result = payments.reconcile(db_factory, str(op_id), source="webhook")
    with db_factory() as db:
        we = db.get(WebhookEvent, uuid.UUID(webhook_event_id))
        we.processing, we.outcome, we.processed_at = "applied", f"Reconciled from provider lookup: payment {result['state']}.", timeutil.now()
