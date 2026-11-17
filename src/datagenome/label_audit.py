from collections import Counter
from dataclasses import dataclass
from importlib.metadata import version
from typing import Any

from .folds import connected_groups, historical_folds
from .ingestion import Dataset, DatasetError
from .modeling import ModelConfig, classification_pipeline
from .splits import Manifest, column, validate


@dataclass(frozen=True)
class LabelAuditConfig:
    folds: int = 5
    minimum_alternative_probability: float = 0.60
    minimum_probability_gap: float = 0.30
    temporal_gap_seconds: int = 0
    temporal_window_seconds: int | None = None


def audit_labels(
    dataset: Dataset,
    target: str,
    manifest: Manifest,
    config: LabelAuditConfig = LabelAuditConfig(),
) -> dict[str, Any]:
    """Rank training labels by out-of-fold disagreement for human review."""
    if (
        type(config.folds) is not int
        or not 2 <= config.folds <= 5
        or not 0 < config.minimum_alternative_probability <= 1
        or not 0 < config.minimum_probability_gap <= 1
    ):
        raise DatasetError(
            "invalid_label_audit", "Use 2 to 5 folds and thresholds in (0, 1]."
        )
    validate(dataset, manifest)
    target_index = column(dataset, target)
    features = [
        i
        for i, name in enumerate(dataset.columns)
        if i != target_index
        and name not in {manifest.config.group, manifest.config.time}
    ]
    train = manifest.partitions["train"]
    records = [i for i in train if dataset.rows[i - 1][target_index].strip()]
    labels = [dataset.rows[i - 1][target_index] for i in records]
    report: dict[str, Any] = {
        "status": "evaluated",
        "method": "grouped_out_of_fold_logistic_regression",
        "folds": config.folds,
        "seed": manifest.config.seed,
        "thresholds": {
            "alternative_probability": config.minimum_alternative_probability,
            "probability_gap": config.minimum_probability_gap,
        },
        "features": len(features),
        "training_records": len(train),
        "missing_target_records": len(train) - len(records),
        "evaluated_records": 0,
        "candidates": [],
        "candidate_count": 0,
        "limitations": [
            "Model disagreement is a review heuristic and can reflect hard examples, "
            "minority groups, model error, or ambiguous labels.",
            "Model probabilities are uncalibrated.",
            "Folds group exact parsed feature vectors. Near duplicates may cross folds.",
            "The source dataset is never modified.",
        ],
    }

    def skip(status: str, reason: str) -> dict[str, Any]:
        return {**report, "status": status, "reason": reason}

    if not features or len(features) > 128 or len(train) > 5000:
        return skip(
            "unsupported",
            "Audit supports 1 to 128 features and up to 5,000 training rows.",
        )
    counts = Counter(labels)
    if len(counts) < 2 or min(counts.values()) < config.folds:
        return skip(
            "insufficient_evidence",
            "Each of at least two classes needs one record per fold.",
        )
    if len(counts) > 20:
        return skip("unsupported", "Audit supports up to 20 target classes.")

    from sklearn.model_selection import StratifiedGroupKFold
    from threadpoolctl import threadpool_limits

    partitions: list[tuple[list[int], list[int]]]
    if manifest.config.time is not None:
        partitions = historical_folds(
            dataset,
            records,
            manifest.config.time,
            config.folds,
            config.temporal_gap_seconds,
            config.temporal_window_seconds,
        )
        partitions = [
            (fit, score)
            for fit, score in partitions
            if len({labels[i] for i in fit}) >= 2
            and {labels[i] for i in score} <= {labels[i] for i in fit}
        ]
        report["method"] = "historical_out_of_fold_logistic_regression"
        report["temporal_gap_seconds"] = config.temporal_gap_seconds
        report["temporal_window_seconds"] = config.temporal_window_seconds
        report["limitations"][2] = (
            "Only strictly earlier observations are fitted. Near duplicates may recur over time."
        )
    else:
        group_index = (
            column(dataset, manifest.config.group) if manifest.config.group else None
        )
        keys = [
            (tuple(dataset.rows[i - 1][j] for j in features),)
            if group_index is None
            else (
                tuple(dataset.rows[i - 1][j] for j in features),
                dataset.rows[i - 1][group_index],
            )
            for i in records
        ]
        groups = connected_groups(keys)
        if len(set(groups)) < config.folds:
            return skip(
                "insufficient_evidence",
                "Too few distinct feature groups for the requested folds.",
            )
        splitter = StratifiedGroupKFold(
            n_splits=config.folds, shuffle=True, random_state=manifest.config.seed
        )
        partitions = [
            (fit.tolist(), score.tolist())
            for fit, score in splitter.split(labels, labels, groups)
        ]
        if any(
            len({labels[i] for i in fit}) != len(counts) or not score
            for fit, score in partitions
        ):
            return skip(
                "insufficient_evidence",
                "Grouped folds cannot retain every class in training.",
            )
    if not partitions:
        return skip(
            "insufficient_evidence",
            "No historical fold has enough prior label support.",
        )

    model = ModelConfig(seed=manifest.config.seed)
    candidates = []
    scored_records = 0
    disagreements = 0
    with threadpool_limits(limits=1):
        for fold, (fit, score) in enumerate(partitions, 1):
            training = [records[i] for i in fit]
            scoring = [records[i] for i in score]
            pipeline, _, design, _, _ = classification_pipeline(
                dataset, features, training, model
            )
            pipeline.fit(design(training), [labels[i] for i in fit])
            probabilities = pipeline.predict_proba(design(scoring))
            classes = pipeline.classes_.tolist()
            scored_records += len(scoring)
            for i, probabilities_for_row in zip(score, probabilities, strict=True):
                given = labels[i]
                predicted = classes[int(probabilities_for_row.argmax())]
                if given == predicted:
                    continue
                disagreements += 1
                given_score = float(probabilities_for_row[classes.index(given)])
                alternative_score = float(
                    probabilities_for_row[classes.index(predicted)]
                )
                gap = alternative_score - given_score
                if (
                    alternative_score >= config.minimum_alternative_probability
                    and gap >= config.minimum_probability_gap
                ):
                    candidates.append(
                        {
                            "record_id": records[i],
                            "fold": fold,
                            "classification": "suspected_label_issue",
                            "observed_label": given,
                            "model_preferred_label": predicted,
                            "observed_probability": given_score,
                            "alternative_probability": alternative_score,
                            "probability_gap": gap,
                        }
                    )
    candidates.sort(key=lambda item: (-item["probability_gap"], item["record_id"]))
    return {
        **report,
        "evaluated_records": scored_records,
        "unscored_labeled_records": len(records) - scored_records,
        "candidate_count": len(candidates),
        "disagreements": disagreements,
        "candidates": candidates,
        "dependencies": {"scikit-learn": version("scikit-learn")},
    }
