"""Train the deployable detector (V2: market-relative screens + sign-constrained logit) on all three markets; export JSON."""
import sys, json, numpy as np, pandas as pd
exec(open(sys.argv[2]).read().split("out = []")[0])
allm = pd.concat(list(M.values()), ignore_index=True)
mr = market_relative(allm)
model = SignLogit(MONO).fit(mr[FEATS].values, mr.y.values)
ref_pool = pd.concat([M["JP"], M["CH"]], ignore_index=True)  # first-price sealed-bid markets: closest to supplier quotes
qs = np.linspace(0, 1, 101)
art = {
    "name": "quoteguard-cartel-mrs-v1",
    "method": "market-relative screens (percentile within market) + logistic regression with economic sign constraints, L2, class-balanced",
    "features": FEATS, "signs": MONO, "mu": model.mu.round(6).tolist(), "sd": model.sd.round(6).tolist(),
    "intercept": round(float(model.b[0]), 6), "coef": model.b[1:].round(6).tolist(),
    "reference": {"name": "study first-price markets (Okinawa, Switzerland)", "n_groups": int(len(ref_pool)),
                  "quantiles": {f: np.quantile(ref_pool[f].values, qs).round(6).tolist() for f in FEATS}},
    "training": {"groups": int(len(allm)), "cartel_groups": int(allm.y.sum()), "markets": {k: {"groups": int(len(v)), "cartel_rate": round(float(v.y.mean()), 3)} for k, v in M.items()},
                 "data": "Imhof & Wallimann (2021), Detecting bid-rigging coalitions in different countries and auction formats, Mendeley Data doi:10.17632/x8jwmbcpgn.1, CC BY 4.0",
                 "min_joint_tenders": 3},
}
json.dump(art, open(sys.argv[4], "w"), indent=1)
print("coef by feature (sign-constrained):")
for f, c in sorted(zip(FEATS, model.b[1:]), key=lambda t: -abs(t[1]))[:10]: print(f"  {f:16s} {c:+.3f}")
