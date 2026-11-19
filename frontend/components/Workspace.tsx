"use client";
import Link from "next/link";
import { useState, useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import {
  Activity,
  ArrowRight,
  Folder,
  Database,
  ScanLine,
  Tags,
  ChartNoAxesCombined,
  Network,
  Scale,
  GitBranch,
  FlaskConical,
  FileText,
  Settings,
  LogOut,
  Menu,
  ShieldCheck,
  ChevronRight,
  Search,
} from "lucide-react";
import {
  request,
  json,
  q,
  download,
  projectSchema,
  versionSchema,
  jobSchema,
  terminal,
  type Session,
  type Version,
  type Job,
} from "../lib/api";
import {
  Action,
  Brand,
  Heading,
  Empty,
  Notice,
  Pending,
  Pill,
  Theme,
  Evidence,
  DataTable,
  Bars,
  value,
  label,
  asObject,
  measurement,
} from "./ui";
import Upload from "./Upload";
import Diagnostics from "./Diagnostics";
const inventorySchema = z.object({
  datasets: z.array(versionSchema),
  analyses: z.array(
    z.object({
      id: z.string(),
      version_id: z.string(),
      created_at: z.string(),
      health: z.record(z.string(), z.unknown()),
    }),
  ),
  experiments: z.array(
    z.object({
      id: z.string(),
      version_id: z.string(),
      state: z.string().nullable(),
      created_at: z.string(),
    }),
  ),
  jobs: z.array(jobSchema),
  offset: z.number(),
  limit: z.number(),
});
export const configSchema = z.object({
  columns: z.array(z.string()),
  target: z.string(),
  split: z.record(z.string(), z.unknown()),
  partition_counts: z.record(z.string(), z.number()),
  partitions: z.record(z.string(), z.array(z.number())).nullable(),
  record_ids: z.array(z.number()).nullable(),
  transformation: z.unknown(),
  parent_id: z.string().nullable(),
});
export type Config = z.infer<typeof configSchema>;
const nav = [
  ["overview", "Overview", Activity],
  ["datasets", "Datasets", Database],
  ["analyses", "Diagnostics", ScanLine],
  ["leakage", "Leakage", ShieldCheck],
  ["labels", "Label intelligence", Tags],
  ["valuation", "Data valuation", ChartNoAxesCombined],
  ["investigation", "Failure investigator", Network],
  ["fairness", "Fairness", Scale],
  ["drift", "Distribution drift", Activity],
  ["recommendations", "Recommendations", ScanLine],
  ["experiments", "Experiments", FlaskConical],
  ["versions", "Dataset versions", GitBranch],
  ["reports", "Reports", FileText],
] as const;
export default function Workspace({
  segments,
  session,
  demo,
  logout,
}: {
  segments: string[];
  session: Session;
  demo: () => Promise<unknown>;
  logout: () => Promise<unknown>;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const client = useQueryClient();
  const [mobile, setMobile] = useState(false);
  const [offset, setOffset] = useState(0);
  const project = segments[1] === "projects" ? segments[2] : undefined;
  const view =
    segments[1] === "settings"
      ? "settings"
      : project
        ? (segments[3] ?? "overview")
        : "projects";
  const projects = useQuery({
    queryKey: [session.user_id, "projects"],
    queryFn: async () =>
      z.array(projectSchema).parse(await request("/projects?limit=100")),
  });
  const inventory = useQuery({
    queryKey: [session.user_id, project, "inventory", offset],
    enabled: !!project,
    queryFn: async () =>
      inventorySchema.parse(
        await request(`/projects/${project}/inventory?offset=${offset}`),
      ),
    refetchInterval: (query) =>
      query.state.data?.jobs.some((j) => !terminal(j.state)) ? 2000 : false,
  });
  const activeProject = projects.data?.find((p) => p.id === project);
  const selected =
    params.get("version") ??
    (segments[3] === "datasets" ? segments[4] : undefined) ??
    inventory.data?.datasets[0]?.id;
  const version = inventory.data?.datasets.find((v) => v.id === selected);
  const configuration = useQuery({
    queryKey: [session.user_id, project, selected, "configuration"],
    enabled: !!project && !!selected,
    queryFn: async () =>
      configSchema.parse(
        await request(
          `/datasets/${selected}/configuration?project_id=${project}`,
        ),
      ),
  });
  function href(page: string) {
    return `/app/projects/${project}${page === "overview" ? "" : "/" + page}${selected ? "?version=" + selected : ""}`;
  }
  function navigateQuery(values: Record<string, string>) {
    const next = new URLSearchParams(params.toString());
    for (const [key, v] of Object.entries(values)) {
      if (v) next.set(key, v);
      else next.delete(key);
    }
    router.push(
      `/app/projects/${project}/${view === "overview" ? "analyses" : view}?${next}`,
    );
  }
  async function refresh() {
    await client.invalidateQueries({ queryKey: [session.user_id] });
  }
  const currentJob = params.get("job");
  const job = useQuery({
    queryKey: [session.user_id, project, currentJob, "job"],
    enabled: !!project && !!currentJob,
    queryFn: async () =>
      jobSchema.parse(
        await request(`/jobs/${currentJob}?project_id=${project}`),
      ),
    refetchInterval: (query) =>
      query.state.data && !terminal(query.state.data.state) ? 1500 : false,
  });
  const jobState = job.data?.state;
  useEffect(() => {
    if (jobState && terminal(jobState))
      void client.invalidateQueries({
        queryKey: [session.user_id, project, "inventory"],
      });
  }, [jobState, client, project, session.user_id]);
  async function submit(
    engines: string[],
    options: Record<string, unknown> = {},
  ) {
    if (!selected || !project) throw new Error("Select a dataset first.");
    const result = jobSchema.parse(
      await request("/analyses", {
        method: "POST",
        body: json({
          project_id: project,
          version_id: selected,
          engines,
          seconds: 30,
          ...options,
        }),
      }),
    );
    navigateQuery({ job: result.id, analysis: "" });
    await refresh();
  }
  const latest = inventory.data?.analyses
    .filter((a) => a.version_id === selected)
    .at(-1);
  const analysis =
    params.get("analysis") ??
    (segments[3] === "analyses" ? segments[4] : undefined) ??
    (job.data?.state === "completed" && !job.data.experiment_id
      ? job.data.result_id
      : null) ??
    latest?.id;
  const [confirm, setConfirm] = useState<{
    title: string;
    body: string;
    action: () => Promise<unknown>;
  } | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (confirm) dialog.current?.showModal();
    else dialog.current?.close();
  }, [confirm]);
  function confirmAction(
    title: string,
    body: string,
    action: () => Promise<unknown>,
  ) {
    setConfirm({ title, body, action });
  }
  return (
    <div className={"app-shell " + (mobile ? "sidebar-open" : "")}>
      <a className="skip-link" href="#workspace-main">
        Skip to content
      </a>
      <aside className="sidebar">
        <Brand />
        <div className="workspace-label">INVESTIGATION WORKSPACE</div>
        <Link
          className={
            "sidebar-link " + (!project && view === "projects" ? "active" : "")
          }
          href="/app/projects"
        >
          <Folder size={17} /> Projects
        </Link>
        {project ? (
          <>
            <div className="sidebar-project">
              {activeProject?.name ?? "Project"}
              <span>LOCAL PROJECT</span>
            </div>
            <nav aria-label="Workspace">
              {nav.map(([key, title, Icon]) => (
                <Link
                  key={key}
                  href={href(key)}
                  onClick={() => setMobile(false)}
                  className={"sidebar-link " + (view === key ? "active" : "")}
                >
                  <Icon size={17} />
                  {title}
                  {key === "investigation" ? (
                    <span className="tiny-tag">BETA</span>
                  ) : null}
                </Link>
              ))}
            </nav>
          </>
        ) : (
          <div className="sidebar-help">
            <Network size={34} />
            <h3>Start with a question.</h3>
            <p>
              Open a project to follow your dataset from evidence to experiment.
            </p>
          </div>
        )}
        <div className="sidebar-bottom">
          <Link className="sidebar-link" href="/app/settings">
            <Settings size={17} /> Settings & privacy
          </Link>
          <Link className="sidebar-link" href="/documentation">
            Documentation ↗
          </Link>
          <span className="local-status">
            <span className="live-dot" /> LOCAL / CPU-FIRST · v0.5.0
          </span>
        </div>
      </aside>
      <div className="app-body">
        <header className="topbar">
          <button
            className="icon-button mobile-toggle"
            aria-label="Toggle workspace navigation"
            onClick={() => setMobile(!mobile)}
          >
            <Menu size={20} />
          </button>
          <div className="breadcrumbs">
            <Link href="/app">Workspace</Link>
            <ChevronRight size={13} />
            <span>
              {activeProject?.name ??
                (view === "settings" ? "Settings" : "Projects")}
            </span>
            {project ? (
              <>
                <ChevronRight size={13} />
                <span>
                  {nav.find((n) => n[0] === view)?.[1] ?? label(view)}
                </span>
              </>
            ) : null}
          </div>
          <div className="topbar-actions">
            {inventory.data ? (
              <span className="muted">
                {inventory.data.jobs.filter((j) => !terminal(j.state)).length}{" "}
                running jobs
              </span>
            ) : null}
            <Theme />
            <span className="account-badge">
              {session.guest ? "Guest session" : session.username}
            </span>
            <Action kind="quiet" onClick={logout}>
              <LogOut size={15} /> Sign out
            </Action>
          </div>
        </header>
        <main id="workspace-main" className="workspace-main">
          {session.guest ? (
            <div className="guest-banner">
              <span>GUEST WORKSPACE</span> Isolated · 500 rows/dataset · 3
              projects · expires{" "}
              {new Date(session.expires_at * 1000).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
              <Link href="/app/settings">Privacy & limits</Link>
            </div>
          ) : null}
          {!project && view === "projects" ? (
            <Projects
              session={session}
              projects={projects.data}
              error={projects.error}
              demo={demo}
              refresh={refresh}
            />
          ) : view === "settings" ? (
            <SettingsPage
              session={session}
              logout={logout}
              confirm={confirmAction}
            />
          ) : (
            <>
              {inventory.isPending ? (
                <Pending text="Loading owned project inventory…" />
              ) : inventory.error ? (
                <Notice error>
                  {inventory.error.message}{" "}
                  <Link href="/app/projects">Return to your projects</Link>
                </Notice>
              ) : inventory.data ? (
                <>
                  <div className="dataset-context">
                    <Database size={16} />
                    <label>
                      ACTIVE VERSION
                      <select
                        aria-label="Active dataset version"
                        value={selected ?? ""}
                        onChange={(e) =>
                          navigateQuery({
                            version: e.target.value,
                            job: "",
                            analysis: "",
                            experiment: "",
                          })
                        }
                      >
                        {inventory.data.datasets.length === 0 ? (
                          <option value="">No dataset yet</option>
                        ) : (
                          inventory.data.datasets.map((v) => (
                            <option key={v.id} value={v.id}>
                              {v.parent_id ? "Derived" : "Original"} ·{" "}
                              {v.id.slice(0, 8)} · {v.row_count} rows
                            </option>
                          ))
                        )}
                      </select>
                    </label>
                    {version ? (
                      <span className="muted">
                        {version.column_count} columns · original preserved
                      </span>
                    ) : null}
                  </div>
                  {job.data ? (
                    <JobPanel
                      job={job.data}
                      project={project!}
                      refresh={async () => {
                        await job.refetch();
                        await refresh();
                      }}
                    />
                  ) : job.error ? (
                    <Notice error>{job.error.message}</Notice>
                  ) : null}
                  {view === "overview" ? (
                    <>
                      <Heading
                        eyebrow="PROJECT / OVERVIEW"
                        title={activeProject?.name ?? "Project overview"}
                        description="A connected view of the evidence collected in this project."
                        action={
                          <Link
                            className="button primary"
                            href={href("datasets")}
                          >
                            Upload dataset <ArrowRight size={16} />
                          </Link>
                        }
                      />
                      <div className="stat-grid">
                        {[
                          ["Dataset versions", inventory.data.datasets.length],
                          ["Analyses", inventory.data.analyses.length],
                          ["Experiments", inventory.data.experiments.length],
                          [
                            "Running jobs",
                            inventory.data.jobs.filter(
                              (j) => !terminal(j.state),
                            ).length,
                          ],
                        ].map(([name, count]) => (
                          <div className="stat" key={String(name)}>
                            <span>{name}</span>
                            <strong>{count}</strong>
                            <small>Current inventory page</small>
                          </div>
                        ))}
                      </div>
                      <div className="two-column">
                        <section className="panel">
                          <h2>Recent diagnostic runs</h2>
                          {inventory.data.analyses.length ? (
                            inventory.data.analyses
                              .slice(-5)
                              .reverse()
                              .map((a) => (
                                <Link
                                  className="list-row"
                                  key={a.id}
                                  href={href("analyses") + "&analysis=" + a.id}
                                >
                                  <span>
                                    Analysis {a.id.slice(0, 8)}
                                    <small>
                                      {new Date(a.created_at).toLocaleString()}
                                    </small>
                                  </span>
                                  <Pill value="completed" />
                                </Link>
                              ))
                          ) : (
                            <Empty title="No evidence collected yet">
                              <p>
                                Upload a dataset, choose a split, then run
                                diagnostics.
                              </p>
                            </Empty>
                          )}
                        </section>
                        <section className="panel">
                          <h2>Project controls</h2>
                          <Rename
                            project={project!}
                            name={activeProject?.name ?? ""}
                            refresh={refresh}
                          />
                          <p className="muted">
                            Created{" "}
                            {activeProject
                              ? new Date(
                                  activeProject.created_at,
                                ).toLocaleString()
                              : "Unavailable"}
                            . Descriptions and last-modified timestamps are not
                            stored by this backend.
                          </p>
                          <button
                            className="danger-button"
                            onClick={() =>
                              confirmAction(
                                "Delete project?",
                                "Removes all project datasets, versions, jobs and reports. Running jobs must stop first. Backups and physical erasure are not covered.",
                                async () => {
                                  await request("/projects/" + project, {
                                    method: "DELETE",
                                  });
                                  await refresh();
                                  router.push("/app/projects");
                                },
                              )
                            }
                          >
                            Delete project
                          </button>
                        </section>
                      </div>
                    </>
                  ) : view === "datasets" ? (
                    <>
                      <Heading
                        title="Dataset workspace"
                        description="A bounded, reviewable path from CSV to diagnostic evidence."
                      />
                      <Upload
                        key={project}
                        project={project!}
                        guest={session.guest}
                        onRegistered={async (v) => {
                          await refresh();
                          navigateQuery({ version: v.id });
                        }}
                      />
                      {version && configuration.data ? (
                        <DatasetView
                          key={selected}
                          project={project!}
                          version={version}
                          config={configuration.data}
                          submit={submit}
                          confirm={confirmAction}
                          refresh={refresh}
                        />
                      ) : null}
                    </>
                  ) : view === "versions" ? (
                    <Versions
                      project={project!}
                      versions={inventory.data.datasets}
                      config={configuration.data}
                      selected={selected}
                      choose={(id) => navigateQuery({ version: id })}
                    />
                  ) : view === "experiments" ? (
                    <Experiments
                      key={selected}
                      project={project!}
                      version={version}
                      session={session}
                      inventory={inventory.data.experiments}
                      params={params}
                      navigate={navigateQuery}
                      refresh={refresh}
                    />
                  ) : view === "reports" ? (
                    <Reports
                      key={project}
                      project={project!}
                      analyses={inventory.data.analyses}
                      confirm={confirmAction}
                      refresh={refresh}
                    />
                  ) : (
                    <Diagnostics
                      key={view + selected}
                      project={project!}
                      version={version}
                      config={configuration.data}
                      view={view}
                      analysis={analysis ?? undefined}
                      analyses={inventory.data.analyses.filter(
                        (a) => a.version_id === selected,
                      )}
                      selectAnalysis={(id) =>
                        navigateQuery({ analysis: id, job: "" })
                      }
                      submit={submit}
                      refresh={refresh}
                    />
                  )}
                  <div className="inventory-pagination">
                    <button
                      disabled={offset === 0}
                      onClick={() => setOffset(Math.max(0, offset - 100))}
                    >
                      Previous inventory page
                    </button>
                    <span>Up to 100 artifacts per kind · offset {offset}</span>
                    <button
                      disabled={
                        Math.max(
                          inventory.data.datasets.length,
                          inventory.data.analyses.length,
                          inventory.data.experiments.length,
                          inventory.data.jobs.length,
                        ) < 100
                      }
                      onClick={() => setOffset(offset + 100)}
                    >
                      Next inventory page
                    </button>
                  </div>
                </>
              ) : null}
            </>
          )}
        </main>
        <div className="app-footer">
          <span>Evidence requires interpretation.</span>
          <Link href="/research">Methods & limitations ↗</Link>
        </div>
      </div>
      <dialog
        ref={dialog}
        aria-labelledby="confirm-title"
        onCancel={() => setConfirm(null)}
      >
        <h2 id="confirm-title">{confirm?.title}</h2>
        <p>{confirm?.body}</p>
        <div className="dialog-actions">
          <button onClick={() => setConfirm(null)}>Cancel</button>
          <Action
            kind="danger-button"
            onClick={async () => {
              await confirm?.action();
              setConfirm(null);
            }}
          >
            Confirm deletion
          </Action>
        </div>
      </dialog>
    </div>
  );
}
function Projects({
  session,
  projects,
  error,
  demo,
  refresh,
}: {
  session: Session;
  projects: z.infer<typeof projectSchema>[] | undefined;
  error: Error | null;
  demo: () => Promise<unknown>;
  refresh: () => Promise<unknown>;
}) {
  const [name, setName] = useState("");
  const [search, setSearch] = useState("");
  const router = useRouter();
  return (
    <>
      <Heading
        title="Your investigation starts here."
        description="Create a project, bring a dataset, follow the evidence."
        action={
          <Action onClick={demo}>
            Open synthetic demo <ArrowRight size={16} />
          </Action>
        }
      />
      <div className="project-create panel">
        <Folder size={22} />
        <label>
          New project name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Customer churn investigation"
            maxLength={100}
          />
        </label>
        <Action
          kind="primary"
          disabled={!name.trim()}
          onClick={async () => {
            const p = projectSchema.parse(
              await request("/projects", {
                method: "POST",
                body: json({ name }),
              }),
            );
            await refresh();
            router.push("/app/projects/" + p.id);
          }}
        >
          Create project <ArrowRight size={16} />
        </Action>
      </div>
      <div className="section-header">
        <h2>Project directory</h2>
        <label className="search-input">
          <Search size={16} />
          <input
            aria-label="Search projects"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search your projects…"
          />
        </label>
      </div>
      {error ? (
        <Notice error>{error.message}</Notice>
      ) : !projects ? (
        <Pending />
      ) : projects.length === 0 ? (
        <Empty title="A clean workspace. A clear starting point.">
          <p>
            Nothing is analyzed until you choose a dataset. Try the synthetic
            demo to see a real workflow.
          </p>
        </Empty>
      ) : (
        <div className="project-grid">
          {projects
            .filter((p) => p.name.toLowerCase().includes(search.toLowerCase()))
            .map((p) => (
              <Link
                className="project-card"
                href={"/app/projects/" + p.id}
                key={p.id}
              >
                <Folder size={24} />
                <Pill value="local project" />
                <h2>{p.name}</h2>
                <p>Created {new Date(p.created_at).toLocaleDateString()}</p>
                <div>
                  Open investigation <ArrowRight size={17} />
                </div>
              </Link>
            ))}
        </div>
      )}
      <Notice>
        {session.guest
          ? "Guest workspaces are isolated and expire after one hour. Registration creates a separate workspace."
          : "Data is stored locally without encryption at rest. Protect your operating-system account and backups."}
      </Notice>
    </>
  );
}
function Rename({
  project,
  name,
  refresh,
}: {
  project: string;
  name: string;
  refresh: () => Promise<unknown>;
}) {
  const [next, setNext] = useState(name);
  return (
    <div className="inline-form">
      <label>
        Project name
        <input
          value={next}
          onChange={(e) => setNext(e.target.value)}
          maxLength={100}
        />
      </label>
      <Action
        onClick={async () => {
          await request("/projects/" + project, {
            method: "PATCH",
            body: json({ name: next }),
          });
          await refresh();
        }}
      >
        Save name
      </Action>
    </div>
  );
}
export function JobPanel({
  job,
  project,
  refresh,
}: {
  job: Job;
  project: string;
  refresh: () => Promise<unknown>;
}) {
  return (
    <section className="job-panel" aria-live="polite">
      <div>
        <Activity size={19} />
        <strong>{job.experiment_id ? "Experiment" : "Analysis"} job</strong>
        <Pill value={job.state} />
        <code>{job.id.slice(0, 8)}</code>
      </div>
      {job.cancel_requested && !terminal(job.state) ? (
        <p>
          Cancellation requested. Waiting for the next fit or engine boundary.
        </p>
      ) : null}
      {job.error ? (
        <Notice error>
          {job.error}. No successful completion was recorded.
        </Notice>
      ) : null}
      <ol className="job-events">
        {job.events.map((e, i) => (
          <li key={i}>
            {value(e.engine ?? e.stage)} ·{" "}
            {value(e.state ?? e.completed_fits ?? e.completed_engines)}
            {e.completed_fits != null ? " completed fits" : ""}
          </li>
        ))}
      </ol>
      {!terminal(job.state) ? (
        <Action
          onClick={async () => {
            await request(`/jobs/${job.id}/cancel?project_id=${project}`, {
              method: "POST",
            });
            await refresh();
          }}
        >
          Request cancellation
        </Action>
      ) : null}
    </section>
  );
}
function DatasetView({
  project,
  version,
  config,
  submit,
  confirm,
  refresh,
}: {
  project: string;
  version: Version;
  config: Config;
  submit: (
    engines: string[],
    options?: Record<string, unknown>,
  ) => Promise<unknown>;
  confirm: (a: string, b: string, c: () => Promise<unknown>) => void;
  refresh: () => Promise<unknown>;
}) {
  const [preview, setPreview] = useState<{
    columns: string[];
    rows: string[][];
  } | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [engines, setEngines] = useState([
    "profile",
    "intelligence",
    "leakage",
    "labels",
    "anomalies",
  ]);
  const [attributes, setAttributes] = useState("");
  return (
    <>
      <section className="panel">
        <div className="section-header">
          <div>
            <h2>Dataset configuration</h2>
            <p>
              {version.row_count} rows · {version.column_count} columns · target{" "}
              {config.target}
            </p>
          </div>
          <Pill value={String(config.split.strategy)} />
        </div>
        <DataTable
          rows={config.columns.map((name) => ({
            column: name,
            role:
              name === config.target
                ? "Target"
                : name === config.split.group
                  ? "Group"
                  : name === config.split.time
                    ? "Time"
                    : "Feature",
          }))}
          caption="Registered columns"
        />
        <details>
          <summary>Split and version metadata</summary>
          <Evidence
            data={{
              split: config.split,
              partition_counts: config.partition_counts,
              transformation: config.transformation,
            }}
          />
        </details>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={reviewed}
            onChange={(e) => setReviewed(e.target.checked)}
          />
          I understand record previews may contain sensitive data.
        </label>
        <Action
          disabled={!reviewed}
          onClick={async () =>
            setPreview(
              await request(
                `/datasets/${version.id}/preview?${q({ project_id: project, reviewed: true, limit: 20 })}`,
              ),
            )
          }
        >
          Load bounded record preview
        </Action>
        {preview ? (
          <DataTable
            rows={preview.rows.map((row) =>
              Object.fromEntries(
                preview.columns.map((c, i) => [c, row[i] || "Missing"]),
              ),
            )}
            caption="Owner-only first 20 records"
          />
        ) : null}
      </section>
      <section className="panel">
        <h2>Configure analysis</h2>
        <p className="muted">
          All computation uses the registered split. The outer test is not
          scored by diagnostics.
        </p>
        <fieldset>
          <legend>Diagnostic engines</legend>
          <div className="check-grid">
            {[
              "profile",
              "intelligence",
              "leakage",
              "labels",
              "anomalies",
              "valuation",
              "errors",
              "fairness",
              "proxies",
            ].map((engine) => (
              <label className="checkbox" key={engine}>
                <input
                  type="checkbox"
                  checked={engines.includes(engine)}
                  onChange={(e) =>
                    setEngines(
                      e.target.checked
                        ? [...engines, engine]
                        : engines.filter((x) => x !== engine),
                    )
                  }
                />
                {label(engine)}
              </label>
            ))}
          </div>
        </fieldset>
        <label>
          Sensitive audit attributes (comma separated, explicit only)
          <input
            value={attributes}
            onChange={(e) => setAttributes(e.target.value)}
            placeholder="Optional column names"
          />
        </label>
        <Notice>
          Fairness requires supplied sensitive attributes and supported binary
          models. Drift needs a separate comparison dataset. Chronological
          univariate scoring and horizon purging are unavailable.
        </Notice>
        <Action
          kind="primary"
          disabled={!engines.length}
          onClick={() =>
            submit(engines, {
              attributes: attributes
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            })
          }
        >
          Run selected diagnostics <ArrowRight size={16} />
        </Action>
      </section>
      <section className="panel">
        <h2>Dataset lifecycle</h2>
        <p>
          Dataset exports preserve source values. Download as CSV text to avoid
          automatic spreadsheet formula evaluation.
        </p>
        <Action
          disabled={!reviewed}
          onClick={() =>
            download(
              `/datasets/${version.id}/export?${q({ project_id: project, reviewed: true })}`,
              "datagenome-dataset.csv.txt",
            )
          }
        >
          Export reviewed CSV text
        </Action>
        <button
          className="danger-button"
          onClick={() =>
            confirm(
              "Delete this dataset lineage?",
              "Deletes original and derived versions, and conservatively clears ALL project results and jobs. Other dataset lineages remain. Physical erasure and backups are not covered.",
              async () => {
                await request(`/datasets/${version.id}?project_id=${project}`, {
                  method: "DELETE",
                });
                await refresh();
              },
            )
          }
        >
          Delete dataset lineage
        </button>
      </section>
    </>
  );
}
function Versions({
  project,
  versions,
  config,
  selected,
  choose,
}: {
  project: string;
  versions: Version[];
  config: Config | undefined;
  selected: string | undefined;
  choose: (id: string) => void;
}) {
  const [comparison, setComparison] = useState<unknown>();
  const parent = versions.find((v) => v.id === selected)?.parent_id;
  return (
    <>
      <Heading
        title="Every change has a history."
        description="Persisted parent–child versions. Originals are never overwritten."
      />
      <div className="lineage-list">
        {versions.map((v) => (
          <button
            className={"lineage-node " + (v.id === selected ? "selected" : "")}
            onClick={() => choose(v.id)}
            key={v.id}
          >
            <GitBranch size={20} />
            <span>
              {v.parent_id
                ? "Derived from " + v.parent_id.slice(0, 8)
                : "Original dataset"}
              <strong>{v.id.slice(0, 12)}</strong>
              <small>
                {v.row_count} rows · {v.column_count} columns ·{" "}
                {new Date(v.created_at).toLocaleString()}
              </small>
            </span>
            <span>
              Inspect <ArrowRight size={15} />
            </span>
          </button>
        ))}
      </div>
      {config ? (
        <section className="panel">
          <h2>Selected transformation</h2>
          <Evidence data={config.transformation} />
          {parent ? (
            <Action
              onClick={async () =>
                setComparison(
                  await request(
                    `/datasets/${parent}/compare/${selected}?project_id=${project}`,
                  ),
                )
              }
            >
              Compare with parent
            </Action>
          ) : (
            <p className="muted">
              Original version has no parent transformation.
            </p>
          )}
          {comparison ? <Evidence data={comparison} /> : null}
        </section>
      ) : null}
      <Notice>
        Deletion operates on entire dataset lineages. There is no
        individual-version deletion endpoint or mutable active-version pointer.
      </Notice>
    </>
  );
}
function Experiments({
  project,
  version,
  session,
  inventory,
  params,
  navigate,
  refresh,
}: {
  project: string;
  version: Version | undefined;
  session: Session;
  inventory: {
    id: string;
    version_id: string;
    state: string | null;
    created_at: string;
  }[];
  params: ReturnType<typeof useSearchParams>;
  navigate: (v: Record<string, string>) => void;
  refresh: () => Promise<unknown>;
}) {
  const [feature, setFeature] = useState("");
  const [records, setRecords] = useState("");
  const [record, setRecord] = useState("");
  const [replacement, setReplacement] = useState("");
  const [preview, setPreview] = useState<unknown>();
  const [approved, setApproved] = useState(false);
  const [planSnapshot, setPlanSnapshot] = useState<string>("");
  const [search, setSearch] = useState<unknown>();
  const plan = {
    remove_features: feature
      ? feature
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
      : [],
    remove_records: records
      ? records.split(",").map((s) => Number(s.trim()))
      : [],
    corrections:
      record && replacement
        ? [{ record_id: Number(record), label: replacement }]
        : [],
  };
  const body = { project_id: project, version_id: version?.id, plan };
  const experiment =
    params.get("experiment") ??
    inventory.filter((e) => e.version_id === version?.id).at(-1)?.id;
  const result = useQuery({
    queryKey: [session.user_id, project, experiment, "experiment"],
    enabled: !!experiment,
    queryFn: () =>
      request<Record<string, unknown>>(
        `/experiments/${experiment}?project_id=${project}`,
      ),
  });
  const arms = Array.isArray(result.data?.arms)
    ? (result.data.arms as Record<string, unknown>[])
    : [];
  return (
    <>
      <Heading
        title="Experiment laboratory"
        description="Controlled changes. Real validation outcomes. No guaranteed improvements."
      />
      {!version ? (
        <Empty title="Select a dataset first" />
      ) : (
        <>
          <div className="two-column">
            <section className="panel">
              <div className="eyebrow">01 / CONCRETE INTERVENTION</div>
              <h2>Prepare a reviewable change</h2>
              <p>
                Fixed logistic-regression baseline; balanced accuracy and macro
                F1 define the supported Pareto comparison.
              </p>
              <label>
                Remove features (comma separated)
                <input
                  value={feature}
                  onChange={(e) => setFeature(e.target.value)}
                  placeholder="e.g. constant"
                />
              </label>
              <label>
                Exclude stable training record IDs
                <input
                  value={records}
                  onChange={(e) => setRecords(e.target.value)}
                  placeholder="e.g. 12, 27"
                />
              </label>
              <div className="form-grid">
                <label>
                  Correct stable record ID
                  <input
                    inputMode="numeric"
                    value={record}
                    onChange={(e) => setRecord(e.target.value)}
                  />
                </label>
                <label>
                  Explicit replacement label
                  <input
                    value={replacement}
                    onChange={(e) => setReplacement(e.target.value)}
                  />
                </label>
              </div>
              <Action
                onClick={async () => {
                  const output = await request("/interventions/preview", {
                    method: "POST",
                    body: json(body),
                  });
                  setPreview(output);
                  setPlanSnapshot(json(body));
                  setApproved(false);
                }}
              >
                Preview intervention
              </Action>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={approved}
                  onChange={(e) => setApproved(e.target.checked)}
                />
                I reviewed this exact plan and authorize bounded retraining.
              </label>
              <Action
                kind="primary"
                disabled={!preview || !approved || planSnapshot !== json(body)}
                onClick={async () => {
                  const job = jobSchema.parse(
                    await request("/experiments", {
                      method: "POST",
                      body: json({
                        project_id: project,
                        version_id: version.id,
                        plans: [plan],
                        authorized: true,
                        max_fits: session.guest ? 3 : 6,
                        seconds: 30,
                      }),
                    }),
                  );
                  navigate({
                    job: job.id,
                    experiment: job.experiment_id ?? "",
                  });
                  await refresh();
                }}
              >
                Run controlled experiment <FlaskConical size={16} />
              </Action>
              <Action
                disabled={!preview || !approved || planSnapshot !== json(body)}
                onClick={async () => {
                  await request("/interventions/apply", {
                    method: "POST",
                    body: json({ ...body, reviewed: true }),
                  });
                  await refresh();
                }}
              >
                Create derived version only
              </Action>
            </section>
            <section className="panel">
              <div className="eyebrow">02 / REVIEW & SAFEGUARDS</div>
              <h2>Before a single fit</h2>
              <Notice>
                Only training records can change. Removal/class guards apply.
                Changing inputs invalidates approval. Experiments remain
                exploratory and keep the held-out test unscored.
              </Notice>
              {preview ? (
                <Evidence data={preview} />
              ) : (
                <Empty title="Preview a proposed intervention">
                  <p>
                    Review affected rows and features here before execution.
                  </p>
                </Empty>
              )}
              <Action
                onClick={async () =>
                  setSearch(
                    await request("/plans/search", {
                      method: "POST",
                      body: json({
                        project_id: project,
                        version_id: version.id,
                        maximum_candidates: 4,
                      }),
                    }),
                  )
                }
              >
                Find bounded structural candidates
              </Action>
              {search ? <Evidence data={search} /> : null}
            </section>
          </div>
          <section className="panel">
            <h2>Persisted experiment outcomes</h2>
            <label>
              Experiment
              <select
                aria-label="Select experiment"
                value={experiment ?? ""}
                onChange={(e) => navigate({ experiment: e.target.value })}
              >
                {!inventory.length ? (
                  <option value="">No experiments yet</option>
                ) : (
                  inventory.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.id.slice(0, 8)} ·{" "}
                      {new Date(e.created_at).toLocaleString()}
                    </option>
                  ))
                )}
              </select>
            </label>
            <Action disabled={!experiment} onClick={() => result.refetch()}>
              Refresh outcomes
            </Action>
            {result.isFetching ? <Pending /> : null}
            {result.error ? (
              <Notice error>{result.error.message}</Notice>
            ) : null}
            {result.data ? (
              <>
                <Pill value={String(result.data.state)} />
                {arms.length ? (
                  <Bars
                    title="Validation balanced accuracy"
                    unit="score (0–1)"
                    data={[
                      {
                        name: "Baseline",
                        value: measurement(
                          asObject(result.data.baseline).balanced_accuracy,
                        ),
                      },
                      ...arms.map((a, i) => ({
                        name: "Arm " + (i + 1) + " " + String(a.role ?? ""),
                        value: measurement(
                          asObject(a.metrics).balanced_accuracy,
                        ),
                      })),
                    ]}
                  />
                ) : null}
                {arms.length ? (
                  <>
                    <DataTable
                      caption="Validation metric comparison"
                      rows={[
                        {
                          arm: "Baseline",
                          accuracy: asObject(result.data.baseline).accuracy,
                          balanced_accuracy: asObject(result.data.baseline)
                            .balanced_accuracy,
                          macro_f1: asObject(result.data.baseline).macro_f1,
                          log_loss: asObject(result.data.baseline).log_loss,
                        },
                        ...arms.map((arm, i) => ({
                          arm: `Arm ${i + 1}: ${String(arm.role)}`,
                          accuracy: asObject(arm.metrics).accuracy,
                          balanced_accuracy: asObject(arm.metrics)
                            .balanced_accuracy,
                          macro_f1: asObject(arm.metrics).macro_f1,
                          log_loss: asObject(arm.metrics).log_loss,
                        })),
                      ]}
                    />
                    <Notice>
                      Validation comparison only. Higher accuracy/F1 and lower
                      log loss are preferable, but a positive point estimate is
                      not proof of improvement. Held-out test scored:{" "}
                      {value(result.data.held_out_evaluated)}.
                    </Notice>
                    {arms.map((arm, i) => (
                      <details key={i}>
                        <summary>
                          Arm {i + 1} changes, per-class evidence and
                          uncertainty
                        </summary>
                        <Evidence
                          data={{
                            delta: arm.delta,
                            class_recall_change: arm.class_recall_change,
                            uncertainty: arm.uncertainty,
                            removed_records: arm.removed_records,
                            corrected_labels: arm.corrected_labels,
                            removed_features: arm.removed_features,
                            training_seconds: arm.training_seconds,
                          }}
                        />
                      </details>
                    ))}
                    <details>
                      <summary>
                        Inspect full persisted experiment metadata
                      </summary>
                      <Evidence data={result.data} />
                    </details>
                  </>
                ) : (
                  <Evidence data={result.data} />
                )}
              </>
            ) : (
              <p className="muted">
                No fabricated comparison is shown before a completed experiment.
              </p>
            )}
          </section>
        </>
      )}
    </>
  );
}
function Reports({
  project,
  analyses,
  confirm,
  refresh,
}: {
  project: string;
  analyses: { id: string; version_id: string; created_at: string }[];
  confirm: (a: string, b: string, c: () => Promise<unknown>) => void;
  refresh: () => Promise<unknown>;
}) {
  const [selected, setSelected] = useState(analyses.at(-1)?.id ?? "");
  const [privacy, setPrivacy] = useState("summary");
  const [format, setFormat] = useState("json");
  const report = useQuery({
    queryKey: [project, selected, "report-preview"],
    enabled: !!selected,
    queryFn: () => request(`/analyses/${selected}?project_id=${project}`),
  });
  return (
    <>
      <Heading
        title="Report center"
        description="Export the actual findings, with an explicit privacy scope."
      />
      {!analyses.length ? (
        <Empty title="No reports yet">
          <p>Complete an analysis to create a persisted report.</p>
        </Empty>
      ) : (
        <section className="panel">
          <div className="form-grid">
            <label>
              Analysis report
              <select
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
              >
                {analyses.map((a) => (
                  <option value={a.id} key={a.id}>
                    {a.id.slice(0, 8)} ·{" "}
                    {new Date(a.created_at).toLocaleString()}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Export format
              <select
                value={format}
                onChange={(e) => setFormat(e.target.value)}
              >
                <option value="json">JSON</option>
                <option value="markdown">Markdown</option>
                <option value="engine-csv">Engine status CSV</option>
              </select>
            </label>
            <label>
              Privacy scope
              <select
                value={privacy}
                onChange={(e) => setPrivacy(e.target.value)}
              >
                <option value="summary">Summary</option>
                <option value="redacted">Redacted (not anonymous)</option>
                <option value="detailed">Detailed — sensitive evidence</option>
              </select>
            </label>
          </div>
          <Notice>
            Detailed exports can include labels, record identifiers and
            findings. Redacted reports are not guaranteed anonymous. Markdown
            and CSV contain summaries.
          </Notice>
          <div className="button-row">
            <Action
              kind="primary"
              onClick={() =>
                download(
                  `/reports/${selected}?${q({ project_id: project, format, privacy })}`,
                  "datagenome-report." +
                    (format === "markdown"
                      ? "md"
                      : format === "engine-csv"
                        ? "csv"
                        : "json"),
                )
              }
            >
              Export report
            </Action>
            <button onClick={() => window.print()}>Print summary</button>
            <button
              className="danger-button"
              onClick={() =>
                confirm(
                  "Delete report?",
                  "Deletes this persisted analysis report. Independently cached diagnostics remain until retention or project deletion.",
                  async () => {
                    await request(
                      `/reports/${selected}?project_id=${project}`,
                      { method: "DELETE" },
                    );
                    setSelected("");
                    await refresh();
                  },
                )
              }
            >
              Delete report
            </button>
          </div>
          {report.data ? (
            <Evidence data={report.data} />
          ) : report.isPending ? (
            <Pending />
          ) : null}
        </section>
      )}
    </>
  );
}
function SettingsPage({
  session,
  logout,
  confirm,
}: {
  session: Session;
  logout: () => Promise<unknown>;
  confirm: (a: string, b: string, c: () => Promise<unknown>) => void;
}) {
  return (
    <>
      <Heading
        title="Settings & privacy"
        description="Explicit boundaries for your local workspace."
      />
      <section className="panel">
        <h2>Session identity</h2>
        <Evidence
          data={{
            account: session.guest ? "Isolated guest" : session.username,
            expires: new Date(session.expires_at * 1000).toLocaleString(),
            session_storage: "HttpOnly cookie; CSRF in memory",
            guest_transfer: "Unsupported; workspaces remain separate",
          }}
        />
        <Action onClick={logout}>Revoke current session</Action>
      </section>
      <section className="panel">
        <h2>Appearance</h2>
        <p>Color theme is the only browser-persisted preference.</p>
        <Theme />
      </section>
      <section className="panel">
        <h2>Limits & retention</h2>
        <p>
          {session.guest
            ? "3 projects · 500 rows / 32 columns per upload · 30-second cooperative budget · 3 fits per experiment · 1-hour guest expiry."
            : "50 projects · 5,000 rows / 64 columns per upload · up to 120-second cooperative budgets · 6 fits per experiment."}
        </p>
        <p>
          One worker, eight active queued/running requests. Account retention
          defaults to indefinite; operators can configure result retention on
          the backend. It cannot be changed through this interface.
        </p>
        <Notice>
          Local SQLite storage is unencrypted. Logical deletion does not
          guarantee physical erasure or remove backups. Keep the service on
          loopback; internet-facing deployment is not certified.
        </Notice>
      </section>
      <section className="panel danger-zone">
        <h2>Delete {session.guest ? "guest workspace" : "account and data"}</h2>
        <p>
          This removes owned resources and revokes sessions. Running work first
          receives cancellation; cleanup may remain pending.
        </p>
        <button
          className="danger-button"
          onClick={() =>
            confirm(
              "Delete this identity and owned data?",
              "This action removes every owned project, dataset and report. Guest and account workspaces are separate. Backups and physical erasure are not covered.",
              async () => {
                await request("/auth/account", { method: "DELETE" });
                window.dispatchEvent(new Event("datagenome-identity-local"));
                window.location.replace(
                  new URL("/", window.location.origin).href,
                );
              },
            )
          }
        >
          Delete {session.guest ? "guest data" : "account and data"}
        </button>
      </section>
    </>
  );
}
