"""LLM extraction with strict validation, evidence verification and a deterministic cross-check."""

from __future__ import annotations

import hashlib
import json
import re

from pydantic import ValidationError

from ..config import get_settings
from ..documents import rules_extractor
from ..documents.evidence import snippet_on_page, value_supported
from ..documents.schema import MONEY_FIELDS, Cited, Extraction
from .requirements_parser import words_to_int
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
        if name == "delivery_days":
            # Normalise day counts deterministically from the cited text (business → calendar days).
            m = re.search(r"within\s+(\d+|[a-z]+)\s+(calendar\s+|business\s+|working\s+)?days?", c.source_text, re.I)
            if m:
                n = int(m.group(1)) if m.group(1).isdigit() else words_to_int(m.group(1))
                if n is not None:
                    business = bool(m.group(2)) and m.group(2).strip().lower() in ("business", "working")
                    c.value = n + (n // 5) * 2 + (2 if n % 5 else 0) if business else n
                    if business:
                        issues.append("Delivery is stated in business days; converted conservatively to calendar days.")
                    continue
        if name in MONEY_FIELDS + ("quantity", "delivery_days") and not value_supported(c.value, c.source_text):
            issues.append(f"{name}: value {c.value} does not appear in its cited text; withheld for review.")
            c.value = None
    # The model's claim that a currency is "explicit" is checked against the document itself.
    code = str(ex.currency.value or "").upper()
    full = "\n".join(by_page.values())
    if ex.currency_explicit and not (len(code) == 3 and re.search(rf"\b{code}\b", full)):
        ex.currency_explicit = False
        issues.append(f"Currency note: no ISO code '{code or '?'}' is printed in the document; treated as inferred.")
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
    # Grounded fallback: a critical value the model left empty, but the deterministic parser cited, is adopted and noted.
    by_page = {p["page_number"]: p.get("text") or "" for p in pages}
    for f in ("quantity", "subtotal", "shipping", "tax", "total", "delivery_days", "valid_until", "currency"):
        mine, theirs = getattr(ex, f), getattr(rules, f)
        if mine.value is None and theirs.value is not None and theirs.page in by_page and snippet_on_page(theirs.source_text or "", by_page[theirs.page]):
            setattr(ex, f, theirs)
            if f == "currency":
                ex.currency_explicit = rules.currency_explicit
            issues.append(f"Note: model returned no {f.replace('_', ' ')}; deterministic parser value used (cited on page {theirs.page}).")
    # Independent cross-check of critical amounts against the deterministic parser.
    for f in ("subtotal", "shipping", "tax", "total", "quantity"):
        a, b = getattr(ex, f).value, getattr(rules, f).value
        if a is not None and b is not None and str(a).rstrip("0").rstrip(".") != str(b).rstrip("0").rstrip("."):
            issues.append(f"{f}: model read {a} but the deterministic parser read {b}; needs review.")
    return ex, {"method": "llm", "model": meta["model"], "prompt_version": EXTRACTION_PROMPT_VERSION, "issues": issues, "latency_ms": meta["latency_ms"]}
