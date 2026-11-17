# Phase 1 methodology and interfaces

## Architecture

The CSV parser creates an immutable table of strings. The CLI and local HTTP API pass it
to the same analysis entry point. The fingerprint, split, descriptive intelligence,
leakage, anomaly, modeling, and experiment modules can also be used directly from Python.
Phase 0 `profile` retains its original response shape. Phase 1 operations return JSON
with `schema_version`, `operation`, `identity`, execution time, and the sections calculated
by that operation. `diagnose` includes profiling, advanced intelligence and anomalies.
Supply a split manifest and target to add leakage findings to that report.

## Dataset and split identity

Source SHA-256 covers the input bytes. Canonical SHA-256 combines hashes of the ordered
header and each ordered record using fixed-length binary digests. Each header/record
hash uses compact UTF-8 JSON. A BOM, CSV quoting and record terminator changes are
normalized by parsing. Cell whitespace, Unicode code points, embedded newlines, column
order and row order are preserved. Blank physical records are ignored. Schema identity
covers ordered header strings. Dataset version identity includes canonical content,
target/split configuration and optional parent ID. The identity timestamp is the UTC
time of metadata creation. Source-file creation time is unavailable for API uploads.

Record IDs are one-based positions within identical canonical content. Manifests
record the dataset hash, split settings, partition IDs and a split fingerprint.
Their hashes detect accidental changes. They are unsigned and provide no attribution.
Partitions must be nonempty, disjoint, and together cover all rows. Stratification
requires at least three records per class. Groups and tied timestamps are indivisible.
Group and chronological ratios are approximate counts of groups or timestamp buckets.
Chronological timestamps use ISO 8601 and default to UTC when no offset is supplied.

## CLI

```powershell
python -m datagenome diagnose data.csv --target label
python -m datagenome detect-anomalies data.csv --iqr-multiplier 2 --max-anomaly-rows 1200
python -m datagenome split data.csv --target label --strategy stratified --seed 42 --output split.json
python -m datagenome detect-leakage data.csv --target label --manifest split.json
python -m datagenome train data.csv --target label --manifest split.json --model logistic-regression
python -m datagenome experiment data.csv --target label --manifest split.json --intervention remove-duplicates
python -m datagenome evaluate data.csv --target label --manifest split.json
```

Use `--strategy group --group customer` for group isolation or
`--strategy chronological --time event_time` for strict time order. Supply
`--audit-group`, `--audit-time`, `--cutoff`, and `--unavailable` to audit constraints
independently of split generation. Use `--constant-feature`, `--suspected-feature`,
`--exclude-record`, or `--imputation` to compare a selected intervention. List options
can be repeated. Commands print JSON unless `--output` is set. Data and I/O errors exit
with code 2. `evaluate` explicitly scores the test set. Run it once after selecting
the model and intervention policy. Repeat the selected intervention flags with
`evaluate` to fit that configuration for final scoring. Experiments themselves score validation only.

## Local HTTP API

Start with `python -m uvicorn datagenome.api:app --host 127.0.0.1`. Open
`http://127.0.0.1:8000/docs` for the generated OpenAPI contract. POST routes take
a raw UTF-8 CSV body with `Content-Type: text/csv` and a `filename` query parameter.

| Route under `/api/v1` | Purpose |
|---|---|
| `datasets/profile` | Phase 0 profile |
| `datasets/diagnose` | Advanced profile and anomaly scores |
| `datasets/anomalies` | Anomaly detector results |
| `datasets/leakage` | Leakage audit |
| `datasets/split` | Generate a split manifest |
| `models/train` | Train and score train and validation |
| `models/evaluate` | Evaluate a configured baseline, including test |
| `experiments/compare` | Compare an explicit validation intervention |

Target is required for leakage, modeling and experiments. The API rebuilds the split
from the query strategy and seed. The CLI can reuse a saved manifest. Use
`DATAGENOME_MAX_BYTES`, `DATAGENOME_MAX_ROWS`, or `DATAGENOME_MAX_COLUMNS` to
configure upload limits. Defaults are 5 MiB, 20,000 records, and 128 columns. The API
accepts one analytical request at a time in one process. It returns structured 413,
415, 422 and 503 errors for size, media, validation and availability failures.
The service is designed for local development and has no authentication layer.

## Evidence and limits

- Missingness means blank or whitespace-only tokens. Row and column counts are exact.
  Co-occurrence uses the top 100 observed patterns. Range validation requires explicit
  supplied bounds through the Python API. Categories and rare lists are capped at 100.
- Exact matches use parsed cell equality. Near matches use one-cell Hamming distance
  among neighbors in forward and reverse lexicographic order, bounded by a candidate
  budget. Sorting can miss pairs. Natural repeats can trigger an exact overlap signal.
- IQR and modified Z-score use per-feature evidence. Modified Z-score uses median
  absolute deviation and reports zero-spread or insufficient observations. Isolation
  Forest and Local Outlier Factor use bounded numeric data with median fill. Ranking
  uses detector agreement. Outliers warrant review and remain in the source rows.
- Cross-split repeats, declared group/time overlap and explicitly unavailable features
  are reported as confirmed violations of the configured audit criteria. Target copies
  and repeated one-to-one label encodings give strong statistical evidence. Binary
  point-biserial correlation, low-cardinality Cramér's V and near-duplicate signals are
  heuristics. Small or single-class paired samples give insufficient evidence. Event
  semantics and arbitrary retrospective preprocessing leakage require external
  information. Leakage findings are capped at 100 displayed record IDs per finding.
- Baselines infer feature types on training records, then fit imputation, scaling and
  capped category encoding in an sklearn Pipeline. Categorical values unseen during
  fit are ignored by the encoder. Numeric values outside ±10¹² are clipped. The target
  never enters the feature matrix. The model API has no serialized estimator input. Tree depth and forest size are
  configurable within fixed local bounds.
- Balanced accuracy is macro recall over classes present in evaluation. Overall
  precision, recall and F1 are macro averages of defined per-class values. Binary
  AUC and average precision use the lexicographically last training class as positive.
  Multiclass AUC is macro one-vs-rest. Undefined metrics return null with reasons.
- Comparisons fit two independent pipelines and hold model settings and validation
  rows fixed. A confirmed violation returns a compromised result without comparison
  scores. A new split needs explicit generation. Thresholds and benchmark outcomes
  depend on dataset design and do not establish causality or generalization.

Primary algorithm references include Liu, Ting and Zhou for Isolation Forest and
Breunig et al. for LOF. [Isolation Forest](https://ieeexplore.ieee.org/abstract/document/4781136),
[LOF](https://doi.org/10.1145/342009.335388).

## Benchmark

Run `python benchmarks/synthetic.py --seeds 104 221 --output benchmark.json`. Add
`--datasets synthetic-output` to export the 15 scenarios per seed with split and
injection metadata. The runner compares row flags with injected masks for anomalies,
missingness and exact overlap. Target-agreement quality is assessed at feature level.
The clean and legitimate-predictor fixtures measure false-positive behavior for
target agreement, with the latter intentionally producing a predictive-strength
heuristic. Measurements do not characterize real-world detector performance.

Resource measurements time intelligence plus leakage checks at 240, 1,000 and 4,000
rows with three features. Peak memory comes from Python tracemalloc and excludes
native allocations, interpreter RSS, fixture generation and model fitting. Runs are
single trials. The local verification environment used Python 3.11, scikit-learn
1.6.1 and NumPy 2.2.6 on Windows. The newer 1.9.1 wheel's tree/neighbor native import
was blocked by this machine's Application Control policy.

## Roadmap

Add operator-defined schemas and wider detector validation on public tabular datasets.
Extend supervised leakage evidence with split-safe univariate evaluation, repeated
seeds, and intervention uncertainty estimates. Dataset valuation, attribution and
the frontend remain planned.
