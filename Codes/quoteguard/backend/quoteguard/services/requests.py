"""Purchase requests and immutable confirmed requirement versions."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit, jobs, timeutil
from ..ai import requirements_parser
from ..domain.requirements import RequirementSpec
from ..errors import AppError
from ..models import Document, PurchaseRequest, RequestVersion
from .context import Actor, get_request

TERMINAL = ("canceled", "superseded")


def create(db: Session, actor: Actor, text: str, title: str | None = None, tz: str | None = None, lab_scenario: str | None = None) -> PurchaseRequest:
    actor.require("requester", "admin")
    text = (text or "").strip()
    if not (10 <= len(text) <= 4000):
        raise AppError("INVALID_REQUEST_TEXT", "Describe the purchase in 10–4000 characters.", 422)
    from ..config import get_settings

    tz = tz or get_settings().DEFAULT_TIMEZONE
    now = timeutil.now()
    req = PurchaseRequest(workspace_id=actor.workspace_id, created_by=actor.user_id, title=(title or text.split(".")[0])[:200], original_text=text,
                          status="draft", timezone=tz, lab_scenario=lab_scenario, created_at=now, updated_at=now)
    db.add(req)
    db.flush()
    parsed = requirements_parser.parse(text, tz, now, workspace_id=actor.workspace_id, request_id=req.id)
    spec, problems = requirements_parser.to_spec(parsed["raw"], tz, now)
    req.draft = {"raw": parsed["raw"], "method": parsed["method"], "model": parsed["model"], "prompt_version": parsed["prompt_version"],
                 "spec": spec.jsonable() if spec else None, "problems": problems}
    audit.record(db, "request.created", workspace_id=actor.workspace_id, actor_id=actor.user_id, principal_id=actor.principal_id, object_type="purchase_request", object_id=req.id, request_id=req.id,
                 meta={"parse_method": parsed["method"], "model": parsed["model"]})
    audit.event(db, workspace_id=actor.workspace_id, request_id=req.id, stage="request", status="info", title="Request drafted from plain language",
                detail=f"Parsed with {'model ' + parsed['model'] if parsed['model'] else 'deterministic rules'}; awaiting human confirmation.", actor=actor.label, tool="requirements_parser")
    return req


def confirm(db: Session, actor: Actor, request_id, spec_in: dict, *, source: str = "initial", note: str | None = None, expected_version: int | None = None) -> RequestVersion:
    """Create an immutable requirement version. Any change after approval invalidates it."""
    actor.require("requester", "admin")
    req = get_request(db, actor, request_id, for_update=True)
    if req.status in TERMINAL:
        raise AppError("REQUEST_CLOSED", "This request is closed.", 409)
    current = db.get(RequestVersion, req.current_version_id) if req.current_version_id else None
    if expected_version is not None and (current.version if current else 0) != expected_version:
        raise AppError("STALE_VERSION", "The requirements changed since you loaded them. Reload and try again.", 409)
    try:
        spec = RequirementSpec.model_validate({**spec_in, "timezone": req.timezone})
    except Exception as e:
        raise AppError("INVALID_REQUIREMENTS", f"Requirements are incomplete: {e}", 422) from None
    if spec.deadline_days is not None and spec.deadline_date is None:
        spec.deadline_date = timeutil.add_days_local(req.created_at, spec.deadline_days, req.timezone)
    next_v = (db.execute(select(func.max(RequestVersion.version)).where(RequestVersion.request_id == req.id)).scalar() or 0) + 1
    rv = RequestVersion(request_id=req.id, version=next_v, requirements=spec.jsonable(), budget_amount=spec.budget_amount, currency=spec.currency, quantity=spec.quantity,
                        deadline_date=spec.deadline_date, deadline_at=timeutil.end_of_local_day(spec.deadline_date, req.timezone) if spec.deadline_date else None,
                        source=source, change_note=note, confirmed_by=actor.user_id, confirmed_at=timeutil.now())
    db.add(rv)
    db.flush()
    req.current_version_id = rv.id
    req.updated_at = timeutil.now()
    if current is not None:
        from .approvals import invalidate_for_request

        invalidate_for_request(db, req, f"Requirements changed to version {next_v}", actor=actor)
    req.status = "analyzing"
    audit.record(db, "request.confirmed", workspace_id=actor.workspace_id, actor_id=actor.user_id, principal_id=actor.principal_id, object_type="request_version", object_id=rv.id, request_id=req.id,
                 meta={"version": next_v, "source": source, "budget": str(spec.budget_amount), "currency": spec.currency, "deadline": spec.deadline_date.isoformat() if spec.deadline_date else None})
    audit.event(db, workspace_id=actor.workspace_id, request_id=req.id, stage="request", status="done", title=f"Requirements v{next_v} confirmed",
                detail=f"{spec.quantity} × {spec.item}; budget {spec.currency} {spec.budget_amount}; deliver by {spec.deadline_date.isoformat() if spec.deadline_date else 'no deadline'}." + (f" Note: {note}" if note else ""),
                refs={"request_version": next_v}, actor=actor.label)
    has_docs = db.execute(select(func.count()).select_from(Document).where(Document.request_id == req.id)).scalar()
    if has_docs:
        jobs.enqueue(db, "analyze_request", {"request_id": req.id}, dedupe_key=f"analyze:{req.id}", delay_seconds=1)
    return rv


def cancel(db: Session, actor: Actor, request_id, reason: str) -> PurchaseRequest:
    actor.require("requester", "admin")
    req = get_request(db, actor, request_id, for_update=True)
    if req.status in TERMINAL:
        return req
    from .approvals import invalidate_for_request

    invalidate_for_request(db, req, f"Request canceled: {reason}", actor=actor)
    req.status = "canceled"
    req.updated_at = timeutil.now()
    audit.record(db, "request.canceled", workspace_id=actor.workspace_id, actor_id=actor.user_id, object_type="purchase_request", object_id=req.id, request_id=req.id, meta={"reason": reason})
    audit.event(db, workspace_id=actor.workspace_id, request_id=req.id, stage="request", status="info", title="Request canceled", detail=reason, actor=actor.label)
    return req


def current_spec(db: Session, req: PurchaseRequest) -> tuple[RequestVersion | None, RequirementSpec | None]:
    if not req.current_version_id:
        return None, None
    rv = db.get(RequestVersion, req.current_version_id)
    return rv, RequirementSpec.model_validate(rv.requirements)
