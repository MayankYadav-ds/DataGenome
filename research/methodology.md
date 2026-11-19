# Mathematical methodology

The [source audit](scientific-audit.md) supplies formulations, assumptions, costs,
numerical guards and existing verification evidence for every implemented family.
The [frozen protocol](../benchmarks/protocols/phase9-v1.json) supplies all executed
settings; [individual trials](../benchmarks/results/phase9/summary.md) retain actual
outcomes rather than a hand-entered scoreboard.

The task is classification. Let D_tr, D_val and D_final be disjoint indexed
partitions. Detector model/preprocessing fitting uses D_tr and its permitted inner
folds. Valuation uses D_val as its utility set. Intervention rules are fixed before
final evaluation and all eligible arms use matching final rows, model family,
hyperparameters and seed. No final metric selects an arm. The benchmark runner
does not change user datasets or application workspaces.

## Detection evaluation

Corruption generators return a new immutable Dataset and a separate changed-row
mask. Only Dataset enters each detector; masks enter metric calculation and the
explicit oracle correction control. Reported precision/recall/F1 are at existing
fixed detector thresholds. AP ranks candidate gaps or baseline scores; k equals the
known number of injected corruptions for precision/recall at k, making this an
evaluation convention rather than a deployable unknown-noise threshold. Random
scores flag at .9; low-probability/disagreement at .5; neighborhood inconsistency
at .6. Clean controls have undefined AP/recall and explicit FPR.

OOF logistic controls use connected exact-vector groups and fold-fitted transforms.
Neighborhood consistency uses five other numeric training observations and fixed
train scaling; it is a different model, not a Confident Learning implementation.
Class-dependent noise concentrates on the first class; feature-dependent noise
concentrates on the largest first-feature values. Zero-noise controls repeat for
each noise family and must not be counted as independent replicates.

Leakage fixtures have declared target copies/encodings, cross-split duplicates,
group/time overlap and clean/legitimate predictor/high-cardinality controls. We
report scenario detection and alert counts separately by classification, without
converting heterogeneous findings into a misleading pooled precision score.
Chronological tree scoring is expanding-window, strictly earlier inner training;
evaluation coverage excludes the initial history block. It is unavailable when
simultaneous group/time isolation or unavailable label horizons cannot be verified.

## Valuation and influence

Exact six-player games permit permutation-definition reference calculation and
full coalition enumeration. Model utility includes the documented empty/single
coalition convention and fold-local coalition preprocessing. MC budgets are 8,
32 and 128 permutations, with caching and at most 256 evaluations. Only MC error
against the same exact Shapley game is approximation error; correlations of LOO,
Banzhaf and fixed-transform KNN games describe agreement, not correctness.

Influence validation differentiates the implemented mean-loss regularized objective
using central differences h=1e-5. Prespecified derivative tolerance is 1e-5, allowing
finite-difference roundoff; solver tolerance is 1e-8. Forty-row fixed-preprocessing
deletions provide actual retraining comparisons. Rank/sign/absolute error are
reported even when damping or influential rows degrade the approximation. No
acceptance threshold for scientific superiority or universal rank quality exists.

## Fairness, drift and health

Independent confusion-count fixtures check undefined denominators explicitly.
Synthetic supplied audit groups have no demographic interpretation. Association
screens do not demonstrate discriminatory use. Unsupported subgroup dependence
intervals remain unavailable.

Drift compares two independently sampled null windows, not an identical copied
window. It distinguishes effect-screen alerts from formal IID tests; Holm correction
includes available univariate and MMD tests jointly. The null sample is too small
to establish calibrated population false-positive control. Conditional label-rule
changes can occur with unchanged covariate marginals; no concept-drift conclusion
is inferred from covariates alone.

Health is an experimental multidimensional burden summary. Coverage, unassessed
components and critical integrity findings accompany the legacy aggregate; changing
weights is a sensitivity analysis, not evidence of accuracy prediction.

## Uncertainty and interpretation

The final study uses paired percentile bootstrap accuracy/balanced-accuracy/macro-F1
differences, 199 resamples, fixed class vocabulary and support gates. IID rows are
an explicit, unverified assumption for Digits because writer IDs are absent.
Intervals are conditional descriptive uncertainty, not proof of writer-independent
generalization. Multiple arm intervals are not simultaneous family-wise intervals.
No significance-based arm selection or cross-arm superiority claim is made.

Means, medians and standard deviations across seeds are descriptive. Seeds sharing
a dataset/development pool are not independent real-world domains. All eligible
arms, zero changes, degradation and unavailable cases remain in artifacts. No
minimum improvement is required and no statistical power guarantee is claimed.
