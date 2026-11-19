# Phase 9 observed evidence

## Leakage

Expected structural/agreement methods detected 15/15 injected scenarios. 3/9 legitimate/control scenarios produced heuristic alerts; 0 produced confirmed split violations. These heterogeneous scenario counts are not pooled feature-level precision.

[Individual trials](../benchmarks/results/phase9/leakage/results.json)

## Label audit

DataGenome AP across nonzero-corruption conditions ranged 0.1623–0.9093. Clean-control false-positive rates ranged 0.0000–0.0333. Random, OOF disagreement, low observed-label probability and neighborhood controls are retained per condition. No natural-label correctness claim.

[Individual trials](../benchmarks/results/phase9/labels/results.json)

## Valuation

Permutation-reference maximum Shapley error: 4.44e-16. MC absolute-error ranges by separate utility/budget: accuracy / mc-shapley-128: 0.0044705–0.015451; accuracy / mc-shapley-32: 0.0084491–0.022338; accuracy / mc-shapley-8: 0.013194–0.042361; negative_log_loss / mc-shapley-128: 0.44607–1.2009; negative_log_loss / mc-shapley-32: 0.72425–1.8987; negative_log_loss / mc-shapley-8: 0.9705–3.7003. Six-player synthetic games only; other methods estimate different quantities. Cross-domain ranking stability remains unestablished.

[Individual trials](../benchmarks/results/phase9/valuation/results.json)

## Influence approximation

135 evaluated configurations; deletion-loss rank correlation ranged 0.9525–1.0000. Maximum finite-difference gradient/Hessian errors: 9.44e-11/3.02e-10. This validates a bounded binary regularized objective, not arbitrary models or causation.

[Individual trials](../benchmarks/results/phase9/influence/results.json)

## Fairness

Independent selection/TPR/FPR count fixtures agree: True. Synthetic audit and planted-proxy screens only; predictive proxy verification and dependence-aware subgroup intervention uncertainty remain NOT RUN.

[Individual trials](../benchmarks/results/phase9/fairness/results.json)

## Drift

0/6 independently sampled null trials had a Holm-adjusted formal rejection; 2/6 had descriptive effect alerts. Conditional outcome changes are not identified from covariate drift alone. Only six null trials: insufficient power to calibrate a population false-positive rate.

[Individual trials](../benchmarks/results/phase9/drift/results.json)

## Independent intervention outcomes

Prespecified record-disjoint Digits blocks: 3. Scored arms: 21; insufficient candidate arms: 3. Relative to baseline, 0 improved, 14 were unchanged and 4 degraded in accuracy. Deltas ranged -0.0169–0.0000. Includes explicit oracle controls; no outcome-based arm selection.

[Individual trials](../benchmarks/results/phase9/interventions/results.json)

## Computational limits

Measured 30 profiling/diagnostic configurations, 100–10,000 rows with 3/16 features. Per-trial runtime ranged 0.270–27.622 s; peak traced Python allocations reached 43.16 MiB. Native allocations and process peak working set are NOT measured. Exponential games are restricted to six players.

[Individual trials](../benchmarks/results/phase9/performance/results.json)
