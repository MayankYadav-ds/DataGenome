import { chromium } from "@playwright/test";
import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";
const root = fileURLToPath(new URL("../../", import.meta.url));
function files(path) {
  return readdirSync(path, { withFileTypes: true }).flatMap((item) =>
    item.isDirectory() ? files(join(path, item.name)) : [join(path, item.name)],
  );
}
const chunks = files(join(root, "frontend/.next/static")).filter((path) =>
  path.endsWith(".js"),
);
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
});
const page = await context.newPage();
const cdp = await context.newCDPSession(page);
await cdp.send("Performance.enable");
await page.goto("http://127.0.0.1:3000", { waitUntil: "networkidle" });
const navigation = await page.evaluate(() => {
  const n = performance.getEntriesByType("navigation")[0];
  return {
    responseStart_ms: n.responseStart,
    responseEnd_ms: n.responseEnd,
    domContentLoaded_ms: n.domContentLoadedEventEnd,
    loadEvent_ms: n.loadEventEnd,
  };
});
const resources = await page.evaluate(() =>
  performance
    .getEntriesByType("resource")
    .filter(
      (r) => r.name.includes("/_next/") && r.name.split("?")[0].endsWith(".js"),
    )
    .map((r) => ({
      name: new URL(r.name).pathname,
      transfer_bytes: r.transferSize,
      encoded_body_bytes: r.encodedBodySize,
      decoded_body_bytes: r.decodedBodySize,
    })),
);
const metrics = Object.fromEntries(
  (await cdp.send("Performance.getMetrics")).metrics.map((m) => [
    m.name,
    m.value,
  ]),
);
const latencies = [];
for (let i = 0; i < 5; i++) {
  const at = performance.now();
  const response = await context.request.get(
    "http://127.0.0.1:3000/api/v1/capabilities",
  );
  latencies.push({
    status: response.status(),
    milliseconds: performance.now() - at,
  });
}
const report = {
  measured_at_utc: new Date().toISOString(),
  method:
    "Single local production-build Chromium run, fresh browser context, 1440x1000. Navigation includes local HTTP and hydration. Script bytes include any immediate prefetch. Five same-origin capability requests include the Next-to-FastAPI bridge. Memory is a CDP snapshot, not peak process memory. No Lighthouse or Core Web Vitals score, isolated chart timing, or production scalability claim.",
  navigation,
  initial_script_resources: resources,
  initial_script_transfer_bytes: resources.reduce(
    (a, r) => a + r.transfer_bytes,
    0,
  ),
  all_production_javascript: {
    files: chunks.length,
    raw_bytes: chunks.reduce((a, p) => a + readFileSync(p).length, 0),
    gzip_bytes: chunks.reduce(
      (a, p) => a + gzipSync(readFileSync(p)).length,
      0,
    ),
  },
  renderer: {
    javascript_heap_used_bytes: metrics.JSHeapUsedSize,
    layout_seconds: metrics.LayoutDuration,
    recalculate_style_seconds: metrics.RecalcStyleDuration,
  },
  api_requests: latencies,
};
writeFileSync(
  join(root, "docs/web-performance.json"),
  JSON.stringify(report, null, 2) + "\n",
);
await browser.close();
console.log(
  JSON.stringify({
    navigation,
    initial_script_transfer_bytes: report.initial_script_transfer_bytes,
    all_production_javascript: report.all_production_javascript,
    renderer: report.renderer,
    api_requests: latencies,
  }),
);
