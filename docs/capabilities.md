# Capability inventory after Phase 7.1 (0.4)

| State | Capability |
|---|---|
| Implemented and regression verified | CSV ingestion/profiling, fingerprints, diagnostics, immutable split manifests, group/chronological partition separation |
| Implemented and regression verified | Training-fold univariate heuristic scoring on supported random/group data; exact target agreement and configured split violations retain separate evidence classes |
| Implemented and regression verified | Out-of-fold label auditing, five valuation methods, logistic influence approximation, failure slices, fairness measurements and drift diagnostics with existing documented limits |
| Implemented and regression verified | Immutable logical dataset versions, safe reviewed corrections/exclusions, training guards, reconstruction, comparison and export |
| Implemented in 7.1 | Training-only declarative numeric/categorical imputation, standard/robust scaling, selected features and bounded one-hot encoding; schema/digest checks and unknown-category handling |
| Implemented in 7.1 | Deterministic structural candidate generation, compatible combinations, conflict rejection, review-first search, bounded evaluations and two-objective nondominance |
| Implemented in 7.1 | Persistent queued analysis and experiment jobs, active experiment deduplication, fit/engine-boundary cancellation, restart interruption recovery, one worker |
| Implemented in 7.1 | Argon2id local accounts, revocable sessions, ownership checks, isolated expiring guests, lifecycle deletion and configurable result retention |
| Implemented in 7.1 | Auth-aware OpenAPI, frontend contract, computed summary tables/series, JSON/CSV/Markdown exports |
| Implemented with scientific limits | Paired independent/group/temporal bootstrap for validation accuracy, balanced accuracy and macro F1; minimum units/class-support gates |
| Experimental | Health weights, priority rules, logistic influence, heuristic label/proxy findings, approximate percentile intervals |
| Partial | Pareto search uses balanced accuracy/macro F1; log loss, cost and removal counts are measured but not configurable search objectives; subgroup/worst-group/disparity uncertainty unavailable |
| Partial | Reports retrieve project/version/experiment sections through related endpoints rather than a single fully joined dashboard document; Markdown/CSV remain summary exports |
| Partial | Occupancy frozen replication scores baseline/random removal; HAR post-run cross-seed overlap invalidated independence; dependent-data selection policies were ineligible |
| Unsupported and deferred | Chronological univariate scoring, horizon/availability purging, predictive proxy verification and automatic label inference |
| Unsupported | Guest/account merging, sharing, internet-facing production certification, encryption at rest, email recovery, multi-process workers |

The frontend workflow gate concerns the tested **local application**. Unsupported
research algorithms do not receive fabricated scores or implicit random-CV fallbacks.
Earlier engine-specific guides remain authoritative for their estimator assumptions.
See [phase audit](phase-7.1.md), [security](security.md),
[frontend contract](frontend-integration.md), and [platform architecture](platform.md).
