from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ... import audit, timeutil
from ...config import get_settings
from ...errors import AppError
from ...models import AuthSession, Membership, User, Workspace
from ...security import DUMMY_HASH, new_token, token_hash, verify_password
from ...services import demo
from ..deps import CSRF_COOKIE, SESSION_COOKIE, Ctx, client_ip, get_db, optional_session, rate_limit, require_ctx

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=200)


def _set_cookies(resp: Response, token: str, csrf: str, max_age: int) -> None:
    secure = get_settings().cookie_secure
    resp.set_cookie(SESSION_COOKIE, token, max_age=max_age, httponly=True, secure=secure, samesite="lax", path="/")
    resp.set_cookie(CSRF_COOKIE, csrf, max_age=max_age, httponly=False, secure=secure, samesite="lax", path="/")


def me_payload(db: Session, sess: AuthSession) -> dict:
    principal = db.get(User, sess.principal_user_id)
    acting = db.get(User, sess.acting_user_id)
    ws = db.get(Workspace, sess.workspace_id) if sess.workspace_id else None
    m = db.execute(select(Membership).where(Membership.workspace_id == sess.workspace_id, Membership.user_id == sess.acting_user_id)).scalar_one_or_none() if ws else None
    personas = []
    if ws and ws.is_demo:
        for mm in db.execute(select(Membership).where(Membership.workspace_id == ws.id)).scalars():
            personas.append({"user_id": str(mm.user_id), "name": mm.user.display_name, "roles": mm.roles, "is_persona": mm.is_demo_persona, "active": mm.user_id == sess.acting_user_id})
    wss = db.execute(select(Workspace).join(Membership, Membership.workspace_id == Workspace.id).where(Membership.user_id == principal.id, Workspace.archived_at.is_(None))
                     .order_by(Workspace.created_at.desc()).limit(8)).scalars().all()
    return {
        "principal": {"id": str(principal.id), "name": principal.display_name, "username": principal.username, "is_demo_account": principal.is_demo_account},
        "acting": {"id": str(acting.id), "name": acting.display_name, "is_persona": acting.is_persona},
        "workspace": {"id": str(ws.id), "name": ws.name, "is_demo": ws.is_demo, "self_approval_allowed": ws.self_approval_allowed} if ws else None,
        "roles": m.roles if m else [],
        "personas": personas,
        "workspaces": [{"id": str(w.id), "name": w.name, "is_demo": w.is_demo} for w in wss],
        "csrf_token": sess.csrf_token,
        "session_expires_at": sess.expires_at.isoformat(),
    }


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    rate_limit(db, f"login:{ip}", 20, 300)
    rate_limit(db, f"login-user:{body.username.lower()}", 10, 300)
    user = db.execute(select(User).where(or_(User.username == body.username, User.email == body.username.lower()))).scalar_one_or_none()
    if user is None or not user.password_hash:
        verify_password(body.password, DUMMY_HASH)
        raise AppError("INVALID_CREDENTIALS", "Username or password is incorrect.", 401)
    if not verify_password(body.password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Username or password is incorrect.", 401)
    s = get_settings()
    if user.is_demo_account:
        # Every demo sign-in gets its own isolated workspace: no shared transaction state.
        ws = demo.provision_workspace(db, user)
        ws_id = ws.id
    else:
        m = db.execute(select(Membership).join(Workspace).where(Membership.user_id == user.id, Workspace.archived_at.is_(None)).order_by(Workspace.created_at)).scalars().first()
        ws_id = m.workspace_id if m else None
    token, csrf = new_token(), new_token()
    sess = AuthSession(token_hash=token_hash(token, s.SESSION_SECRET), principal_user_id=user.id, acting_user_id=user.id, workspace_id=ws_id, csrf_token=csrf,
                       expires_at=timeutil.now() + timedelta(hours=s.SESSION_TTL_HOURS), created_at=timeutil.now(), ip=ip, user_agent=(request.headers.get("user-agent") or "")[:300])
    db.add(sess)
    db.flush()
    audit.record(db, "auth.login", workspace_id=ws_id, actor_id=user.id, object_type="session", object_id=sess.id, meta={"demo": user.is_demo_account})
    _set_cookies(response, token, csrf, s.SESSION_TTL_HOURS * 3600)
    return me_payload(db, sess)


@router.post("/logout")
def logout(response: Response, sess: AuthSession | None = Depends(optional_session), db: Session = Depends(get_db)):
    if sess is not None:
        db.get(AuthSession, sess.id).revoked_at = timeutil.now()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(sess: AuthSession | None = Depends(optional_session), db: Session = Depends(get_db)):
    if sess is None:
        raise AppError("UNAUTHENTICATED", "Please sign in.", 401)
    return me_payload(db, sess)


@router.post("/renew")
def renew(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    sess = db.get(AuthSession, ctx.session.id)
    sess.expires_at = timeutil.now() + timedelta(hours=get_settings().SESSION_TTL_HOURS)
    return me_payload(db, sess)


class SwitchIn(BaseModel):
    user_id: str


@router.post("/switch-persona")
def switch_persona(body: SwitchIn, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    """Labelled role switch, limited to demo workspaces and their seeded personas."""
    ws = db.get(Workspace, ctx.session.workspace_id)
    if not ws.is_demo:
        raise AppError("ROLE_SWITCH_DISABLED", "Role switching is only available in demo workspaces.", 403)
    target = db.execute(select(Membership).where(Membership.workspace_id == ws.id, Membership.user_id == body.user_id)).scalar_one_or_none()
    if target is None or not (target.is_demo_persona or str(target.user_id) == str(ctx.session.principal_user_id)):
        raise AppError("ROLE_SWITCH_DENIED", "You can only switch to this workspace's demo personas.", 403)
    sess = db.get(AuthSession, ctx.session.id)
    sess.acting_user_id = target.user_id
    audit.record(db, "auth.persona_switch", workspace_id=ws.id, actor_id=target.user_id, principal_id=sess.principal_user_id, meta={"to": target.user.display_name})
    return me_payload(db, sess)


class WorkspaceIn(BaseModel):
    workspace_id: str


@router.post("/workspace")
def switch_workspace(body: WorkspaceIn, ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    m = db.execute(select(Membership).where(Membership.workspace_id == body.workspace_id, Membership.user_id == ctx.session.principal_user_id)).scalar_one_or_none()
    if m is None:
        raise AppError("WORKSPACE_ACCESS_DENIED", "You are not a member of this workspace.", 403)
    sess = db.get(AuthSession, ctx.session.id)
    sess.workspace_id, sess.acting_user_id = m.workspace_id, sess.principal_user_id
    return me_payload(db, sess)


@router.post("/new-demo-workspace")
def new_demo_workspace(ctx: Ctx = Depends(require_ctx), db: Session = Depends(get_db)):
    if not ctx.principal.is_demo_account:
        raise AppError("FORBIDDEN", "Only demo accounts can create demo workspaces.", 403)
    rate_limit(db, f"newws:{ctx.principal.id}", 10, 3600)
    ws = demo.provision_workspace(db, ctx.principal)
    sess = db.get(AuthSession, ctx.session.id)
    sess.workspace_id, sess.acting_user_id = ws.id, sess.principal_user_id
    return me_payload(db, sess)
