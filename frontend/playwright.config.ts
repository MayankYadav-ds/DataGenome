import { defineConfig } from "@playwright/test";
const browser = process.env.DATAGENOME_E2E_BROWSER ?? "chromium";
const frontendPort = process.env.DATAGENOME_E2E_FRONTEND_PORT ?? "3000";
const backendPort = process.env.DATAGENOME_E2E_BACKEND_PORT ?? "8765";
if (!["chromium", "firefox", "webkit"].includes(browser))
  throw new Error("Unsupported browser configuration.");
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 90000,
  expect: { timeout: 15000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    browserName: browser as "chromium" | "firefox" | "webkit",
    baseURL:
      process.env.DATAGENOME_E2E_URL ?? `http://127.0.0.1:${frontendPort}`,
    ignoreHTTPSErrors: process.env.DATAGENOME_E2E_LOCAL_TLS === "1",
    headless: true,
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
  },
  webServer: process.env.DATAGENOME_E2E_URL
    ? undefined
    : [
        {
          command: `python -m uvicorn datagenome.api:app --host 127.0.0.1 --port ${backendPort} --no-access-log`,
          env: {
            DATAGENOME_STORE:
              process.env.DATAGENOME_E2E_STORE ??
              `../.datagenome/browser-${browser}.sqlite3`,
          },
          url: `http://127.0.0.1:${backendPort}/health`,
          reuseExistingServer: !process.env.CI,
          timeout: 60000,
        },
        {
          command: `npm start -- --port ${frontendPort}`,
          env: {
            NEXT_TELEMETRY_DISABLED: "1",
            DATAGENOME_BACKEND: `http://127.0.0.1:${backendPort}`,
          },
          url: `http://127.0.0.1:${frontendPort}`,
          reuseExistingServer: !process.env.CI,
          timeout: 90000,
        },
      ],
});
