from __future__ import annotations

import asyncio
import json
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ... import audit, jobs, timeutil
from ...config import get_settings, readiness
from ...db import SessionLocal, session_scope
from ...errors import AppError, not_found
from ...models import (
    AICall,
    Approval,
    Document,
    DocumentPage,
    DemoScenarioRun,
    EvaluationCase,
    EvaluationRun,
    PaymentOperation,
    PurchaseRequest,
    PurchaseSnapshot,
    Quote,
    QuoteVersion,
    RequestVersion,
    Supplier,
    WebhookEvent,
    WorkflowEvent,
    WorkflowRun,
)
from ...money import fmt, to_money
from ...services import approvals, comparison, demo, documents, evaluation, export, merchants, payments, webhooks
from ...services import requests as requests_svc
from ...services.context import get_request, parse_uuid
from ...storage import storage
from ..deps import Ctx, client_ip, get_db, rate_limit, require_ctx

router = APIRouter(prefix="/api/v1")


class Strict(BaseModel):
    # Unknown fields (e.g. a client-supplied amount or payee) are rejected outright.
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ health ----------
@router.get("/health", tags=["health"])
def health():
    return {"status": "ok", "time": timeutil.now().isoformat()}


@router.get("/ready", tags=["health"])
def ready():
    ok = True
    try:
        with session_scope() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        ok = False
    body = readiness(ok)
    return JSONResponse(body, status_code=200 if ok else 503)


@router.get("/config/public", tags=["health"])
def public_config():
    s = get_settings()
    # The PayPal client ID is public by design (it is loaded by PayPal's browser SDK). The secret never leaves the backend.
    return {"paypal_client_id": s.PAYPAL_CLIENT_ID if s.paypal_credentials_present else None, "paypal_adapter": s.paypal_adapter_kind, "currency": s.PAYMENT_CURRENCY,
            "paypal_environment": "sandbox", "demo_mode": s.DEMO_MODE, "demo_lab_enabled": s.DEMO_LAB_ENABLED, "timezone": s.DEFAULT_TIMEZONE,
            "sandbox_buyer": {"email": s.SANDBOX_BUYER_EMAIL, "password": s.SANDBOX_BUYER_PASSWORD} if s.SANDBOX_BUYER_EMAIL else None,
            "jury_login": {"username": s.DEMO_ACCOUNT_USERNAME, "password": s.DEMO_ACCOUNT_PASSWORD} if (s.DEMO_MODE and s.SHOW_JURY_LOGIN and s.DEMO_ACCOUNT_USERNAME) else None}


# ---------------------------------------------------------------- overview ----------
@router.get("/overview", tags=["overview"])
def overview(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    ws = ctx.actor.workspace_id
    base = select(PurchaseRequest).where(PurchaseRequest.workspace_id == ws, PurchaseRequest.archived_at.is_(None))
    reqs = db.execute(base.order_by(PurchaseRequest.updated_at.desc())).scalars().all()
    by_status: dict[str, int] = {}
    for r in reqs:
        if r.lab_scenario:
            continue
        by_status[r.status] = by_status.get(r.status, 0) + 1
    pays = db.execute(select(PaymentOperation).where(PaymentOperation.workspace_id == ws)).scalars().all()
    unresolved_docs = db.execute(select(func.count()).select_from(Document).join(PurchaseRequest, PurchaseRequest.id == Document.request_id)
                                 .where(Document.workspace_id == ws, PurchaseRequest.archived_at.is_(None), Document.status.in_(("failed", "needs_ocr")))).scalar()
    review_quotes = db.execute(select(func.count()).select_from(QuoteVersion).join(Quote, Quote.current_version_id == QuoteVersion.id).join(PurchaseRequest, PurchaseRequest.id == Quote.request_id)
                               .where(Quote.workspace_id == ws, PurchaseRequest.archived_at.is_(None), QuoteVersion.needs_review.is_(True))).scalar()
    return {
        "metrics": {
            "outstanding_requests": sum(v for k, v in by_status.items() if k in ("draft", "analyzing", "needs_clarification", "ready_for_review")),
            "awaiting_approval": by_status.get("ready_for_review", 0),
            "needs_clarification": by_status.get("needs_clarification", 0),
            "confirmed_payments": sum(1 for p in pays if p.state == "completed"),
            "confirmed_payment_total": fmt(sum((p.captured_amount or Decimal(0)) for p in pays if p.state == "completed")),
            "payments_reconciling": sum(1 for p in pays if p.state in ("reconciling", "capture_pending")),
            "unresolved_issues": unresolved_docs + review_quotes + by_status.get("needs_clarification", 0),
        },
        "recent": [request_summary(db, r) for r in reqs[:8]],
        "derived_from": "Counts are computed from stored requests, documents, quote versions and payment operations in this workspace.",
    }


def request_summary(db: Session, r: PurchaseRequest) -> dict:
    rv = db.get(RequestVersion, r.current_version_id) if r.current_version_id else None
    n_docs = db.execute(select(func.count()).select_from(Document).where(Document.request_id == r.id)).scalar()
    op = db.execute(select(PaymentOperation).where(PaymentOperation.request_id == r.id).order_by(PaymentOperation.created_at.desc()).limit(1)).scalar_one_or_none()
    return {"id": str(r.id), "title": r.title, "status": r.status, "lab_scenario": r.lab_scenario, "created_at": r.created_at.isoformat(), "updated_at": r.updated_at.isoformat(),
            "version": rv.version if rv else None, "budget": fmt(rv.budget_amount) if rv else None, "currency": rv.currency if rv else None, "quantity": rv.quantity if rv else None,
            "deadline": rv.deadline_date.isoformat() if rv and rv.deadline_date else None, "documents": n_docs, "payment_state": op.state if op else None, "archived": r.archived_at is not None}


# ---------------------------------------------------------------- requests ----------
class CreateRequestIn(Strict):
    text: str = Field(min_length=10, max_length=4000)
    title: str | None = Field(default=None, max_length=200)


@router.get("/requests", tags=["requests"])
def list_requests(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db), page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
                  include_lab: bool = False, include_archived: bool = False):
    q = select(PurchaseRequest).where(PurchaseRequest.workspace_id == ctx.actor.workspace_id)
    if not include_lab:
        q = q.where(PurchaseRequest.lab_scenario.is_(None))
    if not include_archived:
        q = q.where(PurchaseRequest.archived_at.is_(None))
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar()
    rows = db.execute(q.order_by(PurchaseRequest.created_at.desc()).offset((page - 1) * limit).limit(limit)).scalars().all()
    return {"items": [request_summary(db, r) for r in rows], "page": page, "limit": limit, "total": total}


@router.post("/requests", tags=["requests"], status_code=201)
def create_request(body: CreateRequestIn, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    rate_limit(db, f"ai:{ctx.actor.workspace_id}", 60, 3600)
    req = requests_svc.create(db, ctx.actor, body.text, body.title)
    db.flush()
    return request_detail(db, ctx, req)


@router.post("/demo/sample-request", tags=["demo"], status_code=201)
def sample_request(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    rate_limit(db, f"ai:{ctx.actor.workspace_id}", 60, 3600)
    req = demo.start_sample(db, ctx.actor)
    db.flush()
    return request_detail(db, ctx, req)


def request_detail(db: Session, ctx: Ctx, req: PurchaseRequest) -> dict:
    versions = db.execute(select(RequestVersion).where(RequestVersion.request_id == req.id).order_by(RequestVersion.version)).scalars().all()
    docs = db.execute(select(Document).where(Document.request_id == req.id).order_by(Document.created_at)).scalars().all()
    appr = db.execute(select(Approval).where(Approval.request_id == req.id).order_by(Approval.created_at.desc())).scalars().all()
    ops = db.execute(select(PaymentOperation).where(PaymentOperation.request_id == req.id).order_by(PaymentOperation.created_at.desc())).scalars().all()
    run = db.execute(select(WorkflowRun).where(WorkflowRun.request_id == req.id, WorkflowRun.kind == "analyze_request").order_by(WorkflowRun.created_at.desc()).limit(1)).scalar_one_or_none()
    return {
        **request_summary(db, req),
        "original_text": req.original_text, "timezone": req.timezone, "draft": req.draft, "created_by": str(req.created_by), "lock_version": req.lock_version,
        "versions": [{"id": str(v.id), "version": v.version, "requirements": v.requirements, "source": v.source, "note": v.change_note, "confirmed_at": v.confirmed_at.isoformat(),
                      "deadline_at": v.deadline_at.isoformat() if v.deadline_at else None} for v in versions],
        "documents": [document_json(d) for d in docs],
        "approvals": [approvals.approval_json(a, db.get(PurchaseSnapshot, a.snapshot_id)) for a in appr],
        "payments": [payments.op_json(o) for o in ops],
        "workflow": {"status": run.status, "current_node": run.current_node, "completed_nodes": run.completed_nodes} if run else None,
        "is_requester": req.created_by == ctx.actor.user_id,
    }


@router.get("/requests/{request_id}", tags=["requests"])
def get_request_detail(request_id: str, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    return request_detail(db, ctx, get_request(db, ctx.actor, request_id))


class ConfirmIn(Strict):
    requirements: dict
    expected_version: int | None = None
    note: str | None = Field(default=None, max_length=500)


@router.post("/requests/{request_id}/confirm", tags=["requests"])
def confirm_request(request_id: str, body: ConfirmIn, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    requests_svc.confirm(db, ctx.actor, request_id, body.requirements, note=body.note, expected_version=body.expected_version)
    db.flush()
    return request_detail(db, ctx, get_request(db, ctx.actor, request_id))


class ReasonIn(Strict):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/requests/{request_id}/cancel", tags=["requests"])
def cancel_request(request_id: str, body: ReasonIn, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    req = requests_svc.cancel(db, ctx.actor, request_id, body.reason)
    return request_detail(db, ctx, req)


@router.get("/requests/{request_id}/comparison", tags=["quotes"])
def get_comparison(request_id: str, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    return comparison.comparison(db, ctx.actor, get_request(db, ctx.actor, request_id))


@router.get("/requests/{request_id}/integrity", tags=["quotes"])
def get_integrity(request_id: str, memo: bool = True, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    """Document forensics and supplier-independence analysis, with an optional AI investigator memo."""
    rate_limit(db, f"integrity:{ctx.actor.workspace_id}", 240, 3600)
    from ...services import integrity

    return integrity.report(db, get_request(db, ctx.actor, request_id), with_memo=memo)


class WhatIfIn(Strict):
    budget: str | None = None
    deadline_days: int | None = Field(default=None, ge=0, le=365)
    quantity: int | None = Field(default=None, ge=1, le=100000)
    note: str | None = Field(default=None, max_length=300)


@router.post("/requests/{request_id}/whatif", tags=["what-if"])
def whatif_preview(request_id: str, body: WhatIfIn, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    req = get_request(db, ctx.actor, request_id)
    return comparison.whatif_preview(db, ctx.actor, req, budget=to_money(body.budget) if body.budget else None, deadline_days=body.deadline_days, quantity=body.quantity)


@router.post("/requests/{request_id}/whatif/apply", tags=["what-if"])
def whatif_apply(request_id: str, body: WhatIfIn, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    """Applying a preview creates a new request version; preview values never reach payment directly."""
    req = get_request(db, ctx.actor, request_id)
    rv = db.get(RequestVersion, req.current_version_id) if req.current_version_id else None
    if rv is None:
        raise AppError("REQUEST_NOT_CONFIRMED", "Confirm the requirements first.", 409)
    spec = dict(rv.requirements)
    changes = []
    if body.budget:
        spec["budget_amount"] = fmt(to_money(body.budget))
        changes.append(f"budget {rv.currency} {fmt(rv.budget_amount)} → {spec['budget_amount']}")
    if body.deadline_days is not None:
        spec["deadline_days"], spec["deadline_date"] = body.deadline_days, None
        changes.append(f"delivery window → {body.deadline_days} days")
    if body.quantity:
        spec["quantity"] = body.quantity
        changes.append(f"quantity → {body.quantity}")
    if not changes:
        raise AppError("NO_CHANGES", "Nothing to apply.", 422)
    requests_svc.confirm(db, ctx.actor, req.id, spec, source="whatif", note=(body.note or "Applied what-if: " + ", ".join(changes)), expected_version=rv.version)
    db.flush()
    return request_detail(db, ctx, get_request(db, ctx.actor, request_id))


class ChatIn(Strict):
    question: str = Field(min_length=2, max_length=600)


@router.post("/requests/{request_id}/chat", tags=["quotes"])
def chat(request_id: str, body: ChatIn, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    rate_limit(db, f"chat:{ctx.actor.user_id}", 30, 600)
    return comparison.chat(db, ctx.actor, get_request(db, ctx.actor, request_id), body.question)


@router.post("/requests/{request_id}/analyze", tags=["workflow"])
def reanalyze(request_id: str, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    req = get_request(db, ctx.actor, request_id)
    # Transient parser failures are retried; deterministic ones (encrypted, image-only without OCR) are not.
    retried = 0
    for d in db.execute(select(Document).where(Document.request_id == req.id, Document.error_code.in_(("PARSE_TIMEOUT", "PARSER_CRASHED", "PARSER_OUTPUT_INVALID")))).scalars():
        d.status, d.error_code, d.error_message, d.extraction_started_at = "uploaded", None, None, None
        retried += 1
    jobs.enqueue(db, "analyze_request", {"request_id": req.id}, dedupe_key=f"analyze:{req.id}")
    audit.event(db, workspace_id=req.workspace_id, request_id=req.id, stage="workflow", status="info", title="Analysis re-queued", detail=f"{retried} transiently failed document(s) retried; extracted documents are reused.", actor=ctx.actor.label)
    return {"queued": True, "retried_documents": retried}


def _events(db: Session, ws, request_id, after: int) -> list[dict]:
    rows = db.execute(select(WorkflowEvent).where(WorkflowEvent.workspace_id == ws, WorkflowEvent.request_id == request_id, WorkflowEvent.id > after).order_by(WorkflowEvent.id).limit(300)).scalars().all()
    return [{"id": e.id, "stage": e.stage, "status": e.status, "title": e.title, "detail": e.detail, "refs": e.refs, "actor": e.actor, "tool": e.tool, "at": e.created_at.isoformat()} for e in rows]


@router.get("/requests/{request_id}/events", tags=["workflow"])
def events(request_id: str, after: int = 0, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    req = get_request(db, ctx.actor, request_id)
    return {"items": _events(db, ctx.actor.workspace_id, req.id, after), "status": req.status}


@router.get("/requests/{request_id}/events/stream", tags=["workflow"])
async def events_stream(request: Request, request_id: str, after: int = 0, ctx: Ctx = Depends(require_ctx)):
    """Authenticated SSE of persisted events. Reconnects resume from Last-Event-ID."""
    with session_scope() as db:
        req = get_request(db, ctx.actor, request_id)
        rid, ws = req.id, ctx.actor.workspace_id
    last = int(request.headers.get("last-event-id") or after or 0)

    async def gen():
        nonlocal last
        idle = 0
        while idle < 600 and not await request.is_disconnected():
            def poll():
                with session_scope() as db:
                    st = db.get(PurchaseRequest, rid).status
                    return _events(db, ws, rid, last), st
            items, status = await run_in_threadpool(poll)
            for it in items:
                last = it["id"]
                yield f"id: {it['id']}\nevent: workflow\ndata: {json.dumps(it)}\n\n"
            yield f"event: status\ndata: {json.dumps({'status': status})}\n\n"
            idle = 0 if items else idle + 1
            await asyncio.sleep(1.2)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --------------------------------------------------------------- documents ----------
def document_json(d: Document) -> dict:
    return {"id": str(d.id), "filename": d.filename, "sha256": d.sha256, "text_sha256": d.text_sha256, "size_bytes": d.size_bytes, "pages": d.page_count, "status": d.status,
            "error_code": d.error_code, "error_message": d.error_message, "is_sample": d.is_sample, "suspicious": d.suspicious, "created_at": d.created_at.isoformat(), "request_id": str(d.request_id)}


@router.post("/requests/{request_id}/documents", tags=["documents"], status_code=201)
async def upload(request_id: str, file: UploadFile = File(...), ctx: Ctx = Depends(require_ctx)):
    limit = get_settings().MAX_UPLOAD_MB * 1024 * 1024
    data = await file.read(limit + 1)

    def work():
        with session_scope() as db:
            rate_limit(db, f"upload:{ctx.actor.user_id}", 40, 3600)
            return document_json(documents.upload(db, ctx.actor, request_id, file.filename or "quote.pdf", data, file.content_type))

    return await run_in_threadpool(work)


@router.post("/requests/{request_id}/sample-quotes", tags=["demo"])
def load_samples(request_id: str, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    return {"documents": [document_json(d) for d in demo.load_sample_quotes(db, ctx.actor, request_id)]}


@router.get("/demo/fixtures", tags=["demo"])
def list_fixtures(ctx: Ctx = Depends(require_ctx)):
    return {"fixtures": [{"key": k, "label": v} for k, v in demo.FIXTURE_LABELS.items()]}


@router.post("/requests/{request_id}/fixtures/{key}", tags=["demo"])
def load_fixture(request_id: str, key: str, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    return document_json(demo.load_fixture(db, ctx.actor, request_id, key))


def _doc(db: Session, ctx: Ctx, document_id: str) -> Document:
    d = db.execute(select(Document).where(Document.id == parse_uuid(document_id, "Document"), Document.workspace_id == ctx.actor.workspace_id)).scalar_one_or_none()
    if d is None:
        raise not_found("Document")
    return d


@router.get("/documents/{document_id}", tags=["documents"])
def get_document(document_id: str, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    d = _doc(db, ctx, document_id)
    pages = db.execute(select(DocumentPage).where(DocumentPage.document_id == d.id).order_by(DocumentPage.page_number)).scalars().all()
    return {**document_json(d), "page_meta": [{"page": p.page_number, "width": float(p.width), "height": float(p.height), "method": p.extraction_method, "quality": p.quality, "text": p.text} for p in pages]}


@router.get("/documents/{document_id}/pages/{page}.png", tags=["documents"])
async def page_png(document_id: str, page: int, ctx: Ctx = Depends(require_ctx)):
    def render():
        with session_scope() as db:
            d = _doc(db, ctx, document_id)
            key, count = d.storage_key, d.page_count or 1
        if not 1 <= page <= count:
            raise not_found("Page")
        cache = storage().root / "_renders" / f"{document_id}_{page}.png"
        if cache.exists():
            return cache.read_bytes()
        import io

        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(storage().get(key))
        img = pdf[page - 1].render(scale=2).to_pil()
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(buf.getvalue())
        return buf.getvalue()

    png = await run_in_threadpool(render)
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/documents/{document_id}/file", tags=["documents"])
def download_document(document_id: str, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    d = _doc(db, ctx, document_id)
    return Response(storage().get(d.storage_key), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{d.filename}"', "X-Content-Type-Options": "nosniff"})


@router.get("/evidence", tags=["documents"])
def evidence_desk(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db), request_id: str | None = None):
    q = select(Document, PurchaseRequest).join(PurchaseRequest, PurchaseRequest.id == Document.request_id).where(Document.workspace_id == ctx.actor.workspace_id, PurchaseRequest.archived_at.is_(None))
    if request_id:
        q = q.where(Document.request_id == parse_uuid(request_id))
    out = []
    for d, r in db.execute(q.order_by(Document.created_at.desc()).limit(200)).all():
        quote = db.execute(select(Quote).where(Quote.document_id == d.id)).scalar_one_or_none()
        qv = db.get(QuoteVersion, quote.current_version_id) if quote else None
        out.append({**document_json(d), "request_title": r.title, "lab": r.lab_scenario is not None, "quote_id": str(quote.id) if quote else None,
                    "quote": comparison.quote_version_json(qv) if qv else None, "supplier_link": quote.supplier_link if quote else None})
    return {"items": out}


# ------------------------------------------------------------------ quotes ----------
@router.get("/quotes/{quote_id}/versions", tags=["quotes"])
def quote_versions(quote_id: str, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    q = db.execute(select(Quote).where(Quote.id == parse_uuid(quote_id, "Quote"), Quote.workspace_id == ctx.actor.workspace_id)).scalar_one_or_none()
    if q is None:
        raise not_found("Quote")
    vs = db.execute(select(QuoteVersion).where(QuoteVersion.quote_id == q.id).order_by(QuoteVersion.version)).scalars().all()
    ev = comparison.evidence_index(db, [v.id for v in vs])
    return {"quote_id": str(q.id), "current_version_id": str(q.current_version_id),
            "versions": [{**comparison.quote_version_json(v), "evidence": [comparison.evidence_json(e) for e in ev.values() if e.quote_version_id == v.id]} for v in vs]}


class CorrectIn(Strict):
    field: str = Field(max_length=60)
    value: str | None = Field(default=None, max_length=200)
    note: str = Field(min_length=4, max_length=500)
    expected_version: int | None = None


@router.post("/quotes/{quote_id}/correct", tags=["quotes"])
def correct(quote_id: str, body: CorrectIn, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    qv = documents.correct(db, ctx.actor, quote_id, body.field, body.value, body.note, expected_version=body.expected_version)
    return comparison.quote_version_json(qv)


class SupplierLinkIn(Strict):
    supplier_id: str
    note: str = Field(min_length=4, max_length=300)


@router.post("/quotes/{quote_id}/confirm-supplier", tags=["quotes"])
def confirm_supplier(quote_id: str, body: SupplierLinkIn, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    q = documents.confirm_supplier_link(db, ctx.actor, quote_id, body.supplier_id, body.note)
    return {"quote_id": str(q.id), "supplier_link": q.supplier_link}


@router.get("/suppliers", tags=["quotes"])
def suppliers(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    rows = db.execute(select(Supplier).where(Supplier.workspace_id == ctx.actor.workspace_id).order_by(Supplier.name)).scalars().all()
    return {"items": [{"id": str(s.id), "name": s.name, "merchant": bool(comparison.active_binding(db, s.id))} for s in rows]}


# --------------------------------------------------------------- approvals ----------
@router.get("/requests/{request_id}/approval-review", tags=["approvals"])
def approval_review(request_id: str, quote_id: str, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    return approvals.review(db, ctx.actor, request_id, quote_id)


class ApproveIn(Strict):
    quote_id: str
    terms_hash: str = Field(min_length=64, max_length=64)
    note: str | None = Field(default=None, max_length=500)


@router.post("/requests/{request_id}/approvals", tags=["approvals"], status_code=201)
def approve(request_id: str, body: ApproveIn, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    a = approvals.approve(db, ctx.actor, request_id, body.quote_id, body.terms_hash, body.note)
    return approvals.approval_json(a, db.get(PurchaseSnapshot, a.snapshot_id))


class RejectIn(Strict):
    quote_id: str
    note: str = Field(min_length=4, max_length=500)


@router.post("/requests/{request_id}/reject", tags=["approvals"])
def reject(request_id: str, body: RejectIn, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    approvals.reject(db, ctx.actor, request_id, body.quote_id, body.note)
    return {"ok": True}


@router.post("/approvals/{approval_id}/revoke", tags=["approvals"])
def revoke(approval_id: str, body: ReasonIn, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    a = approvals.revoke(db, ctx.actor, approval_id, body.reason)
    return approvals.approval_json(a)


@router.get("/approvals/{approval_id}", tags=["approvals"])
def get_approval(approval_id: str, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    a = db.execute(select(Approval).where(Approval.id == parse_uuid(approval_id, "Approval"), Approval.workspace_id == ctx.actor.workspace_id)).scalar_one_or_none()
    if a is None:
        raise not_found("Approval")
    if a.status == "active" and a.expires_at <= timeutil.now():
        a.status, a.ended_at, a.end_reason = "expired", timeutil.now(), "Approval expired"
    return approvals.approval_json(a, db.get(PurchaseSnapshot, a.snapshot_id))


# ---------------------------------------------------------------- payments ----------
class Empty(Strict):
    pass


def _pay_rate(ctx: Ctx):
    with session_scope() as db:
        rate_limit(db, f"pay:{ctx.actor.user_id}", 60, 600)


@router.post("/approvals/{approval_id}/checkout", tags=["payments"])
async def checkout(approval_id: str, body: Empty | None = None, ctx: Ctx = Depends(require_ctx)):
    """Creates (or returns) the one payment operation for this approval. No client amounts or payees are accepted."""
    _pay_rate(ctx)
    return await run_in_threadpool(payments.start_checkout, session_scope, ctx.actor, approval_id)


@router.get("/payments", tags=["payments"])
def list_payments(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    rows = db.execute(select(PaymentOperation, PurchaseRequest).join(PurchaseRequest, PurchaseRequest.id == PaymentOperation.request_id)
                      .where(PaymentOperation.workspace_id == ctx.actor.workspace_id).order_by(PaymentOperation.created_at.desc()).limit(100)).all()
    return {"items": [{**payments.op_json(o), "request_title": r.title, "lab": r.lab_scenario is not None} for o, r in rows]}


def _op(db: Session, ctx: Ctx, op_id: str) -> PaymentOperation:
    op = db.execute(select(PaymentOperation).where(PaymentOperation.id == parse_uuid(op_id, "Payment"), PaymentOperation.workspace_id == ctx.actor.workspace_id)).scalar_one_or_none()
    if op is None:
        raise not_found("Payment")
    return op


@router.get("/payments/{op_id}", tags=["payments"])
def get_payment(op_id: str, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    op = _op(db, ctx, op_id)
    snap = db.get(PurchaseSnapshot, op.snapshot_id)
    req = db.get(PurchaseRequest, op.request_id)
    appr = db.get(Approval, op.approval_id)
    return {**payments.op_json(op, db), "snapshot": snap.canonical, "snapshot_hash": snap.hash, "request_title": req.title, "approval": approvals.approval_json(appr)}


@router.post("/payments/{op_id}/capture", tags=["payments"])
async def capture(op_id: str, body: Empty | None = None, ctx: Ctx = Depends(require_ctx)):
    _pay_rate(ctx)
    return await run_in_threadpool(payments.capture, session_scope, ctx.actor, op_id)


@router.post("/payments/{op_id}/reconcile", tags=["payments"])
async def reconcile(op_id: str, ctx: Ctx = Depends(require_ctx)):
    _pay_rate(ctx)
    with session_scope() as db:
        _op(db, ctx, op_id)
    return await run_in_threadpool(payments.reconcile, session_scope, op_id, "user")


@router.post("/payments/{op_id}/buyer-canceled", tags=["payments"])
def buyer_canceled(op_id: str, ctx: Ctx = Depends(require_ctx)):
    return payments.buyer_canceled(session_scope, ctx.actor, op_id)


@router.post("/payments/{op_id}/simulated-approve", tags=["payments"])
def simulated_approve(op_id: str, ctx: Ctx = Depends(require_ctx)):
    return payments.simulated_buyer_approve(session_scope, ctx.actor, op_id)


@router.post("/payments/{op_id}/arm-lost-response", tags=["demo"])
def arm_fault(op_id: str, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    """Demo Lab: discard the provider's response to this operation's next capture (the capture itself still happens)."""
    ctx.actor.require("admin")
    if not ctx.actor.is_demo_workspace or not get_settings().DEMO_LAB_ENABLED:
        raise AppError("DEMO_LAB_DISABLED", "Fault injection is only available in demo workspaces.", 403)
    op = db.execute(select(PaymentOperation).where(PaymentOperation.id == _op(db, ctx, op_id).id).with_for_update().execution_options(populate_existing=True)).scalar_one()
    if op.state != "awaiting_payer":
        raise AppError("INVALID_STATE", "Arm the test before capture.", 409)
    op.fault_injection = "drop_capture_response"
    audit.event(db, workspace_id=op.workspace_id, request_id=op.request_id, stage="payment", status="info", title="Controlled test armed: next capture response will be discarded",
                detail="The capture is still sent to PayPal; QuoteGuard pretends the answer was lost and must reconcile.", actor=ctx.actor.label, tool="demo_lab")
    return payments.op_json(op)


class RefundIn(Strict):
    amount: str
    note: str = Field(min_length=4, max_length=300)


@router.post("/payments/{op_id}/refund", tags=["payments"])
async def refund(op_id: str, body: RefundIn, ctx: Ctx = Depends(require_ctx)):
    _pay_rate(ctx)
    return await run_in_threadpool(payments.refund, session_scope, ctx.actor, op_id, body.amount, body.note)


# ---------------------------------------------------------------- webhooks ----------
@router.post("/webhooks/paypal", tags=["webhooks"], include_in_schema=True)
async def paypal_webhook(request: Request):
    raw = await request.body()

    def store():
        with session_scope() as db:
            rate_limit(db, f"webhook:{client_ip(request)}", 300, 60)
            return webhooks.receive(db, dict(request.headers), raw)

    status, msg = await run_in_threadpool(store)
    return JSONResponse({"status": msg}, status_code=status)


@router.get("/webhooks/events", tags=["webhooks"])
def webhook_events(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    ops = select(PaymentOperation.id).where(PaymentOperation.workspace_id == ctx.actor.workspace_id)
    rows = db.execute(select(WebhookEvent).where(WebhookEvent.operation_id.in_(ops)).order_by(WebhookEvent.received_at.desc()).limit(50)).scalars().all()
    return {"items": [{"id": str(w.id), "event_type": w.event_type, "resource_id": w.resource_id, "verification": w.verification, "processing": w.processing, "outcome": w.outcome,
                       "received_at": w.received_at.isoformat(), "operation_id": str(w.operation_id) if w.operation_id else None} for w in rows]}


# ---------------------------------------------------------------- evidence ----------
@router.get("/requests/{request_id}/export.json", tags=["evidence"])
def export_json(request_id: str, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    pkg = export.package(db, ctx.actor, request_id)
    return Response(json.dumps(pkg, indent=2, default=str), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="quoteguard-evidence-{request_id[:8]}.json"'})


@router.get("/requests/{request_id}/export.pdf", tags=["evidence"])
def export_pdf(request_id: str, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    pdf = export.package_pdf(export.package(db, ctx.actor, request_id))
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="quoteguard-evidence-{request_id[:8]}.pdf"'})


@router.get("/audit/verify", tags=["evidence"])
def audit_verify(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    return {**audit.verify_chain(db, ctx.actor.workspace_id), "limits": export.LIMITATIONS[2]}


# -------------------------------------------------------------------- demo ----------
@router.get("/demo/scenarios", tags=["demo"])
def scenarios(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    runs = db.execute(select(DemoScenarioRun).where(DemoScenarioRun.workspace_id == ctx.actor.workspace_id).order_by(DemoScenarioRun.started_at.desc()).limit(30)).scalars().all()
    return {"scenarios": [{"key": k, "title": v} for k, v in demo.SCENARIOS.items()], "runs": [demo.scenario_json(r) for r in runs],
            "available": ctx.actor.is_demo_workspace and get_settings().DEMO_LAB_ENABLED and "admin" in ctx.actor.roles}


@router.post("/demo/scenarios/{scenario}", tags=["demo"], status_code=202)
def run_scenario(scenario: str, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    rate_limit(db, f"scenario:{ctx.actor.workspace_id}", 20, 3600)
    return demo.scenario_json(demo.start_scenario(db, ctx.actor, scenario))


@router.get("/demo/runs/{run_id}", tags=["demo"])
def scenario_run(run_id: str, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    r = db.execute(select(DemoScenarioRun).where(DemoScenarioRun.id == parse_uuid(run_id), DemoScenarioRun.workspace_id == ctx.actor.workspace_id)).scalar_one_or_none()
    if r is None:
        raise not_found("Scenario run")
    return demo.scenario_json(r)


@router.post("/demo/archive", tags=["demo"])
def demo_archive(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    return demo.archive(db, ctx.actor)


# -------------------------------------------------------------- evaluation ----------
class EvalIn(Strict):
    mode: str = Field(default="llm", pattern="^(llm|rules)$")
    dataset: str = Field(default="quoteguard-holdout-v1", pattern="^quoteguard-(eval|holdout)-v1$")


@router.get("/evaluation/runs", tags=["evaluation"])
def eval_runs(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    rows = db.execute(select(EvaluationRun).where(EvaluationRun.extraction_mode != "forensics").order_by(EvaluationRun.started_at.desc()).limit(20)).scalars().all()
    return {"items": [evaluation.run_json(r) for r in rows]}


@router.get("/evaluation/research", tags=["evaluation"])
def eval_research(ctx: Ctx = Depends(require_ctx)):
    """The bid-rigging transfer study behind the cartel-pattern model (static results; see research/bid_rigging/)."""
    import json
    from pathlib import Path

    from ...research import cartel

    study = json.loads((Path(cartel.__file__).with_name("cartel_study_v1.json")).read_text())
    return {k: study[k] for k in ("name", "version", "date", "data", "protocol", "rows")} | {"model": cartel.model()["name"]}


@router.get("/evaluation/integrity", tags=["evaluation"])
def eval_integrity(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    """Latest stored run of the document-integrity benchmark (deterministic; see integrity_bench.py)."""
    r = db.execute(select(EvaluationRun).where(EvaluationRun.extraction_mode == "forensics").order_by(EvaluationRun.started_at.desc()).limit(1)).scalar_one_or_none()
    if r is None:
        return {"run": None}
    return {"run": {"id": str(r.id), "finished_at": r.finished_at, "code_revision": r.code_revision, "analyzer": r.model, "dataset": r.dataset_version, **(r.summary or {})}}


@router.get("/evaluation/runs/{run_id}", tags=["evaluation"])
def eval_run(run_id: str, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    r = db.get(EvaluationRun, parse_uuid(run_id, "Evaluation run"))
    if r is None:
        raise not_found("Evaluation run")
    cases = db.execute(select(EvaluationCase).where(EvaluationCase.run_id == r.id).order_by(EvaluationCase.case_id)).scalars().all()
    return evaluation.run_json(r, cases)


@router.post("/evaluation/runs", tags=["evaluation"], status_code=202)
def start_eval(body: EvalIn, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    ctx.actor.require("admin")
    rate_limit(db, f"eval:{ctx.principal.id}", 3, 3600)
    running = db.execute(select(func.count()).select_from(EvaluationRun).where(EvaluationRun.status == "running")).scalar()
    if running:
        raise AppError("EVALUATION_RUNNING", "An evaluation run is already in progress.", 409)
    run_id = evaluation.create_run(ctx.principal.id, body.mode, body.dataset)
    jobs.enqueue(db, "run_evaluation", {"run_id": run_id}, max_attempts=1)
    return {"id": str(run_id), "status": "running"}


# ---------------------------------------------------------------- settings ----------
@router.get("/settings", tags=["settings"])
def settings_view(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    ok = True
    usage = db.execute(select(AICall.purpose, func.count(), func.avg(AICall.latency_ms)).where(AICall.workspace_id == ctx.actor.workspace_id).group_by(AICall.purpose)).all()
    return {"readiness": readiness(ok), "merchant_bindings": merchants.list_bindings(db, ctx.actor), "workspace_policy": {"self_approval_allowed": False, "approval_ttl_minutes": get_settings().APPROVAL_TTL_MINUTES},
            "ai_usage": [{"purpose": p, "calls": c, "avg_latency_ms": int(a or 0)} for p, c, a in usage], "roles": sorted(ctx.actor.roles),
            "secrets_note": "Secrets are read from the server environment and are never displayed."}


class MerchantIn(Strict):
    merchant_id: str = Field(min_length=3, max_length=64)
    note: str = Field(min_length=4, max_length=300)


@router.post("/merchant-bindings/{binding_id}", tags=["settings"])
def change_merchant(binding_id: str, body: MerchantIn, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    b = merchants.change_merchant(db, ctx.actor, binding_id, body.merchant_id, body.note)
    return merchants.binding_json(b, db.get(Supplier, b.supplier_id))


__all__ = ["router", "SessionLocal", "uuid"]
