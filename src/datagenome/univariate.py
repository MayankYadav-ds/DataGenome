from collections import Counter
from dataclasses import dataclass
from statistics import mean
from typing import TypedDict

from .folds import connected_groups, historical_folds
from .ingestion import Dataset, DatasetError
from .numeric import number, numeric


@dataclass(frozen=True)
class UnivariateConfig:
    folds: int = 3
    max_features: int = 16
    minimum_score: float = 0.90
    minimum_lift: float = 0.20

    def validate(self) -> None:
        if (
            type(self.folds) is not int
            or type(self.max_features) is not int
            or not 2 <= self.folds <= 5
            or not 1 <= self.max_features <= 32
            or not 0 < self.minimum_score <= 1
            or not 0 < self.minimum_lift <= 1
        ):
            raise DatasetError(
                "invalid_univariate_config",
                "Invalid univariate folds, budget or thresholds.",
            )

    def thresholds(self) -> dict[str, object]:
        return {
            "minimum_balanced_accuracy": self.minimum_score,
            "minimum_baseline_lift": self.minimum_lift,
        }


class FoldScore(TypedDict):
    fold: int
    score: float
    baseline_score: float
    evaluated_records: int
    feature_type: str


@dataclass(frozen=True)
class UnivariateResult:
    columns: tuple[str, ...]
    classification: str
    evidence: dict[str, object]


def evaluate_univariate(
    dataset: Dataset,
    target_index: int,
    train_ids: list[int],
    seed: int,
    config: UnivariateConfig,
    *,
    constrained_split: bool,
    group_index: int | None = None,
    time: str | None = None,
) -> list[UnivariateResult]:
    config.validate()
    definition: dict[str, object] = {
        "metric": "balanced_accuracy",
        "baseline": "most_frequent",
        "folds": config.folds,
        "seed": seed,
        "evaluated_records": 0,
        "score": None,
        "baseline_score": None,
    }
    if (constrained_split and time is None) or (
        time is not None and group_index is not None
    ):
        return [
            UnivariateResult(
                (),
                "unsupported_analysis",
                {
                    **definition,
                    "reason": "Stratified inner folds do not enforce group or time constraints.",
                },
            )
        ]
    if len(train_ids) > 5000:
        return [
            UnivariateResult(
                (),
                "unsupported_analysis",
                {
                    **definition,
                    "reason": "Univariate evaluation supports up to 5,000 training records.",
                },
            )
        ]
    train_rows = [dataset.rows[i - 1] for i in train_ids]
    labeled = [row for row in train_rows if row[target_index].strip()]
    labels = [row[target_index] for row in labeled]
    counts = Counter(labels)
    definition["training_records"] = len(train_rows)
    definition["missing_target_records"] = len(train_rows) - len(labeled)
    if len(counts) < 2 or min(counts.values()) < config.folds:
        return [
            UnivariateResult(
                (),
                "insufficient_evidence",
                {
                    **definition,
                    "reason": "At least two classes with one record per class per fold are required.",
                },
            )
        ]
    if len(counts) > 20:
        return [
            UnivariateResult(
                (),
                "unsupported_analysis",
                {
                    **definition,
                    "reason": "Univariate evaluation supports up to 20 target classes.",
                },
            )
        ]

    from sklearn.dummy import DummyClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.metrics import balanced_accuracy_score
    from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import OneHotEncoder
    from sklearn.tree import DecisionTreeClassifier

    partitions = []
    cv = StratifiedKFold(n_splits=config.folds, shuffle=True, random_state=seed)
    if time is not None:
        records = [i for i in train_ids if dataset.rows[i - 1][target_index].strip()]
        indices = historical_folds(dataset, records, time, config.folds)
        definition["fold_strategy"] = "forward_only_expanding"
        if not indices:
            return [
                UnivariateResult(
                    (),
                    "insufficient_evidence",
                    {**definition, "reason": "Too few distinct historical timestamps."},
                )
            ]
    elif group_index is None:
        indices = list(cv.split(labels, labels))
    else:
        groups = connected_groups(
            [
                (
                    row[group_index],
                    tuple(
                        value
                        for j, value in enumerate(row)
                        if j not in {group_index, target_index}
                    ),
                )
                for row in labeled
            ]
        )
        if (
            any(not row[group_index].strip() for row in labeled)
            or len(set(groups)) < config.folds
        ):
            return [
                UnivariateResult(
                    (),
                    "insufficient_evidence",
                    {
                        **definition,
                        "reason": "Grouped evaluation needs enough complete, distinct groups.",
                    },
                )
            ]
        grouped = StratifiedGroupKFold(
            n_splits=config.folds, shuffle=True, random_state=seed
        )
        indices = list(grouped.split(labels, labels, groups))
    for fit, score in indices:
        fit_labels = [labels[i] for i in fit]
        score_labels = [labels[i] for i in score]
        if set(fit_labels) != set(counts) or set(score_labels) != set(counts):
            return [
                UnivariateResult(
                    (),
                    "insufficient_evidence",
                    {
                        **definition,
                        "reason": "Inner folds cannot preserve all classes without group overlap.",
                    },
                )
            ]
        dummy = DummyClassifier(strategy="most_frequent").fit(
            [[0]] * len(fit), fit_labels
        )
        baseline = float(
            balanced_accuracy_score(score_labels, dummy.predict([[0]] * len(score)))
        )
        partitions.append((fit, score, fit_labels, score_labels, baseline))

    features = [
        i
        for i in range(len(dataset.columns))
        if i != target_index and i != group_index and dataset.columns[i] != time
    ]
    results = []
    for index in features[: config.max_features]:
        name = dataset.columns[index]
        values = [row[index] for row in labeled]
        fold_scores: list[FoldScore] = []
        for fit, score, fit_labels, score_labels, baseline in partitions:
            fit_cells = [values[i] for i in fit]
            score_cells = [values[i] for i in score]
            is_numeric = numeric(fit_cells)
            if is_numeric:
                preprocess = SimpleImputer(strategy="median", keep_empty_features=True)
            else:
                preprocess = OneHotEncoder(handle_unknown="ignore", max_categories=32)
            model = make_pipeline(
                preprocess, DecisionTreeClassifier(max_depth=5, random_state=seed)
            )
            model.fit(design(fit_cells, is_numeric), fit_labels)
            predictions = model.predict(design(score_cells, is_numeric))
            fold_scores.append(
                {
                    "fold": len(fold_scores) + 1,
                    "score": float(balanced_accuracy_score(score_labels, predictions)),
                    "baseline_score": baseline,
                    "evaluated_records": len(score),
                    "feature_type": "numeric" if is_numeric else "categorical",
                }
            )
        score_mean = mean(fold["score"] for fold in fold_scores)
        baseline_mean = mean(fold["baseline_score"] for fold in fold_scores)
        lift = score_mean - baseline_mean
        flagged = score_mean >= config.minimum_score and lift >= config.minimum_lift
        results.append(
            UnivariateResult(
                (name,),
                "suspicious_heuristic" if flagged else "no_signal",
                {
                    **definition,
                    "score": score_mean,
                    "baseline_score": baseline_mean,
                    "lift": lift,
                    "evaluated_records": sum(
                        fold["evaluated_records"] for fold in fold_scores
                    ),
                    "fold_scores": fold_scores,
                },
            )
        )
    if len(features) > config.max_features:
        results.append(
            UnivariateResult(
                (),
                "unsupported_analysis",
                {
                    **definition,
                    "reason": "Only the first configured number of features is evaluated.",
                    "omitted_features": [
                        dataset.columns[i] for i in features[config.max_features :]
                    ],
                },
            )
        )
    return results


def design(cells: list[str], is_numeric: bool) -> list[list[float | str]]:
    if is_numeric:
        values = [number(value) for value in cells]
        # The tree converts inputs to float32. Bound finite values before fitting.
        return [
            [float("nan") if value is None else max(-1e12, min(1e12, value))]
            for value in values
        ]
    # Prefix observed tokens so blanks cannot collide with a literal category.
    return [["value:" + value if value.strip() else "missing:"] for value in cells]
