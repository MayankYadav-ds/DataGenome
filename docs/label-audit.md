# Training label audit

```powershell
python -m datagenome audit-labels data.csv --target label --strategy stratified --output labels.json
python -m datagenome experiment data.csv --target label --strategy stratified --exclude-record 37
python benchmarks/labels.py --output label-benchmark.json
```

The exclusion command illustrates the syntax. Choose record IDs only after reviewing
the audit and keeping the same dataset and split settings. For a saved manifest,
pass the same `--manifest` to both commands. The local API accepts raw CSV at
`POST /api/v1/datasets/label-audit?filename=data.csv&target=label`. The Python surface
is `datagenome.label_audit.audit_labels` with optional `LabelAuditConfig`.

## Method

The audit fits logistic regression on inner folds within the manifest's training
partition. Exact parsed feature vectors are kept in a single fold. Each fit learns
feature typing, imputation, scaling, and categorical encoding from its own fit rows.
Validation and test rows do not contribute to the ranking. Blank training labels
are omitted. Each candidate includes the one-based record ID, fold, observed label,
model-preferred label and the probability gap. Defaults require an alternative
probability of 0.60 and a gap of 0.30. The probabilities are uncalibrated.

This model-disagreement heuristic is related to out-of-sample label-quality ranking.
Confident Learning also estimates a latent label-noise joint distribution, which this
audit does not implement. Run the separate leakage audit before interpreting the
scores. Ambiguous examples, minority groups, and model misspecification can all
produce disagreement. Review the underlying examples before using exclusions.
[Confident Learning](https://arxiv.org/abs/1911.00068).

The audit supports up to 5,000 training rows, 128 features, 20 classes and five folds.
It reports insufficient evidence when the grouped split cannot fit every class.
Group and chronological manifests are unsupported because the inner folds cannot
enforce their constraints. Near duplicates can still cross inner folds. Reports
contain label values and record locations and should be handled as dataset artifacts.

## Synthetic benchmark

Five seeds generate 600 examples each from three overlapping classes. The benchmark
flips 10% of training labels and keeps validation and test labels intact. On Windows
with scikit-learn 1.6.1, it detected 132 of 180 planted flips, with 11 extra flags.
Pooled precision was 92.3% and recall was 73.3%. The five clean controls generated
22 flags. Explicitly dropping all flagged training records changed mean validation
accuracy by +0.33 percentage points, with individual changes from -0.83 to +0.83
points. The experiment did not score the held-out test. These results describe one
synthetic data and noise mechanism.

## Capability inventory

Implemented before this milestone were CSV ingestion and profiling, fingerprints and
version identifiers, duplicate and bounded near-duplicate checks, missingness and
imbalance analysis, four anomaly detectors, split management, leakage diagnostics,
classification baselines and metrics, controlled training interventions, local CLI
and REST interfaces, JSON output, and synthetic and bundled public-data benchmarks.
This milestone adds a training-label review queue and a synthetic impact comparison.

An overall quality score, persisted dataset-version storage, drift and concept drift,
fairness and hidden subgroup evaluation, general-purpose causal attribution, a full recommendation system, interactive visualizations and a web
application remain planned.

Later checkpoints added [record valuation](valuation.md) and a [bounded prediction investigator](investigator.md).
