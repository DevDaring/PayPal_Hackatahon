"""Comparison: build facts from stored quote versions, evaluate deterministically, explain."""

from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, jobs, timeutil
from ..ai.prompts import CHAT_SYSTEM, EXPLAIN_PROMPT_VERSION, EXPLAIN_SYSTEM
from ..ai.provider import AIUnavailable, chat_json
from ..config import get_settings
from ..domain import policy, whatif
from ..domain.requirements import RequirementSpec
from ..errors import AppError
from ..models import (
    Approval,
    Document,
    Evaluation,
    EvidenceLink,
    MerchantBinding,
    PolicyVersion,
    PurchaseRequest,
    Quote,
    QuoteVersion,
    RequestVersion,
    Supplier,
    Workspace,
)
from ..money import fmt
from .context import Actor


def policy_row(db: Session) -> PolicyVersion:
    row = db.execute(select(PolicyVersion).where(PolicyVersion.name == policy.POLICY_NAME, PolicyVersion.version == policy.POLICY_VERSION)).scalar_one_or_none()
    if row is None:
        row = PolicyVersion(name=policy.POLICY_NAME, version=policy.POLICY_VERSION, rules=policy.POLICY_RULES, created_at=timeutil.now())
        db.add(row)
        db.flush()
    return row


def active_binding(db: Session, supplier_id) -> MerchantBinding | None:
    if supplier_id is None:
        return None
    return db.execute(select(MerchantBinding).where(MerchantBinding.supplier_id == supplier_id, MerchantBinding.status == "active")).scalar_one_or_none()


def checkout_status(db: Session, quote: Quote, req: PurchaseRequest) -> tuple[bool, str, MerchantBinding | None]:
    """Separate from compliance: is there an independently configured merchant for this supplier?"""
    if quote.supplier_link != "confirmed":
        return False, "Supplier identity not confirmed by a person; names printed in a PDF are never trusted for payment.", None
    b = active_binding(db, quote.supplier_id)
    if b is None:
        return False, "No PayPal merchant is configured for this supplier.", None
    if b.verified_at is None:
        return False, "Merchant binding has not been verified by an admin.", b
    if b.adapter == "sandbox":
        if not get_settings().paypal_credentials_present:
            return False, "PayPal sandbox credentials are not configured on the server.", b
        if get_settings().PAYPAL_MERCHANT_ID and b.merchant_id != get_settings().PAYPAL_MERCHANT_ID:
            return False, "Merchant binding does not match the configured PayPal sandbox merchant.", b
        return True, f"PayPal sandbox merchant {b.merchant_id}", b
    if b.adapter == "simulated":
        ws = db.get(Workspace, req.workspace_id)
        if get_settings().MOCK_PAYPAL or (ws.is_demo and req.lab_scenario):
            return True, "Simulated PayPal provider (controlled Demo Lab test — not a sandbox transaction)", b
        return False, "Simulated provider is only available in Demo Lab scenarios.", b
    return False, "Unknown merchant adapter.", b


def facts(db: Session, req: PurchaseRequest) -> list[tuple[Quote, QuoteVersion, policy.QuoteFacts, str]]:
    out = []
    quotes = db.execute(select(Quote).where(Quote.request_id == req.id).order_by(Quote.created_at)).scalars().all()
    for q in quotes:
        qv = db.get(QuoteVersion, q.current_version_id)
        ok, reason, _ = checkout_status(db, q, req)
        sup = db.get(Supplier, q.supplier_id) if q.supplier_id else None
        f = policy.QuoteFacts(
            quote_id=str(q.id), supplier=(sup.name if sup and q.supplier_link == "confirmed" else (qv.supplier_name or "Unknown supplier")), currency=qv.currency, currency_status=qv.currency_status,
            quantity=qv.quantity, subtotal=qv.subtotal, shipping=qv.shipping, tax=qv.tax, discount=qv.discount, stated_total=qv.stated_total,
            delivery_days=qv.delivery_days, valid_until=qv.valid_until, attributes={k: v for k, v in (qv.attributes or {}).items() if not k.startswith("_")},
            needs_review=qv.needs_review, checkout_available=ok, unit_price=qv.unit_price,
            scalable_pricing=(qv.attributes or {}).get("_scalable_pricing") == "yes", flat_shipping=(qv.attributes or {}).get("_flat_shipping") == "yes",
            attribute_sources={k[5:]: v for k, v in (qv.attributes or {}).items() if k.startswith("_src_") and v},
        )
        out.append((q, qv, f, reason))
    if out:
        from . import integrity

        verdicts = integrity.assess(db, req, out)["per_quote"]
        for q, _, f, _ in out:
            f.integrity = {k: verdicts[str(q.id)][k] for k in ("status", "detail")}
    return out


def order_date(req: PurchaseRequest):
    return timeutil.local_date(req.timezone)


def evaluate_request(db: Session, request_id) -> dict | None:
    req = db.get(PurchaseRequest, uuid.UUID(str(request_id)), with_for_update=True, populate_existing=True)
    if req is None or req.current_version_id is None:
        return None
    rv = db.get(RequestVersion, req.current_version_id)
    spec = RequirementSpec.model_validate(rv.requirements)
    rows = facts(db, req)
    pol = policy_row(db)
    outs = policy.evaluate_all(spec, [r[2] for r in rows], order_date(req))
    by_id = {o.quote_id: o for o in outs}
    for q, qv, f, _ in rows:
        o = by_id[str(q.id)]
        ev = db.execute(select(Evaluation).where(Evaluation.request_version_id == rv.id, Evaluation.quote_version_id == qv.id, Evaluation.policy_version_id == pol.id)).scalar_one_or_none()
        if ev is None:
            ev = Evaluation(request_version_id=rv.id, quote_version_id=qv.id, policy_version_id=pol.id, created_at=timeutil.now())
            db.add(ev)
        ev.checks, ev.mandatory_status, ev.verified_total = [c.as_dict() for c in o.checks], o.mandatory_status, o.verified_total
        ev.checkout_available, ev.payment_eligible, ev.compliant_rank = o.checkout_available, o.payment_eligible, o.compliant_rank
    summary = policy.summarize(outs, [r[2] for r in rows])
    docs = db.execute(select(Document).where(Document.request_id == req.id)).scalars().all()
    pending = [d for d in docs if d.status in ("uploaded", "extracting")]
    live = db.execute(select(Approval).where(Approval.request_id == req.id, Approval.status.in_(("active", "consumed_for_execution")))).scalar_one_or_none()
    if req.status not in ("canceled", "superseded"):
        if live:
            req.status = "approved"
        elif pending:
            req.status = "analyzing"
        elif summary["no_compliant_quote"] and summary["unknowns"]:
            req.status = "needs_clarification"
        elif rows:
            req.status = "ready_for_review"
    if not pending and rows:
        best = summary["best_compliant_supplier"]
        if best:
            title = f"Recommended: {best} at {rv.currency} {summary['best_compliant_total']}"
            detail = "Lowest verified total among quotes that pass every mandatory requirement." + ("" if summary["best_has_checkout"] else " Checkout is not configured for this supplier.")
        else:
            title, detail = "No fully compliant quote", "No quote passes every mandatory requirement; nothing is recommended. Resolve unknowns or adjust requirements."
        if summary["why_cheapest_loses"]:
            w = summary["why_cheapest_loses"]
            detail += f" Cheapest headline quote ({w['supplier']}) loses: " + "; ".join(c["detail"] for c in w["blocking_checks"])
        audit.event(db, workspace_id=req.workspace_id, request_id=req.id, stage="recommend", status="done" if best else "warning", title=title, detail=detail,
                    refs={"request_version": rv.version, "policy_version": pol.version, "quote_id": summary["best_compliant_quote_id"]}, tool="policy_engine")
    return summary


# ------------------------------------------------------------------- views ----------
def evidence_index(db: Session, qv_ids: list) -> dict:
    links = db.execute(select(EvidenceLink).where(EvidenceLink.quote_version_id.in_(qv_ids)).order_by(EvidenceLink.quote_version_id, EvidenceLink.field)).scalars().all()
    return {ln.id: ln for ln in links}


def evidence_json(ln: EvidenceLink) -> dict:
    return {"id": str(ln.id), "field": ln.field, "document_id": str(ln.document_id), "document_sha256": ln.document_sha256, "quote_version": ln.quote_version,
            "page": ln.page_number, "source_text": ln.source_text, "method": ln.extraction_method, "location": ln.location_status, "bbox": ln.bbox}


def quote_version_json(qv: QuoteVersion) -> dict:
    return {
        "id": str(qv.id), "version": qv.version, "supplier_name": qv.supplier_name, "currency": qv.currency, "currency_status": qv.currency_status, "quantity": qv.quantity,
        "unit_price": fmt(qv.unit_price), "subtotal": fmt(qv.subtotal), "shipping": fmt(qv.shipping), "tax": fmt(qv.tax), "discount": fmt(qv.discount),
        "stated_total": fmt(qv.stated_total), "computed_total": fmt(qv.computed_total), "arithmetic_status": qv.arithmetic_status, "delivery_days": qv.delivery_days,
        "delivery_text": qv.delivery_text, "issue_date": qv.issue_date.isoformat() if qv.issue_date else None, "valid_until": qv.valid_until.isoformat() if qv.valid_until else None,
        "product_description": qv.product_description, "attributes": {k: v for k, v in (qv.attributes or {}).items() if not k.startswith("_")},
        "scalable_pricing": (qv.attributes or {}).get("_scalable_pricing") == "yes", "shipping_terms": qv.shipping_terms, "pricing_terms": qv.pricing_terms,
        "issues": qv.issues, "needs_review": qv.needs_review, "extraction_method": qv.extraction_method, "model": qv.model, "reason": qv.reason, "correction": qv.correction,
        "created_at": qv.created_at.isoformat(),
    }


def comparison(db: Session, actor: Actor, req: PurchaseRequest) -> dict:
    rv = db.get(RequestVersion, req.current_version_id) if req.current_version_id else None
    if rv is None:
        return {"request_version": None, "quotes": [], "summary": None}
    spec = RequirementSpec.model_validate(rv.requirements)
    rows = facts(db, req)
    outs = policy.evaluate_all(spec, [r[2] for r in rows], order_date(req))
    by_id = {o.quote_id: o for o in outs}
    ev = evidence_index(db, [r[1].id for r in rows])
    quotes = []
    for q, qv, f, checkout_reason in rows:
        doc = db.get(Document, q.document_id)
        b = active_binding(db, q.supplier_id) if q.supplier_link == "confirmed" else None
        quotes.append({
            "quote_id": str(q.id), "supplier": f.supplier, "supplier_link": q.supplier_link, "supplier_confirmed_by": q.supplier_confirmed_by,
            "document": {"id": str(doc.id), "filename": doc.filename, "sha256": doc.sha256, "pages": doc.page_count, "is_sample": doc.is_sample, "suspicious": doc.suspicious},
            "version": quote_version_json(qv), "outcome": by_id[str(q.id)].as_dict(), "checkout_reason": checkout_reason,
            "merchant": {"merchant_id": b.merchant_id, "adapter": b.adapter, "label": b.display_label} if b else None,
            "evidence": [evidence_json(ln) for ln in ev.values() if ln.quote_version_id == qv.id],
        })
    return {"request_version": {"id": str(rv.id), "version": rv.version, "requirements": rv.requirements}, "order_date": order_date(req).isoformat(),
            "quotes": quotes, "summary": policy.summarize(outs, [r[2] for r in rows]), "policy": {"name": policy.POLICY_NAME, "version": policy.POLICY_VERSION, "rules": policy.POLICY_RULES},
            "explanation": req.explanation}


def whatif_preview(db: Session, actor: Actor, req: PurchaseRequest, budget=None, deadline_days=None, quantity=None) -> dict:
    rv = db.get(RequestVersion, req.current_version_id) if req.current_version_id else None
    if rv is None:
        raise AppError("REQUEST_NOT_CONFIRMED", "Confirm the requirements first.", 409)
    spec = RequirementSpec.model_validate(rv.requirements)
    rows = facts(db, req)
    return whatif.preview(spec, [r[2] for r in rows], order_date(req), budget=budget, deadline_days=deadline_days, quantity=quantity)


# ------------------------------------------------------------- explanation ----------
def _explain_input(db: Session, req: PurchaseRequest) -> tuple[dict, dict]:
    rv = db.get(RequestVersion, req.current_version_id)
    spec = RequirementSpec.model_validate(rv.requirements)
    rows = facts(db, req)
    outs = policy.evaluate_all(spec, [r[2] for r in rows], order_date(req))
    evid: dict[str, dict] = {}
    quotes = []
    n = 0
    for (q, qv, f, reason), o in zip(rows, outs, strict=True):
        ids = []
        for ln in db.execute(select(EvidenceLink).where(EvidenceLink.quote_version_id == qv.id)).scalars():
            if ln.field in ("total", "shipping", "tax", "subtotal", "delivery_days", "valid_until", "currency") or ln.field.startswith("attr:"):
                n += 1
                key = f"E{n}"
                evid[key] = {"evidence_id": str(ln.id), "quote_id": str(q.id), "field": ln.field, "page": ln.page_number, "text": (ln.source_text or "")[:200]}
                ids.append(key)
        quotes.append({"supplier": f.supplier, "outcome": o.as_dict(), "evidence_ids": ids, "checkout": reason})
    payload = {"requirements": {"item": spec.item, "quantity": spec.quantity, "budget": f"{spec.currency} {spec.budget_amount}", "deadline": spec.deadline_date.isoformat() if spec.deadline_date else None,
                                "mandatory": [c.label for c in spec.mandatory]},
               "summary": policy.summarize(outs, [r[2] for r in rows]), "quotes": quotes, "evidence": {k: {"field": v["field"], "page": v["page"], "text": v["text"]} for k, v in evid.items()}}
    return payload, evid


def _fallback_explanation(payload: dict) -> dict:
    s = payload["summary"]
    paras = []
    if s["best_compliant_supplier"]:
        paras.append(f"{s['best_compliant_supplier']} is the best compliant quote at {payload['requirements']['budget'].split()[0]} {s['best_compliant_total']}: it passes every mandatory requirement and has the lowest verified total among compliant quotes.")
    else:
        paras.append("No quote passes every mandatory requirement, so QuoteGuard does not recommend one.")
    rejected = []
    for q in payload["quotes"]:
        bad = [c for c in q["outcome"]["checks"] if c["status"] != "pass"]
        if bad:
            rejected.append({"supplier": q["supplier"], "reason": "; ".join(c["detail"] for c in bad)})
    return {"headline": (f"Buy from {s['best_compliant_supplier']}" if s["best_compliant_supplier"] else "No compliant quote yet"), "paragraphs": paras, "rejected": rejected,
            "questions_for_suppliers": [f"{u['supplier']}: {u['check']['detail']}" for u in s["unknowns"]][:5]}


def explain(db_factory, request_id) -> None:
    with db_factory() as db:
        req = db.get(PurchaseRequest, uuid.UUID(str(request_id)))
        if req is None or req.current_version_id is None:
            return
        payload, evid = _explain_input(db, req)
        key = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        if req.explanation and req.explanation.get("input_hash") == key:
            return
        ws_id = req.workspace_id
    try:
        out, meta = chat_json(EXPLAIN_SYSTEM, "Computed comparison (data):\n" + json.dumps(payload, default=str), purpose="explain", workspace_id=ws_id, request_id=request_id, max_tokens=1200, temperature=0.2)
        method, model = "llm", meta["model"]
        out = {"headline": str(out.get("headline", ""))[:160], "paragraphs": [str(p)[:900] for p in (out.get("paragraphs") or [])][:4],
               "rejected": [{"supplier": str(r.get("supplier", ""))[:120], "reason": str(r.get("reason", ""))[:400]} for r in (out.get("rejected") or []) if isinstance(r, dict)][:6],
               "questions_for_suppliers": [str(x)[:300] for x in (out.get("questions_for_suppliers") or [])][:5]}
        # Guard: the explanation may not name a different recommended supplier than the policy engine.
        best = payload["summary"]["best_compliant_supplier"]
        if best and best.split()[0].lower() not in (out["headline"] + " ".join(out["paragraphs"])).lower():
            out, method, model = _fallback_explanation(payload), "template", None
    except AIUnavailable:
        out, method, model = _fallback_explanation(payload), "template", None
    with db_factory() as db:
        req = db.get(PurchaseRequest, uuid.UUID(str(request_id)), with_for_update=True, populate_existing=True)
        req.explanation = {**out, "method": method, "model": model, "prompt_version": EXPLAIN_PROMPT_VERSION if method == "llm" else None, "input_hash": key,
                           "evidence": evid, "generated_at": timeutil.now().isoformat(),
                           "disclaimer": "Generated summary of a deterministic result. It is not the model's private reasoning and cannot change totals or eligibility."}


def chat(db: Session, actor: Actor, req: PurchaseRequest, question: str) -> dict:
    from ..ai import paypal_tools
    from ..ai.provider import chat_with_tools
    from ..models import PaymentOperation

    if not (2 <= len(question) <= 600):
        raise AppError("INVALID_QUESTION", "Ask a question of 2–600 characters.", 422)
    if req.current_version_id is None:
        raise AppError("REQUEST_NOT_CONFIRMED", "Confirm the requirements first.", 409)
    payload, evid = _explain_input(db, req)
    op = db.execute(select(PaymentOperation).where(PaymentOperation.request_id == req.id).order_by(PaymentOperation.created_at.desc()).limit(1)).scalar_one_or_none()
    if op is not None:
        payload["payment"] = {"state": op.state, "amount": fmt(op.amount), "currency": op.currency, "has_paypal_order": bool(op.provider_order_id), "has_capture": bool(op.provider_capture_id)}
    user = "Authorised context (data):\n" + json.dumps(payload, default=str) + f"\n\nQuestion: <question>{question}</question>"
    tools_on = op is not None and paypal_tools.available(op.provider_order_id, op.adapter)
    try:
        if tools_on:
            order_id, capture_id = op.provider_order_id, op.provider_capture_id
            out, meta, trace = chat_with_tools(CHAT_SYSTEM + "\nFor live PayPal payment status, call the read-only PayPal tools instead of guessing.", user, paypal_tools.TOOLS,
                                               lambda name: paypal_tools.execute(name, order_id, capture_id), purpose="chat", workspace_id=actor.workspace_id, request_id=req.id)
        else:
            out, meta = chat_json(CHAT_SYSTEM, user, purpose="chat", workspace_id=actor.workspace_id, request_id=req.id, max_tokens=700, temperature=0.2)
            trace = []
        cites = [c for c in (out.get("citations") or []) if isinstance(c, str) and c in evid]
        if trace:
            audit.event(db, workspace_id=req.workspace_id, request_id=req.id, stage="payment", status="info", title="Assistant queried PayPal (read-only Agent Toolkit tools)",
                        detail=", ".join(t["tool"] for t in trace), actor=actor.label, tool="paypal_agent_toolkit")
        return {"answer": str(out.get("answer", ""))[:2000], "citations": [{"key": c, **evid[c]} for c in cites], "model": meta["model"],
                "tool_calls": [{"tool": t["tool"], "source": t["source"], "result": t["result"]} for t in trace], "tools_available": tools_on}
    except AIUnavailable:
        return {"answer": "The AI assistant is not available right now. The comparison, evidence and checks on this page are computed without it.", "citations": [], "model": None, "tool_calls": [], "tools_available": tools_on}
