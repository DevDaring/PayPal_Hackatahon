"""Deterministic assessment of mandatory product attributes (pass / fail / unknown).

Both the extracted value and the cited source sentence are assessed and the worse outcome wins,
so a correct-looking value ("USB-C") cannot pass when its own evidence says "USB-C not supported".
Negation and exclusion fail; conditional or limited statements and conflicting values stay unknown.
"""

from __future__ import annotations

import re

from .requirements import KNOWN_ATTRIBUTES, Criterion

_RANK = {"pass": 0, "unknown": 1, "fail": 2}
_NEG_BEFORE = r"\b(?:no|not|without|non|never|excluding|excludes|except|lacks?|minus)\b[^.;:,]{0,24}?"
_NEG_AFTER = r"[^.;:]{0,30}?\b(?:not\s+(?:supported|included|available|provided|compatible)|isn'?t\s+\w+|unsupported|not\s+part\s+of|excluded|unavailable|sold\s+separately|removed)\b"
_COND = r"\b(?:optional|optionally|on\s+request|upon\s+request|if\s+requested|add-?on|at\s+extra\s+cost|extra\s+charge|upgrade|can\s+be\s+added|subject\s+to\s+availability|available\s+separately)\b"
_LIMIT = r"\b(?:charging\s+only|for\s+charging|power\s+only|adapter\s+only|via\s+adapter|with\s+(?:an?\s+)?adapter)\b"


def _term_re(term: str) -> str:
    t = re.escape(term.lower()).replace(r"\-", r"[\s-]?").replace(r"\ ", r"[\s-]?")
    return rf"(?<![a-z0-9]){t}(?![a-z0-9])"


def _terms(c: Criterion) -> tuple[list[str], list[str]]:
    wanted = sorted({s.lower() for s in c.synonyms} | {c.expected.lower()} - {"yes"}, key=len, reverse=True)
    others: list[str] = []
    info = KNOWN_ATTRIBUTES.get(c.key)
    if info:
        for value, syns in info["values"].items():
            if value.lower() != c.expected.lower() and value.lower() not in ("no", "yes"):
                others += [s.lower() for s in syns] + [value.lower()]
    return wanted, others


def _clause_status(c: Criterion, clause: str, wanted: list[str], others: list[str]) -> tuple[str | None, str]:
    """Return (status or None if the clause says nothing relevant, reason)."""
    t = clause.lower().strip()
    yes_type = c.expected.lower() == "yes"
    if yes_type and t in ("yes", "true", "included", "y"):
        return "pass", "stated as included"
    if yes_type and t in ("no", "false", "none", "n", "not included"):
        return "fail", "stated as not included"
    w_hit = next((w for w in wanted if re.search(_term_re(w), t)), None)
    o_hit = next((o for o in others if re.search(_term_re(o), t)), None)
    if w_hit:
        wr = _term_re(w_hit)
        if re.search(_NEG_BEFORE + wr, t) or re.search(wr + _NEG_AFTER, t):
            return "fail", f"“{clause.strip()}” negates {c.label}"
        if re.search(_COND, t):
            return "unknown", f"“{clause.strip()}” makes {c.label} conditional or optional"
        if re.search(_LIMIT, t) or (o_hit and not yes_type):
            return "unknown", f"“{clause.strip()}” does not clearly provide {c.label}"
        return "pass", f"“{clause.strip()}”"
    if o_hit and not yes_type:
        return "fail", f"“{clause.strip()}” states a different {c.key.replace('_', ' ')}"
    return None, ""


def assess(c: Criterion, value: str | None, source: str | None = None) -> tuple[str, str]:
    """Assess a mandatory attribute from its extracted value and (optionally) its cited source text."""
    texts = [str(x) for x in (value, source) if x is not None and str(x).strip()]
    if not texts:
        return "unknown", f"The quote does not state its {c.key.replace('_', ' ')}; {c.label} cannot be confirmed."
    wanted, others = _terms(c)
    worst, reasons, seen_pass, seen_other = None, [], False, False
    for text in texts:
        for clause in re.split(r"[.;\n]|\bbut\b|\bhowever\b", text, flags=re.I):
            if not clause.strip():
                continue
            st, why = _clause_status(c, clause, wanted, others)
            if st is None:
                continue
            seen_pass |= st == "pass"
            seen_other |= st == "fail" and "different" in why
            if worst is None or _RANK[st] > _RANK[worst]:
                worst, reasons = st, [why]
            elif st == worst and why not in reasons:
                reasons.append(why)
    if worst is None:
        short = len(texts[0].split()) <= 3 and c.expected.lower() != "yes"
        return ("fail", f"Quote states {texts[0]}; requirement is {c.expected}.") if short else ("unknown", f"Quote text '{texts[0][:80]}' does not clearly state {c.label}.")
    if worst == "fail" and seen_pass and seen_other:
        # Both the required value and a different one are stated: ask, do not guess.
        return "unknown", f"Conflicting statements for {c.label}: " + "; ".join(reasons[:2]) + ". Needs clarification."
    if worst == "pass":
        return "pass", f"Quote states {reasons[0]}."
    if worst == "fail":
        return "fail", "Quote evidence: " + "; ".join(reasons[:2]) + "."
    return "unknown", "Needs clarification: " + "; ".join(reasons[:2]) + "."
