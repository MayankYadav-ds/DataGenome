"use client";
import Link from "next/link";
import { useEffect, useState, useRef, lazy, Suspense } from "react";
import { useQueryClient, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  ShieldCheck,
  ScanLine,
  Network,
  GitBranch,
  FlaskConical,
  ChevronRight,
  Eye,
  EyeOff,
  Menu,
} from "lucide-react";
import {
  clearIdentity,
  ApiError,
  json,
  request,
  sessionSchema,
  setCsrf,
  type Session,
} from "../lib/api";
import { Action, Brand, Notice, Pending, Theme } from "./ui";
import preview from "../public/demo-preview.json";
const Workspace = lazy(() => import("./Workspace"));
const Research = lazy(() => import("./Research"));
const repo = "https://github.com/MayankYadav-ds/DataGenome";
export default function Product({ segments }: { segments: string[] }) {
  return <Root segments={segments} />;
}
function Root({ segments }: { segments: string[] }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionError, setSessionError] = useState("");
  const currentIdentity = useRef<string | null>(null);
  const identityTransition = useRef(false);
  useEffect(() => {
    currentIdentity.current = session?.user_id ?? null;
  }, [session?.user_id]);
  const client = useQueryClient();
  const router = useRouter();
  const path = "/" + segments.join("/");
  useEffect(() => {
    let active = true;
    request("/auth/session")
      .then((data) => {
        if (active) {
          const current = sessionSchema.parse(data);
          currentIdentity.current = current.user_id;
          setSession(current);
        }
      })
      .catch((error) => {
        if (!(error instanceof ApiError && error.status === 401))
          setSessionError(error.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    const expired = () => {
      clearIdentity();
      client.clear();
      currentIdentity.current = null;
      setSession(null);
      if (window.location.pathname.startsWith("/app"))
        router.replace("/login?expired=true");
    };
    window.addEventListener("session-expired", expired);
    try {
      const theme = localStorage.getItem("dg-theme");
      if (theme === "light") {
        document.documentElement.dataset.theme = "light";
        window.dispatchEvent(new Event("dg-theme-change"));
      }
    } catch {}
    return () => {
      active = false;
      window.removeEventListener("session-expired", expired);
    };
  }, [client, router]);
  useEffect(() => {
    let active = true;
    const channel =
      typeof BroadcastChannel === "undefined"
        ? null
        : new BroadcastChannel("datagenome-identity");
    const reconcile = async (remote: boolean) => {
      if (!remote && identityTransition.current) return;
      if (remote) {
        clearIdentity();
        client.clear();
        setSession(null);
        setLoading(true);
      }
      try {
        const current = sessionSchema.parse(await request("/auth/session"));
        if (active && (remote || current.user_id !== currentIdentity.current)) {
          clearIdentity();
          client.clear();
          currentIdentity.current = current.user_id;
          setSession(current);
          if (window.location.pathname.startsWith("/app"))
            router.replace("/app");
        }
      } catch (error) {
        if (active && !(error instanceof ApiError && error.status === 401))
          setSessionError(
            error instanceof Error
              ? error.message
              : "Session check unavailable.",
          );
      } finally {
        if (active && remote) setLoading(false);
      }
    };
    const announce = () => channel?.postMessage("changed");
    const focus = () => {
      void reconcile(false);
    };
    if (channel)
      channel.onmessage = () => {
        void reconcile(true);
      };
    window.addEventListener("datagenome-identity-local", announce);
    window.addEventListener("focus", focus);
    return () => {
      active = false;
      channel?.close();
      window.removeEventListener("datagenome-identity-local", announce);
      window.removeEventListener("focus", focus);
    };
  }, [client, router]);
  useEffect(() => {
    if (!session) return;
    const delay = Math.max(0, session.expires_at * 1000 - Date.now());
    const timer = setTimeout(
      () => window.dispatchEvent(new Event("session-expired")),
      Math.min(delay, 2147483647),
    );
    return () => clearTimeout(timer);
  }, [session]);
  async function identify(
    mode: string,
    credentials?: { username: string; password: string },
  ) {
    identityTransition.current = true;
    try {
      clearIdentity();
      client.clear();
      const result = await request<{ csrf_token: string }>("/auth/" + mode, {
        method: "POST",
        body: json(credentials ?? {}),
      });
      setCsrf(result.csrf_token);
      const user = sessionSchema.parse(await request("/auth/session"));
      currentIdentity.current = user.user_id;
      setSession(user);
      window.dispatchEvent(new Event("datagenome-identity-local"));
      return user;
    } finally {
      identityTransition.current = false;
    }
  }
  async function demo() {
    if (!session) await identify("guest");
    const result = await request<{
      project: { id: string };
      version: { id: string };
    }>("/datasets/demo", {
      method: "POST",
      body: json({ name: "Synthetic investigation" }),
    });
    client.clear();
    router.push(
      "/app/projects/" + result.project.id + "?version=" + result.version.id,
    );
  }
  async function logout() {
    await request("/auth/logout", { method: "POST" });
    clearIdentity();
    client.clear();
    setSession(null);
    window.dispatchEvent(new Event("datagenome-identity-local"));
    router.push("/");
  }
  if (segments[0] === "app") {
    if (loading) return <Pending text="Checking your local session…" />;
    if (!session)
      return (
        <main className="auth-page">
          <h1>Open your workspace</h1>
          {sessionError ? (
            <Notice error>
              {sessionError}
              <Action onClick={() => window.location.reload()}>
                Retry session check
              </Action>
            </Notice>
          ) : null}
          <p>
            A local session is required before private data can be displayed.
          </p>
          <Link className="button primary" href="/login">
            Sign in
          </Link>
          <Action onClick={demo}>Explore as guest</Action>
        </main>
      );
    return (
      <Suspense fallback={<Pending text="Opening analytical workspace…" />}>
        <Workspace
          key={session.user_id}
          segments={segments}
          session={session}
          demo={demo}
          logout={logout}
        />
      </Suspense>
    );
  }
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <PublicNav session={session} />
      <main id="main">
        {path === "/login" || path === "/register" ? (
          <Auth mode={path.slice(1)} identify={identify} demo={demo} />
        ) : path === "/demo" ? (
          <section className="public-wrap demo-intro">
            <div className="eyebrow">
              SYNTHETIC / REPRODUCIBLE / REAL ENGINES
            </div>
            <h1>
              A small dataset.
              <br />A real investigation.
            </h1>
            <p>
              Explore 80 synthetic records with missing values, training
              duplicates, conflicting labels, class imbalance and an
              intentionally planted target copy. Every finding is computed by
              DataGenome.
            </p>
            <Notice>
              Guest workspaces last one hour, allow three projects and 500
              uploaded rows per dataset. Guest and registered workspaces stay
              separate.
            </Notice>
            <Action kind="primary" onClick={demo}>
              Launch interactive demo <ArrowRight size={16} />
            </Action>
          </section>
        ) : path === "/" ? (
          <Landing demo={demo} />
        ) : (
          <Information page={segments[0]} />
        )}
      </main>
      <footer>
        <Brand />
        <p>Debug the data, not just the model.</p>
        <div>
          <Link href="/documentation">Documentation</Link>
          <a href={repo}>GitHub</a>
          <a href={repo + "/blob/main/LICENSE"}>Apache 2.0</a>
          <Link href="/privacy">Privacy</Link>
          <Link href="/terms">Terms</Link>
          <a href={repo + "/security"}>Security</a>
          <span>v0.7.0 · self-hosted preview</span>
        </div>
      </footer>
    </>
  );
}
function PublicNav({ session }: { session: Session | null }) {
  const [open, setOpen] = useState(false);
  return (
    <header className="public-nav">
      <Brand />
      <button
        className="mobile-toggle icon-button"
        aria-label="Toggle navigation"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <Menu size={22} />
      </button>
      <nav className={open ? "open" : ""} aria-label="Public">
        <Link href="/features">Product</Link>
        <Link href="/how-it-works">How it works</Link>
        <Link href="/research">Research</Link>
        <Link href="/documentation">Documentation</Link>
        <a href={repo}>GitHub ↗</a>
      </nav>
      <div className="nav-actions">
        <Theme />
        <Link href={session ? "/app" : "/login"}>
          {session ? "Workspace" : "Sign in"}
        </Link>
        <Link className="button primary small" href="/register">
          Get started <ArrowRight size={14} />
        </Link>
      </div>
    </header>
  );
}
function Landing({ demo }: { demo: () => Promise<unknown> }) {
  return (
    <>
      <section className="hero public-wrap">
        <div className="hero-copy">
          <div className="eyebrow">
            <span className="live-dot" /> OPEN SOURCE DATA INTELLIGENCE
          </div>
          <h1>
            Your model is only as reliable as <em>its data.</em>
          </h1>
          <p className="hero-description">
            Find the hidden problems behind unreliable predictions. Investigate
            the evidence. Test your data improvements before you trust them.
          </p>
          <div className="hero-actions">
            <Link className="button primary" href="/app">
              Start analyzing <ArrowRight size={17} />
            </Link>
            <Action onClick={demo}>
              Explore interactive demo <ChevronRight size={16} />
            </Action>
          </div>
          <div className="hero-proof">
            <span>
              <ShieldCheck size={15} /> Local-first by design
            </span>
            <span>
              <GitBranch size={15} /> Reproducible versions
            </span>
            <span>Apache 2.0</span>
          </div>
        </div>
        <div className="hero-visual">
          <div className="signal-label">
            DATASET RELIABILITY / INVESTIGATION MAP
          </div>
          <svg
            className="genome-map"
            viewBox="0 0 540 370"
            role="img"
            aria-label="Conceptual dataset evidence map; not an analytical result"
          >
            <defs>
              <pattern
                id="grid"
                width="30"
                height="30"
                patternUnits="userSpaceOnUse"
              >
                <path
                  d="M 30 0 L 0 0 0 30"
                  fill="none"
                  stroke="currentColor"
                  strokeOpacity=".07"
                />
              </pattern>
            </defs>
            <rect width="540" height="370" fill="url(#grid)" />
            {[0, 1, 2, 3, 4, 5, 6].map((i) => (
              <g key={i}>
                <path
                  d={`M ${180 + Math.sin(i) * 58} ${45 + i * 44} L ${360 - Math.sin(i) * 58} ${45 + i * 44}`}
                  stroke="currentColor"
                  strokeOpacity=".3"
                />
                <circle
                  cx={180 + Math.sin(i) * 58}
                  cy={45 + i * 44}
                  r={i === 3 ? 10 : 6}
                  fill={i === 3 ? "var(--warning)" : "var(--accent)"}
                />
                <circle
                  cx={360 - Math.sin(i) * 58}
                  cy={45 + i * 44}
                  r="6"
                  fill="var(--accent)"
                />
              </g>
            ))}
            <text x="22" y="34" className="chart-label">
              01 / TRACE
            </text>
            <text x="380" y="346" className="chart-label">
              02 / VALIDATE
            </text>
          </svg>
          <div className="visual-note">
            <span className="live-dot" /> Evidence before intervention{" "}
            <span>LOCAL / CPU</span>
          </div>
          <div
            className="verified-preview"
            aria-label="Computed synthetic diagnostic preview"
          >
            <div>
              <strong>{preview.rows}</strong>
              <span>synthetic records</span>
            </div>
            <div>
              <strong>
                {Object.values(preview.recommendation_counts).reduce(
                  (a, b) => a + b,
                  0,
                )}
              </strong>
              <span>review recommendations</span>
            </div>
            <div>
              <strong>{Math.round(preview.health.coverage * 100)}%</strong>
              <span>diagnostic coverage</span>
            </div>
          </div>
          <p className="preview-disclosure">
            Computed with the real backend on the built-in synthetic demo. Not
            customer results. Health and review signals are experimental.
          </p>
        </div>
      </section>
      <section className="workflow-strip">
        <div className="public-wrap">
          {[
            "01 Upload a dataset",
            "02 Find hidden problems",
            "03 Investigate evidence",
            "04 Test improvements",
          ].map((s) => (
            <span key={s}>
              {s}
              <ArrowRight size={15} />
            </span>
          ))}
        </div>
      </section>
      <section className="public-wrap capabilities">
        <div className="section-top">
          <div>
            <div className="eyebrow">FROM DATASET TO DECISION</div>
            <h2>
              One workspace.
              <br />
              Multiple lines of evidence.
            </h2>
          </div>
          <p>
            A high score is a starting point, not a verdict. Keep structural
            violations, statistical evidence and heuristic review signals
            distinct.
          </p>
        </div>
        <div className="feature-grid">
          {[
            [
              ScanLine,
              "Leakage diagnostics",
              "Trace target agreement and configured split violations. Keep strong predictors in context.",
            ],
            [
              Network,
              "Label intelligence",
              "Rank training labels for review using out-of-fold evidence, without automatic relabeling.",
            ],
            [
              FlaskConical,
              "Controlled improvement",
              "Create a derived version, compare validation outcomes and keep your held-out test unscored.",
            ],
          ].map(([Icon, title, text]) => {
            const Glyph = Icon as typeof ScanLine;
            return (
              <article key={String(title)}>
                <Glyph size={25} />
                <h3>{String(title)}</h3>
                <p>{String(text)}</p>
                <Link href="/features">
                  Explore capability <ArrowRight size={15} />
                </Link>
              </article>
            );
          })}
        </div>
      </section>
      <section className="research-banner public-wrap">
        <div>
          <div className="eyebrow">
            SCIENTIFIC BY DESIGN. HONEST ABOUT LIMITS.
          </div>
          <h2>
            Measured findings.
            <br />
            No promises of better accuracy.
          </h2>
          <p>
            Data Shapley, influence functions and explicit split safeguards
            inform an experimental toolkit. Every method has assumptions. Every
            improvement needs validation.
          </p>
        </div>
        <Link className="button" href="/research">
          Read the methodology <ArrowRight size={16} />
        </Link>
      </section>
    </>
  );
}
function Auth({
  mode,
  identify,
  demo,
}: {
  mode: string;
  identify: (
    mode: string,
    c?: { username: string; password: string },
  ) => Promise<unknown>;
  demo: () => Promise<unknown>;
}) {
  const router = useRouter();
  const [show, setShow] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const capabilities = useQuery({
    queryKey: ["public-capabilities"],
    enabled: mode === "register",
    queryFn: () =>
      request<{ authentication: { registration: boolean } }>("/capabilities"),
  });
  return (
    <section className="auth-page">
      <div className="eyebrow">YOUR LOCAL INVESTIGATION WORKSPACE</div>
      <h1>{mode === "register" ? "Create your account." : "Welcome back."}</h1>
      <p>
        Use a local username. No email delivery or external identity provider.
      </p>
      {mode === "register" && capabilities.isPending ? (
        <Pending text="Checking local registration availability…" />
      ) : mode === "register" &&
        (capabilities.error ||
          capabilities.data?.authentication.registration === false) ? (
        <Notice>
          Registration is unavailable on this service. Sign in to an existing
          local account or continue as guest.
        </Notice>
      ) : (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            const data = new FormData(e.currentTarget);
            try {
              await identify(mode, {
                username: String(data.get("username")),
                password: String(data.get("password")),
              });
              router.push("/app");
            } catch (e) {
              setError(
                e instanceof Error ? e.message : "Authentication failed.",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Username
            <input
              name="username"
              autoComplete="username"
              required
              minLength={3}
              maxLength={64}
              pattern="[A-Za-z0-9_.-]+"
            />
          </label>
          <label>
            Password
            <div className="password-field">
              <input
                name="password"
                type={show ? "text" : "password"}
                autoComplete={
                  mode === "register" ? "new-password" : "current-password"
                }
                required
                minLength={12}
                maxLength={256}
              />
              <button
                type="button"
                className="icon-button"
                aria-label={show ? "Hide password" : "Show password"}
                onClick={() => setShow(!show)}
              >
                {show ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </label>
          <small>12–256 characters. Sessions last up to eight hours.</small>
          {mode === "register" ? (
            <label className="checkbox">
              <input type="checkbox" required />I have read the{" "}
              <Link href="/terms">terms</Link> and{" "}
              <Link href="/privacy">privacy information</Link>.
            </label>
          ) : null}
          {error ? <Notice error>{error}</Notice> : null}
          <button className="primary" disabled={busy}>
            {busy
              ? "Checking credentials…"
              : mode === "register"
                ? "Create account"
                : "Sign in"}{" "}
            <ArrowRight size={16} />
          </button>
        </form>
      )}
      <div className="auth-divider">OR EXPLORE LOCALLY</div>
      <Action onClick={demo}>Continue as guest</Action>
      <p>
        {mode === "register"
          ? "Already have an account?"
          : "New to DataGenome?"}{" "}
        <Link href={mode === "register" ? "/login" : "/register"}>
          {mode === "register" ? "Sign in" : "Create an account"}
        </Link>
      </p>
      <small>
        Guest data remains separate from registered accounts. No password reset
        or social login is available.
      </small>
    </section>
  );
}
const info: Record<
  string,
  { title: string; intro: string; sections: [string, string][] }
> = {
  features: {
    title: "Follow the evidence.",
    intro:
      "A connected toolkit for dataset debugging, grounded in supported methods.",
    sections: [
      [
        "Leakage & label intelligence",
        "Distinguish exact target agreement, configured split violations and heuristic signals. Review out-of-fold label disagreements.",
      ],
      [
        "Valuation & failure investigation",
        "Compare five bounded valuation methods. Inspect binary numeric logistic predictions, contributions, neighbors and experimental influence.",
      ],
      [
        "Fairness & drift",
        "Measure explicitly supplied groups, suppressed small cells and distribution differences. No universal fairness score or automatic concept-drift conclusion.",
      ],
      [
        "Controlled interventions",
        "Preview explicit corrections, exclusions and feature changes. Derive versions and compare real validation outcomes without scoring the held-out test.",
      ],
    ],
  },
  "how-it-works": {
    title: "A deliberate path to better data.",
    intro: "Discover → investigate → review → validate.",
    sections: [
      [
        "1. Create a workspace",
        "Open an isolated guest session or register a local account. Upload supported CSV data and choose a target and split strategy.",
      ],
      [
        "2. Collect evidence",
        "Run bounded diagnostics. Inspect coverage, unsupported checks and evidence classifications. Missing coverage is never treated as healthy.",
      ],
      [
        "3. Review a concrete change",
        "Use recommendations as investigation leads. Preview a manual correction, exclusion or feature change before creating a derived version.",
      ],
      [
        "4. Compare outcomes",
        "Execute a controlled experiment. Inspect aggregate and per-class deltas, uncertainty availability and negative outcomes. Export the actual report.",
      ],
    ],
  },
  research: {
    title: "Research foundations. Explicit boundaries.",
    intro:
      "Experimental implementations, not endorsement by the original researchers.",
    sections: [
      [
        "Data Shapley & Banzhaf",
        "Values depend on the model, utility and evaluation data. Exact methods are restricted to tiny training games; approximation rankings are not guaranteed.",
      ],
      [
        "Influence functions",
        "Local logistic influence is an approximation. Measured similarity and inferred influence are different relationships; neither proves causality.",
      ],
      [
        "Evaluation integrity",
        "Preprocessing fits on permitted training data. Diagnostic folds avoid outer validation/test records. Experiments are exploratory validation comparisons.",
      ],
      [
        "Currently unsupported",
        "Forward-only chronological univariate scoring is supported. Horizon-aware purging, predictive proxy verification and subgroup intervention uncertainty remain unavailable. The HAR cross-seed result is descriptive, not independent evidence.",
      ],
    ],
  },
  documentation: {
    title: "Run locally. Investigate deliberately.",
    intro:
      "Windows-compatible setup with Python 3.11+ and Node 24 LTS. No paid services.",
    sections: [
      [
        "Install",
        'From the repository: python -m pip install ".[api,dev]". In frontend: npm ci.',
      ],
      [
        "Start the backend",
        "python -m uvicorn datagenome.api:app --host 127.0.0.1 --port 8765",
      ],
      [
        "Start the web application",
        "In frontend: npm run dev. Open http://127.0.0.1:3000. For production mode: npm run build, then npm start.",
      ],
      [
        "API and contributors",
        "The browser uses a same-origin local bridge. Session cookies stay HttpOnly; CSRF tokens stay in memory. Read the repository guides for supported contracts and limitations.",
      ],
    ],
  },
  about: {
    title: "Debug the data, not just the model.",
    intro:
      "DataGenome is an open-source, local-first dataset investigation platform.",
    sections: [
      [
        "Purpose",
        "Help researchers and engineers inspect unreliable labels, leakage, valuation and model failures with evidence they can review.",
      ],
      [
        "Project status",
        "Pre-1.0 local application. Experimental scientific methods and internet-facing deployment limitations remain explicit. No fabricated adoption or performance claims.",
      ],
    ],
  },
  privacy: {
    title: "Your data stays in your local workspace.",
    intro:
      "Local-first does not mean encrypted, anonymous or physically erased.",
    sections: [
      [
        "Storage",
        "The local SQLite database can contain raw datasets, labels, identifiers and detailed findings. Encryption at rest is not provided. Protect the OS account, directory permissions and backups.",
      ],
      [
        "Guests and retention",
        "Guest sessions expire after one hour and cleanup runs periodically. Account data remains until deletion or configured result retention. Guest/account merging is unsupported.",
      ],
      [
        "Exports and deletion",
        "Detailed reports and previews can be sensitive. Redaction is not guaranteed anonymization. Logical deletion does not guarantee erasure from backups, filesystem journals or SSDs.",
      ],
      [
        "Browser state",
        "Only the color theme is stored locally. Session cookies are HttpOnly. Private datasets, reports and CSRF tokens are not placed in browser localStorage.",
      ],
    ],
  },
  terms: {
    title: "Use with scientific judgment.",
    intro:
      "DataGenome is provided under the Apache License 2.0, without a production-readiness claim.",
    sections: [
      [
        "Your responsibility",
        "Only upload data you are authorized to process. Review findings and interventions. A heuristic signal is not proof of an error or discrimination.",
      ],
      [
        "Local deployment",
        "Keep this preview bound to loopback. Do not expose it publicly without independent deployment hardening. No paid infrastructure is enabled.",
      ],
      [
        "No performance guarantee",
        "Neutral and negative experiment results are expected. A positive validation difference does not establish a general or statistically meaningful improvement.",
      ],
    ],
  },
};
function Information({ page }: { page: string }) {
  const data = info[page];
  if (!data)
    return (
      <section className="public-wrap">
        <h1>Page not found</h1>
        <Link href="/">Return home</Link>
      </section>
    );
  return (
    <article className="public-wrap info-page">
      <div className="eyebrow">
        DATAGENOME / {page.toUpperCase().replaceAll("-", " ")}
      </div>
      <h1>{data.title}</h1>
      <p className="intro">{data.intro}</p>
      {page === "research" ? (
        <Suspense fallback={<Pending text="Loading research" />}>
          <Research />
        </Suspense>
      ) : null}
      {data.sections.map(([title, text]) => (
        <section key={title}>
          <h2>{title}</h2>
          <p>{text}</p>
        </section>
      ))}
      {page === "research" ? (
        <div className="research-links">
          <a href="https://proceedings.mlr.press/v97/ghorbani19c.html">
            Data Shapley · Ghorbani & Zou
          </a>
          <a href="https://proceedings.mlr.press/v70/koh17a.html">
            Influence functions · Koh & Liang
          </a>
          <a href="https://github.com/opendataval/opendataval">
            OpenDataVal framework
          </a>
        </div>
      ) : null}
      <a className="button" href={repo + "/tree/main/docs"}>
        Read repository documentation ↗
      </a>
    </article>
  );
}
