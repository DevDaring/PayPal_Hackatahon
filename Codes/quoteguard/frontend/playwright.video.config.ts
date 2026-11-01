import { defineConfig } from "@playwright/test";

// Records the product walkthrough used by the demo video (see /Video_Script.md).
// OUT_DIR receives: per-page .webm videos, stills (PNG) and walkthrough-timeline.json.
const OUT = process.env.OUT_DIR ?? "video-out";
export default defineConfig({
  testDir: "./e2e/video",
  timeout: 600_000,
  workers: 1,
  reporter: [["list"]],
  outputDir: `${OUT}/raw`,
  use: {
    baseURL: process.env.BASE_URL ?? "https://quoteguard.koushikdeb.com",
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    video: { mode: "on", size: { width: 1920, height: 1080 } },
    colorScheme: "light",
    launchOptions: { slowMo: Number(process.env.SLOWMO ?? 60), ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}) },
  },
});
