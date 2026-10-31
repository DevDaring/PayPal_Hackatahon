"""Request-scoped dependencies: DB session, authenticated actor, CSRF and rate limits."""

from __future__ import annotations

import hmac
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .. import timeutil
from ..config import get_settings
from ..db import SessionLocal
from ..errors import AppError
from ..models import AuthSession, RateLimit, User
from ..security import token_hash
from ..services.context import Actor, load_actor

SESSION_COOKIE = "qg_session"
CSRF_COOKIE = "qg_csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@dataclass
class Ctx:
    session: AuthSession
    actor: Actor
    principal: User


def client_ip(request: Request) -> str:
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


def rate_limit(db: Session, key: str, limit: int, window_seconds: int) -> None:
    now = timeutil.now()
    start = now - timedelta(seconds=now.timestamp() % window_seconds)
    stmt = insert(RateLimit).values(key=key, window_start=start, count=1).on_conflict_do_update(index_elements=[RateLimit.key, RateLimit.window_start], set_={"count": RateLimit.count + 1}).returning(RateLimit.count)
    count = db.execute(stmt).scalar_one()
    db.commit()
    if count > limit:
        raise AppError("RATE_LIMITED", "Too many attempts. Please wait a moment and try again.", 429)


def _load_session(request: Request, db: Session) -> AuthSession | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    sess = db.execute(select(AuthSession).where(AuthSession.token_hash == token_hash(token, get_settings().SESSION_SECRET))).scalar_one_or_none()
    if sess is None or sess.revoked_at is not None or sess.expires_at <= timeutil.now():
        return None
    return sess


def require_ctx(request: Request, db: Session = Depends(get_db)) -> Ctx:
    sess = _load_session(request, db)
    if sess is None:
        raise AppError("UNAUTHENTICATED", "Please sign in.", 401)
    if request.method not in SAFE_METHODS:
        sent = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(sent, sess.csrf_token):
            raise AppError("CSRF_FAILED", "Security token missing or invalid. Reload the page.", 403)
        origin = request.headers.get("origin")
        if origin and origin not in get_settings().cors_origins and origin != get_settings().APP_BASE_URL:
            raise AppError("ORIGIN_REJECTED", "Request origin is not allowed.", 403)
    if sess.workspace_id is None:
        raise AppError("NO_WORKSPACE", "No workspace is selected.", 403)
    now = timeutil.now()
    if sess.last_seen_at is None or (now - sess.last_seen_at) > timedelta(minutes=2):
        sess.last_seen_at = now
    actor = load_actor(db, sess.acting_user_id, sess.principal_user_id, sess.workspace_id)
    principal = db.get(User, sess.principal_user_id)
    db.commit()  # never hold the session row across slow work in the handler
    return Ctx(sess, actor, principal)


def optional_session(request: Request, db: Session = Depends(get_db)) -> AuthSession | None:
    return _load_session(request, db)
