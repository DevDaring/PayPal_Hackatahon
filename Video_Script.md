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
4. **No third-party trademarks or copyrighted material** in your own animations: no PayPal, Gemini, Google or AG Grid logos in generated graphics, and no stock music with unclear rights. PayPal's buttons and window may appear only as they genuinely appear in the product recording.
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

Scene ids written by the recorder: `01_login`, `02_overview`, `03_agent_start`, `04_agent_confirm`, `05_agent_working`, `06_agent_decided`, `07_compare`, `08_evidence`, `09_impact`, `10_whatif`, `11_approve`, `12_checkout`, `13_paypal_popup`, `14_receipt`, `15_replay`, `16_demolab`, `17_evaluation`, `18_end`.

**Clip extraction rule:** a clip for scene X runs from `t_ms[X]` to `t_ms[next scene]` in the main video. Trim dead time freely.

**Speed-ups:**
- The agent's extraction wait (`05_agent_working` → `06_agent_decided`) and the Demo Lab wait (inside `16_demolab`) may be accelerated.
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
| S01 | 0:00–0:09 | **GFX-1 Cold open**: three paper quote cards fall onto a desk; "$470", "$570", "$640" tags flip in | "30 headsets · $600 budget · 3 supplier quotes" | Soft intro, pads only |
| S02 | 0:09–0:20 | **GFX-2 The problem**: $470 card gets an amber "USB-A ≠ USB-C" stamp; $640 card unfolds a "+$160 shipping" strip; a chat bubble "looks good 👍" turns into a payment that doesn't match | "Cheapest ≠ compliant" · "Hidden costs" · "Approval ≠ payment" | Plucks enter |
| S03 | 0:20–0:28 | **GFX-3 Title**: QuoteGuard shield; tagline types in | "QuoteGuard" / "Evidence for every decision. Payments that match what you approved." | Beat enters |
| S04 | 0:28–0:50 | Product: `03_agent_start` → `04_agent_confirm` → `05_agent_working` (sped up) → `06_agent_decided` | Top-left: "Synthetic supplier documents" · "Consent 1 of 3: you confirm" · "Sped up 2×" during extraction | Steady |
| S05 | 0:50–1:10 | Product: `07_compare` → `08_evidence` (zoom 140% on the highlighted PDF line, 1.5 s hold) → brief `09_impact` | Callouts: "Harbor $470 — wrong connector" · "Northstar +$160 shipping" · "ClearWave $570 meets every requirement" · on zoom: "Every number links to its line on the PDF" | Steady |
| S06 | 1:10–1:20 | Product: `10_whatif` ($650, then $560) | "Preview only — never used for payment" | Steady |
| S07 | 1:20–1:33 | Product: `11_approve` → approved state | "Consent 2 of 3: approver signs the exact purchase" · callout on the hash/expiry: "Supplier · amount · PayPal merchant · expiry → one hash" | Slight lift |
| S08 | 1:33–2:00 | Product: `12_checkout` → **PayPal popup video** (cut in, 6–8 s, picture-in-picture or full) → `14_receipt` (hold 3 s on IDs) | "PayPal Sandbox — no real money" (persistent) · "Consent 3 of 3: buyer approves in PayPal" · on receipt: "Captured & verified by PayPal Sandbox" · callout on webhooks | Build, peak at receipt |
| S09 | 2:00–2:15 | Product: `16_demolab` (sped up wait) → hold on "Blocked as expected" and the red diff line | "Controlled test" · callout on diff: "amount changed after approval → blocked" | Tension → resolve |
| S10 | 2:15–2:36 | Product: `17_evaluation`, plus **GFX-4 bar chart** overlay with the numbers in §5 | "26 unfamiliar quotes · labels frozen before testing" | Calm |
| S11 | 2:36–2:50 | **GFX-5 End card** | "QuoteGuard" · "quoteguard.koushikdeb.com" · "github.com/DevDaring/PayPal_Hackatahon" · "PayPal Sandbox · synthetic documents · built for the PayPal AI Hackathon" | Resolve, fade out by 2:50 |

`15_replay` (decision replay) is optional B-roll: use 2–3 s inside S08 or S10 if time allows.

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
| S01 | "Your team needs thirty headsets. The budget is six hundred dollars, and three supplier quotes just arrived as PDFs." | 8.5 s |
| S02 | "The cheapest one has the wrong connector. Another hides a hundred and sixty dollars of shipping. And the payment that finally goes out often isn't what anyone approved." | 10.5 s |
| S03 | "QuoteGuard turns supplier quotes into an evidence-backed PayPal purchase." | 7.5 s |
| S04 | "I describe the purchase in plain English. Gemini drafts the requirements — and the agent stops, because nothing counts until I confirm. Then it gathers the quotes, reads every term, and cites the exact line it came from." | 21 s |
| S05 | "The decision is arithmetic, not a model's opinion. ClearWave, at five hundred seventy dollars, meets every requirement. Harbor looks cheapest but is U-S-B A. Click Northstar's shipping, and there's the line on their PDF." | 19.5 s |
| S06 | "What-ifs are only previews. At six-fifty, Northstar qualifies but still isn't best. At five-sixty, nothing does — so nothing is recommended." | 9.5 s |
| S07 | "An approver signs the exact purchase: supplier, amount, PayPal merchant and expiry, sealed in a single hash." | 12.5 s |
| S08 | "Checkout is built on the server from that approved snapshot, so the browser can't change the amount or the payee. The buyer approves in PayPal's own window. We verify the order, capture it, and PayPal's signed webhook confirms it." | 26 s |
| S09 | "Now let's try to break it. Change the amount after approval — even directly in the database — and execution is blocked until someone approves again." | 14.5 s |
| S10 | "And we measure it. On twenty-six unfamiliar quotes, a rules parser made eleven correct decisions. Gemini with our checks made twenty-four, in three out of three runs. The test also caught one real mistake; we fixed it, and now test for it." | 20.5 s |
| S11 | "QuoteGuard: evidence for every decision, and payments that match what you approved. Built for small teams that buy with PayPal." | 13 s |

Total is about 330 words, roughly 2:30 of speech inside 2:50, leaving natural breathing room. Add 0.3–0.6 s of silence between sentences where the visual needs to land (the S05 PDF zoom and the S08 receipt).

---

## 5. Measured facts you may show (do not change)

All figures were measured on 1 November 2026 and stored in the app (Evaluation page) and in `Codes/quoteguard/reports/`.

The table below compares the two extractors on the **holdout set**: 26 unfamiliar synthetic quotes (prose letters, tables, two-page terms, revised offers, negated specs), with labels frozen **before** testing. These are the **first, unseen runs**.

| Measure | Rules parser | Gemini 2.5 Flash + QuoteGuard checks (3 runs) |
|---|---|---|
| Decisions matching labels | **11 / 26** | **24 / 26** in each of 3 runs |
| Payable quotes wrongly blocked | 8 / 8 | 1 / 8 |
| Non-payable quotes marked payable | 0 / 18 | 1 / 18 in each run — a real defect, fixed and regression-tested afterwards |
| Cited lines found on the cited page | 147 / 147 | 380 / 380 in two runs (377 / 377 in the first) |

After fixing the two general defects this holdout exposed (clause splitting inside "3.5 mm"; plural words), reruns scored AI **26 / 26** in each of 3 runs, with 0 / 18 non-payable marked payable and 0 / 8 payable blocked; the rules parser scored 12 / 26. These reruns are labelled **"seen"**. If you show them, say "after the fix", never "unseen".

Product facts:
- A real sandbox purchase of **$570.00** captured with status COMPLETED.
- Signed PayPal webhooks verified.
- Over 60 automated backend tests.

Bar chart for GFX-4 (two bars only): "Correct decisions on 26 unfamiliar quotes", Rules **11**, AI + checks **24**. Footnote: "Synthetic holdout · labels frozen before testing · 3 AI runs, same result".

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
- **0–3 s:** the $470 card gets an amber stamp "USB-A ≠ USB-C".
- **3–6 s:** the $640 card unfolds a strip "+$160 shipping" in red.
- **6–11 s:** a chat bubble "looks good 👍" morphs into a payment slip whose amount flickers between $570 and $590, then a red outline appears.
- Captions in Inter 40 px: "Cheapest ≠ compliant" · "Hidden costs" · "Approval ≠ payment".

### GFX-3 Title (8 s)
- A shield icon draws in (stroke animation): teal `#14B8A6` shield with a navy check.
- "QuoteGuard" in Instrument Serif 120 px, navy, on off-white.
- Tagline types in, Inter 34 px, navy at 80%: "Evidence for every decision. Payments that match what you approved."

### GFX-4 Results bar chart (overlay in S10, 7 s)
- Two horizontal bars that grow left to right (ease-out 1.2 s): Rules **11** (grey `#94A3B8`), AI + checks **24** (teal), on a 0–26 scale.
- Labels and footnote exactly as in §5.

### GFX-5 End card (14 s)
- Navy background, QuoteGuard wordmark, then three lines fade in:
  - `quoteguard.koushikdeb.com`
  - `github.com/DevDaring/PayPal_Hackatahon`
  - "PayPal Sandbox · synthetic documents · built for the PayPal AI Hackathon"

### Overlays on product footage
- **Corner labels** (top-left pill): white text on navy at 85%, Inter 26 px, 16 px padding, 12 px radius. Text: "Synthetic supplier documents" / "PayPal Sandbox — no real money" / "Controlled test" / "Sped up 2×".
- **Consent badges** (top-right): amber pill, navy text, e.g. "Consent 2 of 3: approver signs".
- **Callouts:** a 3 px teal rounded rectangle around the UI element plus a label card with a short arrow. Animate in over 0.25 s and hold ≥ 1.5 s. Use **red** for the Demo Lab diff and the Harbor/Northstar issues, **teal** for ClearWave and evidence.
- **Zoom:** in S05 (the highlighted PDF line) and S08 (receipt IDs), scale 1.0 → 1.4 over 0.6 s around the element, hold, then return.
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
- [ ] The numbers on screen equal §5 exactly.
- [ ] No third-party logos in generated graphics; music is original.
- [ ] Captions match the voice-over word for word; nothing is cut off at the frame edges.
- [ ] Watched once at 100% on a laptop: all UI text is readable (zoom where it isn't).
- [ ] Audio: voice clear over music, no clipping, −14 LUFS.

---

## 10. YouTube upload

- **Title:** QuoteGuard — from supplier PDF to an approved PayPal purchase (PayPal AI Hackathon)
- **Visibility:** Public. Check playback while signed out.
- **Thumbnail:** `stills/07_compare.png` with the overlay "Evidence for every decision" (Instrument Serif, navy on off-white band).
- **Chapters:** 0:00 The problem · 0:28 Agent mode · 0:50 Evidence & decision · 1:20 Exact approval · 1:33 PayPal Sandbox checkout · 2:00 Controlled test · 2:15 Measured results · 2:36 QuoteGuard
- **Description:**

> QuoteGuard turns supplier quotes into an evidence-backed PayPal purchase. Every extracted term links to the line on the supplier's PDF; the decision is deterministic; an approver signs a hash of the exact purchase; checkout is built only from that approved snapshot and verified with PayPal before capture.
>
> Live demo: https://quoteguard.koushikdeb.com (one-click jury sign-in) · Code: https://github.com/DevDaring/PayPal_Hackatahon
>
> Shown: a real PayPal **Sandbox** purchase (no real money) with synthetic supplier documents. Demo Lab scenes are controlled tests. Some waits are sped up and labelled.
>
> Built with PayPal Orders v2 / Payments v2 / JS SDK / webhooks / Agent Toolkit, Gemini 2.5 Flash, FastAPI, PostgreSQL, LangGraph, React, AG Grid.
