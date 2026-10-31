"""Admin-managed merchant bindings. A binding is never created from document content."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, timeutil
from ..errors import AppError, not_found
from ..models import MerchantBinding, PurchaseRequest, Quote, Supplier
from .context import Actor, parse_uuid


def binding_json(b: MerchantBinding, supplier: Supplier | None) -> dict:
    return {"id": str(b.id), "supplier_id": str(b.supplier_id), "supplier": supplier.name if supplier else None, "provider": b.provider, "environment": b.environment,
            "adapter": b.adapter, "merchant_id": b.merchant_id, "label": b.display_label, "status": b.status, "version": b.version,
            "verified_at": b.verified_at.isoformat() if b.verified_at else None, "updated_at": b.updated_at.isoformat()}


def list_bindings(db: Session, actor: Actor) -> list[dict]:
    rows = db.execute(select(MerchantBinding, Supplier).join(Supplier, Supplier.id == MerchantBinding.supplier_id).where(MerchantBinding.workspace_id == actor.workspace_id).order_by(Supplier.name)).all()
    return [binding_json(b, s) for b, s in rows]


def change_merchant(db: Session, actor: Actor, binding_id, merchant_id: str, note: str, *, invalidate: bool = True) -> MerchantBinding:
    """Changing the payee bumps the binding version and invalidates approvals that used it."""
    actor.require("admin")
    merchant_id = (merchant_id or "").strip()
    if not (3 <= len(merchant_id) <= 64) or not merchant_id.replace("-", "").isalnum():
        raise AppError("INVALID_VALUE", "Merchant IDs are 3–64 letters, digits or dashes.", 422)
    b = db.execute(select(MerchantBinding).where(MerchantBinding.id == parse_uuid(binding_id, "Merchant binding"), MerchantBinding.workspace_id == actor.workspace_id).with_for_update()).scalar_one_or_none()
    if b is None:
        raise not_found("Merchant binding")
    old = b.merchant_id
    if invalidate:
        from .approvals import invalidate_for_request

        req_ids = db.execute(select(Quote.request_id).where(Quote.supplier_id == b.supplier_id).distinct()).scalars().all()
        for rid in req_ids:
            invalidate_for_request(db, db.get(PurchaseRequest, rid), f"Payee merchant changed from {old} to {merchant_id}", actor=actor)
    b.merchant_id, b.version, b.updated_at = merchant_id, b.version + 1, timeutil.now()
    audit.record(db, "merchant_binding.changed", workspace_id=actor.workspace_id, actor_id=actor.user_id, object_type="merchant_binding", object_id=b.id, meta={"from": old, "to": merchant_id, "note": note, "version": b.version})
    return b
