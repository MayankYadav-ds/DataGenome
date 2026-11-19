"use client";
import { useMemo, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { AlertCircle, Check, LoaderCircle, Moon, Sun } from "lucide-react";
export function Brand() {
  return (
    <Link className="brand" href="/" aria-label="DataGenome home">
      <svg viewBox="0 0 32 36" width="29" height="33" aria-hidden="true">
        <path
          d="M6 3v30M26 3v30M6 6h20M6 18h20M6 30h20M6 6l20 12L6 30"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        />
        <circle cx="6" cy="6" r="3" fill="currentColor" />
        <circle cx="26" cy="18" r="3" fill="currentColor" />
        <circle cx="6" cy="30" r="3" fill="currentColor" />
      </svg>
      <span>
        DataGenome<span className="brand-dot">.</span>
      </span>
    </Link>
  );
}
export function Theme() {
  const dark = useSyncExternalStore(
    subscribeTheme,
    () => document.documentElement.dataset.theme !== "light",
    () => true,
  );
  return (
    <button
      className="icon-button"
      aria-label="Toggle color theme"
      onClick={() => {
        const next = !dark;
        document.documentElement.dataset.theme = next ? "dark" : "light";
        try {
          localStorage.setItem("dg-theme", next ? "dark" : "light");
        } catch {}
        window.dispatchEvent(new Event("dg-theme-change"));
      }}
    >
      {dark ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}
function subscribeTheme(update: () => void) {
  const storage = (event: StorageEvent) => {
    if (
      event.key === "dg-theme" &&
      ["light", "dark"].includes(event.newValue ?? "")
    ) {
      document.documentElement.dataset.theme = event.newValue!;
      update();
    }
  };
  window.addEventListener("dg-theme-change", update);
  window.addEventListener("storage", storage);
  return () => {
    window.removeEventListener("dg-theme-change", update);
    window.removeEventListener("storage", storage);
  };
}
export function Notice({
  children,
  error = false,
}: {
  children: React.ReactNode;
  error?: boolean;
}) {
  return (
    <div
      className={"notice " + (error ? "danger" : "")}
      role={error ? "alert" : "note"}
    >
      <AlertCircle size={17} />
      <div>{children}</div>
    </div>
  );
}
export function Pending({
  text = "Loading measured results…",
}: {
  text?: string;
}) {
  return (
    <div className="pending" role="status">
      <LoaderCircle size={18} className="spin" />
      {text}
    </div>
  );
}
export function Action({
  children,
  onClick,
  kind = "",
  disabled = false,
}: {
  children: React.ReactNode;
  onClick: () => Promise<unknown> | unknown;
  kind?: string;
  disabled?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <span className="action-wrap">
      <button
        disabled={busy || disabled}
        className={"button " + kind}
        onClick={async () => {
          setError("");
          setBusy(true);
          try {
            await onClick();
          } catch (e) {
            setError(e instanceof Error ? e.message : "Action failed.");
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? <LoaderCircle size={15} className="spin" /> : null}
        {children}
      </button>
      {error ? (
        <span className="inline-error" role="alert">
          {error}
        </span>
      ) : null}
    </span>
  );
}
export function Pill({ value }: { value: string }) {
  return (
    <span
      className={
        "pill " +
        (/confirmed|failed|critical/.test(value)
          ? "bad"
          : /completed/.test(value)
            ? "good"
            : "neutral")
      }
    >
      {/completed/.test(value) ? <Check size={12} /> : null}
      {value.replaceAll("_", " ")}
    </span>
  );
}
export function Heading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <header className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow ?? "WORKSPACE / DATAGENOME"}</div>
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {action}
    </header>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <section className="empty">
      <div className="empty-mark">＋</div>
      <h2>{title}</h2>
      {children}
    </section>
  );
}
export const measurement = (v: unknown) =>
  typeof v === "number" && Number.isFinite(v) ? v : Number.NaN;
export const label = (s: string) =>
  s.replaceAll("_", " ").replace(/(^| )\w/g, (c) => c.toUpperCase());
export function value(v: unknown): string {
  if (v == null) return "Unavailable";
  if (typeof v === "number")
    return !Number.isFinite(v)
      ? "Unavailable"
      : Number.isInteger(v)
        ? v.toLocaleString()
        : Math.abs(v) < 0.0001
          ? v.toExponential(3)
          : v.toLocaleString(undefined, { maximumSignificantDigits: 5 });
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}
export function DataTable({
  rows,
  caption = "Measured evidence",
}: {
  rows: Record<string, unknown>[];
  caption?: string;
}) {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("");
  const [page, setPage] = useState(0);
  const filtered = useMemo(() => {
    const selected = rows.filter((row) =>
      Object.values(row).some((v) =>
        value(v).toLowerCase().includes(search.toLowerCase()),
      ),
    );
    return sort
      ? selected.sort((a, b) =>
          typeof a[sort] === "number" && typeof b[sort] === "number"
            ? Number(b[sort]) - Number(a[sort])
            : value(a[sort]).localeCompare(value(b[sort])),
        )
      : selected;
  }, [rows, search, sort]);
  const keys = Array.from(
    new Set(rows.flatMap((row) => Object.keys(row))),
  ).slice(0, 64);
  return (
    <div className="table-module">
      <div className="table-toolbar">
        <label>
          Filter records{" "}
          <input
            aria-label={"Filter " + caption}
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            placeholder="Search loaded evidence…"
          />
        </label>
        <span className="muted">{filtered.length} records</span>
      </div>
      <div className="table-scroll">
        <table>
          <caption>{caption}</caption>
          <thead>
            <tr>
              {keys.map((key) => (
                <th key={key}>
                  <button onClick={() => setSort(key)}>{label(key)} ↕</button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.slice(page * 15, page * 15 + 15).map((row, i) => (
              <tr key={i}>
                {keys.map((key) => (
                  <td
                    key={key}
                    title={
                      typeof row[key] === "object" ? undefined : value(row[key])
                    }
                  >
                    {row[key] !== null && typeof row[key] === "object" ? (
                      <StructuredCell data={row[key] as object} />
                    ) : (
                      value(row[key])
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 ? (
          <p className="muted">No matching records.</p>
        ) : null}
      </div>
      <div className="pagination">
        <button disabled={page === 0} onClick={() => setPage(page - 1)}>
          Previous
        </button>
        <span>Page {page + 1} · 15 rows per page</span>
        <button
          disabled={(page + 1) * 15 >= filtered.length}
          onClick={() => setPage(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
function StructuredCell({ data }: { data: object }) {
  const [open, setOpen] = useState(false);
  return (
    <details
      className="cell-details"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>
        Inspect{" "}
        {Array.isArray(data)
          ? `${data.length} items`
          : `${Object.keys(data).length} fields`}
      </summary>
      {open ? <Evidence data={data} depth={2} /> : null}
    </details>
  );
}
export function Evidence({
  data,
  depth = 0,
}: {
  data: unknown;
  depth?: number;
}) {
  if (data == null) return <span className="muted">Unavailable</span>;
  if (typeof data !== "object") return <span>{value(data)}</span>;
  if (Array.isArray(data)) {
    if (!data.length)
      return <p className="muted">No findings in this result.</p>;
    if (
      data.every(
        (item) => item && typeof item === "object" && !Array.isArray(item),
      )
    )
      return <DataTable rows={data as Record<string, unknown>[]} />;
    return (
      <ul className="evidence-list">
        {data.slice(0, 100).map((v, i) => (
          <li key={i}>
            {typeof v === "object" ? (
              <Evidence data={v} depth={depth + 1} />
            ) : (
              value(v)
            )}
          </li>
        ))}
        {data.length > 100 ? (
          <li>
            Showing 100 of {data.length}. Export detailed JSON for the complete
            result.
          </li>
        ) : null}
      </ul>
    );
  }
  return (
    <div className="evidence-grid">
      {Object.entries(data).map(([key, v]) =>
        typeof v === "object" && v !== null ? (
          <details key={key} open={depth < 1}>
            <summary>{label(key)}</summary>
            <Evidence data={v} depth={depth + 1} />
          </details>
        ) : (
          <div className="datum" key={key}>
            <span>{label(key)}</span>
            {key === "classification" || key === "status" ? (
              <Pill value={value(v)} />
            ) : (
              <strong>{value(v)}</strong>
            )}
          </div>
        ),
      )}
    </div>
  );
}
export function Bars({
  data,
  title,
  unit = "value",
}: {
  data: { name: string; value: number }[];
  title: string;
  unit?: string;
}) {
  const shown = data.filter((d) => Number.isFinite(d.value)).slice(0, 16);
  const scale = Math.max(1, ...shown.map((d) => Math.abs(d.value)));
  if (!shown.length)
    return <p className="muted">No numerical measurements available.</p>;
  return (
    <figure className="chart">
      <figcaption>{title}</figcaption>
      <svg
        role="img"
        aria-label={title + "; " + unit}
        viewBox={`0 0 620 ${shown.length * 30 + 30}`}
      >
        <title>{title}</title>
        <desc>
          Measured {unit}. Negative values extend left of zero. Exact values are
          labelled.
        </desc>
        {shown.map((d, i) => (
          <g key={i}>
            <text x="0" y={i * 30 + 20} className="chart-label">
              {d.name.slice(0, 21)}
            </text>
            <rect
              x={d.value < 0 ? 380 + (d.value / scale) * 150 : 380}
              y={i * 30 + 6}
              width={(Math.abs(d.value) / scale) * 150}
              height="18"
              rx="2"
              className={d.value < 0 ? "negative" : "positive"}
            >
              <title>
                {d.name}: {d.value} {unit}
              </title>
            </rect>
            <text x="548" y={i * 30 + 20} className="chart-value">
              {Number(d.value.toPrecision(4))}
            </text>
          </g>
        ))}
        <line
          x1="380"
          x2="380"
          y1="0"
          y2={shown.length * 30}
          className="axis"
        />
        <text x="378" y={shown.length * 30 + 22} className="chart-label">
          0 · {unit}
        </text>
      </svg>
      <details>
        <summary>View numerical data</summary>
        <DataTable rows={shown} caption={title} />
      </details>
    </figure>
  );
}
export function asObject(data: unknown): Record<string, unknown> {
  return data && typeof data === "object" && !Array.isArray(data)
    ? (data as Record<string, unknown>)
    : {};
}
