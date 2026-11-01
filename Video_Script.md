# QuoteGuard — Demo Video Production Script

**Deliverable:** one MP4, **2:45–2:55** (hard limit: under 3:00), 1920×1080, 30 fps, H.264 + AAC, English voice-over, burned-in captions + `.srt`, original background music, real product footage recorded with Playwright, plus a few motion-graphic scenes.
**Upload:** YouTube, **Public**, link pasted into Devpost before **12 Nov 2026, 12:00 PST**.

This file is the single source of truth for the video. It is written for automated agents (TTS, music, animation, editing). Follow the **honesty rules** in §0 exactly; they are judging requirements, not style preferences.

---

## 0. Non-negotiable rules

1. **Real product footage only** for anything that claims to work. Every product scene comes from the Playwright recording in §2, against the live site `https://quoteguard.koushikdeb.com`. Do not mock or re-render UI.
2. **Label reality on screen:**
   - "PayPal Sandbox — no real money" during checkout, receipt and the end card.
   - "Synthetic supplier documents" in the first product scene.
   - "Controlled test" in Demo Lab.
   - **"Sped up 2×"** (or the actual factor) on any accelerated clip.
3. **No invented numbers.** Use only the numbers in §5 (measured) and the capture ID that appears in *your* recording. Never type a capture ID by hand.
4. **No third-party trademarks or copyrighted material** in your own animations: no PayPal, Anthropic, NanoGPT, Google or AG Grid logos in generated graphics, and no stock music with unclear rights. PayPal's buttons and window may appear only as they genuinely appear in the product recording.
5. **Generated video must not contain text.** Generative models garble letters. All text, numbers and labels are overlays (§7), rendered as crisp vector or HTML text.
6. **Voice-over stays inside the scene's time window.** If TTS runs long, shorten the pause or speed up the footage (and label it), never the meaning.
7. **Final length 2:45–2:55.** Judges are not required to watch past 3:00.

---

## 1. Pipeline overview

```
§2 Record product footage (Playwright, real PayPal Sandbox purchase)  → video-out/raw/*.webm, stills/, walkthrough-timeline.json
§4 Voice-over (TTS)                                                   → vo/S01.wav … vo/S11.wav
§6 Music (original, generated)                                        → music/bed.wav
§7 Motion graphics (HTML/CSS rendered by Playwright, optional AI b-roll) → gfx/*.mp4
§8 Edit & assemble (ffmpeg)                                           → build/quoteguard_demo.mp4 + .srt
§9 QA checklist → §10 YouTube upload
```

Suggested working folder: `/home/Debz/Hackathon/PayPal_Hackatahon/Video/` (do not commit large media to the repo).

---

## 2. Record the product footage (Playwright)

The repo contains a ready recorder: `Codes/quoteguard/frontend/e2e/video/walkthrough.spec.ts`, with config `playwright.video.config.ts`.

- **Session:** a fresh isolated demo workspace.
- **Interaction:** a visible teal cursor that glides to each click (Playwright videos do not show the real cursor).
- **Payment:** a **real PayPal Sandbox purchase**, with the buyer logging in inside PayPal's popup.
- **Outputs:** 1080p video, PNG stills, and scene timestamps.

```bash
cd /home/Debz/Hackathon/PayPal_Hackatahon/Codes/quoteguard/frontend
set -a; . <(grep -E '^SANDBOX_BUYER_(EMAIL|PASSWORD)=' /home/Debz/Host/quoteguard/.env); set +a
OUT_DIR=/home/Debz/Hackathon/PayPal_Hackatahon/Video/capture \
BASE_URL=https://quoteguard.koushikdeb.com \
CHROME_PATH=/home/Debz/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome \
SLOWMO=60 npx playwright test -c playwright.video.config.ts
```

Outputs in `Video/capture/`:

| File | Content |
|---|---|
| `raw/**/video.webm` (largest) | Main app footage, 1920×1080, start → end |
| `raw/**/video-1.webm` (or similar) | **PayPal popup window** (separate page = separate file) |
| `stills/*.png` | 1080p stills per scene (thumbnails, fallbacks, Devpost gallery) |
| `walkthrough-timeline.json` | `scenes[]` with `scene` id and `t_ms` = ms from start of the **main** video |

Scene ids written by the recorder: `01_login`, `02_overview`, `03_agent_start`, `04_agent_confirm`, `05_agent_working`, `06_agent_decided`, `07_compare`, `08_evidence`, `09_impact`, `10_whatif`, `11_approve`, `12_checkout`, `13_paypal_popup`, `14_receipt`, `15_replay`, `16_demolab_integrity`, `17_radar_edited_bill`, `18_radar_cover_quotes`, `19_evaluation`, `20_end`.

The two Demo Lab attacks (`16_demolab_integrity`) start together; the recorder shows the edited bill first, then returns for the cover quotes, so the second wait is usually already over.

**Clip extraction rule:** a clip for scene X runs from `t_ms[X]` to `t_ms[next scene]` in the main video. Trim dead time freely.

**Speed-ups:**
- The agent's extraction wait (`05_agent_working` → `06_agent_decided`) and the Demo Lab wait (inside `16_demolab_integrity`) may be accelerated.
- Label them with the overlay "Sped up N×".
- Use `setpts=PTS/N` to accelerate.

**Before recording:** run the recorder once as a warm-up, so the model and caches are warm. Then record the take you will use.

**If the recorder fails:** rerun it. Never stitch footage from different runs inside one continuous scene. Cutting between scenes from different runs is fine, as long as the receipt's IDs are from the same run as the checkout shown.

Optional: export `Video/capture/stills/14_receipt.png` and read the PayPal **order** and **capture IDs** from it for the description in §10.

---

## 3. Scene plan and timeline (target 2:50)

Style: calm, confident, product-first. Brand palette:
- **Navy** `#0F2541`, **teal** `#0F766E` / `#14B8A6`, **warm off-white** `#FBF8F3`, **amber** `#F59E0B` (uncertainty), **red** `#B42318` (blocked).
- Fonts: **Instrument Serif** (headlines) and **Inter** (UI and captions), both OFL.

| # | Time | Visual (source) | On-screen overlays (§7) | Music |
|---|---|---|---|---|
| S01 | 0:00–0:08 | **GFX-1 Cold open**: three paper quote cards fall onto a desk; "$470", "$570", "$640" tags flip in | "30 headsets · $600 budget · 3 supplier quotes" | Soft intro, pads only |
| S02 | 0:08–0:19 | **GFX-2 The problem**: amber "USB-A ≠ USB-C" stamp on $470; "+$160 shipping" strip on $640; then the $640 tag is scratched out and retyped "$540"; two ghost cards appear behind a third, joined by a thin red thread | "Cheapest ≠ compliant" · "Hidden costs" · "Edited bills" · "Staged competition" | Plucks enter |
| S03 | 0:19–0:25 | **GFX-3 Title**: QuoteGuard shield; tagline types in | "QuoteGuard" / "Evidence for every decision. Payments that match what you approved." | Beat enters |
| S04 | 0:25–0:42 | Product: `03_agent_start` → `04_agent_confirm` → `05_agent_working` (sped up) → `06_agent_decided` | "Synthetic supplier documents" · "Consent 1 of 3: you confirm" · "Sped up 2×" during extraction | Steady |
| S05 | 0:42–0:58 | Product: `07_compare` → `08_evidence` (zoom 140% on the highlighted PDF line, 1.5 s hold) | "Harbor $470 — wrong connector" · "Northstar +$160 shipping" · "ClearWave $570 meets every requirement" · on zoom: "Every number links to its line on the PDF" | Steady |
| S06 | 0:58–1:08 | Product: `11_approve` → approved state | "Consent 2 of 3: approver signs the exact purchase" · on hash: "Supplier · amount · PayPal merchant · expiry → one hash" | Slight lift |
| S07 | 1:08–1:30 | Product: `12_checkout` → **PayPal popup video** (6–8 s, picture-in-picture) → `14_receipt` (hold 2.5 s on IDs) | "PayPal Sandbox — no real money" (persistent) · "Consent 3 of 3: buyer approves in PayPal" · "Captured & verified by PayPal Sandbox" | Build, peak at receipt |
| S08 | 1:30–1:58 | Product: `16_demolab_integrity` (sped up wait, hold on the **Counterfactual** step) → `17_radar_edited_bill` (zoom 140% on the "Recovered original / Shown in the file now" table) | "Controlled test" · on counterfactual: "Without forensics: payable, rank 1" (red) · on table: "Recovered from the PDF's hidden revision" (teal) · "BLOCKED" stamp | Tension |
| S09 | 1:58–2:20 | Product: `18_radar_cover_quotes`: provenance graph (zoom 130%), then bid screens, then the AI memo | On graph edges: "same author" · "same original file" · "same phone" · on screens: "Cover-bidding shape (Huber & Imhof, 2019)" · on memo: "AI explains · numbers verified · verdict computed without the model" | Tension → resolve |
| S10 | 2:20–2:36 | Product: `19_evaluation` (integrity benchmark card) with **GFX-4** counters overlaid | "82 labelled cases · synthetic · deterministic" | Calm |
| S11 | 2:36–2:50 | **GFX-5 End card** | "QuoteGuard" · "quoteguard.koushikdeb.com" · "github.com/DevDaring/PayPal_Hackatahon" · "PayPal Sandbox · synthetic documents · built for the PayPal AI Hackathon" | Resolve, fade out by 2:50 |

`10_whatif` and `15_replay` are optional B-roll (2–3 s) if a scene runs short. Do not add new claims for them.

---

## 4. Voice-over

**Voice:** English, warm, clear, mid-pace (about 150 wpm). Calm confidence; no hype or exclamation marks. A neutral international or US accent is fine; male or female.
**TTS settings (any engine):** stability medium-high, style low, 0% background noise, 48 kHz mono WAV, −16 LUFS per clip. One file per scene so timing can be adjusted.
**Pronunciation:**
- "QuoteGuard" = *quote-guard*; "PayPal" = *pay-pal*.
- "USB-C" = *U-S-B C*; "USB-A" = *U-S-B A*.
- "$570" = *five hundred seventy dollars* (or "five-seventy" where written).

| Scene | Voice-over text (speak exactly) | Max length |
|---|---|---|
| S01 | "Your team needs thirty headsets. The budget is six hundred dollars, and three supplier quotes just arrived as PDFs." | 7.5 s |
| S02 | "The cheapest has the wrong connector. Another hides a hundred and sixty dollars of shipping. And sometimes the document itself has been quietly edited — or the competition is staged." | 10.5 s |
| S03 | "QuoteGuard turns supplier quotes into a verified PayPal purchase." | 5.5 s |
| S04 | "I describe the purchase in plain English. The agent drafts the requirements and stops until I confirm. Then it reads every quote and cites the exact line behind every number." | 16.5 s |
| S05 | "The decision is arithmetic, not a model's opinion. ClearWave, at five hundred seventy dollars, meets every requirement. Click Northstar's shipping, and there's the line on their PDF." | 15.5 s |
| S06 | "An approver signs the exact purchase — supplier, amount, PayPal merchant and expiry — sealed in one hash." | 9.5 s |
| S07 | "Checkout is built on the server from that approved snapshot. The buyer approves in PayPal's own window; we verify the order before capturing, and PayPal's signed webhook confirms it." | 21 s |
| S08 | "Now, the fraud a finance team actually worries about. Someone opens Northstar's six-hundred-forty-dollar quote in a PDF editor and changes it to five-forty. The page looks untouched, the maths adds up, and without forensics it would win and be paid. But PDFs keep their history. QuoteGuard recovers the original revision — six-forty — and blocks it." | 27.5 s |
| S09 | "Or the only quote under budget arrives with two competitors its own salesperson wrote. The provenance graph links all three: same author, same original file, same phone number. The prices even show the cover-bidding shape from bid-rigging research. An AI investigator explains it — using only verified facts." | 21.5 s |
| S10 | "And we measure it: eighty-two labelled cases. Zero false alarms on thirty-eight honest ones, forty of forty-four attacks caught, and every hidden original recovered. The four misses are published too." | 15.5 s |
| S11 | "QuoteGuard. Evidence for every decision, and payments that match what you approved." | 9 s |

Total is about 340 words, roughly 2:30 of speech inside 2:50. Add 0.3–0.6 s of silence where the visual needs to land: the S05 PDF zoom, the S07 receipt, the S08 recovered-original table and the S09 graph.

Extra pronunciation: "Huber and Imhof" = *HOO-ber and IM-hoff* (only in on-screen text; not spoken). "five-forty" / "six-forty" = *five forty* / *six forty* dollars.

---

## 5. Measured facts you may show (do not change)

All figures are stored in the app (Evaluation page) and in `Codes/quoteguard/reports/`.

### 5a. Document integrity benchmark (the headline numbers for S10)

`quoteguard-integrity-v1`, 82 labelled purchase cases, scored by the deterministic analyzer `integrity-v1` (no model in the verdict). Measured 1 November 2026, locally and again on the live server with identical results.

| Measure | Result |
|---|---|
| Honest cases flagged (false alarms) | **0 / 38** (60 honest documents, incl. all 26 holdout layouts and honest suppliers sharing invoicing software) |
| Attacks caught | **40 / 44** (36 blocked, 4 sent to review) |
| Original amounts recovered from hidden PDF revisions | **15 / 15** (12 of them on holdout layouts) |
| Misses, published | 4 — a cleanly re-saved edit (×3) and an invented competitor with fresh, unrelated metadata (×1) |

Say "synthetic" if you show the table; it is a regression benchmark built by the same team, not a field estimate.

### 5b. The two Demo Lab attacks (S08, S09)

- **Edited bill:** Northstar's real quote is $640.00 (shipping $160.00). Edited in a PDF editor to $540.00 (shipping $60.00). Without forensics the same policy rates it *payable, rank 1*; with forensics, **Document integrity: FAIL** and the approval attempt is refused. Original recovered: "Total: $640.00 → $540.00".
- **Staged competition:** Pinecrest Audio $585.00 (only quote under the $600 budget), "competitors" Alder $612.00 and Birch $629.00. Links: Pinecrest↔Alder same author; Alder↔Birch same original document ID; Pinecrest↔Birch same phone number; all created minutes apart with the same tool. Bid screens: coefficient of variation **0.036**, relative distance **2.25** (the cover-bidding shape). Without forensics: *payable, rank 1*; with forensics: blocked.
- The AI investigator memo is written by **Claude Sonnet 5.5 via NanoGPT**; its wording varies between runs, so read it from your recording — never retype it.

### 5c. Extraction: rules vs. AI on unfamiliar layouts (optional, not in the VO)

Holdout set: 26 unfamiliar synthetic quotes, labels frozen **before** testing.

| Run | Rules parser | AI + QuoteGuard checks |
|---|---|---|
| First, unseen runs (Gemini 2.5 Flash, 3 runs) | **11 / 26** | **24 / 26** in each run |
| After fixing two defects the holdout exposed — "seen" (Gemini 2.5 Flash, 3 runs) | 12 / 26 | 26 / 26 in each run |
| Current model — "seen" (Claude Sonnet 5.5 via NanoGPT, 1 run) | 12 / 26 (deterministic, unchanged) | **23 / 26**; 0 / 18 non-payable marked payable; 1 / 8 payable blocked; 368 / 368 citations found. All 3 misses fail safe (a missed subtotal ×2, “fail” instead of “unknown” ×1) |

Only the first row may be called "unseen". If you show any of this, name the model.

Product facts:
- A real sandbox purchase of **$570.00** captured with status COMPLETED; signed PayPal webhooks verified.
- 72 automated backend tests.

---

## 6. Music

**Original, generated; no samples with unclear rights.** One continuous bed of 2:55, mixed under the voice.

**Prompt for the music model:**
> Warm, modern instrumental for a fintech product demo. 100 BPM, key of D major. Soft analog synth pads, gentle plucked synth arpeggio, light electronic drums with brushed hi-hats, subtle bass. Optimistic and trustworthy, not cheesy. Structure: 0:00–0:20 pads and plucks only (calm, slightly curious); 0:20 drums enter softly; 1:33–2:00 gentle build with an added warm lead; 2:00–2:15 brief tension (filtered, sparse); 2:15 resolve to calm; 2:36–2:55 outro, fade to silence. No vocals, no risers louder than the bed, no sudden drops.

**Mix:**
- Music sits at −24 LUFS under the voice (sidechain duck 8–10 dB) and −16 LUFS when no voice.
- Overall master −14 LUFS integrated, −1 dBTP.
- Fade in 0.5 s, fade out 2.5 s.

**Optional SFX** (subtle, −28 LUFS): soft paper rustle (S01), a gentle "click" on the evidence zoom (S05), a soft confirm chime on the receipt (S08), a muted "deny" thud on Blocked (S09).

---

## 7. Motion graphics and overlays

Render all graphics as **HTML/CSS/SVG animated pages recorded with Playwright at 1920×1080**, or with any motion tool. This keeps text crisp and correct. Use the brand palette and fonts from §3. Background `#FBF8F3` (light) or `#0F2541` (dark).

### GFX-1 Cold open (9 s, dark navy background)
- Three white "paper" cards (rounded 18 px, soft shadow) drop in with slight rotation (−6°, 2°, 7°), staggered 0.25 s.
- Each card has two grey lines (fake text) and a price tag that flips in: **$470**, **$570**, **$640**.
- Overlay text, Instrument Serif 64 px, white, fades in at 2 s: "30 headsets · $600 budget · 3 supplier quotes".
- Optional AI b-roll behind the cards (no text, blurred 8 px): *"Top-down view of a tidy desk with a laptop and printed documents, soft morning light, shallow depth of field, calm office, no logos, no text"* (seedance / higgsfield / fal, 5 s, slow push-in).

### GFX-2 The problem (11 s)
- **0–2.5 s:** the $470 card gets an amber stamp "USB-A ≠ USB-C".
- **2.5–5 s:** the $640 card unfolds a strip "+$160 shipping" in red.
- **5–8 s:** on the same $640 card, a white box slides over "$640" and "$540" is typed on top; a faint ghost of "$640" stays visible underneath (it is still in the file).
- **8–11 s:** two pale "competitor" cards slide in behind a third; a thin red thread joins all three.
- Captions in Inter 40 px: "Cheapest ≠ compliant" · "Hidden costs" · "Edited bills" · "Staged competition".

### GFX-3 Title (8 s)
- A shield icon draws in (stroke animation): teal `#14B8A6` shield with a navy check.
- "QuoteGuard" in Instrument Serif 120 px, navy, on off-white.
- Tagline types in, Inter 34 px, navy at 80%: "Evidence for every decision. Payments that match what you approved."

### GFX-4 Integrity counters (overlay in S10, 8 s)
- Three counters count up (ease-out 1.2 s, staggered 0.4 s), Instrument Serif 96 px on a navy band:
  - **0 / 38** — "honest cases flagged"
  - **40 / 44** — "attacks caught"
  - **15 / 15** — "hidden originals recovered"
- Footnote, Inter 24 px: "82 labelled synthetic cases · deterministic forensics · 4 misses published".

### GFX-6 Hidden revision (optional insert in S08, 3 s, before the product zoom)
- A PDF page peels back like a sheet of paper, revealing an identical page underneath where "$640.00" glows teal while the top sheet shows "$540.00" in red. Purely illustrative; label it "Illustration".

### GFX-5 End card (14 s)
- Navy background, QuoteGuard wordmark, then three lines fade in:
  - `quoteguard.koushikdeb.com`
  - `github.com/DevDaring/PayPal_Hackatahon`
  - "PayPal Sandbox · synthetic documents · built for the PayPal AI Hackathon"

### Overlays on product footage
- **Corner labels** (top-left pill): white text on navy at 85%, Inter 26 px, 16 px padding, 12 px radius. Text: "Synthetic supplier documents" / "PayPal Sandbox — no real money" / "Controlled test" / "Sped up 2×".
- **Consent badges** (top-right): amber pill, navy text, e.g. "Consent 2 of 3: approver signs".
- **Callouts:** a 3 px teal rounded rectangle around the UI element plus a label card with a short arrow. Animate in over 0.25 s and hold ≥ 1.5 s. Use **red** for the Harbor/Northstar issues, the counterfactual and the provenance links; **teal** for ClearWave, evidence and the recovered original.
- **Zoom:** in S05 (the highlighted PDF line), S07 (receipt IDs), S08 (the recovered-original table) and S09 (the provenance graph), scale 1.0 → 1.4 over 0.6 s around the element, hold, then return.
- **Captions:** burned-in, Inter 34 px, white with 60% black box, bottom-centre, max 2 lines, max 42 characters per line. Also export a `.srt`.

**Locating elements for callouts:** use the stills in `Video/capture/stills/` (same 1920×1080 frame) to place boxes, then track to the video at the scene's `t_ms`. The UI layout is static within each scene.

---

## 8. Edit and assemble

1. Convert the raw footage to 30 fps CFR: `ffmpeg -i main.webm -r 30 -c:v libx264 -crf 16 -pix_fmt yuv420p main.mp4` (same for the popup video).
2. Cut clips per §3 using `walkthrough-timeline.json`. Speed up the waits with `setpts=PTS/2` (and label them).
3. **PayPal popup:** insert 6–8 s of `popup.mp4` between `12_checkout` and `14_receipt`, either full-frame or as picture-in-picture (60% scale, centred, 12 px radius, drop shadow) over a blurred freeze of the checkout.
4. Lay voice-over clips at the scene starts. Lay the music bed across the whole timeline with sidechain ducking.
5. Add GFX scenes, overlays and captions.
6. Final encode: `-c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -r 30 -c:a aac -b:a 192k -movflags +faststart`, with loudness normalised to −14 LUFS (`loudnorm=I=-14:TP=-1:LRA=11`).
7. Check that the duration is between 165 and 175 s: `ffprobe -show_entries format=duration -of csv=p=0 build/quoteguard_demo.mp4`.

---

## 9. QA checklist (all must be true)

- [ ] Duration 2:45–2:55.
- [ ] Every product claim is shown in real footage from the same recording run (checkout → popup → receipt).
- [ ] "PayPal Sandbox — no real money" is visible during checkout and receipt; "Synthetic supplier documents" and "Controlled test" labels are present; every speed-up is labelled.
- [ ] The capture ID shown is the one from this recording, not typed.
- [ ] The numbers on screen equal §5 exactly; S08 shows $640.00 → $540.00 from the recording itself.
- [ ] S08 and S09 say "Controlled test"; the AI memo text on screen is from the recording, not retyped.
- [ ] No third-party logos in generated graphics; music is original.
- [ ] Captions match the voice-over word for word; nothing is cut off at the frame edges.
- [ ] Watched once at 100% on a laptop: all UI text is readable (zoom where it isn't).
- [ ] Audio: voice clear over music, no clipping, −14 LUFS.

---

## 10. YouTube upload

- **Title:** QuoteGuard — from supplier PDF to an approved PayPal purchase (PayPal AI Hackathon)
- **Visibility:** Public. Check playback while signed out.
- **Thumbnail:** `stills/17_radar_edited_bill.png` with the overlay "It was $640." (Instrument Serif, navy on off-white band); fallback `stills/07_compare.png` with "Evidence for every decision".
- **Chapters:** 0:00 The problem · 0:25 Agent mode · 0:42 Evidence & decision · 0:58 Exact approval · 1:08 PayPal Sandbox checkout · 1:30 Catching an edited bill · 1:58 Exposing staged competition · 2:20 Measured results · 2:36 QuoteGuard
- **Description:**

> QuoteGuard turns supplier quotes into an evidence-backed PayPal purchase. Every extracted term links to the line on the supplier's PDF; the decision is deterministic; Integrity Radar recovers hidden PDF revisions and links "competing" quotes that share an author, file or phone number (with bid-rigging screens from Huber & Imhof, 2019); an approver signs a hash of the exact purchase; checkout is built only from that approved snapshot and verified with PayPal before capture.
>
> Live demo: https://quoteguard.koushikdeb.com (one-click jury sign-in) · Code: https://github.com/DevDaring/PayPal_Hackatahon
>
> Shown: a real PayPal **Sandbox** purchase (no real money) with synthetic supplier documents. Demo Lab scenes are controlled tests. Some waits are sped up and labelled.
>
> Built with PayPal Orders v2 / Payments v2 / JS SDK / webhooks / Agent Toolkit, Claude Sonnet 5.5 via NanoGPT, pdfplumber + pypdf forensics, FastAPI, PostgreSQL, LangGraph, React, AG Grid.
