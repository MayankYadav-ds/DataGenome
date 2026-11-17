# Group, chronological, fairness and drift diagnostics

```powershell
python -m datagenome audit-fairness data.csv --target label --sensitive-column cohort
python -m datagenome detect-proxies data.csv --target label --sensitive-column cohort
python -m datagenome fairness-comparison data.csv --target label --sensitive-column cohort --exclude-record 12
python -m datagenome.drift reference.csv later.csv --target label
python -m datagenome.confirmation freeze data.csv --target label --protocol study.protocol.json
python -m datagenome.confirmation score data.csv --protocol study.protocol.json
python benchmarks/fairness_drift.py --output phase6.report.json
```

The local REST routes `/api/v1/datasets/fairness`, `/api/v1/datasets/proxies`, and
`/api/v1/experiments/fairness-comparison` accept raw CSV and repeatable
`sensitive_column` query parameters. The drift route `/api/v1/datasets/drift`
accepts JSON with `reference_csv` and `comparison_csv` strings and optional
`target`, `iid`, and `privacy_mode`. Both CSVs and the combined request have
size limits. Frozen slice protocols are exposed through the local Python SDK and
CLI. The REST API has no filesystem access to protocols. Fixed-model performance
drift is available through the Python SDK.

## Evaluation isolation

Group and chronological manifests validate group disjointness and strict timestamp
ordering across train, validation and test. Configured group and timestamp
metadata are excluded from baseline, valuation, label audit, slice and investigator
predictors. Group-aware inner folds keep same-group and exact feature duplicates
together, including transitive relationships. Infeasible folds return insufficient
evidence. Chronological label audits use strictly earlier records, support a gap
and optional rolling cutoff through `LabelAuditConfig`, and count unscored
labeled rows separately. ISO timestamps are normalized to UTC, with UTC assumed
for naive values. Tied times stay together. Chronological univariate prediction
scoring remains unsupported.

When supplied to the Python leakage SDK, timestamp-column availability mappings
identify records where a feature was recorded after prediction time. Their
absence leaves availability unverified. A historical gap separates timestamps.
It does not prove overlapping target horizons were purged.

## Fairness and uncertainty

Supply audit attributes explicitly. The auditor excludes them from fitting and
reports on binary validation predictions. The selected positive label defaults
to the lexicographically last training label. Groups need minimum support and
minimum observed positive and negative counts. Up to three attributes and 256
groups per intersection are supported. Undefined rates carry a reason. ECE
uses ten equal-width bins. Detailed reports give representation and descriptive
missingness and numeric summaries for eligible groups. Summary and redacted
modes omit names, labels, row IDs and the split envelope. Context can still
identify a group. Use a local artifact suffix such as `.report.json`.

Demographic parity difference is the maximum selection-rate gap and ratio is
minimum divided by maximum, when defined. Equal opportunity is the maximum TPR
gap and equalized odds difference is the maximum of the TPR and FPR gaps.
There is no fixed reference group. Measures can disagree and do not establish
unfair treatment. Optional SDK Wilson intervals are for supported proportions
when IID rows are explicitly asserted, and are disabled for group or time
manifests. These are not significance tests for disparities.
[Hardt, Price and Srebro](https://arxiv.org/abs/1610.02413),
[Fairlearn metric conventions](https://fairlearn.org/main/user_guide/assessment/common_fairness_metrics.html).
Fairlearn is a documentation reference and is not a runtime dependency.

The controlled fairness comparison applies only explicitly selected training
exclusions and holds validation rows fixed. It refuses removals that violate
retained class or intersection support. It reports accuracy and subgroup
changes separately. This path is exploratory. Frozen removal evaluates matched
arms independently under group or chronological manifests, currently with class
recall but without sensitive subgroup scoreboards. Training weights and manual
label correction remain unavailable.

## Proxies and drift

Proxy screening computes mutual information divided by sensitive-attribute
entropy on paired training rows. Numeric features use training quintiles;
categorical features pool values after the 31 most frequent. The descriptive
review threshold is 0.30. Legitimate associations can exceed it. This method
does not estimate causal proxy use or fit a sensitive-attribute predictor.

Numeric drift reports a KS effect, scaled Wasserstein distance, robust
quantiles, PSI and Jensen–Shannon divergence using reference decile edges with
outer bins and 0.5 pseudocounts. Constant reference features get less/equal/greater
bins. Categorical divergence uses base-2 JSD and reports new and disappearing
categories. Chi-square p-values are withheld if any expected cell is below five.
Blank-cell differences are separate. Screening thresholds are 0.20 for KS,
0.10 for JSD and 0.10 for absolute missingness change. Joint drift uses biased
RBF MMD on pooled standardized complete cases, with a pooled median squared
distance bandwidth and bounded samples. Permutation inference is optional.
[Maximum Mean Discrepancy](https://www.jmlr.org/papers/v13/gretton12a.html).

Enable IID tests only when exchangeability is justified. Holm adjusts available
p-values across the comparison. Effect alerts are independent of p-values.
Dependent-group bootstraps and temporal block inference remain unavailable.
Observed label frequencies are distinct from performance changes. The performance
SDK fits one model on reference training and scores reference validation and a
compatible labeled comparison. It excludes configured audit metadata from fitting
and returns fixed-model changes including class recall in detailed mode. Neither
covariate nor performance change establishes concept drift.

## Frozen slice confirmation

Freeze validation slice definitions, model, support and gap criteria before
scoring. Confirmation shares Phase 5's local ledger with frozen removal and
checks exact feature overlap against development data. It reports absent and
undersupported slices. With IID explicitly asserted it tests elevated slice
errors against the complement using one-sided Fisher tests and Holm adjustment.
Otherwise replication means a descriptive threshold was reached and carries
no significance claim. See [ledger limits](independent.md).

## Capability and benchmark scope

Phase 5 regression tests cover fingerprints, manifests, label audits, leakage,
valuation, independent claims, experimental logistic influence, investigation,
and privacy summaries. Influence remains experimental and group/time label
audits now have constrained folds. Phase 6's two-seed suite covers independent
unchanged controls, effect sizes, numeric/categorical/missingness and dependence
shifts, label and conditional outcome changes, representation, proxy and
legitimate associations, subgroup performance and intersectional screening,
metadata contamination, low support, frozen slice replication and frozen
removal. It uses synthetic settings. Public fairness/drift replication,
group/block uncertainty, predictive proxy verification and independent
fairness-specific improvement evidence remain open.
