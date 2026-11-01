"""PostgreSQL schema. PostgreSQL is authoritative for every permission and payment state.

Request, approval and payment states are deliberately separate enums (see docs/PAYMENTS.md).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

MONEY = Numeric(14, 2)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)


def fk(target: str, nullable: bool = False, ondelete: str | None = None, index: bool = True):
    return mapped_column(UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable, index=index)


def created():
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


REQUEST_STATES = ("draft", "analyzing", "needs_clarification", "ready_for_review", "approved", "superseded", "canceled")
APPROVAL_STATES = ("active", "consumed_for_execution", "expired", "revoked", "invalidated")
PAYMENT_STATES = ("not_started", "order_creating", "awaiting_payer", "capture_pending", "reconciling", "completed", "canceled", "failed")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


# ---------------------------------------------------------------- identity ----------
class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = pk()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    username: Mapped[str | None] = mapped_column(String(80), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str | None] = mapped_column(String(300))
    is_system_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo_account: Mapped[bool] = mapped_column(Boolean, default=False)
    is_persona: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = created()


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(160))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    self_approval_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created()


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = fk("workspaces.id", ondelete="CASCADE")
    user_id: Mapped[uuid.UUID] = fk("users.id", ondelete="CASCADE")
    roles: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list)
    is_demo_persona: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = created()
    user: Mapped[User] = relationship(lazy="joined")


class AuthSession(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = pk()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    principal_user_id: Mapped[uuid.UUID] = fk("users.id", ondelete="CASCADE")
    acting_user_id: Mapped[uuid.UUID] = fk("users.id", ondelete="CASCADE")
    workspace_id: Mapped[uuid.UUID | None] = fk("workspaces.id", nullable=True, ondelete="SET NULL")
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = created()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))


class RateLimit(Base):
    __tablename__ = "rate_limits"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


# ------------------------------------------------------------- suppliers ------------
class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("workspace_id", "normalized_name"),)
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = fk("workspaces.id", ondelete="CASCADE")
    name: Mapped[str] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created()


class MerchantBinding(Base):
    """Server-side mapping from a supplier record to a configured PayPal merchant.

    Created only by an admin. Never derived from a document; holds no API secrets.
    """

    __tablename__ = "merchant_bindings"
    __table_args__ = (
        Index("uq_active_binding_per_supplier", "supplier_id", unique=True, postgresql_where=text("status = 'active'")),
        CheckConstraint("environment = 'sandbox'", name="ck_binding_sandbox_only"),
    )
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = fk("workspaces.id", ondelete="CASCADE")
    supplier_id: Mapped[uuid.UUID] = fk("suppliers.id", ondelete="CASCADE")
    provider: Mapped[str] = mapped_column(String(30), default="paypal")
    environment: Mapped[str] = mapped_column(String(20), default="sandbox")
    adapter: Mapped[str] = mapped_column(String(20))  # sandbox | simulated
    merchant_id: Mapped[str] = mapped_column(String(64))
    display_label: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="active")
    version: Mapped[int] = mapped_column(Integer, default=1)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = created()


# -------------------------------------------------------------- requests ------------
class PurchaseRequest(Base):
    __tablename__ = "purchase_requests"
    __table_args__ = (CheckConstraint(_in("status", REQUEST_STATES), name="ck_request_status"),)
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = fk("workspaces.id", ondelete="CASCADE")
    created_by: Mapped[uuid.UUID] = fk("users.id")
    title: Mapped[str] = mapped_column(String(200))
    original_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    timezone: Mapped[str] = mapped_column(String(64))
    draft: Mapped[dict | None] = mapped_column(JSONB)  # unconfirmed parse, never used for eligibility
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("request_versions.id", use_alter=True, name="fk_request_current_version"))
    lab_scenario: Mapped[str | None] = mapped_column(String(60))
    explanation: Mapped[dict | None] = mapped_column(JSONB)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lock_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = created()
    __mapper_args__ = {"version_id_col": lock_version}


class RequestVersion(Base):
    """Immutable confirmed requirements. Changes create a new row."""

    __tablename__ = "request_versions"
    __table_args__ = (UniqueConstraint("request_id", "version"),)
    id: Mapped[uuid.UUID] = pk()
    request_id: Mapped[uuid.UUID] = fk("purchase_requests.id", ondelete="CASCADE")
    version: Mapped[int] = mapped_column(Integer)
    requirements: Mapped[dict] = mapped_column(JSONB)
    budget_amount: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String(3))
    quantity: Mapped[int] = mapped_column(Integer)
    deadline_date: Mapped[date | None] = mapped_column(Date)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(30))  # initial | whatif | edit
    change_note: Mapped[str | None] = mapped_column(Text)
    confirmed_by: Mapped[uuid.UUID] = fk("users.id")
    confirmed_at: Mapped[datetime] = created()


# ------------------------------------------------------------- documents ------------
class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("request_id", "sha256"),)
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = fk("workspaces.id", ondelete="CASCADE")
    request_id: Mapped[uuid.UUID] = fk("purchase_requests.id", ondelete="CASCADE")
    supplier_id: Mapped[uuid.UUID | None] = fk("suppliers.id", nullable=True)
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    text_sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    mime: Mapped[str] = mapped_column(String(100))
    page_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="uploaded")  # uploaded|extracting|extracted|failed|needs_ocr
    extraction_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(Text)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    supplier_confirmed_by: Mapped[str | None] = mapped_column(String(120))  # set only for controlled sample fixtures
    suspicious: Mapped[list | None] = mapped_column(JSONB)
    forensics: Mapped[dict | None] = mapped_column(JSONB)  # structural PDF forensics from the isolated parser
    uploaded_by: Mapped[uuid.UUID] = fk("users.id")
    created_at: Mapped[datetime] = created()


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number"),)
    id: Mapped[uuid.UUID] = pk()
    document_id: Mapped[uuid.UUID] = fk("documents.id", ondelete="CASCADE")
    page_number: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(64))
    width: Mapped[float] = mapped_column(Numeric(10, 2))
    height: Mapped[float] = mapped_column(Numeric(10, 2))
    words: Mapped[list] = mapped_column(JSONB)  # [[text, x0, top, x1, bottom], ...]
    extraction_method: Mapped[str] = mapped_column(String(20))  # text | ocr
    quality: Mapped[str] = mapped_column(String(20))  # good | low | empty


# ---------------------------------------------------------------- quotes ------------
class Quote(Base):
    __tablename__ = "quotes"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = fk("workspaces.id", ondelete="CASCADE")
    request_id: Mapped[uuid.UUID] = fk("purchase_requests.id", ondelete="CASCADE")
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), unique=True)
    supplier_id: Mapped[uuid.UUID | None] = fk("suppliers.id", nullable=True)
    # A name printed in a PDF is only a suggestion. Checkout needs a human-confirmed link.
    supplier_link: Mapped[str] = mapped_column(String(20), default="none")  # none | suggested | confirmed
    supplier_confirmed_by: Mapped[str | None] = mapped_column(String(120))
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("quote_versions.id", use_alter=True, name="fk_quote_current_version"))
    created_at: Mapped[datetime] = created()


class QuoteVersion(Base):
    __tablename__ = "quote_versions"
    __table_args__ = (UniqueConstraint("quote_id", "version"),)
    id: Mapped[uuid.UUID] = pk()
    quote_id: Mapped[uuid.UUID] = fk("quotes.id", ondelete="CASCADE")
    version: Mapped[int] = mapped_column(Integer)
    supplier_name: Mapped[str | None] = mapped_column(String(200))
    currency: Mapped[str | None] = mapped_column(String(3))
    currency_status: Mapped[str] = mapped_column(String(20))  # explicit | inferred | unknown
    quantity: Mapped[int | None] = mapped_column(Integer)
    unit_price: Mapped[Decimal | None] = mapped_column(MONEY)
    subtotal: Mapped[Decimal | None] = mapped_column(MONEY)
    shipping: Mapped[Decimal | None] = mapped_column(MONEY)
    tax: Mapped[Decimal | None] = mapped_column(MONEY)
    discount: Mapped[Decimal | None] = mapped_column(MONEY)
    stated_total: Mapped[Decimal | None] = mapped_column(MONEY)
    computed_total: Mapped[Decimal | None] = mapped_column(MONEY)
    arithmetic_status: Mapped[str] = mapped_column(String(30))  # consistent | contradictory | incomplete
    delivery_days: Mapped[int | None] = mapped_column(Integer)
    delivery_text: Mapped[str | None] = mapped_column(Text)
    issue_date: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    product_description: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)  # {"connector": "USB-C", ...}
    shipping_terms: Mapped[str | None] = mapped_column(Text)
    pricing_terms: Mapped[str | None] = mapped_column(Text)
    issues: Mapped[list] = mapped_column(JSONB, default=list)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    extraction_method: Mapped[str] = mapped_column(String(30))  # llm | rules | correction
    model: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(30))  # extracted | correction | supplier_revision
    correction: Mapped[dict | None] = mapped_column(JSONB)
    parent_version_id: Mapped[uuid.UUID | None] = fk("quote_versions.id", nullable=True)
    created_by: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    created_at: Mapped[datetime] = created()


class QuoteItem(Base):
    __tablename__ = "quote_items"
    id: Mapped[uuid.UUID] = pk()
    quote_version_id: Mapped[uuid.UUID] = fk("quote_versions.id", ondelete="CASCADE")
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[int | None] = mapped_column(Integer)
    unit_price: Mapped[Decimal | None] = mapped_column(MONEY)
    line_total: Mapped[Decimal | None] = mapped_column(MONEY)


class EvidenceLink(Base):
    __tablename__ = "evidence_links"
    id: Mapped[uuid.UUID] = pk()
    quote_version_id: Mapped[uuid.UUID] = fk("quote_versions.id", ondelete="CASCADE")
    field: Mapped[str] = mapped_column(String(60))
    document_id: Mapped[uuid.UUID] = fk("documents.id", ondelete="CASCADE")
    document_sha256: Mapped[str] = mapped_column(String(64))
    quote_version: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer)
    source_text: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(30))
    location_status: Mapped[str] = mapped_column(String(20))  # bbox | text_only | not_found | correction
    bbox: Mapped[list | None] = mapped_column(JSONB)  # [[x0, top, x1, bottom], ...] in PDF points


# --------------------------------------------------------- policy & evals -----------
class PolicyVersion(Base):
    __tablename__ = "policy_versions"
    __table_args__ = (UniqueConstraint("name", "version"),)
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer)
    rules: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created()


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (UniqueConstraint("request_version_id", "quote_version_id", "policy_version_id"),)
    id: Mapped[uuid.UUID] = pk()
    request_version_id: Mapped[uuid.UUID] = fk("request_versions.id", ondelete="CASCADE")
    quote_version_id: Mapped[uuid.UUID] = fk("quote_versions.id", ondelete="CASCADE")
    policy_version_id: Mapped[uuid.UUID] = fk("policy_versions.id")
    checks: Mapped[list] = mapped_column(JSONB)
    mandatory_status: Mapped[str] = mapped_column(String(10))  # pass | fail | unknown
    verified_total: Mapped[Decimal | None] = mapped_column(MONEY)
    checkout_available: Mapped[bool] = mapped_column(Boolean)
    payment_eligible: Mapped[bool] = mapped_column(Boolean)
    compliant_rank: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = created()


# -------------------------------------------------------------- workflow ------------
class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = fk("workspaces.id", ondelete="CASCADE")
    request_id: Mapped[uuid.UUID] = fk("purchase_requests.id", ondelete="CASCADE")
    request_version_id: Mapped[uuid.UUID | None] = fk("request_versions.id", nullable=True)
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    current_node: Mapped[str | None] = mapped_column(String(60))
    completed_nodes: Mapped[list] = mapped_column(JSONB, default=list)
    ai_calls: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created()


class WorkflowEvent(Base):
    """A persisted, concise application event. Never model chain-of-thought."""

    __tablename__ = "workflow_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[uuid.UUID] = fk("workspaces.id", ondelete="CASCADE")
    request_id: Mapped[uuid.UUID] = fk("purchase_requests.id", ondelete="CASCADE")
    run_id: Mapped[uuid.UUID | None] = fk("workflow_runs.id", nullable=True, ondelete="CASCADE")
    stage: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20))  # started | done | warning | blocked | failed | info
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str | None] = mapped_column(Text)
    refs: Mapped[dict | None] = mapped_column(JSONB)
    actor: Mapped[str] = mapped_column(String(120))
    tool: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = created()


# -------------------------------------------------------- approval & pay ------------
class PurchaseSnapshot(Base):
    __tablename__ = "purchase_snapshots"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = fk("workspaces.id", ondelete="CASCADE")
    request_id: Mapped[uuid.UUID] = fk("purchase_requests.id", ondelete="CASCADE")
    request_version_id: Mapped[uuid.UUID] = fk("request_versions.id")
    quote_version_id: Mapped[uuid.UUID] = fk("quote_versions.id")
    merchant_binding_id: Mapped[uuid.UUID] = fk("merchant_bindings.id")
    canonical: Mapped[dict] = mapped_column(JSONB)
    canonical_json: Mapped[str] = mapped_column(Text)
    terms_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), index=True)
    total: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String(3))
    created_at: Mapped[datetime] = created()


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint(_in("status", APPROVAL_STATES), name="ck_approval_status"),
        # At most one live approval per request at any time.
        Index("uq_live_approval_per_request", "request_id", unique=True, postgresql_where=text("status IN ('active','consumed_for_execution')")),
    )
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = fk("workspaces.id", ondelete="CASCADE")
    request_id: Mapped[uuid.UUID] = fk("purchase_requests.id", ondelete="CASCADE")
    snapshot_id: Mapped[uuid.UUID] = fk("purchase_snapshots.id")
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="active")
    requested_by: Mapped[uuid.UUID] = fk("users.id")
    approver_id: Mapped[uuid.UUID] = fk("users.id")
    approver_principal_id: Mapped[uuid.UUID] = fk("users.id")
    note: Mapped[str | None] = mapped_column(Text)
    signed_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[str | None] = mapped_column(Text)
    end_details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created()


class ApprovalDecision(Base):
    """Rejections (and approvals) as decisions, separate from the approval lifecycle."""

    __tablename__ = "approval_decisions"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = fk("workspaces.id", ondelete="CASCADE")
    request_id: Mapped[uuid.UUID] = fk("purchase_requests.id", ondelete="CASCADE")
    snapshot_id: Mapped[uuid.UUID | None] = fk("purchase_snapshots.id", nullable=True)
    quote_id: Mapped[uuid.UUID | None] = fk("quotes.id", nullable=True)
    decision: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[uuid.UUID] = fk("users.id")
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created()


class PaymentOperation(Base):
    __tablename__ = "payment_operations"
    __table_args__ = (
        CheckConstraint(_in("state", PAYMENT_STATES), name="ck_payment_state"),
        # One checkout operation per approval: duplicate clicks resolve to the same row.
        UniqueConstraint("approval_id", "kind", name="uq_operation_per_approval"),
    )
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = fk("workspaces.id", ondelete="CASCADE")
    request_id: Mapped[uuid.UUID] = fk("purchase_requests.id", ondelete="CASCADE")
    approval_id: Mapped[uuid.UUID] = fk("approvals.id")
    snapshot_id: Mapped[uuid.UUID] = fk("purchase_snapshots.id")
    kind: Mapped[str] = mapped_column(String(20), default="checkout")
    business_key: Mapped[str] = mapped_column(String(120), unique=True)
    adapter: Mapped[str] = mapped_column(String(20))  # sandbox | simulated
    state: Mapped[str] = mapped_column(String(20), default="not_started")
    amount: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String(3))
    merchant_id: Mapped[str] = mapped_column(String(64))
    order_request_id: Mapped[str] = mapped_column(String(64), unique=True)
    capture_request_id: Mapped[str] = mapped_column(String(64), unique=True)
    provider_order_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    provider_order_status: Mapped[str | None] = mapped_column(String(40))
    provider_capture_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    provider_capture_status: Mapped[str | None] = mapped_column(String(40))
    captured_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    payer_reference: Mapped[str | None] = mapped_column(String(120))  # payer id only; no PII
    last_error_code: Mapped[str | None] = mapped_column(String(60))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    fault_injection: Mapped[str | None] = mapped_column(String(40))
    reconcile_attempts: Mapped[int] = mapped_column(Integer, default=0)
    lock_version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[uuid.UUID] = fk("users.id")
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = created()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __mapper_args__ = {"version_id_col": lock_version}


class ProviderTransaction(Base):
    """Every provider call we made, with redacted outcome. Never deleted by demo reset."""

    __tablename__ = "provider_transactions"
    id: Mapped[uuid.UUID] = pk()
    operation_id: Mapped[uuid.UUID] = fk("payment_operations.id")
    call: Mapped[str] = mapped_column(String(30))  # create_order | get_order | capture | refund | get_capture
    request_id_header: Mapped[str | None] = mapped_column(String(64))
    http_status: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(40))  # ok | timeout | error | response_discarded_by_test
    provider_ref: Mapped[str | None] = mapped_column(String(64))
    provider_status: Mapped[str | None] = mapped_column(String(40))
    debug_id: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[dict | None] = mapped_column(JSONB)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = created()


class Refund(Base):
    __tablename__ = "refunds"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = fk("workspaces.id", ondelete="CASCADE")
    operation_id: Mapped[uuid.UUID] = fk("payment_operations.id")
    capture_id: Mapped[str] = mapped_column(String(64))
    amount: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String(3))
    state: Mapped[str] = mapped_column(String(20))  # pending | completed | failed | reconciling
    request_id_header: Mapped[str] = mapped_column(String(64), unique=True)
    provider_refund_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    note: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID] = fk("users.id")
    created_at: Mapped[datetime] = created()


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    id: Mapped[uuid.UUID] = pk()
    provider_event_id: Mapped[str] = mapped_column(String(80), unique=True)
    event_type: Mapped[str] = mapped_column(String(80))
    resource_type: Mapped[str | None] = mapped_column(String(60))
    resource_id: Mapped[str | None] = mapped_column(String(80))
    headers: Mapped[dict] = mapped_column(JSONB)
    raw_body: Mapped[str] = mapped_column(Text)
    verification: Mapped[str] = mapped_column(String(20), default="pending")  # pending|verified|invalid|error
    processing: Mapped[str] = mapped_column(String(20), default="pending")  # pending|applied|ignored|failed
    outcome: Mapped[str | None] = mapped_column(Text)
    operation_id: Mapped[uuid.UUID | None] = fk("payment_operations.id", nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    received_at: Mapped[datetime] = created()
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_ready", "status", "run_after"),)
    id: Mapped[uuid.UUID] = pk()
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSONB)
    dedupe_key: Mapped[str | None] = mapped_column(String(160), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|succeeded|failed|dead
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    run_after: Mapped[datetime] = created()
    locked_by: Mapped[str | None] = mapped_column(String(80))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = created()


class AuditEvent(Base):
    """Append-only at the application level, hash-chained per workspace.

    The chain detects ordinary modification; a privileged DB administrator could
    rewrite it. It is not immutable proof.
    """

    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[uuid.UUID | None] = fk("workspaces.id", nullable=True, ondelete="CASCADE")
    actor_user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    principal_user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    object_type: Mapped[str | None] = mapped_column(String(60))
    object_id: Mapped[str | None] = mapped_column(String(80))
    request_id: Mapped[uuid.UUID | None] = fk("purchase_requests.id", nullable=True, ondelete="CASCADE")
    meta: Mapped[dict | None] = mapped_column(JSONB)
    correlation_id: Mapped[str | None] = mapped_column(String(40))
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[uuid.UUID] = pk()
    status: Mapped[str] = mapped_column(String(20))
    dataset_version: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(120))
    extraction_mode: Mapped[str] = mapped_column(String(20))  # llm | rules
    code_revision: Mapped[str | None] = mapped_column(String(60))
    config: Mapped[dict] = mapped_column(JSONB)
    summary: Mapped[dict | None] = mapped_column(JSONB)
    triggered_by: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    started_at: Mapped[datetime] = created()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"
    id: Mapped[uuid.UUID] = pk()
    run_id: Mapped[uuid.UUID] = fk("evaluation_runs.id", ondelete="CASCADE")
    case_id: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(40))
    field_results: Mapped[dict] = mapped_column(JSONB)
    evidence_checked: Mapped[int] = mapped_column(Integer, default=0)
    evidence_correct: Mapped[int] = mapped_column(Integer, default=0)
    decision_expected: Mapped[str] = mapped_column(String(20))
    decision_actual: Mapped[str | None] = mapped_column(String(20))
    unsafe_expected_blocked: Mapped[bool | None] = mapped_column(Boolean)
    payment_blocked: Mapped[bool | None] = mapped_column(Boolean)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)


class ExtractionCache(Base):
    __tablename__ = "extraction_cache"
    __table_args__ = (UniqueConstraint("workspace_id", "cache_key"),)
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = fk("workspaces.id", ondelete="CASCADE")
    cache_key: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created()


class AICall(Base):
    __tablename__ = "ai_calls"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID | None] = fk("workspaces.id", nullable=True, ondelete="CASCADE")
    request_id: Mapped[uuid.UUID | None] = fk("purchase_requests.id", nullable=True, ondelete="CASCADE")
    purpose: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20))
    latency_ms: Mapped[int] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = created()


class SimulatedProviderOrder(Base):
    """State for the explicitly labelled simulated PayPal adapter (MOCK_PAYPAL=true).

    Kept in PostgreSQL so it survives restarts and behaves like a remote provider.
    """

    __tablename__ = "simulated_provider_orders"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    create_request_id: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(30))  # CREATED | APPROVED | COMPLETED | VOIDED
    body: Mapped[dict] = mapped_column(JSONB)
    capture_request_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    capture_id: Mapped[str | None] = mapped_column(String(40), unique=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refunds: Mapped[list] = mapped_column(JSONB, default=list)
    capture_calls: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = created()


class DemoScenarioRun(Base):
    """Results of a controlled Demo Lab test, produced by the normal services."""

    __tablename__ = "demo_scenario_runs"
    id: Mapped[uuid.UUID] = pk()
    workspace_id: Mapped[uuid.UUID] = fk("workspaces.id", ondelete="CASCADE")
    scenario: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))  # running | finished | error
    request_id: Mapped[uuid.UUID | None] = fk("purchase_requests.id", nullable=True, ondelete="SET NULL")
    steps: Mapped[list] = mapped_column(JSONB, default=list)
    verdict: Mapped[str | None] = mapped_column(String(40))
    summary: Mapped[str | None] = mapped_column(Text)
    started_by: Mapped[uuid.UUID] = fk("users.id")
    started_at: Mapped[datetime] = created()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
