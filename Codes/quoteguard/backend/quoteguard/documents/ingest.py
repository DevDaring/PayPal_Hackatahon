"""Upload validation and isolated parsing."""

from __future__ import annotations

import io
import json
import resource
import subprocess
import sys

from ..config import get_settings
from ..errors import AppError


def validate_upload(data: bytes, filename: str, content_type: str | None) -> int:
    s = get_settings()
    if len(data) == 0:
        raise AppError("EMPTY_FILE", "The uploaded file is empty.", 422)
    if len(data) > s.MAX_UPLOAD_MB * 1024 * 1024:
        raise AppError("FILE_TOO_LARGE", f"PDFs must be at most {s.MAX_UPLOAD_MB} MB.", 413)
    if not data[:1024].lstrip().startswith(b"%PDF-"):
        raise AppError("UNSUPPORTED_FILE", "Only PDF quotations are supported. The file does not have a PDF header.", 415)
    if content_type and content_type not in ("application/pdf", "application/x-pdf", "application/octet-stream"):
        raise AppError("UNSUPPORTED_FILE", "Only PDF quotations are supported.", 415)
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise AppError("PASSWORD_PROTECTED", "This PDF is password-protected. Ask the supplier for an unprotected copy.", 422)
        n = len(reader.pages)
    except AppError:
        raise
    except (PdfReadError, Exception):
        raise AppError("UNREADABLE_PDF", "The PDF structure could not be read.", 422) from None
    if n > s.MAX_PDF_PAGES:
        raise AppError("TOO_MANY_PAGES", f"Quotations are limited to {s.MAX_PDF_PAGES} pages (this one has {n}).", 422)
    return n


def _limits():
    resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))


def parse_isolated(data: bytes) -> dict:
    """Parse in a child process with memory/CPU limits and a wall-clock timeout."""
    s = get_settings()
    try:
        proc = subprocess.run(
            [sys.executable, "-s", "-m", "quoteguard.documents.parse_child", str(s.MAX_PDF_PAGES)],
            input=data,
            capture_output=True,
            timeout=60,
            preexec_fn=_limits,
            cwd=str(__import__("pathlib").Path(__file__).resolve().parents[2]),
        )
    except subprocess.TimeoutExpired:
        return {"error": "PARSE_TIMEOUT"}
    if proc.returncode != 0:
        return {"error": "PARSER_CRASHED"}
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return {"error": "PARSER_OUTPUT_INVALID"}


def page_quality(text: str) -> str:
    stripped = "".join(text.split())
    if len(stripped) < 25:
        return "empty"
    return "good"
