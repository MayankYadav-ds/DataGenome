import { expect, test } from "@playwright/test";
test("nonce CSP blocks untrusted inline script and rejects forged hosts", async ({
  page,
}) => {
  const response = await page.goto("/");
  const policy = response?.headers()["content-security-policy"] ?? "";
  expect(policy).toContain("'nonce-");
  expect(policy).not.toContain("'unsafe-eval'");
  expect(policy).toContain("frame-ancestors 'none'");
  // A parser-created script models injected markup. A DevTools-created script
  // runs in a debugger-authorized context and is not an untrusted HTML fixture.
  await page.evaluate(() => {
    const frame = document.createElement("iframe");
    frame.srcdoc =
      "<script>parent.document.documentElement.dataset.injected='executed'</script>";
    document.body.append(frame);
  });
  await expect(page.locator("iframe")).toHaveCount(1);
  await expect.poll(() => page.frames().length).toBe(2);
  expect(await page.locator("html").getAttribute("data-injected")).toBeNull();
  try {
    const forged = await page.request.get("/api/v1/capabilities", {
      headers: { Host: "attacker.invalid" },
    });
    expect(forged.status()).toBe(403);
  } catch (error) {
    // Playwright also uses the overridden Host for TLS SNI. The local Caddy
    // listener refuses that name before an HTTP request can reach Next.js.
    expect(new URL(page.url()).protocol).toBe("https:");
    expect(String(error)).toMatch(/EPROTO.*SSL|SSL.*alert|TLS.*alert/s);
  }
  const crossOrigin = await page.request.post("/api/v1/projects", {
    headers: { Origin: "https://attacker.invalid" },
    data: { name: "Untrusted origin" },
  });
  expect(crossOrigin.status()).toBe(403);
});
