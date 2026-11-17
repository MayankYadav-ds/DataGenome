from collections import Counter
from itertools import combinations
from statistics import median
from typing import Any

from .ingestion import Dataset, DatasetError
from .modeling import MODELS, ModelConfig, classification_pipeline
from .numeric import number
from .splits import Manifest, column, validate


def analyze_errors(
    dataset: Dataset,
    target: str,
    manifest: Manifest,
    model: ModelConfig = ModelConfig(),
    *,
    min_support: int = 10,
    summary_only: bool = False,
) -> dict[str, Any]:
    validate(dataset, manifest)
    if (
        not 5 <= min_support <= 500
        or len(dataset.rows) > 2000
        or len(dataset.columns) > 33
    ):
        raise DatasetError(
            "slice_budget",
            "Use 5–500 minimum support, at most 2,000 rows and 32 features.",
        )
    if (
        model.model not in MODELS
        or not 0 <= model.seed < 2**32
        or not 1 <= model.max_depth <= 16
        or not 1 <= model.trees <= 64
        or model.imputation not in {"mean", "median", "most_frequent"}
    ):
        raise DatasetError("invalid_slice_model", "Invalid model settings.")
    target_index = column(dataset, target)
    train = manifest.partitions["train"]
    ids = manifest.partitions["validation"]
    features = [
        j
        for j, name in enumerate(dataset.columns)
        if j != target_index
        and name not in {manifest.config.group, manifest.config.time}
    ]
    labels = [dataset.rows[i - 1][target_index] for i in train]
    truth = [dataset.rows[i - 1][target_index] for i in ids]
    if (
        not features
        or not 2 <= len(set(labels)) <= 20
        or set(truth) - set(labels)
        or any(not label.strip() for label in labels)
    ):
        raise DatasetError(
            "slice_input",
            "Use features and known validation labels with 2–20 training classes.",
        )

    from threadpoolctl import threadpool_limits

    pipeline, _, design, _, _ = classification_pipeline(dataset, features, train, model)
    with threadpool_limits(limits=1):
        pipeline.fit(design(train), labels)
        predictions = pipeline.predict(design(ids)).tolist()
    errors = [
        actual != predicted
        for actual, predicted in zip(truth, predictions, strict=True)
    ]
    rate = sum(errors) / len(errors)
    slices = []
    interaction_inputs: list[tuple[int, dict[str, Any], set[int]]] = []
    tested = 0

    def collect(definition: dict[str, Any], members: set[int]) -> bool:
        nonlocal tested
        tested += 1
        if len(members) < min_support or len(members) == len(ids):
            return False
        error_count = sum(errors[i] for i in members)
        error_rate = error_count / len(members)
        slices.append(
            {
                "definition": definition,
                "records": len(members),
                "errors": error_count,
                "error_rate": error_rate,
                "baseline_error_rate": rate,
                "absolute_error_difference": error_rate - rate,
                "relative_error_rate": error_rate / rate if rate else None,
                "accuracy": 1 - error_rate,
            }
        )
        return True

    for label in sorted(set(truth)):
        collect(
            {"kind": "class", "label": label},
            {i for i, value in enumerate(truth) if value == label},
        )
    for j in features:
        trained = [
            dataset.rows[i - 1][j] for i in train if dataset.rows[i - 1][j].strip()
        ]
        observed = [dataset.rows[i - 1][j] for i in ids]
        local_candidates: list[tuple[dict[str, Any], set[int]]] = [
            (
                {"kind": "missing", "feature": dataset.columns[j]},
                {i for i, value in enumerate(observed) if not value.strip()},
            )
        ]
        numeric_train = [number(value) for value in trained]
        if numeric_train and all(value is not None for value in numeric_train):
            threshold = median([value for value in numeric_train if value is not None])
            numeric_eval = [number(value) for value in observed]
            for side in ("le", "gt"):
                local_candidates.append(
                    (
                        {
                            "kind": "numeric",
                            "feature": dataset.columns[j],
                            "operator": side,
                            "threshold": threshold,
                        },
                        {
                            i
                            for i, value in enumerate(numeric_eval)
                            if value is not None
                            and (value <= threshold) == (side == "le")
                        },
                    )
                )
        else:
            for value, _ in Counter(trained).most_common(5):
                local_candidates.append(
                    (
                        {
                            "kind": "category",
                            "feature": dataset.columns[j],
                            "value": value,
                        },
                        {i for i, cell in enumerate(observed) if cell == value},
                    )
                )
        for definition, members in local_candidates:
            if collect(definition, members) and len(interaction_inputs) < 12:
                interaction_inputs.append((j, definition, members))
    for (i, a, left), (j, b, right) in combinations(interaction_inputs, 2):
        if i != j:
            collect({"kind": "intersection", "conditions": [a, b]}, left & right)
    slices.sort(key=lambda item: (-item["absolute_error_difference"], -item["records"]))
    result: dict[str, Any] = {
        "validation_records": len(ids),
        "baseline_error_rate": rate,
        "min_support": min_support,
        "candidate_count": tested,
        "supported_slices": len(slices),
        "limitations": [
            "Exploratory slice screening uses one validation partition.",
            "Candidate multiplicity can generate false alarms. No significance tests are performed.",
            "Confirm patterns independently before acting.",
        ],
    }
    if not summary_only:
        result["slices"] = slices[:30]
        result["dataset_sha256"] = manifest.dataset_sha256
        result["split_sha256"] = manifest.fingerprint
    return result
