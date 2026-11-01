"""Measured evaluation over the labelled fixture set. Results are stored as produced; nothing is prefilled."""

from __future__ import annotations

import subprocess
import time
import uuid
from datetime import date, timedelta
from decimal import Decimal

from .. import timeutil
from ..ai import quote_extractor
from ..config import get_settings
from ..db import session_scope
from ..documents.evidence import snippet_on_page, value_supported
from ..documents.parse_child import parse
from ..domain import policy
from ..domain.requirements import RequirementSpec, criterion_for
from ..fixtures import EVAL_DATASET_VERSION, EVAL_SCENARIO_DATE, eval_cases, image_only_pdf, quote_pdf
from ..models import EvaluationCase, EvaluationRun
from ..money import to_money
from .documents import _date, _int, _ocr_pages

FIELDS = ["supplier_name", "currency", "quantity", "subtotal", "shipping", "tax", "total", "delivery_days", "valid_until", "attr:connector"]


def eval_spec() -> RequirementSpec:
    return RequirementSpec(item="USB-C headsets with microphones", quantity=30, budget_amount=Decimal("600.00"), currency="USD", deadline_days=7,
                           deadline_date=EVAL_SCENARIO_DATE + timedelta(days=7), mandatory=[criterion_for("connector", "USB-C"), criterion_for("microphone", "yes")])


def _code_revision() -> str | None:
    s = get_settings()
    if s.CODE_REVISION:
        return s.CODE_REVISION
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=3).stdout.strip() or None
    except Exception:
        return None


def _same(field: str, expected, actual) -> bool:
    if expected is None or actual is None:
        return expected is None and actual is None
    if field in ("subtotal", "shipping", "tax", "total"):
        return to_money(str(expected)) == to_money(str(actual))
    if field in ("quantity", "delivery_days"):
        return _int(expected) == _int(actual)
    if field == "supplier_name":
        return str(expected).lower().strip(" .") in str(actual).lower() or str(actual).lower().strip(" .") in str(expected).lower()
    if field == "attr:connector":
        return str(expected).upper().replace(" ", "-") == str(actual).upper().replace(" ", "-").replace("TYPE-", "")
    return str(expected).strip().upper() == str(actual).strip().upper()


DATASETS = ("quoteguard-eval-v1", "quoteguard-holdout-v1")


def _cases(dataset: str) -> list[dict]:
    if dataset == "quoteguard-holdout-v1":
        from ..holdout import holdout_cases

        return [{**c, "kind": "image" if c["category"] == "ocr" else "text"} for c in holdout_cases()]
    return eval_cases()


def create_run(triggered_by, mode: str, dataset: str = EVAL_DATASET_VERSION) -> uuid.UUID:
    if dataset not in DATASETS:
        raise ValueError("unknown dataset")
    s = get_settings()
    mode = "llm" if mode == "llm" and s.ai_configured else "rules"
    with session_scope() as db:
        run = EvaluationRun(status="running", dataset_version=dataset, provider=s.AI_PROVIDER if mode == "llm" else "none", model=s.AI_MODEL if mode == "llm" else "deterministic-rules-v1",
                            extraction_mode=mode, code_revision=_code_revision(), triggered_by=triggered_by, started_at=timeutil.now(),
                            config={"scenario_date": EVAL_SCENARIO_DATE.isoformat(), "budget": "600.00", "deadline_days": 7, "ocr_provider": s.OCR_PROVIDER or None, "checkout_assumed_configured": True,
                                    "labels_visible_to_model": False})
        db.add(run)
        db.flush()
        return run.id


def execute(run_id) -> dict:
    with session_scope() as db:
        run = db.get(EvaluationRun, uuid.UUID(str(run_id)))
        mode = run.extraction_mode
    spec = eval_spec()
    totals = {f: [0, 0] for f in FIELDS}
    ev_checked = ev_correct = agree = n = unsafe = unsafe_blocked = should_pass = false_block = 0
    by_cat: dict[str, list[int]] = {}
    latencies = []
    with session_scope() as db:
        dataset = db.get(EvaluationRun, uuid.UUID(str(run_id))).dataset_version
    t_start = timeutil.now()
    review = 0
    for case in _cases(dataset):
        n += 1
        t0 = time.monotonic()
        err = None
        actual_decision = None
        field_results = {}
        blocked = True
        ev_c = ev_ok = 0
        try:
            pdf = case["pdf"]() if "pdf" in case else (image_only_pdf(case["q"]) if case["kind"] == "image" else quote_pdf(case["q"]))
            pages = parse(pdf, 20)["pages"]
            ocr = False
            if all(len("".join((p["text"] or "").split())) < 25 for p in pages):
                texts = _ocr_pages(pdf, [p["page_number"] for p in pages], None, None)
                for p in pages:
                    p["text"], p["words"] = texts.get(p["page_number"], ""), []
                ocr = bool(texts)
            if not any((p["text"] or "").strip() for p in pages):
                actual_decision = "unknown"
                err = "Image-only PDF and OCR unavailable: requested a text-readable PDF."
                ex = None
            else:
                ex, meta = quote_extractor.extract(pages, ["connector", "microphone"], force_rules=(mode == "rules"))
            if ex is not None:
                by_page = {p["page_number"]: p["text"] for p in pages}
                values = {f: (ex.attributes.get("connector").value if ex.attributes.get("connector") else None) if f == "attr:connector" else getattr(ex, f).value for f in FIELDS}
                for f in FIELDS:
                    ok = _same(f, case["expected"].get(f), values[f])
                    field_results[f] = {"expected": case["expected"].get(f), "actual": None if values[f] is None else str(values[f]), "correct": ok}
                    totals[f][1] += 1
                    totals[f][0] += int(ok)
                cited = [getattr(ex, f) for f in ex.model_fields if hasattr(getattr(ex, f), "source_text")] + list(ex.attributes.values())
                for c in cited:
                    if c.value is not None and c.source_text:
                        ev_c += 1
                        good = c.page in by_page and snippet_on_page(c.source_text, by_page[c.page]) and (not str(c.value).replace(".", "").isdigit() or value_supported(c.value, c.source_text))
                        ev_ok += int(bool(good))
                cur = ex.currency.value.upper() if isinstance(ex.currency.value, str) and len(ex.currency.value) == 3 else None
                facts = policy.QuoteFacts(case["case_id"], str(ex.supplier_name.value), cur, "unknown" if cur is None else ("explicit" if ex.currency_explicit else "inferred"),
                                          _int(ex.quantity.value), to_money(ex.subtotal.value), to_money(ex.shipping.value), to_money(ex.tax.value), to_money(ex.discount.value), to_money(ex.total.value),
                                          _int(ex.delivery_days.value), _date(ex.valid_until.value), {k: v.value for k, v in ex.attributes.items()}, needs_review=ocr or any(i.split(":")[0] in ("subtotal", "shipping", "tax", "total", "quantity") for i in meta.get("issues", [])),
                                          checkout_available=True, unit_price=to_money(ex.unit_price.value),
                                          attribute_sources={k: v.source_text for k, v in ex.attributes.items() if v.source_text})
                o = policy.evaluate_all(spec, [facts], EVAL_SCENARIO_DATE)[0]
                actual_decision, blocked = o.mandatory_status, not o.payment_eligible
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:200]}"
            actual_decision, blocked = "error", True
        ms = int((time.monotonic() - t0) * 1000)
        latencies.append(ms)
        ev_checked += ev_c
        ev_correct += ev_ok
        review += int(actual_decision in ("unknown", "error"))
        a = actual_decision == case["expected_decision"]
        agree += int(a)
        cat = by_cat.setdefault(case["category"], [0, 0])
        cat[0] += int(a)
        cat[1] += 1
        is_unsafe = case["expected_decision"] != "pass"
        unsafe += int(is_unsafe)
        unsafe_blocked += int(is_unsafe and blocked)
        should_pass += int(not is_unsafe)
        false_block += int((not is_unsafe) and blocked)
        with session_scope() as db:
            db.add(EvaluationCase(run_id=uuid.UUID(str(run_id)), case_id=case["case_id"], category=case["category"], field_results=field_results, evidence_checked=ev_c, evidence_correct=ev_ok,
                                  decision_expected=case["expected_decision"], decision_actual=actual_decision, unsafe_expected_blocked=(blocked if is_unsafe else None), payment_blocked=blocked, latency_ms=ms, error=err))
    summary = {
        "cases": n,
        "field_accuracy": {f: {"correct": c, "total": t, "accuracy": round(c / t, 4) if t else None} for f, (c, t) in totals.items()},
        "evidence": {"checked": ev_checked, "correct": ev_correct, "rate": round(ev_correct / ev_checked, 4) if ev_checked else None},
        "decision_agreement": {"agree": agree, "total": n, "rate": round(agree / n, 4) if n else None},
        "by_category": {k: {"agree": v[0], "total": v[1]} for k, v in by_cat.items()},
        "unsafe_payment_attempts": {"blocked": unsafe_blocked, "total": unsafe},
        "false_blocking": {"blocked": false_block, "total": should_pass},
        "latency_ms": {"samples": latencies, "count": len(latencies), "median": sorted(latencies)[len(latencies) // 2] if latencies else None},
        "confidence_note": "No model confidence percentages are reported; extraction status categories are used instead.",
        "review_burden": {"needs_review": review, "total": n, "note": "Cases ending 'unknown' need a person (ask supplier or correct a field)."},
        "false_eligibility": {"count": unsafe - unsafe_blocked, "total": unsafe},
        "tokens": _tokens_since(t_start),
    }
    with session_scope() as db:
        run = db.get(EvaluationRun, uuid.UUID(str(run_id)))
        run.status, run.summary, run.finished_at = "finished", summary, timeutil.now()
    return summary


def run_json(run: EvaluationRun, cases: list[EvaluationCase] | None = None) -> dict:
    out = {"id": str(run.id), "status": run.status, "dataset_version": run.dataset_version, "provider": run.provider, "model": run.model, "extraction_mode": run.extraction_mode,
           "code_revision": run.code_revision, "config": run.config, "summary": run.summary, "started_at": run.started_at.isoformat(), "finished_at": run.finished_at.isoformat() if run.finished_at else None}
    if cases is not None:
        out["cases"] = [{"case_id": c.case_id, "category": c.category, "field_results": c.field_results, "evidence_checked": c.evidence_checked, "evidence_correct": c.evidence_correct,
                         "decision_expected": c.decision_expected, "decision_actual": c.decision_actual, "payment_blocked": c.payment_blocked, "latency_ms": c.latency_ms, "error": c.error} for c in cases]
    return out


__all__ = ["create_run", "execute", "run_json", "date"]


def _tokens_since(start) -> dict:
    """Measured model usage during this run (evaluation calls have no workspace)."""
    from sqlalchemy import func, select

    from ..models import AICall

    with session_scope() as db:
        calls, pt, ct = db.execute(select(func.count(), func.coalesce(func.sum(AICall.prompt_tokens), 0), func.coalesce(func.sum(AICall.completion_tokens), 0))
                                   .where(AICall.workspace_id.is_(None), AICall.created_at >= start, AICall.purpose == "extract_quote")).one()
    return {"model_calls": calls, "prompt_tokens": int(pt), "completion_tokens": int(ct)}
