**QuoteGuard — strategy to compete for a PayPal AI Hackathon prize**

Reviewed on **1 November 2026, UTC** against local revision `3d9d882`, the deployment in `/home/Debz/Host/quoteguard/`, the running application, and current official hackathon pages. This document proposes improvements; it does not claim they have been implemented. Prize priorities are my assessment, not predictions of judges' decisions.

**Recommendation: focus on Best Use of PayPal + AI, strengthen the overall entry, and pursue AG Grid as a conditional second prize opportunity.** QuoteGuard already has enough features for a substantial entry. The highest-value work is to fix gaps in its central trust promise, demonstrate why AI is useful on unfamiliar documents, and make the complete purchase story immediately understandable. A larger feature list will contribute less than credible evidence that the existing product works.

Suggested positioning:

> QuoteGuard helps small operations teams turn supplier quotes into an evidence-backed PayPal purchase. Every decision links to its source, and the payment must match what a person approved.

Keep the existing 30-headset purchase as the main story. Add one unfamiliar quote and one controlled failure to establish that the product works beyond its prepared examples.

**1. Prize strategy and competition requirements**

The published deadline is **12 November 2026, 20:00 UTC** (12:00 PST). There are no prescribed tracks. The relevant awards are below; priorities reflect product fit, not estimated odds. [Official overview and prizes](https://paypalaihackathon.devpost.com/)

| Target | Award | Recommendation | Evidence that would make the entry persuasive |
|---|---|---|---|
| Best Use of PayPal + AI | $5,000 | Primary | AI interprets unfamiliar quotes; approved evidence determines a real Sandbox order; capture and recovery preserve the purchase constraints. |
| Overall places | $12,000 / $8,000 / $5,000 | Compete through the same product | Strong execution plus a clear customer, useful workflow, measured results, and coherent presentation. |
| Best Demo Delivery | $5,000 | Strong secondary fit | A concise, readable video shows a problem, a surprising finding, a successful checkout, and proof. |
| Best Use of Agentic Commerce | $5,000 | Conditional | A resumable workflow accepts a user's request and documents, handles exceptions, and completes the authorized commerce journey. |
| Best Use of AG Grid | $5,000 / $2,000 / three $1,000 awards | Sponsor target, with a time limit | An evidence dashboard with useful interaction and a working Studio agent enhancement. |
| Most Impactful | $5,000 | Supporting opportunity | Observed results from actual intended users; the current synthetic example alone is insufficient evidence of impact. |

One project may receive one Grand Prize **or** one Honorable Mention, plus one Sponsor Prize. These are complementary targets, not a stack of all the awards above. Five judging dimensions carry equal weight: implementation, design, impact, innovation, and presentation. Judging runs **1–15 December 2026**, ending at **16:00 UTC on 15 December**; keep the submitted build available through then. [Official Rules, sections 1, 4, 6 and 8](https://paypalaihackathon.devpost.com/rules)

**AG Grid requires a strategy adjustment.** Its sponsor page emphasizes AG Studio, polished dashboards, custom widgets/layout, and the Studio Agent Framework. The rules allow any AG Grid tools, so Community usage establishes eligibility, but the current comparison table does not fully address that stated emphasis. Treat Studio as an opportunity to improve sponsor fit, not as a mandatory rewrite. [AG Grid sponsor brief](https://paypalaihackathon.devpost.com/details/aggrid)

APIMatic is a fallback opportunity only if its PayPal Context Plugin is actually used for remaining integration work and that contribution is documented. Installing a tool or adding a logo is not a useful product improvement. Do not migrate hosting or add unrelated sponsor integrations merely to collect names. [APIMatic sponsor brief](https://paypalaihackathon.devpost.com/details/apimatic)

**2. What I verified, and what is already strong**

| Evidence | Observation | Scope of confidence |
|---|---|---|
| Source versus deployed backend | All 55 Python files under `backend/quoteguard` matched their deployed copies byte for byte. | Backend source parity; not a complete environment or frontend artifact comparison. |
| Running site | HTTPS homepage, health, and readiness responded successfully. Readiness reported PostgreSQL connected, Gemini configured, and PayPal Sandbox configured. | A point-in-time check, not an uptime or provider transaction test. |
| Browser journey | Fresh demo sign-in → Agent Mode → confirmed requirements → three extracted quotes → ClearWave recommendation → comparison → $560 what-if → evaluation. | Real hosted workflow; no new PayPal order or capture was initiated in this review. |
| Recommendation | ClearWave $570; Harbor $470 fails USB-C; Northstar $640 includes $160 shipping and exceeds the $600 budget. | Observed in the browser. |
| Time to recommendation | Approximately 12.8 seconds from initial browser navigation to the approval checkpoint in one run. | Cache and network state uncontrolled; do not publish as a general latency claim. |
| UI | Cohesive styling, source-linked values, explicit synthetic/Sandbox labels, clear purchase steps. No page exceptions occurred in the inspected journey. | Desktop inspection at 1440 × 1000; not a full accessibility or browser audit. |
| Stored evaluation | Latest report records 24/24 decision agreement, 18/18 non-payable cases blocked by policy, and 379/380 valid evidence references. | Historical results read from committed reports, not rerun here. |
| Existing payment evidence | `BUILD_STATUS.md` records a completed Sandbox capture and verified webhooks. | Existing project evidence; not independently repeated during this review. |

Preserve the useful foundations: deterministic money arithmetic, explicit unknowns, versioned corrections, approval snapshots, real Sandbox integration, operation records, Decision Replay, Demo Lab, evidence exports, and isolated demo workspaces. They are already implemented; rebuilding them would waste time.

The main remaining judging gaps are:

| Dimension | Current gap | Best improvement |
|---|---|---|
| Implementation | Some edge paths contradict the strongest safety claims. | Close the policy and recovery gaps below, with focused regression evidence. |
| Design | The comparison's evidence grid appears below a large explanation; Agent Mode is tied to the sample and local component state. | Put the decision and evidence together; support resuming a real user request. |
| Impact | Submission copy explicitly says customer savings have not been measured. | Run a small observed user study and report its actual results. |
| Innovation | AI purchasing and approval workflows already exist. | Demonstrate the trace from source evidence through approval to confirmed payment and recovery. |
| Presentation | A detailed script exists, but it mixes the automatic and manual sample paths. | Rehearse one consistent route and record the final functioning build. |

**3. Fix these before adding features**

**P0-A — mandatory attributes can pass despite explicit negation.** In [policy.py](Codes/quoteguard/backend/quoteguard/domain/policy.py), `_match_attribute()` accepts substring matches. Isolated calls to the real policy evaluator, with otherwise valid quote facts, produced these results:

| Input attribute | Current result | Required result |
|---|---|---|
| Connector: `USB-C not supported` | All mandatory checks pass; payment eligible | Fail, or unknown pending clarification |
| Microphone: `no microphone` | All mandatory checks pass; payment eligible | Fail |
| Microphone: `microphone not included` | All mandatory checks pass; payment eligible | Fail |

These are reproduced policy-layer defects. I did not establish that every example passes through the complete PDF ingestion pipeline unchanged. That distinction matters, but the final policy boundary must reject them regardless of which extractor supplied the facts.

Use typed normalized attributes with explicit supported/unsupported/unknown values. Retain the source phrase and citation alongside the normalized value. Handle negation and contradictory statements before positive matching; ambiguous prose must remain unknown. Review the analogous first-match extraction behavior in [rules_extractor.py](Codes/quoteguard/backend/quoteguard/documents/rules_extractor.py), and the semantic support checks in [quote_extractor.py](Codes/quoteguard/backend/quoteguard/ai/quote_extractor.py).

**Acceptance:** positive, negative, contradictory, and conditional phrases have regression coverage; a complete document-to-approval test rejects the negative cases; malformed normalization cannot turn an unknown into a pass. Include examples such as “USB-C charging only; audio via USB-A.” Matching a real sentence on a page does not prove that the sentence supports the extracted interpretation.

**P0-B — recovery must preserve the normal checkout checks.** In [payments.py](Codes/quoteguard/backend/quoteguard/services/payments.py), `reconcile()` can call `capture_order()` when an order is approved and the local operation is reconciling/capture-pending. That branch does not call the approval revalidator or `_validate_order_for_capture()` used by normal capture.

An isolated control-flow probe with mocked database/provider dependencies reached capture even when the approval guard was configured to reject and the provider summary contained a different operation/payee. Neither guard was called. This establishes a missing check in that branch, not an exploit demonstrated against PayPal. Separately, the pure order validator returned no error when the provider payee was missing.

Centralize the checks used before any new capture attempt. Verify operation association, amount, currency, payee, approval integrity and applicable expiry rules, while preserving the existing operation and idempotency key. A missing payee must trigger further authoritative verification or manual review, not silently count as a match. Review recovery of uncertain order creation as well.

Distinguish two recovery cases explicitly:

- **A capture already happened:** verify and record the provider result, even if the approval has since expired. Do not lose a receipt or create a replacement payment.
- **A capture has not happened:** recheck authority and provider order details before issuing a side effect. Define expiry behavior clearly, including uncertain provider outcomes; do not discard the original operation and start again.

**Acceptance:** exercise expiry during recovery, wrong/missing payee, wrong operation ID, changed amounts, duplicate worker/webhook delivery, and an already-completed capture after expiry. Prove both “no unauthorized new capture” and “existing captures are correctly reconciled.” Use isolated PostgreSQL and fake-provider tests, followed by a controlled Sandbox rehearsal. Do not run destructive test fixtures against the hosted database.

**P0-C — make the evidence claims precise.** [evaluation.py](Codes/quoteguard/backend/quoteguard/services/evaluation.py) derives the “unsafe payments blocked” metric from `not o.payment_eligible`; it does not attempt a PayPal transaction for each evaluation case. Rename it **“Non-payable cases correctly rejected by policy.”** Report actual payment-boundary tests separately. Likewise, replace “2 costly mistakes avoided” with “2 purchasing issues detected in this sample” until real avoided mistakes have been observed.

Keep “supplier claim” on delivery estimates. Use “meets confirmed requirements” instead of an unconditional “safe choice.” Preserve the stated limits of the audit hash chain and the distinction between real Sandbox activity and simulated Demo Lab results.

**P0-D — close the submission packaging gap.** The repository is public, but the MIT license is nested at [Codes/quoteguard/LICENSE](Codes/quoteguard/LICENSE); there is no root `LICENSE`. Add the same appropriate license at the root and confirm GitHub recognizes it. Complete the repository About description and website. The public GitHub page currently leaves those fields empty. [Repository reviewed](https://github.com/DevDaring/PayPal_Hackatahon)

The submission needs a working build or complete setup instructions, public licensed source, tool disclosure, and a public YouTube demonstration under three minutes. Make these easy to find from the root README. [Submission requirements](https://paypalaihackathon.devpost.com/)

**4. Establish why AI improves the product**

The most consequential evaluation finding is that the existing **rules-only baseline also scores 24/24**. Its recorded median is **35 ms**, versus **4,526 ms** for the latest AI run. These are separate historical runs, not a controlled performance comparison, but the present dataset does not establish an incremental decision benefit from AI. Sources: [rules report](Codes/quoteguard/reports/evaluation-20261031-1904-rules.json), [latest AI report](Codes/quoteguard/reports/evaluation-20261031-1913-llm.json).

A judge can reasonably ask why a model is necessary. Answer with measured generalization to supplier language and layouts that the simple parser cannot handle.

Create a new, frozen holdout set of **at least 24 additional quotes**, with labels written independently before evaluation. Include unfamiliar layouts, prose instead of field labels, multi-page conditions, revised offers, optional versus included charges, negated specifications, ambiguous currencies, and image-only documents. Use permissioned/redacted real examples where possible; otherwise identify the examples as synthetic and construct them independently of the existing fixture generator. Do not tune on the holdout and continue describing it as unseen.

Evaluate rules and AI against the same inputs and labels. Repeat the final AI configuration at least three times and retain every run, including failures. Report extraction completeness/correctness, citation support, decision agreement, false eligibility, false blocks, review burden, latency, and measured token usage/cost where available. Separate invalid citations, unsupported meanings, and missing evidence: these are different failure modes.

**Release criterion:** zero false eligibility on the known critical negative cases, all negative payment-boundary tests passing, and demonstrable improvement on unfamiliar documents without silently weakening checks. Treat these as release gates, not claims of universal safety. If AI adds no measurable benefit on the new set, state that result and narrow the product's AI claim to the tasks it actually improves.

Use one held-out quote in the demo: show an unusual supplier sentence, the extracted term, its evidence, and the resulting decision. Keep the deterministic calculation visible. This is a stronger demonstration than a larger model name or a more elaborate chat panel.

**5. Turn the guided sample into a dependable user workflow**

[AgentMode.tsx](Codes/quoteguard/frontend/src/pages/AgentMode.tsx) starts with `/demo/sample-request` and loads `/sample-quotes`. Its active request and progress live in React state, several stages advance after fixed delays, and two polling loops have no deadline. The backend persists request work, but the Agent Mode screen does not restore that work on mount. Its catch path can leave the run active, and failed extraction can leave comparison polling waiting indefinitely.

Improve this existing screen rather than creating another experience:

- Accept a request ID in the route and reconstruct progress from stored request/events. Refreshing or returning to the screen must resume the same request.
- Support the existing user-entered request and uploaded documents. Offer the sample as a clearly labeled shortcut.
- Derive stage state from service results. Distinguish succeeded, needs review, failed, waiting for approval, and waiting for PayPal buyer consent.
- Add bounded polling, cancellation, actionable errors and retry/resume controls. Surface extraction failure instead of marking the reading stage complete and waiting forever.
- Let the person edit parsed requirements at the confirmation checkpoint.
- Explain the actual consent sequence: requirements confirmation, organizational approval, then buyer authorization in PayPal. “Exactly two human checkpoints” currently understates the payment interaction.

**Acceptance:** an unfamiliar quote can travel through this workflow; refresh resumes; a failed document and a model timeout produce actionable states; retry does not duplicate documents or requests; checkout still uses the existing authenticated approval/payment services. The model must never invent payment authority.

For the comparison screen, keep the visual design and improve density. At the inspected desktop size, the grid begins below the first viewport, while the generated explanation occupies much of the screen. Put a compact recommendation, the key exception, and the evidence grid near the top; expand the full explanation on demand. Keep approval visible and make opening a source cell obvious.

When what-if is active, show **“Confirmed purchase: $600 budget”** and **“Preview: $560 budget”** together. The current original recommendation remains visible above a preview saying no supplier qualifies; both are legitimate, but their relationship needs to be immediately clear. Give budget inputs a range appropriate to the current request instead of the sample-specific $400–$900 limits.

**6. Add a focused AG Studio enhancement only after the core fixes**

Proposed feature: a **Purchase Evidence Dashboard** built from the current request's real stored data. Reuse the comparison and evidence viewer, the what-if service, approval information, and payment operation records.

The dashboard should answer practical questions: which requirements fail, what evidence supports the selected quote, what changes under a different budget, and whether the eventual payment matches the approved purchase. Use a compact cost-breakdown widget, requirement-status widget, and payment/approval widget. Keep preview values separate from confirmed purchase values.

Add one working Studio agent interaction:

> “Show quotes with uncertain costs, compare the $560 and $650 budgets, and open the evidence behind the recommendation.”

The agent may configure widgets, filter request-scoped data, request a deterministic what-if calculation, and open evidence. It may not change confirmed requirements, approvals, merchant bindings or payment authority. Natural-language actions should visibly change the dashboard and be reversible. Persist the layout and restore it after refresh.

This is my proposed product enhancement, not an official sponsor requirement. AG Studio has a React component and supports custom/server-connected agent execution; assess integration against the installed React/grid versions before committing to it. [React quick start](https://www.ag-grid.com/studio/react/quick-start/), [agent integration documentation](https://www.ag-grid.com/studio/react/ai-agents/)

**Decision gate:** allow a four-hour prototype and a maximum of roughly ten hours total. Continue only if real request data renders, one agent action works, existing checkout remains unaffected, and the license remains valid throughout judging. Otherwise keep the existing Community grid, improve its evidence interaction, and focus on the primary prize. Do not leave an unfinished sponsor dashboard in the main journey. The sponsor advertises a 45-day trial; check the actual expiration date. [Sponsor access information](https://paypalaihackathon.devpost.com/details/aggrid)

The existing [CompareStep.tsx](Codes/quoteguard/frontend/src/components/CompareStep.tsx) CSV export also deserves a small hardening change: sanitize spreadsheet-formula prefixes in supplier-provided text and test exported values. AG Grid documents the behavior of exported values and the formula-injection concern. [CSV export documentation](https://www.ag-grid.com/react-data-grid/csv-export/)

**7. Make the customer and differentiation credible**

Start with a narrow customer hypothesis: a small support team, agency, or training business where one operations person compares a few equipment quotes and a second person approves the purchase. Validate that these users actually encounter PDF quotations and can buy from suppliers accepting PayPal. The current product supports one configured Sandbox merchant; it is not yet a general supplier-payment platform.

Do not claim that AI procurement or reapproval after changes is new. Ramp already documents quote-based intake, approval workflows, and reevaluation of approvals after relevant changes. That makes a broad “AI procurement assistant” claim weak. QuoteGuard's proposed differentiation is its compact, inspectable evidence-to-payment workflow for a smaller purchasing task. This is positioning to validate, not proof that competitors lack similar controls. [Ramp's documented procurement flow](https://support.ramp.com/how-to-submit-procurement-requests/)

Before recording, recruit **three to five relevant people** for a short observed task. Give each comparable manual and QuoteGuard tasks, alternate task order, and record time to decision, correct supplier selection, overlooked terms, required corrections, and whether the approval/payment explanation is understood. Record sample size and limitations. Obtain permission before quoting feedback or publishing documents. These sessions are a usability signal, not a representative market study.

Use the outcome to write a defensible impact sentence: “In N observed sessions, participants completed X and encountered Y.” Leave the numbers blank until measured. Do not convert the sample's $160 shipping line into money saved; it is a disclosed supplier charge, and no purchase loss has been observed.

A plausible first business model is a workspace subscription for small teams, contingent on validating repeated use and willingness to pay. Do not build subscriptions, charge transaction fees, or claim a price customers accepted before testing the need. A useful next commercial milestone is one design partner willing to use the product on recurring purchases.

**8. Rebuild the demo around one purchase and one failure**

Use a **2:40–2:50** recording target. The first screen should show the purchasing problem, not a login procedure. Prepare a fresh isolated workspace, then record actual product behavior. Preserve visible Sandbox/synthetic labels and label any accelerated waits or simulated scenario.

| Time | Show | Purpose |
|---|---|---|
| 0:00–0:15 | $600 request and the three quotes | Identify the buyer and the decision; establish the stakes. |
| 0:15–0:40 | AI extracts a less familiar quote; open its source evidence | Demonstrate useful interpretation and traceability. |
| 0:40–1:00 | Harbor's wrong connector, Northstar's shipping, ClearWave at $570 | Make the recommendation understandable without reading paragraphs. |
| 1:00–1:20 | Exact purchase approval, with supplier, amount and payee readable | Connect the decision to the authorized payment. |
| 1:20–1:55 | Actual PayPal Sandbox buyer consent, capture, and receipt | Prove the commerce journey works end to end. |
| 1:55–2:15 | One controlled changed-payee or changed-amount scenario blocks execution | Establish the main differentiator with a visible before/after. |
| 2:15–2:35 | Evidence package and the final honest evaluation/user findings | Substantiate the trust and impact claims. |
| 2:35–2:50 | Clear closing product screen and demo URL | Leave the audience with the customer benefit. |

If Studio is finished and useful, replace about ten seconds of the comparison segment with its working agent interaction. Do not cram every feature into the video. Keep duplicate-click and lost-response cases available in Demo Lab and the README for deeper inspection.

Correct the existing [DEMO_SCRIPT.md](Codes/quoteguard/submission/DEMO_SCRIPT.md): Agent Mode already loads the three quotes, so a subsequent manual “Load 3 sample quotes” step is inconsistent. Synchronize [SUBMISSION.md](Codes/quoteguard/submission/SUBMISSION.md), the READMEs, and build status; the submission currently says 33 backend tests while other files say 34. Use the verified final test count. The root `Video_Script.md` is empty; there is no need to maintain two conflicting script locations.

Prepare three strong stills: evidence beside comparison, an approval mismatch blocking execution, and the actual Sandbox receipt. Show a real capture ID from the final rehearsal with its provenance; do not manufacture proof. Test the final YouTube link signed out and verify readable text and captions.

**9. Execution plan for the remaining time**

Assumption: one builder with roughly 50–65 focused hours available before the deadline. Estimates are planning ranges, not promises. If less time is available, preserve the order below and drop the sponsor enhancement first.

| Window, UTC dates | Work | Effort | Exit condition |
|---|---|---:|---|
| Nov 1–2 | P0 policy/recovery fixes; precise metric labels; root license | 10–14 h | Critical regressions pass; failure claims match the implementation. |
| Nov 3–4 | Agent resume/error states; comparison layout; build independent holdout | 10–12 h | A user-provided request survives refresh and an extraction failure; labels frozen. |
| Nov 5 | Run comparative evaluation; begin observed user sessions | 5–7 h | AI contribution and limitations are recorded with raw evidence. |
| Nov 6–7 | Conditional Studio prototype and integration | 4–10 h | Keep only if its useful agent interaction is reliable; otherwise stop. |
| Nov 8 | Finish user sessions; refine copy; integrated Sandbox rehearsal | 5–7 h | One coherent purchase plus one controlled failure works on the final candidate. |
| Nov 9–10 | Record video, screenshots and submission; rehearse judge access | 8–10 h | Complete submission package; outside user can follow the instructions. |
| Nov 11 | Submit and verify links; freeze the submitted release | 3–4 h | Submission receipt, public video/repository, working demo and tagged source agree. |
| Nov 12 | Buffer for verified blockers before 20:00 UTC | Reserve | No new feature work. |

A **48-hour minimum plan** is: close the two critical defects, correct evidence labels and licensing, demonstrate AI on a small frozen unfamiliar set, rehearse the real Sandbox purchase, and record a clear video. Omit Studio and broader workflow expansion if they threaten these essentials.

Keep development separate from the submitted deployment after freeze. The rules limit post-deadline submission changes; retain the exact release and its evidence for judging. [Official Rules, section 5](https://paypalaihackathon.devpost.com/rules)

**10. Final release gates**

- [ ] Negative and contradictory specifications cannot become payable merely through substring matching.
- [ ] Normal capture and recovery enforce the same required authority/provider checks; completed captures still reconcile after expiry.
- [ ] A new user can complete the intended workflow, understand previews, recover from extraction errors, and resume after refresh.
- [ ] The AI claim is supported by a frozen comparison with the baseline; all final repeated runs and remaining errors are disclosed.
- [ ] Actual Sandbox captures, simulated provider scenarios, and policy-only evaluations are labeled separately.
- [ ] Video, submission text, source revision, screenshots, and hosted behavior agree.
- [ ] The public repository has a root license, clear setup, demo access instructions, and accurate tool attribution.
- [ ] The existing secret-check script and an inspection of exported artifacts find no private server credentials. Demo buyer access is Sandbox-only.
- [ ] Final verification includes backend boundary tests, frontend checks, the real browser journey, and a controlled Sandbox capture/webhook rehearsal. Historical green tests are not a substitute for checks on the submitted revision.
- [ ] API and worker have restart supervision, storage/database backup, sufficient AI quota and disk capacity, and monitoring through judging. Current `run.sh` launches detached processes; verify an external supervisor or add one so a later worker crash does not leave analysis stalled.
- [ ] Seeded documents and fresh workspaces remain usable in December; old approvals/quotes are clearly expired rather than presented as ready to pay.
- [ ] The demo, Sandbox access, model access and any Studio license remain usable through **15 December, 16:00 UTC**.

**Scope to defer:** multi-merchant onboarding, live money, payouts, lending, escrow, ERP integration, a supplier marketplace, broad multilingual/voice features, and production fraud guarantees. Also defer promoting refunds until the implemented partial-refund path has a complete recovery story and a Sandbox rehearsal; its ambiguous state currently lacks the checkout path's explicit reconciliation scheduling.

The next work should produce a smaller set of stronger claims: the selected quote is supported by evidence, the approval covers that exact purchase, PayPal confirms the intended payment, failure recovery preserves those facts, and intended users can understand the result. Those claims connect the product directly to the strongest prize targets.
