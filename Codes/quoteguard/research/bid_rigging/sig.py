import sys, json, numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score
exec(open(sys.argv[2]).read().split("out = []")[0])  # nested.py preamble (loads lomo + variants)
sel = {"JP": "V2 MR + sign-constrained logit", "CH": "V3 MR ensemble (V1 ⊕ V2, rank average)", "IT": "V2 MR + sign-constrained logit"}
res = {}
for target in ("JP", "CH", "IT"):
    src = [m for m in M if m != target]
    tr = pd.concat([M[s] for s in src], ignore_index=True); te = M[target].reset_index(drop=True); y = te.y.values
    ours = run_variant(sel[target], tr, te)
    base = {"B1 rule": rule_score(te)}
    for k in ("B2 RF on screens (Huber & Imhof 2019)", "B3 lasso logit (Imhof & Wallimann 2021)", "B4 boosted trees on screens"):
        base[k.split(" (")[0]] = fit_predict(k, tr, te)[0]
    r = np.random.default_rng(1); idx = np.arange(len(y)); res[target] = {"ours": round(roc_auc_score(y, ours), 3)}
    for k, p in base.items():
        d = []
        for _ in range(1000):
            s = r.choice(idx, len(idx))
            if len(set(y[s])) == 2: d.append(roc_auc_score(y[s], ours[s]) - roc_auc_score(y[s], p[s]))
        d = np.array(d); res[target][k] = {"auc": round(roc_auc_score(y, p), 3), "diff": round(float(np.mean(d)), 3), "ci95": [round(float(np.percentile(d, 2.5)), 3), round(float(np.percentile(d, 97.5)), 3)], "p_le0": round(float((d <= 0).mean()), 4)}
    print(target, json.dumps(res[target]), flush=True)
json.dump(res, open(sys.argv[4], "w"), indent=1)
