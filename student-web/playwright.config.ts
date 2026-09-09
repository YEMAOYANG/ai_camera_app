import { defineConfig, devices } from "@playwright/test";

const systemChrome = process.env.MIRA_E2E_USE_SYSTEM_CHROME === "1"
  ? { browserName: "chromium" as const, channel: "chrome" }
  : {};

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: "html",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "on-first-retry",
  },
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: !process.env.CI,
    env: {
      OPENMAIC_FULL_RUNTIME_PUBLIC_URL: "http://127.0.0.1:3101",
    },
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"], ...systemChrome } },
    { name: "tablet", use: { ...devices["iPad Pro 11"], ...systemChrome } },
  ],
});
