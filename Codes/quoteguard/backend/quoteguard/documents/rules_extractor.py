"""Deterministic extractor for text-readable quotations.

Used when no AI provider is configured, as a baseline in evaluation, and as an
independent cross-check of model output. It only returns values it can cite.
"""

from __future__ import annotations

import re
from datetime import datetime

from .schema import Cited, Extraction, LineItem

RULES_VERSION = "rules-v2"
_NUM = r"(?:US\$|USD|\$|€|£|₹|INR|EUR)?\s?([0-9][0-9,]*(?:\.[0-9]{1,2})?)"
_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fourteen": 14, "twenty": 20, "thirty": 30}


def _lines(pages: list[dict]):
    for p in pages:
        for line in (p.get("text") or "").splitlines():
            if line.strip():
                yield p["page_number"], line.strip()


def _first(pages, pattern, flags=re.I):
    for pg, line in _lines(pages):
        m = re.search(pattern, line, flags)
        if m:
            return pg, line, m
    return None


def _money_field(pages, label_pattern: str, zero_words=("free", "included", "waived", "exempt", "0%")) -> Cited:
    hit = _first(pages, rf"^\s*(?:{label_pattern})\b[^:\n]*?[:\s]\s*(.*)$")
    if not hit:
        return Cited()
    pg, line, m = hit
    rest = line.rsplit(":", 1)[1] if ":" in line else m.group(1)
    n = re.search(r"(?:US\$|USD|\$|€|£|₹|INR|EUR)\s?([0-9][0-9,]*(?:\.[0-9]{1,2})?)", rest) or re.search(r"\b([0-9][0-9,]*\.[0-9]{2})\b", rest) or re.search(_NUM, rest)
    if n:
        return Cited(value=n.group(1).replace(",", ""), page=pg, source_text=line)
    if any(w in rest.lower() for w in zero_words) and not re.search(r"not included|excluded|extra|tbd|to be (confirmed|determined)|calculated", rest, re.I):
        return Cited(value="0.00", page=pg, source_text=line)
    return Cited()  # stated label but no determinable amount → unknown


def _parse_date(s: str):
    s = s.strip().rstrip(".")
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%B %d, %Y", "%d %b %Y", "%b %d, %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def extract(pages: list[dict], attribute_keys: list[str] | None = None) -> Extraction:
    ex = Extraction()
    attribute_keys = attribute_keys or ["connector", "microphone"]

    # Supplier: an explicit "Supplier:" label, else the first heading line on page 1.
    hit = _first(pages, r"^(?:supplier|vendor|from)\s*[:\-]\s*(.+)$")
    if hit:
        ex.supplier_name = Cited(value=hit[2].group(1).strip(), page=hit[0], source_text=hit[1])
    else:
        for pg, line in _lines(pages):
            if re.search(r"(supplies|office|devices|inc\.?|ltd\.?|llc|co\.|trading|electronics|systems)$", line, re.I):
                ex.supplier_name = Cited(value=line, page=pg, source_text=line)
                break

    hit = _first(pages, r"\bcurrency\s*[:\-]\s*([A-Z]{3})\b", 0)
    if hit:
        ex.currency, ex.currency_explicit = Cited(value=hit[2].group(1), page=hit[0], source_text=hit[1]), True
    else:
        hit = _first(pages, r"\b(USD|EUR|INR|GBP)\b", 0)
        if hit:
            ex.currency, ex.currency_explicit = Cited(value=hit[2].group(1), page=hit[0], source_text=hit[1]), True
        else:
            hit = _first(pages, r"(\$|€|£|₹)\s?\d")
            if hit:
                sym = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR"}[hit[2].group(1)]
                ex.currency = Cited(value=sym, page=hit[0], source_text=hit[1])
                ex.ambiguities.append(f"Currency inferred from the '{hit[2].group(1)}' symbol; no currency code is stated.")

    hit = _first(pages, r"\b(?:quantity|qty)\s*[:\-]?\s*(\d{1,6})\b")
    if hit:
        ex.quantity = Cited(value=int(hit[2].group(1)), page=hit[0], source_text=hit[1])
    hit = _first(pages, rf"\bunit price\b[^:\n]*[:\s]\s*{_NUM}")
    if hit:
        ex.unit_price = Cited(value=hit[2].group(1).replace(",", ""), page=hit[0], source_text=hit[1])

    ex.subtotal = _money_field(pages, r"(?:item\s+|items\s+)?sub-?total")
    ex.shipping = _money_field(pages, r"shipping|delivery charge|freight")
    ex.tax = _money_field(pages, r"(?:sales\s+)?tax(?:es)?|gst|vat")
    ex.discount = _money_field(pages, r"discount", zero_words=())
    ex.total = _money_field(pages, r"(?:grand\s+)?total(?:\s+due)?", zero_words=())

    hit = _first(pages, r"\b(?:delivery|dispatch|lead time|ships?)\b[^\n]*?\bwithin\s+(\d+|[a-z]+)\s+(calendar\s+|business\s+|working\s+)?days?")
    if hit:
        raw = hit[2].group(1).lower()
        days = int(raw) if raw.isdigit() else _WORDS.get(raw)
        if days is not None:
            if hit[2].group(2) and hit[2].group(2).strip().lower() in ("business", "working"):
                days = days + (days // 5) * 2 + (2 if days % 5 else 0)
                ex.ambiguities.append("Delivery is stated in business days; converted conservatively to calendar days.")
            ex.delivery_days = Cited(value=days, page=hit[0], source_text=hit[1])

    for key, pat in (("issue_date", r"\b(?:issue date|quote date|date of issue|issued)\s*[:\-]\s*(.+)$"), ("valid_until", r"\b(?:valid until|valid through|expires|expiry date|validity)\s*[:\-]\s*(.+)$")):
        hit = _first(pages, pat)
        if hit:
            d = _parse_date(hit[2].group(1))
            if d:
                setattr(ex, key, Cited(value=d, page=hit[0], source_text=hit[1]))

    hit = _first(pages, r"^(?:product|item|description)\s*[:\-]\s*(.+)$")
    if hit:
        ex.product_description = Cited(value=hit[2].group(1), page=hit[0], source_text=hit[1])
    hit = _first(pages, r"^shipping terms?\s*[:\-]\s*(.+)$")
    if hit:
        ex.shipping_terms = Cited(value=hit[2].group(1), page=hit[0], source_text=hit[1])
        ex.flat_shipping = "flat" in hit[2].group(1).lower()
    hit = _first(pages, r"^pricing terms?\s*[:\-]\s*(.+)$")
    if hit:
        ex.pricing_terms = Cited(value=hit[2].group(1), page=hit[0], source_text=hit[1])
        ex.pricing_scales_with_quantity = bool(re.search(r"unit price (applies|holds|valid) (for|to) (any|all|orders)", hit[2].group(1), re.I))

    if "connector" in attribute_keys:
        hit = _first(pages, r"\b(USB[- ]?C|USB Type-C|USB[- ]?A|USB Type-A|3\.5\s?mm)\b")
        if hit:
            v = hit[2].group(1).upper().replace(" ", "-").replace("TYPE-", "")
            v = {"USB-C": "USB-C", "USBC": "USB-C", "USB-A": "USB-A", "USBA": "USB-A"}.get(v.replace("--", "-"), hit[2].group(1))
            ex.attributes["connector"] = Cited(value=v, page=hit[0], source_text=hit[1])
    if "microphone" in attribute_keys:
        hit = _first(pages, r"\b(no microphone|without (a )?microphone|microphone|boom mic|mic)\b")
        if hit:
            neg = hit[2].group(1).lower().startswith(("no ", "without"))
            ex.attributes["microphone"] = Cited(value="no" if neg else "yes", page=hit[0], source_text=hit[1])

    if ex.product_description.value and ex.quantity.value:
        ex.line_items = [LineItem(description=str(ex.product_description.value), quantity=int(ex.quantity.value), unit_price=ex.unit_price.value, line_total=ex.subtotal.value)]
    return ex
