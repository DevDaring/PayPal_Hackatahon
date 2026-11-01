# Build status

Legend: ✅ implemented and verified · 🟡 implemented, verification needs a credential or manual step · ⏸ deferred

## P0 — core

| Capability | Status | Verified by |
|---|---|---|
| Password login (scrypt), server sessions, CSRF, CORS allowlist, rate limits | ✅ | tests 17, e2e |
| Workspaces, requester/approver/admin roles, self-approval disabled, labelled demo role switch | ✅ | tests 6, 17 |
| Isolated demo workspace per jury sign-in | ✅ | test 17, live site |
| Structured request drafting (Gemini + rules fallback), human confirmation, immutable versions, tz-aware deadline | ✅ | e2e, smoke |
| PDF upload validation, sandboxed parsing, hashes, page text + word boxes | ✅ | tests 3, 14 |
| Evidence links (doc ID, SHA-256, quote version, page, source text, method, bbox / text-only) | ✅ | test 3, e2e drawer |
| Human correction with note → new quote version, original preserved, approvals invalidated | ✅ | test 4 |
| Decimal totals, arithmetic checks, pass/fail/unknown, explicit unknowns | ✅ | tests 1, 2 |
| Recommendation + “why the cheapest loses” + cited explanation (LLM phrases, never decides) | ✅ | test 1, e2e |
| Version-bound approval: canonical snapshot hash, expiry, HMAC token, re-validation before order and capture | ✅ | tests 5, 6, 9 |
| PayPal Sandbox order creation from snapshot with `PayPal-Request-Id` | ✅ | live sandbox (order `9PP37766SL637140C`), e2e |
| PayPal buyer approval + capture | ✅ | live sandbox purchase 1 Nov 2026: order `8J490246E38235409`, capture `6KR959288R730242A` COMPLETED; Playwright `e2e/sandbox-capture.spec.ts` |
| Reconciliation, durable jobs, crash recovery | ✅ | tests 11, 12 |
| Signed webhook handling (store → verify → dedupe → lookup) | ✅ | test 13; live `CHECKOUT.ORDER.APPROVED` and `PAYMENT.CAPTURE.COMPLETED` deliveries signature-verified and applied |
| Comparison, approval, checkout and receipt screens | ✅ | e2e screenshots |
| Three reproducible sample quotations + extra fixtures | ✅ | `fixtures/` |
| Tests for payment and authorization boundaries | ✅ | 34 backend tests |

## P1 — differentiators

| Capability | Status |
|---|---|
| Decision Replay (persisted events, actor/tool, timestamps) | ✅ |
| What-if budget/delivery explorer; quantity only when pricing terms allow; apply → new version | ✅ |
| Demo Lab: amount change, merchant change (incl. direct DB tamper), malicious PDF, duplicate clicks, lost response | ✅ (5 scenarios tested) |
| Measured evaluation dashboard (24 labelled cases, stored runs) | ✅ |
| Evidence package PDF + JSON (no secrets) | ✅ test 16 |

## P2 — optional

| Capability | Status |
|---|---|
| Merchant-admin partial refund with concurrency guard | 🟡 implemented, test 18; live sandbox refund not yet run |
| Grounded Q&A side panel with read-only PayPal Agent Toolkit tools (order details, transaction lookup) | ✅ (test + live sandbox call) |
| Agent Mode: autonomous pipeline with two human checkpoints | ✅ (e2e) |
| “What QuoteGuard caught” impact card; AG Grid live what-if column, tooltips, CSV export; AG Grid evaluation grid with filters | ✅ |
| OCR for image-only PDFs via vision model (always needs review) | ✅ (hosted config enables it) |
| Bengali/Hindi input | ⏸ |
| Voice input | ⏸ |
| Additional sponsor integration | ⏸ |

## Not built, by design

Marketplace, lending, escrow, autonomous supplier onboarding, multi-merchant platform payouts, live-money mode, fraud certification, ERP features.

## Versions checked (31 Oct 2026)

Python 3.12 · FastAPI 0.162.0 · SQLAlchemy 2.1.6 · Alembic 1.20.1 · psycopg 3.3.6 · Pydantic 2.14.2 · httpx 0.28.1 · LangGraph 1.2.19 · pdfplumber 0.11.10 · pypdf 6.21.4 · pypdfium2 5.14.0 · ReportLab 5.1.0 · PostgreSQL 16 · Node 20.18 · React 19.3.1 · Vite 6.4.5 (Vite 8 needs Node ≥20.19) · TypeScript 5.9.3 · Tailwind 4.3.3 · TanStack Query 5.105 · React Router 7.18 · AG Grid Community 36.2 · @paypal/react-paypal-js 10.6.1 (SDK v5 buttons API) · Playwright 1.64.1. Full lock: `backend/requirements.lock`, `frontend/package-lock.json`.

## Work done during the hackathon

Everything in this repository was written during the hackathon period (initial commit 31 Oct 2026). No pre-existing codebase was reused.
