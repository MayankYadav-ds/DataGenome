import { test, expect } from "@playwright/test";
import { demo, open } from "./helpers";
test("a real queued analysis can be cancelled and reopened after refresh", async ({
  page,
}) => {
  const { project, version } = await demo(page);
  await open(page, project, version, "datasets");
  const csv =
    "x,z,label\n" +
    Array.from({ length: 200 }, (_, i) => `${i},${i % 7},${i % 2}`).join("\n");
  await page.getByLabel("Choose CSV file", { exact: true }).setInputFiles({
    name: "cancellation.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv),
  });
  await page
    .getByRole("button", { name: "Configure analysis", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Review registration", exact: true })
    .click();
  await page
    .getByLabel(
      "I am authorized to process this dataset and reviewed the split configuration.",
    )
    .check();
  await page
    .getByRole("button", { name: "Register dataset", exact: true })
    .click();
  await expect(
    page.getByText("200 rows · 3 columns · target label", { exact: true }),
  ).toBeVisible();
  const active = new URL(page.url()).searchParams.get("version")!;
  await open(page, project, active, "valuation");
  await page.getByLabel("Valuation algorithm").selectOption("loo");
  await page
    .getByRole("button", { name: "Run data valuation", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Request cancellation", exact: true })
    .click();
  await expect(page.locator(".job-panel .pill")).toHaveText("cancelled", {
    timeout: 60000,
  });
  await page.reload();
  await expect(page.locator(".job-panel .pill")).toHaveText("cancelled");
  const url = new URL(page.url());
  const result = await (
    await page.request.get(
      `/api/v1/jobs/${url.searchParams.get("job")}?project_id=${project}`,
    )
  ).json();
  expect(result.cancel_requested).toBe(true);
  expect(result.result_id).toBeNull();
});
