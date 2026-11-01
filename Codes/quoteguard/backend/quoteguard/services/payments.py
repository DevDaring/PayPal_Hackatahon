"""Payment execution. Deterministic backend service; the model has no path to it.

Pattern for every provider call:
  1. short transaction: lock rows, check authority, commit the intent (state + stable request id)
  2. provider call with NO database transaction open
  3. short transaction: record the outcome; ambiguous outcomes become `reconciling`
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit, jobs, timeutil
from ..errors import AppError, not_found
from ..models import Approval, PaymentOperation, ProviderTransaction, PurchaseRequest, Refund
from ..money import fmt, to_money
from ..paypal import get_adapter
from ..paypal.base import ProviderAmbiguous, ProviderError, ProviderResult, order_summary
from . import approvals
from .context import Actor, parse_uuid

DBFactory = Callable[[], AbstractContextManager[Session]]


# ------------------------------------------------------------------- helpers --------
def _tx(db: Session, op_id, call: str, outcome: str, *, request_id: str | None = None, res: ProviderResult | None = None, err: Exception | None = None, ref: str | None = None, status: str | None = None, summary: dict | None = None):
    db.add(ProviderTransaction(
        operation_id=op_id, call=call, request_id_header=request_id, outcome=outcome, http_status=(res.http_status if res else getattr(err, "http_status", None)),
        provider_ref=ref, provider_status=status, debug_id=(res.debug_id if res else getattr(err, "debug_id", None)), latency_ms=res.latency_ms if res else None,
        summary=summary if summary is not None else ({"error": getattr(err, "code", type(err).__name__ if err else None), "message": str(err)[:300]} if err else None),
        created_at=timeutil.now()))


def build_order_body(op: PaymentOperation, canonical: dict) -> dict:
    """The PayPal order is built only from the stored approved snapshot."""
    cur = canonical["currency"]
    a = canonical["amounts"]
    subtotal, shipping, tax = Decimal(a["subtotal"]), Decimal(a["shipping"]), Decimal(a["tax"])
    discount = Decimal(a["discount"]) if a.get("discount") else Decimal("0")
    items = []
    for li in canonical.get("line_items") or []:
        if li.get("quantity") and li.get("unit_price"):
            items.append({"name": li["description"][:120], "quantity": str(li["quantity"]), "unit_amount": {"currency_code": cur, "value": li["unit_price"]}, "category": "PHYSICAL_GOODS"})
    if not items or sum(Decimal(i["unit_amount"]["value"]) * int(i["quantity"]) for i in items) != subtotal:
        items = [{"name": f"{canonical['quantity']} × items per quote v{canonical['quote']['version']}"[:120], "quantity": "1", "unit_amount": {"currency_code": cur, "value": fmt(subtotal)}, "category": "PHYSICAL_GOODS"}]
    breakdown = {"item_total": {"currency_code": cur, "value": fmt(subtotal)}, "shipping": {"currency_code": cur, "value": fmt(shipping)}, "tax_total": {"currency_code": cur, "value": fmt(tax)}}
    if discount > 0:
        breakdown["discount"] = {"currency_code": cur, "value": fmt(discount)}
    return {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": canonical["request"]["id"][:36],
            "custom_id": str(op.id),
            "invoice_id": f"QG-{op.id.hex[:24]}",
            "description": f"QuoteGuard demo purchase — {canonical['supplier']['name']}"[:127],
            "amount": {"currency_code": cur, "value": fmt(op.amount), "breakdown": breakdown},
            "items": items,
            "payee": {"merchant_id": canonical["merchant"]["merchant_id"]},
        }],
        "application_context": {"brand_name": "QuoteGuard Demo", "shipping_preference": "NO_SHIPPING", "user_action": "PAY_NOW"},
    }


def op_json(op: PaymentOperation, db: Session | None = None) -> dict:
    out = {
        "id": str(op.id), "state": op.state, "adapter": op.adapter, "amount": fmt(op.amount), "currency": op.currency, "merchant_id": op.merchant_id,
        "approval_id": str(op.approval_id), "request_id": str(op.request_id), "provider_order_id": op.provider_order_id, "provider_order_status": op.provider_order_status,
        "provider_capture_id": op.provider_capture_id, "provider_capture_status": op.provider_capture_status, "captured_amount": fmt(op.captured_amount),
        "last_error_code": op.last_error_code, "last_error_message": op.last_error_message, "reconcile_attempts": op.reconcile_attempts,
        "fault_injection_armed": op.fault_injection is not None, "order_request_id": op.order_request_id, "capture_request_id": op.capture_request_id,
        "created_at": op.created_at.isoformat(), "updated_at": op.updated_at.isoformat(), "completed_at": op.completed_at.isoformat() if op.completed_at else None,
    }
    if db is not None:
        txs = db.execute(select(ProviderTransaction).where(ProviderTransaction.operation_id == op.id).order_by(ProviderTransaction.created_at)).scalars().all()
        out["provider_calls"] = [{"call": t.call, "outcome": t.outcome, "http_status": t.http_status, "provider_ref": t.provider_ref, "provider_status": t.provider_status,
                                  "request_id_header": t.request_id_header, "debug_id": t.debug_id, "latency_ms": t.latency_ms, "at": t.created_at.isoformat()} for t in txs]
        refunds = db.execute(select(Refund).where(Refund.operation_id == op.id).order_by(Refund.created_at)).scalars().all()
        out["refunds"] = [{"id": str(r.id), "amount": fmt(r.amount), "state": r.state, "provider_refund_id": r.provider_refund_id, "note": r.note, "at": r.created_at.isoformat()} for r in refunds]
    return out


def _lock_op(db: Session, op_id) -> PaymentOperation:
    """Lock order everywhere: purchase_requests → payment_operations (events reference the request)."""
    rid = db.execute(select(PaymentOperation.request_id).where(PaymentOperation.id == op_id)).scalar_one()
    db.execute(select(PurchaseRequest.id).where(PurchaseRequest.id == rid).with_for_update().execution_options(populate_existing=True))
    return db.execute(select(PaymentOperation).where(PaymentOperation.id == op_id).with_for_update().execution_options(populate_existing=True)).scalar_one()


def _lock_op_chain(db: Session, actor: Actor | None, op_id) -> tuple[PurchaseRequest, Approval, PaymentOperation]:
    q = select(PaymentOperation).where(PaymentOperation.id == parse_uuid(op_id, "Payment"))
    if actor is not None:
        q = q.where(PaymentOperation.workspace_id == actor.workspace_id)
    op = db.execute(q).scalar_one_or_none()
    if op is None:
        raise not_found("Payment")
    req = db.execute(select(PurchaseRequest).where(PurchaseRequest.id == op.request_id).with_for_update().execution_options(populate_existing=True)).scalar_one()
    appr = db.execute(select(Approval).where(Approval.id == op.approval_id).with_for_update().execution_options(populate_existing=True)).scalar_one()
    op = db.execute(select(PaymentOperation).where(PaymentOperation.id == op.id).with_for_update().execution_options(populate_existing=True)).scalar_one()
    return req, appr, op


def _event(db: Session, op: PaymentOperation, status: str, title: str, detail: str | None = None, actor: str = "system", tool: str = "payment_service"):
    audit.event(db, workspace_id=op.workspace_id, request_id=op.request_id, stage="payment", status=status, title=title, detail=detail,
                refs={"operation_id": op.id, "provider_order_id": op.provider_order_id, "provider_capture_id": op.provider_capture_id}, actor=actor, tool=tool)


# ------------------------------------------------------------- create order ---------
def start_checkout(db_factory: DBFactory, actor: Actor, approval_id) -> dict:
    actor.require("requester", "approver", "admin")
    aid = parse_uuid(approval_id, "Approval")
    with db_factory() as db:
        appr = db.execute(select(Approval).where(Approval.id == aid, Approval.workspace_id == actor.workspace_id)).scalar_one_or_none()
        if appr is None:
            raise not_found("Approval")
        existing = db.execute(select(PaymentOperation).where(PaymentOperation.approval_id == aid)).scalar_one_or_none()
        if existing is not None:
            return _existing_checkout(existing, db)

    error: AppError | None = None
    with db_factory() as db:
        db.execute(select(PurchaseRequest).where(PurchaseRequest.id == appr.request_id).with_for_update().execution_options(populate_existing=True)).scalar_one()
        appr = db.execute(select(Approval).where(Approval.id == aid).with_for_update().execution_options(populate_existing=True)).scalar_one()
        existing = db.execute(select(PaymentOperation).where(PaymentOperation.approval_id == aid)).scalar_one_or_none()
        if existing is not None:  # a concurrent click won the lock first
            return _existing_checkout(existing, db)
        try:
            canonical = approvals.revalidate(db, appr, allow_consumed=False)
        except AppError as e:
            error = e  # the invalidation is committed by leaving this block normally
        if error is None:
            m = canonical["merchant"]
            op_id = uuid.uuid4()
            op = PaymentOperation(id=op_id, workspace_id=appr.workspace_id, request_id=appr.request_id, approval_id=appr.id, snapshot_id=appr.snapshot_id, kind="checkout",
                                  business_key=f"checkout:{appr.id}", adapter=m["adapter"], state="order_creating", amount=Decimal(canonical["amounts"]["total"]), currency=canonical["currency"],
                                  merchant_id=m["merchant_id"], order_request_id=f"qg-order-{op_id.hex}", capture_request_id=f"qg-capture-{op_id.hex}", created_by=actor.user_id,
                                  created_at=timeutil.now(), updated_at=timeutil.now())
            db.add(op)
            appr.status = "consumed_for_execution"
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                with db_factory() as db2:
                    return _existing_checkout(db2.execute(select(PaymentOperation).where(PaymentOperation.approval_id == aid)).scalar_one(), db2)
            body = build_order_body(op, canonical)
            audit.record(db, "payment.order_intent", workspace_id=op.workspace_id, actor_id=actor.user_id, principal_id=actor.principal_id, object_type="payment_operation", object_id=op.id,
                         request_id=op.request_id, meta={"amount": fmt(op.amount), "currency": op.currency, "merchant_id": op.merchant_id, "paypal_request_id": op.order_request_id, "adapter": op.adapter})
            _event(db, op, "started", "Checkout started from the approved snapshot", f"{op.currency} {fmt(op.amount)} to merchant {op.merchant_id} via {'PayPal Sandbox' if op.adapter == 'sandbox' else 'simulated provider'}. Approval consumed for this one operation.", actor=actor.label)
    if error is not None:
        raise error
    return _create_order_call(db_factory, op_id, body)


def _existing_checkout(op: PaymentOperation, db: Session) -> dict:
    if op.state in ("canceled", "failed"):
        raise AppError("PAYMENT_" + op.state.upper(), f"This approval's payment was {op.state}: {op.last_error_message or op.last_error_code}. A fresh approval is required.", 409)
    return {**op_json(op, db), "duplicate": True}


def _create_order_call(db_factory: DBFactory, op_id: uuid.UUID, body: dict) -> dict:
    with db_factory() as db:
        op = db.get(PaymentOperation, op_id)
        adapter_kind, req_id = op.adapter, op.order_request_id
    provider = get_adapter(adapter_kind)
    try:
        res = provider.create_order(body, req_id)
    except ProviderAmbiguous as e:
        with db_factory() as db:
            op = _lock_op(db, op_id)
            _tx(db, op.id, "create_order", "timeout", request_id=req_id, err=e)
            if op.state == "order_creating":
                op.state, op.last_error_code, op.updated_at = "reconciling", "PROVIDER_TIMEOUT", timeutil.now()
                jobs.enqueue(db, "reconcile_payment", {"operation_id": op.id}, dedupe_key=f"reconcile:{op.id}", delay_seconds=2, max_attempts=8)
                _event(db, op, "warning", "PayPal did not answer order creation — reconciling", "The same PayPal-Request-Id will be retried; no second order is created.")
            return op_json(op, db)
    except ProviderError as e:
        with db_factory() as db:
            op = _lock_op(db, op_id)
            _tx(db, op.id, "create_order", "error", request_id=req_id, err=e)
            op.state, op.last_error_code, op.last_error_message, op.updated_at = "failed", e.code, e.message[:500], timeutil.now()
            appr = db.get(Approval, op.approval_id, with_for_update=True, populate_existing=True)
            appr.status, appr.ended_at, appr.end_reason = "invalidated", timeutil.now(), f"PayPal rejected order creation ({e.code})"
            _event(db, op, "failed", f"PayPal rejected order creation: {e.code}", e.message[:300])
        raise AppError("PROVIDER_REJECTED", f"PayPal rejected the order: {e.message}", 502, {"provider_code": e.code}) from None
    return _apply_order_created(db_factory, op_id, res)


def _apply_order_created(db_factory: DBFactory, op_id, res: ProviderResult) -> dict:
    s = order_summary(res.body)
    with db_factory() as db:
        op = _lock_op(db, op_id)
        _tx(db, op.id, "create_order", "ok", request_id=op.order_request_id, res=res, ref=s["id"], status=s["status"], summary=s)
        if s["amount"] != fmt(op.amount) or s["currency"] != op.currency or s["custom_id"] != str(op.id):
            op.state, op.last_error_code, op.updated_at = "failed", "ORDER_MISMATCH", timeutil.now()
            _event(db, op, "failed", "Provider order does not match the approved snapshot", str(s))
            return op_json(op, db)
        op.provider_order_id, op.provider_order_status = s["id"], s["status"]
        if op.state in ("order_creating", "reconciling"):
            op.state, op.last_error_code, op.updated_at = "awaiting_payer", None, timeutil.now()
            _event(db, op, "done", f"PayPal order {s['id']} created", f"{op.currency} {fmt(op.amount)} — waiting for the buyer to approve in PayPal.", tool="paypal.orders.create")
        return op_json(op, db)


# ------------------------------------------------------------------ capture ---------
def capture(db_factory: DBFactory, actor: Actor, op_id) -> dict:
    actor.require("requester", "approver", "admin")
    error: AppError | None = None
    with db_factory() as db:
        req, appr, op = _lock_op_chain(db, actor, op_id)
        if op.state == "completed":
            return {**op_json(op, db), "duplicate": True}
        if op.state in ("capture_pending", "reconciling"):
            return {**op_json(op, db), "duplicate": True, "in_progress": True}
        if op.state != "awaiting_payer":
            raise AppError("PAYMENT_" + op.state.upper(), f"Payment is {op.state.replace('_', ' ')}" + (f": {op.last_error_message}" if op.last_error_message else "."), 409)
        try:
            approvals.revalidate(db, appr, allow_consumed=True)
        except AppError as e:
            error = e
            op.state, op.last_error_code, op.last_error_message, op.updated_at = "canceled", e.code, e.message[:500], timeutil.now()
            _event(db, op, "blocked", f"Capture blocked: {e.code}", e.message, actor=actor.label, tool="snapshot_guard")
        if error is None:
            op.state, op.updated_at = "capture_pending", timeutil.now()
            audit.record(db, "payment.capture_intent", workspace_id=op.workspace_id, actor_id=actor.user_id, principal_id=actor.principal_id, object_type="payment_operation", object_id=op.id,
                         request_id=op.request_id, meta={"paypal_request_id": op.capture_request_id, "order_id": op.provider_order_id})
        oid, adapter_kind, cap_req, op_uuid = op.provider_order_id, op.adapter, op.capture_request_id, op.id
        fault = op.fault_injection
    if error is not None:
        raise error
    return _verify_and_capture(db_factory, op_uuid, oid, adapter_kind, cap_req, fault, actor.label)


def _validate_order_for_capture(op: PaymentOperation, s: dict) -> str | None:
    if s["custom_id"] != str(op.id):
        return "Order is not associated with this payment operation."
    if s["amount"] != fmt(op.amount) or s["currency"] != op.currency:
        return f"Order amount {s['currency']} {s['amount']} differs from approved {op.currency} {fmt(op.amount)}."
    if op.adapter == "sandbox" and s["payee_merchant_id"] and s["payee_merchant_id"] != op.merchant_id:
        return f"Order payee {s['payee_merchant_id']} differs from the approved merchant {op.merchant_id}."
    return None


def _verify_and_capture(db_factory: DBFactory, op_id, order_id: str, adapter_kind: str, cap_req: str, fault: str | None, actor_label: str) -> dict:
    provider = get_adapter(adapter_kind)
    # Provider-side check of association, payee, amount and payer approval before capture.
    try:
        got = provider.get_order(order_id)
    except (ProviderAmbiguous, ProviderError) as e:
        with db_factory() as db:
            op = _lock_op(db, op_id)
            _tx(db, op.id, "get_order", "timeout" if isinstance(e, ProviderAmbiguous) else "error", err=e, ref=order_id)
            if op.state == "capture_pending":
                op.state, op.last_error_code, op.last_error_message, op.updated_at = "awaiting_payer", "PROVIDER_UNAVAILABLE", "PayPal could not be reached to verify the order; nothing was captured. Try again.", timeutil.now()
            return op_json(op, db)
    s = order_summary(got.body)
    with db_factory() as db:
        op = _lock_op(db, op_id)
        _tx(db, op.id, "get_order", "ok", res=got, ref=order_id, status=s["status"], summary=s)
        problem = _validate_order_for_capture(op, s)
        if problem:
            op.state, op.last_error_code, op.last_error_message, op.updated_at = "failed", "ORDER_MISMATCH", problem, timeutil.now()
            _event(db, op, "blocked", "Capture blocked: provider order does not match", problem, tool="payment_guard")
            return op_json(op, db)
        if s["status"] == "COMPLETED" or s["captures"]:
            pass  # already captured (e.g. lost response earlier); fall through to reconcile below
        elif s["status"] != "APPROVED":
            op.state, op.provider_order_status, op.updated_at = "awaiting_payer", s["status"], timeutil.now()
            op.last_error_code, op.last_error_message = "PAYER_NOT_APPROVED", "The buyer has not approved this order in PayPal yet."
            return op_json(op, db)
        op.provider_order_status, op.payer_reference = s["status"], s["payer_id"]
    if s["captures"]:
        return reconcile(db_factory, str(op_id), source="capture-precheck")
    try:
        res = provider.capture_order(order_id, cap_req)
        if fault == "drop_capture_response":
            # Controlled Demo Lab test: the provider DID process the capture; we discard its answer.
            with db_factory() as db:
                op = _lock_op(db, op_id)
                _tx(db, op.id, "capture", "response_discarded_by_test", request_id=cap_req, summary={"note": "Controlled test discarded the provider response"})
                op.fault_injection = None
            raise ProviderAmbiguous("controlled test: response discarded")
    except ProviderAmbiguous as e:
        with db_factory() as db:
            op = _lock_op(db, op_id)
            if not str(e).startswith("controlled test"):
                _tx(db, op.id, "capture", "timeout", request_id=cap_req, err=e)
            op.state, op.last_error_code, op.last_error_message, op.updated_at = "reconciling", "CAPTURE_RESULT_UNKNOWN", "The capture result was not received. Checking PayPal before doing anything else.", timeutil.now()
            jobs.enqueue(db, "reconcile_payment", {"operation_id": op.id}, dedupe_key=f"reconcile:{op.id}", delay_seconds=2, max_attempts=8)
            _event(db, op, "warning", "Capture response lost — payment is reconciling", "Not marked paid or failed. QuoteGuard will look up the order at PayPal and never creates a replacement order.", tool="paypal.orders.capture")
            return op_json(op, db)
    except ProviderError as e:
        if e.code in ("ORDER_ALREADY_CAPTURED", "DUPLICATE_REQUEST_ID"):
            return reconcile(db_factory, str(op_id), source="already-captured")
        with db_factory() as db:
            op = _lock_op(db, op_id)
            _tx(db, op.id, "capture", "error", request_id=cap_req, err=e)
            if e.code in ("INSTRUMENT_DECLINED", "PAYER_ACTION_REQUIRED"):
                op.state, op.last_error_code, op.last_error_message = "awaiting_payer", e.code, "PayPal declined the funding source. The buyer can choose another one."
                _event(db, op, "warning", f"Capture declined by PayPal ({e.code})", "Buyer can retry with another funding source.")
            else:
                op.state, op.last_error_code, op.last_error_message = "failed", e.code, e.message[:500]
                _event(db, op, "failed", f"PayPal rejected the capture ({e.code})", e.message[:300])
            op.updated_at = timeutil.now()
            return op_json(op, db)
    return _apply_capture(db_factory, op_id, res.body, res=res, call="capture", actor_label=actor_label)


def _apply_capture(db_factory: DBFactory, op_id, body: dict, *, res: ProviderResult | None, call: str, actor_label: str = "system") -> dict:
    s = order_summary(body)
    cap = s["captures"][0] if s["captures"] else None
    with db_factory() as db:
        op = _lock_op(db, op_id)
        _tx(db, op.id, call, "ok", request_id=op.capture_request_id if call == "capture" else None, res=res, ref=cap["id"] if cap else s["id"], status=cap["status"] if cap else s["status"], summary=s)
        if op.state == "completed":
            return {**op_json(op, db), "duplicate": True}  # never regress or double-apply
        op.provider_order_status = s["status"]
        if cap is None:
            return op_json(op, db)
        if cap["amount"] != fmt(op.amount) or cap["currency"] != op.currency:
            op.state, op.last_error_code, op.last_error_message = "reconciling", "CAPTURE_AMOUNT_MISMATCH", f"Captured {cap['currency']} {cap['amount']} differs from approved {op.currency} {fmt(op.amount)}; manual review needed."
            _event(db, op, "blocked", "Captured amount differs from approval — manual review", op.last_error_message)
            return op_json(op, db)
        op.provider_capture_id, op.provider_capture_status = cap["id"], cap["status"]
        if cap["status"] == "COMPLETED":
            op.state, op.captured_amount, op.completed_at, op.last_error_code, op.last_error_message = "completed", to_money(cap["amount"]), timeutil.now(), None, None
            audit.record(db, "payment.captured", workspace_id=op.workspace_id, object_type="payment_operation", object_id=op.id, request_id=op.request_id,
                         meta={"order_id": op.provider_order_id, "capture_id": cap["id"], "amount": cap["amount"], "currency": cap["currency"], "adapter": op.adapter, "via": call})
            _event(db, op, "done", f"Capture confirmed by {'PayPal Sandbox' if op.adapter == 'sandbox' else 'simulated provider'}: {op.currency} {cap['amount']}",
                   f"Order {op.provider_order_id}, capture {cap['id']} (status COMPLETED, verified via {call}).", tool=f"paypal.{call}")
        elif cap["status"] == "PENDING":
            op.state, op.last_error_code, op.last_error_message = "reconciling", "PROVIDER_PENDING", "PayPal reports the capture as PENDING. Waiting for PayPal to complete it."
            jobs.enqueue(db, "reconcile_payment", {"operation_id": op.id}, dedupe_key=f"reconcile:{op.id}", delay_seconds=30, max_attempts=10)
            _event(db, op, "warning", "PayPal capture pending", "Not yet paid; will reconcile through webhook or lookup.")
        else:
            op.state, op.last_error_code, op.last_error_message = "failed", f"CAPTURE_{cap['status']}", f"PayPal reports capture status {cap['status']}."
            _event(db, op, "failed", f"PayPal capture {cap['status']}", None)
        op.updated_at = timeutil.now()
        return op_json(op, db)


# ---------------------------------------------------------------- reconcile ---------
def reconcile(db_factory: DBFactory, op_id: str, source: str = "worker") -> dict:
    """Authoritative lookup. Retries only the SAME logical operation with the SAME request id."""
    with db_factory() as db:
        op = _lock_op(db, uuid.UUID(str(op_id)))
        if op is None:
            raise not_found("Payment")
        if op.state in ("completed", "canceled", "failed") and source != "webhook":
            return op_json(op, db)
        op.reconcile_attempts += 1
        snapshot = (op.id, op.adapter, op.provider_order_id, op.order_request_id, op.capture_request_id, op.state)
    op_uuid, adapter_kind, order_id, order_req, cap_req, state = snapshot
    provider = get_adapter(adapter_kind)
    if order_id is None:
        # Order creation outcome unknown: replay the same create with the same PayPal-Request-Id.
        with db_factory() as db:
            from ..models import PurchaseSnapshot

            op = db.get(PaymentOperation, op_uuid)
            body = build_order_body(op, db.get(PurchaseSnapshot, op.snapshot_id).canonical)
        res = provider.create_order(body, order_req)  # ambiguity propagates → job retry
        return _apply_order_created(db_factory, op_uuid, res)
    got = provider.get_order(order_id)
    s = order_summary(got.body)
    if s["captures"]:
        return _apply_capture(db_factory, op_uuid, got.body, res=got, call="get_order")
    if s["status"] == "APPROVED" and state in ("reconciling", "capture_pending"):
        try:
            res = provider.capture_order(order_id, cap_req)
        except ProviderError as e:
            if e.code == "ORDER_ALREADY_CAPTURED":
                got = provider.get_order(order_id)
                return _apply_capture(db_factory, op_uuid, got.body, res=got, call="get_order")
            raise
        return _apply_capture(db_factory, op_uuid, res.body, res=res, call="capture")
    with db_factory() as db:
        op = _lock_op(db, op_uuid)
        _tx(db, op.id, "get_order", "ok", res=got, ref=order_id, status=s["status"], summary=s)
        op.provider_order_status = s["status"]
        if s["status"] in ("CREATED", "PAYER_ACTION_REQUIRED", "SAVED") and op.state in ("reconciling", "capture_pending", "order_creating"):
            op.state, op.last_error_code, op.last_error_message = "awaiting_payer", None, None
            _event(db, op, "info", "Reconciled: order still awaits buyer approval", "Nothing was captured.")
        elif s["status"] == "VOIDED":
            op.state, op.last_error_code = "canceled", "ORDER_VOIDED"
            _event(db, op, "info", "Reconciled: PayPal voided the order", None)
        op.updated_at = timeutil.now()
        return op_json(op, db)


def recover_stuck(db: Session, older_than_seconds: int = 45) -> int:
    """After a crash between intent and result: move in-flight operations to reconciliation."""
    from datetime import timedelta

    cutoff = timeutil.now() - timedelta(seconds=older_than_seconds)
    stuck = db.execute(select(PaymentOperation).where(PaymentOperation.state.in_(("order_creating", "capture_pending")), PaymentOperation.updated_at < cutoff).with_for_update(skip_locked=True).execution_options(populate_existing=True)).scalars().all()
    for op in stuck:
        op.state, op.last_error_code, op.updated_at = "reconciling", "RECOVERED_AFTER_RESTART", timeutil.now()
        jobs.enqueue(db, "reconcile_payment", {"operation_id": op.id}, dedupe_key=f"reconcile:{op.id}", max_attempts=8)
        _event(db, op, "warning", "Recovered an in-flight payment after restart", "Recorded intent had no result; reconciling with PayPal using the same request id.")
    return len(stuck)


# ----------------------------------------------------------- buyer actions ----------
def buyer_canceled(db_factory: DBFactory, actor: Actor, op_id) -> dict:
    with db_factory() as db:
        _, _, op = _lock_op_chain(db, actor, op_id)
        if op.state == "awaiting_payer":
            op.last_error_code, op.last_error_message, op.updated_at = "BUYER_CANCELED", "The buyer closed PayPal without approving. Nothing was charged; you can retry.", timeutil.now()
            _event(db, op, "info", "Buyer canceled in PayPal", "No money moved. The same order can be approved again.", actor=actor.label)
        return op_json(op, db)


def simulated_buyer_approve(db_factory: DBFactory, actor: Actor, op_id) -> dict:
    with db_factory() as db:
        _, _, op = _lock_op_chain(db, actor, op_id)
        if op.adapter != "simulated":
            raise AppError("NOT_SIMULATED", "Real PayPal orders must be approved by the buyer in PayPal.", 409)
        oid = op.provider_order_id
    get_adapter("simulated").approve(oid)
    with db_factory() as db:
        op = db.get(PaymentOperation, parse_uuid(op_id))
        _event(db, op, "info", "Simulated buyer approved the order", "Controlled test step standing in for PayPal buyer login.", actor=actor.label)
        return op_json(op, db)


# ------------------------------------------------------------------ refunds ---------
def refund(db_factory: DBFactory, actor: Actor, op_id, amount: str, note: str) -> dict:
    actor.require("admin")
    if not note or len(note.strip()) < 4:
        raise AppError("NOTE_REQUIRED", "Explain the refund in a short note.", 422)
    amt = to_money(amount)
    if amt is None or amt <= 0:
        raise AppError("INVALID_VALUE", "Enter a positive refund amount.", 422)
    with db_factory() as db:
        _, _, op = _lock_op_chain(db, actor, op_id)
        if op.state != "completed" or not op.provider_capture_id:
            raise AppError("NOT_CAPTURED", "Only a completed capture can be refunded.", 409)
        used = db.execute(select(func.coalesce(func.sum(Refund.amount), 0)).where(Refund.operation_id == op.id, Refund.state.in_(("pending", "completed", "reconciling")))).scalar()
        remaining = op.captured_amount - Decimal(used)
        if amt > remaining:
            raise AppError("REFUND_EXCEEDS_CAPTURE", f"At most {op.currency} {fmt(remaining)} can still be refunded.", 409)
        r = Refund(workspace_id=op.workspace_id, operation_id=op.id, capture_id=op.provider_capture_id, amount=amt, currency=op.currency, state="pending",
                   request_id_header=f"qg-refund-{uuid.uuid4().hex}", note=note.strip()[:300], requested_by=actor.user_id, created_at=timeutil.now())
        db.add(r)
        db.flush()
        rid, cap_id, cur, req_hdr, adapter_kind = r.id, op.provider_capture_id, op.currency, r.request_id_header, op.adapter
        audit.record(db, "refund.intent", workspace_id=op.workspace_id, actor_id=actor.user_id, object_type="refund", object_id=r.id, request_id=op.request_id, meta={"amount": fmt(amt), "capture_id": cap_id})
    try:
        res = get_adapter(adapter_kind).refund_capture(cap_id, fmt(amt), cur, req_hdr, note)
        state, ref = ("completed" if res.body.get("status") == "COMPLETED" else "reconciling"), res.body.get("id")
    except ProviderAmbiguous:
        state, ref = "reconciling", None
    except ProviderError as e:
        state, ref = "failed", None
        with db_factory() as db:
            db.get(Refund, rid).state = "failed"
        raise AppError("PROVIDER_REJECTED", f"PayPal rejected the refund: {e.message}", 502) from None
    with db_factory() as db:
        op = _lock_op(db, db.get(Refund, rid).operation_id)
        r = db.get(Refund, rid, with_for_update=True, populate_existing=True)
        r.state, r.provider_refund_id = state, ref
        _tx(db, op.id, "refund", "ok" if state != "reconciling" else "timeout", request_id=req_hdr, ref=ref, status=state)
        _event(db, op, "done" if state == "completed" else "warning", f"Refund {state}: {cur} {fmt(amt)}", f"Provider refund {ref or 'pending lookup'} against capture {cap_id}.", actor=actor.label, tool="paypal.captures.refund")
        return op_json(op, db)
