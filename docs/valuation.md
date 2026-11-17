# Training-record valuation

```powershell
python -m datagenome value-data data.csv --target label --method loo --output valuation.json
python -m datagenome value-data data.csv --target label --method knn-shapley --k 3
python -m datagenome value-data tiny.csv --target label --method mc-shapley --permutations 32 --max-evaluations 1024
python -m datagenome value-data data.csv --target label --method loo --utility class_recall --utility-class rare
python -m datagenome compare-removal data.csv --target label --method knn-shapley --removal-fraction 0.2
python benchmarks/valuation.py --output valuation-benchmark.json
```

Use a saved manifest for both valuation and removal to fix the partition IDs.
The Python SDK is `datagenome.valuation.value_data` with a `ValuationConfig`
and optional `ModelConfig`. The local REST routes accept a raw UTF-8 CSV body
with `Content-Type: text/csv` and query parameters `filename`, `target`,
`method`, `utility`, and resource controls. Use `POST /api/v1/datasets/valuation`
and `POST /api/v1/experiments/data-removal`. API flags use underscores. Responses
inherit the existing versioned report envelope and structured errors.

## Architecture and utility

The split manifest validates the dataset fingerprint and partition IDs. IDs are
one-based record positions. Valuation scores only validation records and rejects
exact feature overlap between train and validation. The full dataset fingerprint
includes held-out records, but their values and labels do not contribute to utility.
The retraining utility reuses the baseline preprocessing pipeline and fits it on
each coalition. Fits and subsets are cached within a request. Larger utilities
are better. Supported metrics are accuracy, balanced accuracy, macro F1 over
validation classes, negative log loss, and recall of an explicitly selected
validation class. Log loss is negated and probabilities are floored at 1e-15.

Single-class coalitions predict their sole label. The empty coalition has
uniform reference probabilities over the validation-class vocabulary. Its
accuracy, balanced accuracy, and class recall are the expected uniform-guess
scores. Empty macro F1 is defined as zero for abstention. This is a convention
for the game, and changing it changes values. Failed fits abort the request
rather than entering a fallback score. Supported retraining models are the
existing dummy, logistic regression, decision tree and random forest baselines.

## Algorithms

| Method | Definition and cost |
|---|---|
| Exact leave-one-out | With player set N and utility v, record i gets v(N) minus v(N without i). At most n+1 utility evaluations. The value is local to the full coalition. |
| Exact Shapley | Sum v(S plus i) minus v(S) over subsets excluding i, weighted by 1 / [n choose(n-1, size(S))]. At most 2^n unique utilities and O(n 2^n) marginal operations. |
| Monte Carlo Shapley | Average marginal utilities along seeded random permutations. At most P(n+1) utility requests before caching. Reports per-record marginal sample SD and changes in the running estimate. SD is descriptive and the trace makes no convergence guarantee. |
| Exact Banzhaf | Average a player's marginal utility over subsets excluding it with equal weights 1 / 2^(n-1). At most 2^n utilities. No efficiency constraint generally holds. |
| KNN Shapley | Exact values for the fraction of K matching neighbor slots, with unfilled slots contributing zero. For ordered position j, s_j = s_(j+1) + (match_j - match_(j+1)) min(K,j)/(Kj), with s_n = match_n/n. Uses fixed full-training scaling, squared Euclidean distance, and record-ID tie breaks. O(m(nd + n log n)) time and one distance ordering at a time. Supports finite numeric features. |

KNN's `accuracy` configuration selects its soft matching utility. The output
names that utility `knn_soft_match`. It is distinct from hard KNN accuracy and
classifier retraining utilities. Its full-training transform is held fixed across
KNN coalitions so the recurrence applies. Duplicate records remain separate
players and ties are deterministic. Values depend on the chosen model and metric.
Negative values are evidence of conditional marginal effects.

Primary references are [Data Shapley](https://proceedings.mlr.press/v97/ghorbani19c.html),
[KNN Shapley](https://arxiv.org/abs/1908.08619),
[Data Banzhaf](https://proceedings.mlr.press/v206/wang23e.html), and
[OpenDataVal, including leave-one-out baselines](https://arxiv.org/abs/2306.10577).

## Removal and safeguards

Removal compares the full training baseline with low-valued, high-valued,
random and, when there are enough candidates, suspected-label exclusions.
Each evaluated arm removes the same count, subject to per-class caps that
preserve every class and limit each class's removal fraction. The report shows
validation metrics, per-class recall changes and minority recall degradation.
Selection and evaluation share validation data, so observed gains are exploratory.
Held-out test metrics are reserved for a later, independently specified analysis.
Source data is read-only and valuation reports can reveal labels and record IDs.

Limits are 128 training rows for LOO, eight for exact Shapley and Banzhaf, 64 for
Monte Carlo, and 1,000 for KNN. All methods cap validation at 500 rows and features
at 32. Retraining accepts up to 1,024 cached utility evaluations, up to 256
permutations and a cooperative deadline checked between evaluations. Parallel
fits are disabled. A single fit can finish after the deadline before cancellation
is observed. Budget exhaustion returns a structured error. KNN uses an analytic
recurrence and reports validation queries separately from retraining evaluations.

## Benchmarks and remaining work

The deterministic suite uses two seeds across twelve synthetic scenarios and
evaluates approximation error on two eight-or-fewer-player reference games.
It reports rank correlation, top-K overlap, known-corruption retrieval against
a random control, validation removal outcomes, elapsed time, fit counts and
tracemalloc peaks. Python allocation peaks exclude native allocations.
The existing ingestion, profiles, fingerprints, split management, leakage and
label diagnostics, model training, metrics, CLI and REST are regression tested.
The benchmark provides cross-seed and cross-model stability measurements for
small reference fixtures. It does not establish real-world ranking stability.

Phase 5 adds [experimental logistic influence](influence.md) for a fixed preprocessing objective. These local loss derivatives are distinct from the global coalition utilities described here.

In the two six-record reference games, 16 sampled permutations produced mean
absolute errors of 0.022 and 0.030 utility units. Exact versus sampled Spearman
correlation was 0.49 and 0.14, with two of the top three overlapping for both
seeds. Switching the Monte Carlo seed gave correlations of 0.71 and 0.37.
Changing the LOO model gave correlations of 0.61 and -0.31. These small games
showed substantial ranking sensitivity.

Across 24 scenario runs, mean validation-accuracy deltas were +2.92 percentage
points for low-value removal, -0.83 for high-value removal, and -0.42 for random
removal. One high-value arm reduced minority recall. Four label-audit arms
had enough eligible matches and averaged +7.50 points. Their average uses a
different set of runs. On the eight planted-corruption runs, KNN bottom-K
precision and recall averaged 1.00 on these fixtures, while the matched random
control averaged 0.225 precision. Test rows were reserved.

Phase 5 adds an [independent evaluation and permutation stability workflow](independent.md).
