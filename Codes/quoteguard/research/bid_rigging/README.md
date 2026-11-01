# Cross-market bid-rigging detection with market-relative screens

QuoteGuard's research contribution: a cartel-pattern detector that keeps working in a market it was never trained on, and that ships inside the product (`backend/quoteguard/research/cartel.py`).

## Question

Statistical screens from the bid-rigging literature, such as the coefficient of variation of bids and the relative distance between the two lowest bids, detect cartels well when a model is trained and tested in the **same** market. A procurement tool, however, is deployed in markets where no labelled cartels exist. **How well do screen-based detectors transfer to an unseen market, and can we make them transfer better?**

## Data

We use the public replication data of Imhof & Wallimann (2021), *Detecting bid-rigging coalitions in different countries and auction formats* (International Review of Law and Economics). It is available from Mendeley Data (doi:10.17632/x8jwmbcpgn.1) under CC BY 4.0. Each row is a group of three firms that bid together in at least 3 tenders. Its screens are summarised over those tenders (min / max / mean / median), and it carries a label for whether the tenders fall in a proven cartel period.

| Market | Groups | Cartel share | Auction format |
|---|---|---|---|
| Okinawa, Japan | 2,000 | 10 % | first-price sealed bid |
| Switzerland | 1,542 | 58 % | first-price sealed bid |
| Turin, Italy | 20,251 | 7 % | average-bid auction (discounts) |

`./get_data.sh data/` downloads the files. The data is not redistributed in this repository.

## Method: market-relative screens + sign-constrained model

1. **Screens per tender.** From the three bids we compute: the coefficient of variation; the percentage difference between the two lowest bids; the max–min spread; relative distance; normalised distance; alternative distance; and adjusted skewness. All use the published definitions, verified against the data: with three bids, RD = √2 × RDalter, and RDnorm ∈ [0, 2].
2. **Group aggregation.** For each screen we take the min, max, mean and median over the group's joint tenders, giving 28 features.
3. **Market-relative transform (new).** Each feature is replaced by its **percentile within its own market**. This needs only that market's unlabelled bids, which an auditor or buyer always has. It removes the scale and format differences that defeat transfer, such as typical spreads of about 1 % in Okinawa against about 30 % in Turin.
4. **Economic sign constraints (new).** A class-balanced logistic model is trained with coefficients constrained to the direction cover-bidding theory predicts:
   - less dispersion → more suspicious (coefficient of variation, spread);
   - a more isolated winner → more suspicious (difference, RD, normalised distance, alternative distance);
   - skewness is left unconstrained.

   We also pre-declared a monotone gradient-boosting variant and a rank-average ensemble. **The variant is chosen only by inner validation on the training markets** (train on one, validate on the other), never on the test market.

## Protocol

**Leave-one-market-out:** train on two markets, test on the third. All thresholds are fixed in advance (0.5 for class-balanced models), and no labels from the test market are used.

The baselines are re-implemented on the same features, "in the style of" each paper, not as exact replications of their full pipelines:

- **B1:** the two-screen rule, RD > 1 and CV < 5 % (the screens popularised by Swiss competition-authority practice and Huber & Imhof 2019).
- **B2:** a random forest on raw screens (Huber & Imhof 2019 style).
- **B3:** lasso logistic regression on raw screens (one of the learners in Imhof & Wallimann 2021).
- **B4:** gradient-boosted trees on raw screens.

**Uncertainty:** 95 % bootstrap intervals; paired bootstrap (1,000 resamples) for differences.

## Results (held-out market AUC)

| Method | Japan | Switzerland | Italy | Mean |
|---|---|---|---|---|
| B1 two-screen rule | 0.639 | 0.829 | 0.633 | 0.700 |
| B2 random forest (Huber & Imhof style) | 0.638 | 0.766 | 0.739 | 0.714 |
| B3 lasso logit (Imhof & Wallimann style) | 0.627 | 0.824 | 0.844 | 0.765 |
| B4 boosted trees | 0.682 | 0.759 | 0.747 | 0.729 |
| **Ours** | **0.773** | **0.837** | **0.845** | **0.818** |

Our method's balanced accuracy at the pre-set threshold is 0.715 / 0.760 / 0.736. The baselines average 0.585 (random forest), 0.608 (lasso) and 0.700 (rule).

**Paired differences (ours − baseline, AUC):**
- **Significantly better in 9 of 12 comparisons:** in every market against the random forest and the boosted trees (+0.07 to +0.13); against the lasso in Japan (+0.146, 95 % CI [0.122, 0.169]); against the rule in Japan and Italy.
- **Statistically tied in the other 3:** against the rule in Switzerland (+0.008, CI [−0.012, 0.029]); against the lasso in Switzerland (+0.013, CI [−0.010, 0.036]) and Italy (+0.000, CI [−0.009, 0.010]).
- **Never significantly worse.** No baseline is best-or-tied in all three markets; ours is.

**Finding:** flexible models that look excellent inside one market (random forest AUC 0.96–0.99 under within-market cross-validation) fall to 0.64–0.77 in an unseen market. Putting screens on a market-relative scale and constraining the model to economic theory recovers most of that loss.

## Limits

- Three markets, all construction or road-works. Group-level data with at least 3 joint tenders, not single tenders.
- Our baselines are re-implementations on shared features. Each paper's original pipeline, data preparation and within-market evaluation differ.
- In QuoteGuard the percentile reference is the pooled Okinawa + Swiss first-price markets until a workspace has its own history. That is a weaker setting than the study, where the test market's own unlabelled data provides the reference.
- Inside the product it is a **review signal** (medium severity) for supplier groups seen in at least 3 purchases. It is never proof of collusion and never decides a payment on its own.

## Reproduce

```bash
./get_data.sh data/ && python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python lomo.py data/ results/lomo.json                                   # all methods, leave-one-market-out
.venv/bin/python nested.py data/ results/nested.json lomo.py                        # pre-declared variants, inner selection
.venv/bin/python sig.py data/ nested.py lomo.py results/significance.json           # paired bootstrap vs baselines
.venv/bin/python train_export.py data/ nested.py lomo.py ../../backend/quoteguard/research/cartel_model_v1.json
```

## References

- Huber, M. & Imhof, D. (2019). Machine learning with screens for detecting bid-rigging cartels. *International Journal of Industrial Organization*.
- Imhof, D. & Wallimann, H. (2021). Detecting bid-rigging coalitions in different countries and auction formats. *International Review of Law and Economics*, doi:10.1016/j.irle.2021.106016. Data: Mendeley Data doi:10.17632/x8jwmbcpgn.1 (CC BY 4.0).
- Wallimann, H., Imhof, D. & Huber, M. (2023). A machine learning approach for flagging incomplete bid-rigging cartels. *Computational Economics* (arXiv:2004.05629).
- Okinawa data: Ishii (2014) and Huber et al. (2020); Italian data: Conley & Decarolis (2016) — as cited by the data authors.
