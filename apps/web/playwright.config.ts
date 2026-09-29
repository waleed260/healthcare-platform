import { defineConfig, devices } from "@playwright/test";

const port = process.env.PLAYWRIGHT_PORT ?? "3000";
const chromiumLaunchOptions = process.env.PW_NO_SANDBOX === "1" || process.env.PW_CHROMIUM_EXECUTABLE_PATH ? {
  ...(process.env.PW_NO_SANDBOX === "1" ? { args: ["--no-sandbox"] } : {}),
  ...(process.env.PW_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PW_CHROMIUM_EXECUTABLE_PATH } : {}),
} : undefined;
const webServer = process.env.PLAYWRIGHT_EXTERNAL_SERVER ? undefined : {
  command: `npm run build && npm run start -- -H 127.0.0.1 -p ${port}`,
  url: `http://127.0.0.1:${port}`,
  reuseExistingServer: !process.env.CI,
  timeout: 120_000,
};

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer,
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"], launchOptions: chromiumLaunchOptions } },
    { name: "mobile", use: { ...devices["Pixel 5"] } },
  ],
});
