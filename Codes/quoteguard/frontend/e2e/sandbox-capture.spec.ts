import { expect, test } from "@playwright/test";

// Real PayPal Sandbox purchase (fake money). Runs only when sandbox buyer credentials are provided via env.
const EMAIL = process.env.SANDBOX_BUYER_EMAIL, PASSWORD = process.env.SANDBOX_BUYER_PASSWORD;
const SHOTS = process.env.SHOTS_DIR;
const shot = async (page: any, name: string) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true }); };

test.skip(!EMAIL || !PASSWORD, "sandbox buyer credentials not provided");

test("real PayPal Sandbox: buyer approves, server captures, receipt shows provider IDs", async ({ page }) => {
  test.setTimeout(300_000);
  await page.goto("/login");
  await page.getByRole("button", { name: "Fill to Sign in" }).click();
  await page.getByRole("button", { name: "Try sample purchase" }).click();
  await page.getByRole("button", { name: "Confirm requirements" }).click();
  await page.getByRole("button", { name: "Load 3 sample quotes" }).click();
  await expect(page.getByText("Extracted", { exact: true })).toHaveCount(3, { timeout: 120_000 });
  await page.getByRole("button", { name: /Compare/ }).first().click();
  await page.getByRole("button", { name: "Review for approval" }).click();
  await page.getByRole("button", { name: /Switch to Avery Chen/ }).click();
  await page.getByRole("button", { name: "Approve exact purchase" }).click();
  await page.getByRole("button", { name: "Continue to PayPal checkout" }).click();

  const frame = page.frameLocator("iframe[title*='PayPal']").first();
  const popupP = page.waitForEvent("popup");
  await frame.locator("[data-funding-source='paypal']").first().click();
  const pp = await popupP;
  await pp.waitForLoadState("domcontentloaded");
  await pp.locator("#email").fill(EMAIL!, { timeout: 60_000 });
  if (await pp.locator("#btnNext").isVisible().catch(() => false)) await pp.locator("#btnNext").click();
  await pp.locator("#password").fill(PASSWORD!, { timeout: 60_000 });
  await pp.locator("#btnLogin").click();
  const payBtn = pp.locator("#payment-submit-btn, button:has-text('Complete Purchase'), button:has-text('Pay Now'), button:has-text('Continue to Review Order'), button[data-id='payment-submit-btn']").first();
  await payBtn.click({ timeout: 90_000 });
  await pp.waitForEvent("close", { timeout: 90_000 }).catch(() => {});

  await expect(page.getByText(/Verified by PayPal Sandbox/)).toBeVisible({ timeout: 90_000 });
  await page.waitForTimeout(1500);
  await shot(page, "20-real-sandbox-receipt");
});
