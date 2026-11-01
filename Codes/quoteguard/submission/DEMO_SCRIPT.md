# Demo video — script and shot list (target 2:45)

Record the real app at https://quoteguard.koushikdeb.com (1440×900, browser zoom 100%). Before recording: sign in once, run all five Demo Lab scenarios so results are ready, and open a sandbox personal (buyer) account in another tab. If any wait is trimmed, add a small “sped up” caption — never cut a step so that it looks like it happened.

On-screen labels to keep visible: “Synthetic supplier documents”, “PayPal Sandbox”, “Demo Lab · controlled test”.

| Time | Shot | Voice-over |
|---|---|---|
| 0:00–0:15 | Login → **Fill to Sign in** → Overview hero. | “Small teams buy from PDF quotes. The cheapest number is rarely the real price, and approvals rarely match what gets paid. QuoteGuard takes you from a supplier PDF to an approved PayPal purchase — with evidence for every decision.” |
| 0:15–0:30 | **Watch the agent work** → Run the agent → requirements chips → *Confirm requirements & continue* → nodes light up. | “The agent drafts structured requirements from plain English, then stops: nothing counts until a person confirms. Then it gathers quotes, reads and cites every term, verifies, and decides — on its own.” |
| 0:30–0:45 | **Load 3 sample quotes** → cards fill in. Click Northstar's shipping → drawer highlights “$160.00” on the PDF. | “Three synthetic supplier quotes. Every extracted value cites the exact line it came from — here's Northstar's hidden $160 expedited shipping, highlighted on the page.” |
| 0:45–1:05 | Compare: ClearWave **$570** recommended; “Why the cheapest quote loses” (Harbor USB-A). Drag budget to **$650** → “Northstar compliant, ClearWave still best”; tap **$560** → “No compliant quote.” | “Totals and checks are deterministic decimal maths; the AI only explains. Harbor is cheapest but USB-A. What-if: at $650 Northstar qualifies but still isn't best; at $560 nothing qualifies, and QuoteGuard won't force a pick.” |
| 1:05–1:25 | Review exact purchase → switch to **Avery (approver)** → Approve → snapshot hash + expiry. Cut to Demo Lab card **Amount changed after approval** (pre-run): “Blocked as expected” with the diff `amounts.total 590 → 610`. | “The approver signs a hash of the exact purchase: supplier, amount, PayPal merchant, expiry. In Demo Lab, when the amount changes after approval — even by editing the database directly — execution is blocked and needs a fresh approval.” |
| 1:25–2:05 | Pay step → **Pay with PayPal** → sandbox buyer logs in and approves → back: “Capture confirmed” → Receipt with order and capture IDs, “Verified by PayPal Sandbox”. | “Now a real PayPal Sandbox checkout. The order is built on the server from the approved snapshot — the browser can't change the amount or payee. The buyer approves in PayPal; we verify the order's amount and payee, capture, and show the confirmed capture ID.” |
| 2:05–2:25 | Receipt → scroll **Decision replay** → click **Evidence package (PDF)**. Cut to Demo Lab **Duplicate clicks** (“1 operation, 1 provider capture”) and **Lost response** (“reconciling → recovered”). | “Decision Replay shows what actually happened, and the evidence package exports it. Five simultaneous clicks make one payment; if PayPal's response is lost, the payment reconciles by lookup instead of charging twice.” |
| 2:25–2:45 | Evaluation page: 24 cases, 18/18 unsafe blocked, 0 false blocks, run timestamp + model. End on Overview. | “We measure it: 24 labelled quotes including adversarial ones. Limits: synthetic documents, sandbox only, one merchant. Built for small operations teams who want AI-assisted buying they can actually audit. That's QuoteGuard.” |

Word count ≈ 330 → about 2:40 at a calm pace.

## Shot checklist

- [ ] Login with jury card visible
- [ ] Requirements with exact deadline date
- [ ] Evidence drawer with amber highlight
- [ ] Comparison grid + recommendation + why-cheapest-loses
- [ ] What-if $650 and $560
- [ ] Approval with hash and countdown
- [ ] Demo Lab amount-changed result
- [ ] Real PayPal Sandbox popup and approval
- [ ] Receipt with order + capture IDs
- [ ] Decision replay + evidence PDF
- [ ] Demo Lab duplicate + lost-response results
- [ ] Evaluation dashboard with timestamp/model
