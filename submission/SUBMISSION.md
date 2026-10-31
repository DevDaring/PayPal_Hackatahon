# QuoteGuard — Devpost submission copy

**Tagline:** From supplier PDF to approved PayPal purchase — with evidence for every decision and checks before money moves.

**Categories:** Best Use of PayPal + AI (primary) · Agentic Commerce (secondary)

**Try it:** https://quoteguard.koushikdeb.com — click **Fill to Sign in** on the login page (each sign-in gets its own isolated demo workspace). PayPal runs in **Sandbox**; documents are synthetic.

## Inspiration

Small-business operations managers buy equipment from PDF quotes. The headline price is rarely the real price: shipping hides in a footnote, a connector is wrong, a quote has expired. Approvals happen in chat threads that say “looks good” — and then someone pays an amount nobody actually approved. AI agents that “just buy things” make this worse unless every step is grounded and checked.

## What it does

1. **Describe** the purchase in plain language — QuoteGuard drafts typed requirements (quantity, budget incl. shipping & tax, delivery date in your timezone, must-haves) for a person to confirm.
2. **Extract** supplier PDFs with Gemini. Every value cites a verbatim line; QuoteGuard verifies the line is on that page, draws its bounding box, checks the number appears in it, and cross-checks with a deterministic parser. Click any number to see where it came from.
3. **Compare** with deterministic Decimal arithmetic: pass / fail / **unknown** — missing evidence is never a pass. It explains *why the cheapest quote loses* (Harbor's $470 quote is USB-A) and *what's hidden* (Northstar's $160 expedited shipping), and a what-if explorer shows that raising the budget to $650 makes Northstar compliant but still not best.
4. **Approve the exact purchase.** The approver signs a SHA-256 hash of a canonical snapshot: supplier, quote version and document hash, items, amounts, currency, PayPal merchant, policy version, expiry. Self-approval is disabled.
5. **Pay with PayPal.** The backend builds the PayPal Orders v2 order only from the approved snapshot (the browser cannot send an amount or payee), re-validates the snapshot before order creation and again before capture, and checks the order's amount, currency, custom ID and payee before capturing. Both organisation approval and PayPal buyer approval are required.
6. **Prove it.** Receipt with order/capture IDs, a Decision Replay of actual recorded events, every provider call, a hash-chained audit log, and a downloadable PDF/JSON evidence package.

**Demo Lab** lets judges attack it: change the amount or payee after approval (including by editing the database directly), upload a PDF that tells the AI to ignore the budget and pay an email address, click Pay five times at once, or drop PayPal's capture response mid-flight. Each scenario runs the real services and reports what actually happened.

## How we built it

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, httpx. A shared domain package is used by the API, the worker and Demo Lab.
- **Agent workflow:** LangGraph `extract_quotes → evaluate_constraints → summarize_recommendation`, with node progress persisted in PostgreSQL so restarts resume. The model gets page text and returns JSON — no tools, no HTTP, no payments.
- **AI:** Gemini 2.5 Flash through its OpenAI-compatible endpoint (swappable for OpenAI or OpenRouter), versioned prompts, bounded calls, and an extraction cache keyed by document hash, prompt, schema and model.
- **PayPal:** Orders v2 create/get/capture and Payments v2 refunds from the backend with stable `PayPal-Request-Id`s per logical operation; official PayPal JS SDK buttons for buyer approval; webhook signature verification; reconciliation by authoritative lookup.
- **Durability:** a PostgreSQL jobs table (transactional outbox), row locks in one global order, unique constraints per approval, no DB transaction held during provider calls, and a crash-recovery sweep.
- **Frontend:** React 19 + TypeScript + Vite, Tailwind v4, TanStack Query, **AG Grid Community** for the evidence-linked comparison grid, accessible dialogs, keyboard navigation, reduced-motion support.
- **Quality:** 33 backend tests on real PostgreSQL (concurrency, lost responses, restarts, forged/duplicate/out-of-order webhooks, cross-workspace access, Demo Lab), Vitest, and a Playwright journey against the live deployment.

## Challenges

- **Making “unknown” first-class.** It is tempting to treat a missing shipping line as $0. QuoteGuard refuses, and the UI makes the gap visible and actionable.
- **Concurrency that only shows up under load.** Our own tests found an inverted lock order (payment row vs. request row) that deadlocked concurrent captures/refunds, and stale optimistic-lock versions on locking reads. Both are fixed and covered.
- **Trusting the model less.** Our first live evaluation found one unsafe case: the model claimed a currency was “explicitly stated” when only “$” appeared. We now verify that claim against the document. We changed the system, not the labels.

## Accomplishments

- A complete purchase journey running against **real PayPal Sandbox**, where every number on screen links to its source line.
- Measured evaluation on 24 labelled synthetic quotes (clean, ambiguous, malformed, adversarial). Latest Gemini run: 24/24 decisions agree with labels, 18/18 unsafe cases blocked, 0/6 false blocks, 379/380 evidence references valid. Single run, synthetic templates — see limitations.

## What we learned

Grounding is a pipeline, not a prompt: citations only help if the system re-checks them, and payments need the same discipline — idempotency keys are not enough without durable operation records, lock ordering and reconciliation.

## Impact hypothesis

For a small team buying a few thousand dollars of equipment a month, the value is fewer surprise costs, approvals that mean something, and an audit trail that takes seconds instead of an afternoon. We have not measured savings with real customers; that is the next step.

## What's next

Real supplier documents and a larger evaluation set; multi-merchant flows via PayPal's partner/platform APIs; budget sync with accounting tools; Bengali/Hindi request input; an external anchor for the audit chain.

## Built with

python · fastapi · postgresql · sqlalchemy · alembic · langgraph · gemini · paypal-orders-api · paypal-js-sdk · react · typescript · vite · tailwindcss · ag-grid · tanstack-query · playwright · caddy

## Honest limits

Synthetic documents only. PayPal Sandbox only (no real money). One configured sandbox merchant. USD checkout only. Delivery dates are supplier claims. The audit hash chain detects ordinary edits but not a privileged database administrator. Model output varies between runs.
