# Threat model

Scope: the purchase path from supplier document to PayPal Sandbox capture. Assets: the organisation's money (here, sandbox funds), approval authority, the integrity of the evidence record, and workspace data.

## 1. Document injection

| Threat | Control | Evidence |
|---|---|---|
| PDF text instructs the model (“ignore the buyer's budget”, “you are the approver”, hidden 6-pt text) | Pages are delimited as untrusted data; the system prompt states the model cannot approve/pay/change budgets; the model has **no tools**; output is schema-validated (`extra="forbid"`) | `test_malicious_pdf_cannot_change_policy_permissions_or_payee`, Demo Lab *malicious_pdf*, eval cases `adv-*` |
| Model invents or alters numbers | Each value must cite a verbatim line on a page; the line is located on that page; the number must appear in its own evidence; critical amounts are cross-checked against a deterministic parser; disagreements force review | `verify()` in `ai/quote_extractor.py`; eval “evidence references valid” |
| Model claims a currency is explicit when only “$” is printed | ISO code must appear in the document text, otherwise the currency is *inferred* → check is *unknown* | fixed after an evaluation run caught it (see TESTING.md) |
| Model reads a spec correctly but the sentence negates or conditions it (“microphone not included”, “USB-C charging only; audio via USB-A”) | `domain/attributes.py` assesses the extracted value **and** the cited sentence per clause (negation, optional/add-on, charging-only, conflicting values); the worse result wins; unknown is never promoted to pass | parametrised tests + end-to-end approval rejection |
| Eligibility decided by the model | Totals and pass/fail/unknown are computed by `domain/policy.py` with `Decimal`; explanations that name a different supplier are discarded | `test_reference_quotes_exact_totals_and_outcomes` |
| Malicious file structure | Header/encryption/page-count checks; parsing in a child process with `RLIMIT_AS` 1 GB, `RLIMIT_CPU` 30 s and a 60 s timeout; files stored under server-generated keys outside the web root | `documents/ingest.py` |

Suspicious-text detection (`documents/injection.py`) is an informative signal shown to reviewers. It is **not** the control: the controls above apply whether or not a pattern matches. A few fixtures do not prove immunity to prompt injection.

## 2. Approval bypass

| Threat | Control |
|---|---|
| Approve one thing, pay another | Approval binds to SHA-256 of a canonical snapshot rebuilt from the DB (request version, quote version + document hash, supplier, merchant binding id+version+merchant ID, items, amounts, currency, policy version, expiry). Order creation and capture rebuild it again and compare. |
| Approver sees stale terms | The approver posts the `terms_hash` they reviewed; the server refuses if current terms hash differs. |
| Self-approval / wrong role | Roles per workspace membership; requesters cannot approve; self-approval is a workspace policy, disabled. Demo personas are a labelled server-side switch limited to demo workspaces. |
| Expired / revoked / forged approvals | Server-side state is authoritative; HMAC token with `APPROVAL_SIGNING_SECRET` is an additional integrity check, never a substitute. |
| PayPal buyer approval used to bypass org approval | Capture requires an existing payment operation tied to a live approval; revocation cancels the operation. |
| Client changes amount/payee | Request bodies forbid unknown fields; the order is built from the stored snapshot; capture validates the provider order's amount, currency, custom_id and payee. |
| Cross-workspace object references | All lookups filter by workspace; foreign IDs return 404. |

## 3. Identity mapping (who gets paid)

- Payees exist only as admin-managed `merchant_bindings`, sandbox-only (DB CHECK), one active per supplier, versioned.
- A supplier name, email or bank detail printed in a PDF never becomes a payee. Uploaded quotes get a *suggested* supplier link; checkout requires a human-confirmed link.
- Changing a binding bumps its version and invalidates approvals that used it; a mismatch with `PAYPAL_MERCHANT_ID` disables checkout.
- Demo Lab *merchant_changed* shows both the service-path change and a direct DB tamper being blocked.

## 4. Duplicate or lost payments

- One operation per approval (unique constraint) + stable `PayPal-Request-Id` per logical operation, persisted before the call.
- Row locks in a single global order; no transaction held across provider calls.
- Lost/ambiguous responses → `reconciling` → authoritative lookup; retries reuse the same request ID; no replacement orders.
- Crash recovery sweeps in-flight operations into reconciliation.
- Webhooks: verify, dedupe, map to known operation and payee, then look up; completed state never regresses.
- Tests: concurrent checkout/capture (8 threads), lost capture response, restart after intent, duplicate/forged/unrelated/out-of-order webhooks, concurrent refunds.

## 5. Platform

- Password hashing with scrypt; constant-cost path for unknown users; DB-backed rate limits on login, uploads, AI, chat, scenarios, payments, webhooks.
- HttpOnly + SameSite=Lax + Secure session cookie, CSRF double-submit header with origin check, explicit CORS allowlist, strict CSP (PayPal domains only where the SDK needs them), HSTS, `X-Frame-Options: DENY`.
- Secrets only from the environment; the browser receives the public PayPal client ID only; exports exclude tokens, secrets and payer data; `scripts/check-secrets.sh`.
- Structured logs with correlation IDs; model calls logged with latency and token counts, not content.

## Residual risks (stated plainly)

- The audit hash chain detects ordinary edits; a database administrator could rewrite the chain. No external anchor.
- An uploaded PDF proves nothing about supplier identity, inventory or authenticity.
- LLM extraction varies between runs; the validation layer catches unsupported values but a plausible, consistently mis-read value on the right line could still pass. Human review of the comparison is part of the workflow.
- One sandbox merchant; multi-merchant (platform/partner) payouts are out of scope.
- Demo accounts are shared credentials by design; isolation is per sign-in workspace, not per person.
