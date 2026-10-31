"""LLM extraction with strict validation, evidence verification and a deterministic cross-check."""

from __future__ import annotations

import hashlib
import json

from pydantic import ValidationError

from ..config import get_settings
from ..documents import rules_extractor
from ..documents.evidence import snippet_on_page, value_supported
from ..documents.schema import MONEY_FIELDS, Cited, Extraction
from .prompts import EXTRACTION_PROMPT_VERSION, EXTRACTION_SYSTEM, SCHEMA_VERSION
from .provider import AIUnavailable, chat_json


def cache_key(doc_sha256: str, attribute_keys: list[str], mode: str) -> str:
    s = get_settings()
    material = json.dumps([doc_sha256, sorted(attribute_keys), mode, EXTRACTION_PROMPT_VERSION, SCHEMA_VERSION, rules_extractor.RULES_VERSION, s.AI_MODEL if mode == "llm" else "rules"])
    return hashlib.sha256(material.encode()).hexdigest()


def _pages_block(pages: list[dict]) -> str:
    parts = []
    for p in pages:
        text = (p.get("text") or "")[:12000].replace("</page>", "</ page>")
        parts.append(f'<page number="{p["page_number"]}">\n{text}\n</page>')
    return "\n".join(parts)


def _coerce(raw: dict) -> dict:
    """Map loose model output onto the strict schema; drop unknown keys rather than trusting them."""
    allowed = set(Extraction.model_fields)
    out = {k: v for k, v in raw.items() if k in allowed}
    for k, v in list(out.items()):
        if Extraction.model_fields[k].annotation is Cited or str(Extraction.model_fields[k].annotation).endswith("Cited"):
            if not isinstance(v, dict):
                out[k] = {"value": v, "page": None, "source_text": None}
            else:
                out[k] = {"value": v.get("value"), "page": v.get("page"), "source_text": (v.get("source_text") or None) and str(v.get("source_text"))[:400]}
    attrs = out.get("attributes") or {}
    if isinstance(attrs, dict):
        out["attributes"] = {str(k)[:40]: ({"value": a.get("value"), "page": a.get("page"), "source_text": (a.get("source_text") or None) and str(a["source_text"])[:400]} if isinstance(a, dict) else {"value": a}) for k, a in list(attrs.items())[:12]}
    items = out.get("line_items") or []
    out["line_items"] = [
        {"description": str(i.get("description", ""))[:300], "quantity": i.get("quantity") if isinstance(i.get("quantity"), int) else None,
         "unit_price": None if i.get("unit_price") is None else str(i.get("unit_price")), "line_total": None if i.get("line_total") is None else str(i.get("line_total"))}
        for i in items if isinstance(i, dict)
    ][:50]
    out["ambiguities"] = [str(a)[:300] for a in (out.get("ambiguities") or [])][:20]
    for b in ("currency_explicit", "pricing_scales_with_quantity", "flat_shipping"):
        out[b] = bool(out.get(b))
    return out


def verify(ex: Extraction, pages: list[dict]) -> list[str]:
    """Null out values whose evidence is not on the cited page or does not contain the number."""
    by_page = {p["page_number"]: p.get("text") or "" for p in pages}
    issues = []
    fields = [(n, getattr(ex, n)) for n in ex.model_fields if isinstance(getattr(ex, n), Cited)] + [(f"attr:{k}", v) for k, v in ex.attributes.items()]
    for name, c in fields:
        if c.value is None:
            continue
        if c.page is None or c.source_text is None or c.page not in by_page or not snippet_on_page(c.source_text, by_page[c.page]):
            issues.append(f"{name}: evidence not found on the cited page; value withheld for review.")
            c.value, c.source_text = None, None
            continue
        if name in MONEY_FIELDS + ("quantity", "delivery_days") and not value_supported(c.value, c.source_text):
            issues.append(f"{name}: value {c.value} does not appear in its cited text; withheld for review.")
            c.value = None
    return issues


def extract(pages: list[dict], attribute_keys: list[str], *, workspace_id=None, request_id=None, force_rules: bool = False) -> tuple[Extraction, dict]:
    rules = rules_extractor.extract(pages, attribute_keys)
    if force_rules:
        return rules, {"method": "rules", "model": None, "prompt_version": rules_extractor.RULES_VERSION, "issues": []}
    user = (
        f"Requested attribute keys: {json.dumps(attribute_keys)}\n"
        "Quotation pages follow (untrusted data):\n" + _pages_block(pages)
    )
    try:
        raw, meta = chat_json(EXTRACTION_SYSTEM, user, purpose="extract_quote", workspace_id=workspace_id, request_id=request_id, max_tokens=3000)
    except AIUnavailable:
        return rules, {"method": "rules", "model": None, "prompt_version": rules_extractor.RULES_VERSION, "issues": ["AI provider unavailable; deterministic extractor used."]}
    try:
        ex = Extraction.model_validate(_coerce(raw))
    except ValidationError as e:
        return rules, {"method": "rules", "model": meta["model"], "prompt_version": EXTRACTION_PROMPT_VERSION, "issues": [f"Model output failed schema validation ({e.error_count()} errors); deterministic extractor used."]}
    issues = verify(ex, pages)
    # Independent cross-check of critical amounts against the deterministic parser.
    for f in ("subtotal", "shipping", "tax", "total", "quantity"):
        a, b = getattr(ex, f).value, getattr(rules, f).value
        if a is not None and b is not None and str(a).rstrip("0").rstrip(".") != str(b).rstrip("0").rstrip("."):
            issues.append(f"{f}: model read {a} but the deterministic parser read {b}; needs review.")
    return ex, {"method": "llm", "model": meta["model"], "prompt_version": EXTRACTION_PROMPT_VERSION, "issues": issues, "latency_ms": meta["latency_ms"]}
