# Phase 8 verification — 0.5.0

Verified on Windows on 2026-11-19. Starting checkpoint: public `main` at
`d8d8918f222d91ce194ac8a432b6cd08cfcb7278`, clean and synchronized, with the prior
Windows CI successful. The account owner remained the sole repository collaborator.
No visibility, access, history, paid infrastructure or original user dataset changes
were made. Expenditure: ₹0.

## Delivered local application

The public product pages, login/registration, real isolated guest demo, projects,
four-step CSV ingestion, diagnostic workspaces, individual prediction investigation,
recommendations, reviewed manual interventions, dataset lineage, controlled
experiments, report exports and deletion/settings use the existing backend.
See the [route/API matrix, startup and developer guide](web-application.md).
Small owner-checked inventory/configuration endpoints and an optional valuation
method field support the browser without duplicating scientific engines.

Query caches persist across navigation and clear on identity changes, including
cross-tab changes and late responses. The loopback-only same-origin bridge preserves
backend authorization, cookies and CSRF checks. Raw evidence requires review;
downloaded dataset text uses a `.csv.txt` filename to reduce automatic spreadsheet
formula execution. This does not make untrusted CSV safe to open as a spreadsheet.

## Observed verification

| Check | Observed result |
|---|---|
| Installed-wheel Python regression suite | 93 passed in 55.38 seconds; coverage not run |
| Wheel/source agreement | All 48 Python modules byte-identical; import from site-packages |
| Python quality | Ruff lint and format pass (103 files); strict mypy passes (48 modules) |
| Packaging | Wheel and source archive built; source includes frontend, lockfile, tests and screenshots; excludes dependencies, generated bundles, databases and local environment files |
| Module CLI / dependency consistency | `python -m datagenome --version` reports 0.5.0; `pip check` passes |
| Frontend | 17 unit tests pass; strict TypeScript, ESLint, formatting and optimized build pass |
| Real production browser integration | Six scenarios pass in 47.0 seconds; no mocked scientific responses |
| Accessibility / responsive | Applicable axe WCAG 2.2 AA checks pass on public/authentication pages and a workspace; widths 360, 390, 768, 1024, 1440 and 1920 checked |
| Dependency advisory scans | npm and pip-audit report no known advisories at verification time |

The browser scenarios cover registration, failed and successful login, logout,
session revocation, ownership denial, CSRF/origin rejection, cross-tab cache
isolation, cancellation, invalid and valid CSV uploads, raw-preview consent, drift,
diagnostics, unsupported valuation input, supported leave-one-out valuation,
individual predictions, fairness, repeated recommendation dismissals, manual label
correction, exact-plan approval, real experiments, versions, export and deletion.

The synthetic experiment removed the constant feature and applied an explicit
training-label correction. Both baseline and requested arm had validation accuracy,
balanced accuracy and macro F1 of 1.0. Log loss was approximately 0.030145 versus
0.005778. The held-out test was not scored. This easy planted-target-copy fixture
demonstrates plumbing, not generalization, label-detector accuracy or a proven
intervention benefit. No new scientific benchmark claim is made.

Twenty-one [synthetic screenshots](screenshots/README.md) document the working
application. Visual review corrected overly dense nested evidence cells and made
experiment metrics primary, with detailed metadata expandable. Tiny nonzero
statistical values retain scientific notation rather than displaying as zero.

## Measured local performance

[Raw observations and methodology](web-performance.json) come from one fresh
Chromium context against the optimized local build at 1440×1000:

- DOMContentLoaded: 33 ms; load event: 175.8 ms.
- Initial script transfer: 191,915 bytes including immediate prefetch.
- All 28 production JavaScript files: 1,149,023 raw bytes, 356,053 gzip bytes.
- Renderer JavaScript heap snapshot: 4,937,800 bytes, not peak process memory.
- Five bridged capability requests: 11.08–31.06 ms, median 20.34 ms.

These are single-run localhost observations. No Lighthouse/Core Web Vitals score,
isolated chart timing, network-device performance or scalability claim is made.

## Limits and maintenance

This is a local application preview, not an internet-facing production deployment.
Database encryption, shared organizations, guest/account transfer, password reset,
email verification, PDF generation and individual-version deletion are unavailable.
Drift comparisons are not persisted project jobs; recommendation dismissal lasts
only in the current view. Advanced SDK configuration and prediction-specific
before/after intervention comparison are not exposed as working web controls.
Research limitations remain in the [capability inventory](capabilities.md).

Windows Application Control blocked the newer scikit-learn native module locally;
verification used scikit-learn 1.6.1 with NumPy 2.2.6 and SciPy 1.17.1, without
bypassing Windows controls. Tests emit existing SciPy solver and Starlette TestClient
deprecation warnings. ESLint 9 is deprecated but retains compatible Next plugin
peers. GitHub withdrew the previously reported picomatch advisory on 2026-11-18;
the dependency was not represented as patched. Advisory scans are time-bound.

Chromium automation and screenshots do not certify other browser engines, complete
assistive-technology compatibility or formal accessibility compliance. Logical
deletion is not physical secure erasure. Continued internet hardening and broader
scientific validation remain necessary.

The first hosted run passed backend checks and caught Windows Git converting
frontend source to CRLF before Prettier. Explicit frontend LF checkout attributes
correct this without disabling formatting checks.

The Windows CI now includes backend checks plus frontend types, lint, formatting,
unit tests, build and real browser integration. Publication commit and hosted run
results are reported with the release handoff after execution.
