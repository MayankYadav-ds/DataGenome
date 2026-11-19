# DataGenome: An Evidence-Driven Framework for Dataset Debugging and Machine Learning Failure Investigation

Open technical report, Phase9, November2026. **Not peer reviewed.** No conference
publication, commercial superiority or production-readiness claim is made.

## 1. Abstract

DataGenome combines bounded local diagnostics, inspectable evidence and explicitly
reviewed data interventions. This report evaluates injected-label detection,
leakage screening, six-player valuation games, regularized logistic influence,
synthetic subgroup/drift fixtures and prespecified record-disjoint interventions.
All generated observations and negative outcomes are preserved in executable
artifacts. Scientific scope is bounded; heuristic agreement does not establish
incorrect labels, causal responsibility, universal fairness or improved accuracy.

## 2. Introduction

Dataset debugging mixes structural facts, statistical associations and uncertain
intervention hypotheses. A useful platform must keep these distinctions visible.
The goal is trustworthy evidence, including evidence that removal rules degrade
performance. Phase9 prioritizes evaluation isolation over additional interfaces.

## 3. Problem formulation

For a classifier trained on D_tr, detectors rank features/records for review.
D_val supports exploratory utility and prespecified arm selection. D_final is
reserved before final scoring. A corruption mask is evaluation truth only, never
a diagnostic input. Known injected corrections are explicitly oracle controls.
Natural dataset labels are not assumed wrong because a classifier disagrees.

## 4. Related work

Data Shapley and Banzhaf formalize distinct cooperative-game marginal quantities.
Influence functions approximate a model's response to infinitesimal reweighting;
finite deletion adds approximation error. OpenDataVal motivates reproducible
valuation comparisons and Confident Learning motivates label-noise research.
[Verified references](references.md) link the original papers and interfaces.
These are research foundations, not endorsements or identical implementations.

## 5. System architecture

The Python SDK remains the scientific source of truth. Existing CLI, local API,
owned workspaces, immutable versions and React application remain operational.
Optional benchmark commands invoke the same engines, record execution metadata
and publish aggregate files. The research page fetches a small generated summary
and links every observation to individual suite artifacts. No external LLM,
telemetry service, paid API or cloud worker creates scientific explanations.

## 6. Mathematical methodology

[The complete source audit](scientific-audit.md) records implemented formulations,
input/model assumptions, cost, existing evidence and gaps for profiling, leakage,
labels, all valuation methods, influence, investigation, slices, fairness, proxies,
drift, health, recommendations, interventions, preprocessing and uncertainty.
[Methodology](methodology.md) defines thresholds, reference games, baseline ranking,
undefined metric conventions and conditional uncertainty. In particular, only MC
versus identical exact Shapley is an approximation comparison; other games need
not have comparable score magnitudes.

## 7. Experimental design

The [frozen registry](../benchmarks/protocols/phase9-v1.json) predates new independent
scoring and specifies seeds11/23/37, corruption rates0/.1/.2 and bounded settings.
Commit `34a5563` contains the execution source and protocol. Public diagnostic
datasets evaluated in earlier phases remain exploratory. Prespecified Digits final
blocks are disjoint across seeds; all blocks are excluded from development.
Trial IDs, hashes, dependencies, model/algorithm/corruption configuration, budgets,
runtime, warnings, unsuccessful cases and results are recorded. Outcome-based arm
selection and repeated final scoring are not part of the protocol.

## 8. Dataset descriptions

[Provenance](references.md) attributes Iris, Wine, WDBC and Optical Digits to their
original UCI sources and records CC BY4.0 terms. Installed scikit-learn copies
provide offline acquisition. Canonical hashes verify the derived representation;
no raw records are added to Git. Public label studies cover binary/multiclass
numeric tasks. Mixed/category/group/time scenarios use explicit synthetic fixtures
or previously documented studies; they are not invented public metadata. The
Digits task uses only0/1 and a fixed central4×4 pixel subset to bound computation.

## 9. Algorithm comparisons

Label audit is compared with random ranking, OOF disagreement, low observed-label
probability and five-neighbor inconsistency. Leakage fixtures include legitimate
strong predictors and high-cardinality controls. Exact LOO/Shapley/Banzhaf and
bounded numeric KNN are compared descriptively, and increasing MC budgets are
compared with the identical exact game. Influence estimates are compared with
actual fixed-preprocessing refits across correlation, repeats, separation,
influential observations, regularization and damping configurations.

## 10. Results

[Generated observations](results.md) and the [full descriptive tables](../benchmarks/results/phase9/summary.md)
are derived from execution, including unfavorable results. The JSON artifacts
retain every trial; their exact byte hashes appear in the public result index.
No manually entered benchmark scoreboard or selective successful-case average
replaces those files. Label AP and FPR remain per dataset/noise condition; clean
controls have undefined AP. Numerical derivative correctness and retraining
approximation quality are reported separately.

## 11. Independent intervention evaluation

Original, matched random removal, lowest/highest KNN-value removal, suspected
label exclusion, oracle correction, duplicate removal and combined arms are
prespecified. All scored arms share final records, logistic model settings and
seed. Ineligible duplicate arms are retained as insufficient candidates. Removal
caps preserve classes. Synthetic oracle corrections are not a deployable automatic
labeling method. The generated tables retain validation and independent accuracy,
balanced accuracy, macro F1, negative log loss, per-class recall, paired changes,
training counts and conditional bootstrap intervals.

No accuracy improvement occurred across the non-baseline arm comparisons in this
small task. Zero changes and degradations are evidence against promising universal
benefit. This does not establish equivalence or prove an algorithm always fails.
Writer identifiers are unavailable: record separation does not prove independence
between writers. Earlier compromised HAR outcomes remain descriptive.

## 12. Computational analysis

The workload suite measures increasing100/500/1,000/5,000/10,000 rows and3/16
features, with ingestion, profiling, intelligence, leakage, eligible labels,
health/recommendation generation and serialization timings. Other suites time
their own valuation/influence/models/experiments. Python tracemalloc is per-trial
peak and excludes native allocations; process peak working set is NOT RUN. See
[hardware, commands and budget details](reproducibility.md). Native fits are
cooperatively bounded, not hard-preempted. Exponential games use six players.

## 13. Failure cases

Legitimate strong predictors may trigger heuristic leakage alerts. OOF label
disagreement flags valid difficult/minority records. Thresholded candidates tie
many scores; probability-based controls may rank injected errors better. Value
rankings condition on the utility/model/validation game. Damping changes influence
estimates. Drift effect alerts are not equivalent to formal rejection, and
conditional outcome changes need not shift covariates. Health coverage is incomplete
and its aggregate is not validated as an accuracy predictor. All unsupported arms
and method configurations remain explicit rather than receiving fabricated scores.

## 14. Threats to validity

[Threats and remaining checkpoints](threats-to-validity.md) distinguish code
regressions from scientific guarantees. Small classic datasets, synthetic noise,
few seeds, shared development records, missing dependence identifiers and limited
benchmark breadth constrain inference. There is no independent real-world natural
label-error annotation or cross-domain intervention replication. No correction
for simultaneous arm intervals is claimed. Reproducing a published final benchmark
is replication, not a new unseen evaluation.

## 15. Ethical and privacy considerations

Only public appropriately attributed datasets and explicit synthetic data enter
the research runner. Public artifacts exclude local workspaces, raw records,
credential material, corruption masks and local ledger selections. WDBC findings
do not justify medical decisions. Synthetic audit groups do not establish real
demographic fairness. Reports can still reveal information; redaction is not
guaranteed anonymity. Never remove minority records without source review.

## 16. Reproducibility instructions

[The toolkit guide](reproducibility.md) provides module-based Windows commands,
protocol/seed controls, dataset identity checks, result formats and all quality
gates. Trial journals preserve interruptions and failures. Exclusive holdout
receipts block detectable overlap across changed labels and subset indexing;
legacy or malformed receipts refuse scoring. Independent evaluation is not safe
against intentional ledger deletion or arbitrary feature/schema changes.

## 17. Limitations

OpenDataVal execution is blocked by incompatible pinned/native dependencies in
the verified environment and remains NOT RUN. Confident Learning, predictive
proxy verification, label-availability horizon purging and dependence-aware
subgroup intervention uncertainty are NOT RUN. Strict simultaneous group/time
univariate folds remain unsupported. Public categorical/mixed/group/temporal
expansion, same-player cross-seed valuation stability and broader natural-error
validation remain incomplete. This is a bounded research milestone, not full
scientific validation of all intended applications.

## 18. Future work

Prespecify new domains and independent group/time final blocks, obtain verified
label-availability metadata, test same-player valuation ranking stability over
larger model/utility families, and isolate compatible optional reference packages.
Measure native/process memory separately and expand numerical/reference fixtures.
Do not tune these next protocols on the final outcomes published here. Production
security/deployment work belongs to a future directive; Phase10 is not started.

## 19. References

See [verified primary references and dataset attribution](references.md).
