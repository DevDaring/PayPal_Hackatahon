# QuoteGuard — PayPal AI Hackathon

**From supplier PDF to approved PayPal purchase — with evidence for every decision and checks before money moves.**

QuoteGuard reads supplier quotations, links every extracted term to the exact line on the PDF it came from, checks purchasing requirements with deterministic code, binds organisation approval to a hashed snapshot of the exact purchase, and completes that purchase through **PayPal Sandbox** — with durable idempotency, reconciliation of lost responses, and a downloadable evidence package.

- **Live demo:** https://quoteguard.koushikdeb.com — click **Fill to Sign in** on the login page. Every demo sign-in gets its own isolated workspace.
- **PayPal Sandbox only.** No real money moves; live mode is disabled in code. Supplier documents are synthetic.
- **Source code:** [`Codes/quoteguard/`](Codes/quoteguard/) — full README with setup, tests and configuration: [`Codes/quoteguard/README.md`](Codes/quoteguard/README.md)

![QuoteGuard](Codes/quoteguard/submission/assets/cover.jpg)

## The journey

| Step | What happens | Why you can trust it |
|---|---|---|
| Describe | Plain-English request → typed requirements (quantity, budget incl. shipping & tax, delivery date, must-haves) | A person confirms every value before it counts |
| Extract | Gemini reads supplier PDFs; every value cites a verbatim line | Citations are re-checked on the page, highlighted, number-verified and cross-checked by a deterministic parser |
| Compare | Pass / fail / **unknown** per requirement, “why the cheapest quote loses”, what-if explorer | Decimal arithmetic in code; the AI only explains; missing evidence is never a pass |
| Approve | Approver signs the exact purchase | SHA-256 of a canonical snapshot (supplier, quote version, amounts, PayPal merchant, expiry); self-approval disabled |
| Pay | PayPal Orders v2 + official PayPal buttons | Order built only from the approved snapshot; re-validated before order creation and capture; stable `PayPal-Request-Id`s |
| Prove | Receipt, decision replay, evidence package | Provider IDs, every provider call, hash-chained audit log (limits stated) |

**Agent Mode** runs a resumable workflow on your own request and PDFs (or the sample): it reads, cites, verifies and decides on its own, and stops at the three consents it cannot give — you confirm the requirements, an approver signs the exact purchase, the buyer authorises in PayPal. The assistant can query PayPal through **PayPal Agent Toolkit** read-only tools scoped by the server to the request.

**Demo Lab** runs controlled attacks through the real services: amount or payee changed after approval (even by editing the database directly), a PDF that tells the AI to ignore the budget and pay an email address, five simultaneous Pay/Capture clicks, and a capture whose response is lost.

## Measured, not claimed

- 61 backend tests on real PostgreSQL (negated specs end-to-end, recovery after expiry, wrong/missing payee, duplicate deliveries, concurrency, webhooks, Demo Lab), frontend unit tests, Playwright journeys against the live site including a real Sandbox buyer approval and capture.
- **Why AI:** on a separate holdout of 26 *unfamiliar* quote layouts (labels frozen before testing), the rules parser made 11/26 correct decisions; Gemini 2.5 Flash + QuoteGuard's checks made 24/26 in each of three runs. That run also exposed one false eligibility — fixed, regression-tested, and every later run is labelled “seen” (26/26 ×3). Development set: 24/24. Policy-level metrics are named “non-payable cases rejected by policy”; payment-boundary behaviour is tested separately. All runs are kept in [`Codes/quoteguard/reports/`](Codes/quoteguard/reports/).

## Documentation

| | |
|---|---|
| Architecture & trust boundaries | [`docs/ARCHITECTURE.md`](Codes/quoteguard/docs/ARCHITECTURE.md) |
| Payment states, sequence, reconciliation | [`docs/PAYMENTS.md`](Codes/quoteguard/docs/PAYMENTS.md) |
| Threat model | [`docs/THREAT_MODEL.md`](Codes/quoteguard/docs/THREAT_MODEL.md) |
| AI disclosure | [`docs/AI_DISCLOSURE.md`](Codes/quoteguard/docs/AI_DISCLOSURE.md) |
| Testing, evaluation, sandbox checklist | [`docs/TESTING.md`](Codes/quoteguard/docs/TESTING.md) |
| Deployment (self-host, Docker Compose, Render) | [`docs/DEPLOYMENT.md`](Codes/quoteguard/docs/DEPLOYMENT.md) |
| Build status | [`BUILD_STATUS.md`](Codes/quoteguard/BUILD_STATUS.md) |
| Demo video production script | [`Video_Script.md`](Video_Script.md) |
| Submission copy & demo script | [`submission/`](Codes/quoteguard/submission/) |

## Stack

Python 3.12 · FastAPI · SQLAlchemy · Alembic · PostgreSQL · LangGraph · Gemini (OpenAI-compatible API) · PayPal Orders v2 / Payments v2 / JS SDK · React 19 · TypeScript · Vite · Tailwind CSS · TanStack Query · AG Grid Community · Playwright.

## Limits

Synthetic documents only; PayPal Sandbox only; one configured sandbox merchant; USD checkout; delivery dates are supplier claims; the audit hash chain is not tamper-proof against a database administrator; model output varies between runs.

## License

MIT — see [`Codes/quoteguard/LICENSE`](Codes/quoteguard/LICENSE).
