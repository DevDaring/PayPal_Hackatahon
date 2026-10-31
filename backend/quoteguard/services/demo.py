"""Isolated demo workspaces, the guided sample purchase, and Demo Lab controlled tests.

Demo Lab scenarios call the SAME services as normal operation. Their verdicts are computed
from what those services actually returned; nothing here declares a block in advance.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .. import audit, fixtures, timeutil
from ..config import get_settings
from ..db import session_scope
from ..errors import AppError
from ..models import (
    Approval,
    DemoScenarioRun,
    Document,
    MerchantBinding,
    Membership,
    PaymentOperation,
    ProviderTransaction,
    PurchaseRequest,
    Quote,
    QuoteVersion,
    SimulatedProviderOrder,
    Supplier,
    User,
    Workspace,
)
from ..security import hash_password
from . import approvals, comparison, documents, merchants, payments
from . import requests as requests_svc
from .context import Actor, get_request, load_actor
from .workflow import run_analysis

SAMPLE_TEXT = "Buy 30 USB-C headsets with microphones. Total budget $600 including shipping and stated taxes. Delivery within seven calendar days."
SAMPLE_SPEC = {"item": "USB-C headsets with microphones", "quantity": 30, "budget_amount": "600.00", "currency": "USD", "budget_includes": ["shipping", "tax"], "deadline_days": 7,
               "mandatory": [{"key": "connector", "label": "USB-C connector", "expected": "USB-C", "synonyms": ["usb-c", "usb type-c", "type-c", "usb c"]},
                             {"key": "microphone", "label": "Built-in microphone", "expected": "yes", "synonyms": ["microphone", "mic", "boom mic", "noise-cancelling mic"]}],
               "preferred": [], "ambiguities": []}
PERSONA_EMAIL = "approver.persona@demo.quoteguard.invalid"
SAMPLE_CONFIRMER = "QuoteGuard sample fixture (controlled supplier mapping)"


def persona_user(db: Session) -> User:
    u = db.execute(select(User).where(User.email == PERSONA_EMAIL)).scalar_one_or_none()
    if u is None:
        # Personas have no password: they can only be reached through the labelled role switch.
        u = User(email=PERSONA_EMAIL, display_name="Avery Chen · Demo approver", password_hash=None, is_persona=True, created_at=timeutil.now())
        db.add(u)
        db.flush()
    return u


def merchant_adapter() -> tuple[str, str]:
    s = get_settings()
    if s.MOCK_PAYPAL:
        return "simulated", "SIMULATED-CLEARWAVE"
    if s.paypal_credentials_present and s.PAYPAL_MERCHANT_ID:
        return "sandbox", s.PAYPAL_MERCHANT_ID
    return "sandbox", "UNCONFIGURED"


def provision_workspace(db: Session, principal: User, name: str | None = None) -> Workspace:
    ws = Workspace(name=name or f"Demo workspace · {timeutil.now().astimezone().strftime('%d %b %H:%M')}", is_demo=True, self_approval_allowed=False,
                   created_by_user_id=principal.id, created_at=timeutil.now())
    db.add(ws)
    db.flush()
    db.add(Membership(workspace_id=ws.id, user_id=principal.id, roles=["requester", "admin"], created_at=timeutil.now()))
    db.add(Membership(workspace_id=ws.id, user_id=persona_user(db).id, roles=["approver"], is_demo_persona=True, created_at=timeutil.now()))
    adapter, mid = merchant_adapter()
    for name_, bind in (("Northstar Office", False), ("ClearWave Supplies", True), ("Harbor Devices", False)):
        sup = Supplier(workspace_id=ws.id, name=name_, normalized_name=documents.normalize_name(name_), created_at=timeutil.now())
        db.add(sup)
        db.flush()
        if bind:
            db.add(MerchantBinding(workspace_id=ws.id, supplier_id=sup.id, adapter=adapter, merchant_id=mid,
                                   display_label=("PayPal Sandbox merchant" if adapter == "sandbox" else "Simulated merchant"), status="active",
                                   verified_at=timeutil.now() if mid != "UNCONFIGURED" else None, created_at=timeutil.now(), updated_at=timeutil.now()))
    audit.record(db, "workspace.provisioned", workspace_id=ws.id, actor_id=principal.id, object_type="workspace", object_id=ws.id, meta={"demo": True, "merchant_adapter": adapter})
    return ws


# ------------------------------------------------------------- sample flow ----------
def start_sample(db: Session, actor: Actor) -> PurchaseRequest:
    return requests_svc.create(db, actor, SAMPLE_TEXT, title="30 USB-C headsets for the support team")


def _supplier(db: Session, ws_id, name: str) -> Supplier:
    return db.execute(select(Supplier).where(Supplier.workspace_id == ws_id, Supplier.normalized_name == documents.normalize_name(name))).scalar_one()


def load_sample_quotes(db: Session, actor: Actor, request_id) -> list[Document]:
    req = get_request(db, actor, request_id)
    issue = timeutil.local_date(req.timezone, req.created_at)
    out = []
    for s in fixtures.main_scenario(issue):
        sup = _supplier(db, actor.workspace_id, s["supplier"])
        out.append(documents.upload(db, actor, req.id, s["filename"], fixtures.quote_pdf(s["q"]), "application/pdf", is_sample=True, supplier_id=sup.id, confirmed_by=SAMPLE_CONFIRMER))
    return out


FIXTURE_LABELS = {
    "missing_shipping": "Missing shipping cost", "unclear_currency": "Currency symbol only", "expired": "Expired validity",
    "contradictory": "Contradictory total", "malicious": "Embedded malicious instructions", "scanned": "Scanned image-only PDF (OCR)",
}


def load_fixture(db: Session, actor: Actor, request_id, key: str) -> Document:
    if key not in FIXTURE_LABELS:
        raise AppError("UNKNOWN_FIXTURE", "Unknown fixture.", 404)
    req = get_request(db, actor, request_id)
    q = fixtures.lab_fixtures(timeutil.local_date(req.timezone, req.created_at))[key]
    data = fixtures.image_only_pdf(q) if key == "scanned" else fixtures.quote_pdf(q)
    return documents.upload(db, actor, req.id, f"{q['supplier'].replace(' ', '_')}_{key}_DEMO.pdf", data, "application/pdf", is_sample=True)


def archive(db: Session, actor: Actor) -> dict:
    """Archive demo requests. Provider transaction history is never deleted, refunded or recaptured."""
    actor.require("admin")
    ws = db.get(Workspace, actor.workspace_id)
    if not ws.is_demo:
        raise AppError("NOT_DEMO_WORKSPACE", "Reset is only available in demo workspaces.", 403)
    reqs = db.execute(select(PurchaseRequest).where(PurchaseRequest.workspace_id == ws.id, PurchaseRequest.archived_at.is_(None))).scalars().all()
    kept = 0
    for r in reqs:
        try:
            approvals.invalidate_for_request(db, r, "Demo session archived", actor=actor)
        except AppError:
            kept += 1  # paid or in-flight: archived for display, history preserved
        r.archived_at = timeutil.now()
    audit.record(db, "demo.archived", workspace_id=ws.id, actor_id=actor.user_id, meta={"requests": len(reqs), "with_payment_history": kept})
    return {"archived_requests": len(reqs), "payment_history_preserved": True}


# ---------------------------------------------------------------- Demo Lab ----------
SCENARIOS = {
    "amount_changed": "Amount changed after approval",
    "merchant_changed": "Merchant mapping changed after approval",
    "malicious_pdf": "PDF with embedded instructions",
    "double_click": "Duplicate clicks and concurrent capture",
    "lost_response": "Provider timeout after a successful capture",
}


class _Recorder:
    def __init__(self, run_id):
        self.run_id = run_id

    def step(self, title: str, status: str, detail: str = "", data: dict | None = None):
        with session_scope() as db:
            r = db.get(DemoScenarioRun, self.run_id, with_for_update=True, populate_existing=True)
            r.steps = [*r.steps, {"title": title, "status": status, "detail": detail, "data": data or {}, "at": timeutil.now().isoformat()}]


def start_scenario(db: Session, actor: Actor, scenario: str) -> DemoScenarioRun:
    actor.require("admin")
    s = get_settings()
    ws = db.get(Workspace, actor.workspace_id)
    if not (s.DEMO_LAB_ENABLED and ws.is_demo):
        raise AppError("DEMO_LAB_DISABLED", "Demo Lab runs only in isolated demo workspaces.", 403)
    if scenario not in SCENARIOS:
        raise AppError("UNKNOWN_SCENARIO", "Unknown scenario.", 404)
    running = db.execute(select(func.count()).select_from(DemoScenarioRun).where(DemoScenarioRun.workspace_id == ws.id, DemoScenarioRun.status == "running")).scalar()
    if running >= 2:
        raise AppError("RATE_LIMITED", "Two scenarios are already running in this workspace.", 429)
    run = DemoScenarioRun(workspace_id=ws.id, scenario=scenario, status="running", steps=[], started_by=actor.user_id, started_at=timeutil.now())
    db.add(run)
    db.flush()
    threading.Thread(target=_run_scenario, args=(run.id, scenario, actor), daemon=True).start()
    return run


def _approver(db: Session, actor: Actor) -> Actor:
    return load_actor(db, persona_user(db).id, actor.principal_id, actor.workspace_id)


def _lab_request(actor: Actor, scenario: str, rec: _Recorder, *, adapter: str | None = None, extra_fixture: str | None = None) -> tuple[str, str]:
    """A fresh lab request with its own ClearWave lab supplier + binding, analysed by the normal workflow."""
    with session_scope() as db:
        req = requests_svc.create(db, actor, SAMPLE_TEXT, title=f"[Demo Lab] {SCENARIOS[scenario]}", lab_scenario=scenario)
        requests_svc.confirm(db, actor, req.id, SAMPLE_SPEC, note="Demo Lab fixture requirements")
        main = _supplier(db, actor.workspace_id, "ClearWave Supplies")
        mb = db.execute(select(MerchantBinding).where(MerchantBinding.supplier_id == main.id)).scalar_one()
        n = db.execute(select(func.count()).select_from(Supplier).where(Supplier.workspace_id == actor.workspace_id)).scalar()
        lab = Supplier(workspace_id=actor.workspace_id, name=f"ClearWave Supplies (lab copy {n})", normalized_name=f"clearwave lab {uuid.uuid4().hex[:8]}", created_at=timeutil.now())
        db.add(lab)
        db.flush()
        a = adapter or mb.adapter
        db.add(MerchantBinding(workspace_id=actor.workspace_id, supplier_id=lab.id, adapter=a, merchant_id=mb.merchant_id if a == mb.adapter else "SIMULATED-CLEARWAVE",
                               display_label="Lab binding", status="active", verified_at=timeutil.now(), created_at=timeutil.now(), updated_at=timeutil.now()))
        db.query(DemoScenarioRun).filter(DemoScenarioRun.id == rec.run_id).update({"request_id": req.id})
        issue = timeutil.local_date(req.timezone, req.created_at)
        for s in fixtures.main_scenario(issue):
            sup_id = lab.id if s["key"] == "clearwave" else _supplier(db, actor.workspace_id, s["supplier"]).id
            documents.upload(db, actor, req.id, s["filename"], fixtures.quote_pdf(s["q"]), "application/pdf", is_sample=True, supplier_id=sup_id, confirmed_by=SAMPLE_CONFIRMER)
        if extra_fixture:
            q = fixtures.lab_fixtures(issue)[extra_fixture]
            documents.upload(db, actor, req.id, f"{q['supplier'].replace(' ', '_')}_{extra_fixture}_DEMO.pdf", fixtures.quote_pdf(q), "application/pdf", is_sample=True)
        rid = str(req.id)
    run_analysis(rid)
    with session_scope() as db:
        q = db.execute(select(Quote).where(Quote.request_id == uuid.UUID(rid), Quote.supplier_id == lab.id)).scalar_one()
        qid = str(q.id)
    rec.step("Lab request analysed by the normal workflow", "info", "Three labelled sample quotes extracted and evaluated" + (f", plus the '{extra_fixture}' fixture" if extra_fixture else "") + ".", {"request_id": rid})
    return rid, qid


def _approve(actor: Actor, rid: str, qid: str, rec: _Recorder) -> str:
    with session_scope() as db:
        ap = _approver(db, actor)
        review = approvals.review(db, ap, rid, qid)
        appr = approvals.approve(db, ap, rid, qid, review["terms_hash"], note="Demo Lab approval")
        rec.step("Organisation approval issued", "ok", f"Approved by {ap.label}: {review['terms']['currency']} {review['terms']['amounts']['total']} to merchant {review['terms']['merchant']['merchant_id']}.",
                 {"approval_id": str(appr.id), "snapshot_hash": appr.snapshot_hash})
        return str(appr.id)


def _attempt_checkout(actor: Actor, approval_id: str) -> tuple[dict | None, AppError | None]:
    try:
        return payments.start_checkout(session_scope, actor, approval_id), None
    except AppError as e:
        return None, e


def _run_scenario(run_id, scenario: str, actor: Actor) -> None:
    rec = _Recorder(run_id)
    verdict, summary = "error", ""
    try:
        verdict, summary = globals()[f"_scn_{scenario}"](actor, rec)
        status = "finished"
    except Exception as e:  # report honestly; never claim a result we did not observe
        status = "error"
        rec.step("Scenario error", "failed", f"{type(e).__name__}: {str(e)[:300]}", {"trace": traceback.format_exc()[-800:]})
        summary = "The scenario could not complete; see steps."
    with session_scope() as db:
        r = db.get(DemoScenarioRun, run_id)
        r.status, r.verdict, r.summary, r.finished_at = status, verdict, summary, timeutil.now()


def _scn_amount_changed(actor: Actor, rec: _Recorder):
    rid, qid = _lab_request(actor, "amount_changed", rec)
    appr1 = _approve(actor, rid, qid, rec)
    with session_scope() as db:
        documents.correct(db, actor, qid, "shipping", "50.00", "Supplier emailed a revised quote: shipping $30 → $50", reason="supplier_revision")
    with session_scope() as db:
        documents.correct(db, actor, qid, "total", "590.00", "Same revised quote restates the total as $590", reason="supplier_revision")
    rec.step("Supplier revision recorded through the normal correction service", "info", "Shipping $30.00 → $50.00 and total $570.00 → $590.00 (quote versions 2–3).")
    _, err = _attempt_checkout(actor, appr1)
    a_blocked = err is not None
    rec.step("Checkout attempted with the original approval", "blocked" if a_blocked else "failed", f"{err.code}: {err.message}" if err else "NOT BLOCKED — checkout started.", {"code": err.code if err else None})
    run_analysis(rid)
    appr2 = _approve(actor, rid, qid, rec)
    with session_scope() as db:
        q = db.get(Quote, uuid.UUID(qid))
        # Defence in depth: simulate a change that bypassed every service hook (direct row edit).
        db.execute(update(QuoteVersion).where(QuoteVersion.id == q.current_version_id).values(shipping="70.00", computed_total="610.00", stated_total="610.00"))
    rec.step("Controlled tamper: amount edited directly in the database after re-approval", "info", "Bypasses the invalidation hook to test the execution-time guard: total $590.00 → $610.00.")
    _, err2 = _attempt_checkout(actor, appr2)
    b_blocked = err2 is not None and err2.code in ("SNAPSHOT_CHANGED", "QUOTE_NOT_ELIGIBLE")
    rec.step("Execution-time snapshot check", "blocked" if b_blocked else "failed", f"{err2.code}: {err2.message}" if err2 else "NOT BLOCKED", {"code": err2.code if err2 else None, "changes": (err2.details or {}).get("changes") if err2 else None})
    ok = a_blocked and b_blocked
    return ("blocked_as_expected" if ok else "not_blocked"), ("Both the change hook and the execution-time hash check stopped payment; a fresh approval is required." if ok else "At least one attempt was not blocked.")


def _scn_merchant_changed(actor: Actor, rec: _Recorder):
    rid, qid = _lab_request(actor, "merchant_changed", rec)
    appr1 = _approve(actor, rid, qid, rec)
    with session_scope() as db:
        q = db.get(Quote, uuid.UUID(qid))
        b = db.execute(select(MerchantBinding).where(MerchantBinding.supplier_id == q.supplier_id)).scalar_one()
        original = b.merchant_id
        merchants.change_merchant(db, actor, b.id, "ATTACKER-MERCHANT-01", "Controlled test: payee mapping changed after approval")
    rec.step("Admin changed the payee mapping after approval", "info", f"Merchant {original} → ATTACKER-MERCHANT-01 (binding version bumped).")
    _, err = _attempt_checkout(actor, appr1)
    a_blocked = err is not None
    rec.step("Checkout attempted with the original approval", "blocked" if a_blocked else "failed", f"{err.code}: {err.message}" if err else "NOT BLOCKED", {"code": err.code if err else None})
    with session_scope() as db:
        b = db.execute(select(MerchantBinding).where(MerchantBinding.supplier_id == db.get(Quote, uuid.UUID(qid)).supplier_id).with_for_update().execution_options(populate_existing=True)).scalar_one()
        b.merchant_id, b.version = original, b.version + 1
    run_analysis(rid)
    appr2 = _approve(actor, rid, qid, rec)
    with session_scope() as db:
        db.execute(update(MerchantBinding).where(MerchantBinding.supplier_id == db.get(Quote, uuid.UUID(qid)).supplier_id).values(merchant_id="ATTACKER-MERCHANT-02"))
    rec.step("Controlled tamper: payee edited directly in the database after re-approval", "info", "Bypasses the service layer to test the execution-time guard.")
    _, err2 = _attempt_checkout(actor, appr2)
    b_blocked = err2 is not None
    rec.step("Execution-time merchant check", "blocked" if b_blocked else "failed", f"{err2.code}: {err2.message}" if err2 else "NOT BLOCKED",
             {"code": err2.code if err2 else None, "changes": (err2.details or {}).get("changes") if err2 else None})
    with session_scope() as db:
        db.execute(update(MerchantBinding).where(MerchantBinding.supplier_id == db.get(Quote, uuid.UUID(qid)).supplier_id).values(merchant_id=original))
    ok = a_blocked and b_blocked
    return ("blocked_as_expected" if ok else "not_blocked"), ("Payment cannot be redirected: the approved merchant identity is part of the hashed snapshot." if ok else "A merchant change was not blocked.")


def _scn_malicious_pdf(actor: Actor, rec: _Recorder):
    rid, _ = _lab_request(actor, "malicious_pdf", rec, extra_fixture="malicious")
    with session_scope() as db:
        req = db.get(PurchaseRequest, uuid.UUID(rid))
        doc = db.execute(select(Document).where(Document.request_id == req.id, Document.filename.like("%malicious%"))).scalar_one()
        q = db.execute(select(Quote).where(Quote.document_id == doc.id)).scalar_one()
        qv = db.get(QuoteVersion, q.current_version_id)
        rv, spec = requests_svc.current_spec(db, req)
        view = comparison.comparison(db, actor, req)
        outcome = next(x["outcome"] for x in view["quotes"] if x["quote_id"] == str(q.id))
        rec.step("Suspicious text detected (informative signal only)", "info" if doc.suspicious else "warning",
                 "; ".join(f"p{h['page']}: {h['label']} — “{h['excerpt'][:90]}”" for h in (doc.suspicious or [])) or "No pattern matched — the controls below still apply.")
        rec.step("Extracted facts are plain data", "ok", f"Supplier {qv.supplier_name}; total {qv.currency} {qv.stated_total}; method {qv.extraction_method}.")
        budget_ok = str(spec.budget_amount) == "600.00" and rv.version == 1
        rec.step("Budget policy unchanged", "ok" if budget_ok else "failed", f"Requirements still version {rv.version} with budget {spec.currency} {spec.budget_amount}.")
        rec.step("Deterministic policy outcome", "blocked" if outcome["mandatory_status"] != "pass" else "failed",
                 "; ".join(f"{c['label']}: {c['status']}" for c in outcome["checks"] if c["status"] != "pass") or "All checks passed")
        payee_ok = q.supplier_link != "confirmed" and not outcome["checkout_available"]
        rec.step("Payee from PDF ignored", "ok" if payee_ok else "failed", "The email in the PDF is not a payee. Supplier link is only 'suggested', so checkout is unavailable.")
        try:
            approvals.approve(db, _approver(db, actor), rid, str(q.id), "0" * 64, note="attempt")
            blocked, msg = False, "Approval succeeded"
        except AppError as e:
            blocked, msg = True, f"{e.code}: {e.message}"
        rec.step("Approval attempt for the malicious quote", "blocked" if blocked else "failed", msg)
        rec.step("Model tool permissions", "ok", "The extraction model receives page text only and returns JSON. It has no approval, payment, HTTP, file or shell tools.")
    ok = budget_ok and payee_ok and blocked and outcome["mandatory_status"] != "pass"
    return ("blocked_as_expected" if ok else "not_blocked"), ("Embedded instructions stayed data: budget, permissions and payee were unaffected. This is one fixture, not proof of immunity." if ok else "A control did not hold.")


def _sim_approved_checkout(actor: Actor, rec: _Recorder, scenario: str) -> tuple[str, str]:
    rid, qid = _lab_request(actor, scenario, rec, adapter="simulated")
    appr = _approve(actor, rid, qid, rec)
    return rid, appr


def _scn_double_click(actor: Actor, rec: _Recorder):
    rid, appr = _sim_approved_checkout(actor, rec, "double_click")
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda _: _attempt_checkout(actor, appr), range(5)))
    op_ids = {r[0]["id"] for r in results if r[0]}
    with session_scope() as db:
        op = db.execute(select(PaymentOperation).where(PaymentOperation.approval_id == uuid.UUID(appr))).scalar_one()
        creates = db.execute(select(func.count()).select_from(ProviderTransaction).where(ProviderTransaction.operation_id == op.id, ProviderTransaction.call == "create_order")).scalar()
    rec.step("5 simultaneous 'Pay' clicks", "ok" if len(op_ids) == 1 and creates == 1 else "failed", f"{len(op_ids)} payment operation(s), {creates} provider order-create call(s).", {"operations": list(op_ids), "order_creates": creates})
    payments.simulated_buyer_approve(session_scope, actor, str(op.id))
    rec.step("Simulated buyer approval", "info", "Stands in for the PayPal buyer login in this controlled test.")
    with ThreadPoolExecutor(max_workers=5) as pool:
        caps = list(pool.map(lambda _: _try(lambda: payments.capture(session_scope, actor, str(op.id))), range(5)))
    with session_scope() as db:
        op = db.get(PaymentOperation, op.id)
        sim = db.get(SimulatedProviderOrder, op.provider_order_id)
        capture_calls = db.execute(select(func.count()).select_from(ProviderTransaction).where(ProviderTransaction.operation_id == op.id, ProviderTransaction.call == "capture")).scalar()
        provider_captures = sim.capture_calls
    ok = len(op_ids) == 1 and creates == 1 and provider_captures == 1 and op.state == "completed"
    rec.step("5 simultaneous capture requests", "ok" if ok else "failed",
             f"Final state {op.state}; {capture_calls} capture call(s) sent; provider recorded {provider_captures} capture. Other requests saw the in-progress/completed operation.",
             {"responses": [c.get("state") if isinstance(c, dict) else c for c in caps]})
    return ("one_operation" if ok else "duplicate_detected"), ("One logical payment, one provider capture." if ok else "Duplicate work was observed.")


def _try(fn):
    try:
        return fn()
    except AppError as e:
        return e.code


def _scn_lost_response(actor: Actor, rec: _Recorder):
    rid, appr = _sim_approved_checkout(actor, rec, "lost_response")
    op = payments.start_checkout(session_scope, actor, appr)
    payments.simulated_buyer_approve(session_scope, actor, op["id"])
    with session_scope() as db:
        payments._lock_op(db, uuid.UUID(op["id"])).fault_injection = "drop_capture_response"
    rec.step("Fault injection armed", "info", "The provider adapter will perform the capture but its response will be discarded.")
    res = payments.capture(session_scope, actor, op["id"])
    rec.step("Capture response lost", "ok" if res["state"] == "reconciling" else "failed", f"Payment state after the lost response: {res['state']} (not 'failed', not 'paid').")
    res2 = payments.reconcile(session_scope, op["id"], source="demo-lab")
    with session_scope() as db:
        sim = db.get(SimulatedProviderOrder, res2["provider_order_id"])
        ops = db.execute(select(func.count()).select_from(PaymentOperation).where(PaymentOperation.request_id == uuid.UUID(rid))).scalar()
    ok = res["state"] == "reconciling" and res2["state"] == "completed" and sim.capture_calls == 1 and ops == 1
    rec.step("Reconciled through provider lookup", "ok" if ok else "failed",
             f"Looked up order {res2['provider_order_id']}: capture {res2['provider_capture_id']} COMPLETED. Provider captures: {sim.capture_calls}; payment operations: {ops}; no replacement order created.")
    return ("recovered" if ok else "not_recovered"), ("The lost response became 'reconciling' and recovered to one confirmed capture." if ok else "Recovery did not behave as expected.")


def scenario_json(r: DemoScenarioRun) -> dict:
    return {"id": str(r.id), "scenario": r.scenario, "title": SCENARIOS.get(r.scenario, r.scenario), "status": r.status, "verdict": r.verdict, "summary": r.summary,
            "request_id": str(r.request_id) if r.request_id else None, "steps": r.steps, "started_at": r.started_at.isoformat(), "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "controlled_test": True}


def ensure_demo_account(db: Session) -> None:
    """Seed the shared jury login from environment configuration (never hardcoded)."""
    s = get_settings()
    if not (s.DEMO_ACCOUNT_USERNAME and s.DEMO_ACCOUNT_PASSWORD):
        return
    u = db.execute(select(User).where(User.username == s.DEMO_ACCOUNT_USERNAME)).scalar_one_or_none()
    if u is None:
        db.add(User(email=f"{s.DEMO_ACCOUNT_USERNAME.lower()}@demo.quoteguard.invalid", username=s.DEMO_ACCOUNT_USERNAME, display_name=f"{s.DEMO_ACCOUNT_USERNAME} · Demo requester",
                    password_hash=hash_password(s.DEMO_ACCOUNT_PASSWORD), is_demo_account=True, created_at=timeutil.now()))
    persona_user(db)


__all__ = ["provision_workspace", "start_sample", "load_sample_quotes", "load_fixture", "archive", "start_scenario", "scenario_json", "SCENARIOS", "FIXTURE_LABELS", "Approval"]
