import { expect, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
export async function shot(page: Page, name: string) {
  const folder = resolve(
    process.env.DATAGENOME_SCREENSHOTS ?? "test-results/screenshots",
  );
  mkdirSync(folder, { recursive: true });
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement)
      document.activeElement.blur();
    window.scrollTo(0, 0);
  });
  await page.screenshot({
    path: resolve(folder, name + ".png"),
    fullPage: true,
  });
}
export async function demo(page: Page) {
  await page.goto("/demo");
  await page.getByRole("button", { name: /Launch interactive demo/ }).click();
  await expect(
    page.getByRole("heading", { name: "Synthetic investigation", exact: true }),
  ).toBeVisible();
  const url = new URL(page.url());
  return {
    project: url.pathname.split("/")[3],
    version: url.searchParams.get("version")!,
  };
}
export async function open(
  page: Page,
  project: string,
  version: string,
  view: string,
  analysis?: string,
) {
  const root = `/app/projects/${project}`;
  if (new URL(page.url()).pathname.startsWith(root)) {
    await expect(page.getByLabel("Active dataset version")).toBeVisible();
    if (
      (await page.getByLabel("Active dataset version").inputValue()) !== version
    ) {
      await page.getByLabel("Active dataset version").selectOption(version);
    }
    const destination = view === "overview" ? root : `${root}/${view}`;
    await page.locator(`.sidebar a[href^="${destination}?"]`).first().click();
    if (analysis) await page.getByLabel("Evidence run").selectOption(analysis);
  } else {
    await page.goto(
      `${root}/${view}?version=${version}${analysis ? "&analysis=" + analysis : ""}`,
    );
  }
  await expect(page.getByLabel("Active dataset version")).toBeVisible();
}
export async function completed(page: Page) {
  await expect(page.locator(".job-panel .pill").first()).toHaveText(
    "completed",
    { timeout: 60000 },
  );
  const url = new URL(page.url());
  const project = url.pathname.split("/")[3],
    job = url.searchParams.get("job");
  const response = await page.request.get(
    `/api/v1/jobs/${job}?project_id=${project}`,
  );
  expect(response.ok()).toBeTruthy();
  return response.json();
}
