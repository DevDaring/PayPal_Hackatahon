import { expect, test } from "@playwright/test";

const SHOTS = process.env.SHOTS_DIR;
const shot = async (page: any, name: string) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true }); };

test("agent mode: sample run resumes after refresh and reaches the approval consent; compare shows preview vs confirmed", async ({ page }) => {
  test.setTimeout(300_000);
  await page.goto("/login");
  await page.getByRole("button", { name: "Fill to Sign in" }).click();
  await page.getByRole("link", { name: "Watch the agent work" }).click();
  await page.getByRole("button", { name: /Use the sample purchase/ }).click();
  await expect(page).toHaveURL(/\/agent\/[0-9a-f-]{36}/);
  await page.getByRole("button", { name: "Confirm requirements & continue" }).click();
  await expect(page.locator('[data-stage="read"][data-state="active"], [data-stage="read"][data-state="done"]')).toBeVisible({ timeout: 60_000 });
  await page.reload(); // refresh mid-run: progress is rebuilt from stored state
  await expect(page.locator('[data-stage="confirm"][data-state="done"]')).toBeVisible();
  await expect(page.getByRole("button", { name: "Review & approve the exact purchase" })).toBeVisible({ timeout: 180_000 });
  await shot(page, "30-agent-mode");
  await page.getByRole("link", { name: /Open step by step/ }).click();
  await page.getByRole("button", { name: /Compare/ }).first().click();
  await expect(page.getByText("Evidence grid")).toBeVisible();
  await expect(page.getByText("What QuoteGuard caught")).toBeVisible();
  await page.getByRole("button", { name: /\$650/ }).click();
  await expect(page.getByText(/Confirmed purchase:/)).toBeVisible();
  await expect(page.getByText(/Preview:.*not used for payment/)).toBeVisible();
  await expect(page.locator(".ag-header-cell-text", { hasText: "What-if" })).toBeVisible();
  await page.waitForTimeout(1200);
  await shot(page, "31-compare-impact-whatif");
});

test("agent mode accepts the user's own request and asks for their documents", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Fill to Sign in" }).click();
  await expect(page.getByRole("heading", { name: /Good to see you/ })).toBeVisible();
  await page.goto("/agent");
  await page.getByLabel("What should the agent buy?").fill("Order 12 USB-C headsets with microphones for new hires, budget USD 300 including shipping, within 10 days.");
  await page.getByRole("button", { name: "Run the agent" }).click();
  await page.getByRole("button", { name: "Confirm requirements & continue" }).click({ timeout: 60_000 });
  await expect(page.getByRole("button", { name: "Upload supplier PDFs" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: "Use 3 sample quotes" })).toBeVisible();
});
