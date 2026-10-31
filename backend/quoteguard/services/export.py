"""Downloadable purchase evidence package (JSON + PDF). No tokens, secrets or payer personal data."""

from __future__ import annotations

import io
import json

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session
from xml.sax.saxutils import escape

from .. import audit, timeutil
from ..models import Approval, Document, PaymentOperation, ProviderTransaction, PurchaseRequest, PurchaseSnapshot, Quote, QuoteVersion, RequestVersion, User, WorkflowEvent
from ..money import fmt
from . import comparison
from .context import Actor, get_request

LIMITATIONS = [
    "Supplier documents are synthetic demo samples. An uploaded PDF does not prove supplier identity, inventory or authenticity.",
    "Delivery times are supplier claims, not verified fulfilment.",
    "The audit hash chain detects ordinary modification; a privileged database administrator could rewrite it. It is not immutable proof or a legal certification.",
    "PayPal Sandbox transactions move no real money.",
    "Generated explanations summarise deterministic results; they are not the model's internal reasoning.",
]


def package(db: Session, actor: Actor, request_id) -> dict:
    req = get_request(db, actor, request_id)
    versions = db.execute(select(RequestVersion).where(RequestVersion.request_id == req.id).order_by(RequestVersion.version)).scalars().all()
    quotes = []
    for q in db.execute(select(Quote).where(Quote.request_id == req.id)).scalars():
        doc = db.get(Document, q.document_id)
        qvs = db.execute(select(QuoteVersion).where(QuoteVersion.quote_id == q.id).order_by(QuoteVersion.version)).scalars().all()
        quotes.append({"quote_id": str(q.id), "document": {"filename": doc.filename, "sha256": doc.sha256, "text_sha256": doc.text_sha256, "synthetic_sample": doc.is_sample},
                       "supplier_link": q.supplier_link, "versions": [comparison.quote_version_json(v) for v in qvs]})
    appr_rows = db.execute(select(Approval).where(Approval.request_id == req.id).order_by(Approval.created_at)).scalars().all()
    approvals_out = []
    for a in appr_rows:
        snap = db.get(PurchaseSnapshot, a.snapshot_id)
        approver = db.get(User, a.approver_id)
        approvals_out.append({"approval_id": str(a.id), "status": a.status, "approver": approver.display_name if approver else None, "created_at": a.created_at.isoformat(), "expires_at": a.expires_at.isoformat(),
                              "end_reason": a.end_reason, "snapshot_hash": snap.hash, "terms_hash": snap.terms_hash, "snapshot": snap.canonical})
    pays = []
    for op in db.execute(select(PaymentOperation).where(PaymentOperation.request_id == req.id).order_by(PaymentOperation.created_at)).scalars():
        txs = db.execute(select(ProviderTransaction).where(ProviderTransaction.operation_id == op.id).order_by(ProviderTransaction.created_at)).scalars().all()
        pays.append({"operation_id": str(op.id), "approval_id": str(op.approval_id), "adapter": op.adapter, "environment": "sandbox" if op.adapter == "sandbox" else "simulated (controlled test)",
                     "state": op.state, "amount": fmt(op.amount), "currency": op.currency, "merchant_id": op.merchant_id, "paypal_order_id": op.provider_order_id, "paypal_capture_id": op.provider_capture_id,
                     "capture_status": op.provider_capture_status, "captured_amount": fmt(op.captured_amount), "completed_at": op.completed_at.isoformat() if op.completed_at else None,
                     "paypal_request_ids": {"order": op.order_request_id, "capture": op.capture_request_id},
                     "provider_calls": [{"call": t.call, "outcome": t.outcome, "http_status": t.http_status, "provider_ref": t.provider_ref, "provider_status": t.provider_status, "debug_id": t.debug_id, "at": t.created_at.isoformat()} for t in txs]})
    events = db.execute(select(WorkflowEvent).where(WorkflowEvent.request_id == req.id).order_by(WorkflowEvent.id)).scalars().all()
    view = comparison.comparison(db, actor, req) if req.current_version_id else None
    return {
        "package": "quoteguard.evidence-package.v1",
        "generated_at": timeutil.now().isoformat(),
        "request": {"id": str(req.id), "title": req.title, "original_text": req.original_text, "status": req.status, "timezone": req.timezone,
                    "versions": [{"version": v.version, "requirements": v.requirements, "source": v.source, "note": v.change_note, "confirmed_at": v.confirmed_at.isoformat()} for v in versions]},
        "quotes": quotes,
        "comparison": {"summary": view["summary"], "outcomes": [{"supplier": x["supplier"], **x["outcome"]} for x in view["quotes"]], "policy": view["policy"]} if view else None,
        "approvals": approvals_out,
        "payments": pays,
        "timeline": [{"at": e.created_at.isoformat(), "stage": e.stage, "status": e.status, "title": e.title, "detail": e.detail, "actor": e.actor, "tool": e.tool} for e in events],
        "audit_chain": audit.verify_chain(db, actor.workspace_id),
        "limitations": LIMITATIONS,
        "excluded": ["API keys", "OAuth access tokens", "payer personal data", "raw payment credentials", "document bodies"],
    }


def package_pdf(pkg: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm, title="QuoteGuard evidence package")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], textColor=colors.HexColor("#0f2541"), fontSize=18)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=colors.HexColor("#0f766e"), fontSize=12, spaceBefore=10)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=8.5, leading=11)
    mono = ParagraphStyle("m", parent=body, fontName="Courier", fontSize=7.5, leading=9.5)

    def P(t, st=body):
        return Paragraph(escape(str(t)), st)

    def table(rows, widths=None):
        t = Table([[P(c) for c in r] for r in rows], colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6f2f0")), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    r = pkg["request"]
    s = [P("QuoteGuard — Purchase evidence package", h1), P(f"Generated {pkg['generated_at']} · Request {r['id']}", body), Spacer(1, 6),
         P("Request", h2), P(r["original_text"]), P(f"Status: {r['status']} · Requirement versions: {len(r['versions'])}")]
    if pkg["comparison"]:
        s += [P("Comparison (deterministic policy)", h2),
              table([["Supplier", "Mandatory", "Verified total", "Checkout", "Rank"]] + [[o["supplier"], o["mandatory_status"], o["verified_total"] or "unknown", "yes" if o["checkout_available"] else "no", o["compliant_rank"] or "—"] for o in pkg["comparison"]["outcomes"]])]
    s += [P("Quote documents", h2), table([["File", "SHA-256", "Versions"]] + [[q["document"]["filename"], q["document"]["sha256"], len(q["versions"])] for q in pkg["quotes"]], [55 * mm, 95 * mm, 20 * mm])]
    s += [P("Approvals", h2)]
    for a in pkg["approvals"]:
        s += [P(f"{a['status'].upper()} · approver {a['approver']} · created {a['created_at']} · expires {a['expires_at']}" + (f" · ended: {a['end_reason']}" if a["end_reason"] else "")),
              P(f"Snapshot hash {a['snapshot_hash']}", mono)]
    s += [P("Payments", h2)]
    for p in pkg["payments"]:
        s += [P(f"{p['environment']} · state {p['state']} · {p['currency']} {p['amount']} → merchant {p['merchant_id']}"), P(f"Order {p['paypal_order_id']} · Capture {p['paypal_capture_id']} ({p['capture_status']})", mono),
              table([["Call", "Outcome", "HTTP", "Ref", "Status"]] + [[c["call"], c["outcome"], c["http_status"] or "", c["provider_ref"] or "", c["provider_status"] or ""] for c in p["provider_calls"]])]
    s += [P("Decision replay", h2), table([["Time (UTC)", "Stage", "Event"]] + [[e["at"][:19], e["stage"], f"{e['title']} — {e['detail'] or ''}"] for e in pkg["timeline"]], [32 * mm, 20 * mm, 128 * mm])]
    s += [P("Audit chain", h2), P(json.dumps(pkg["audit_chain"]), mono), P("Limitations", h2)] + [P("• " + x) for x in pkg["limitations"]]
    doc.build(s)
    return buf.getvalue()
