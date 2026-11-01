"""Cartel-pattern model for recurring supplier groups (QuoteGuard research contribution).

Screens follow the bid-rigging literature and the definitions of the public data we trained on
(Imhof & Wallimann 2021, CC BY 4.0), computed from the three bids of a supplier group in each tender:
  cvbid     coefficient of variation, percent          Diffperc  (b2 - b1) / b1, percent
  Spread    (max - min) / min                          RD1       (b2 - b1) / sd(losing bids)
  RDnorm    (b2 - b1) / mean adjacent gap              RDalter   (b2 - b1) / mean gap among losing bids
  skew1     adjusted Fisher-Pearson skewness
Each screen is aggregated over the group's joint tenders (min / max / mean / median), expressed as a percentile of a
market reference ("market-relative screens"), and scored by a logistic model whose coefficients are constrained to the
signs economic theory predicts for cover bidding. Training, the leave-one-market-out study and baselines live in
research/bid_rigging/. This is a review signal, never proof.
"""

from __future__ import annotations

import bisect
import itertools
import json
import math
import statistics
from functools import lru_cache
from pathlib import Path

SCREENS = ["cvbid", "Diffperc", "Spread", "RD1", "RDnorm", "RDalter", "skew1"]
LABELS = {"cvbid": "bid spread (CV)", "Diffperc": "gap to runner-up", "Spread": "max–min spread", "RD1": "relative distance", "RDnorm": "isolated winner (normalised distance)",
          "RDalter": "winner gap vs. losing-bid gaps", "skew1": "skew of bids"}


@lru_cache(maxsize=1)
def model() -> dict:
    return json.loads((Path(__file__).with_name("cartel_model_v1.json")).read_text())


def tender_screens(bids: list[float]) -> dict[str, float] | None:
    b = sorted(float(x) for x in bids if x and x > 0)
    if len(b) < 3:
        return None
    n, mean, sd = len(b), statistics.mean(b), statistics.stdev(b)
    gaps = [b[i + 1] - b[i] for i in range(n - 1)]
    losing_sd = statistics.stdev(b[1:])
    g = sum((x - mean) ** 3 for x in b) / n / ((sum((x - mean) ** 2 for x in b) / n) ** 1.5) if sd > 0 else 0.0
    eps = 1e-9
    return {
        "cvbid": 100 * sd / mean, "Diffperc": 100 * gaps[0] / b[0], "Spread": (b[-1] - b[0]) / b[0],
        "RD1": gaps[0] / max(losing_sd, eps), "RDnorm": gaps[0] / max(sum(gaps) / (n - 1), eps),
        "RDalter": gaps[0] / max(sum(gaps[1:]) / (n - 2), eps), "skew1": g * math.sqrt(n * (n - 1)) / (n - 2),
    }


def coalition_features(tenders: list[dict[str, float]]) -> dict[str, float]:
    out = {}
    for s in SCREENS:
        v = [t[s] for t in tenders]
        out["min3" + s], out["max3" + s], out["mean3" + s], out["median3" + s] = min(v), max(v), statistics.mean(v), statistics.median(v)
    return out


def _percentile(value: float, grid: list[float]) -> float:
    i = bisect.bisect_left(grid, value)
    if i <= 0:
        return 0.0
    if i >= len(grid):
        return 1.0
    lo, hi = grid[i - 1], grid[i]
    frac = 0 if hi == lo else (value - lo) / (hi - lo)
    return (i - 1 + frac) / (len(grid) - 1)


def score(features: dict[str, float], reference: dict[str, list[float]] | None = None) -> dict:
    m = model()
    ref = reference or m["reference"]["quantiles"]
    z, contrib = m["intercept"], []
    for f, mu, sd, c in zip(m["features"], m["mu"], m["sd"], m["coef"]):
        p = _percentile(features[f], ref[f])
        term = c * (p - mu) / sd
        z += term
        if c:
            contrib.append((term, f, p))
    prob = 1 / (1 + math.exp(-z))
    contrib.sort(reverse=True)
    drivers = [{"feature": f, "screen": LABELS[next(s for s in SCREENS if f.endswith(s))], "aggregate": f[:-len(next(s for s in SCREENS if f.endswith(s)))].replace("3", ""),
                "percentile": round(p, 2), "push": round(t, 2)} for t, f, p in contrib[:3] if t > 0]
    return {"probability": round(prob, 3), "drivers": drivers}


def recurring_groups(current: dict[str, float], history: list[dict[str, float]], min_tenders: int | None = None) -> list[dict]:
    """current/history: {supplier_key: total} per tender. Scores every 3-supplier group of the current tender that
    also quoted together in enough past tenders."""
    need = min_tenders or model()["training"]["min_joint_tenders"]
    out = []
    for trio in itertools.combinations(sorted(k for k, v in current.items() if v), 3):
        joint = [t for t in [current, *history] if all(t.get(k) for k in trio)]
        if len(joint) < need:
            continue
        tenders = [tender_screens([t[k] for k in trio]) for t in joint]
        if any(x is None for x in tenders):
            continue
        winners = [min(trio, key=lambda k: t[k]) for t in joint]
        res = score(coalition_features(tenders))
        out.append({"suppliers": list(trio), "joint_tenders": len(joint), "winners": winners, "rotation": len(set(winners)), **res,
                    "screens_current": {k: round(v, 3) for k, v in tenders[0].items()}})
    return sorted(out, key=lambda r: -r["probability"])
