"""Natural language → typed requirement draft. The draft must be confirmed by a person."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from ..domain.requirements import KNOWN_ATTRIBUTES, RequirementSpec, criterion_for
from ..money import to_money
from .prompts import REQUIREMENTS_PROMPT_VERSION, REQUIREMENTS_SYSTEM
from .provider import AIUnavailable, chat_json

_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
          "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}


def words_to_int(s: str) -> int | None:
    s = s.lower().strip()
    if s.isdigit():
        return int(s)
    total = 0
    for part in re.split(r"[\s-]+", s):
        if part in _UNITS:
            total += _UNITS[part]
        elif part in _TENS:
            total += _TENS[part]
        elif part == "hundred":
            total = max(total, 1) * 100
        else:
            return None
    return total


_NUMWORD = r"(\d+|(?:(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[\s-](?:one|two|three|four|five|six|seven|eight|nine))?)|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|hundred)"


def parse_rules(text: str, tz: str) -> dict:
    t = text.strip()
    amb: list[str] = []
    qty = None
    item = None
    m = re.search(rf"\b(?:buy|order|purchase|need|procure)?\s*{_NUMWORD}\s+([A-Za-z0-9\- ]+?)(?:\s+with\b|[.,;]|$)", t, re.I)
    if m:
        qty = words_to_int(m.group(1))
        item = m.group(2).strip()
    budget = None
    currency = None
    m = re.search(r"(?:budget|max(?:imum)?|up to|not exceed)[^0-9$₹€£]{0,30}(US\$|\$|USD|INR|₹|EUR|€|GBP|£)?\s?([0-9][0-9,]*(?:\.\d{1,2})?)\s*(USD|INR|EUR|GBP)?", t, re.I)
    if m:
        budget = to_money(m.group(2))
        sym = (m.group(1) or m.group(3) or "").upper()
        currency = {"$": "USD", "US$": "USD", "USD": "USD", "₹": "INR", "INR": "INR", "€": "EUR", "EUR": "EUR", "£": "GBP", "GBP": "GBP"}.get(sym)
        if sym == "$":
            amb.append("Currency inferred from '$' as USD.")
    if currency is None:
        amb.append("Budget currency is not stated.")
    includes = [x for x in ("shipping", "tax") if re.search(rf"includ\w*[^.]*{x}", t, re.I)]
    deadline_days = None
    m = re.search(rf"within\s+{_NUMWORD}\s+(calendar\s+|business\s+|working\s+)?days?", t, re.I)
    if m:
        deadline_days = words_to_int(m.group(1))
        if m.group(2) and m.group(2).strip().lower() in ("business", "working"):
            amb.append("Deadline given in business days; interpreted as calendar days — please confirm.")
    mandatory = []
    m = re.search(r"\b(USB[- ]?C|USB Type-C|USB[- ]?A|3\.5\s?mm|Bluetooth)\b", t, re.I)
    if m:
        v = m.group(1).upper().replace(" ", "-").replace("TYPE-", "")
        v = {"USBC": "USB-C", "USB-C": "USB-C", "USBA": "USB-A", "USB-A": "USB-A"}.get(v, m.group(1))
        mandatory.append({"key": "connector", "expected": v})
        if item:
            item = re.sub(re.escape(m.group(1)), "", item, flags=re.I).strip()
    if re.search(r"\b(microphones?|mics?)\b", t, re.I):
        mandatory.append({"key": "microphone", "expected": "yes"})
    return {
        "item": (item or "items").strip(" -"),
        "quantity": qty,
        "budget_amount": str(budget) if budget is not None else None,
        "currency": currency,
        "budget_includes": includes or ["shipping", "tax"],
        "deadline_days": deadline_days,
        "deadline_date": None,
        "mandatory": mandatory,
        "preferred": [],
        "ambiguities": amb,
    }


def to_spec(raw: dict, tz: str, created_at: datetime) -> tuple[RequirementSpec | None, list[str]]:
    """Validate a raw draft into a RequirementSpec. Returns (spec or None, problems)."""
    problems: list[str] = list(raw.get("ambiguities") or [])
    today = created_at.astimezone(__import__("zoneinfo").ZoneInfo(tz)).date()
    deadline_date = None
    if raw.get("deadline_date"):
        try:
            deadline_date = date.fromisoformat(str(raw["deadline_date"]))
        except ValueError:
            problems.append("Deadline date could not be read.")
    elif raw.get("deadline_days") is not None:
        deadline_date = today + timedelta(days=int(raw["deadline_days"]))
    mandatory = []
    for c in raw.get("mandatory") or []:
        key = re.sub(r"[^a-z0-9_]", "_", str(c.get("key", "")).lower())[:40].strip("_")
        if key and c.get("expected"):
            mandatory.append(criterion_for(key, str(c["expected"])))
    try:
        spec = RequirementSpec(
            item=raw.get("item") or "items",
            quantity=int(raw["quantity"]),
            budget_amount=Decimal(str(raw["budget_amount"])),
            currency=raw.get("currency") or "",
            budget_includes=raw.get("budget_includes") or ["shipping", "tax"],
            deadline_days=raw.get("deadline_days") if raw.get("deadline_days") is not None else ((deadline_date - today).days if deadline_date else None),
            deadline_date=deadline_date,
            timezone=tz,
            mandatory=mandatory,
            preferred=[str(p)[:120] for p in (raw.get("preferred") or [])][:10],
            ambiguities=[str(a)[:200] for a in problems][:10],
        )
        return spec, problems
    except Exception as e:  # missing quantity/budget/currency → needs clarification
        problems.append(f"Required fields missing or invalid: {type(e).__name__}")
        return None, problems


def parse(text: str, tz: str, created_at: datetime, *, workspace_id=None, request_id=None) -> dict:
    """Return {'raw': draft, 'method': 'llm'|'rules', 'model': ...}. Rules are the fallback."""
    rules = parse_rules(text, tz)
    try:
        raw, meta = chat_json(REQUIREMENTS_SYSTEM, f"Today is {created_at.date().isoformat()} ({tz}).\n<request>\n{text[:4000]}\n</request>", purpose="requirements", workspace_id=workspace_id, request_id=request_id, max_tokens=800)
        # Deterministic guards: keep model values only when the source text supports them.
        if raw.get("budget_amount") is not None and to_money(raw["budget_amount"]) is not None:
            amt = to_money(raw["budget_amount"])
            if str(int(amt)) not in text.replace(",", "") and str(amt) not in text:
                raw["budget_amount"] = rules["budget_amount"]
                raw.setdefault("ambiguities", []).append("Model budget not found in text; used the stated figure.")
        for k in ("quantity", "currency", "deadline_days"):
            if raw.get(k) is None and rules.get(k) is not None:
                raw[k] = rules[k]
        known = {c["key"] for c in raw.get("mandatory") or []}
        for c in rules["mandatory"]:
            if c["key"] not in known:
                raw.setdefault("mandatory", []).append(c)
        raw["mandatory"] = [c for c in raw.get("mandatory") or [] if isinstance(c, dict)]
        for c in raw["mandatory"]:
            if c.get("key") == "connector" and str(c.get("expected", "")).upper().replace(" ", "-") in ("USB-C", "USB-TYPE-C", "TYPE-C"):
                c["expected"] = "USB-C"
            if c.get("key") in ("microphone", "mic", "has_microphone"):
                c["key"], c["expected"] = "microphone", "yes"
        return {"raw": raw, "method": "llm", "model": meta["model"], "prompt_version": REQUIREMENTS_PROMPT_VERSION}
    except AIUnavailable:
        return {"raw": rules, "method": "rules", "model": None, "prompt_version": "rules-v1"}


__all__ = ["parse", "parse_rules", "to_spec", "KNOWN_ATTRIBUTES"]
