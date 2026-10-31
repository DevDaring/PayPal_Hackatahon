"""Organisation approval bound to the exact purchase (canonical snapshot + hash).

Lock order everywhere: purchase_requests → approvals → payment_operations.
"""

from __future__ import annotations

import hmac
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, timeutil
from ..config import get_settings
from ..domain import policy
from ..domain.requirements import RequirementSpec
from ..domain.snapshot import canonical_json, diff, snapshot_hash
from ..errors import AppError, not_found
from ..models import (
    Approval,
    ApprovalDecision,
    Document,
    MerchantBinding,
    PaymentOperation,
    PurchaseRequest,
    PurchaseSnapshot,
    Quote,
    QuoteItem,
    QuoteVersion,
    RequestVersion,
    Supplier,
    Workspace,
)
from ..money import SUPPORTED_CHECKOUT_CURRENCIES, fmt
from ..security import sign
from . import comparison
from .context import Actor, get_request, parse_uuid


def _lock_request(db: Session, req_id) -> PurchaseRequest:
    return db.execute(select(PurchaseRequest).where(PurchaseRequest.id == req_id).with_for_update()).scalar_one()


def build_terms(db: Session, req: PurchaseRequest, quote: Quote) -> dict:
    """The exact purchase, rebuilt purely from current authoritative database state."""
    rv = db.get(RequestVersion, req.current_version_id)
    qv = db.get(QuoteVersion, quote.current_version_id)
    doc = db.get(Document, quote.document_id)
    sup = db.get(Supplier, quote.supplier_id) if quote.supplier_id else None
    ok, reason, b = comparison.checkout_status(db, quote, req)
    items = db.execute(select(QuoteItem).where(QuoteItem.quote_version_id == qv.id).order_by(QuoteItem.description)).scalars().all()
    return {
        "schema": "quoteguard.purchase-terms.v1",
        "workspace_id": str(req.workspace_id),
        "request": {"id": str(req.id), "version_id": str(rv.id), "version": rv.version, "budget": fmt(rv.budget_amount), "currency": rv.currency},
        "quote": {"id": str(quote.id), "version_id": str(qv.id), "version": qv.version, "document_sha256": doc.sha256},
        "supplier": {"id": str(sup.id) if sup else None, "name": sup.name if sup else qv.supplier_name, "link": quote.supplier_link},
        "merchant": None if b is None else {"binding_id": str(b.id), "binding_version": b.version, "provider": b.provider, "environment": b.environment, "adapter": b.adapter, "merchant_id": b.merchant_id},
        "line_items": [{"description": i.description, "quantity": i.quantity, "unit_price": fmt(i.unit_price), "line_total": fmt(i.line_total)} for i in items],
        "quantity": qv.quantity,
        "currency": qv.currency,
        "amounts": {"subtotal": fmt(qv.subtotal), "shipping": fmt(qv.shipping), "tax": fmt(qv.tax), "discount": fmt(qv.discount), "total": fmt(qv.computed_total)},
        "shipping_terms": qv.shipping_terms,
        "delivery_promise_days": qv.delivery_days,
        "policy": {"name": policy.POLICY_NAME, "version": policy.POLICY_VERSION},
    }


def _eligibility(db: Session, req: PurchaseRequest, quote: Quote) -> policy.QuoteOutcome:
    rv = db.get(RequestVersion, req.current_version_id)
    spec = RequirementSpec.model_validate(rv.requirements)
    rows = comparison.facts(db, req)
    outs = policy.evaluate_all(spec, [r[2] for r in rows], comparison.order_date(req))
    return next(o for o in outs if o.quote_id == str(quote.id))


def _ineligible_error(o: policy.QuoteOutcome, currency: str | None) -> AppError:
    if currency and currency not in SUPPORTED_CHECKOUT_CURRENCIES:
        return AppError("UNSUPPORTED_CURRENCY", f"Checkout supports {', '.join(sorted(SUPPORTED_CHECKOUT_CURRENCIES))} only; this quote is in {currency}.", 409)
    if o.mandatory_status == "fail":
        return AppError("QUOTE_NOT_ELIGIBLE", "This quote fails a mandatory requirement: " + "; ".join(c.detail for c in o.checks if c.status == "fail"), 409)
    if o.mandatory_status == "unknown":
        return AppError("QUOTE_NEEDS_REVIEW", "Resolve unknown terms before approval: " + "; ".join(c.detail for c in o.checks if c.status == "unknown"), 409)
    if not o.checkout_available:
        return AppError("MERCHANT_UNCONFIGURED", "This supplier has no configured, verified PayPal merchant.", 409)
    return AppError("QUOTE_NOT_ELIGIBLE", "This quote is not payment-eligible.", 409)


def _find_quote(db: Session, actor: Actor, req: PurchaseRequest, quote_id) -> Quote:
    q = db.execute(select(Quote).where(Quote.id == parse_uuid(quote_id, "Quote"), Quote.request_id == req.id, Quote.workspace_id == actor.workspace_id)).scalar_one_or_none()
    if q is None:
        raise not_found("Quote")
    return q


def review(db: Session, actor: Actor, request_id, quote_id) -> dict:
    req = get_request(db, actor, request_id)
    if req.current_version_id is None:
        raise AppError("REQUEST_NOT_CONFIRMED", "Confirm the requirements first.", 409)
    quote = _find_quote(db, actor, req, quote_id)
    terms = build_terms(db, req, quote)
    o = _eligibility(db, req, quote)
    ws = db.get(Workspace, actor.workspace_id)
    self_blocked = req.created_by == actor.user_id and not ws.self_approval_allowed
    return {"terms": terms, "terms_hash": snapshot_hash(terms), "outcome": o.as_dict(), "eligible": o.payment_eligible,
            "can_approve": "approver" in actor.roles and not self_blocked and o.payment_eligible,
            "blocked_reason": None if o.payment_eligible else _ineligible_error(o, terms["currency"]).message,
            "self_approval_blocked": self_blocked, "approval_ttl_minutes": get_settings().APPROVAL_TTL_MINUTES}


def approve(db: Session, actor: Actor, request_id, quote_id, terms_hash: str, note: str | None = None) -> Approval:
    actor.require("approver")
    req = get_request(db, actor, request_id, for_update=True)
    if req.status in ("canceled", "superseded") or req.current_version_id is None:
        raise AppError("REQUEST_CLOSED", "This request cannot be approved.", 409)
    ws = db.get(Workspace, actor.workspace_id)
    if req.created_by == actor.user_id and not ws.self_approval_allowed:
        raise AppError("SELF_APPROVAL_DISABLED", "Requesters cannot approve their own purchases in this workspace.", 403)
    quote = _find_quote(db, actor, req, quote_id)
    terms = build_terms(db, req, quote)
    o = _eligibility(db, req, quote)
    if not o.payment_eligible:
        raise _ineligible_error(o, terms["currency"])
    current_hash = snapshot_hash(terms)
    if not hmac.compare_digest(current_hash, terms_hash or ""):
        raise AppError("SNAPSHOT_CHANGED", "The purchase terms changed after you opened this review. Review the updated terms.", 409)
    live = db.execute(select(Approval).where(Approval.request_id == req.id, Approval.status.in_(("active", "consumed_for_execution")))).scalar_one_or_none()
    if live:
        raise AppError("APPROVAL_EXISTS", "This request already has a live approval. Revoke it first to approve different terms.", 409)
    expires = timeutil.now() + timedelta(minutes=get_settings().APPROVAL_TTL_MINUTES)
    snapshot = {**terms, "approval": {"approver_id": str(actor.user_id), "expires_at": expires.isoformat()}}
    snap = PurchaseSnapshot(workspace_id=actor.workspace_id, request_id=req.id, request_version_id=req.current_version_id, quote_version_id=quote.current_version_id,
                            merchant_binding_id=terms["merchant"]["binding_id"], canonical=snapshot, canonical_json=canonical_json(snapshot), terms_hash=current_hash,
                            hash=snapshot_hash(snapshot), total=o.verified_total, currency=terms["currency"], created_at=timeutil.now())
    db.add(snap)
    db.flush()
    token = sign(f"{snap.id}|{snap.hash}|{expires.isoformat()}", get_settings().APPROVAL_SIGNING_SECRET)
    appr = Approval(workspace_id=actor.workspace_id, request_id=req.id, snapshot_id=snap.id, snapshot_hash=snap.hash, status="active", requested_by=req.created_by,
                    approver_id=actor.user_id, approver_principal_id=actor.principal_id, note=note, signed_token=token, expires_at=expires, created_at=timeutil.now())
    db.add(appr)
    db.add(ApprovalDecision(workspace_id=actor.workspace_id, request_id=req.id, snapshot_id=snap.id, quote_id=quote.id, decision="approved", actor_id=actor.user_id, note=note, created_at=timeutil.now()))
    req.status = "approved"
    db.flush()
    audit.record(db, "approval.issued", workspace_id=actor.workspace_id, actor_id=actor.user_id, principal_id=actor.principal_id, object_type="approval", object_id=appr.id, request_id=req.id,
                 meta={"snapshot_hash": snap.hash, "terms_hash": current_hash, "total": fmt(o.verified_total), "currency": terms["currency"], "merchant_id": terms["merchant"]["merchant_id"], "expires_at": expires.isoformat()})
    audit.event(db, workspace_id=actor.workspace_id, request_id=req.id, stage="approve", status="done", title=f"Approval issued by {actor.label}",
                detail=f"Bound to snapshot {snap.hash[:12]}… — {terms['supplier']['name']}, {terms['currency']} {fmt(o.verified_total)}, merchant {terms['merchant']['merchant_id']}; expires {expires.strftime('%H:%M UTC')}.",
                refs={"approval_id": appr.id, "snapshot_hash": snap.hash}, actor=actor.label)
    return appr


def reject(db: Session, actor: Actor, request_id, quote_id, note: str) -> None:
    actor.require("approver")
    if not note or len(note.strip()) < 4:
        raise AppError("NOTE_REQUIRED", "Give a short reason for the rejection.", 422)
    req = get_request(db, actor, request_id, for_update=True)
    quote = _find_quote(db, actor, req, quote_id)
    db.add(ApprovalDecision(workspace_id=actor.workspace_id, request_id=req.id, quote_id=quote.id, decision="rejected", actor_id=actor.user_id, note=note, created_at=timeutil.now()))
    audit.record(db, "approval.rejected", workspace_id=actor.workspace_id, actor_id=actor.user_id, object_type="purchase_request", object_id=req.id, request_id=req.id, meta={"quote_id": str(quote.id), "note": note})
    audit.event(db, workspace_id=actor.workspace_id, request_id=req.id, stage="approve", status="blocked", title=f"Rejected by {actor.label}", detail=note, actor=actor.label)


def _end(appr: Approval, status: str, reason: str, details: dict | None = None) -> None:
    appr.status, appr.ended_at, appr.end_reason, appr.end_details = status, timeutil.now(), reason, details


def invalidate_for_request(db: Session, req: PurchaseRequest, reason: str, *, actor: Actor | None = None, details: dict | None = None) -> int:
    """Called by every change that could alter the purchase. In-flight captures freeze changes."""
    _lock_request(db, req.id)
    lives = db.execute(select(Approval).where(Approval.request_id == req.id, Approval.status.in_(("active", "consumed_for_execution"))).with_for_update()).scalars().all()
    n = 0
    for appr in lives:
        op = db.execute(select(PaymentOperation).where(PaymentOperation.approval_id == appr.id).with_for_update()).scalar_one_or_none()
        if op is not None and op.state in ("capture_pending", "reconciling"):
            raise AppError("PAYMENT_IN_PROGRESS", "A payment capture is in progress for the approved snapshot; changes are frozen until it is reconciled.", 409)
        if op is not None and op.state == "completed":
            raise AppError("PURCHASE_COMPLETED", "This purchase is already paid. Create a new request for different terms.", 409)
        if op is not None and op.state in ("not_started", "order_creating", "awaiting_payer"):
            op.state, op.last_error_code, op.last_error_message, op.updated_at = "canceled", "APPROVAL_INVALIDATED", reason, timeutil.now()
        _end(appr, "invalidated", reason, details)
        n += 1
        audit.record(db, "approval.invalidated", workspace_id=req.workspace_id, actor_id=actor.user_id if actor else None, object_type="approval", object_id=appr.id, request_id=req.id, meta={"reason": reason, **(details or {})})
        audit.event(db, workspace_id=req.workspace_id, request_id=req.id, stage="approve", status="blocked", title="Approval invalidated", detail=reason + ". A fresh approval is required.",
                    refs={"approval_id": appr.id}, actor=actor.label if actor else "system")
    if n and req.status == "approved":
        req.status = "ready_for_review"
    return n


def revalidate(db: Session, appr: Approval, *, allow_consumed: bool) -> dict:
    """Server-side authority check before order creation and before capture.

    Raises (and persists the ending of the approval) when anything relevant changed.
    The caller must hold the request and approval row locks.
    """
    allowed = ("active", "consumed_for_execution") if allow_consumed else ("active",)
    if appr.status not in allowed:
        code = {"expired": "APPROVAL_EXPIRED", "revoked": "APPROVAL_REVOKED", "invalidated": "SNAPSHOT_CHANGED", "consumed_for_execution": "APPROVAL_CONSUMED"}.get(appr.status, "APPROVAL_INVALID")
        raise AppError(code, f"This approval is {appr.status.replace('_', ' ')}" + (f": {appr.end_reason}" if appr.end_reason else "."), 409, {"details": appr.end_details})
    snap = db.get(PurchaseSnapshot, appr.snapshot_id)
    expected = sign(f"{snap.id}|{snap.hash}|{appr.expires_at.isoformat()}", get_settings().APPROVAL_SIGNING_SECRET)
    if not hmac.compare_digest(expected, appr.signed_token) or snap.hash != appr.snapshot_hash:
        _end(appr, "invalidated", "Approval signature check failed")
        raise AppError("APPROVAL_INVALID", "Approval integrity check failed.", 409)
    if timeutil.now() >= appr.expires_at:
        _end(appr, "expired", "Approval expired before execution")
        audit.event(db, workspace_id=appr.workspace_id, request_id=appr.request_id, stage="approve", status="blocked", title="Approval expired", detail="Execution blocked; request a fresh approval.")
        raise AppError("APPROVAL_EXPIRED", "The approval expired. Ask an approver to approve the current terms again.", 409)
    req = db.get(PurchaseRequest, appr.request_id)
    quote = db.get(Quote, parse_uuid(snap.canonical["quote"]["id"]))
    current = build_terms(db, req, quote)
    approved_terms = {k: v for k, v in snap.canonical.items() if k != "approval"}
    if snapshot_hash(current) != snap.terms_hash:
        changes = diff(approved_terms, current)
        code = "MERCHANT_CHANGED" if any(c["field"].startswith("merchant") for c in changes) else "SNAPSHOT_CHANGED"
        _end(appr, "invalidated", "Purchase terms changed after approval", {"changes": changes})
        audit.record(db, "approval.blocked_execution", workspace_id=appr.workspace_id, object_type="approval", object_id=appr.id, request_id=appr.request_id, meta={"code": code, "changes": changes})
        audit.event(db, workspace_id=appr.workspace_id, request_id=appr.request_id, stage="execute", status="blocked", title="Execution blocked: approved terms no longer match",
                    detail="; ".join(f"{c['field']}: {c['approved']} → {c['current']}" for c in changes[:6]), refs={"approval_id": appr.id, "code": code}, tool="snapshot_guard")
        if req.status == "approved":
            req.status = "ready_for_review"
        raise AppError(code, "The purchase changed after approval, so execution is blocked and a fresh approval is required.", 409, {"changes": changes})
    o = _eligibility(db, req, quote)
    if not o.payment_eligible:
        _end(appr, "invalidated", "Quote is no longer payment-eligible")
        raise _ineligible_error(o, current["currency"])
    return snap.canonical


def revoke(db: Session, actor: Actor, approval_id, reason: str) -> Approval:
    actor.require("approver", "admin")
    appr = db.execute(select(Approval).where(Approval.id == parse_uuid(approval_id, "Approval"), Approval.workspace_id == actor.workspace_id)).scalar_one_or_none()
    if appr is None:
        raise not_found("Approval")
    _lock_request(db, appr.request_id)
    appr = db.execute(select(Approval).where(Approval.id == appr.id).with_for_update()).scalar_one()
    if appr.status not in ("active", "consumed_for_execution"):
        return appr
    op = db.execute(select(PaymentOperation).where(PaymentOperation.approval_id == appr.id).with_for_update()).scalar_one_or_none()
    if op and op.state in ("capture_pending", "reconciling", "completed"):
        raise AppError("PAYMENT_IN_PROGRESS", "Payment is already being captured or is complete; the approval can no longer be revoked.", 409)
    if op:
        op.state, op.last_error_code, op.updated_at = "canceled", "APPROVAL_REVOKED", timeutil.now()
    _end(appr, "revoked", reason or "Revoked")
    req = db.get(PurchaseRequest, appr.request_id)
    if req.status == "approved":
        req.status = "ready_for_review"
    audit.record(db, "approval.revoked", workspace_id=actor.workspace_id, actor_id=actor.user_id, object_type="approval", object_id=appr.id, request_id=appr.request_id, meta={"reason": reason})
    audit.event(db, workspace_id=actor.workspace_id, request_id=appr.request_id, stage="approve", status="blocked", title=f"Approval revoked by {actor.label}", detail=reason, actor=actor.label)
    return appr


def approval_json(appr: Approval, snap: PurchaseSnapshot | None = None) -> dict:
    return {"id": str(appr.id), "status": appr.status, "snapshot_hash": appr.snapshot_hash, "expires_at": appr.expires_at.isoformat(), "created_at": appr.created_at.isoformat(),
            "approver_id": str(appr.approver_id), "requested_by": str(appr.requested_by), "note": appr.note, "ended_at": appr.ended_at.isoformat() if appr.ended_at else None,
            "end_reason": appr.end_reason, "end_details": appr.end_details, "snapshot": snap.canonical if snap else None, "total": fmt(snap.total) if snap else None,
            "currency": snap.currency if snap else None}


__all__ = ["approve", "reject", "revoke", "review", "revalidate", "invalidate_for_request", "build_terms", "approval_json", "MerchantBinding"]
