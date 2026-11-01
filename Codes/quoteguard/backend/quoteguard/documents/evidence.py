"""Locate a supporting snippet on a page and return word-level bounding boxes."""

from __future__ import annotations

import re

_TOKEN = re.compile(r"[a-z0-9]+")


def norm_tokens(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def snippet_on_page(snippet: str, page_text: str) -> bool:
    a, b = norm_tokens(snippet), norm_tokens(page_text)
    if not a:
        return False
    joined = " " + " ".join(b) + " "
    return (" " + " ".join(a) + " ") in joined


def locate(snippet: str, words: list[list]) -> list[list[float]] | None:
    """Find the snippet as a consecutive run of page words. Returns one box per line, or None."""
    target = norm_tokens(snippet)
    if not target:
        return None
    flat: list[tuple[str, list]] = []
    for w in words:
        for t in norm_tokens(w[0]):
            flat.append((t, w))
    n = len(target)
    for i in range(len(flat) - n + 1):
        if all(flat[i + k][0] == target[k] for k in range(n)):
            seen: list = []
            for k in range(n):
                w = flat[i + k][1]
                if not seen or seen[-1] is not w:
                    seen.append(w)
            lines: dict[int, list[float]] = {}
            for w in seen:
                key = round(w[2] / 4)
                box = lines.get(key)
                lines[key] = [min(box[0], w[1]), min(box[1], w[2]), max(box[2], w[3]), max(box[3], w[4])] if box else [w[1], w[2], w[3], w[4]]
            return [[round(v, 2) for v in b] for b in lines.values()]
    return None


def value_supported(value, snippet: str) -> bool:
    """Independent numeric check: the extracted number must appear in its own evidence."""
    if value is None or snippet is None:
        return False
    s = str(value)
    if re.fullmatch(r"0+(\.0+)?", s.strip()) and re.search(r"\b(free|included|waived|no charge|complimentary)\b", snippet, re.I):
        return True
    digits = re.sub(r"[^0-9.]", "", s)
    if not digits:
        return True
    snippet_nums = {re.sub(r"[^0-9.]", "", m).rstrip(".") for m in re.findall(r"\d[\d,]*(?:\.\d+)?", snippet)}
    candidates = {digits, digits.rstrip("0").rstrip(".") if "." in digits else digits}
    try:
        from decimal import Decimal

        dv = Decimal(digits)
        candidates |= {n for n in snippet_nums if n and Decimal(n) == dv}
    except Exception:
        pass
    return bool(candidates & snippet_nums)
