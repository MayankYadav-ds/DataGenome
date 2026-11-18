# Phase 7.1 audit, methodology and verification

Starting checkpoint independently checked: main and origin/main both
`890a9041eb995a6b84539b918b1b137b59e52475`, version 0.3.0, clean tree, 75 tests,
previous hosted Windows CI successful. Public visibility and sole GitHub collaborator
MayankYadav-ds (admin) were verified using read-only GitHub API calls. No repository
permissions, source datasets, unrelated repositories or remote history were changed.
This milestone prepares experimental 0.4.0, not a production/stable certification.

## Audit priorities and scope

| Priority | Actual finding | Resolution/state |
|---|---|---|
| P0 | Project scope alone did not authenticate HTTP users | Added revocable sessions, CSRF/origin checks and ownership at central Store lookups plus job lookups; tested real cross-owner paths |
| P0 | Legacy projects could be ambiguously adopted | Schema 2 intentionally leaves them unowned over HTTP; trusted SDK remains available |
| P1 | No functional isolated guest lifecycle | Demo/upload/analysis/experiment/report/delete workflow and expiry cleanup added |
| P1 | Experiment HTTP requests blocked until training completed | Persisted queued metadata/jobs atomically; one worker; cancellation/recovery/deduplication added |
| P1 | Dataset/project/report deletion missing | Transactional lifecycle operations, busy rejection, conservative derived-artifact clearing and optional result retention |
| P1 | Learned parameters were not reconstructible | Declarative bounded persisted preprocessing, source version/split association, digest/schema validation and restoration tests |
| P1 | Frontend contract omitted authentication and lifecycle | Auth-aware OpenAPI plus integration and security guides; capability discovery reflects unsupported states |
| P2 | Search required every candidate manually | Bounded constants/exact-training-duplicate candidates and compatible combination; conflicts explicit; remaining objectives deferred |
| P2 | Dependence intervals were detached from experiments | Integrated three paired validation metrics with explicit effective-unit/class-support checks |
| P2 | Reporting lacked chart-ready summaries | Added computed health/recommendation series, tables and execution metadata; full project/version joins remain separate |
| P2 | No independent dependent-data replication | Occupancy final partition eligible; post-run HAR cross-seed overlap invalidated independent status; no rescore |
| P3 | Chronological univariate, label-horizon metadata and predictive proxy models absent | Explicitly deferred/unsupported; existing chronological split checks remain active; no random-CV substitution |
| P3 | Broader worst-group/fairness uncertainty and sensitive-subgroup scoreboards | Deferred until subgroup policy, minimum units and dependence treatment are validated |

All prior engines were reviewed for how they connect to orchestration, versions,
reports and persistence. Existing common ingestion, numeric handling, folds and
classification pipelines are reused. Learned preprocessing is a declarative dataset
artifact, not a second executable model loader; estimator preprocessing still fits
inside estimator training/folds. No pickle loading was introduced. Existing label,
valuation, influence, investigator, fairness and drift limitations remain in their
guides. Unknown engines preserve explicit unsupported states. Recommendations are
review candidates tied to actual findings, never automatic data edits.

## Planner and persistence

Search inspects training-only constants and exact duplicate rows, considers their
combination, and caps candidates at four. IDs derive deterministically from plans.
Rejected derivations retain reason codes. Compatibility rejects conflicting label
replacements and remove-versus-correct/review conflicts; merges preserve stricter
support/removal limits. Authorized evaluation records baseline, requested and
eligible matched-random arms, including negative outcomes. Fit limits include
controls. Two-objective nondominance covers balanced accuracy and macro F1, without
claiming superiority. Log loss, per-class recall, rows/features removed and measured
cost are reported; configurable multi-objective optimization and automatic
label-audit/valuation candidate selection remain partial.

Preprocessing parameters contain ordered feature specifications, version ID, split
fingerprint, training stable IDs and output width. Numeric inference and imputation
use training data only; numeric values are clipped to ±1e12. Standard scaling uses
population standard deviation; robust scaling uses median and inclusive IQR; near
constant scales fall back to one. Missing categorical values use the most frequent
training category (lexical tie break); unknown categories encode all zero. Limits
are 32 selected features, 32 categories each, encoded width 256, 5,000 records.
Restoration is exact for the tested finite fixtures; floating results otherwise
should be compared with tolerance 1e-12. Digests detect accidental corruption, not
malicious modification by a trusted local database editor. No executable artifacts.

The SQLite queue has one application worker, eight active requests and transactional
claiming. Analysis progress counts engines; experiment progress counts actual
completed fits. Running cancellation is cooperative between fits, not a native
hard kill. Time budgets are checked at these boundaries. Restart marks running jobs
interrupted, preserves queued jobs and records interrupted experiment outcomes.
Concurrent 24-artifact writes across four threads pass without lost/duplicate IDs.
This is not a multi-process scheduler or a production database load test.

## Uncertainty assumptions

Experiments keep outer test data unscored. Paired validation predictions are used
transiently for bootstrap comparisons; only aggregate results are persisted in
experiment results. A fixed configuration (99 samples, seed 42, minimum eight units,
temporal block length five timestamps) is recorded in each estimated metric. The
SDK exposes bounded configurations (39–999 samples). Group sampling resamples whole
groups; temporal sampling uses overlapping blocks of consecutive timestamp units;
independent sampling resamples records. Combined group/time dependence is unsupported.
Temporal input order and appropriate block length remain caller/scientific duties.
Accuracy, balanced accuracy and macro F1 use fixed observed class vocabulary; missing
class support in too many bootstrap replicates is explicit, with no manufactured
interval. Subgroup recall, worst-group recall and fairness disparity intervals are
not yet integrated. Repeated partitions are not treated as independent evidence.
Zero-width intervals with identical outcomes are not proof of equivalence. A positive
observed delta alone is not a statistically meaningful improvement claim.

## Public replication and synthetic benchmarks

UCI provenance and CC BY 4.0 licenses were rechecked at the
[HAR source](https://archive.ics.uci.edu/dataset/240/human+activity+recognition+using+smartphones)
and [Occupancy source](https://archive.ics.uci.edu/dataset/357/occupancy+detection).
Attribution: Reyes-Ortiz, Anguita, Ghio, Oneto and Parra (HAR, 2013);
Candanedo and Feldheim (Occupancy, 2016). Archives stay outside Git. HAR uses actual
subject IDs, first six documented acceleration features and every sixth source row.
Occupancy uses actual date fields, five environmental features and every tenth
source row; repeated timestamps are deduplicated and conflicts excluded. Neither
source supplies independently verified label-availability/horizon metadata.

`benchmarks/dependent_replication.py freeze` writes the model, manifest, archive/data
hashes, 5% random-removal IDs, metrics, absence of sensitive subgroups and resampling
policy **before** score. `score` checks identity and creates an exclusive consumed
ledger before fitting; reuse is rejected even after failure. It targets seed-19 reserved test partitions. A post-run cross-seed audit found
57 HAR test records had previously appeared in seed-47 validation. Therefore the
HAR result below is **descriptive only and ineligible as independent replication**.
The script now checks the union of prior seed-19/47 validation identities and blocks
that HAR evaluation before fitting. No replacement HAR outcome was scored after
this discovery. Occupancy's fixed chronological test did not overlap prior validation
and retains independent status. The original local consumed ledgers are preserved;
the published aggregate records the eligibility correction. Only one frozen policy is scored per dataset;
no iterative optimization followed these results. The local ledger is not adversarial
tamper-proof and does not detect a deliberate duplicate workspace.

| Final partition | Records | Baseline accuracy | Random 5% removal | Interpretation |
|---|---:|---:|---:|---|
| HAR (descriptive, not independent) | 161 | 52.1739% | 53.4161% | 57 prior-validation overlaps; also only three subject units |
| Occupancy | 412 | 99.2718% | 99.2718% | Zero paired change; 34 effective 12-timestamp blocks; no improvement/equivalence claim |

HAR balanced accuracy 51.4973% → 53.1414%, macro F1 .48731 → .50272.
Occupancy balanced accuracy 99.5066% and macro F1 .99067 were unchanged. Low-value
removal, label-audit exclusions and other improvement arms were explicitly ineligible
because a validated dependent-data intervention policy was not frozen. Sensitive
subgroup outcomes are unavailable. Full reproducible public aggregate results and
protocol digests are in `docs/phase-7.1-results.json`.

The deterministic synthetic workflow benchmark used seeds 19 and 47 over six
scenarios. Ten eligible comparisons reconstructed correctly and kept test unscored;
minority exclusion was rejected by class guards twice. Constant removal, missing-data,
label-correction and duplicate fixtures had zero accuracy delta. Harmful predictor
removal reduced validation accuracy by 20 and 75 percentage points. These are tiny
controlled fixtures, not evidence of real-world improvement. Runtime 29.115 seconds;
peak traced Python allocation 9,605,119 bytes; process peak working set 135,270,400
bytes. The categorical valuation fixture explicitly returned unsupported rather
than a fabricated score.

A separate synthetic 60-row HTTP-stack run measured startup .447s, analysis job
.295s, experiment job 1.344s, median project GET .0163s over 20 requests, SQLite
98,304 bytes, peak traced Python allocation 8,999,409 bytes, process working set
157,757,440 bytes and process peak 203,816,960 bytes. TestClient includes the ASGI
HTTP stack but not network transport. Startup includes the Argon2 dummy hash. Tracing
excludes native allocations; process peak includes imports. Single-run timings are
not scalability claims. Runtime measurements were taken before final documentation
and contract metadata changes, with the same computational workflows.

## Verification and remaining work

Verification runs on Windows/Python 3.11 with scikit-learn 1.6.1 because the machine's
Application Control blocks a native module in 1.9.1. OS controls were not bypassed.
An advisory scan with pip-audit 2.10.1 initially found advisories in development pip
22.3 only; upgrading that environment to pip 26.3 yielded no known vulnerabilities
in the scanned environment. This is a point-in-time scan, not a guarantee for every
allowed dependency combination. tomli was rebuilt as its supported pure Python
package because its accelerated wheel was blocked by Application Control. Runtime
Argon2 bindings loaded normally. Core licenses: NumPy/SciPy/scikit-learn BSD family,
threadpoolctl BSD, FastAPI MIT, Uvicorn BSD, Argon2-cffi MIT; bindings include Apache
components. No additional heavyweight frameworks or paid services were added.

Final installed-wheel full suite: **90 passed, zero failures**, including 15 readiness
regressions (62.84 seconds on Windows). Ruff lint/format and strict mypy pass (48
source files). Wheel and source distribution builds pass; all 48 wheel source files
match the reviewed source and the source archive contains test helpers and OpenAPI.
Installed module origin was confirmed inside site-packages, and pip check passes.
Hosted Windows CI status is reported with the release commit.
New regressions cover actual HTTP accounts/guests, credential hashing, revocation,
expiry, cross-owner real datasets/jobs/reports/experiments, CSRF/origin checks,
preview/byte/project limits, deletion/cleanup, legacy migration, declarative
reconstruction and evaluation isolation, concurrent writes, cancellation/recovery,
computed report series and auth-aware schema. No existing assertion was weakened.

The frontend gate targets this tested local application. Research F/G/H remain
unsupported; E, B, I and J have explicitly scoped partial coverage above. Public
hosting, encrypted storage, stronger ACL certification, sharing, password recovery,
full report joins and dependent sensitive-subgroup inference are not certified.
Do not start Phase 8 within this directive. Total expenditure: ₹0.
