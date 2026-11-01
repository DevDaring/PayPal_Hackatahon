import { expect, test } from "@playwright/test";

// Critical journey: jury sign-in → sample request → confirm → extract → compare → approve → PayPal order.
// Buyer approval inside PayPal needs a sandbox buyer login and is covered by the manual checklist.
const SHOTS = process.env.SHOTS_DIR;
const shot = async (page: any, name: string) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true }); };

test("sample purchase reaches a PayPal sandbox order bound to the approved snapshot", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByText("Jury access")).toBeVisible();
  await shot(page, "01-login");
  await page.getByRole("button", { name: "Fill to Sign in" }).click();
  await expect(page.getByRole("heading", { name: /Good to see you/ })).toBeVisible();
  await shot(page, "02-overview");

  await page.getByRole("button", { name: "Try sample purchase" }).click();
  await expect(page.getByRole("button", { name: "Confirm requirements" })).toBeVisible();
  await shot(page, "03-requirements");
  await page.getByRole("button", { name: "Confirm requirements" }).click();

  await page.getByRole("button", { name: "Load 3 sample quotes" }).click();
  await expect(page.getByText("Extracted", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Extracted", { exact: true })).toHaveCount(3, { timeout: 120_000 });
  await page.waitForTimeout(1500);
  await shot(page, "04-evidence");

  await page.getByRole("button", { name: /Compare/ }).first().click();
  await expect(page.getByText("Meets every confirmed requirement")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByRole("heading", { name: "ClearWave Supplies" })).toBeVisible();
  await expect(page.getByText("Why the cheapest quote loses")).toBeVisible();
  await page.waitForTimeout(2500);
  await shot(page, "05-compare");

  // Evidence drawer from a grid cell
  await page.locator(".ag-row").filter({ hasText: "Northstar" }).getByText("$160.00").click();
  await expect(page.getByText("Exact location on page")).toBeVisible();
  await page.waitForTimeout(1200);
  await shot(page, "06-evidence-drawer");
  await page.keyboard.press("Escape");

  // What-if: $650 keeps ClearWave best; $560 leaves no compliant quote
  await page.getByRole("button", { name: "$560" }).click();
  await expect(page.getByText("No quote is fully compliant under these settings")).toBeVisible();
  await shot(page, "07-whatif");
  await page.getByRole("button", { name: "Reset" }).click();

  await page.getByRole("button", { name: "Review for approval" }).click();
  await expect(page.getByText("You are acting as the requester")).toBeVisible();
  await page.getByRole("button", { name: /Switch to Avery Chen/ }).click();
  await expect(page.getByRole("button", { name: "Approve exact purchase" })).toBeEnabled();
  await shot(page, "08-approve");
  await page.getByRole("button", { name: "Approve exact purchase" }).click();
  await expect(page.getByText(/Organisation approval active/)).toBeVisible();
  await shot(page, "09-approved");

  await page.getByRole("button", { name: "Continue to PayPal checkout" }).click();
  await expect(page.getByText("PayPal SANDBOX")).toBeVisible();
  const frame = page.frameLocator("iframe[title*='PayPal']").first();
  await expect(frame.locator("[data-funding-source='paypal']").first()).toBeVisible({ timeout: 60_000 });
  await page.waitForTimeout(1500);
  await shot(page, "10-checkout");
});
