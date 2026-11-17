# Model Failure Investigator

```powershell
python -m datagenome investigate data.csv --target label --record-id 42
python -m datagenome investigate data.csv --target label --record-id 42 --exclude-record 9
python -m datagenome analyze-errors data.csv --target label --minimum-support 15 --privacy-mode summary
python benchmarks/investigator.py --output investigator.report.json
```

Choose a one-based record ID in a saved or reproducible validation partition.
The local API accepts raw CSV at `POST /api/v1/models/investigate`,
`POST /api/v1/models/error-slices`, and `POST /api/v1/experiments/interventions`.
Set `filename`, `target`, and, for prediction operations, `record_id` as query
parameters. The intervention route requires an explicit selection. The Python
entry points are `inspect_prediction` and `analyze_errors`.

## Prediction evidence

The investigator trains an internal binary logistic model on numeric features.
Median imputation, centering and scaling use training rows. The specified
validation record supplies its actual class, predicted class, probability,
margin, and correctness. An additive logit reconstruction reports the intercept
and transformed source-feature contributions. It does not rank differently
scaled raw coefficients as importances.

Detailed failure reports include ten nearby training records, label-audit flags,
exact feature matches, candidate global KNN utility values, and experimental
local influence scores. Each serves a different purpose. The evidence graph
uses explicit measured or inferred edges for neighbor relationships,
label suspicion, duplication, global valuation and estimated influence.
Recommendations reference the evidence and ask for manual label verification.
These relationships do not establish causation.

Explicit record, duplicate, or feature removal retrains a derived training model
and compares the selected prediction, validation accuracy, and per-class recall.
Both classes must be retained. The workflow leaves original data intact. Manual
relabeling and alternative investigative imputation are unsupported. The
investigator reserves the final partition. A successful validation correction
does not establish generalization. [Influence objective](influence.md).

## Error slices

The separate scanner uses one exploratory validation partition. It examines
training-defined numeric median splits, frequent categories, missing indicators,
actual classes, and pairwise intersections from at most twelve eligible
feature slices. It enforces minimum support, reports up to 30 slices and shows
base error, absolute and relative rates. It does not perform significance
testing. Multiplicity and overlapping slices can make findings unstable.
[Slice Finder research](https://research.google/pubs/slice-finder-automated-data-slicing-for-model-validation/).

In the two prespecified synthetic runs a shifted subgroup produced errors for all
12 subgroup members, against baseline validation error rates of 36.1% and 38.9%.
The inspected failure remained after the explicit exclusion in both runs.
Overall validation accuracy changed by 0 and +2.78 percentage points. Observed
logit reconstruction error was at most 2.3e-16.

## Privacy and bounds

The detailed report can expose feature names, transformed values, labels,
record IDs and fingerprints. `--privacy-mode redacted` and `summary` both
return the same conservative aggregate view. They omit these fields, slice
definitions, and dataset and split identifiers. Prediction correctness and
aggregate counts or metrics remain sensitive in context. This is not
anonymization. Local output paths stay under caller control. Use the ignored
suffices `.local.csv`, `.private.csv`, `.protocol.json`, and `.report.json`
for local artifacts. Review other filenames before staging.

The investigator allows one validation prediction per request, at most 2,000
rows and 32 features, one explicit intervention comparison, and a Hessian
dimension of at most 33. The slice scanner uses the same input caps and one
fit. Model fitting is limited to one worker. Global valuation uses a separate
bounded KNN request and reports unsupported cases. Keep detailed diagnostics
and frozen receipts on the local filesystem.
