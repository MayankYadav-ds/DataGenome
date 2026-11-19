# Frozen research benchmarks

The Phase9 core is implemented in `datagenome.benchmark*` so installed-wheel module
commands execute the same methods as SDK/API callers. The earlier standalone
scripts remain available as historical/descriptive studies, not silently promoted
to independent evidence.

- [Prespecified configuration and dataset hashes](protocols/phase9-v1.json).
- [All executed trial artifacts and summary tables](results/phase9/summary.md).
- [Source audit and mathematical assumptions](../research/scientific-audit.md).
- [Windows reproduction commands](../research/reproducibility.md).
- [Technical report](../research/technical-report.md).

Use `python -m datagenome benchmark --suite smoke --output .datagenome/research/smoke`.
Additional explicit suites: leakage, labels, valuation, influence, fairness, drift,
interventions, performance. Expensive runs are optional. A completed directory
refuses overwrite. Freeze new exploratory seeds/protocols before scoring; do not
reset ledgers to call previously scored records unseen.

Original datasets are acquired offline from scikit-learn's bundled copies and
canonical checksums must match the checked-in protocol. Only aggregate results
are committed. Corruption masks, local final-record selections, ledgers, user
datasets and credentials are excluded. The summary generator copies safe aggregate
JSON/CSV/Markdown, computes byte hashes and generates the web evidence file.
Failed cases and negative effects remain visible. Exported JSON uses explicit LF
bytes to keep identities reproducible on Windows.

The `model_configuration` trial envelope records the protocol's default model;
method-specific model/utility overrides are recorded in `configuration` and
`result` (e.g. fixed-objective influence, decision-tree valuation or KNN utility).
Reference finite games have no dataset or split; null identity fields are not
claims of a public-data experiment. Standalone fair/proxy fixtures use explicitly
synthetic attributes, never fabricated public protected/group/time metadata.

Published execution used source commit `34a5563` and package metadata0.5.0 before
the report/UI release bump to0.6.0. This is retained verbatim in artifacts, not
rewritten to pretend the final release commit executed earlier experiments.
