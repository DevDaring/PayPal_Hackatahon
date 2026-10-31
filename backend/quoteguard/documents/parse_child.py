"""PDF text extraction, run in a resource-limited child process (see ingest.parse_isolated).

Reads PDF bytes from stdin and writes JSON pages to stdout. Treats the PDF as hostile input.
"""

from __future__ import annotations

import io
import json
import sys


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
    return {"pages": pages}


if __name__ == "__main__":
    max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    try:
        out = parse(sys.stdin.buffer.read(), max_pages)
    except Exception as e:  # malformed PDFs are reported, never crash the worker
        out = {"error": "UNREADABLE_PDF", "detail": type(e).__name__}
    sys.stdout.write(json.dumps(out))
