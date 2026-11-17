import warnings
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from importlib.metadata import version
from time import perf_counter
from typing import Any

from .identity import fingerprint
from .ingestion import Dataset, DatasetError
from .numeric import number, numeric
from .splits import Manifest, column, validate

MODELS = ("dummy", "logistic-regression", "decision-tree", "random-forest")


@dataclass(frozen=True)
class ModelConfig:
    model: str = "logistic-regression"
    seed: int = 42
    imputation: str = "median"
    max_depth: int = 8
    trees: int = 32


def divide(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def metrics(
    labels: list[str], predictions: list[str], probabilities: Any, classes: list[str]
) -> dict[str, object]:
    from sklearn.metrics import (
        accuracy_score,
        average_precision_score,
        confusion_matrix,
        log_loss,
        roc_auc_score,
    )

    order = sorted(set(labels) | set(classes) | set(predictions))
    matrix = confusion_matrix(labels, predictions, labels=order).tolist()
    result: dict[str, object] = {
        "accuracy": float(accuracy_score(labels, predictions)),
        "labels": order,
        "confusion_matrix": matrix,
    }
    undefined: dict[str, str] = {}
    per_class = {}
    totals = sum(map(sum, matrix))
    recalls = []
    precisions = []
    f1s = []
    weighted = 0.0
    for i, label in enumerate(order):
        actual = sum(matrix[i])
        predicted = sum(row[i] for row in matrix)
        correct = matrix[i][i]
        precision = divide(correct, predicted)
        recall = divide(correct, actual)
        f1 = divide(2 * correct, actual + predicted)
        for name, value in (("precision", precision), ("recall", recall), ("f1", f1)):
            if value is None:
                undefined[f"per_class/{label}/{name}"] = "Metric denominator is zero."
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": actual,
        }
        if precision is not None:
            precisions.append(precision)
        if recall is not None:
            recalls.append(recall)
        if f1 is not None:
            f1s.append(f1)
            weighted += f1 * actual
    macro_f1 = sum(f1s) / len(f1s)
    result.update(
        per_class=per_class,
        balanced_accuracy=sum(recalls) / len(recalls),
        precision=sum(precisions) / len(precisions),
        recall=sum(recalls) / len(recalls),
        f1=macro_f1,
        macro_f1=macro_f1,
        weighted_f1=weighted / totals,
    )
    result.update(roc_auc=None, average_precision=None, log_loss=None)
    supported = set(labels) <= set(classes) and len(classes) >= 2
    if supported:
        result["log_loss"] = float(log_loss(labels, probabilities, labels=classes))
    else:
        undefined["log_loss"] = (
            "Requires at least two fitted classes and known evaluation labels."
        )
    if supported and set(labels) == set(classes):
        if len(classes) == 2:
            binary = [int(label == classes[1]) for label in labels]
            result["roc_auc"] = float(roc_auc_score(binary, probabilities[:, 1]))
            result["average_precision"] = float(
                average_precision_score(binary, probabilities[:, 1])
            )
            result["positive_label"] = classes[1]
        else:
            result["roc_auc"] = float(
                roc_auc_score(
                    labels,
                    probabilities,
                    labels=classes,
                    multi_class="ovr",
                    average="macro",
                )
            )
    else:
        undefined["roc_auc"] = (
            "Requires every fitted class and no unseen label in evaluation."
        )
    if result["average_precision"] is None:
        undefined["average_precision"] = (
            "Requires binary evaluation with both fitted classes."
        )
    result["undefined_metrics"] = undefined
    return result


def fit_baseline(
    dataset: Dataset,
    target: str,
    manifest: Manifest,
    config: ModelConfig = ModelConfig(),
    *,
    include_test: bool = False,
    train_ids: Sequence[int] | None = None,
    exclude: Sequence[str] = (),
) -> dict[str, Any]:
    from sklearn.exceptions import ConvergenceWarning
    from threadpoolctl import threadpool_limits

    validate(dataset, manifest)
    target_index = column(dataset, target)
    train = list(manifest.partitions["train"] if train_ids is None else train_ids)
    if (
        not train
        or len(set(train)) != len(train)
        or not set(train) <= set(manifest.partitions["train"])
    ):
        raise DatasetError(
            "invalid_training_subset", "Training IDs must be a nonempty train subset."
        )
    if (
        config.model not in MODELS
        or not 0 <= config.seed < 2**32
        or config.imputation not in {"median", "mean", "most_frequent"}
        or not 1 <= config.max_depth <= 16
        or not 1 <= config.trees <= 64
    ):
        raise DatasetError("invalid_model", "Unsupported model, seed or imputation.")
    if len(dataset.rows) > 20000 or len(dataset.columns) > 128:
        raise DatasetError(
            "model_size_limit", "Modeling supports 20,000 rows and 128 columns.", 413
        )
    if any(name not in dataset.columns or name == target for name in exclude):
        raise DatasetError(
            "invalid_excluded_feature", "Excluded features must be non-target columns."
        )
    selected = [
        i
        for i, name in enumerate(dataset.columns)
        if i != target_index and name not in exclude
    ]
    if not selected:
        raise DatasetError("no_features", "At least one training feature is required.")

    def labels(ids: Sequence[int]) -> list[str]:
        values = [dataset.rows[i - 1][target_index] for i in ids]
        if any(not value.strip() for value in values):
            raise DatasetError(
                "missing_target", "Model partitions require nonblank target labels."
            )
        return values

    training_labels = labels(train)
    if len(set(training_labels)) < 2 and config.model == "logistic-regression":
        raise DatasetError(
            "insufficient_classes", "Logistic regression needs two training classes."
        )
    if len(set(training_labels)) > 50:
        raise DatasetError(
            "too_many_classes", "At most 50 training classes are supported."
        )
    pipeline, preprocess, design, numeric_indices, categorical_indices = (
        classification_pipeline(dataset, selected, train, config)
    )
    estimator = pipeline.named_steps["estimator"]
    evaluation: dict[str, Any] = {}
    with threadpool_limits(limits=1):
        start = perf_counter()
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always", ConvergenceWarning)
            pipeline.fit(design(train), training_labels)
        model_warnings = sorted(
            {
                "Model fit emitted " + warning.category.__name__ + "."
                for warning in captured
            }
        )
        train_seconds = perf_counter() - start
        start = perf_counter()
        partitions = {"train": train, "validation": manifest.partitions["validation"]}
        if include_test:
            partitions["test"] = manifest.partitions["test"]
        for key, ids in partitions.items():
            evaluation_labels = labels(ids)
            if len(set(evaluation_labels) | set(training_labels)) > 50:
                raise DatasetError(
                    "too_many_classes", "At most 50 evaluation classes are supported."
                )
            design_matrix = design(ids)
            evaluation[key] = metrics(
                evaluation_labels,
                pipeline.predict(design_matrix).tolist(),
                pipeline.predict_proba(design_matrix),
                estimator.classes_.tolist(),
            )
        evaluate_seconds = perf_counter() - start
    learned: dict[str, object] = {}
    if numeric_indices:
        numeric_steps = preprocess.named_transformers_["numeric"].named_steps
        learned["number"] = [
            numeric_steps["impute"].statistics_.tolist(),
            numeric_steps["scale"].mean_.tolist(),
            numeric_steps["scale"].scale_.tolist(),
        ]
    if categorical_indices:
        categorical_steps = preprocess.named_transformers_["categorical"].named_steps
        learned["category"] = list(
            map(lambda values: values.tolist(), categorical_steps["encode"].categories_)
        )
    return {
        "config": asdict(config),
        "parameters": estimator.get_params(),
        "dataset_sha256": manifest.dataset_sha256,
        "split_sha256": manifest.fingerprint,
        "train_seconds": train_seconds,
        "evaluate_seconds": evaluate_seconds,
        "dependencies": {name: version(name) for name in ("numpy", "scikit-learn")},
        "preprocessing": {
            "numeric": [dataset.columns[selected[i]] for i in numeric_indices],
            "categorical": [dataset.columns[selected[i]] for i in categorical_indices],
            "numeric_imputation": config.imputation,
            "categorical_imputation": "most_frequent",
            "max_categories": 32,
            "numeric_clip": 1e12,
            "fitted_state_sha256": fingerprint(learned),
            "unknown_categories": "ignore",
        },
        "metrics": evaluation,
        "accuracy_gap": float(
            evaluation["train"]["accuracy"] - evaluation["validation"]["accuracy"]
        ),
        "warnings": model_warnings,
        "limitations": [
            "Type inference and preprocessing are fitted on training rows only.",
            "Macro metrics average defined per-class values.",
            "Numeric values are clipped to the documented range before scaling.",
        ],
    }


def classification_pipeline(
    dataset: Dataset, selected: list[int], train: Sequence[int], config: ModelConfig
) -> tuple[Any, Any, Callable[[Sequence[int]], Any], list[int], list[int]]:
    import numpy as np
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    numeric_indices = [
        i
        for i, feature in enumerate(selected)
        if numeric([dataset.rows[i - 1][feature] for i in train])
    ]
    numeric_set = set(numeric_indices)
    categorical_indices = [i for i in range(len(selected)) if i not in numeric_set]

    def design(ids: Sequence[int]) -> Any:
        rows: list[list[object]] = []
        for record_id in ids:
            row: list[object] = []
            for i, feature in enumerate(selected):
                cell = dataset.rows[record_id - 1][feature]
                if i in numeric_set:
                    value = number(cell)
                    row.append(
                        float("nan") if value is None else min(1e12, max(-1e12, value))
                    )
                else:
                    row.append(cell if cell.strip() else float("nan"))
            rows.append(row)
        return np.asarray(rows, dtype=object)

    preprocess = ColumnTransformer(
        [
            (
                "numeric",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy=config.imputation)),
                        ("scale", StandardScaler()),
                    ]
                ),
                numeric_indices,
            ),
            (
                "categorical",
                Pipeline(
                    [
                        (
                            "impute",
                            SimpleImputer(
                                strategy="most_frequent", keep_empty_features=True
                            ),
                        ),
                        (
                            "encode",
                            OneHotEncoder(handle_unknown="ignore", max_categories=32),
                        ),
                    ]
                ),
                categorical_indices,
            ),
        ],
        sparse_threshold=1.0,
    )
    estimator = make_estimator(config)
    pipeline = Pipeline([("preprocessing", preprocess), ("estimator", estimator)])
    return pipeline, preprocess, design, numeric_indices, categorical_indices


def make_estimator(config: ModelConfig) -> Any:
    if config.model == "dummy":
        from sklearn.dummy import DummyClassifier

        return DummyClassifier(strategy="prior")
    if config.model == "logistic-regression":
        from sklearn.linear_model import LogisticRegression

        return LogisticRegression(random_state=config.seed, max_iter=300)
    if config.model == "decision-tree":
        from sklearn.tree import DecisionTreeClassifier

        return DecisionTreeClassifier(
            random_state=config.seed, max_depth=config.max_depth
        )
    from sklearn.ensemble import RandomForestClassifier

    return RandomForestClassifier(
        random_state=config.seed,
        max_depth=config.max_depth,
        n_estimators=config.trees,
        n_jobs=1,
    )
