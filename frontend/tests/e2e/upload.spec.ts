import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { demo, open, shot } from "./helpers";
test("CSV validation, registration, previews, drift, deletion and workspace accessibility", async ({
  page,
}) => {
  const { project, version } = await demo(page);
  await open(page, project, version, "datasets");
  await shot(page, "dataset-upload");
  await page.getByLabel("Choose CSV file", { exact: true }).setInputFiles({
    name: "bad.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("x,label\n1,0"),
  });
  await expect(page.locator(".notice[role=alert]")).toContainText("Only CSV");
  const csv =
    "x,z,constant,label\n" +
    Array.from({ length: 60 }, (_, i) => `${i},${i % 3},1,${i % 2}`).join("\n");
  await page.getByLabel("Choose CSV file", { exact: true }).setInputFiles({
    name: "synthetic.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv),
  });
  await expect(
    page.getByRole("heading", { name: "Inspect the schema" }),
  ).toBeVisible();
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
    page.getByText("60 rows · 4 columns · target label", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("I understand record previews may contain sensitive data.")
    .check();
  await page
    .getByRole("button", { name: "Load bounded record preview" })
    .click();
  await expect(
    page.getByRole("table").filter({ hasText: "Owner-only first 20 records" }),
  ).toBeVisible();
  const rawDownload = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export reviewed CSV text", exact: true })
    .click();
  expect((await rawDownload).suggestedFilename()).toBe(
    "datagenome-dataset.csv.txt",
  );
  await open(page, project, version, "drift");
  await page.getByLabel("Reference CSV", { exact: true }).setInputFiles({
    name: "reference.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv),
  });
  await page.getByLabel("Comparison CSV", { exact: true }).setInputFiles({
    name: "comparison.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv.replace("0,0,1,0", "100,0,1,0")),
  });
  await page
    .getByRole("button", { name: "Compute distribution comparison" })
    .click();
  await expect(
    page.getByText("Multivariate", { exact: true }).first(),
  ).toBeVisible();
  await shot(page, "drift");
  await open(page, project, version, "overview");
  const audit = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(audit.violations).toEqual([]);
  await page
    .getByRole("button", { name: "Delete project", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Cancel", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page
    .getByRole("button", { name: "Delete project", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Confirm deletion", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your investigation starts here." }),
  ).toBeVisible();
  expect((await page.request.get(`/api/v1/projects/${project}`)).status()).toBe(
    404,
  );
});
