import { expect, test } from "@playwright/test";

const SHOTS = process.env.SHOTS_DIR;
const shot = async (page: any, name: string) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true }); };

test("Demo Lab scenarios produce verdicts from real services; other screens render", async ({ page }) => {
  test.setTimeout(420_000);
  await page.goto("/login");
  await page.getByRole("button", { name: "Fill to Sign in" }).click();
  await expect(page.getByRole("heading", { name: /Good to see you/ })).toBeVisible();

  await page.getByRole("link", { name: "Demo Lab" }).first().click();
  await expect(page.getByRole("heading", { name: "Try to break the payment path" })).toBeVisible();
  const runs = page.getByRole("button", { name: "Run" });
  for (let i = 0; i < 5; i++) {
    await runs.nth(i).click();
    await expect(page.getByText("Running").first()).toBeVisible();
    await expect(page.getByText("Running")).toHaveCount(0, { timeout: 120_000 });
  }
  await expect(page.getByText("Blocked as expected")).toHaveCount(3);
  await expect(page.getByText("One logical operation")).toBeVisible();
  await expect(page.getByText("Recovered safely")).toBeVisible();
  await shot(page, "11-demo-lab");

  await page.getByRole("link", { name: "Evaluation" }).first().click();
  await expect(page.getByText("Decision agreement")).toBeVisible();
  await shot(page, "12-evaluation");
  await page.getByRole("link", { name: "Settings" }).first().click();
  await expect(page.getByText("PayPal Sandbox credentials")).toBeVisible();
  await shot(page, "13-settings");
  await page.getByRole("link", { name: "Payments" }).first().click();
  await expect(page.getByText("Payment operations")).toBeVisible();
  await shot(page, "14-payments");
  await page.getByRole("link", { name: "Evidence" }).first().click();
  await expect(page.getByText("Every document, every extracted term")).toBeVisible();
  await page.waitForTimeout(1500);
  await shot(page, "15-evidence-desk");
});

test("mobile layout keeps navigation usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  await page.getByRole("button", { name: "Fill to Sign in" }).click();
  await expect(page.getByRole("button", { name: "Open navigation" })).toBeVisible();
  await shot(page, "16-mobile-overview");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("link", { name: "Demo Lab", exact: true })).toBeVisible();
});
