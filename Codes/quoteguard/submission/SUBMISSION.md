# QuoteGuard — Devpost submission copy

**Tagline:** From supplier PDF to an approved PayPal purchase — evidence for every decision, and a payment that must match what a person approved.

**Prize fit:** no tracks — every submission is judged for the Grand Prizes and Honorable Mentions. Primary fit **Best Use of PayPal + AI**; also Best Demo Delivery and Best Use of Agentic Commerce. Sponsor prize: **Best Use of AG Grid** (evidence-linked comparison grid with live what-if column, tooltips and safe CSV export; filterable evaluation grid).

**Try it:** https://quoteguard.koushikdeb.com — **Fill to Sign in** on the login page (every sign-in gets its own isolated workspace). PayPal runs in **Sandbox** (no real money); supplier documents are synthetic. A sandbox buyer login is shown on the checkout screen.

**Video:** <YouTube link> · **Code:** https://github.com/DevDaring/PayPal_Hackatahon (MIT)

## Inspiration

A small operations team buying 30 headsets compares three PDF quotes. The cheapest one has the wrong connector; another hides $160 of shipping in a footnote. Someone says “looks good” in chat, and the payment that finally goes out is not exactly what was approved. AI that “just buys things” makes this worse unless every step is grounded and checked.

## What it does

1. **Describe** the purchase in plain English; Gemini drafts typed requirements (quantity, budget incl. shipping & tax, delivery date in your timezone, must-haves). **A person confirms them** (consent 1 of 3).
2. **Extract** supplier PDFs — your uploads or the labelled samples. Every value must cite a verbatim line; QuoteGuard checks the line is on that page, highlights it, verifies the number appears in it, re-assesses product specs from the *cited sentence* (so “microphone not included” or “USB-C charging only; audio via 3.5 mm” cannot pass), and cross-checks amounts with a deterministic parser.
3. **Compare** with Decimal arithmetic: pass / fail / **unknown** — missing evidence is never a pass. It shows why the cheapest quote loses, what each quote hides, and what-if previews that are clearly separated from the confirmed purchase.
4. **Approve the exact purchase** (consent 2 of 3): an approver signs a SHA-256 hash of supplier, quote version, items, amounts, PayPal merchant, policy version and expiry. Self-approval is disabled.
5. **Pay with PayPal** (consent 3 of 3): the backend builds the Orders v2 order only from the approved snapshot, re-validates it before order creation and before capture, and checks the order's operation, amount, currency and payee with PayPal before capturing. Recovery after a lost response runs the **same** checks before any new capture, and still records a capture that already happened.
6. **Prove it:** receipt with PayPal order/capture IDs, signed-webhook verification, Decision Replay of recorded events, every provider call, and a PDF/JSON evidence package.

**Agent Mode** runs this as a resumable workflow on your own request and documents (or the sample): it reads, cites, verifies and decides on its own, survives refresh, surfaces failures with retry, and stops at the three consents it cannot give. The assistant can query PayPal through **PayPal's Agent Toolkit** — read-only order and transaction lookups with the order ID injected by the server.

**Demo Lab** lets judges attack the payment path with the real services: amount or payee changed after approval (including direct database edits), a PDF that tells the AI to ignore the budget and pay an email address, five simultaneous Pay/Capture clicks, and a capture response that is lost in flight. Concurrency/lost-response scenarios use a clearly labelled simulated provider because a real capture needs a human buyer login; the real Sandbox purchase is shown separately.

## Why the AI matters (measured)

We built a second, **independent holdout set of 26 unfamiliar quotes** — prose letters without field labels, invoice tables, two-page terms, revised offers, optional charges, negated specs, ambiguous currency, injected instructions, a scanned page — and **froze its labels in a commit before any run**. Same PDFs and labels for both extractors:

| First (unseen) runs | Rules parser | Gemini 2.5 Flash + QuoteGuard checks (3 runs) |
|---|---|---|
| Decisions matching labels | 11 / 26 | 24 / 26 in each run |
| Payable quotes wrongly blocked | 8 / 8 | 1 / 8 |
| Non-payable quotes marked payable | 0 / 18 | 1 / 18 in each run |

That single false eligibility (“charges over USB-C; audio through the 3.5 mm jack”) exposed two general defects in our spec checker — clause splitting inside “3.5 mm” and missed plurals. We fixed them, added regression tests, and labelled every later run “seen”: 26 / 26 in each of 3 runs, 0 false eligibility, 0 false blocks (rules: 12 / 26). On the original development set both extractors agree with the labels; the rules parser was written against those templates, which is exactly why we built the holdout.

## How we built it

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, httpx; a shared domain package used by the API, the worker and Demo Lab.
- **Agent workflow:** LangGraph `extract_quotes → evaluate_constraints → summarize_recommendation`, node progress persisted in PostgreSQL; a durable jobs table instead of Redis. The model returns JSON only — it has no tools that reach approvals or payments.
- **AI:** Gemini 2.5 Flash via its OpenAI-compatible endpoint (swappable for OpenAI/OpenRouter), versioned prompts, bounded calls, evidence verification, OCR for scanned pages (always needs review).
- **PayPal:** Orders v2 create/get/capture, Payments v2 refunds, webhook signature verification, stable `PayPal-Request-Id`s per logical operation, reconciliation by authoritative lookup, JS SDK buttons for buyer approval, and the **Agent Toolkit** for read-only assistant lookups.
- **Frontend:** React 19 + TypeScript + Vite, Tailwind v4, TanStack Query, **AG Grid Community**, accessible dialogs, reduced-motion support.
- **Quality:** 61 backend tests on real PostgreSQL (negated specs end-to-end, recovery after expiry, wrong/missing payee, duplicate deliveries, concurrent capture and refunds, forged and out-of-order webhooks, cross-workspace access, all Demo Lab scenarios); Vitest; Playwright journeys against the live site, including a real Sandbox buyer approval and capture.

## Challenges

- **“Unknown” as a first-class answer** — refusing to treat a missing shipping line or an optional microphone as acceptable.
- **Concurrency** — our own tests found an inverted lock order (deadlock under concurrent capture/refund) and stale optimistic-lock versions; both fixed and covered.
- **Trusting the model less** — the first evaluation runs found an unsafe case (a claimed explicit currency) and the holdout found another (a charging-only connector). Each time we changed the system, not the labels.

## Who it's for, and what's new

A small team where one operations person compares a few equipment quotes and a second person approves, buying from suppliers that accept PayPal. AI procurement and re-approval after changes exist in larger platforms; QuoteGuard's angle is a compact, inspectable trail from **the supplier's own sentence** to **the approved hash** to **the confirmed PayPal capture**, including what happens when things go wrong.

## Impact (honest)

We have not yet run observed sessions with real buyers or measured savings; the $160 shipping line in the sample is a disclosed supplier charge, not money saved. The next step is three to five observed sessions with operations staff (time to decision, correct supplier, overlooked terms) and one design partner on recurring purchases. A plausible model is a small-team workspace subscription — to be validated, not assumed.

## Limits

Synthetic documents only; PayPal Sandbox only; one configured sandbox merchant; USD checkout; delivery dates are supplier claims; the audit hash chain detects ordinary edits but not a privileged database administrator; model output varies between runs (all runs are kept on the Evaluation page).

## Built with

python · fastapi · postgresql · sqlalchemy · alembic · langgraph · gemini · paypal-orders-api · paypal-js-sdk · paypal-agent-toolkit · react · typescript · vite · tailwindcss · ag-grid · tanstack-query · playwright · caddy
