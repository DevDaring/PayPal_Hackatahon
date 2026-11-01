"""PDF text extraction, run in a resource-limited child process (see ingest.parse_isolated).

Reads PDF bytes from stdin and writes JSON pages to stdout. Treats the PDF as hostile input.
"""

from __future__ import annotations

import io
import json
import re
import sys

_MONEY = re.compile(r"^[$€£]?\d{1,3}(?:,?\d{3})*\.\d{2}$|^[$€£]\d+$")
_ID = re.compile(rb"/ID\s*\[\s*<([0-9A-Fa-f]{8,64})>")


def _s(v) -> str:
    if isinstance(v, bytes):
        try:
            return v.decode("utf-16") if v[:2] in (b"\xfe\xff", b"\xff\xfe") else v.decode("latin-1")
        except UnicodeDecodeError:
            return ""
    return str(v) if v is not None else ""


def _base_font(name: str) -> str:
    return name.split("+", 1)[1] if len(name) > 7 and name[6] == "+" else name  # drop subset tag "ABCDEF+"


def _patches(page) -> list[dict]:
    """Opaque filled shapes drawn AFTER text that they cover: the classic white-box edit.

    Uses content-stream order (pdfminer objects in drawing order, no layout analysis)."""
    from pdfminer.layout import LTChar, LTCurve

    objs = list(page.layout)
    area = float(page.width) * float(page.height)
    out = []
    for i, o in enumerate(objs):
        if not isinstance(o, LTCurve) or not getattr(o, "fill", False):
            continue
        w, h = o.x1 - o.x0, o.y1 - o.y0
        if w * h > 0.25 * area or w < 3 or h < 3:
            continue
        inside = lambda c: o.x0 - 0.5 <= (c.x0 + c.x1) / 2 <= o.x1 + 0.5 and o.y0 - 0.5 <= (c.y0 + c.y1) / 2 <= o.y1 + 0.5
        under = sorted((c for c in objs[:i] if isinstance(c, LTChar) and inside(c)), key=lambda c: c.x0)
        hidden = "".join(c.get_text() for c in under).strip()
        if not any(ch.isalnum() for ch in hidden):
            continue
        over = "".join(c.get_text() for c in sorted((c for c in objs[i + 1:] if isinstance(c, LTChar) and inside(c)), key=lambda c: c.x0)).strip()
        col = o.non_stroking_color
        out.append({"page": page.page_number, "bbox": [round(o.x0, 1), round(float(page.height) - o.y1, 1), round(o.x1, 1), round(float(page.height) - o.y0, 1)],
                    "hidden": hidden[:80], "replacement": over[:80], "fill": [round(float(x), 3) for x in col] if isinstance(col, (list, tuple)) else col})
        if len(out) >= 20:
            break
    return out


def _money_fonts(page) -> list[dict]:
    """Font and size of every amount, plus the font of the label beside it on the same line."""
    words = page.extract_words(extra_attrs=["fontname", "size"])
    out = []
    for i, w in enumerate(words):
        if not _MONEY.match(w["text"]):
            continue
        left = [v for v in words if abs(v["top"] - w["top"]) < 2 and v["x1"] <= w["x0"] + 0.5]
        nb = max(left, key=lambda v: v["x1"]) if left else None
        out.append({"page": page.page_number, "text": w["text"], "font": _base_font(w["fontname"]), "size": round(float(w["size"]), 1),
                    "label_font": _base_font(nb["fontname"]) if nb else None, "label": nb["text"] if nb else None,
                    "bbox": [round(w["x0"], 1), round(w["top"], 1), round(w["x1"], 1), round(w["bottom"], 1)]})
    return out[:200]


def _revision_text(data: bytes) -> str | None:
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join((p.extract_text(layout=False) or "") for p in pdf.pages[:20])[:40000]
    except Exception:
        return None


def forensics(data: bytes, pdf) -> dict:
    meta = {k.lower(): _s(v)[:200] for k, v in (pdf.metadata or {}).items() if k in ("Author", "Creator", "Producer", "Title", "CreationDate", "ModDate")}
    ids = _ID.findall(data)
    # Each %%EOF ends a revision. An incremental update leaves every earlier revision byte-for-byte in the file.
    ends = [m.end() for m in re.finditer(rb"%%EOF", data)]
    revisions = []
    for n, end in enumerate(ends[:-1][-4:]):
        revisions.append({"index": n + 1, "bytes": end, "text": _revision_text(data[:end])})
    fonts = sorted({_base_font(c.get("fontname", "")) for p in pdf.pages[:20] for c in p.chars})
    return {"meta": meta, "doc_id": ids[0].decode().lower() if ids else None, "revision_count": len(ends), "previous_revisions": revisions,
            "patches": [x for p in pdf.pages[:20] for x in _patches(p)], "money_fonts": [x for p in pdf.pages[:20] for x in _money_fonts(p)], "fonts": fonts[:40]}


def parse(data: bytes, max_pages: int) -> dict:
    import pdfplumber

    pages = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if len(pdf.pages) > max_pages:
            return {"error": "TOO_MANY_PAGES", "page_count": len(pdf.pages)}
        for i, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(keep_blank_chars=False, use_text_flow=True, extra_attrs=[])
            text = page.extract_text(layout=False) or ""
            pages.append({
                "page_number": i,
                "width": float(page.width),
                "height": float(page.height),
                "text": text,
                "words": [[w["text"], round(float(w["x0"]), 2), round(float(w["top"]), 2), round(float(w["x1"]), 2), round(float(w["bottom"]), 2)] for w in words],
            })
        try:
            extra = forensics(data, pdf)
        except Exception as e:  # forensics are best-effort; parsing must still succeed
            extra = {"error": type(e).__name__}
    return {"pages": pages, "forensics": extra}


if __name__ == "__main__":
    max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    try:
        out = parse(sys.stdin.buffer.read(), max_pages)
    except Exception as e:  # malformed PDFs are reported, never crash the worker
        out = {"error": "UNREADABLE_PDF", "detail": type(e).__name__}
    sys.stdout.write(json.dumps(out))
