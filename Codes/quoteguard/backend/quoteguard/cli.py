"""Operational commands: `python -m quoteguard.cli <command>`.

  seed                 create policy row, demo login and the normal-mode workspace (from .env)
  archive-demo         admin cleanup: archive demo workspaces older than N hours (history preserved)
  run-eval [llm|rules] run the labelled evaluation set and store measured results
  export-fixtures DIR  write sample PDFs + the separate evaluation manifest
  register-webhook URL create the PayPal sandbox webhook subscription and print its ID
  run-integrity-bench  score the document-integrity analyzer on the labelled forensic benchmark and store it
"""

from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from . import timeutil
from .config import get_settings
from .db import session_scope
from .models import Membership, MerchantBinding, Supplier, User, Workspace
from .security import hash_password
from .services import comparison, demo, evaluation
from .services.documents import normalize_name


def _user(db, email: str, password: str, name: str) -> User:
    u = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
    if u is None:
        u = User(email=email.lower(), display_name=name, password_hash=hash_password(password), created_at=timeutil.now())
        db.add(u)
        db.flush()
    return u


def seed() -> None:
    s = get_settings()
    with session_scope() as db:
        comparison.policy_row(db)
        demo.ensure_demo_account(db)
        if s.DEMO_REQUESTER_EMAIL and s.DEMO_APPROVER_EMAIL and s.ADMIN_EMAIL:
            ws = db.execute(select(Workspace).where(Workspace.name == "Northwind Support Ops", Workspace.is_demo.is_(False))).scalar_one_or_none()
            if ws is None:
                ws = Workspace(name="Northwind Support Ops", is_demo=False, self_approval_allowed=False, created_at=timeutil.now())
                db.add(ws)
                db.flush()
                for email, pw, name, roles in ((s.DEMO_REQUESTER_EMAIL, s.DEMO_REQUESTER_PASSWORD, "Riya Sen · Requester", ["requester"]),
                                               (s.DEMO_APPROVER_EMAIL, s.DEMO_APPROVER_PASSWORD, "Marcus Hale · Approver", ["approver"]),
                                               (s.ADMIN_EMAIL, s.ADMIN_PASSWORD, "Operations Admin", ["admin", "approver"])):
                    u = _user(db, email, pw, name)
                    db.add(Membership(workspace_id=ws.id, user_id=u.id, roles=roles, created_at=timeutil.now()))
                adapter, mid = demo.merchant_adapter()
                for name, bind in (("Northstar Office", False), ("ClearWave Supplies", True), ("Harbor Devices", False)):
                    sup = Supplier(workspace_id=ws.id, name=name, normalized_name=normalize_name(name), created_at=timeutil.now())
                    db.add(sup)
                    db.flush()
                    if bind and adapter == "sandbox" and mid != "UNCONFIGURED":
                        db.add(MerchantBinding(workspace_id=ws.id, supplier_id=sup.id, adapter="sandbox", merchant_id=mid, display_label="PayPal Sandbox merchant", status="active",
                                               verified_at=timeutil.now(), created_at=timeutil.now(), updated_at=timeutil.now()))
    print("seed complete")


def archive_demo(hours: int = 48) -> None:
    cutoff = timeutil.now() - timedelta(hours=hours)
    with session_scope() as db:
        rows = db.execute(select(Workspace).where(Workspace.is_demo.is_(True), Workspace.archived_at.is_(None), Workspace.created_at < cutoff)).scalars().all()
        for w in rows:
            w.archived_at = timeutil.now()  # payment and audit history are retained
    print(f"archived {len(rows)} demo workspace(s)")


def run_eval(mode: str = "llm", dataset: str = "quoteguard-eval-v1") -> None:
    run_id = evaluation.create_run(None, mode, dataset)
    summary = evaluation.execute(run_id)
    print(json.dumps({"run_id": str(run_id), **{k: summary[k] for k in ("cases", "decision_agreement", "evidence", "unsafe_payment_attempts", "false_blocking")}}, indent=2))


def export_fixtures(out: str) -> None:
    from . import fixtures

    d = Path(out)
    (d / "eval").mkdir(parents=True, exist_ok=True)
    (d / "samples").mkdir(parents=True, exist_ok=True)
    issue = fixtures.EVAL_SCENARIO_DATE
    for s in fixtures.main_scenario(issue):
        (d / "samples" / s["filename"]).write_bytes(fixtures.quote_pdf(s["q"]))
    for k, q in fixtures.lab_fixtures(issue).items():
        (d / "samples" / f"{k}_DEMO.pdf").write_bytes(fixtures.image_only_pdf(q) if k == "scanned" else fixtures.quote_pdf(q))
    manifest = []
    for c in fixtures.eval_cases():
        name = f"{c['case_id']}.pdf"
        (d / "eval" / name).write_bytes(fixtures.image_only_pdf(c["q"]) if c["kind"] == "image" else fixtures.quote_pdf(c["q"]))
        manifest.append({"case_id": c["case_id"], "file": name, "category": c["category"], "expected": c["expected"], "expected_decision": c["expected_decision"]})
    # Expected labels live in a separate manifest that is never given to the model.
    (d / "eval_manifest.json").write_text(json.dumps({"dataset_version": fixtures.EVAL_DATASET_VERSION, "scenario_date": issue.isoformat(), "cases": manifest}, indent=2))
    from . import holdout

    (d / "holdout").mkdir(parents=True, exist_ok=True)
    for c in holdout.holdout_cases():
        (d / "holdout" / f"{c['case_id']}.pdf").write_bytes(c["pdf"]())
    (d / "holdout_manifest.json").write_text(json.dumps(holdout.manifest(), indent=2))
    print(f"wrote fixtures to {d}")


def run_integrity_bench(out_dir: str | None = None) -> None:
    from . import integrity_bench
    from .documents.integrity import INTEGRITY_VERSION
    from .models import EvaluationRun

    result = integrity_bench.run()
    with session_scope() as db:
        db.add(EvaluationRun(status="finished", dataset_version=integrity_bench.BENCH_VERSION, provider="deterministic", model=INTEGRITY_VERSION, extraction_mode="forensics",
                             code_revision=evaluation._code_revision(), config={"members": integrity_bench.MEMBERS}, summary=result, started_at=timeutil.now(), finished_at=timeutil.now()))
    if out_dir:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / f"integrity-{timeutil.now():%Y%m%d-%H%M%S}.json").write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps({k: v for k, v in result["summary"].items() if k != "by_category"}, indent=2))


def register_webhook(url: str) -> None:
    from .paypal.sandbox import PayPalSandbox

    pp = PayPalSandbox()
    for w in pp.list_webhooks():
        if w["url"] == url:
            print(f"existing webhook {w['id']}")
            return
    events = ["CHECKOUT.ORDER.APPROVED", "CHECKOUT.ORDER.COMPLETED", "PAYMENT.CAPTURE.COMPLETED", "PAYMENT.CAPTURE.PENDING", "PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.REFUNDED", "PAYMENT.CAPTURE.REVERSED"]
    print(f"created webhook {pp.create_webhook(url, events)['id']}")


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["help"]
    {"seed": lambda: seed(), "archive-demo": lambda: archive_demo(int(args[0]) if args else 48), "run-eval": lambda: run_eval(args[0] if args else "llm", args[1] if len(args) > 1 else "quoteguard-eval-v1"),
     "export-fixtures": lambda: export_fixtures(args[0] if args else "../fixtures"), "register-webhook": lambda: register_webhook(args[0]),
     "run-integrity-bench": lambda: run_integrity_bench(args[0] if args else None)}.get(cmd, lambda: print(__doc__))()
