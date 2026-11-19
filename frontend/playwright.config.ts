import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  reporter: "list",
  use: {
    baseURL: "http://localhost:5173",
    browserName: "chromium",
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    headless: true,
    permissions: ["microphone", "clipboard-read", "clipboard-write"],
    launchOptions: {
      args: [
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
      ],
    },
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --host localhost --strictPort",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
  },
});
