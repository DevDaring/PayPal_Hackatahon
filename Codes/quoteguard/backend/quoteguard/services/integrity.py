"""Integrity assessment for a request's quotes: forensics per document plus independence across suppliers."""

from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import timeutil
from ..ai import provider
from ..db import session_scope
from ..documents import ingest
from ..documents.integrity import INTEGRITY_VERSION, DocInput, analyze
from ..models import Document, DocumentPage, ExtractionCache, Membership, PurchaseRequest, User
from ..storage import storage

log = logging.getLogger(__name__)


def _member_names(db: Session, workspace_id) -> list[str]:
    users = db.execute(select(User).join(Membership, Membership.user_id == User.id).where(Membership.workspace_id == workspace_id)).scalars().all()
    names = []
    for u in users:
        names += [n for n in (u.display_name.split("·")[0].strip() if u.display_name else None, u.username, u.email.split("@")[0] if u.email else None) if n]
    return names


def _history(db: Session, req: PurchaseRequest, limit: int = 200) -> list[dict[str, float]]:
    """Past tenders in this workspace: {supplier_key: stated total} per request with at least three priced quotes."""
    from ..documents.integrity import supplier_key
    from ..models import Quote, QuoteVersion, Supplier

    rows = db.execute(select(Quote.request_id, Supplier.name, QuoteVersion.supplier_name, QuoteVersion.stated_total)
                      .join(QuoteVersion, QuoteVersion.id == Quote.current_version_id)
                      .join(PurchaseRequest, PurchaseRequest.id == Quote.request_id)
                      .outerjoin(Supplier, Supplier.id == Quote.supplier_id)
                      .where(Quote.workspace_id == req.workspace_id, Quote.request_id != req.id, PurchaseRequest.status != "canceled")
                      .order_by(PurchaseRequest.created_at.desc()).limit(limit * 6)).all()
    by_req: dict = {}
    for rid, linked, extracted, total in rows:
        name = linked or extracted  # the linked supplier record is authoritative; the extracted name is a fallback
        if name and total:
            by_req.setdefault(rid, {})[supplier_key(name)] = float(total)
    return [t for t in by_req.values() if len(t) >= 3][:limit]


def ensure_forensics(db: Session, doc: Document) -> dict | None:
    """Documents processed before forensics existed are assessed from the stored file, once."""
    if doc.forensics is None and doc.status == "extracted":
        parsed = ingest.parse_isolated(storage().get(doc.storage_key))
        doc.forensics = parsed.get("forensics") or {"error": parsed.get("error", "UNAVAILABLE")}
    return doc.forensics


def assess(db: Session, req: PurchaseRequest, rows) -> dict:
    """rows: comparison.facts() output — (Quote, QuoteVersion, QuoteFacts, reason)."""
    docs = []
    if not rows:
        return analyze([], [])
    for q, qv, f, _ in rows:
        doc = db.get(Document, q.document_id)
        pages = db.execute(select(DocumentPage).where(DocumentPage.document_id == doc.id).order_by(DocumentPage.page_number)).scalars().all()
        docs.append(DocInput(key=str(q.id), supplier=f.supplier, text="\n".join(p.text for p in pages), forensics=ensure_forensics(db, doc), total=qv.stated_total, filename=doc.filename))
    return analyze(docs, _member_names(db, req.workspace_id), _history(db, req))


_MEMO_SYSTEM = """You are a procurement fraud investigator writing for a busy approver.
You receive deterministic forensic findings about supplier quotes. They are facts; do not add new facts, numbers, names or accusations.
Explain in plain English what the findings mean, how confident a reader should be, and what to do next. Never state that fraud is proven.
Refer to findings by what they show, never by their ids (no "F1"), and name suppliers as given.
Return JSON: {"headline": str (max 14 words), "explanation": str (max 90 words), "next_steps": [str, str, str], "question_for_supplier": str}."""


def _numbers(s: str) -> set[str]:
    import re

    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", s)}


def memo(db: Session, req: PurchaseRequest, result: dict) -> dict | None:
    """AI investigator memo over the findings. Numbers it states must appear in the findings, or it is discarded."""
    material = [f for f in result["findings"] if f["severity"] != "low"]
    if not material:
        return None
    payload = json.dumps({"findings": [{k: f[k] for k in ("id", "severity", "title", "detail")} for f in result["findings"]],
                          "suppliers": {k: v["supplier"] for k, v in result["documents"].items()}, "bid_screens": result.get("screens")}, sort_keys=True, default=str)
    key = hashlib.sha256(("integrity-memo:" + INTEGRITY_VERSION + _MEMO_SYSTEM + payload).encode()).hexdigest()  # prompt-versioned; fits cache_key(64)
    hit = db.execute(select(ExtractionCache).where(ExtractionCache.workspace_id == req.workspace_id, ExtractionCache.cache_key == key)).scalar_one_or_none()
    if hit:
        return hit.result
    ws_id, req_id = req.workspace_id, req.id
    db.commit()  # never hold row locks across a model call (the call log references this request)
    try:
        out, meta = provider.chat_json(_MEMO_SYSTEM, payload, purpose="integrity_memo", workspace_id=ws_id, request_id=req_id, max_tokens=700, temperature=0.1)
    except provider.AIUnavailable:
        return None
    text = " ".join([str(out.get("headline", "")), str(out.get("explanation", "")), *map(str, out.get("next_steps") or []), str(out.get("question_for_supplier", ""))])
    allowed = _numbers(payload)
    if not out.get("headline") or not (_numbers(text) <= allowed):
        log.info("integrity memo discarded: unsupported numbers")
        return None
    res = {"headline": str(out["headline"])[:140], "explanation": str(out.get("explanation", ""))[:900], "next_steps": [str(x)[:240] for x in (out.get("next_steps") or [])][:3],
           "question_for_supplier": str(out.get("question_for_supplier", ""))[:400], "model": meta.get("model"), "provider": meta.get("provider")}
    try:
        with session_scope() as s2:
            s2.add(ExtractionCache(workspace_id=ws_id, cache_key=key, result=res, created_at=timeutil.now()))
    except IntegrityError:
        pass  # a concurrent request stored the same memo
    return res


def report(db: Session, req: PurchaseRequest, *, with_memo: bool = True) -> dict:
    from .comparison import facts

    rows = facts(db, req)
    result = assess(db, req, rows)
    result["memo"] = memo(db, req, result) if with_memo else None
    return result
