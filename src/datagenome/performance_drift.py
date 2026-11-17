from math import isfinite
from typing import Any

from .fairness import binary_metrics
from .ingestion import Dataset, DatasetError
from .modeling import MODELS, ModelConfig, classification_pipeline, metrics
from .splits import Manifest, column, validate


def performance_drift(
    reference: Dataset,
    comparison: Dataset,
    target: str,
    manifest: Manifest,
    model: ModelConfig = ModelConfig(),
    *,
    group: str | None = None,
    min_support: int = 20,
    summary_only: bool = True,
) -> dict[str, Any]:
    """Fit once on reference training; score reference validation and labeled comparison."""
    validate(reference, manifest)
    if (
        reference.columns != comparison.columns
        or len(reference.rows) > 5000
        or len(comparison.rows) > 5000
        or len(reference.columns) > 65
        or not 5 <= min_support <= 1000
        or model.model not in MODELS
        or not 0 <= model.seed < 2**32
        or not 1 <= model.max_depth <= 16
        or not 1 <= model.trees <= 64
        or model.imputation not in {"median", "mean", "most_frequent"}
    ):
        raise DatasetError(
            "performance_drift_input",
            "Use aligned labeled CSV schemas and a bounded model.",
        )
    target_idx = column(reference, target)
    group_idx = column(reference, group) if group is not None else None
    excluded = {target, group, manifest.config.group, manifest.config.time}
    selected = [i for i, name in enumerate(reference.columns) if name not in excluded]
    train = manifest.partitions["train"]
    ref_ids = manifest.partitions["validation"]
    future_ids = list(
        range(len(reference.rows) + 1, len(reference.rows) + len(comparison.rows) + 1)
    )
    # Joint indexing lets the same train-fitted design transform both windows.
    data = Dataset(reference.columns, reference.rows + comparison.rows)
    labels = [data.rows[i - 1][target_idx] for i in train]
    classes = sorted(set(labels))
    if (
        not selected
        or not 2 <= len(classes) <= 20
        or any(not label.strip() for label in classes)
    ):
        raise DatasetError(
            "performance_drift_labels",
            "Use nonblank classification labels and predictive features.",
        )
    train_keys = {tuple(data.rows[i - 1][j] for j in selected) for i in train}
    if any(
        tuple(data.rows[i - 1][j] for j in selected) in train_keys
        for i in ref_ids + future_ids
    ):
        raise DatasetError(
            "performance_drift_contamination",
            "Evaluation rows share exact features with training.",
        )
    if any(data.rows[i - 1][target_idx] not in classes for i in ref_ids + future_ids):
        raise DatasetError(
            "performance_drift_labels",
            "Evaluation labels must be known during training.",
        )
    from threadpoolctl import threadpool_limits

    pipeline, _, design, _, _ = classification_pipeline(data, selected, train, model)
    periods: list[dict[str, Any]] = []
    with threadpool_limits(limits=1):
        pipeline.fit(design(train), labels)
        for ids in (ref_ids, future_ids):
            truth = [data.rows[i - 1][target_idx] for i in ids]
            x = design(ids)
            predicted = pipeline.predict(x).tolist()
            probs = pipeline.predict_proba(x)
            scores: dict[str, Any] = metrics(truth, predicted, probs, classes)
            ece = None
            if len(classes) == 2:
                ece = binary_metrics(
                    [v == classes[-1] for v in truth],
                    [v == classes[-1] for v in predicted],
                    probs[:, 1].tolist(),
                    False,
                )["calibration_ece_10"]
            group_rates = {}
            if group_idx is not None:
                for key in {data.rows[i - 1][group_idx] for i in ids}:
                    positions = [
                        j
                        for j, i in enumerate(ids)
                        if data.rows[i - 1][group_idx] == key
                    ]
                    if key.strip() and len(positions) >= min_support:
                        group_rates[key] = sum(
                            truth[j] == predicted[j] for j in positions
                        ) / len(positions)
            periods.append(
                {
                    "accuracy": scores["accuracy"],
                    "balanced_accuracy": scores["balanced_accuracy"],
                    "macro_f1": scores["macro_f1"],
                    "calibration_ece": ece,
                    "group_accuracy": group_rates,
                    "recall": {
                        key: value["recall"]
                        for key, value in scores["per_class"].items()
                    },
                }
            )
    before, after = periods
    changes = {
        key: after[key] - before[key]
        if before[key] is not None and after[key] is not None
        else None
        for key in ("accuracy", "balanced_accuracy", "macro_f1", "calibration_ece")
    }
    if not all(value is None or isfinite(value) for value in changes.values()):
        raise DatasetError(
            "performance_drift_undefined", "At least one outcome is nonfinite."
        )
    group_changes = {
        key: after["group_accuracy"][key] - before["group_accuracy"][key]
        for key in before["group_accuracy"].keys() & after["group_accuracy"].keys()
    }
    result = {
        "status": "evaluated",
        "same_fitted_model": True,
        "changes": changes,
        "eligible_group_count": len(group_changes),
        "worst_group_accuracy_change": min(group_changes.values(), default=None),
        "limitations": [
            "Both periods use one reference-trained model.",
            "Performance change alone does not identify its cause or establish concept drift.",
        ],
    }
    if not summary_only:
        result.update(
            reference=before, comparison=after, group_accuracy_changes=group_changes
        )
    return result
