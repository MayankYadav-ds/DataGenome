"use client";
import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { ArrowRight, Network } from "lucide-react";
import { request, json, type Version } from "../lib/api";
import {
  Action,
  Heading,
  Empty,
  Notice,
  Pending,
  Pill,
  Evidence,
  Bars,
  asObject,
  value,
  DataTable,
  label,
  measurement,
} from "./ui";
import type { Config } from "./Workspace";
const reportSchema = z
  .object({
    schema_version: z.string(),
    health: z
      .object({ score: z.number().nullable(), coverage: z.number() })
      .passthrough(),
    engines: z.record(
      z.string(),
      z
        .object({
          status: z.string(),
          result: z.unknown().optional(),
          code: z.string().optional(),
        })
        .passthrough(),
    ),
    recommendations: z.array(z.record(z.string(), z.unknown())).optional(),
    limitations: z.array(z.string()).optional(),
  })
  .passthrough();
const titles: Record<string, [string, string, string]> = {
  analyses: [
    "Diagnostic evidence",
    "Collect independent lines of evidence. Failed or unavailable methods remain explicit.",
    "profile",
  ],
  leakage: [
    "Leakage investigation",
    "Distinguish confirmed configured violations, exact target agreement and heuristic signals.",
    "leakage",
  ],
  labels: [
    "Label intelligence",
    "Out-of-fold disagreement is a review signal, not a calibrated label-error probability.",
    "labels",
  ],
  valuation: [
    "Data valuation",
    "Model-, utility- and evaluation-dependent values. Negative does not mean mislabeled.",
    "valuation",
  ],
  investigation: [
    "Model failure investigator",
    "Trace one validation prediction through measured contributions and related training evidence.",
    "investigation",
  ],
  fairness: [
    "Fairness intelligence",
    "Explicit sensitive attributes, suppressed small cells and competing fairness definitions.",
    "fairness",
  ],
  drift: [
    "Distribution drift",
    "Distribution change is not automatic evidence of concept drift.",
    "drift",
  ],
  recommendations: [
    "Recommendation review",
    "Evidence supports investigation. Every intervention needs explicit review.",
    "profile",
  ],
};
export default function Diagnostics({
  project,
  version,
  config,
  view,
  analysis,
  analyses,
  selectAnalysis,
  submit,
}: {
  project: string;
  version: Version | undefined;
  config: Config | undefined;
  view: string;
  analysis: string | undefined;
  analyses: { id: string; created_at: string }[];
  selectAnalysis: (id: string) => void;
  submit: (
    engines: string[],
    options?: Record<string, unknown>,
  ) => Promise<unknown>;
  refresh: () => Promise<unknown>;
}) {
  const [detailed, setDetailed] = useState(false);
  const [method, setMethod] = useState("knn-shapley");
  const [attributes, setAttributes] = useState("");
  const [record, setRecord] = useState("");
  const [validation, setValidation] = useState<number[]>([]);
  const [dismissed, setDismissed] = useState<Record<string, number[]>>({});
  const [title, description, engine] = titles[view] ?? titles.analyses;
  const report = useQuery({
    queryKey: [project, analysis, detailed, "report"],
    enabled: !!analysis,
    queryFn: async () =>
      reportSchema.parse(
        await request(
          `/analyses/${analysis}?project_id=${project}&privacy=${detailed ? "detailed" : "summary"}`,
        ),
      ),
  });
  const outcome = report.data?.engines[engine];
  const result = asObject(outcome?.result);
  const data =
    result[
      view === "labels"
        ? "label_audit"
        : view === "valuation"
          ? "valuation"
          : view === "investigation"
            ? "investigation"
            : view === "fairness"
              ? "fairness"
              : view === "leakage"
                ? "leakage"
                : "profile"
    ] ?? outcome?.result;
  const payload = asObject(data);
  return (
    <>
      <Heading
        eyebrow="EVIDENCE WORKSPACE / LOCAL ANALYSIS"
        title={title}
        description={description}
        action={
          version && view !== "drift" && view !== "recommendations" ? (
            <Action
              kind="primary"
              disabled={view === "investigation" && !record}
              onClick={() =>
                submit(
                  view === "analyses"
                    ? [
                        "profile",
                        "intelligence",
                        "leakage",
                        "labels",
                        "anomalies",
                      ]
                    : [engine],
                  {
                    valuation_method: method,
                    attributes: attributes
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                    ...(record ? { record_id: Number(record) } : {}),
                  },
                )
              }
            >
              Run {view === "analyses" ? "diagnostics" : title.toLowerCase()}{" "}
              <ArrowRight size={16} />
            </Action>
          ) : undefined
        }
      />
      {!version ? (
        <Empty title="Choose a dataset to investigate">
          <Link href={"/app/projects/" + project + "/datasets"}>
            Upload a dataset
          </Link>
        </Empty>
      ) : (
        <>
          {view === "valuation" ? (
            <section className="panel compact">
              <label>
                Valuation algorithm
                <select
                  value={method}
                  onChange={(e) => setMethod(e.target.value)}
                >
                  {[
                    [
                      "knn-shapley",
                      "Numeric KNN Shapley · up to 1,000 train rows",
                    ],
                    ["loo", "Leave-one-out · up to 128"],
                    ["shapley", "Exact Data Shapley · up to 8"],
                    ["mc-shapley", "Monte Carlo Shapley · up to 64"],
                    ["banzhaf", "Exact Data Banzhaf · up to 8"],
                  ].map(([v, t]) => (
                    <option key={v} value={v}>
                      {t}
                    </option>
                  ))}
                </select>
              </label>
              <Notice>
                Defaults: accuracy utility, fixed logistic model except numeric
                KNN, bounded evaluations and a 30-second cooperative budget.
                Ineligible requests return their reason instead of fabricated
                values.
              </Notice>
            </section>
          ) : null}
          {view === "fairness" ? (
            <section className="panel">
              <label>
                Explicit sensitive attributes (comma separated)
                <input
                  value={attributes}
                  onChange={(e) => setAttributes(e.target.value)}
                  placeholder="Column names; never inferred"
                />
              </label>
              <Notice>
                Binary classification only. Small groups are suppressed;
                undefined metrics stay unavailable. No universal fairness score,
                predictive proxy verification or subgroup confidence intervals.
              </Notice>
            </section>
          ) : null}
          {view === "investigation" ? (
            <section className="panel">
              <div className="section-header">
                <h2>Select a validation prediction</h2>
                <Network size={23} />
              </div>
              <p>
                Supported configuration: binary numeric logistic model with
                fixed median imputation. Measured contributions and similarity
                are distinct from approximate influence.
              </p>
              <Action
                onClick={async () => {
                  const reviewed = await request<{
                    partitions: Record<string, number[]>;
                  }>(
                    `/datasets/${version.id}/configuration?project_id=${project}&reviewed=true`,
                  );
                  setValidation(reviewed.partitions.validation);
                  setRecord(String(reviewed.partitions.validation[0] ?? ""));
                }}
              >
                Review validation identifiers
              </Action>
              <label>
                Validation record position
                <select
                  aria-label="Validation prediction"
                  value={record}
                  onChange={(e) => setRecord(e.target.value)}
                >
                  <option value="">Review and select a record</option>
                  {validation.map((id) => (
                    <option key={id}>{id}</option>
                  ))}
                </select>
              </label>
              <Notice>
                Record positions identify the current version. Stable training
                IDs for corrections are available in reviewed dataset metadata.
                No causal interpretation is implied.
              </Notice>
            </section>
          ) : null}
          {view === "drift" ? <Drift /> : null}
          <label className="analysis-selector">
            Evidence run
            <select
              aria-label="Evidence run"
              value={analysis ?? ""}
              onChange={(e) => selectAnalysis(e.target.value)}
            >
              <option value="">Choose a completed analysis</option>
              {analyses.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.id.slice(0, 8)} · {new Date(a.created_at).toLocaleString()}
                </option>
              ))}
            </select>
          </label>
          {analysis ? (
            <section className="panel">
              <div className="section-header">
                <h2>Analysis {analysis.slice(0, 8)}</h2>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={detailed}
                    onChange={(e) => setDetailed(e.target.checked)}
                  />
                  Reveal owner-only detailed evidence
                </label>
              </div>
              {report.isFetching ? <Pending /> : null}
              {report.error ? (
                <Notice error>{report.error.message}</Notice>
              ) : null}
              {report.data ? (
                <>
                  <Health data={report.data.health} />
                  {!detailed ? (
                    <Notice>
                      Summary scope hides sensitive feature, label and record
                      evidence. Reveal detailed evidence only in a private
                      environment.
                    </Notice>
                  ) : view === "recommendations" ? (
                    <>
                      <p>
                        Dismissal applies to this view only; no persisted review
                        status is claimed.
                      </p>
                      {report.data.recommendations?.map((recommendation, i) =>
                        (dismissed[analysis] ?? []).includes(i) ? null : (
                          <article className="recommendation" key={i}>
                            <Pill
                              value={String(
                                recommendation.evidence_type ??
                                  "review required",
                              )}
                            />
                            <Evidence data={recommendation} />
                            <div className="button-row">
                              <Link
                                className="button"
                                href={`/app/projects/${project}/experiments?version=${version.id}`}
                              >
                                Review in experiment lab{" "}
                                <ArrowRight size={14} />
                              </Link>
                              <button
                                onClick={() =>
                                  setDismissed((previous) => ({
                                    ...previous,
                                    [analysis]: [
                                      ...(previous[analysis] ?? []),
                                      i,
                                    ],
                                  }))
                                }
                              >
                                Dismiss from current view
                              </button>
                            </div>
                          </article>
                        ),
                      ) ?? <p>No recommendations were generated.</p>}
                    </>
                  ) : view === "analyses" ? (
                    Object.entries(report.data.engines).map(([name, e]) => (
                      <details className="engine-result" key={name} open>
                        <summary>
                          {label(name)} <Pill value={e.status} />
                        </summary>
                        {e.code ? <Notice>{e.code}</Notice> : null}
                        <Evidence data={e.result ?? { status: e.status }} />
                      </details>
                    ))
                  ) : outcome ? (
                    <>
                      <div className="section-header">
                        <h3>{title} results</h3>
                        <Pill value={outcome.status} />
                      </div>
                      {outcome.status !== "completed" ? (
                        <Notice>
                          {outcome.code ??
                            "This engine did not produce a supported result. Check configuration and documented limits."}
                        </Notice>
                      ) : null}
                      {view === "valuation" &&
                      Array.isArray(payload.records) ? (
                        <Bars
                          title="Record valuation · first 16 scored records"
                          data={(
                            payload.records as Record<string, unknown>[]
                          ).map((r) => ({
                            name: "Record " + r.record_id,
                            value: measurement(r.score),
                          }))}
                          unit="utility contribution"
                        />
                      ) : null}
                      {view === "labels" &&
                      Array.isArray(payload.candidates) ? (
                        <DataTable
                          rows={payload.candidates as Record<string, unknown>[]}
                          caption="Training label review candidates"
                        />
                      ) : null}
                      {view === "investigation" ? (
                        <Investigation data={payload} />
                      ) : (
                        <Evidence data={data} />
                      )}
                      <details>
                        <summary>Execution and method context</summary>
                        <Evidence data={result} />
                      </details>
                    </>
                  ) : (
                    <Notice>
                      This analysis did not run {title.toLowerCase()}. Submit
                      the engine above; no missing values are shown as zero.
                    </Notice>
                  )}
                  <div className="method-warning">
                    <h3>Interpretation matters</h3>
                    {view === "leakage" ? (
                      <p>
                        Strong predictive power is a heuristic, not proof of
                        leakage. Chronological univariate and label-horizon
                        protection remain unsupported.
                      </p>
                    ) : view === "labels" ? (
                      <p>
                        Do not replace labels automatically. Review records and
                        use a concrete intervention preview before retraining.
                      </p>
                    ) : (
                      <p>
                        Health is an experimental weighted burden score, not a
                        calibrated measure of model performance. Optional
                        methods can be unsupported independently.
                      </p>
                    )}
                    <Link href="/research">Read scientific limitations ↗</Link>
                  </div>
                </>
              ) : null}
            </section>
          ) : view !== "drift" ? (
            <Empty title="No completed evidence for this version">
              <p>
                Run the supported diagnostic above. Job events will appear here
                as they are recorded.
              </p>
            </Empty>
          ) : null}
          {config ? (
            <details className="panel">
              <summary>Dataset boundaries and limitations</summary>
              <Evidence
                data={{
                  target: config.target,
                  split: config.split,
                  counts: config.partition_counts,
                }}
              />
            </details>
          ) : null}
          {view === "labels" ||
          view === "valuation" ||
          view === "investigation" ? (
            <Link
              className="button"
              href={`/app/projects/${project}/experiments?version=${version.id}`}
            >
              Preview a manual correction or exclusion <ArrowRight size={16} />
            </Link>
          ) : null}
        </>
      )}
    </>
  );
}
function Health({
  data,
}: {
  data: { score: number | null; coverage: number; [key: string]: unknown };
}) {
  return (
    <div className="health-grid">
      <div>
        <span className="eyebrow">EXPERIMENTAL HEALTH ASSESSMENT</span>
        <strong>
          {data.score === null ? "Unassessed" : data.score.toFixed(1)}
          <small>{data.score === null ? "" : " / 100"}</small>
        </strong>
        <p>
          Weighted available diagnostic components. Not a model-performance
          score.
        </p>
      </div>
      <div>
        <span className="eyebrow">DIAGNOSTIC COVERAGE</span>
        <strong>
          {(data.coverage * 100).toFixed(0)}
          <small>% assessed</small>
        </strong>
        <meter
          min="0"
          max="1"
          value={data.coverage}
          aria-label="Diagnostic coverage"
        />
        <p>
          Unassessed:{" "}
          {Array.isArray(data.unassessed)
            ? data.unassessed.join(", ")
            : "See component results"}
        </p>
      </div>
      <div>
        <span className="eyebrow">CRITICAL INTEGRITY FINDINGS</span>
        <strong>
          {value(
            data.critical_violation_count ??
              (Array.isArray(data.critical_violations)
                ? data.critical_violations.length
                : null),
          )}
        </strong>
        <p>
          Configured structural evidence is separate from the aggregate score.
        </p>
      </div>
    </div>
  );
}
function Investigation({ data }: { data: Record<string, unknown> }) {
  const contributions = asObject(
    data.contribution ?? data.feature_contributions ?? data.contributions,
  );
  const graph = asObject(data.evidence_graph);
  const edges = Array.isArray(graph.edges)
    ? (graph.edges as Record<string, unknown>[])
    : [];
  return (
    <>
      <Evidence
        data={data.prediction ?? { status: "Prediction details unavailable" }}
      />
      {Array.isArray(contributions.features) ? (
        <Bars
          title="Feature contributions to reconstructed logit"
          unit="logit"
          data={(contributions.features as Record<string, unknown>[]).map(
            (row) => ({
              name: String(row.feature),
              value: measurement(row.logit_contribution),
            }),
          )}
        />
      ) : null}
      {edges.length ? (
        <section className="evidence-relationships">
          <h3>Evidence relationships</h3>
          <p>
            Showing {Math.min(12, edges.length)} of {edges.length} recorded
            relationships. Detailed JSON retains the complete evidence graph.
          </p>
          <p>
            Connections below are recorded by the backend. Inferred influence is
            not a causal relationship.
          </p>
          {edges.slice(0, 12).map((edge, i) => (
            <div className="relationship" key={i}>
              <code>{String(edge.source)}</code>
              <span>
                → {String(edge.type).replaceAll("_", " ").toLowerCase()} →
              </span>
              <code>{String(edge.target)}</code>
              <Pill value={String(edge.evidence ?? "measured")} />
            </div>
          ))}
        </section>
      ) : null}
      <Evidence data={data} />
    </>
  );
}
function Drift() {
  const [reference, setReference] = useState("");
  const [comparison, setComparison] = useState("");
  const [result, setResult] = useState<unknown>();
  async function load(file: File | undefined, set: (s: string) => void) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".csv") || file.size > 1500000)
      throw new Error("Choose a CSV no larger than 1.5 MB.");
    set(
      new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(
        await file.arrayBuffer(),
      ),
    );
  }
  const [error, setError] = useState("");
  return (
    <section className="panel">
      <h2>Compare two local CSV datasets</h2>
      <p>
        Explicit reference and comparison inputs. Results are not persisted in
        project reports; keep this view open or export the displayed evidence
        separately.
      </p>
      <div className="form-grid">
        <label>
          Reference CSV
          <input
            type="file"
            accept=".csv"
            onChange={(e) =>
              void load(e.target.files?.[0], setReference).catch((e) =>
                setError(e.message),
              )
            }
          />
        </label>
        <label>
          Comparison CSV
          <input
            type="file"
            accept=".csv"
            onChange={(e) =>
              void load(e.target.files?.[0], setComparison).catch((e) =>
                setError(e.message),
              )
            }
          />
        </label>
      </div>
      {error ? <Notice error>{error}</Notice> : null}
      <Notice>
        Independent observations are not assumed. Statistical tests requiring
        IID input remain unavailable. Feature shifts alone do not demonstrate
        concept drift.
      </Notice>
      <Action
        kind="primary"
        disabled={!reference || !comparison}
        onClick={async () =>
          setResult(
            await request("/datasets/drift", {
              method: "POST",
              body: json({
                reference_csv: reference,
                comparison_csv: comparison,
                iid: false,
                privacy_mode: "detailed",
              }),
            }),
          )
        }
      >
        Compute distribution comparison
      </Action>
      {result ? <Evidence data={result} /> : null}
    </section>
  );
}
