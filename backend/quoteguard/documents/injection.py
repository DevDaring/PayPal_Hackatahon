"""Suspicious-instruction signals in document text.

This is an informative signal for reviewers. It is NOT the defence: access control and
deterministic policy apply whether or not a pattern matches.
"""

from __future__ import annotations

import re

PATTERNS = [
    (r"ignore (all |any )?(previous|prior|the|your)?\s*(buyer'?s?|user'?s?)?\s*(instructions|budget|rules|policy|constraints)", "Instruction to ignore rules"),
    (r"disregard (the|all|any|previous)", "Instruction to disregard"),
    (r"(system|developer)\s*(prompt|message|instruction)", "Claims to be a system message"),
    (r"you are (now )?(an?|the) (ai|assistant|agent|model)", "Addresses the AI directly"),
    (r"(approve|authori[sz]e) (this|the) (purchase|payment|order) (immediately|automatically|now)", "Requests automatic approval"),
    (r"(send|transfer|wire|route) (the )?(payment|funds|money) to", "Redirects payment destination"),
    (r"(pay|payment) (to|via) [\w.+-]+@[\w-]+\.[\w.]+", "Supplies a payment email"),
    (r"(iban|swift|routing number|account number)\s*[:#]", "Supplies bank details"),
    (r"mark (this|the) quote as (compliant|eligible|approved)", "Asks to mark quote compliant"),
    (r"budget (is|has been) (increased|raised|waived)", "Claims a budget change"),
]


def scan(pages: list[dict]) -> list[dict]:
    hits = []
    for p in pages:
        text = p.get("text") or ""
        for pat, label in PATTERNS:
            for m in re.finditer(pat, text, flags=re.I):
                start = max(0, m.start() - 40)
                hits.append({"page": p["page_number"], "label": label, "excerpt": text[start : m.end() + 60].replace("\n", " ").strip()})
    # One entry per (page, label)
    seen, out = set(), []
    for h in hits:
        k = (h["page"], h["label"])
        if k not in seen:
            seen.add(k)
            out.append(h)
    return out
