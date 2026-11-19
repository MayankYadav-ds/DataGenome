import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 90000,
  expect: { timeout: 15000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:3000",
    headless: true,
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command:
        "python -m uvicorn datagenome.api:app --host 127.0.0.1 --port 8765 --no-access-log",
      env: { DATAGENOME_STORE: "../.datagenome/browser.sqlite3" },
      url: "http://127.0.0.1:8765/health",
      reuseExistingServer: !process.env.CI,
      timeout: 60000,
    },
    {
      command: "npm start -- --port 3000",
      env: { NEXT_TELEMETRY_DISABLED: "1" },
      url: "http://127.0.0.1:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 90000,
    },
  ],
});
