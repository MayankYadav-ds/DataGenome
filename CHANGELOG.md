# Changelog

## 0.3.0

- Added immutable logical versions, reviewed transformations, orchestration, explicit plan comparisons, bounded jobs and report views.
- Added paired cluster/block bootstrap and reproducible public grouped/temporal acquisition benchmarks.

- Added group-aware and historical audit folds, fairness diagnostics, distribution and performance drift, and frozen slice confirmation.

- Added frozen holdout evaluation, an experimental logistic influence engine, and a validation prediction investigator with error slices and redacted output.

- Added five validation-only training-record valuation methods and matched data removal experiments.

## 0.2.0

- Added deterministic dataset identities and reproducible split manifests.
- Added advanced profiling, anomaly detection and split-aware leakage audits.
- Added classification baselines, metric reporting and controlled validation experiments.
- Extended the CLI and local HTTP API and added reproducible diagnostic benchmarks.

## 0.1.0

- Added local CSV ingestion, profiling, structured findings, and a profiling CLI.
- Added a local HTTP API and reproducible synthetic classification demonstration.

## 0.4.0 — authenticated local backend

- Argon2id accounts, revocable cookie sessions, CSRF checks, isolated guests and
  server-side project ownership; legacy CLI projects stay unowned over HTTP.
- Project rename/delete, dataset lineage deletion, bounded reviewed previews,
  report listing/deletion, synthetic guest demo, expiry cleanup and optional retention.
- Declarative training-only learned preprocessing with reconstruction and corruption checks.
- Persistent queued experiments, active-request deduplication, fit-boundary
  cancellation, restart recovery and real fit progress; HTTP authorized experiments
  now return a job instead of synchronously returning results.
- Bounded structural candidate search, conflict checking, paired independent/group/
  temporal bootstrap for validation accuracy, balanced accuracy and macro F1.
- Auth-aware OpenAPI, measured report series, security regressions and frozen
  public-data replication. Scientific extensions remain explicitly unsupported.

Migration: back up local SQLite data before first opening with 0.4. Schema 1
migrates to 2 without assigning legacy ownership. Older readers reject schema 2.
Use the trusted local SDK/CLI for legacy projects or re-upload into a reviewed
new authenticated project; no implicit ownership transfer. HTTP clients must
create/login to a session, retain cookies and send `X-CSRF-Token` on mutations.
Secure cookies require `DATAGENOME_HTTPS=1` with HTTPS; loopback HTTP development
uses HttpOnly/SameSite strict cookies without Secure. See docs/security.md.
