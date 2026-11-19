import { test, expect } from "@playwright/test";
import { demo, open, completed, shot } from "./helpers";
test("real guest diagnostics, investigator, correction, experiments, versions and exports", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const { project, version } = await demo(page);
  await shot(page, "project-dashboard");
  await open(page, project, version, "analyses");
  await page
    .getByRole("button", { name: "Run diagnostics", exact: true })
    .click();
  const baseline = await completed(page);
  await page.getByLabel("Reveal owner-only detailed evidence").check();
  await expect(
    page
      .locator(".engine-result > summary")
      .filter({ hasText: "Profile" })
      .first(),
  ).toBeVisible();
  await shot(page, "dataset-health");
  for (const view of ["leakage", "labels", "recommendations"]) {
    await open(page, project, version, view, baseline.result_id);
    await page.getByLabel("Reveal owner-only detailed evidence").check();
    await expect(page.locator(".health-grid")).toBeVisible();
    await shot(page, view);
    if (view === "recommendations") {
      await expect(page.locator(".recommendation").first()).toBeVisible();
      const count = await page.locator(".recommendation").count();
      expect(count).toBeGreaterThanOrEqual(2);
      await page
        .getByRole("button", { name: "Dismiss from current view", exact: true })
        .first()
        .click();
      await expect(page.locator(".recommendation")).toHaveCount(count - 1);
      await page
        .getByRole("button", { name: "Dismiss from current view", exact: true })
        .first()
        .click();
      await expect(page.locator(".recommendation")).toHaveCount(count - 2);
    }
  }
  await open(page, project, version, "valuation");
  await page
    .getByRole("button", { name: "Run data valuation", exact: true })
    .click();
  await completed(page);
  await page.getByLabel("Reveal owner-only detailed evidence").check();
  await expect(
    page.getByText("unsupported_knn_features", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Valuation algorithm").selectOption("loo");
  await page
    .getByRole("button", { name: "Run data valuation", exact: true })
    .click();
  await completed(page);
  await expect(page.locator(".chart")).toBeVisible();
  await shot(page, "valuation");
  await open(page, project, version, "investigation");
  await page
    .getByRole("button", { name: "Review validation identifiers" })
    .click();
  await expect(page.getByLabel("Validation prediction")).not.toHaveValue("");
  await page
    .getByRole("button", {
      name: "Run model failure investigator",
      exact: true,
    })
    .click();
  await completed(page);
  await page.getByLabel("Reveal owner-only detailed evidence").check();
  await expect(
    page.getByRole("heading", { name: "Evidence relationships" }),
  ).toBeVisible();
  await shot(page, "failure-investigator");
  await open(page, project, version, "fairness");
  await page
    .getByLabel("Explicit sensitive attributes (comma separated)")
    .fill("review_code");
  await page
    .getByRole("button", { name: "Run fairness intelligence", exact: true })
    .click();
  await completed(page);
  await page.getByLabel("Reveal owner-only detailed evidence").check();
  await shot(page, "fairness");
  await open(page, project, version, "experiments");
  await page.getByLabel("Remove features (comma separated)").fill("constant");
  const cfg = await (
    await page.request.get(
      `/api/v1/datasets/${version}/configuration?project_id=${project}&reviewed=true`,
    )
  ).json();
  const id = cfg.partitions.train[0];
  const csv = await (
    await page.request.get(
      `/api/v1/datasets/${version}/export?project_id=${project}&reviewed=true`,
    )
  ).text();
  const current = csv.trim().split(/\r?\n/)[id].split(",").at(-1);
  await page
    .getByLabel("Correct stable record ID", { exact: true })
    .fill(String(id));
  await page
    .getByLabel("Explicit replacement label")
    .fill(current === "1" ? "0" : "1");
  await page
    .getByRole("button", { name: "Preview intervention", exact: true })
    .click();
  await expect(page.getByText("Dry Run", { exact: true })).toBeVisible();
  await page
    .getByLabel("I reviewed this exact plan and authorize bounded retraining.")
    .check();
  await page.getByRole("button", { name: /Run controlled experiment/ }).click();
  const experiment = await completed(page);
  await page.getByRole("button", { name: "Refresh outcomes" }).click();
  await expect(
    page
      .getByRole("figure")
      .filter({ hasText: "Validation balanced accuracy" }),
  ).toBeVisible();
  await shot(page, "experiments");
  const output = await (
    await page.request.get(
      `/api/v1/experiments/${experiment.experiment_id}?project_id=${project}`,
    )
  ).json();
  expect(output.held_out_evaluated).toBe(false);
  expect(output.arms[0].corrected_labels).toBe(1);
  await open(page, project, version, "versions");
  await expect(page.locator(".lineage-node")).toHaveCount(2);
  await shot(page, "versions");
  await open(page, project, version, "reports");
  const downloading = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export report", exact: true })
    .click();
  expect((await downloading).suggestedFilename()).toBe(
    "datagenome-report.json",
  );
  await shot(page, "reports");
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
  expect(errors).toEqual([]);
  await page.getByRole("button", { name: "Toggle color theme" }).click();
  await shot(page, "workspace-light");
  await page.getByRole("button", { name: "Toggle color theme" }).click();
  for (const width of [360, 390, 768, 1024, 1440, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    if (width === 390) await shot(page, "workspace-mobile");
  }
  await page
    .getByRole("link", { name: "Settings & privacy", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Settings & privacy", exact: true }),
  ).toBeVisible();
  await shot(page, "settings-privacy");
  await page
    .getByRole("button", { name: "Delete guest data", exact: true })
    .click();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  expect((await page.request.get(`/api/v1/projects/${project}`)).status()).toBe(
    200,
  );
  await page
    .getByRole("button", { name: "Delete guest data", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Confirm deletion", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: /Your model is only/ }),
  ).toBeVisible();
  expect((await page.request.get("/api/v1/auth/session")).status()).toBe(401);
});
