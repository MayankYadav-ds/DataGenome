# Phase 9 source audit and prespecified scope

Audit checkpoint: 0.5.0 at `7ed7dfb`. Passing software tests establish specific
invariants, not general scientific validity. Complexity below uses n training rows,
m scoring rows, d features, F one model fit, K folds and B resamples/permutations.
All methods remain restricted to their implemented configurations.

| Implementation / mathematical definition | Assumptions and cost | Evidence and remaining gaps |
|---|---|---|
| `profiling`, `intelligence`, `duplicates`: parsed-cell counts, missing share, inclusive quartiles, Pearson correlation, exact equality; near matches use sorted-neighbor Hamming distance | Blank-only missingness; finite numeric parsing; roughly O(nd + nd² + n log n·d), pair/feature budgets | Profile, intelligence and identity tests. Whitespace and alternate numeric encodings can produce distinct keys. Near matching is incomplete; uniqueness is not a semantic identifier. |
| `leakage`, `univariate`: exact target equality/bijection; binary point-biserial association and categorical association; bounded depth-5 tree balanced accuracy versus most-frequent inner-fold baseline | Training-only feature fitting, numeric median/categorical unknown handling; O(Kdn log n), at most 32 features/5 folds/5,000 training rows. Group components merge repeated vectors and supplied groups | Univariate tests perturb outer rows. Exact agreement remains strong statistical evidence; declared split violations remain confirmed violations. New forward historical folds are strictly earlier, exclude time as predictor and report partial scoring coverage. Combined group/time and label-horizon purging remain unsupported. |
| `label_audit`: OOF logistic disagreement, alternative p≥0.6 and probability gap≥0.3, descending gap ranking | Fold-local imputation/scaling/encoding; exact vectors/group IDs connected; forward expanding windows when time supplied; O(KF) | Label tests check train-only scoring, group/temporal behavior. Probabilities are uncalibrated; hard/minority examples can be falsely flagged. Candidate-only ranking creates ties outside the threshold. No claim of Confident Learning equivalence. |
| `valuation`: LOO v(N)−v(N\i); `valuation_math`: Shapley sum over S not containing i of [v(S+i)−v(S)]/[n·choose(n−1,|S|)] | Classification utility on fixed validation, preprocessing refit per coalition; LOO O(nF), exact O(2ⁿF) with cache, at most 8 exact players | Existing finite-game/efficiency tests. Phase 9 adds independent permutation reference, utility/model sensitivity and six-player comparisons. Empty utility is explicitly specified; it is not a universal scientific convention. Validation-conditioned values do not identify causal errors. |
| Monte Carlo Shapley: mean permutation marginal contribution | O(BnF) upper bound, unique-coalition cache/budget; sampling SD is marginal-contribution SD, not error probability or guaranteed convergence | Increasing 8/32/128 permutation budgets; errors versus exact on the identical game. No monotonic convergence guarantee. |
| KNN Shapley: backward nearest-neighbor recurrence for soft label-match utility, empty utility zero | Numeric complete data only; fixed train-fitted scaling; O(m(nd+n log n)); k≤n | Numeric reference fixtures and exact-game comparisons; not equivalent to logistic model Shapley. Ties resolve by training index. Inexpensive does not mean model-specific. |
| Banzhaf: uniform-coalition mean marginal, weight 2⁻(n−1) | O(2ⁿF), ≤8 players, same utility restrictions | Subset reference checks; no Shapley efficiency axiom and no interchangeability of score magnitudes. |
| `influence`: mean binary logistic loss + λ||β||²/2, including intercept. Gradient mean[(σ(xβ)−y)x]+λβ; Hessian Xᵀdiag(p(1−p))X/n+λI | Fixed preprocessing, convex regularized numeric objective, Hessian O(nd²), solve O(d³); condition≤1e8, optimum residual≤1e−6, solve residual≤1e−8 | Finite-difference gradient/Hessian and fixed-preprocessing deletion refits; duplicates, correlation, separation, outlier and damping/λ sensitivity. Renormalized deletion estimate uses (gᵢ−mean g)ᵀH⁻¹g_eval/(n−1). Damping changes approximation. No arbitrary-model or causal support. |
| `investigator`: median/standardized numeric binary objective, logit β₀+Σβⱼxⱼ; exact Euclidean neighbors, linked label/valuation/influence evidence | ≤2,000 rows/32 features; train-only transforms, validation-only selected record; O(F+nd), optional O(KF+valuation) | Investigator reference and logit reconstruction tests; first three fixed validation records in new study. Exact relation edges and inferred links are distinct; neighbor relevance does not establish cause. |
| `error_slices`, `confirmation`: train-defined cutoffs/categories, validation error-rate gaps; frozen independent membership with Fisher tests only on explicit IID assertion | Bounded candidate intersections, O(md·candidates); confirmatory selection frozen before scoring; Holm across candidates | Existing confirmation tests. Adaptive discovery is exploratory; no p-values on discovery slices. Prior HAR reuse remains descriptive. |
| `fairness`: confusion counts; selection, TPR/FPR/FNR, balanced accuracy; max−min group gaps, min/max selection ratio, worst eligible accuracy | Binary known labels, explicitly supplied audit columns excluded from predictors; support gates and intersections; O(F+md); Wilson only when IID asserted and not group/time split | Existing and independent count fixtures, suppressed/undefined cells explicit. Definitions can conflict; no universal fairness classification. Dependence-aware subgroup intervention intervals NOT RUN. |
| `proxies`: training MI(feature bins, sensitive)/H(sensitive), threshold .3 | Quantile bins or pooled ≤32 categories; no demographic inference; O(nd) plus contingency counts | Planted synthetic proxy/control study; finite-sample bias and grouping can mislead. Predictive proxy verification NOT RUN. |
| `drift`: KS, scaled Wasserstein, smoothed PSI/JSD; categorical JSD with chi-square only expected cells≥5; complete-case RBF biased MMD and plus-one permutation p | ≤10,000 rows/64 columns, MMD≤256/window/16 numeric columns, pooled scaling/bandwidth invariant under permutations; O(Bs²); Holm across all available tests | Null, mean/variance/category/missing/dependence/label/conditional-change fixtures. Threshold alerts differ from formal rejection. Missingness is descriptive; no inference without exchangeability. Covariate drift does not establish concept drift. |
| `performance_drift`: one frozen classifier, reference validation and later labeled comparison metrics | Matching schema, no exact feature overlap, dependence inference unavailable | Existing regression and temporal/grouped benchmark evidence. Needs labels; relationship-change experiments do not prove causal change. |
| `orchestration.health`: available-component weighted mean; completeness, duplicate burden, constant-feature share, candidate-label agreement and integrity, no imputation | Coverage denominated against seven potential components; integrity weight2, others1; O(components) | Existing score/weight/coverage fixtures and Phase 9 weight sensitivity. Includes target column in descriptive profile components by existing contract. Score is burden, not predicted accuracy; unavailable diagnostics cannot imply good health. |
| `recommendations`, `versions`, `planner`, `search`: evidence-linked review requests; explicit immutable transforms, per-class/group guards, fixed validation comparisons and Pareto summary | ≤4 plans/6 fits and cooperative time budgets; structural search only; no learned replacement labels | Existing platform/Phase6/readiness/browser safeguards cover class/group/time retention, authorization and immutability. Recommendations are hypotheses; agreement is not calibrated probability. New independent oracle correction is a separately named research control. |
| `uncertainty`: paired percentile bootstrap of fixed predictions; row, group or overlapping time-block resampling | Representative IID rows/exchangeable clusters/adequate block length, ≥8 effective units; fixed class vocabulary; O(Bm) | Existing interval tests; insufficient support reported. Seeds on one dataset are not independent domains; zero-width intervals do not prove equivalence. |
| `preprocessing`, `modeling`: train-inferred types, median/mean fills, scale, pooled one-hot; macro metrics average defined denominators | Numeric clipping for stability; unknown categories ignored; O(nd) plus fit | Existing isolation/unseen/missing tests. Coalition/refit preprocessing differs from fixed influence/KNN transforms. Macro precision excludes undefined classes under documented legacy convention. |

## Prioritized corrections

P0: the old independent ledger keyed only canonical dataset hash plus exact test
partition. Overlapping test records, training-label changes and subset reindexing
could evade it. New local receipts hold label-independent feature fingerprints and
record IDs, reject overlap, reserve under an exclusive lock, and fail closed on
old or malformed receipts. Both independent-removal and error-slice scoring use it.
Claims survive failed/interrupted scoring. This is not a tamper-proof global
registry: separate ledgers, feature edits, renamed schemas or deleted receipts can
still prevent detection. Published older scores are not retroactively independent.

P1: forward-only univariate evaluation fills a known unsupported temporal mode.
No label availability metadata exists, so horizon purging is not invented. Numeric
thresholds and classifier settings remain frozen; outer rows never select them.

## Frozen core scope and exclusions

`benchmarks/protocols/phase9-v1.json` freezes source identities, seeds 11/23/37,
corruption intensities 0/.1/.2, models, numerical tolerances and budgets before new
final scoring. Diagnostics on Iris/Wine/WDBC are exploratory because previous
versions already evaluated these datasets. A fixed Digits 0/1 central-pixel task
provides three disjoint final blocks; all blocks are excluded from development.
Writer IDs are unavailable, so record separation is not a claim of new-writer
generalization or unconditional IID observations. HAR's compromised comparison
remains descriptive. No new public categorical/group/temporal dataset is claimed;
controlled synthetic cases and prior sourced studies supply limited coverage.

OpenDataVal optional execution and Confident Learning are excluded from this core
environment. Verified OpenDataVal upstream metadata requires NumPy ~1.26, sklearn
~1.3, SciPy ~1.11 and heavyweight torch/pykeops dependencies, conflicting with this
verified NumPy2/sklearn1.6 environment. No dependency downgrade or comparison of
incompatible utilities is performed. Independent mathematical references remain.

All results, including failures and negative deltas, will be retained. Local
cooperative deadlines are checked between trials; bounded inputs/coalitions
prevent unbounded exponential work but do not hard-preempt a native model fit.
