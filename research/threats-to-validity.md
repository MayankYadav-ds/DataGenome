# Threats to validity and remaining scope

- Injected noise supplies known truth but does not identify genuine public-data
  label mistakes. Feature/class-dependent noise tests chosen mechanisms only.
- Random seeds on a single dataset share task structure; they are not independent
  domains. Repeated clean controls are duplicated across noise families.
- Iris/Wine/WDBC were previously scored; new diagnostic comparisons are exploratory.
  HAR's compromised cross-seed comparison remains descriptive permanently.
- Digits evaluation blocks have disjoint feature records and no scored development
  overlap, but absent writer identifiers preclude new-writer independence claims.
  The two-class central-pixel task is easy and small; ceiling effects reduce power.
- Bootstrap intervals assume IID rows conditional on fixed fitted predictions and
  do not include domain shift, uncertain writers, arm selection or training variation.
  Per-arm intervals are not simultaneous family-wise intervals. Identical paired
  predictions can yield zero width without establishing equivalence.
- Only a few independently drawn null drift trials are available. They cannot
  establish a calibrated population false-positive rate; descriptive effect thresholds
  are separate from Holm-adjusted formal tests. Dependence invalidates IID inference.
- Six-player synthetic valuation studies are mathematical/implementation checks, not
  large public-data rankings. Score magnitudes from different games are not directly
  comparable. Same-player cross-seed valuation stability remains incomplete.
- Influence applies to a regularized binary fixed-preprocessing objective with a
  penalized intercept, not arbitrary sklearn/neural/production estimators.
- The scientific audit identifies assumptions and reviewed code paths, not a formal
  proof. Existing edge-case tests and new benchmarks leave untested configurations.
- A local ledger cannot identify outside-ledger reuse, renamed/recomputed features
  or malicious edits. Prior published records remain descriptive where provenance
  of scoring is uncertain. Legacy receipts fail closed; do not reset them to assert
  fresh independence.
- Dataset bundled-version hashes detect changed inputs; floating point, optimizer,
  library and hardware differences can affect results. Python memory tracing excludes
  native allocations. Native calls are not forcibly stopped by cooperative deadlines.

## Explicit remaining checkpoints

P0 correction for detectable holdout overlap and forward-only temporal scoring are
implemented and regression tested. Core reproducible scientific comparisons and
record-disjoint interventions are attempted without an improvement requirement.

Partial/not run: new public categorical/mixed/group/temporal expansion; exhaustive
validation of every corruption family; same-player cross-seed/public-data valuation
stability; OpenDataVal execution/adapter; Confident Learning; predictive proxies;
label-horizon purging; dependence-aware subgroup intervention uncertainty; native
process peak memory; broad natural-error and independent cross-domain validation.

OpenDataVal has a precise dependency/native compatibility blocker. Missing verified
label-availability, writer and subgroup dependence metadata block stronger inference.
Other breadth items are outside the bounded CPU core scope, not represented as
completed. Scientific validation is **PARTIAL** beyond that scope.
