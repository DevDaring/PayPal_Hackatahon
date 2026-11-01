import { expect, test } from "@playwright/test";

const SHOTS = process.env.SHOTS_DIR;
const shot = async (page: any, name: string) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true }); };

test("agent mode runs to the approval checkpoint; compare shows impact and what-if column", async ({ page }) => {
  test.setTimeout(240_000);
  await page.goto("/login");
  await page.getByRole("button", { name: "Fill to Sign in" }).click();
  await page.getByRole("link", { name: "Watch the agent work" }).click();
  await page.getByRole("button", { name: "Run the agent" }).click();
  await page.getByRole("button", { name: "Confirm requirements & continue" }).click();
  await expect(page.getByRole("button", { name: "Review & approve the exact purchase" })).toBeVisible({ timeout: 150_000 });
  await page.waitForTimeout(800);
  await shot(page, "30-agent-mode");
  await page.getByRole("link", { name: /Open this request step by step/ }).click();
  await page.getByRole("button", { name: /Compare/ }).first().click();
  await expect(page.getByText("What QuoteGuard caught")).toBeVisible();
  await page.getByRole("button", { name: "$650" }).click();
  await expect(page.locator(".ag-header-cell-text", { hasText: "What-if" })).toBeVisible();
  await page.waitForTimeout(1500);
  await shot(page, "31-compare-impact-whatif");
});
