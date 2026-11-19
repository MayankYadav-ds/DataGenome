"use client";
import { useState } from "react";
import { UploadCloud, ArrowRight, Check } from "lucide-react";
import { request, json, versionSchema, type Version } from "../lib/api";
import { Action, DataTable, Notice, Pending } from "./ui";
import { z } from "zod";
const profileSchema = z.object({
  row_count: z.number(),
  column_count: z.number(),
  columns: z.array(
    z.object({
      name: z.string(),
      dtype: z.string(),
      missing_count: z.number(),
      unique_count: z.number(),
    }),
  ),
});
export default function Upload({
  project,
  guest,
  onRegistered,
}: {
  project: string;
  guest: boolean;
  onRegistered: (v: Version) => Promise<unknown>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(1);
  const [profile, setProfile] = useState<z.infer<typeof profileSchema> | null>(
    null,
  );
  const [target, setTarget] = useState("");
  const [strategy, setStrategy] = useState("stratified");
  const [group, setGroup] = useState("");
  const [time, setTime] = useState("");
  const [seed, setSeed] = useState(42);
  const [reviewed, setReviewed] = useState(false);
  async function load(next: File | undefined) {
    if (!next) return;
    setError("");
    setProfile(null);
    setReviewed(false);
    if (!next.name.toLowerCase().endsWith(".csv")) {
      setError("Only CSV files are supported.");
      return;
    }
    if (next.size > (guest ? 1000000 : 5000000)) {
      setError(
        "File exceeds the browser upload budget: " +
          (guest ? "1 MB for guests." : "5 MB."),
      );
      return;
    }
    setBusy(true);
    try {
      const csv = new TextDecoder("utf-8", {
        fatal: true,
        ignoreBOM: true,
      }).decode(await next.arrayBuffer());
      const preview = profileSchema.parse(
        await request("/datasets/profile?filename=upload.csv", {
          method: "POST",
          body: csv,
          headers: { "Content-Type": "text/csv" },
        }),
      );
      if (guest && (preview.row_count > 500 || preview.column_count > 32))
        throw new Error("Guest uploads allow 500 rows and 32 columns.");
      setFile(next);
      setText(csv);
      setProfile(preview);
      setTarget(preview.columns.at(-1)?.name ?? "");
      setStep(2);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not validate CSV.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel upload-panel">
      <div className="stepper" aria-label="Upload steps">
        {["Upload", "Inspect", "Configure", "Review"].map((name, i) => (
          <span
            className={step === i + 1 ? "current" : step > i + 1 ? "done" : ""}
            key={name}
          >
            {step > i + 1 ? <Check size={13} /> : i + 1}
            <span>{name}</span>
          </span>
        ))}
      </div>
      {error ? <Notice error>{error}</Notice> : null}
      {busy ? (
        <Pending text="Transferring CSV and validating with the backend…" />
      ) : null}
      {step === 1 ? (
        <div
          className="drop-zone"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            void load(e.dataTransfer.files[0]);
          }}
        >
          <UploadCloud size={36} />
          <h2>Bring a dataset. Keep control.</h2>
          <p>Drop a CSV here, or choose a local file.</p>
          <label className="file-picker">
            Choose CSV file
            <input
              type="file"
              accept=".csv,text/csv"
              aria-label="Choose CSV file"
              onChange={(e) => void load(e.target.files?.[0])}
            />
          </label>
          <small>
            {guest
              ? "500 rows · 32 columns · 1 MB browser limit"
              : "5,000 rows · 64 columns · 5 MB browser limit"}
            . No cloud upload.
          </small>
        </div>
      ) : null}
      {step === 2 && profile ? (
        <>
          <h2>Inspect the schema</h2>
          <p>
            {file?.name} · {profile.row_count} rows · {profile.column_count}{" "}
            columns. Types and missing counts computed by the backend.
          </p>
          <DataTable
            rows={profile.columns}
            caption="Validated column profiles"
          />
          <div className="button-row">
            <button onClick={() => setStep(1)}>Choose another file</button>
            <button className="primary" onClick={() => setStep(3)}>
              Configure analysis <ArrowRight size={16} />
            </button>
          </div>
        </>
      ) : null}
      {step === 3 && profile ? (
        <>
          <h2>Define evaluation boundaries</h2>
          <div className="form-grid">
            <label>
              Classification target
              <select
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              >
                {profile.columns.map((c) => (
                  <option key={c.name}>{c.name}</option>
                ))}
              </select>
            </label>
            <label>
              Split strategy
              <select
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
              >
                {["stratified", "random", "group", "chronological"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
            <label>
              Random seed
              <input
                type="number"
                min="0"
                max="4294967295"
                value={seed}
                onChange={(e) => setSeed(Number(e.target.value))}
              />
            </label>
            {strategy === "group" ? (
              <label>
                Group identifier
                <select
                  value={group}
                  onChange={(e) => setGroup(e.target.value)}
                >
                  <option value="">Choose group column</option>
                  {profile.columns
                    .filter((c) => c.name !== target)
                    .map((c) => (
                      <option key={c.name}>{c.name}</option>
                    ))}
                </select>
              </label>
            ) : null}
            {strategy === "chronological" ? (
              <label>
                Timestamp column
                <select value={time} onChange={(e) => setTime(e.target.value)}>
                  <option value="">Choose time column</option>
                  {profile.columns
                    .filter((c) => c.name !== target)
                    .map((c) => (
                      <option key={c.name}>{c.name}</option>
                    ))}
                </select>
              </label>
            ) : null}
          </div>
          <Notice>
            Classification only. Group/time columns are protected from model
            inputs. Horizon-aware purging and chronological univariate scoring
            are unsupported. Feature selection uses reviewed derived versions
            after registration.
          </Notice>
          <div className="button-row">
            <button onClick={() => setStep(2)}>Back</button>
            <button
              className="primary"
              disabled={
                (strategy === "group" && !group) ||
                (strategy === "chronological" && !time) ||
                !Number.isInteger(seed) ||
                seed < 0 ||
                seed >= 2 ** 32
              }
              onClick={() => setStep(4)}
            >
              Review registration <ArrowRight size={16} />
            </button>
          </div>
        </>
      ) : null}
      {step === 4 && profile ? (
        <>
          <h2>Review before registration</h2>
          <dl className="review-list">
            <div>
              <dt>File</dt>
              <dd>{file?.name}</dd>
            </div>
            <div>
              <dt>Target</dt>
              <dd>{target}</dd>
            </div>
            <div>
              <dt>Split</dt>
              <dd>
                {strategy} · seed {seed}
              </dd>
            </div>
            <div>
              <dt>Dimensions</dt>
              <dd>
                {profile.row_count} × {profile.column_count}
              </dd>
            </div>
          </dl>
          <Notice>
            Raw data is stored in your owned local SQLite workspace without
            encryption at rest. Registration does not run a model or change your
            source file. Choose diagnostic engines after registration.
          </Notice>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={reviewed}
              onChange={(e) => setReviewed(e.target.checked)}
            />
            I am authorized to process this dataset and reviewed the split
            configuration.
          </label>
          <div className="button-row">
            <button onClick={() => setStep(3)}>Back</button>
            <Action
              kind="primary"
              disabled={!reviewed}
              onClick={async () => {
                const result = versionSchema.parse(
                  await request("/datasets", {
                    method: "POST",
                    body: json({
                      project_id: project,
                      csv: text,
                      target,
                      strategy,
                      seed,
                      group: strategy === "group" ? group : null,
                      time: strategy === "chronological" ? time : null,
                    }),
                  }),
                );
                await onRegistered(result);
                setStep(1);
                setFile(null);
                setText("");
                setProfile(null);
              }}
            >
              Register dataset <ArrowRight size={16} />
            </Action>
          </div>
        </>
      ) : null}
    </section>
  );
}
