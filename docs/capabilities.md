# Capability inventory after Phase 7

| State | Capability |
|---|---|
| Implemented and regression verified | CSV ingestion/profile, fingerprints, bounded diagnostics, manifests, group/chronological separation, label audits, error slices, local CLI and REST |
| Implemented and regression verified | Five valuation methods, frozen independent removal protocol and shared slice-confirmation ledger |
| Implemented and verified in this milestone | SQLite local projects, immutable logical versions, dry runs, explicit training corrections and exclusions, protected provenance, reconstruction and export |
| Implemented and verified in this milestone | Engine orchestration, partial failures, exact-configuration caches, engine progress, health coverage, deterministic recommendations with conflicts |
| Implemented and verified in this milestone | Explicit plan review, bounded authorized retraining, random removal controls, per-class outcomes, two-objective nondominance |
| Implemented with limited deployment scope | One-process queued analysis jobs, cancellation between engines, interruption recovery and local project artifact scoping |
| Experimental | Health weights, priority rules, influence derivatives, heuristic label and proxy findings, resampling intervals |
| Partially implemented | Group/temporal uncertainty supports paired bounded outcomes; it is not wired into every model/subgroup report |
| Partially implemented | JSON contains full engine findings; Markdown and CSV support health/status summaries |
| Partially implemented | Background queue runs diagnostics; experiments run synchronously with fit limits |
| Partially implemented | Version history and reconstruction support a prior-version restore by selection; no mutable active-version pointer |
| Unsupported | Chronological univariate scoring, target-horizon purging, group-dependent fairness inference beyond the paired SDK |
| Unsupported | Learned persistent dataset transformations, arbitrary new label classes, automatic inferred relabeling |
| Planned | Predictive proxy verification, independent sensitive-subgroup intervention scoreboards, automatic compatible-plan search, PDF reports, authenticated multi-user service |
| Not blocked | UCI grouped and temporal acquisition succeeded; no paid infrastructure was used |

The complete Phase 7 definition remains partial because the listed unsupported
scientific workflows and broader automatic search are not available. Phase 8
can use the local contracts after reviewing these limits. A frontend does not
remove the need for independent model and subgroup validation.

Earlier milestone methods and scope are documented in the corresponding guides.
See [platform guide](platform.md), [fairness and drift](fairness-drift.md),
[influence](influence.md), [independent evaluation](independent.md), and
[valuation](valuation.md).
