import { expect, test } from "@playwright/test";

test("Integrity Radar: an edited supplier PDF is caught, the original amount is recovered and approval is refused", async ({ page }) => {
  test.setTimeout(420_000);
  await page.goto("/login");
  await page.getByRole("button", { name: "Fill to Sign in" }).click();
  await expect(page).not.toHaveURL(/login/);
  await page.goto("/demo-lab");
  const card = page.locator("div.rounded-2xl", { has: page.getByRole("heading", { name: "Supplier PDF edited to fit the budget" }) }).first();
  await card.getByRole("button", { name: "Run" }).click();
  await expect(card.getByText("Blocked as expected")).toBeVisible({ timeout: 300_000 });
  await expect(card.getByText(/Counterfactual: the same policy without document forensics/)).toBeVisible();
  await expect(card.getByText(/payment eligible True, rank 1/)).toBeVisible();
  const href = await card.getByRole("link", { name: "Open lab request" }).getAttribute("href");
  await page.goto(`${href}/compare`);
  const radar = page.locator("[data-integrity]");
  await expect(radar).toHaveAttribute("data-integrity", "block", { timeout: 120_000 });
  const finding = radar.locator("[data-finding='revision_edit']");
  await expect(finding.getByText("Total: $640.00")).toBeVisible();
  await expect(finding.getByText("Total: $540.00")).toBeVisible();
});
