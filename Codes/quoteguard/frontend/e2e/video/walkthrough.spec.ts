import { expect, test, type Locator, type Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

/**
 * Scripted product walkthrough for the demo video. Each scene() call records a timestamp
 * (ms from the start of the main video) into walkthrough-timeline.json so voice-over and edits can be synced.
 * Runs against the live site; uses a fresh isolated demo workspace and a REAL PayPal Sandbox purchase.
 */
const OUT = process.env.OUT_DIR ?? "video-out";
const EMAIL = process.env.SANDBOX_BUYER_EMAIL!, PASSWORD = process.env.SANDBOX_BUYER_PASSWORD!;
const marks: { scene: string; t_ms: number; note?: string }[] = [];
let t0 = 0;

const CURSOR = `
  (() => { if (window.__qgCursor) return; window.__qgCursor = true;
    const d = document.createElement('div');
    d.style.cssText = 'position:fixed;z-index:2147483647;pointer-events:none;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;background:rgba(20,184,166,.35);border:2px solid #0f766e;box-shadow:0 0 0 6px rgba(20,184,166,.15);transition:transform .12s ease;left:-50px;top:-50px';
    document.addEventListener('mousemove', e => { d.style.left = e.clientX + 'px'; d.style.top = e.clientY + 'px'; }, true);
    document.addEventListener('mousedown', () => { d.style.transform = 'scale(.7)'; }, true);
    document.addEventListener('mouseup', () => { d.style.transform = 'scale(1)'; }, true);
    const add = () => document.body ? document.body.appendChild(d) : setTimeout(add, 50); add(); })();`;

async function prep(page: Page) {
  await page.addInitScript(CURSOR);
}
function scene(name: string, note?: string) {
  marks.push({ scene: name, t_ms: Date.now() - t0, note });
}
async function glide(page: Page, target: Locator) {
  await target.scrollIntoViewIfNeeded();
  const box = await target.boundingBox();
  if (box) await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 28 });
  await page.waitForTimeout(250);
}
async function click(page: Page, target: Locator) {
  await glide(page, target);
  await target.click();
}
async function still(page: Page, name: string) {
  await page.screenshot({ path: `${OUT}/stills/${name}.png` });
}
const pause = (page: Page, ms: number) => page.waitForTimeout(ms);

test("QuoteGuard demo walkthrough (real PayPal Sandbox)", async ({ page, context }) => {
  test.skip(!EMAIL || !PASSWORD, "set SANDBOX_BUYER_EMAIL / SANDBOX_BUYER_PASSWORD");
  mkdirSync(`${OUT}/stills`, { recursive: true });
  await prep(page);
  context.on("page", (p) => prep(p));
  t0 = Date.now();

  scene("01_login", "Sign-in page with jury access card");
  await page.goto("/login");
  await pause(page, 1800);
  await still(page, "01_login");
  await click(page, page.getByRole("button", { name: "Fill to Sign in" }));
  await expect(page.getByRole("heading", { name: /Good to see you/ })).toBeVisible();

  scene("02_overview", "Overview hero and safeguards");
  await pause(page, 2200);
  await still(page, "02_overview");
  await click(page, page.getByRole("link", { name: "Watch the agent work" }));

  scene("03_agent_start", "Agent Mode start: plain-English request");
  await pause(page, 1800);
  await still(page, "03_agent_start");
  await click(page, page.getByRole("button", { name: /Use the sample purchase/ }));

  scene("04_agent_confirm", "Agent drafted requirements; consent 1 of 3");
  const confirm = page.getByRole("button", { name: "Confirm requirements & continue" });
  await expect(confirm).toBeVisible({ timeout: 60_000 });
  await pause(page, 1500);
  await still(page, "04_agent_confirm");
  await click(page, confirm);

  scene("05_agent_working", "Gather → read & cite → verify → decide (live)");
  await expect(page.getByRole("button", { name: "Review & approve the exact purchase" })).toBeVisible({ timeout: 180_000 });
  scene("06_agent_decided", "Recommendation reached; consent 2 of 3 waiting");
  await pause(page, 2200);
  await still(page, "06_agent_decided");

  await click(page, page.getByRole("link", { name: /Open step by step/ }));
  await click(page, page.getByRole("button", { name: /Compare/ }).first());
  scene("07_compare", "Recommendation + why the cheapest loses + evidence grid");
  await expect(page.getByText("Why the cheapest quote loses")).toBeVisible({ timeout: 60_000 });
  await pause(page, 2500);
  await still(page, "07_compare");

  scene("08_evidence", "Click Northstar $160 shipping → PDF line highlighted");
  await click(page, page.locator(".ag-row").filter({ hasText: "Northstar" }).getByText("$160.00"));
  await expect(page.getByText("Exact location on page")).toBeVisible();
  await pause(page, 3000);
  await still(page, "08_evidence");
  await page.keyboard.press("Escape");

  scene("09_impact", "What QuoteGuard caught");
  await glide(page, page.getByText("What QuoteGuard caught"));
  await pause(page, 2500);
  await still(page, "09_impact");

  scene("10_whatif", "What-if: $650 then $560");
  await click(page, page.getByRole("button", { name: /\$650/ }));
  await pause(page, 2600);
  await still(page, "10_whatif_650");
  await click(page, page.getByRole("button", { name: /\$560/ }));
  await expect(page.getByText("No quote is fully compliant under these settings")).toBeVisible();
  await pause(page, 2600);
  await still(page, "10_whatif_560");
  await click(page, page.getByRole("button", { name: "Reset" }));

  scene("11_approve", "Exact purchase terms + hash; approver persona signs");
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await click(page, page.getByRole("button", { name: "Review for approval" }));
  await click(page, page.getByRole("button", { name: /Switch to Avery Chen/ }));
  await pause(page, 1500);
  await still(page, "11_approve");
  await click(page, page.getByRole("button", { name: "Approve exact purchase" }));
  await expect(page.getByText(/Organisation approval active/)).toBeVisible();
  await pause(page, 2000);
  await still(page, "11_approved");

  scene("12_checkout", "Real PayPal Sandbox checkout; consent 3 of 3");
  await click(page, page.getByRole("button", { name: "Continue to PayPal checkout" }));
  const frame = page.frameLocator("iframe[title*='PayPal']").first();
  await expect(frame.locator("[data-funding-source='paypal']").first()).toBeVisible({ timeout: 60_000 });
  await pause(page, 2000);
  await still(page, "12_checkout");
  const popupP = page.waitForEvent("popup");
  await frame.locator("[data-funding-source='paypal']").first().click();
  const pp = await popupP;
  scene("13_paypal_popup", "PayPal's own window (recorded as a separate video file)");
  await pp.waitForLoadState("domcontentloaded");
  await pp.locator("#email").fill(EMAIL, { timeout: 60_000 });
  if (await pp.locator("#btnNext").isVisible().catch(() => false)) await pp.locator("#btnNext").click();
  await pp.locator("#password").fill(PASSWORD, { timeout: 60_000 });
  await pp.screenshot({ path: `${OUT}/stills/13_paypal_login.png` });
  await pp.locator("#btnLogin").click();
  const pay = pp.locator("#payment-submit-btn, button[data-id='payment-submit-btn'], button:has-text('Complete Purchase'), button:has-text('Pay Now')").first();
  await pay.waitFor({ state: "visible", timeout: 90_000 });
  await pp.waitForTimeout(1500);
  await pp.screenshot({ path: `${OUT}/stills/13_paypal_review.png` });
  await pay.click({ timeout: 90_000 });
  await pp.waitForEvent("close", { timeout: 90_000 }).catch(() => {});

  scene("14_receipt", "Capture confirmed by PayPal Sandbox; receipt with IDs");
  await expect(page.getByText(/Verified by PayPal Sandbox/)).toBeVisible({ timeout: 90_000 });
  await pause(page, 3000);
  await still(page, "14_receipt");
  scene("15_replay", "Decision replay + provider calls");
  await glide(page, page.getByText("Decision replay"));
  await pause(page, 3000);
  await still(page, "15_replay");

  scene("16_demolab_integrity", "Demo Lab: an edited bill and staged competition, run through the real services");
  await click(page, page.getByRole("link", { name: "Demo Lab", exact: true }));
  await expect(page.getByRole("heading", { name: "Try to break the payment path" })).toBeVisible();
  const card = (t: string) => page.locator("div.rounded-2xl", { has: page.getByRole("heading", { name: t }) }).first();
  const EDITED = "Supplier PDF edited to fit the budget", COVER = "Fabricated competing quotes";
  await click(page, card(EDITED).getByRole("button", { name: "Run" }));
  await card(COVER).getByRole("button", { name: "Run" }).click();  // second attack runs in parallel; shown later
  await expect(card(EDITED).getByText("Blocked as expected")).toBeVisible({ timeout: 240_000 });
  await glide(page, card(EDITED).getByText("Counterfactual: the same policy without document forensics"));
  await pause(page, 3000);
  await still(page, "16_demolab_integrity");

  scene("17_radar_edited_bill", "Integrity Radar: original $640 recovered from the PDF's hidden revision");
  const editedHref = await card(EDITED).getByRole("link", { name: "Open lab request" }).getAttribute("href");
  await page.goto(`${editedHref}/compare`);
  const radar = page.locator("[data-integrity]");
  await expect(radar).toBeVisible({ timeout: 120_000 });
  await expect(radar.getByText(/AI investigator memo/)).toBeVisible({ timeout: 90_000 }).catch(() => {});
  await glide(page, radar.locator("[data-finding='revision_edit']"));
  await pause(page, 4500);
  await still(page, "17_radar_edited_bill");

  scene("18_radar_cover_quotes", "Integrity Radar: provenance graph links the 'competitors' (author, file, phone) + bid screens");
  await page.goto("/demo-lab");
  await expect(card(COVER).getByText("Blocked as expected")).toBeVisible({ timeout: 240_000 });
  const coverHref = await card(COVER).getByRole("link", { name: "Open lab request" }).getAttribute("href");
  await page.goto(`${coverHref}/compare`);
  await expect(radar).toBeVisible({ timeout: 120_000 });
  await expect(radar.getByText(/AI investigator memo/)).toBeVisible({ timeout: 90_000 }).catch(() => {});
  await glide(page, radar.getByText("Provenance graph"));
  await pause(page, 4000);
  await still(page, "18_radar_cover_quotes");
  await glide(page, radar.getByText("Bid screens"));
  await pause(page, 2500);

  scene("19_evaluation", "Evaluation: integrity benchmark, then extraction rules vs AI");
  await click(page, page.getByRole("link", { name: "Evaluation", exact: true }));
  await expect(page.getByTestId("integrity-bench")).toBeVisible({ timeout: 30_000 });
  await pause(page, 3500);
  await still(page, "19_evaluation");
  await glide(page, page.getByText("Rules vs AI on these documents"));
  await pause(page, 2500);

  scene("20_end", "End");
  await pause(page, 1000);
  writeFileSync(`${OUT}/walkthrough-timeline.json`, JSON.stringify({ base_url: page.url(), viewport: "1920x1080", scenes: marks,
    note: "t_ms is milliseconds from the start of the MAIN page video. The PayPal popup is a separate .webm in raw/." }, null, 2));
});
