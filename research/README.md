# DataGenome research

Start with the [Phase9 technical report](technical-report.md), [source audit](scientific-audit.md),
[mathematical methodology](methodology.md), [observed evidence](results.md),
[reproduction commands](reproducibility.md) and [threats to validity](threats-to-validity.md).
The [primary-source and dataset attribution guide](references.md) documents current
provenance and optional interoperability limits. Validation remains partial beyond
the measured scope; no peer review or production readiness is claimed.

## Earlier research foundations

Phase 0 uses descriptive checks on individual CSV files. These publications guide later
experiments. Evaluate each technique against a controlled baseline before drawing
conclusions about model performance.

- Jiang et al. (2023), [OpenDataVal](https://papers.nips.cc/paper_files/paper/2023/hash/5b047c7d862059a5df623c1ce2982fca-Abstract-Datasets_and_Benchmarks.html), benchmarks multiple training-data valuation methods.
- Ghorbani and Zou (2019), [Data Shapley](https://proceedings.mlr.press/v97/ghorbani19c.html), assigns training records values based on marginal contributions to a chosen utility.
- Wang and Jia (2023), [Data Banzhaf](https://proceedings.mlr.press/v206/wang23e.html), studies valuation robustness to noisy utility scores.
- Koh and Liang (2017), [Influence Functions](https://proceedings.mlr.press/v70/koh17a.html), estimates how training records influence predictions.
- Northcutt et al. (2021), [Confident Learning](https://arxiv.org/abs/1911.00068), estimates label noise and ranks records for review.
- Liu et al. (2008), [Isolation Forest](https://ieeexplore.ieee.org/abstract/document/4781136), uses isolation to identify candidate anomalies.
- Lundberg and Lee (2017), [SHAP](https://proceedings.neurips.cc/paper_files/paper/2017/hash/8a20a8621978632d76c43dfd28b67767-Abstract.html), attributes model predictions to input features.
