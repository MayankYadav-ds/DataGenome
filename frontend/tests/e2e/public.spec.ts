import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { shot } from "./helpers";
test("public routes, keyboard access, responsive themes and accessibility", async ({
  page,
}) => {
  for (const route of [
    "/",
    "/features",
    "/how-it-works",
    "/research",
    "/documentation",
    "/about",
    "/privacy",
    "/terms",
    "/login",
    "/register",
  ]) {
    await page.goto(route);
    await expect(page.locator("h1")).toHaveCount(1);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
  }
  for (const width of [360, 390, 768, 1024, 1440, 1920]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /Your model is only/ }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    if ([390, 1440].includes(width)) await shot(page, "landing-dark-" + width);
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("button", { name: "Toggle color theme" }).click();
  await shot(page, "landing-light");
  for (const route of ["/", "/login", "/register"]) {
    await page.goto(route);
    const audit = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(audit.violations).toEqual([]);
    if (route !== "/") await shot(page, route.slice(1));
  }
  await page.goto("/login");
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to content" }),
  ).toBeFocused();
});
