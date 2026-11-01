"""Read-only PayPal Agent Toolkit tools for the request assistant.

The model may *choose* to call these tools, but it supplies no arguments: the server injects
the order/capture IDs belonging to the current request. Only read actions are registered —
no create, capture, refund or invoice tools are reachable from the model.
"""

from __future__ import annotations

import json
import time

from ..config import get_settings
from ..paypal.base import order_summary

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "paypal_get_order_details",
            "description": "Read-only. Look up THIS purchase request's PayPal order (status, amount, payee merchant, captures) through the PayPal Agent Toolkit. Takes no arguments.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "paypal_find_capture_transaction",
            "description": "Read-only. Search PayPal transaction reporting for THIS request's capture through the PayPal Agent Toolkit. Reporting can lag behind captures. Takes no arguments.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]
ALLOWED = {t["function"]["name"] for t in TOOLS}


def _api():
    from paypal_agent_toolkit.shared.api import PayPalAPI
    from paypal_agent_toolkit.shared.configuration import Context

    s = get_settings()
    return PayPalAPI(client_id=s.PAYPAL_CLIENT_ID, secret=s.PAYPAL_CLIENT_SECRET, context=Context(sandbox=True))


def available(order_id: str | None, adapter: str | None) -> bool:
    s = get_settings()
    return bool(order_id and adapter == "sandbox" and s.paypal_credentials_present)


def execute(name: str, order_id: str, capture_id: str | None) -> dict:
    """Run one allowed tool with server-chosen arguments; return a redacted, model-safe result."""
    if name not in ALLOWED:
        return {"error": "tool not allowed"}
    t0 = time.monotonic()
    try:
        if name == "paypal_get_order_details":
            raw = _api().run("get_order_details", {"order_id": order_id})
            body = json.loads(raw) if isinstance(raw, str) else raw
            # Use only provider data; the toolkit's prose message is not passed on.
            result = {"order": order_summary(body.get("raw") or {})}
        else:
            if not capture_id:
                return {"found": False, "note": "No capture exists yet for this request.", "latency_ms": 0}
            raw = _api().run("list_transactions", {"transaction_id": capture_id, "search_months": 1})
            body = json.loads(raw) if isinstance(raw, str) else raw
            details = body.get("transaction_details") or []
            info = (details[0].get("transaction_info") if details else {}) or {}
            result = {"found": bool(body.get("found")), "transaction_status": info.get("transaction_status"),
                      "amount": (info.get("transaction_amount") or {}).get("value"), "note": None if body.get("found") else "Not in PayPal reporting yet (reporting can lag)."}
    except Exception as e:  # tool failures are reported to the model as data, never raised to the user
        result = {"error": type(e).__name__}
    result["latency_ms"] = int((time.monotonic() - t0) * 1000)
    return result
