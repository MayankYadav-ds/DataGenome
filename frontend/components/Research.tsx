"use client";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { DataTable, Notice, Pending } from "./ui";

export const researchSchema = z.object({
  protocol_sha256: z.string(),
  source_commit: z.string(),
  scope: z.string(),
  suites: z.array(
    z.object({
      suite: z.string(),
      trials: z.number(),
      evaluated: z.number(),
      failed: z.number(),
      seconds: z.number(),
    }),
  ),
  observations: z.array(
    z.object({ topic: z.string(), finding: z.string(), artifact: z.string() }),
  ),
  limitations: z.array(z.string()),
});
export function ResearchEvidence({
  report,
}: {
  report: z.infer<typeof researchSchema>;
}) {
  return (
    <section aria-labelledby="executed-research">
      <h2 id="executed-research">Executed research evidence</h2>
      <p>{report.scope}</p>
      <p>
        Frozen protocol: <code>{report.protocol_sha256}</code>
      </p>
      <p>
        Execution source commit: <code>{report.source_commit}</code>
      </p>
      <DataTable
        rows={report.suites}
        caption="Prespecified suite execution, including unsuccessful cases"
      />
      {report.observations.map((row) => (
        <section key={row.topic}>
          <h3>{row.topic}</h3>
          <p>{row.finding}</p>
          <a
            href={`https://github.com/MayankYadav-ds/DataGenome/blob/main/benchmarks/results/phase9/${encodeURIComponent(row.artifact)}/results.json`}
          >
            Inspect recorded experiments
          </a>
        </section>
      ))}
      <Notice>
        These are research observations, not customer outcomes or a guarantee of
        improved performance.
      </Notice>
      <ul>
        {report.limitations.map((text) => (
          <li key={text}>{text}</li>
        ))}
      </ul>
      <p>
        <a href="https://github.com/MayankYadav-ds/DataGenome/blob/main/research/technical-report.md">
          Technical report, methods and reproduction
        </a>
      </p>
    </section>
  );
}
export default function Research() {
  const query = useQuery({
    queryKey: ["public-research-evidence"],
    queryFn: async ({ signal }) => {
      const response = await fetch("/research-results.json", { signal });
      if (!response.ok)
        throw new Error("Published research evidence is unavailable.");
      return researchSchema.parse(await response.json());
    },
  });
  if (query.isPending)
    return <Pending text="Loading recorded research evidence" />;
  if (query.isError)
    return (
      <Notice error>
        Published research evidence is unavailable. Repository reports remain
        accessible below.
      </Notice>
    );
  return <ResearchEvidence report={query.data} />;
}
