import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { ResearchEvidence, researchSchema } from "../components/Research";

it("renders negative and failed research evidence with source attribution", () => {
  const report = researchSchema.parse({
    protocol_sha256: "test-protocol",
    source_commit: "fixture",
    scope: "Synthetic test fixture",
    suites: [
      {
        suite: "interventions",
        trials: 2,
        evaluated: 1,
        failed: 1,
        seconds: 1,
      },
    ],
    observations: [
      {
        topic: "Interventions",
        finding: "One arm degraded by -0.1; one case failed.",
        artifact: "interventions",
      },
    ],
    limitations: ["Exploratory fixture; not a published benchmark."],
  });
  render(<ResearchEvidence report={report} />);
  expect(
    screen.getByText("One arm degraded by -0.1; one case failed."),
  ).toBeVisible();
  expect(screen.getByText("test-protocol")).toBeVisible();
  expect(
    screen.getByRole("link", { name: "Inspect recorded experiments" }),
  ).toHaveAttribute(
    "href",
    expect.stringContaining("interventions/results.json"),
  );
  expect(
    screen.getByText("Exploratory fixture; not a published benchmark."),
  ).toBeVisible();
});
