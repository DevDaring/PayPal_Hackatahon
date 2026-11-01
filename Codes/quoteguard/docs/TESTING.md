# Testing and evaluation

Four kinds of evidence, kept separate:

| Kind | What | How to run | Uses real PayPal? | Uses real model? |
|---|---|---|---|---|
| Deterministic tests | Policy, arithmetic, snapshot hashing, authorization, concurrency, webhooks, Demo Lab | `cd backend && .venv/bin/pytest -q` | No — in-memory fake provider with PayPal-Request-Id semantics | No (`MOCK_AI`) |
| Mocked integration tests | Full services on real PostgreSQL (`quoteguard_test`, schema built by the Alembic migration) with the fake provider | same suite | No | No |
| Live AI evaluation | 24 labelled synthetic quotes through the extraction + policy pipeline | `python -m quoteguard.cli run-eval llm` (or the Evaluation page) | No | Yes |
| Integrity benchmark | 82 labelled purchase cases: honest controls and manipulated documents | `python -m quoteguard.cli run-integrity-bench ../reports` (Evaluation page shows the latest) | No | No — deterministic |
| Actual sandbox checks | Real PayPal Sandbox calls | manual checklist below + Playwright journey | **Yes** | Yes |

## Results — 1 November 2026 (final revision)

**Backend (pytest 9.2, PostgreSQL 16):** `75 passed` (~73 s). Cartel-pattern model: screen definitions match the published data (RD = √2·RDalter for three bids, bounds of RDnorm and skew), the exported coefficients obey the sign constraints, a rotating-cartel history is flagged while each document alone is clear, competitive histories score < 0.2, and groups with fewer than 3 joint purchases are not scored; the `rotating_cartel` Demo Lab scenario runs end-to-end. Integrity tests: clean sample is clear; original amounts recovered from an incremental edit; white-box patch, retyped amount and insider authorship each detected; cover-quote set linked by author, document ID, phone and creation time with the cover-bid screen; honest suppliers on the same invoicing software *not* linked; the AI memo is discarded when it states a number absent from the findings; and a regression for a self-deadlock found live (row lock held across the model call while the call logger referenced the request) — the test fails on the old code. Both Demo Lab integrity scenarios run end-to-end. Beyond the brief's 18 checks: negated/conditional/conflicting specifications at the policy layer and end-to-end (PDF → extraction → approval rejected, from a supplier *with* a configured merchant); recovery after approval expiry (no new capture), recovery with valid approval under 4 racing deliveries (one capture, one request id), recovery against wrong payee / missing payee / wrong operation / changed amount (no capture), an existing capture recorded after expiry, missing payee in normal capture; Agent Toolkit tool scoping; regressions from the holdout.

| # (brief §14) | Test |
|---|---|
| 1 | `test_reference_quotes_exact_totals_and_outcomes` — $640 / $570 / $470, ranks, why-cheapest-loses, what-if $650 and $560 |
| 2 | `test_missing_costs_and_uncertain_currency_never_verified` (4 cases), `test_contradictory_total_needs_review` |
| 3 | `test_evidence_references_resolve_to_source_text` — every link's text is on its page; ≥30 with bounding boxes |
| 4 | `test_correction_creates_version_and_invalidates_approval` |
| 5 | `test_tampered_amount_or_merchant_blocks_order_creation`, `test_change_after_order_blocks_capture` |
| 6 | `test_expired_revoked_and_unauthorised_approvals_fail`, `test_cross_workspace_access_is_not_found` |
| 7 | `test_unconfigured_supplier_cannot_be_paid` |
| 8 | `test_client_cannot_change_amount_or_payee` |
| 9 | `test_paypal_buyer_approval_cannot_bypass_org_approval`, `test_org_approval_alone_cannot_capture` |
| 10 | `test_concurrent_checkout_and_capture_are_one_operation` (8 threads each) |
| 11 | `test_lost_capture_response_reconciles_without_second_charge` |
| 12 | `test_restart_after_intent_resumes_safely` |
| 13 | `test_webhooks_duplicate_invalid_unrelated_and_reordered` |
| 14 | `test_malicious_pdf_cannot_change_policy_permissions_or_payee` |
| 15 | `test_distinct_outcomes_for_decline_cancel_pending_and_outage` (backend codes; UI renders each distinctly) |
| 16 | `test_export_has_references_and_no_secrets` |
| 17 | `test_live_mode_cannot_be_enabled`, `test_demo_login_gets_isolated_workspace_and_cannot_switch_elsewhere` |
| 18 | `test_refund_cannot_exceed_capture_even_concurrently` |
| — | `test_audit_chain_detects_modification`, `test_demo_lab_scenarios_use_real_services` ×5 |

Bugs these tests found and fixed during the build: an inverted lock order between payment and request rows (deadlock under concurrent refunds/captures), stale optimistic-lock versions on locking reads, and a crash when correcting a quote's total.

**Frontend:** `npm test` → 4 passed (Vitest). `tsc -b` clean. Production build succeeds.

**End-to-end (Playwright, Chromium) against https://quoteguard.koushikdeb.com, after the provider switch:** 8 passed — Agent Mode ×2, the journey, Demo Lab + screens, mobile, a **real PayPal Sandbox buyer approval and capture**, and `integrity.spec.ts` ×2 (edited bill caught, $640.00 recovered, counterfactual payable at rank 1, approval refused; rotating cartel held for review by the cartel-pattern model, research table rendered). The journey: jury sign-in → sample request → confirm → 3 PDFs extracted by the model → comparison (ClearWave recommended, Harbor's USB-A shown) → evidence drawer highlights Northstar's $160 shipping line → what-if $560 shows “no compliant quote” → role switch → approval → checkout renders official PayPal Sandbox buttons.

### Live AI evaluation (dataset `quoteguard-eval-v1`, 24 cases, scenario clock 2026-11-02)

Stored in `reports/` and on the Evaluation page. Checkout is assumed configured so extraction and policy are measured in isolation.

| Run (UTC) | Mode / model | Decision agreement | Non-payable rejected by policy | False blocking | Evidence refs valid |
|---|---|---|---|---|---|
| 19:04 | deterministic rules | 24/24 | 18/18 | 0/6 | 377/380 |
| 19:04 | gemini-2.5-flash | 20/24 | **17/18** | 2/6 | 377/377 |
| 19:09 | gemini-2.5-flash (after fixes 1–3) | 23/24 | 18/18 | 1/6 | 379/380 |
| 19:13 | gemini-2.5-flash (after fix 4) | 24/24 | 18/18 | 0/6 | 379/380 |

What the first model run found, and the fixes (system changes — labels were not edited):

1. **Unsafe pass:** the model reported `currency_explicit: true` for a quote that only printed “$”. The claim is now checked against the document text.
2. “Free shipping” was withheld because the numeric-support check found no digits; zero values are now supported by “free/included/waived” evidence.
3. Business-day delivery: day counts are now recomputed deterministically from the cited line.
4. When the model returns nothing for a critical field that the deterministic parser cites on the page, the parser's value is used and the fallback is noted.

Caveats: single runs, so no latency percentiles (individual timings are shown); one template family; the deterministic baseline was written alongside these templates, so its 24/24 overstates real-world accuracy; model output varies between runs.

### Independent holdout (dataset `quoteguard-holdout-v1`, 26 unfamiliar quotes)

Built by a separate generator (`backend/quoteguard/holdout.py`) with different wording and layouts: prose letters without field labels, invoice tables, two-page terms, revised offers, optional charges, negated/optional specs, ambiguous currency, injected instructions and a scanned page. **Labels were committed (`fixtures/holdout_manifest.json`, commit `76f6781`) before any run.** Same PDFs and labels for both extractors; all runs kept.

| Runs (1 Nov, UTC) | Extractor | Decisions matching labels | Non-payable marked payable | Payable wrongly blocked | Cited lines valid | Needs human review | Median time / doc | Tokens per run |
|---|---|---|---|---|---|---|---|---|
| 07:43 (unseen) | rules | 11/26 | 0/18 | 8/8 | 147/147 | 23/26 | 22 ms | 0 |
| 07:43–07:47 (unseen) | gemini-2.5-flash ×3 | 24/26 each | **1/18 each** | 1/8 each | 377/377, 380/380, 380/380 | 9/26 | ≈4.9 s | ≈47k |
| 07:57 after fixes (seen) | rules | 12/26 | 0/18 | 8/8 | 147/147 | 22/26 | 24 ms | 0 |
| 07:57–08:03 after fixes (seen) | gemini-2.5-flash ×3 | 26/26 each | 0/18 | 0/8 | 379/379, 380/380, 377/377 | 8/26 | ≈4.9–5.7 s | ≈47k |
| 10:43 provider switch (seen) | anthropic/claude-sonnet-5.5 via NanoGPT | 23/26 | **0/18** | 1/8 | 368/368 | — | ≈7.1 s | — |

The live demo switched from Gemini to **Claude Sonnet 5.5 via NanoGPT** on 1 November (no GCP keys). Its three disagreements all fail safe: `ho-twopage-clean` and `ho-revised-over` missed the subtotal (→ unknown; the first is the one payable quote blocked), and `ho-letter-mic-optional` was assessed “fail” instead of “unknown”. We did not tune prompts on the holdout after this run.

Development set on the final revision (08:05): rules 24/24, Gemini 24/24, 0 false eligibility, 0 false blocks. After the provider switch (10:46): Claude Sonnet 5.5 24/24, 0/18 non-payable marked payable, 0/6 payable blocked, 379/380 citations valid. Reports: `reports/evaluation-20261101-*`.

The unseen false eligibility (`ho-letter-3.5mm`: “charges over USB-C; audio connects through the 3.5 mm jack”) exposed two general defects in the specification checker — clauses were split on the decimal point in “3.5 mm”, hiding the conflicting connector, and plural terms (“microphones”) were not matched, causing the one false block. Both were fixed with regression tests; runs after the fix are labelled **seen** in the stored config and in the UI, and must not be described as unseen. What the holdout shows: on unfamiliar layouts the rules parser fails safe but blocks almost everything payable, while the model plus deterministic checks reads them correctly; the checks — not the model — are what keep a misread from becoming payable.

## Manual real-sandbox checklist

Status as of 1 Nov 2026 — **full real-sandbox purchase verified** with US-region sandbox merchant `AT2QVVSQLWMDQ` and a US sandbox buyer (the first attempt with India-registered accounts was rejected by PayPal with `UNSUPPORTED_PAYEE_CURRENCY`).

| Step | How | Status |
|---|---|---|
| OAuth client-credentials token | backend start / first order | ✅ verified (sandbox) |
| Order creation with `PayPal-Request-Id`, payee merchant validated before capture | approve ClearWave → Pay step | ✅ verified (e.g. order `9PP37766SL637140C`) |
| Duplicate checkout returns same order | click Pay twice / Demo Lab | ✅ verified (same operation, one create call) |
| Capture refused before buyer approval | Capture without approving | ✅ verified (`PAYER_NOT_APPROVED`) |
| Buyer login + approval in PayPal popup | `e2e/sandbox-capture.spec.ts` (US sandbox buyer) | ✅ verified |
| Capture COMPLETED, IDs on receipt | after approval | ✅ order `8J490246E38235409`, capture `6KR959288R730242A`, USD 570.00 |
| Lost capture response → reconciling → completed | Pay step: “discard PayPal's capture response”, then approve | ⏳ run manually |
| Webhook delivery verified | `CHECKOUT.ORDER.APPROVED`, `PAYMENT.CAPTURE.COMPLETED` | ✅ both signature-verified with PayPal and applied via lookup |
| Partial refund | Receipt → Partial refund (admin) | ⏳ run manually after a capture |

Webhook simulator note: events sent from the PayPal dashboard simulator are not tied to a real order and their signature verification semantics differ from app-generated events, so they are not used as proof of a transaction.

## Document integrity benchmark — `quoteguard-integrity-v1` (1 November 2026)

Deterministic analyzer `integrity-v1`; identical results locally and on the live server (`reports/integrity-*.json`, digest `ec06707f2857916e`).

| Group | Cases | Result |
|---|---|---|
| Honest controls (sample set, all 26 holdout layouts as single documents, 8 honest three-supplier groups built from holdout layouts with independent metadata, 2 pairs of honest suppliers on the same invoicing software and template, a harmless metadata-only re-save) | 38 (60 documents) | **0 flagged** |
| Edited bill — PDF editor, incremental save | 3 | 3 blocked, original recovered 3/3 |
| Edited bill — white-box patch, flattened | 3 | 3 blocked |
| Edited bill — amount retyped in another font | 3 | 3 sent to review (expected) |
| Edited bill on holdout layouts — incremental / white-box | 12 / 12 | 12 / 12 blocked; originals recovered 12/12 |
| Staged competition — shared author, copied file, shared phone, shared email, written by the requester, demo set | 6 | 6 blocked |
| Staged competition — same tool, minutes apart only | 1 | sent to review (expected) |
| **Hard, expected misses** — edit cleanly re-saved as a new file (×3); invented competitors with fresh, unrelated metadata (×1) | 4 | **not caught** |

Totals: 40/44 attacks caught (36 blocked), 0/38 false alarms, 78/82 decisions match the label, 15/15 originals recovered. Caveats: synthetic documents, and the attack generator and detectors were written by the same team — this is a regression benchmark, not a field accuracy estimate. Thresholds were not tuned after the first run.

## Research study — cross-market bid-rigging detection (`research/bid_rigging/`)

Real data (Imhof & Wallimann 2021, CC BY 4.0): 23,793 bidder groups with proven cartel periods. Leave-one-market-out, variant chosen on training markets only, thresholds fixed in advance. Held-out AUC — rule 0.700, random forest 0.714, boosted trees 0.729, lasso 0.765, **ours 0.818** (Japan 0.773 / Switzerland 0.837 / Italy 0.845); paired bootstrap: significantly better in 9/12 comparisons, ties in 3, never worse. Results JSON in `research/bid_rigging/results/`; reproduce with the commands in that README.
