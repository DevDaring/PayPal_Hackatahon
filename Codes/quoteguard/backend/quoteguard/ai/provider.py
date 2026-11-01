"""OpenAI-compatible chat adapter (OpenAI, OpenRouter, Gemini's OpenAI endpoint).

The model only ever receives text and returns JSON. It has no tools that reach HTTP,
the filesystem, the environment or payment services.
"""

from __future__ import annotations

import itertools
import json
import logging
import re
import threading
import time

import httpx

from ..config import get_settings
from ..db import session_scope
from ..errors import AppError
from ..models import AICall

log = logging.getLogger("quoteguard.ai")


class AIUnavailable(Exception):
    pass


class _KeyRing:
    def __init__(self, keys: list[str]):
        self._keys = keys
        self._cycle = itertools.cycle(range(len(keys))) if keys else None
        self._lock = threading.Lock()

    def next(self) -> str:
        with self._lock:
            return self._keys[next(self._cycle)]


_ring: _KeyRing | None = None


def _keys() -> _KeyRing:
    global _ring
    if _ring is None:
        _ring = _KeyRing(get_settings().ai_keys)
    return _ring


def _parse_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])


def chat_json(
    system: str,
    user: str,
    *,
    purpose: str,
    workspace_id=None,
    request_id=None,
    max_tokens: int | None = None,
    temperature: float = 0.0,
) -> tuple[dict, dict]:
    """Return (parsed_json, meta). Retries rate limits on the next key, bounded."""
    s = get_settings()
    if not s.ai_configured or s.MOCK_AI:
        raise AIUnavailable("AI provider is not configured")
    body = {
        "model": s.AI_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens or s.AI_MAX_TOKENS,
        "response_format": {"type": "json_object"},
    }
    if s.AI_PROVIDER == "gemini":
        body["reasoning_effort"] = "none" if "2.5-flash" in s.AI_MODEL else "low"
    last_err = "unknown"
    attempts = min(4, max(2, len(s.ai_keys) * 2))
    for attempt in range(attempts):
        t0 = time.monotonic()
        status = "error"
        usage = {}
        try:
            r = httpx.post(
                s.AI_BASE_URL.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {_keys().next()}", "Content-Type": "application/json"},
                json=body,
                timeout=s.AI_TIMEOUT_SECONDS,
            )
            if r.status_code in (429, 500, 502, 503, 504):
                last_err = f"provider {r.status_code}"
                status = "retry"
                time.sleep(min(4, 0.6 * (attempt + 1)))
                continue
            if r.status_code >= 400:
                last_err = f"provider {r.status_code}"
                break
            d = r.json()
            usage = d.get("usage") or {}
            content = d["choices"][0]["message"]["content"] or ""
            parsed = _parse_json(content)
            status = "ok"
            return parsed, {"model": s.AI_MODEL, "provider": s.AI_PROVIDER, "latency_ms": int((time.monotonic() - t0) * 1000), "usage": usage}
        except (httpx.HTTPError, ValueError, KeyError) as e:
            last_err = type(e).__name__
            status = "error"
        finally:
            try:
                with session_scope() as db:
                    db.add(AICall(workspace_id=workspace_id, request_id=request_id, purpose=purpose, provider=s.AI_PROVIDER, model=s.AI_MODEL, status=status,
                                  latency_ms=int((time.monotonic() - t0) * 1000), prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens")))
            except Exception:  # logging must never break the caller
                log.warning("ai call log failed")
    raise AIUnavailable(f"model call failed: {last_err}")


def require_budget(used: int) -> None:
    if used >= get_settings().AI_MAX_CALLS_PER_REQUEST:
        raise AppError("AI_BUDGET_EXCEEDED", "This request reached its AI call limit; continue with manual review.", 429)


def chat_with_tools(system: str, user: str, tools: list[dict], run_tool, *, purpose: str, workspace_id=None, request_id=None, max_rounds: int = 2) -> tuple[dict, dict, list[dict]]:
    """OpenAI-compatible tool calling, bounded to `max_rounds` tool rounds.

    `run_tool(name) -> dict` is supplied by the caller and ignores any model-provided arguments.
    Returns (parsed_json_answer, meta, trace).
    """
    s = get_settings()
    if not s.ai_configured or s.MOCK_AI:
        raise AIUnavailable("AI provider is not configured")
    messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    trace: list[dict] = []
    t_all = time.monotonic()
    for round_ in range(max_rounds + 1):
        body = {"model": s.AI_MODEL, "messages": messages, "temperature": 0.2, "max_tokens": 900}
        if round_ < max_rounds:
            body["tools"], body["tool_choice"] = tools, "auto"
        if s.AI_PROVIDER == "gemini":
            body["reasoning_effort"] = "none" if "2.5-flash" in s.AI_MODEL else "low"
        t0 = time.monotonic()
        status, usage = "error", {}
        try:
            r = httpx.post(s.AI_BASE_URL.rstrip("/") + "/chat/completions", headers={"Authorization": f"Bearer {_keys().next()}"}, json=body, timeout=s.AI_TIMEOUT_SECONDS)
            if r.status_code >= 400:
                raise AIUnavailable(f"provider {r.status_code}")
            d = r.json()
            usage = d.get("usage") or {}
            msg = d["choices"][0]["message"]
            status = "ok"
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise AIUnavailable(type(e).__name__) from None
        finally:
            try:
                with session_scope() as db:
                    db.add(AICall(workspace_id=workspace_id, request_id=request_id, purpose=purpose, provider=s.AI_PROVIDER, model=s.AI_MODEL, status=status,
                                  latency_ms=int((time.monotonic() - t0) * 1000), prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens")))
            except Exception:
                log.warning("ai call log failed")
        calls = msg.get("tool_calls") or []
        if not calls:
            content = msg.get("content") or ""
            try:
                parsed = _parse_json(content)
            except ValueError:
                parsed = {"answer": content.strip(), "citations": []}
            return parsed, {"model": s.AI_MODEL, "provider": s.AI_PROVIDER, "latency_ms": int((time.monotonic() - t_all) * 1000)}, trace
        messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls", "extra_content")} | {"role": "assistant"})
        for c in calls[:3]:
            name = (c.get("function") or {}).get("name", "")
            result = run_tool(name)
            trace.append({"tool": name, "source": "PayPal Agent Toolkit", "result": result})
            messages.append({"role": "tool", "tool_call_id": c.get("id", name), "content": json.dumps(result, default=str)})
    raise AIUnavailable("tool loop did not finish")
