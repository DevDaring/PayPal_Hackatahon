"""Pre-declared variants; selection by inner leave-one-source-market-out AUC only; then one held-out score per market."""
import sys, json, warnings
import numpy as np, pandas as pd
from scipy.optimize import minimize
from scipy.stats import rankdata
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, balanced_accuracy_score
sys.argv += []
exec(open(sys.argv[3]).read().split("rows = []")[0])  # reuse loaders, features, baselines from lomo.py

class SignLogit:
    """Logistic regression whose coefficients obey the economic sign prior (L2, class-balanced)."""
    def __init__(self, signs, l2=1.0): self.signs, self.l2 = np.array(signs), l2
    def fit(self, X, y):
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9; Z = (X - self.mu) / self.sd
        w = np.where(y == 1, 0.5 / y.mean(), 0.5 / (1 - y.mean()))
        def f(b):
            z = Z @ b[1:] + b[0]; p = 1 / (1 + np.exp(-z))
            loss = -(w * (y * np.log(p + 1e-12) + (1 - y) * np.log(1 - p + 1e-12))).mean() + self.l2 * (b[1:] ** 2).sum() / len(y)
            g = Z.T @ (w * (p - y)) / len(y) + 2 * self.l2 * b[1:] / len(y)
            return loss, np.concatenate([[(w * (p - y)).mean()], g])
        bounds = [(None, None)] + [((0, None) if s > 0 else (None, 0) if s < 0 else (None, None)) for s in self.signs]
        self.b = minimize(f, np.zeros(Z.shape[1] + 1), jac=True, bounds=bounds, method="L-BFGS-B").x; return self
    def predict_proba(self, X):
        z = ((X - self.mu) / self.sd) @ self.b[1:] + self.b[0]; p = 1 / (1 + np.exp(-z)); return np.c_[1 - p, p]

def mono_gbm(): return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300, class_weight="balanced", monotonic_cst=MONO, random_state=0)
def rank01(p): return (rankdata(p) - 1) / max(1, len(p) - 1)

VARIANTS = {  # declared before running; all use market-relative screens + the economic sign prior
    "V1 MR + monotone boosting": lambda a, b: mono_gbm().fit(a, ya).predict_proba(b)[:, 1],
    "V2 MR + sign-constrained logit": lambda a, b: SignLogit(MONO).fit(a, ya).predict_proba(b)[:, 1],
    "V3 MR ensemble (V1 ⊕ V2, rank average)": lambda a, b: (rank01(mono_gbm().fit(a, ya).predict_proba(b)[:, 1]) + rank01(SignLogit(MONO).fit(a, ya).predict_proba(b)[:, 1])) / 2,
}

def run_variant(name, tr, te):
    global ya
    a, b = market_relative(tr), market_relative(te); ya = a.y.values
    return VARIANTS[name](a[FEATS].values, b[FEATS].values)

out = []
for target in ("JP", "CH", "IT"):
    src = [m for m in M if m != target]
    inner = {}
    for name in VARIANTS:  # inner: train on one source market, validate on the other (both directions)
        inner[name] = np.mean([roc_auc_score(M[v].y, run_variant(name, M[t].reset_index(drop=True), M[v].reset_index(drop=True))) for t, v in ((src[0], src[1]), (src[1], src[0]))])
    chosen = max(inner, key=inner.get)
    tr = pd.concat([M[s] for s in src], ignore_index=True); te = M[target].reset_index(drop=True)
    p = run_variant(chosen, tr, te); y = te.y.values
    thr = np.quantile(p, 1 - 0.5) if chosen.startswith("V3") else 0.5
    lo, hi = boot_auc(y, p)
    rec = {"target": target, "inner_auc": {k: round(v, 3) for k, v in inner.items()}, "chosen": chosen, "auc": round(roc_auc_score(y, p), 3), "auc_ci": [round(lo, 3), round(hi, 3)],
           "bal_acc": round(balanced_accuracy_score(y, (p >= thr).astype(int)), 3)}
    # also report every variant's held-out score for transparency (not used for selection)
    rec["all_heldout_auc"] = {k: round(roc_auc_score(y, run_variant(k, tr, te)), 3) for k in VARIANTS}
    out.append(rec); print(json.dumps(rec), flush=True)
print("MEAN held-out AUC of selected:", round(np.mean([r["auc"] for r in out]), 3), " bal_acc:", round(np.mean([r["bal_acc"] for r in out]), 3))
json.dump(out, open(sys.argv[2], "w"), indent=1)
