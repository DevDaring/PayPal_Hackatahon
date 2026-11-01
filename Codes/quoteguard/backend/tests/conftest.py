"""Test harness: real PostgreSQL (locks and constraints matter), frozen scenario clock,
deterministic extraction (MOCK_AI) and an in-memory fake PayPal provider."""

from __future__ import annotations

import os
import secrets
import threading
import uuid
from datetime import UTC, datetime

import pytest

TEST_DB = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL", "").replace("/quoteguard_dev", "/quoteguard_test")
if "quoteguard_test" not in TEST_DB:
    # Read the dev URL from the repo .env and point it at the dedicated test database.
    from pathlib import Path

    env = Path(__file__).resolve().parents[2] / ".env"
    for line in env.read_text().splitlines() if env.exists() else []:
        if line.startswith("DATABASE_URL="):
            TEST_DB = line.split("=", 1)[1].rsplit("/", 1)[0] + "/quoteguard_test"
os.environ.update({
    "QUOTEGUARD_ENV_FILE": "/dev/null", "APP_ENV": "test", "DATABASE_URL": TEST_DB, "MOCK_AI": "true", "MOCK_PAYPAL": "false",
    "AI_PROVIDER": "none", "OCR_PROVIDER": "", "PAYPAL_CLIENT_ID": "test-client-id", "PAYPAL_CLIENT_SECRET": "test-client-secret-DO-NOT-LEAK",
    "PAYPAL_MERCHANT_ID": "TESTMERCHANT01", "PAYPAL_WEBHOOK_ID": "WH-TEST", "STORAGE_PATH": __import__("tempfile").mkdtemp(prefix="qg-test-storage-"),
    "SESSION_SECRET": secrets.token_urlsafe(40), "APPROVAL_SIGNING_SECRET": secrets.token_urlsafe(40), "APPROVAL_TTL_MINUTES": "60",
    "DEMO_ACCOUNT_USERNAME": "JuryTest", "DEMO_ACCOUNT_PASSWORD": "JuryTest-pass-1", "CORS_ALLOWED_ORIGINS": "http://testserver",
})

from sqlalchemy import text  # noqa: E402

from quoteguard import timeutil  # noqa: E402
from quoteguard.db import Base, engine, reset_engine, session_scope  # noqa: E402
from quoteguard.paypal import set_adapter  # noqa: E402
from quoteguard.paypal.base import PaymentProvider, ProviderAmbiguous, ProviderError, ProviderResult  # noqa: E402

SCENARIO_NOW = datetime(2026, 11, 1, 6, 0, tzinfo=UTC)


class FakePayPal(PaymentProvider):
    """Behaves like Orders v2 for the parts we rely on, including PayPal-Request-Id idempotency."""

    name = "sandbox"

    def __init__(self):
        self.lock = threading.Lock()
        self.orders: dict[str, dict] = {}
        self.by_request: dict[str, str] = {}
        self.capture_by_request: dict[str, str] = {}
        self.calls: list[tuple[str, str | None]] = []
        self.create_bodies: list[dict] = []
        self.capture_count = 0
        self.fail_next: dict[str, Exception] = {}
        self.timeout_after_capture = False
        self.capture_status = "COMPLETED"
        self.payee_override: str | None = None
        self.refunds: dict[str, list] = {}

    def _maybe_fail(self, op):
        exc = self.fail_next.pop(op, None)
        if exc:
            raise exc

    def _view(self, o):
        body = {"id": o["id"], "status": o["status"], "purchase_units": [dict(o["pu"])], "payer": {"payer_id": "BUYER1"} if o["status"] != "CREATED" else None}
        if o.get("capture_id"):
            body["purchase_units"][0]["payments"] = {"captures": [{"id": o["capture_id"], "status": o["capture_status"], "amount": o["pu"]["amount"], "final_capture": True}]}
        return body

    def create_order(self, body, request_id):
        with self.lock:
            self.calls.append(("create_order", request_id))
            self._maybe_fail("create_order")
            if request_id in self.by_request:
                return ProviderResult(self._view(self.orders[self.by_request[request_id]]), 200, 1)
            oid = "ORD" + uuid.uuid4().hex[:12].upper()
            pu = dict(body["purchase_units"][0])
            pu["payee"] = {"merchant_id": self.payee_override or pu.get("payee", {}).get("merchant_id")}
            self.orders[oid] = {"id": oid, "status": "CREATED", "pu": pu}
            self.by_request[request_id] = oid
            self.create_bodies.append(body)
            return ProviderResult(self._view(self.orders[oid]), 201, 1)

    def approve(self, oid):
        with self.lock:
            self.orders[oid]["status"] = "APPROVED"

    def get_order(self, oid):
        with self.lock:
            self.calls.append(("get_order", oid))
            self._maybe_fail("get_order")
            if oid not in self.orders:
                raise ProviderError("RESOURCE_NOT_FOUND", "not found", 404)
            return ProviderResult(self._view(self.orders[oid]), 200, 1)

    def capture_order(self, oid, request_id):
        with self.lock:
            self.calls.append(("capture", request_id))
            self._maybe_fail("capture")
            o = self.orders[oid]
            if self.capture_by_request.get(request_id) == oid:
                return ProviderResult(self._view(o), 200, 1)
            if o["status"] == "COMPLETED":
                raise ProviderError("ORDER_ALREADY_CAPTURED", "already captured", 422)
            if o["status"] != "APPROVED":
                raise ProviderError("ORDER_NOT_APPROVED", "payer has not approved", 422)
            self.capture_count += 1
            o["status"], o["capture_id"], o["capture_status"] = "COMPLETED", "CAP" + uuid.uuid4().hex[:10].upper(), self.capture_status
            self.capture_by_request[request_id] = oid
            if self.timeout_after_capture:
                self.timeout_after_capture = False
                raise ProviderAmbiguous("timeout after provider processed capture")
            return ProviderResult(self._view(o), 201, 1)

    def get_capture(self, cid):
        raise NotImplementedError

    def refund_capture(self, cid, amount, currency, request_id, note):
        with self.lock:
            lst = self.refunds.setdefault(cid, [])
            for r in lst:
                if r["rid"] == request_id:
                    return ProviderResult({"id": r["id"], "status": "COMPLETED"}, 200, 1)
            r = {"id": "REF" + uuid.uuid4().hex[:8], "rid": request_id, "amount": amount}
            lst.append(r)
            return ProviderResult({"id": r["id"], "status": "COMPLETED"}, 201, 1)

    def verify_webhook(self, headers, event, webhook_id):
        return "SUCCESS" if headers.get("paypal-transmission-sig") == "valid" else "FAILURE"


@pytest.fixture(scope="session", autouse=True)
def database():
    reset_engine()
    with engine().begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    from alembic import command
    from alembic.config import Config

    from pathlib import Path

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    command.upgrade(cfg, "head")  # the migration itself is under test
    yield


@pytest.fixture(autouse=True)
def clean(database):
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine().begin() as c:
        c.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    timeutil.freeze(SCENARIO_NOW)
    yield
    timeutil.freeze(None)


@pytest.fixture
def paypal():
    fake = FakePayPal()
    set_adapter("sandbox", fake)
    yield fake
    set_adapter("sandbox", None)


@pytest.fixture
def world(paypal):
    """A demo workspace with requester+admin (principal) and approver persona, plus the analysed sample request."""
    from quoteguard.models import User
    from quoteguard.security import hash_password
    from quoteguard.services import demo
    from quoteguard.services import requests as rs
    from quoteguard.services.context import load_actor
    from quoteguard.services.workflow import run_analysis

    with session_scope() as db:
        u = User(email="req@test.invalid", username="req", display_name="Req", password_hash=hash_password("x"), is_demo_account=True, created_at=timeutil.now())
        db.add(u)
        db.flush()
        ws = demo.provision_workspace(db, u)
        requester = load_actor(db, u.id, u.id, ws.id)
        approver = load_actor(db, demo.persona_user(db).id, u.id, ws.id)
        req = rs.create(db, requester, demo.SAMPLE_TEXT)
        rs.confirm(db, requester, req.id, demo.SAMPLE_SPEC)
        demo.load_sample_quotes(db, requester, req.id)
        rid = req.id
    run_analysis(str(rid))
    return {"requester": requester, "approver": approver, "request_id": rid, "workspace_id": ws.id, "paypal": paypal}
