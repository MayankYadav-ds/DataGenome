# Local improvement workspace

Version 0.3 introduces one local SQLite store connecting diagnostic orchestration,
immutable logical dataset versions, reviewed transformations, bounded experiments,
analysis jobs and report views. Existing CSV commands and endpoints remain available.

## Reproducible workflow

Use Python 3.11 or later and install `.[api,dev]`. Create a tiny local CSV or use the
existing deterministic demonstration generator. In PowerShell from the repository:

```powershell
python examples/generate_demo.py demo.csv
python -m datagenome.workspace project study
python -m datagenome.workspace register demo.csv --project PROJECT_ID --target label --strategy random
python -m datagenome.workspace diagnose VERSION_ID --project PROJECT_ID
python -m datagenome.workspace recommend VERSION_ID --project PROJECT_ID --privacy detailed
python -m datagenome.workspace preview-intervention VERSION_ID --project PROJECT_ID --plan plan.json
python -m datagenome.workspace apply-intervention VERSION_ID --project PROJECT_ID --plan plan.json --reviewed
python -m datagenome.workspace optimize-data VERSION_ID --project PROJECT_ID --plan plan.json
python -m datagenome.workspace report VERSION_ID --project PROJECT_ID --output study.report.md
```

Copy the returned IDs into later commands. With an imbalanced demo the stratified
split may be infeasible, so this example explicitly requests random splitting.
Use `{"constant_features":["batch"]}` as the demo plan. Optimize defaults to review.
Pass `--reviewed` only after reviewing a concrete plan to run its validation
comparison. Exports open a new file exclusively. To restore, select the earlier
version ID and export it with `workspace export` and `--reviewed`. Version history,
reconstruction, and `compare-versions` operate within the registered dataset lineage.

## Diagnosis, score and recommendations

`orchestration.orchestrate` runs selected engines in a fixed order and preserves
completed results if an optional engine fails. Profile and intelligence run first.
Dataset identity, split, full diagnostic settings, dependency versions and project
scope form each cache key. Successful engine results are cached. Engines return
unsupported or budget status when inputs or requested context are unavailable.
Full reports retain structured progress events and per-engine results. A deadline
is checked between engines and does not interrupt native model fitting.

The health assessment has the following explicit dimensions.

| Component | Default formula on a 0–100 scale | Weight |
|---|---|---|
| Completeness | 100 × (1 − missing cells / cells) | 1 |
| Duplicate burden | 100 × (1 − repeated rows / rows) | 1 |
| Feature variation | 100 × (1 − constant columns / columns) | 1 |
| Label agreement | 100 × (1 − suspected candidates / scored labels) | 1 |
| Evaluation integrity | 0 with a confirmed configured violation, otherwise 100 after audit | 2 |

The aggregate is a weighted average of available components. `health` accepts
custom positive weights through the SDK. Seven dimensions define the coverage
denominator; representation and distribution stability remain unscored. A missing
engine supplies no component. Integrity flags remain a separate critical list
even with a high aggregate. A partial label audit reflects only scored records.
This heuristic burden score is experimental. It is not calibrated to model success
and does not provide a universal fairness assessment.

Recommendations reference an engine and finding ID, define their evidence type,
suggest an investigation, identify conflicts and require review. Ranking uses
severity bases 100/70/40/10 for critical/high/warning/info, plus at most ten points
for affected-record count in tens. This published priority rule is not an expected
utility estimate. Related detectors are not counted as independent confirmation.
For example, model disagreement calls for label review, while low valuation also
warns about minority-class contributions. No recommendation applies a plan.

## Logical versions and transformations

Original registration records source SHA-256, content and schema hashes, target,
manifest, original positional IDs and source name. Every derived version is an
immutable SQLite artifact with parent, plan, content hash, root-stable record IDs,
and protected provenance. The provenance includes original and corrected labels.
It is sensitive. Reconstruction reruns the recorded transformation and checks
content and identity mapping. API metadata omits rows and provenance.

Supported structural transformations are explicit training exclusions, exact
training duplicate removal, training label corrections to the existing class
vocabulary, review/ambiguous annotations, and feature exclusion including verified
training constants. Source files and evaluation labels are preserved. Row removal
is capped at 20%; minimum class and group counts are checked; target and split
metadata are protected; derived manifests are rebuilt and validated. Overlapping
remove-and-correct requests are rejected. Review annotations do not change
training weights or label values.

Engine record positions refer to the current version. Job reports include their
position-to-stable-ID mapping, and recommendation record IDs are mapped to root
stable IDs before publication. Use these stable IDs in transformation plans.
Learned imputation and encoding stay in the train-fitted model pipeline. Persisted,
learned dataset transformations and arbitrary target-schema expansion remain
unsupported.

## Experiments and uncertainty

Review mode validates supplied plans and reports anticipated changes without
persisting versions. Explicit authorization enables a bounded comparison of up
to four supplied plans, at most six fits including baseline and eligible matched
random-removal controls. A random control matches removal count and is rejected
if the same safety guards fail. Removed, corrected and excluded-feature counts
are reported. Fixed validation identities and labels are checked before fitting.
All candidate pipelines fit separately on their training rows. Per-class recall
can worsen despite aggregate gains. Nondominated candidates use balanced accuracy
and macro F1, and do not identify a universally best plan. Model runtime is
reported separately for fitting and evaluation.

The planner does not consume final test scores. Independent testing continues
through the frozen Phase 5 protocol and ledger, whose bypass limitations still
apply. Sensitive-subgroup comparison remains the separate Phase 6 workflow.
SDK `paired_interval` offers paired cluster bootstrap or moving temporal blocks
with 39–999 repetitions and at least eight effective resampling units. Caller
supplies the appropriate dependence unit and chronological order. Temporal
blocks preserve equal-timestamp observations. Block length is prespecified.
Intervals are approximate and depend on representative clusters or stationary
local blocks. Identical paired outcomes can yield zero-width intervals and do
not demonstrate equivalence.

## Persistence, jobs and API

The database schema is version 1. Fresh stores initialize transactionally and
unknown future schemas are rejected. Artifacts are append-only. Request and
result metadata are separate so an interrupted process cannot present a missing
result as completed. Experiments recover with terminal interrupted records.
Job transitions support queued, running, completed, failed, cancelled and
interrupted. The internal schema reserves created, while public submission
atomically queues a job. Cancellation is cooperative between engines and before
result persistence. On startup running jobs become interrupted and queued jobs
resume. There is one worker and at most eight queued/running requests globally.
Progress reports actual completed engines rather than estimated percentages.

Start `python -m uvicorn datagenome.api:app --host 127.0.0.1`. The app creates
`.datagenome/platform.sqlite3` or the server-configured `DATAGENOME_STORE` path.
Use one server process; concurrent server ownership and hard cancellation are
unsupported. The store caps individual artifacts at 16 MB, artifacts per project
at 1,000, and retained jobs per project at 1,000. New JSON requests are capped at
6 MB. Existing analysis limits still apply.

| API route | Purpose |
|---|---|
| GET /api/v1/capabilities | Implemented and unsupported platform capabilities |
| POST /api/v1/projects; GET /api/v1/projects | Local project registration and listing |
| POST /api/v1/datasets | CSV string, target, split settings and project ID |
| GET /api/v1/datasets/{version_id} | Version metadata |
| GET /api/v1/datasets/{version_id}/versions | Paginated history |
| GET /api/v1/datasets/{version_id}/compare/{other_id} | Logical differences |
| GET /api/v1/datasets/{version_id}/export | Explicitly reviewed CSV content |
| POST /api/v1/interventions/preview; /apply | Dry run or reviewed derived version |
| POST /api/v1/analyses | Queue selected diagnostics |
| GET /api/v1/jobs/{job_id}; POST .../cancel | Actual status, progress and cancellation |
| GET /api/v1/analyses/{analysis_id}; .../recommendations | Result views and recommendation review |
| POST /api/v1/experiments; GET .../{experiment_id} | Plan review or authorized comparison and status |
| GET /api/v1/reports/{analysis_id} | JSON, Markdown or engine-status CSV |

Project IDs scope all persisted lookups. They do not authenticate a user.
OpenAPI describes the typed registration, version, job and transformation
contracts. The database contains detailed versions, diagnostic caches and
provenance even when the returned report view is summary. Protect the local
directory accordingly. There is no automatic upload. Summary and redacted report
views omit labels, field names, row IDs and hashes; aggregate values can remain
identifying. Report Markdown provides a human-readable status and health view;
detailed engine evidence is available in JSON. This service needs authentication,
authorization and a broader security review before any multi-user deployment.

## Benchmark interpretation

The synthetic suite runs six fixtures at seeds 19 and 47. Constant exclusion,
the tested missing-value data, and the planted label corrections yielded neutral
validation accuracy changes. Removing the informative feature reduced accuracy
by 20 and 75 percentage points. The minority-erasure plan was rejected in both
runs. Duplicate-removal candidates and matched random controls were neutral.
Reconstruction matched every eligible derived version and all twelve analysis
jobs completed. Tests separately cover failures, cancellation and restart
interruption.

The public acquisition scripts fetch archives from UCI and retain checksums.
UCI lists [Human Activity Recognition](https://archive.ics.uci.edu/dataset/240/human+activity+recognition+using+smartphones)
and [Occupancy Detection](https://archive.ics.uci.edu/dataset/357/occupancy+detection)
under CC BY 4.0. HAR attribution is Reyes-Ortiz, Anguita, Ghio, Oneto and Parra
(2013); Occupancy attribution is Candanedo (2016), with the associated study by
Candanedo and Feldheim. Archive content is local and excluded from Git.

HAR uses 1,718 every-sixth windows, six documented acceleration features,
subject-isolated 50/40/10 splits and two prespecified seeds. Random 5% training
removal changed validation accuracy by 0.00 and +0.55 percentage points.
Subject-bootstrap intervals were approximately [−2.09,+1.91] and [−0.27,+1.39]
percentage points across twelve validation subjects. Occupancy uses 2,058
every-tenth rows ordered by recorded date and a 12-timestamp moving block.
Both runs retained 99.51% validation accuracy after random 5% removal, producing
zero paired changes. Neither public benchmark scores the reserved final partition.
No event times are inferred for HAR. Occupancy uses concurrent environmental
measurements and does not establish forecast-time feature availability.

The final synthetic workflow run took 29.40 seconds with 10.84 MiB peak traced
Python allocations. Windows process working set rose from approximately 101.02
to 121.97 MiB, with a process-wide peak of 126.33 MiB. The working-set high-water
mark includes interpreter and native libraries loaded before the benchmark.
Tracing covers only allocations observed after measurement started.
