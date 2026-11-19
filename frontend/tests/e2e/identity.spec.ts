import { test, expect } from "@playwright/test";
import { demo } from "./helpers";
test("registration, login failures, logout, ownership isolation and revocation", async ({
  page,
  browser,
}) => {
  const username = "browser_" + Date.now();
  await page.goto("/register");
  await page.getByLabel("Username", { exact: true }).fill(username);
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic-password-123");
  await page.getByRole("checkbox").check();
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your investigation starts here." }),
  ).toBeVisible();
  await page.getByLabel("New project name").fill("<em>untrusted-project</em>");
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "<em>untrusted-project</em>",
      exact: true,
    }),
  ).toBeVisible();
  const project = new URL(page.url()).pathname.split("/")[3];
  expect(await page.locator("main em").count()).toBe(0);
  const other = await browser.newContext();
  const otherPage = await other.newPage();
  await demo(otherPage);
  expect(
    (
      await otherPage.request.get(`/api/v1/projects/${project}/inventory`)
    ).status(),
  ).toBe(404);
  await otherPage.goto(`/app/projects/${project}`);
  await expect(otherPage.locator(".notice[role=alert]")).toContainText(
    "absent",
  );
  expect(
    await otherPage
      .getByText("<em>untrusted-project</em>", { exact: true })
      .count(),
  ).toBe(0);
  await other.close();
  expect(
    (
      await page.request.post("/api/v1/projects", {
        data: { name: "missing csrf" },
      })
    ).status(),
  ).toBe(403);
  expect(
    (
      await page.request.post("/api/v1/auth/guest", {
        headers: { Origin: "https://attacker.invalid" },
      })
    ).status(),
  ).toBe(403);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.goto("/login");
  await page.getByLabel("Username", { exact: true }).fill(username);
  await page.getByLabel("Password", { exact: true }).fill("wrong-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.locator(".notice[role=alert]")).toContainText(
    "Invalid username or password",
  );
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByText("<em>untrusted-project</em>", { exact: true }),
  ).toBeVisible();
  const csrf = (await (await page.request.get("/api/v1/auth/csrf")).json())
    .csrf_token;
  await page.request.post("/api/v1/auth/logout", {
    headers: { "X-CSRF-Token": csrf },
  });
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Welcome back." }),
  ).toBeVisible();
});
