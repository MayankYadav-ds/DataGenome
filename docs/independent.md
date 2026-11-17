# Independent removal evaluation

Freeze a protocol before evaluating its final partition. The exploratory report
selects arms using training and diagnostic validation data. It records the
dataset hash, full manifest, random seed, model and dependency versions, utility,
class caps policy, fraction, eligible arm IDs and outcome metrics. The local
protocol digest checks accidental changes.

```powershell
python -m datagenome.independent freeze data.csv --target label --protocol study.protocol.json
python -m datagenome.independent score data.csv --protocol study.protocol.json
python benchmarks/independent.py --output independent.report.json
python benchmarks/stability.py --output stability.report.json
```

The Python entry points are `freeze_removal` and `score_frozen`. Final scoring
does no selection and atomically claims the partition using an exclusive ledger
file, before testing for exact feature overlap or fitting a final arm. The ledger
blocks reuse of that dataset and exact final partition in the same directory.
If execution fails after claiming, the claim remains. A separate result file
records successful scoring. Preserve both artifacts. The local ledger and
unkeyed digest cannot stop intentional bypass, changes to dataset identity, use
of alternate workspaces, overlapping partitions, or manual reuse of outcomes.
The protocol exposes file operations locally through the CLI and Python, without
offering arbitrary file access through the API.

## Public benchmarks

Scikit-learn bundles the three datasets. UCI lists them under CC BY 4.0.
No dataset copy is committed. Provenance and attribution are recorded at the
[Wisconsin Diagnostic data page](https://archive.ics.uci.edu/dataset/17/breast+cancer+wisconsin+diagnostic),
[Wine data page](https://archive.ics.uci.edu/dataset/109/wine), and
[Iris data page](https://archive.ics.uci.edu/dataset/53/iris).
The clean and training-only label-flip variants share fold assignments per seed
and supply two paired conditions on the same source data. Their outcomes are
dependent. The 10% removal fraction and seeds 11, 23 and 37 were fixed in code.
Metrics include accuracy, balanced accuracy, macro F1, negative log loss, and
per-class recall. Per-trial paired deltas provide descriptive variation without
confidence intervals.

Four of 18 trials were blocked by exact feature overlap. For the 14 scored
trials, low-value removal averaged +0.94 percentage points on exploratory
validation and +2.81 on the independent partition. High-value removal averaged
-0.91 and -0.14 points. Random removal averaged -0.28 and +0.21 points. Four eligible
label-audit arms averaged 0.00 and +4.72 points. Exact-duplicate arms did not reach
the matched count on the scored trials.

## Valuation stability

The stability sweep compares exact Shapley against 16, 32, 64, 128 and 256 sampled
permutations for six-record clean and duplicate games. It uses accuracy and
negative log loss, and preserves separate per-game results for both scales.
Across those eight small games, raw MAE averaged 0.476 at 16 and 0.199 at 256,
and mean defined Spearman increased from 0.36 to 0.64. Pooled MAE mixes scales
and is descriptive only. Use the per-metric results for interpretation. The
benchmark records tied exact scores, both rank correlations, top and bottom
overlap, runtime and cached utility counts. It does not establish general ranking
convergence. The previous model-dependence results remain exploratory.
