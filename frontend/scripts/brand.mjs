// Render the original, trusted vector branding to a social-platform-compatible PNG.
import { chromium } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1200, height: 630 } });
await page.setContent(
  '<html><body style="margin:0">' +
    readFileSync(new URL("../public/social.svg", import.meta.url), "utf8") +
    "</body></html>",
);
await page.screenshot({
  path: fileURLToPath(new URL("../public/social.png", import.meta.url)),
});
await browser.close();
