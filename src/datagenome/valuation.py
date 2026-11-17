from collections.abc import Sequence
from dataclasses import asdict, dataclass
from math import isfinite
from statistics import mean, median
from time import perf_counter
from typing import Any, TypedDict

from .ingestion import Dataset, DatasetError
from .modeling import MODELS, ModelConfig, classification_pipeline
from .numeric import number
from .splits import Manifest, column, validate
from .valuation_math import exact_values, knn_values, sampled_values

METHODS = ("loo", "shapley", "mc-shapley", "knn-shapley", "banzhaf")
UTILITIES = (
    "accuracy",
    "balanced_accuracy",
    "macro_f1",
    "negative_log_loss",
    "class_recall",
)
LIMITS = {"loo": 128, "shapley": 8, "mc-shapley": 64, "knn-shapley": 1000, "banzhaf": 8}


@dataclass(frozen=True)
class ValuationConfig:
    method: str = "loo"
    metric: str = "accuracy"
    positive_class: str | None = None
    seed: int = 42
    max_evaluations: int = 256
    permutations: int = 16
    k: int = 3
    seconds: float = 30


class RecordValue(TypedDict):
    record_id: int
    label: str
    score: float
    sampling_sd: float | None


class UtilityEvaluator:
    def __init__(
        self,
        dataset: Dataset,
        target: str,
        train: Sequence[int],
        validation: Sequence[int],
        config: ValuationConfig,
        model: ModelConfig,
        excluded: tuple[str | None, ...] = (),
    ) -> None:
        self.dataset = dataset
        self.config = config
        self.model = model
        self.train = sorted(train)
        self.validation = list(validation)
        target_index = column(dataset, target)
        self.features = [
            i
            for i, name in enumerate(dataset.columns)
            if i != target_index and name not in excluded
        ]
        self.target_index = target_index
        self.labels = [dataset.rows[i - 1][target_index] for i in self.validation]
        self.classes = sorted(set(self.labels))
        self.cache: dict[int, float] = {}
        self.fits = 0
        self.start = perf_counter()
        all_labels = self.labels + [
            dataset.rows[i - 1][target_index] for i in self.train
        ]
        if any(not label.strip() for label in all_labels):
            raise DatasetError(
                "missing_valuation_label",
                "Training and validation labels must be present.",
            )
        if len(set(all_labels)) > 20 or not self.features:
            raise DatasetError(
                "unsupported_valuation_input",
                "Valuation requires features and at most 20 classes.",
            )
        if (config.metric == "class_recall") != (config.positive_class is not None):
            raise DatasetError(
                "invalid_valuation_class",
                "Class recall requires an explicit validation class.",
            )
        if (
            config.positive_class is not None
            and config.positive_class not in self.classes
        ):
            raise DatasetError(
                "invalid_valuation_class",
                "The requested class is absent from validation.",
            )

    def check_budget(self) -> None:
        if perf_counter() - self.start > self.config.seconds:
            raise DatasetError(
                "valuation_timeout", "Valuation exceeded its cooperative time budget."
            )

    def __call__(self, mask: int) -> float:
        self.check_budget()
        if mask in self.cache:
            return self.cache[mask]
        if len(self.cache) >= self.config.max_evaluations:
            raise DatasetError(
                "valuation_budget", "Utility evaluation budget exceeded."
            )
        ids = [record for i, record in enumerate(self.train) if mask & (1 << i)]
        score = self.score(ids)
        self.cache[mask] = score
        return score

    def score(self, ids: list[int]) -> float:
        from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
        from threadpoolctl import threadpool_limits

        self.check_budget()
        labels = [self.dataset.rows[i - 1][self.target_index] for i in ids]
        known = set(labels)
        if len(known) >= 2:
            pipeline, _, design, _, _ = classification_pipeline(
                self.dataset, self.features, ids, self.model
            )
            with threadpool_limits(limits=1):
                pipeline.fit(design(ids), labels)
                matrix = design(self.validation)
                predictions = pipeline.predict(matrix).tolist()
                probabilities = (
                    pipeline.predict_proba(matrix)
                    if self.config.metric == "negative_log_loss"
                    else None
                )
            self.fits += 1
            probability_index = {name: i for i, name in enumerate(pipeline.classes_)}
        else:
            predictions = [labels[0]] * len(self.labels) if labels else []
            probabilities = None
            probability_index = {}
        self.check_budget()
        metric = self.config.metric
        if metric == "negative_log_loss":
            from math import log

            if probabilities is None:
                # Empty predicts uniformly over the task vocabulary. Singleton predicts its class.
                return mean(
                    log(
                        max(
                            1e-15,
                            (1 / len(self.classes))
                            if not labels
                            else float(actual == labels[0]),
                        )
                    )
                    for actual in self.labels
                )
            return mean(
                log(
                    max(
                        1e-15,
                        float(row[probability_index[actual]])
                        if actual in probability_index
                        else 0.0,
                    )
                )
                for actual, row in zip(self.labels, probabilities, strict=True)
            )
        if not predictions:
            # Expected utility of a uniform random classifier over validation classes.
            if metric == "macro_f1":
                return 0.0  # Explicit abstention receives zero class F1.
            return 1 / len(self.classes)
        if metric == "accuracy":
            return float(accuracy_score(self.labels, predictions))
        if metric == "balanced_accuracy":
            return float(balanced_accuracy_score(self.labels, predictions))
        if metric == "macro_f1":
            return float(
                f1_score(
                    self.labels,
                    predictions,
                    labels=self.classes,
                    average="macro",
                    zero_division=0,
                )
            )
        return mean(
            float(pred == actual)
            for pred, actual in zip(predictions, self.labels, strict=True)
            if actual == self.config.positive_class
        )


def value_data(
    dataset: Dataset,
    target: str,
    manifest: Manifest,
    config: ValuationConfig = ValuationConfig(),
    *,
    model: ModelConfig | None = None,
) -> dict[str, Any]:
    validate(dataset, manifest)
    train, validation = (manifest.partitions[name] for name in ("train", "validation"))
    if (
        config.method not in METHODS
        or config.metric not in UTILITIES
        or not 0 <= config.seed < 2**32
        or not 1 <= config.max_evaluations <= 1024
        or not 2 <= config.permutations <= 256
        or not 1 <= config.k <= 1000
        or not 0 < config.seconds <= 120
    ):
        raise DatasetError(
            "invalid_valuation_config",
            "Unsupported method, utility or resource configuration.",
        )
    if (
        len(train) > LIMITS[config.method]
        or len(validation) > 500
        or len(dataset.columns) > 33
    ):
        raise DatasetError(
            "valuation_size_limit",
            "Method training limit, 500 validation rows, or 32 features exceeded.",
            413,
        )
    target_index = column(dataset, target)
    excluded = (manifest.config.group, manifest.config.time)

    def features_of(i: int) -> tuple[str, ...]:
        row = dataset.rows[i - 1]
        return row[:target_index] + row[target_index + 1 :]

    train_keys = {features_of(i) for i in train}
    if any(features_of(i) in train_keys for i in validation):
        raise DatasetError(
            "valuation_contamination",
            "Training and validation share exact feature vectors.",
        )
    n = len(train)
    if (
        config.method == "loo"
        and config.max_evaluations < n + 1
        or (config.method in {"shapley", "banzhaf"} and config.max_evaluations < 1 << n)
    ):
        raise DatasetError(
            "valuation_budget", "Budget is below the required number of evaluations."
        )
    model = model or ModelConfig(seed=config.seed)
    if (
        model.model not in MODELS
        or not 0 <= model.seed < 2**32
        or model.imputation not in {"median", "mean", "most_frequent"}
        or not 1 <= model.max_depth <= 16
        or not 1 <= model.trees <= 64
    ):
        raise DatasetError(
            "invalid_model", "Unsupported valuation model configuration."
        )
    engine = UtilityEvaluator(
        dataset, target, train, validation, config, model, excluded
    )
    variability = None
    convergence: list[dict[str, float | int]] = []
    full = (1 << n) - 1
    if config.method == "knn-shapley":
        if config.metric != "accuracy" or config.k > n:
            raise DatasetError(
                "unsupported_knn_utility",
                "KNN Shapley requires accuracy and K no larger than training size.",
            )
        matrices: list[list[list[float]]] = []
        for ids in (engine.train, engine.validation):
            matrix = []
            for i in ids:
                values = [number(dataset.rows[i - 1][j]) for j in engine.features]
                if any(value is None for value in values):
                    raise DatasetError(
                        "unsupported_knn_features",
                        "KNN Shapley requires finite numeric features without blanks.",
                    )
                matrix.append(
                    [
                        min(1e12, max(-1e12, value))
                        for value in values
                        if value is not None
                    ]
                )
            matrices.append(matrix)
        training, scoring = matrices
        import numpy as np
        from sklearn.preprocessing import StandardScaler

        scaler = StandardScaler().fit(training)
        labels = [dataset.rows[i - 1][engine.target_index] for i in engine.train]
        trained = np.clip(scaler.transform(training), -1e12, 1e12).tolist()
        scored = np.clip(scaler.transform(scoring), -1e12, 1e12).tolist()
        scores = knn_values(
            trained, scored, labels, engine.labels, config.k, engine.check_budget
        )
        baseline = sum(scores)
        empty = 0.0
    else:
        baseline = engine(full)
        empty = None
        if config.method == "loo":
            scores = [baseline - engine(full ^ (1 << i)) for i in range(n)]
        elif config.method == "mc-shapley":
            scores, variability, convergence = sampled_values(
                n, engine, config.seed, config.permutations
            )
            empty = engine(0)
        else:
            scores = exact_values(n, engine, banzhaf=config.method == "banzhaf")
            empty = engine(0)
    if not all(isfinite(score) for score in scores):
        raise DatasetError(
            "undefined_valuation", "Valuation yielded a non-finite score."
        )
    records: list[RecordValue] = [
        {
            "record_id": record,
            "label": dataset.rows[record - 1][engine.target_index],
            "score": scores[i],
            "sampling_sd": variability[i] if variability is not None else None,
        }
        for i, record in enumerate(engine.train)
    ]
    ranked = sorted(records, key=lambda row: (-row["score"], row["record_id"]))
    ratings_by_class: dict[str, list[float]] = {}
    duplicate_groups: dict[tuple[str, ...], list[RecordValue]] = {}
    for record in records:
        ratings_by_class.setdefault(record["label"], []).append(record["score"])
        duplicate_groups.setdefault(features_of(record["record_id"]), []).append(record)
    negative_duplicates = sorted(
        record["record_id"]
        for group in duplicate_groups.values()
        if len(group) > 1
        for record in group
        if record["score"] < 0
    )
    negative_conflicts = sorted(
        record["record_id"]
        for group in duplicate_groups.values()
        if len({record["label"] for record in group}) > 1
        for record in group
        if record["score"] < 0
    )
    return {
        "method": config.method,
        "utility": "knn_soft_match"
        if config.method == "knn-shapley"
        else config.metric,
        "config": asdict(config),
        "model": "fixed_scaled_knn" if config.method == "knn-shapley" else model.model,
        "model_config": None if config.method == "knn-shapley" else asdict(model),
        "dataset_sha256": manifest.dataset_sha256,
        "split_sha256": manifest.fingerprint,
        "full_utility": baseline,
        "empty_utility": empty,
        "records": ranked,
        "utility_evaluations": len(engine.cache),
        "model_fits": engine.fits,
        "knn_validation_queries": len(validation)
        if config.method == "knn-shapley"
        else 0,
        "elapsed_seconds": perf_counter() - engine.start,
        "convergence_trace": convergence,
        "summary": {
            "highest": ranked[:5],
            "lowest": ranked[-5:][::-1],
            "near_zero_count": sum(abs(score) <= 1e-9 for score in scores),
            "median": median(scores),
            "class_distribution": {
                label: {
                    "count": len(values),
                    "mean": mean(values),
                    "min": min(values),
                    "max": max(values),
                }
                for label, values in sorted(ratings_by_class.items())
            },
            "negative_duplicate_records": negative_duplicates,
            "negative_conflicting_label_records": negative_conflicts,
        },
        "limitations": [
            "Scores are conditional on utility, model, and validation data.",
            "Negative scores do not identify incorrect labels.",
            "KNN uses fixed preprocessing and a soft matching-neighbor utility.",
            "Sampling standard deviations describe marginal contributions.",
            "Held-out test performance is never scored.",
        ],
    }
