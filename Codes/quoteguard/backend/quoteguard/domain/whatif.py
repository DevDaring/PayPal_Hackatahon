"""What-if previews: recompute from existing facts. Previews never reach payment."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from ..money import fmt
from .policy import QuoteFacts, evaluate_all, summarize
from .requirements import RequirementSpec


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def preview(
    spec: RequirementSpec,
    facts: list[QuoteFacts],
    order_date: date,
    *,
    budget: Decimal | None = None,
    deadline_days: int | None = None,
    quantity: int | None = None,
) -> dict:
    base = evaluate_all(spec, facts, order_date)
    new_spec = spec.model_copy(deep=True)
    if budget is not None:
        new_spec.budget_amount = budget
    if deadline_days is not None:
        new_spec.deadline_days = deadline_days
        new_spec.deadline_date = order_date + timedelta(days=deadline_days)

    notes: list[str] = []
    new_facts = facts
    if quantity is not None and quantity != spec.quantity:
        new_spec.quantity = quantity
        new_facts = []
        for f in facts:
            if f.scalable_pricing and f.flat_shipping and f.unit_price is not None:
                sub = (f.unit_price * quantity).quantize(Decimal("0.01"))
                new_facts.append(replace(f, quantity=quantity, subtotal=sub, stated_total=None))
                notes.append(f"{f.supplier}: quoted terms state the unit price applies at this quantity, so the subtotal was recalculated.")
            else:
                notes.append(f"{f.supplier}: pricing terms do not say the unit price holds at {quantity} units — a revised quote is required.")
                new_facts.append(f)
    after = evaluate_all(new_spec, new_facts, order_date)

    changes = []
    before_by = {o.quote_id: o for o in base}
    cur = spec.currency
    for o in after:
        b = before_by[o.quote_id]
        if b.mandatory_status != o.mandatory_status:
            lever = []
            if budget is not None and budget != spec.budget_amount:
                lever.append(f"{'increasing' if budget > spec.budget_amount else 'reducing'} the budget from {cur} {fmt(spec.budget_amount)} to {cur} {fmt(budget)}")
            if deadline_days is not None and deadline_days != spec.deadline_days:
                lever.append(f"changing the delivery window from {spec.deadline_days} to {deadline_days} days")
            if quantity is not None and quantity != spec.quantity:
                lever.append(f"changing quantity to {quantity}")
            verb = {"pass": "makes {s} compliant", "fail": "makes {s} non-compliant", "unknown": "leaves {s} undetermined"}[o.mandatory_status]
            changes.append({
                "quote_id": o.quote_id,
                "supplier": o.supplier,
                "before": b.mandatory_status,
                "after": o.mandatory_status,
                "sentence": _cap(" and ".join(lever) or "This change") + " " + verb.format(s=o.supplier) + ".",
            })
    s_before, s_after = summarize(base, facts), summarize(after, new_facts)
    if s_before["best_compliant_quote_id"] != s_after["best_compliant_quote_id"]:
        if s_after["no_compliant_quote"]:
            notes.append("No quote is fully compliant under these settings, so nothing is recommended.")
        else:
            notes.append(f"The best compliant quote would become {s_after['best_compliant_supplier']} ({cur} {s_after['best_compliant_total']}).")
    elif not s_after["no_compliant_quote"]:
        notes.append(f"{s_after['best_compliant_supplier']} remains the best compliant quote.")
    return {
        "preview_only": True,
        "inputs": {"budget": fmt(new_spec.budget_amount), "deadline_days": new_spec.deadline_days, "deadline_date": new_spec.deadline_date.isoformat() if new_spec.deadline_date else None, "quantity": new_spec.quantity},
        "outcomes": [o.as_dict() for o in after],
        "summary": s_after,
        "changes": changes,
        "notes": notes,
    }
