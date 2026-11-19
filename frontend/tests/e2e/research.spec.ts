import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { shot } from "./helpers";

test("published research preserves adverse outcomes and artifact links", async ({
  page,
}) => {
  await page.goto("/research");
  await expect(
    page.getByRole("heading", { name: "Executed research evidence" }),
  ).toBeVisible();
  await expect(
    page.getByText(/0 improved, 14 were unchanged and 4 degraded/),
  ).toBeVisible();
  await expect(
    page.getByText(
      /620a55c420ebf04101832b5110a9f61393d3bdb17afbe9784c3705fd1d2a6018/,
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Inspect recorded experiments" }),
  ).toHaveCount(8);
  for (const width of [360, 390, 768, 1024, 1440, 1920]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  const audit = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(audit.violations).toEqual([]);
  await shot(page, "research-phase9");
});
