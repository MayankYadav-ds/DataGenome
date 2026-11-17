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

## Training-only univariate predictive evaluation

Opt in with `python -m datagenome detect-leakage data.csv --target label --univariate`
or add `univariate=true` to the local leakage API query. In Python pass
`LeakageConfig(univariate=UnivariateConfig())` to `inspect_leakage`. Import
`UnivariateConfig` from `datagenome.univariate`. The usual leakage result shape
and classifications remain in use. Opt-in results use method `univariate_predictive`.
A result below threshold has classification `no_signal`. Undefined scores are
null and carry a reason.

The detector uses stratified inner folds drawn entirely from the outer training
partition. A depth-five decision tree scores each feature against a majority-class
dummy. Fold-local numeric inference and median imputation handle numeric inputs.
Categorical encoding learns up to 32 categories per fold, treats blanks as their own
category and ignores unknown categories at scoring time. The score is mean fold
balanced accuracy, using equal weight per fold. The defaults require a score of
at least 0.90 and a lift of at least 0.20. Both thresholds are prespecified and
independent of validation and test data.

The default budget is three folds and the first 16 features in CSV order. Configure
two to five folds and up to 32 features with `--univariate-folds` and
`--univariate-max-features`. The score and lift flags are
`--univariate-minimum-score` and `--univariate-minimum-lift`. API fields use
underscores. The detector supports up to 5,000 training records and 20 classes.
Unlabeled training rows are excluded. Group and chronological audits return an
unsupported result for this detector because random stratified folds cannot
enforce those constraints. Ordinary stratified folds can share near-identical
records. Tree depth, feature ordering and category caps can hide real effects.

The public-data benchmark records original feature alerts separately from
injected copy and encoding detections. Its synthetic negative control generates a
predictor before assigning the label, establishing that the feature is legitimately
available. A heuristic alert on that feature illustrates why predictive strength
alone does not establish leakage. Original public features lack independent
provenance labels, so their alerts are counts rather than verified false positives.

On Windows with scikit-learn 1.6.1, the prespecified five-seed run detected all
20 injected columns across both datasets and produced zero alerts on the
original public features. It flagged the legitimate synthetic predictor on all
five splits, with zero confirmed violations on that control. These results
measure the fixtures and the specified settings.
