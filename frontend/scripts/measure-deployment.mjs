import { chromium } from "@playwright/test";
import { writeFileSync } from "node:fs";

const output = process.argv[2];
if (!output) throw new Error("Provide a new output JSON path.");
const browser = await chromium.launch();
try {
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  await cdp.send("Performance.enable");
  await page.goto("https://localhost:8443", { waitUntil: "networkidle" });
  const navigation = await page.evaluate(() => {
    const entry = performance.getEntriesByType("navigation")[0];
    return {
      response_start_ms: entry.responseStart,
      response_end_ms: entry.responseEnd,
      dom_content_loaded_ms: entry.domContentLoadedEventEnd,
      load_event_ms: entry.loadEventEnd,
    };
  });
  const metrics = Object.fromEntries(
    (await cdp.send("Performance.getMetrics")).metrics.map((m) => [
      m.name,
      m.value,
    ]),
  );
  const report = {
    measured_at_utc: new Date().toISOString(),
    method:
      "One fresh Chromium context against the synthetic local HTTPS Compose stack. Local CA verification disabled for this probe only. Navigation includes TLS, SSR, assets and hydration. CDP heap is a snapshot, not peak process memory. No Core Web Vitals or enterprise-scale claim.",
    navigation,
    renderer_heap_used_bytes: metrics.JSHeapUsedSize,
    renderer_layout_seconds: metrics.LayoutDuration,
  };
  writeFileSync(output, JSON.stringify(report, null, 2) + "\n", { flag: "wx" });
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
}
