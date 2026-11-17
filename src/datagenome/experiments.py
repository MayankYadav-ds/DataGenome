from dataclasses import asdict, dataclass, replace
from typing import Any

from .identity import canonical
from .ingestion import Dataset, DatasetError
from .leakage import LeakageConfig, inspect_leakage
from .modeling import ModelConfig, fit_baseline
from .splits import Manifest, column, validate


@dataclass(frozen=True)
class Intervention:
    remove_duplicates: bool = False
    constant_features: tuple[str, ...] = ()
    suspected_features: tuple[str, ...] = ()
    excluded_records: tuple[int, ...] = ()
    imputation: str | None = None


def active(intervention: Intervention) -> bool:
    return any(
        (
            intervention.remove_duplicates,
            intervention.constant_features,
            intervention.suspected_features,
            intervention.excluded_records,
            intervention.imputation,
        )
    )


def prepare(
    dataset: Dataset, target: str, manifest: Manifest, intervention: Intervention
) -> tuple[list[int], list[str]]:
    validate(dataset, manifest)
    original = manifest.partitions["train"]
    if not set(intervention.excluded_records) <= set(original):
        raise DatasetError(
            "held_out_protected", "Excluded records must belong to training."
        )
    features = sorted(
        set(intervention.constant_features + intervention.suspected_features)
    )
    if target in features:
        raise DatasetError("invalid_excluded_feature", "The target cannot be excluded.")
    for name in intervention.constant_features:
        index = column(dataset, name)
        unique = {
            dataset.rows[i - 1][index]
            for i in original
            if dataset.rows[i - 1][index].strip()
        }
        if len(unique) != 1:
            raise DatasetError(
                "nonconstant_feature",
                "Selected constant feature is not constant in train.",
            )
    dropped = set(intervention.excluded_records)
    selected = [record for record in original if record not in dropped]
    if intervention.remove_duplicates:
        seen = set()
        retained = []
        for record in selected:
            row = dataset.rows[record - 1]
            if row not in seen:
                retained.append(record)
            seen.add(row)
        selected = retained
    for name in features:
        column(dataset, name)
    return selected, features


def compare(
    dataset: Dataset,
    target: str,
    manifest: Manifest,
    intervention: Intervention,
    model: ModelConfig = ModelConfig(),
    leakage: LeakageConfig = LeakageConfig(),
) -> dict[str, Any]:
    if not active(intervention):
        raise DatasetError(
            "missing_intervention", "Select an explicit training intervention."
        )
    selected, features = prepare(dataset, target, manifest, intervention)
    original = manifest.partitions["train"]
    violations = [
        signal.id
        for signal in inspect_leakage(dataset, target, manifest, leakage)
        if signal.classification == "confirmed_violation"
    ]
    if violations:
        return {
            "status": "compromised",
            "violations": violations,
            "limitations": [
                "A confirmed split or configuration violation blocks comparison.",
                "Correct the manifest through an explicit operation.",
            ],
        }
    before = fit_baseline(dataset, target, manifest, model)
    after = fit_baseline(
        dataset,
        target,
        manifest,
        replace(model, imputation=intervention.imputation or model.imputation),
        train_ids=selected,
        exclude=features,
    )
    left, right = before["metrics"]["validation"], after["metrics"]["validation"]
    differences = {
        key: right[key] - left[key]
        for key in (
            "accuracy",
            "balanced_accuracy",
            "macro_f1",
            "weighted_f1",
            "roc_auc",
            "average_precision",
            "log_loss",
        )
        if left[key] is not None and right[key] is not None
    }
    change = differences["accuracy"]
    columns = tuple(name for name in dataset.columns if name not in features)
    indices = [dataset.columns.index(name) for name in columns]
    derived = Dataset(
        columns, tuple(tuple(dataset.rows[i - 1][j] for j in indices) for i in selected)
    )
    return {
        "status": "compared",
        "original": before,
        "modified": after,
        "validation_differences": differences,
        "accuracy_outcome": "improved"
        if change > 0
        else "degraded"
        if change < 0
        else "unchanged",
        "affected_records": len(original) - len(selected),
        "affected_features": len(features),
        "intervention": asdict(intervention),
        "modified_training_sha256": canonical(derived),
        "parent_dataset_sha256": manifest.dataset_sha256,
        "held_out_evaluated": False,
        "limitations": [
            "One validation split does not quantify uncertainty.",
            "Intervention selection uses validation only.",
        ],
    }
