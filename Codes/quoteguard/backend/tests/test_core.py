"""Required checks from the build brief, numbered as in §14."""

from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update

from quoteguard import timeutil
from quoteguard.db import session_scope
from quoteguard.domain import policy, whatif
from quoteguard.domain.requirements import RequirementSpec, criterion_for
from quoteguard.errors import AppError
from quoteguard.models import Approval, Document, DocumentPage, EvidenceLink, MerchantBinding, PaymentOperation, Quote, QuoteVersion, WebhookEvent
from quoteguard.services import approvals, comparison, demo, documents, export, payments, webhooks
from quoteguard.services import requests as rs
from quoteguard.services.workflow import run_analysis

from .conftest import FakePayPal


def quotes_by_supplier(rid, actor):
    with session_scope() as db:
        view = comparison.comparison(db, actor, db.get(__import__("quoteguard.models", fromlist=["PurchaseRequest"]).PurchaseRequest, rid))
    return {q["supplier"]: q for q in view["quotes"]}, view


def approve(world, supplier="ClearWave Supplies"):
    qs, _ = quotes_by_supplier(world["request_id"], world["requester"])
    qid = qs[supplier]["quote_id"]
    with session_scope() as db:
        rv = approvals.review(db, world["approver"], world["request_id"], qid)
        a = approvals.approve(db, world["approver"], world["request_id"], qid, rv["terms_hash"])
        return str(a.id), qid


def checkout(world, appr_id):
    return payments.start_checkout(session_scope, world["requester"], appr_id)


SPEC = RequirementSpec(item="USB-C headsets", quantity=30, budget_amount=Decimal("600"), currency="USD", deadline_days=7, deadline_date=date(2026, 11, 8),
                       mandatory=[criterion_for("connector", "USB-C"), criterion_for("microphone", "yes")])


def facts(**kw):
    base = dict(quote_id="q", supplier="S", currency="USD", currency_status="explicit", quantity=30, subtotal=Decimal("540.00"), shipping=Decimal("30.00"), tax=Decimal("0.00"),
                discount=None, stated_total=Decimal("570.00"), delivery_days=5, valid_until=date(2026, 12, 1), attributes={"connector": "USB-C", "microphone": "yes"}, checkout_available=True,
                unit_price=Decimal("18.00"))
    base.update(kw)
    return policy.QuoteFacts(**base)


# 1 ----------------------------------------------------------------------------------
def test_reference_quotes_exact_totals_and_outcomes(world):
    qs, view = quotes_by_supplier(world["request_id"], world["requester"])
    cw, ns, hd = qs["ClearWave Supplies"]["outcome"], qs["Northstar Office"]["outcome"], qs["Harbor Devices"]["outcome"]
    assert (cw["verified_total"], cw["mandatory_status"], cw["compliant_rank"], cw["payment_eligible"]) == ("570.00", "pass", 1, True)
    assert (ns["verified_total"], ns["mandatory_status"]) == ("640.00", "fail")
    assert next(c for c in ns["checks"] if c["key"] == "budget")["status"] == "fail"
    assert (hd["verified_total"], hd["mandatory_status"]) == ("470.00", "fail")
    assert next(c for c in hd["checks"] if c["key"] == "attr:connector")["status"] == "fail"
    assert view["summary"]["why_cheapest_loses"]["supplier"] == "Harbor Devices"
    # What-if: $650 makes Northstar compliant but not cheapest; $560 leaves none compliant.
    f = [policy.QuoteFacts(quote_id=q["quote_id"], supplier=s, currency="USD", currency_status="explicit", quantity=30, subtotal=Decimal(q["version"]["subtotal"]),
                           shipping=Decimal(q["version"]["shipping"]), tax=Decimal(q["version"]["tax"]), discount=None, stated_total=Decimal(q["version"]["stated_total"]),
                           delivery_days=5, valid_until=date(2026, 12, 1), attributes=q["version"]["attributes"], checkout_available=s.startswith("ClearWave")) for s, q in qs.items()]
    p650 = whatif.preview(SPEC, f, date(2026, 11, 1), budget=Decimal("650"))
    assert {c["supplier"] for c in p650["changes"]} == {"Northstar Office"} and p650["summary"]["best_compliant_supplier"] == "ClearWave Supplies"
    p560 = whatif.preview(SPEC, f, date(2026, 11, 1), budget=Decimal("560"))
    assert p560["summary"]["no_compliant_quote"] is True and p560["summary"]["best_compliant_quote_id"] is None


# 2 ----------------------------------------------------------------------------------
@pytest.mark.parametrize("change,key", [({"shipping": None}, "cost_known"), ({"tax": None}, "cost_known"), ({"currency_status": "inferred"}, "currency"), ({"currency": None, "currency_status": "unknown"}, "currency")])
def test_missing_costs_and_uncertain_currency_never_verified(change, key):
    o = policy.evaluate(SPEC, facts(**change), date(2026, 11, 1))
    assert o.verified_total is None and o.mandatory_status == "unknown" and not o.payment_eligible
    assert next(c for c in o.checks if c.key == key).status == "unknown"


def test_contradictory_total_needs_review():
    o = policy.evaluate(SPEC, facts(stated_total=Decimal("560.00")), date(2026, 11, 1))
    assert o.arithmetic_status == "contradictory" and o.verified_total is None and not o.payment_eligible


# 3 ----------------------------------------------------------------------------------
def test_evidence_references_resolve_to_source_text(world):
    with session_scope() as db:
        links = db.execute(select(EvidenceLink)).scalars().all()
        assert len(links) >= 30
        for ln in links:
            page = db.execute(select(DocumentPage).where(DocumentPage.document_id == ln.document_id, DocumentPage.page_number == ln.page_number)).scalar_one()
            assert " ".join(ln.source_text.split()) in " ".join(page.text.split())
            assert ln.document_sha256 == db.get(Document, ln.document_id).sha256
        assert sum(1 for ln in links if ln.location_status == "bbox" and ln.bbox) >= 30


# 4 ----------------------------------------------------------------------------------
def test_correction_creates_version_and_invalidates_approval(world):
    appr_id, qid = approve(world)
    with session_scope() as db:
        qv = documents.correct(db, world["requester"], qid, "shipping", "35.00", "Supplier confirmed new freight rate by email")
        assert qv.version == 2 and qv.correction["original_value"] == "30.00" and qv.correction["note"].startswith("Supplier")
        a = db.get(Approval, uuid.UUID(appr_id))
        assert a.status == "invalidated"
        old = db.execute(select(QuoteVersion).where(QuoteVersion.quote_id == uuid.UUID(qid), QuoteVersion.version == 1)).scalar_one()
        assert str(old.shipping) == "30.00"  # original preserved
    with pytest.raises(AppError) as e:
        checkout(world, appr_id)
    assert e.value.code in ("SNAPSHOT_CHANGED", "APPROVAL_INVALID")


# 5 ----------------------------------------------------------------------------------
def test_tampered_amount_or_merchant_blocks_order_creation(world):
    appr_id, qid = approve(world)
    with session_scope() as db:  # bypass service hooks: only the execution-time guard can catch this
        q = db.get(Quote, uuid.UUID(qid))
        db.execute(update(MerchantBinding).where(MerchantBinding.supplier_id == q.supplier_id).values(merchant_id="EVIL"))
    with pytest.raises(AppError) as e:
        checkout(world, appr_id)
    assert e.value.code == "MERCHANT_CHANGED"
    assert any(c["field"] == "merchant.merchant_id" for c in e.value.details["changes"])
    assert world["paypal"].create_bodies == []


def test_change_after_order_blocks_capture(world):
    appr_id, qid = approve(world)
    op = checkout(world, appr_id)
    world["paypal"].approve(op["provider_order_id"])
    with session_scope() as db:
        q = db.get(Quote, uuid.UUID(qid))
        db.execute(update(QuoteVersion).where(QuoteVersion.id == q.current_version_id).values(shipping="60.00", computed_total="600.00", stated_total="600.00"))
    with pytest.raises(AppError) as e:
        payments.capture(session_scope, world["requester"], op["id"])
    assert e.value.code == "SNAPSHOT_CHANGED" and world["paypal"].capture_count == 0
    with session_scope() as db:
        assert db.get(PaymentOperation, uuid.UUID(op["id"])).state == "canceled"


# 6 ----------------------------------------------------------------------------------
def test_expired_revoked_and_unauthorised_approvals_fail(world):
    appr_id, qid = approve(world)
    timeutil.freeze(timeutil.now() + timedelta(minutes=61))
    with pytest.raises(AppError) as e:
        checkout(world, appr_id)
    assert e.value.code == "APPROVAL_EXPIRED"
    timeutil.freeze(timeutil.now() - timedelta(minutes=61))
    # requester cannot approve (role) and self-approval is disabled
    with session_scope() as db:
        rv = approvals.review(db, world["requester"], world["request_id"], qid)
        with pytest.raises(AppError) as e2:
            approvals.approve(db, world["requester"], world["request_id"], qid, rv["terms_hash"])
        assert e2.value.code == "FORBIDDEN"
    appr2, _ = approve(world)
    with session_scope() as db:
        approvals.revoke(db, world["approver"], appr2, "changed mind")
    with pytest.raises(AppError) as e3:
        checkout(world, appr2)
    assert e3.value.code == "APPROVAL_REVOKED"


def test_cross_workspace_access_is_not_found(world, paypal):
    from quoteguard.models import User
    from quoteguard.services.context import load_actor

    appr_id, qid = approve(world)
    with session_scope() as db:
        other = User(email="o@test.invalid", display_name="Other", created_at=timeutil.now())
        db.add(other)
        db.flush()
        ws2 = demo.provision_workspace(db, other)
        stranger = load_actor(db, other.id, other.id, ws2.id)
        stranger_approver = load_actor(db, demo.persona_user(db).id, other.id, ws2.id)
        with pytest.raises(AppError) as e:
            approvals.review(db, stranger_approver, world["request_id"], qid)
        assert e.value.status == 404
        with pytest.raises(AppError) as e:
            load_actor(db, other.id, other.id, world["workspace_id"])
        assert e.value.code == "WORKSPACE_ACCESS_DENIED"
    with pytest.raises(AppError) as e:
        payments.start_checkout(session_scope, stranger, appr_id)
    assert e.value.status == 404


# 7 ----------------------------------------------------------------------------------
def test_unconfigured_supplier_cannot_be_paid(world):
    with session_scope() as db:
        spec = {**demo.SAMPLE_SPEC, "budget_amount": "650.00"}
        rs.confirm(db, world["requester"], world["request_id"], spec, source="whatif", expected_version=1)
    run_analysis(str(world["request_id"]))
    qs, _ = quotes_by_supplier(world["request_id"], world["requester"])
    assert qs["Northstar Office"]["outcome"]["mandatory_status"] == "pass" and not qs["Northstar Office"]["outcome"]["checkout_available"]
    with session_scope() as db:
        rv = approvals.review(db, world["approver"], world["request_id"], qs["Northstar Office"]["quote_id"])
        with pytest.raises(AppError) as e:
            approvals.approve(db, world["approver"], world["request_id"], qs["Northstar Office"]["quote_id"], rv["terms_hash"])
    assert e.value.code == "MERCHANT_UNCONFIGURED"


# 8 ----------------------------------------------------------------------------------
def test_client_cannot_change_amount_or_payee(world):
    from fastapi.testclient import TestClient

    from quoteguard.api.main import app

    appr_id, _ = approve(world)
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"username": "JuryTest", "password": "nope"})
    assert r.status_code == 401
    # API layer: unknown fields are rejected before any service runs.
    from quoteguard.api.routers.core import Empty

    with pytest.raises(Exception):
        Empty.model_validate({"amount": "1.00", "payee": "evil@example.com"})
    op = checkout(world, appr_id)
    body = world["paypal"].create_bodies[0]["purchase_units"][0]
    assert body["amount"]["value"] == "570.00" and body["payee"]["merchant_id"] == "TESTMERCHANT01" and body["custom_id"] == op["id"]
    assert sum(Decimal(i["unit_amount"]["value"]) * int(i["quantity"]) for i in body["items"]) == Decimal(body["amount"]["breakdown"]["item_total"]["value"])


# 9 ----------------------------------------------------------------------------------
def test_paypal_buyer_approval_cannot_bypass_org_approval(world):
    appr_id, _ = approve(world)
    op = checkout(world, appr_id)
    world["paypal"].approve(op["provider_order_id"])  # buyer approved in PayPal
    with session_scope() as db:
        approvals.revoke(db, world["approver"], appr_id, "organisation withdrew approval")
    with pytest.raises(AppError) as e:
        payments.capture(session_scope, world["requester"], op["id"])
    assert e.value.code == "PAYMENT_CANCELED" and world["paypal"].capture_count == 0


def test_org_approval_alone_cannot_capture(world):
    appr_id, _ = approve(world)
    op = checkout(world, appr_id)
    res = payments.capture(session_scope, world["requester"], op["id"])  # buyer has not approved
    assert res["state"] == "awaiting_payer" and res["last_error_code"] == "PAYER_NOT_APPROVED" and world["paypal"].capture_count == 0


# 10 ---------------------------------------------------------------------------------
def test_concurrent_checkout_and_capture_are_one_operation(world):
    appr_id, _ = approve(world)
    with ThreadPoolExecutor(8) as pool:
        ops = list(pool.map(lambda _: checkout(world, appr_id), range(8)))
    assert len({o["id"] for o in ops}) == 1
    assert sum(1 for c in world["paypal"].calls if c[0] == "create_order") == 1
    with session_scope() as db:  # losers saw the in-progress operation; read the settled one
        settled = db.get(PaymentOperation, uuid.UUID(ops[0]["id"]))
        assert settled.state == "awaiting_payer"
        world["paypal"].approve(settled.provider_order_id)

    def cap(_):
        try:
            return payments.capture(session_scope, world["requester"], ops[0]["id"])["state"]
        except AppError as e:
            return e.code

    with ThreadPoolExecutor(8) as pool:
        states = list(pool.map(cap, range(8)))
    assert world["paypal"].capture_count == 1
    assert "completed" in states
    with session_scope() as db:
        assert db.execute(select(func.count()).select_from(PaymentOperation)).scalar() == 1


# 11 ---------------------------------------------------------------------------------
def test_lost_capture_response_reconciles_without_second_charge(world):
    appr_id, _ = approve(world)
    op = checkout(world, appr_id)
    world["paypal"].approve(op["provider_order_id"])
    world["paypal"].timeout_after_capture = True
    res = payments.capture(session_scope, world["requester"], op["id"])
    assert res["state"] == "reconciling"
    again = payments.capture(session_scope, world["requester"], op["id"])  # impatient retry
    assert again.get("in_progress") and world["paypal"].capture_count == 1
    done = payments.reconcile(session_scope, op["id"])
    assert done["state"] == "completed" and done["provider_capture_id"] and world["paypal"].capture_count == 1
    assert len(world["paypal"].orders) == 1  # no replacement order


# 12 ---------------------------------------------------------------------------------
def test_restart_after_intent_resumes_safely(world):
    appr_id, _ = approve(world)
    world["paypal"].fail_next["create_order"] = ProviderAmbiguousLike()
    op = checkout(world, appr_id)
    assert op["state"] == "reconciling" and op["provider_order_id"] is None
    # "restart": the worker reconciles by replaying the same PayPal-Request-Id
    res = payments.reconcile(session_scope, op["id"])
    assert res["state"] == "awaiting_payer"
    creates = [c for c in world["paypal"].calls if c[0] == "create_order"]
    assert len(creates) == 2 and creates[0][1] == creates[1][1] and len(world["paypal"].orders) == 1
    # crash between capture intent and result: state capture_pending with no result recorded
    world["paypal"].approve(res["provider_order_id"])
    with session_scope() as db:
        o = db.get(PaymentOperation, uuid.UUID(op["id"]))
        o.state, o.updated_at = "capture_pending", timeutil.now() - timedelta(minutes=5)
    with session_scope() as db:
        assert payments.recover_stuck(db) == 1
    final = payments.reconcile(session_scope, op["id"])
    assert final["state"] == "completed" and world["paypal"].capture_count == 1


def ProviderAmbiguousLike():
    from quoteguard.paypal.base import ProviderAmbiguous

    return ProviderAmbiguous("timeout")


# 13 ---------------------------------------------------------------------------------
def _event(eid, etype, order_id, capture_id=None, payee="TESTMERCHANT01"):
    res = {"id": capture_id or order_id, "payee": {"merchant_id": payee}}
    if capture_id:
        res["supplementary_data"] = {"related_ids": {"order_id": order_id}}
    return json.dumps({"id": eid, "event_type": etype, "resource_type": "capture" if capture_id else "checkout-order", "resource": res}).encode()


def test_webhooks_duplicate_invalid_unrelated_and_reordered(world):
    appr_id, _ = approve(world)
    op = checkout(world, appr_id)
    world["paypal"].approve(op["provider_order_id"])
    done = payments.capture(session_scope, world["requester"], op["id"])
    assert done["state"] == "completed"
    good = {"paypal-transmission-sig": "valid", "paypal-auth-algo": "x", "paypal-cert-url": "x", "paypal-transmission-id": "x", "paypal-transmission-time": "x"}
    with session_scope() as db:
        assert webhooks.receive(db, good, _event("E1", "PAYMENT.CAPTURE.COMPLETED", op["provider_order_id"], done["provider_capture_id"]))[1] == "accepted"
        assert webhooks.receive(db, good, _event("E1", "PAYMENT.CAPTURE.COMPLETED", op["provider_order_id"], done["provider_capture_id"]))[1] == "duplicate"
        webhooks.receive(db, {**good, "paypal-transmission-sig": "forged"}, _event("E2", "PAYMENT.CAPTURE.DENIED", op["provider_order_id"], done["provider_capture_id"]))
        webhooks.receive(db, good, _event("E3", "PAYMENT.CAPTURE.COMPLETED", "UNKNOWNORDER", "UNKNOWNCAP"))
        webhooks.receive(db, good, _event("E4", "CHECKOUT.ORDER.APPROVED", op["provider_order_id"]))  # late, out-of-order
        ids = {w.provider_event_id: str(w.id) for w in db.execute(select(WebhookEvent)).scalars()}
    for eid in ("E1", "E2", "E3", "E4"):
        webhooks.process(session_scope, ids[eid])
    with session_scope() as db:
        w = {x.provider_event_id: x for x in db.execute(select(WebhookEvent)).scalars()}
        assert (w["E1"].verification, w["E1"].processing) == ("verified", "applied")
        assert (w["E2"].verification, w["E2"].processing) == ("invalid", "ignored")
        assert w["E3"].processing == "ignored"
        assert db.get(PaymentOperation, uuid.UUID(op["id"])).state == "completed"  # never regressed
    assert world["paypal"].capture_count == 1


# 14 ---------------------------------------------------------------------------------
def test_malicious_pdf_cannot_change_policy_permissions_or_payee(world):
    with session_scope() as db:
        demo.load_fixture(db, world["requester"], world["request_id"], "malicious")
    run_analysis(str(world["request_id"]))
    qs, _ = quotes_by_supplier(world["request_id"], world["requester"])
    mal = qs["Brightline Audio Co."]
    assert mal["document"]["suspicious"] and mal["supplier_link"] == "suggested" and not mal["outcome"]["checkout_available"]
    assert mal["outcome"]["mandatory_status"] == "fail"
    with session_scope() as db:
        _, spec = rs.current_spec(db, db.get(__import__("quoteguard.models", fromlist=["PurchaseRequest"]).PurchaseRequest, world["request_id"]))
        assert spec.budget_amount == Decimal("600.00")
        rv = approvals.review(db, world["approver"], world["request_id"], mal["quote_id"])
        assert rv["eligible"] is False and rv["terms"]["merchant"] is None


# 15 ---------------------------------------------------------------------------------
def test_distinct_outcomes_for_decline_cancel_pending_and_outage(world):
    from quoteguard.paypal.base import ProviderAmbiguous, ProviderError

    appr_id, _ = approve(world)
    op = checkout(world, appr_id)
    canceled = payments.buyer_canceled(session_scope, world["requester"], op["id"])
    assert (canceled["state"], canceled["last_error_code"]) == ("awaiting_payer", "BUYER_CANCELED")
    world["paypal"].fail_next["get_order"] = ProviderAmbiguous("outage")
    outage = payments.capture(session_scope, world["requester"], op["id"])
    assert (outage["state"], outage["last_error_code"]) == ("awaiting_payer", "PROVIDER_UNAVAILABLE")
    world["paypal"].approve(op["provider_order_id"])
    world["paypal"].fail_next["capture"] = ProviderError("INSTRUMENT_DECLINED", "declined", 422)
    declined = payments.capture(session_scope, world["requester"], op["id"])
    assert (declined["state"], declined["last_error_code"]) == ("awaiting_payer", "INSTRUMENT_DECLINED")
    world["paypal"].capture_status = "PENDING"
    pending = payments.capture(session_scope, world["requester"], op["id"])
    assert (pending["state"], pending["last_error_code"], pending["provider_capture_status"]) == ("reconciling", "PROVIDER_PENDING", "PENDING")


# 16 ---------------------------------------------------------------------------------
def test_export_has_references_and_no_secrets(world):
    appr_id, _ = approve(world)
    op = checkout(world, appr_id)
    world["paypal"].approve(op["provider_order_id"])
    done = payments.capture(session_scope, world["requester"], op["id"])
    with session_scope() as db:
        pkg = export.package(db, world["requester"], world["request_id"])
        pdf = export.package_pdf(pkg)
    blob = json.dumps(pkg, default=str)
    assert done["provider_capture_id"] in blob and op["provider_order_id"] in blob and pkg["approvals"][0]["snapshot_hash"] in blob
    for secret in ("test-client-secret-DO-NOT-LEAK", "access_token", "password_hash", "BUYER1"):
        assert secret not in blob
    assert pdf.startswith(b"%PDF") and pkg["audit_chain"]["valid"] is True


# 17 ---------------------------------------------------------------------------------
def test_live_mode_cannot_be_enabled():
    from pydantic import ValidationError

    from quoteguard.config import Settings

    with pytest.raises(ValidationError):
        Settings(PAYPAL_MODE="live")


def test_demo_login_gets_isolated_workspace_and_cannot_switch_elsewhere(world):
    from fastapi.testclient import TestClient

    from quoteguard.api.main import app

    with session_scope() as db:
        demo.ensure_demo_account(db)
    a, b = TestClient(app), TestClient(app)
    ma = a.post("/api/v1/auth/login", json={"username": "JuryTest", "password": "JuryTest-pass-1"}).json()
    mb = b.post("/api/v1/auth/login", json={"username": "JuryTest", "password": "JuryTest-pass-1"}).json()
    assert ma["workspace"]["id"] != mb["workspace"]["id"] and ma["workspace"]["is_demo"]
    r = a.post("/api/v1/auth/workspace", json={"workspace_id": str(world["workspace_id"])}, headers={"X-CSRF-Token": a.cookies.get("qg_csrf")})
    assert r.status_code == 403
    r = a.get(f"/api/v1/requests/{world['request_id']}")
    assert r.status_code == 404
    r = a.post("/api/v1/demo/sample-request")  # missing CSRF header
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_FAILED"


# 18 ---------------------------------------------------------------------------------
def test_refund_cannot_exceed_capture_even_concurrently(world):
    appr_id, _ = approve(world)
    op = checkout(world, appr_id)
    world["paypal"].approve(op["provider_order_id"])
    payments.capture(session_scope, world["requester"], op["id"])

    def refund(_):
        try:
            return payments.refund(session_scope, world["requester"], op["id"], "200.00", "damaged units")["state"]
        except AppError as e:
            return e.code

    with ThreadPoolExecutor(5) as pool:
        out = list(pool.map(refund, range(5)))
    assert out.count("REFUND_EXCEEDS_CAPTURE") == 3
    total = sum(Decimal(r["amount"]) for refs in world["paypal"].refunds.values() for r in refs)
    assert total == Decimal("400.00") <= Decimal("570.00")


def test_audit_chain_detects_modification(world):
    from quoteguard import audit
    from quoteguard.models import AuditEvent

    with session_scope() as db:
        assert audit.verify_chain(db, world["workspace_id"])["valid"]
        ev = db.execute(select(AuditEvent).where(AuditEvent.workspace_id == world["workspace_id"]).order_by(AuditEvent.id).limit(1)).scalar_one()
        ev.meta = {"tampered": True}
    with session_scope() as db:
        assert audit.verify_chain(db, world["workspace_id"])["valid"] is False


def test_fake_provider_is_used():
    assert FakePayPal.name == "sandbox"


# Demo Lab ---------------------------------------------------------------------------
@pytest.mark.parametrize("scenario,verdict", [("amount_changed", "blocked_as_expected"), ("merchant_changed", "blocked_as_expected"), ("malicious_pdf", "blocked_as_expected"),
                                              ("double_click", "one_operation"), ("lost_response", "recovered")])
def test_demo_lab_scenarios_use_real_services(world, scenario, verdict):
    from quoteguard.models import DemoScenarioRun

    with session_scope() as db:
        run = DemoScenarioRun(workspace_id=world["workspace_id"], scenario=scenario, status="running", steps=[], started_by=world["requester"].user_id, started_at=timeutil.now())
        db.add(run)
        db.flush()
        run_id = run.id
    demo._run_scenario(run_id, scenario, world["requester"])
    with session_scope() as db:
        r = db.get(DemoScenarioRun, run_id)
        assert (r.status, r.verdict) == ("finished", verdict), r.steps


def test_agent_toolkit_tools_are_read_only_and_server_scoped(monkeypatch):
    from quoteguard.ai import paypal_tools

    names = {t["function"]["name"] for t in paypal_tools.TOOLS}
    assert names == {"paypal_get_order_details", "paypal_find_capture_transaction"}
    assert all(t["function"]["parameters"]["properties"] == {} for t in paypal_tools.TOOLS)  # model supplies no arguments
    assert paypal_tools.execute("pay_order", "ORDER1", None) == {"error": "tool not allowed"}
    seen = {}

    class FakeAPI:
        def run(self, method, params):
            seen[method] = params
            return '{"message": "has been successfully captured", "status": "CREATED", "raw": {"id": "ORDER1", "status": "CREATED", "purchase_units": [{"amount": {"value": "570.00", "currency_code": "USD"}}]}}'

    monkeypatch.setattr(paypal_tools, "_api", lambda: FakeAPI())
    res = paypal_tools.execute("paypal_get_order_details", "ORDER1", None)
    assert seen == {"get_order_details": {"order_id": "ORDER1"}}
    assert res["order"]["status"] == "CREATED" and "message" not in json.dumps(res)  # toolkit prose is never forwarded
