import { expect, test } from "@playwright/test";

test("focus reconciliation cannot invalidate an in-flight guest sign-in", async ({
  page,
}) => {
  await page.goto("/demo");
  let focusedDuringSignIn = false;
  await page.route("**/api/v1/auth/guest", async (route) => {
    const response = await route.fetch();
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    focusedDuringSignIn = true;
    await route.fulfill({ response });
  });
  await page.getByRole("button", { name: /Launch interactive demo/ }).click();
  await expect(
    page.getByRole("heading", { name: "Synthetic investigation", exact: true }),
  ).toBeVisible();
  expect(focusedDuringSignIn).toBe(true);
});
