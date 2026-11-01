"""Deterministic policy evaluation. The LLM never decides totals or eligibility.

Mandatory checks resolve to pass, fail or unknown. Missing evidence is unknown, never pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from ..money import SUPPORTED_CHECKOUT_CURRENCIES, fmt
from .attributes import assess
from .requirements import RequirementSpec

POLICY_NAME = "quoteguard-default"
POLICY_VERSION = 1
POLICY_RULES = {
    "ranking": ["verified_total_asc", "delivery_days_asc"],
    "mandatory": ["currency", "quantity", "cost_known", "budget", "delivery", "validity", "attributes"],
    "payment_eligibility": "all mandatory pass AND amounts verified AND not expired AND checkout configured AND currency supported",
    "excluded_ranking_inputs": ["demographics", "language", "inferred nationality"],
}


@dataclass
class QuoteFacts:
    quote_id: str
    supplier: str
    currency: str | None
    currency_status: str  # explicit | inferred | unknown
    quantity: int | None
    subtotal: Decimal | None
    shipping: Decimal | None
    tax: Decimal | None
    discount: Decimal | None
    stated_total: Decimal | None
    delivery_days: int | None
    valid_until: date | None
    attributes: dict = field(default_factory=dict)
    needs_review: bool = False
    checkout_available: bool = False
    unit_price: Decimal | None = None
    scalable_pricing: bool = False
    flat_shipping: bool = False
    attribute_sources: dict = field(default_factory=dict)  # attribute key -> cited source sentence


@dataclass
class Check:
    key: str
    label: str
    status: str  # pass | fail | unknown
    detail: str
    fields: list[str]

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "status": self.status, "detail": self.detail, "fields": self.fields}


@dataclass
class QuoteOutcome:
    quote_id: str
    supplier: str
    checks: list[Check]
    mandatory_status: str
    verified_total: Decimal | None
    computed_total: Decimal | None
    arithmetic_status: str
    estimated_delivery: date | None
    checkout_available: bool
    payment_eligible: bool
    compliant_rank: int | None = None

    def as_dict(self) -> dict:
        return {
            "quote_id": self.quote_id,
            "supplier": self.supplier,
            "checks": [c.as_dict() for c in self.checks],
            "mandatory_status": self.mandatory_status,
            "verified_total": fmt(self.verified_total),
            "computed_total": fmt(self.computed_total),
            "arithmetic_status": self.arithmetic_status,
            "estimated_delivery": self.estimated_delivery.isoformat() if self.estimated_delivery else None,
            "checkout_available": self.checkout_available,
            "payment_eligible": self.payment_eligible,
            "compliant_rank": self.compliant_rank,
        }


def arithmetic(f: QuoteFacts) -> tuple[Decimal | None, str]:
    """Return (computed_total, status). Incomplete when any component is not stated."""
    parts = [f.subtotal, f.shipping, f.tax]
    if any(p is None for p in parts):
        return None, "incomplete"
    computed = f.subtotal + f.shipping + f.tax - (f.discount or Decimal("0"))
    if f.unit_price is not None and f.quantity is not None and (f.unit_price * f.quantity).quantize(Decimal("0.01")) != f.subtotal:
        return computed, "contradictory"
    if f.stated_total is not None and f.stated_total != computed:
        return computed, "contradictory"
    return computed, "consistent"


def _money(d: Decimal | None, cur: str | None) -> str:
    return "unknown" if d is None else f"{cur or ''} {fmt(d)}".strip()


def evaluate(spec: RequirementSpec, f: QuoteFacts, order_date: date, quantity_override: int | None = None) -> QuoteOutcome:
    checks: list[Check] = []
    cur = spec.currency

    # Currency: never invent exchange rates.
    if f.currency is None or f.currency_status == "unknown":
        checks.append(Check("currency", "Currency", "unknown", "The quote does not state a currency.", ["currency"]))
    elif f.currency != cur:
        checks.append(Check("currency", "Currency", "fail", f"Quote is in {f.currency}; budget is in {cur}. No exchange rate is assumed.", ["currency"]))
    elif f.currency_status != "explicit":
        checks.append(Check("currency", "Currency", "unknown", f"Currency {f.currency} is inferred from symbols, not stated.", ["currency"]))
    else:
        checks.append(Check("currency", "Currency", "pass", f"Quoted in {f.currency}.", ["currency"]))

    wanted_qty = quantity_override or spec.quantity
    if f.quantity is None:
        checks.append(Check("quantity", "Quantity", "unknown", "Quoted quantity is not stated.", ["quantity"]))
    elif f.quantity != wanted_qty:
        checks.append(Check("quantity", "Quantity", "fail", f"Quote covers {f.quantity} units; request is for {wanted_qty}.", ["quantity"]))
    else:
        checks.append(Check("quantity", "Quantity", "pass", f"{f.quantity} units quoted.", ["quantity"]))

    computed, arith = arithmetic(f)
    missing = [n for n, v in (("item subtotal", f.subtotal), ("shipping", f.shipping), ("tax", f.tax)) if v is None]
    if missing:
        checks.append(Check("cost_known", "All costs stated", "unknown", f"Not stated in the quote: {', '.join(missing)}. Ask the supplier before comparing.", ["subtotal", "shipping", "tax"]))
    elif arith == "contradictory":
        detail = f"Stated total {_money(f.stated_total, f.currency)} does not equal computed {_money(computed, f.currency)}."
        if f.unit_price is not None and f.quantity is not None and f.unit_price * f.quantity != f.subtotal:
            detail = f"Unit price × quantity ({_money(f.unit_price * f.quantity, f.currency)}) does not equal the subtotal {_money(f.subtotal, f.currency)}."
        checks.append(Check("cost_known", "All costs stated", "unknown", detail + " Needs review.", ["subtotal", "shipping", "tax", "total"]))
    elif f.needs_review:
        checks.append(Check("cost_known", "All costs stated", "unknown", "Extraction flagged for human review before amounts can be trusted.", ["total"]))
    else:
        checks.append(Check("cost_known", "All costs stated", "pass", f"Subtotal {_money(f.subtotal, f.currency)} + shipping {_money(f.shipping, f.currency)} + tax {_money(f.tax, f.currency)} = {_money(computed, f.currency)}.", ["subtotal", "shipping", "tax", "total"]))

    verified_total = computed if (not missing and arith == "consistent" and not f.needs_review and checks[0].status == "pass") else None
    if verified_total is None:
        reason = "currency is not confirmed" if checks[0].status != "pass" and not missing and arith == "consistent" else "the total is not verified"
        checks.append(Check("budget", f"Within {cur} {fmt(spec.budget_amount)} budget", "unknown", f"Cannot compare with the budget because {reason}.", ["total"]))
    elif verified_total <= spec.budget_amount:
        checks.append(Check("budget", f"Within {cur} {fmt(spec.budget_amount)} budget", "pass", f"{_money(verified_total, cur)} is within budget ({_money(spec.budget_amount - verified_total, cur)} headroom).", ["total"]))
    else:
        checks.append(Check("budget", f"Within {cur} {fmt(spec.budget_amount)} budget", "fail", f"{_money(verified_total, cur)} exceeds the budget by {_money(verified_total - spec.budget_amount, cur)}.", ["total", "shipping"]))

    est = order_date + timedelta(days=f.delivery_days) if f.delivery_days is not None else None
    if spec.deadline_date is None:
        checks.append(Check("delivery", "Delivery deadline", "pass", "No delivery deadline in the request.", ["delivery"]))
    elif est is None:
        checks.append(Check("delivery", f"Delivered by {spec.deadline_date.isoformat()}", "unknown", "The quote does not state a delivery time.", ["delivery"]))
    elif est <= spec.deadline_date:
        checks.append(Check("delivery", f"Delivered by {spec.deadline_date.isoformat()}", "pass", f"Supplier claims delivery within {f.delivery_days} days (≈ {est.isoformat()} if ordered {order_date.isoformat()}). This is a supplier claim.", ["delivery"]))
    else:
        checks.append(Check("delivery", f"Delivered by {spec.deadline_date.isoformat()}", "fail", f"Supplier claims {f.delivery_days} days (≈ {est.isoformat()}), after the deadline.", ["delivery"]))

    if f.valid_until is None:
        checks.append(Check("validity", "Quote still valid", "unknown", "No validity date is stated.", ["valid_until"]))
    elif f.valid_until < order_date:
        checks.append(Check("validity", "Quote still valid", "fail", f"Quote expired on {f.valid_until.isoformat()}.", ["valid_until"]))
    else:
        checks.append(Check("validity", "Quote still valid", "pass", f"Valid until {f.valid_until.isoformat()}.", ["valid_until"]))

    for c in spec.mandatory:
        status, detail = assess(c, (f.attributes or {}).get(c.key), (f.attribute_sources or {}).get(c.key))
        checks.append(Check(f"attr:{c.key}", c.label, status, detail, [f"attr:{c.key}"]))

    statuses = {c.status for c in checks}
    mandatory = "fail" if "fail" in statuses else ("unknown" if "unknown" in statuses else "pass")
    eligible = mandatory == "pass" and verified_total is not None and f.checkout_available and (f.currency in SUPPORTED_CHECKOUT_CURRENCIES)
    return QuoteOutcome(f.quote_id, f.supplier, checks, mandatory, verified_total, computed, arith, est, f.checkout_available, eligible)


def rank(outcomes: list[QuoteOutcome], facts: dict[str, QuoteFacts]) -> list[QuoteOutcome]:
    """Transparent ordering among compliant quotes: lowest verified total, then fastest delivery."""
    compliant = [o for o in outcomes if o.mandatory_status == "pass" and o.verified_total is not None]
    compliant.sort(key=lambda o: (o.verified_total, facts[o.quote_id].delivery_days if facts[o.quote_id].delivery_days is not None else 10**6, o.supplier))
    for i, o in enumerate(compliant, start=1):
        o.compliant_rank = i
    return outcomes


def evaluate_all(spec: RequirementSpec, facts: list[QuoteFacts], order_date: date, quantity_override: int | None = None) -> list[QuoteOutcome]:
    outs = [evaluate(spec, f, order_date, quantity_override) for f in facts]
    return rank(outs, {f.quote_id: f for f in facts})


def summarize(outcomes: list[QuoteOutcome], facts: list[QuoteFacts]) -> dict:
    """Deterministic recommendation summary (the LLM may only phrase this, never change it)."""
    best = next((o for o in outcomes if o.compliant_rank == 1), None)
    by_id = {f.quote_id: f for f in facts}
    priced = [(o, o.verified_total if o.verified_total is not None else by_id[o.quote_id].stated_total) for o in outcomes]
    priced = [(o, t) for o, t in priced if t is not None]
    cheapest = min(priced, key=lambda p: p[1])[0] if priced else None
    why_cheapest_loses = None
    if cheapest and best and cheapest.quote_id != best.quote_id:
        blockers = [c for c in cheapest.checks if c.status != "pass"]
        why_cheapest_loses = {"quote_id": cheapest.quote_id, "supplier": cheapest.supplier, "blocking_checks": [c.as_dict() for c in blockers]}
    unknowns = [{"quote_id": o.quote_id, "supplier": o.supplier, "check": c.as_dict()} for o in outcomes for c in o.checks if c.status == "unknown"]
    return {
        "best_compliant_quote_id": best.quote_id if best else None,
        "best_compliant_supplier": best.supplier if best else None,
        "best_compliant_total": fmt(best.verified_total) if best else None,
        "best_has_checkout": bool(best and best.checkout_available),
        "payment_eligible_quote_ids": [o.quote_id for o in outcomes if o.payment_eligible],
        "cheapest_quote_id": cheapest.quote_id if cheapest else None,
        "why_cheapest_loses": why_cheapest_loses,
        "unknowns": unknowns,
        "no_compliant_quote": best is None,
    }
