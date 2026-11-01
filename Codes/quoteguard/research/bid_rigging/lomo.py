"""Leave-one-market-out evaluation of bid-rigging detectors on real cartel data (Imhof & Wallimann 2021, CC BY 4.0)."""
import sys, json, warnings
import numpy as np, pandas as pd
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression, LogisticRegressionCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, balanced_accuracy_score
warnings.filterwarnings("ignore")
D = sys.argv[1].rstrip('/') + '/'
def load(f, name):
    x = pd.read_csv(D + f)
    x = x[x.cartelperiod.notna()].replace([np.inf, -np.inf], np.nan)
    feats = [c for c in x.columns if c.startswith(("min3", "max3", "mean3", "median3"))]
    x = x.dropna(subset=feats).copy(); x["market"] = name; x["y"] = x.cartelperiod.astype(int)
    return x
M = {"JP": load("Japanesedata.csv", "JP"), "CH": load("Swissdata.csv", "CH"), "IT": load("Italiandata.csv", "IT")}
SCR = ["cvbid", "Diffperc", "Spread", "RD1", "RDnorm", "RDalter", "skew1"]
AGG = ("min3", "max3", "mean3", "median3")
FEATS = [a + s for s in SCR for a in AGG]
# Economic prior (cover bidding): collusion -> lower dispersion (cv, spread), larger isolated gap (Diffperc, RD*). skew unconstrained.
SIGN = {"cvbid": -1, "Spread": -1, "Diffperc": 1, "RD1": 1, "RDnorm": 1, "RDalter": 1, "skew1": 0}
MONO = [SIGN[f[len(f) - len(s):]] if False else 0 for f in FEATS]
MONO = [next(SIGN[s] for s in SCR if f.endswith(s)) for f in FEATS]

def market_relative(df):
    """Percentile rank of each feature within its own market (unlabelled, available to an auditor of that market)."""
    out = df.copy()
    for m, g in df.groupby("market"):
        out.loc[g.index, FEATS] = g[FEATS].rank(pct=True).values
    return out

def rule_score(df):  # Imhof / COMCO style screens: RD > 1 and CV < 5 %  (binary)
    return ((df.mean3RD1 > 1) & (df.mean3cvbid < 5)).astype(float).values

METHODS = {
    "B1 screen rule (RD>1 & CV<5%)": None,
    "B2 RF on screens (Huber & Imhof 2019)": lambda: RandomForestClassifier(500, min_samples_leaf=3, class_weight="balanced", n_jobs=-1, random_state=0),
    "B3 lasso logit (Imhof & Wallimann 2021)": lambda: make_pipeline(StandardScaler(), LogisticRegressionCV(Cs=10, penalty="l1", solver="saga", class_weight="balanced", max_iter=5000, scoring="roc_auc")),
    "B4 boosted trees on screens": lambda: HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300, class_weight="balanced", random_state=0),
    "Ours: market-relative + monotone boosting": "MRS-MONO",
    "Ablation: market-relative + RF": "MRS-RF",
    "Ablation: raw + monotone boosting": "RAW-MONO",
}

def fit_predict(key, tr, te):
    if key == "MRS-MONO" or key == "RAW-MONO":
        a, b = (market_relative(tr), market_relative(te)) if key == "MRS-MONO" else (tr, te)
        m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300, class_weight="balanced", monotonic_cst=MONO, random_state=0)
        m.fit(a[FEATS].values, a.y); return m.predict_proba(b[FEATS].values)[:, 1], m.predict_proba(a[FEATS].values)[:, 1]
    if key == "MRS-RF":
        a, b = market_relative(tr), market_relative(te)
        m = RandomForestClassifier(500, min_samples_leaf=3, class_weight="balanced", n_jobs=-1, random_state=0)
        m.fit(a[FEATS].values, a.y); return m.predict_proba(b[FEATS].values)[:, 1], m.predict_proba(a[FEATS].values)[:, 1]
    m = METHODS[key]()
    m.fit(tr[FEATS].values, tr.y); return m.predict_proba(te[FEATS].values)[:, 1], m.predict_proba(tr[FEATS].values)[:, 1]

def boot_auc(y, p, n=300, seed=0):
    r = np.random.default_rng(seed); idx = np.arange(len(y)); out = []
    for _ in range(n):
        s = r.choice(idx, len(idx)); 
        if len(set(y[s])) == 2: out.append(roc_auc_score(y[s], p[s]))
    return np.percentile(out, [2.5, 97.5])

rows = []
for target in ("JP", "CH", "IT"):
    sources = [m for m in M if m != target]
    tr = pd.concat([M[s] for s in sources], ignore_index=True); te = M[target].reset_index(drop=True)
    y = te.y.values
    for name, key in METHODS.items():
        if key is None:
            p = rule_score(te); thr_pred = p
        else:
            p, ptr = fit_predict(name if key not in ("MRS-MONO", "MRS-RF", "RAW-MONO") else key, tr, te)
            thr = 0.5  # all models class-balanced; threshold fixed in advance (no target labels used)
            thr_pred = (p >= thr).astype(int)
        auc = roc_auc_score(y, p); lo, hi = boot_auc(y, p)
        rows.append({"target": target, "train": "+".join(sources), "method": name, "auc": round(auc, 3), "auc_ci": [round(lo, 3), round(hi, 3)], "bal_acc": round(balanced_accuracy_score(y, thr_pred), 3), "n": len(y), "cartel_rate": round(y.mean(), 3)})
        print(f"{target:3s} {name:44s} AUC {auc:.3f} [{lo:.3f},{hi:.3f}]  balAcc {rows[-1]['bal_acc']:.3f}", flush=True)
df = pd.DataFrame(rows)
print("\nMEAN over held-out markets:")
print(df.groupby("method")[["auc", "bal_acc"]].mean().sort_values("auc", ascending=False).round(3).to_string())
json.dump(rows, open(sys.argv[2], "w"), indent=1)
