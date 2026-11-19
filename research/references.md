# Verified primary sources

Checked 2026-11-19. These publications motivate methods; their authors do not
endorse DataGenome, and this technical report has not been peer reviewed.

- Ghorbani and Zou (2019), [Data Shapley: Equitable Valuation of Data for Machine Learning](https://proceedings.mlr.press/v97/ghorbani19c.html).
- Wang and Jia (2023), [Data Banzhaf: A Robust Data Valuation Framework for Machine Learning](https://proceedings.mlr.press/v206/wang23e.html).
- Koh and Liang (2017), [Understanding Black-box Predictions via Influence Functions](https://proceedings.mlr.press/v70/koh17a.html).
- Jiang et al. (2023), [OpenDataVal](https://arxiv.org/abs/2306.10577); [official interfaces](https://opendataval.github.io/), [upstream dependency metadata](https://github.com/opendataval/opendataval/blob/main/pyproject.toml), [PyPI release metadata](https://pypi.org/pypi/opendataval/json).
- Northcutt et al., [Confident Learning](https://arxiv.org/abs/1911.00068). This is related work; no integration or equivalent implementation is claimed.

## Dataset provenance and redistribution

No source data rows are added to Git. Offline loaders use the installed scikit-learn
bundled copies; the protocol records canonical SHA-256 hashes after explicit float
and label string conversion. A changed bundled dataset fails identity matching.
There is no arbitrary URL download or archive extraction command.

| Dataset | Original repository / attribution | Role and changes |
|---|---|---|
| Iris | [UCI, Fisher](https://archive.ics.uci.edu/dataset/53/iris) | 150 records, 4 numeric features; injected training labels; prior evaluations make final claims exploratory |
| Wine | [UCI, Aeberhard and Forina](https://archive.ics.uci.edu/dataset/109/wine) | 178 records, 13 numeric features; multiclass injected labels; descriptive only |
| WDBC | [UCI, Wolberg, Street and Mangasarian](https://archive.ics.uci.edu/dataset/17/breast+cancer+wisconsin+diagnostic) | 569 records, 30 numeric features; binary injected labels; descriptive only; no clinical claims |
| Optical Digits | [UCI, Alpaydin and Kaynak](https://archive.ics.uci.edu/dataset/80/optical+recognition+of+handwritten+digits) | scikit-learn's 1,797-record subset, restricted to digits0/1 and the fixed central4×4 pixels; no fitted feature selection or writer IDs |

The original UCI dataset pages state CC BY 4.0. Attribution is retained here;
generated research files contain aggregate metrics and identities, not sensitive
medical records or reconstructed digit images. Dataset licenses remain distinct
from this repository's Apache-2.0 software license. Recheck original source terms
before redistributing data. Synthetic group/time attributes are never presented as
observed public-dataset metadata.

## OpenDataVal interoperability status

The checked upstream package declares Python>=3.9 and MIT licensing. Its DataFetcher
manages split arrays, DataEvaluator provides per-training-record values, and
ExperimentMediator manages evaluation. Available documented methods include KNN
Shapley, influence and random valuation. Fair comparison requires identical split
arrays, preprocessing, model objective, empty-coalition convention, utility and
budget, not merely matching method names.

Execution/adapter: **NOT RUN** in the verified environment. Upstream pins NumPy
~1.26.4, sklearn~1.3 and SciPy~1.11, plus torch~2.2.2, torchvision and pykeops. Those
requirements conflict with the verified NumPy2/sklearn1.6 environment and introduce
heavy native dependencies on this Windows machine. We did not downgrade the core
environment or bypass Application Control. No superiority claim is made. A future
isolated optional environment should exchange safe numeric arrays/JSON and match
the complete game before comparing methods; no untrusted pickle is required.
