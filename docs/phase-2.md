# Phase 2 public-dataset validation

Run from the repository root after installing DataGenome.

```powershell
python benchmarks/public.py --output public-benchmark.json
```

The script loads two datasets bundled with scikit-learn and requires no download.
Breast Cancer Wisconsin (Diagnostic) provides a binary case with 569 rows and 30
features. Wine provides a three-class case with 178 rows and 13 features.
[UCI diagnostic dataset](https://archive.ics.uci.edu/dataset/17/breast+cancer+wisconsin+diagnostic),
[UCI wine dataset](https://archive.ics.uci.edu/dataset/109/wine),
[scikit-learn bundled datasets](https://scikit-learn.org/stable/datasets/toy_dataset.html).

## Leakage threshold sensitivity

Each of five prespecified stratified split seeds audits the original data and an
injected counterpart containing a target copy and a one-to-one string encoding.
Only the injected columns have known positive provenance. Signals on original
features are reported separately. Association at a high threshold remains
heuristic evidence. The sweep uses 0.70, 0.80, 0.90, and 0.95. The binary
point-biserial check does not apply to Wine. Exact copy and encoding detectors
remain independent of the association threshold.

Use `--association-threshold` on the CLI or `association_threshold` in the HTTP
query to inspect another setting. The default remains 0.90.

## Paired held-out experiment

A fixed, label-independent mask blanks roughly one quarter of the cells in the
first three features. Both arms use the same masked data, partition IDs and
logistic-regression configuration. Median and mean imputers fit on their own
training partitions. The comparison is prespecified and both arms are scored on
the same held-out rows in each repeat. Confirmed contamination causes a split to
be skipped and reported with its finding IDs.

The JSON preserves per-split validation and test deltas for accuracy, balanced
accuracy and macro F1. A positive delta favors mean imputation. Rows can recur
across repeated splits. The observed ranges describe variation across splits
and should not be interpreted as confidence intervals. Two small datasets and
one injected missingness mechanism provide limited evidence about other settings.
