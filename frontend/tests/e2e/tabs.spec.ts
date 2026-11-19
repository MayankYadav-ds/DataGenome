import { test, expect } from "@playwright/test";
import { demo } from "./helpers";
test("identity changes in another tab clear previously displayed private data", async ({
  page,
  context,
}) => {
  await demo(page);
  await expect(
    page.getByRole("heading", { name: "Synthetic investigation", exact: true }),
  ).toBeVisible();
  const second = await context.newPage();
  await second.goto("/register");
  await second
    .getByLabel("Username", { exact: true })
    .fill("tabs_" + Date.now());
  await second
    .getByLabel("Password", { exact: true })
    .fill("synthetic-password-123");
  await second.getByRole("checkbox").check();
  await second
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    second.getByRole("heading", { name: "Your investigation starts here." }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Your investigation starts here." }),
  ).toBeVisible();
  expect(
    await page.getByText("Synthetic investigation", { exact: true }).count(),
  ).toBe(0);
  await second.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Welcome back." }),
  ).toBeVisible();
});
