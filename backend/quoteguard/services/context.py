"""The authenticated actor and server-side authorization helpers used by every service."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import AppError, forbidden, not_found
from ..models import Membership, PurchaseRequest, User, Workspace

ROLES = ("requester", "approver", "admin")


@dataclass
class Actor:
    user_id: uuid.UUID
    principal_id: uuid.UUID
    workspace_id: uuid.UUID
    roles: set[str] = field(default_factory=set)
    display_name: str = ""
    is_demo_workspace: bool = False

    def require(self, *roles: str) -> None:
        if not self.roles.intersection(roles):
            raise forbidden(f"This action requires the {' or '.join(roles)} role in this workspace.")

    @property
    def label(self) -> str:
        return self.display_name or str(self.user_id)


def load_actor(db: Session, acting_user_id: uuid.UUID, principal_id: uuid.UUID, workspace_id: uuid.UUID) -> Actor:
    m = db.execute(select(Membership).where(Membership.workspace_id == workspace_id, Membership.user_id == acting_user_id)).scalar_one_or_none()
    ws = db.get(Workspace, workspace_id)
    if m is None or ws is None or ws.archived_at is not None:
        raise AppError("WORKSPACE_ACCESS_DENIED", "You are not a member of this workspace.", 403)
    user = db.get(User, acting_user_id)
    return Actor(acting_user_id, principal_id, workspace_id, set(m.roles), user.display_name if user else "", ws.is_demo)


def get_request(db: Session, actor: Actor, request_id, *, for_update: bool = False) -> PurchaseRequest:
    """Every object lookup is scoped by workspace; another workspace's ID reads as not found."""
    try:
        rid = uuid.UUID(str(request_id))
    except ValueError:
        raise not_found("Purchase request") from None
    q = select(PurchaseRequest).where(PurchaseRequest.id == rid, PurchaseRequest.workspace_id == actor.workspace_id)
    if for_update:
        q = q.with_for_update()
    req = db.execute(q).scalar_one_or_none()
    if req is None:
        raise not_found("Purchase request")
    return req


def parse_uuid(value, what: str = "Resource") -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise not_found(what) from None
