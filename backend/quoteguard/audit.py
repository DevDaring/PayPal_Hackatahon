"""Append-only audit log with a per-workspace hash chain, plus workflow event helpers."""

from __future__ import annotations

import contextvars
import json
import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from . import timeutil
from .models import AuditEvent, WorkflowEvent
from .security import sha256_text

correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)

_SECRET_KEYS = {"password", "secret", "token", "access_token", "authorization", "client_secret", "api_key"}


def redact(value):
    if isinstance(value, dict):
        return {k: ("[redacted]" if k.lower() in _SECRET_KEYS else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def _jsonable(value):
    return json.loads(json.dumps(value, default=str))


def record(
    db: Session,
    action: str,
    *,
    workspace_id=None,
    actor_id=None,
    principal_id=None,
    object_type: str | None = None,
    object_id=None,
    request_id=None,
    meta: dict | None = None,
) -> AuditEvent:
    meta = _jsonable(redact(meta or {}))
    if workspace_id is not None:
        # Serialise chain appends per workspace for the rest of this transaction.
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"audit:{workspace_id}"})
    prev = db.execute(
        select(AuditEvent.hash).where(AuditEvent.workspace_id == workspace_id).order_by(AuditEvent.id.desc()).limit(1)
    ).scalar_one_or_none()
    at = timeutil.now()
    payload = json.dumps(
        {
            "prev": prev,
            "ws": str(workspace_id) if workspace_id else None,
            "actor": str(actor_id) if actor_id else None,
            "action": action,
            "object": [object_type, str(object_id) if object_id else None],
            "meta": meta,
            "at": at.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    ev = AuditEvent(
        workspace_id=workspace_id,
        actor_user_id=actor_id,
        principal_user_id=principal_id or actor_id,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id else None,
        request_id=request_id,
        meta=meta,
        correlation_id=correlation_id.get(),
        prev_hash=prev,
        hash=sha256_text(payload),
        created_at=at,
    )
    db.add(ev)
    return ev


def verify_chain(db: Session, workspace_id) -> dict:
    rows = db.execute(select(AuditEvent).where(AuditEvent.workspace_id == workspace_id).order_by(AuditEvent.id)).scalars().all()
    prev = None
    for ev in rows:
        payload = json.dumps(
            {
                "prev": prev,
                "ws": str(ev.workspace_id) if ev.workspace_id else None,
                "actor": str(ev.actor_user_id) if ev.actor_user_id else None,
                "action": ev.action,
                "object": [ev.object_type, ev.object_id],
                "meta": ev.meta,
                "at": ev.created_at.isoformat(),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        if ev.prev_hash != prev or sha256_text(payload) != ev.hash:
            return {"valid": False, "broken_at": ev.id, "checked": len(rows)}
        prev = ev.hash
    return {"valid": True, "checked": len(rows), "head": prev}


def event(
    db: Session,
    *,
    workspace_id,
    request_id,
    stage: str,
    status: str,
    title: str,
    detail: str | None = None,
    refs: dict | None = None,
    actor: str = "system",
    tool: str | None = None,
    run_id: uuid.UUID | None = None,
) -> WorkflowEvent:
    ev = WorkflowEvent(
        workspace_id=workspace_id,
        request_id=request_id,
        run_id=run_id,
        stage=stage,
        status=status,
        title=title[:200],
        detail=detail,
        refs=_jsonable(refs) if refs else None,
        actor=actor,
        tool=tool,
        created_at=timeutil.now(),
    )
    db.add(ev)
    return ev
