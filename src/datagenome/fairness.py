from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations
from math import sqrt
from statistics import median
from typing import Any

from .ingestion import Dataset, DatasetError
from .modeling import MODELS, ModelConfig, classification_pipeline
from .numeric import number
from .splits import Manifest, column, validate


@dataclass(frozen=True)
class FairnessConfig:
    attributes: tuple[str, ...]
    positive_label: str | None = None
    min_support: int = 20
    min_class_count: int = 5
    independent_rows: bool = False
    summary_only: bool = True


def proportion(n: int, total: int, interval: bool) -> dict[str, Any]:
    if not total:
        return {"value": None, "reason": "zero_denominator", "wilson_95": None}
    rate = n / total
    z = 1.95996398454
    scale = 1 + z * z / total
    mid = (rate + z * z / (2 * total)) / scale
    half = z * sqrt(rate * (1 - rate) / total + z * z / (4 * total**2)) / scale
    return {
        "value": rate,
        "reason": None,
        "wilson_95": [max(0.0, mid - half), min(1.0, mid + half)] if interval else None,
    }


def binary_metrics(
    truth: Sequence[bool],
    predicted: Sequence[bool],
    probabilities: Sequence[float],
    interval: bool,
) -> dict[str, Any]:
    tp = sum(a and b for a, b in zip(truth, predicted, strict=True))
    fp = sum(not a and b for a, b in zip(truth, predicted, strict=True))
    fn = sum(a and not b for a, b in zip(truth, predicted, strict=True))
    tn = len(truth) - tp - fp - fn
    tpr, fpr = proportion(tp, tp + fn, interval), proportion(fp, fp + tn, interval)
    metrics: dict[str, Any] = {
        "accuracy": proportion(tp + tn, len(truth), interval),
        "precision": proportion(tp, tp + fp, interval),
        "recall": tpr,
        "true_positive_rate": tpr,
        "false_positive_rate": fpr,
        "false_negative_rate": proportion(fn, tp + fn, interval),
        "selection_rate": proportion(tp + fp, len(truth), interval),
        "f1": proportion(2 * tp, 2 * tp + fp + fn, False),
    }
    balanced = (tpr["value"] + 1 - fpr["value"]) / 2 if tp + fn and fp + tn else None
    metrics["balanced_accuracy"] = {
        "value": balanced,
        "reason": None if balanced is not None else "missing_observed_class",
        "wilson_95": None,
    }
    metrics["confusion_matrix"] = [[tn, fp], [fn, tp]]
    bins: dict[int, list[tuple[float, bool]]] = {}
    for p, y in zip(probabilities, truth, strict=True):
        bins.setdefault(min(int(p * 10), 9), []).append((p, y))
    metrics["calibration_ece_10"] = sum(
        abs(sum(p - y for p, y in values)) for values in bins.values()
    ) / len(truth)
    return metrics


def audit_fairness(
    dataset: Dataset,
    target: str,
    manifest: Manifest,
    config: FairnessConfig,
    model: ModelConfig = ModelConfig(),
    *,
    excluded_records: tuple[int, ...] = (),
) -> dict[str, Any]:
    validate(dataset, manifest)
    if (
        not 1 <= len(config.attributes) <= 3
        or len(set(config.attributes)) != len(config.attributes)
        or target in config.attributes
        or not 5 <= config.min_support <= 1000
        or not 1 <= config.min_class_count <= 100
        or len(dataset.rows) > 5000
        or len(dataset.columns) > 65
    ):
        raise DatasetError(
            "fairness_config",
            "Use 1–3 distinct audit attributes, valid support thresholds and a bounded dataset.",
        )
    if (
        model.model not in MODELS
        or not 0 <= model.seed < 2**32
        or not 1 <= model.max_depth <= 16
        or not 1 <= model.trees <= 64
        or model.imputation not in {"median", "mean", "most_frequent"}
    ):
        raise DatasetError("fairness_model", "Invalid audit model configuration.")
    attributes = [column(dataset, name) for name in config.attributes]
    label = column(dataset, target)
    train_original = manifest.partitions["train"]
    held = manifest.partitions["validation"]
    excluded = set(excluded_records)
    if not excluded <= set(train_original) or len(excluded) > len(train_original) // 5:
        raise DatasetError(
            "fairness_intervention", "Exclude at most 20% of training records only."
        )
    train = [i for i in train_original if i not in excluded]
    labels = [dataset.rows[i - 1][label] for i in train]
    classes = sorted(set(labels))
    positive = (
        config.positive_label
        if config.positive_label is not None
        else (classes[-1] if classes else "")
    )
    if (
        len(classes) != 2
        or positive not in classes
        or any(not value.strip() for value in classes)
        or {dataset.rows[i - 1][label] for i in held} - set(classes)
    ):
        raise DatasetError(
            "fairness_binary", "Use binary training labels and known validation labels."
        )
    original_classes = Counter(dataset.rows[i - 1][label] for i in train_original)
    retained_classes = Counter(labels)
    if any(
        retained_classes[key] < min(value, config.min_class_count)
        for key, value in original_classes.items()
    ):
        raise DatasetError(
            "fairness_class_guard",
            "Removal violates the minimum retained class support.",
        )
    for size in range(1, len(attributes) + 1):
        for fields in combinations(attributes, size):
            before = Counter(
                tuple(dataset.rows[i - 1][j] for j in fields) for i in train_original
            )
            after = Counter(
                tuple(dataset.rows[i - 1][j] for j in fields) for i in train
            )
            if len(before) > 256:
                raise DatasetError(
                    "fairness_group_budget",
                    "Audit supports up to 256 training groups per intersection.",
                )
            if any(
                after[key] < min(count, config.min_support)
                for key, count in before.items()
            ):
                raise DatasetError(
                    "fairness_group_guard",
                    "Removal violates the minimum retained group support.",
                )
    excluded_names = {
        *config.attributes,
        manifest.config.group,
        manifest.config.time,
        target,
    }
    features = [
        i for i, name in enumerate(dataset.columns) if name not in excluded_names
    ]
    if not features:
        raise DatasetError(
            "fairness_features", "At least one non-audit feature is required."
        )

    from threadpoolctl import threadpool_limits

    pipeline, _, design, _, _ = classification_pipeline(dataset, features, train, model)
    with threadpool_limits(limits=1):
        pipeline.fit(design(train), labels)
        matrix = design(held)
        predicted = [value == positive for value in pipeline.predict(matrix)]
        probabilities = pipeline.predict_proba(matrix)[
            :, classes.index(positive)
        ].tolist()
    actual = [dataset.rows[i - 1][label] == positive for i in held]
    interval = config.independent_rows and manifest.config.strategy not in {
        "group",
        "chronological",
    }
    reports: list[dict[str, Any]] = []
    for size in range(1, len(attributes) + 1):
        for fields in combinations(attributes, size):

            def key(i: int) -> tuple[str, ...]:
                return tuple(dataset.rows[i - 1][j] for j in fields)

            by_group: dict[tuple[str, ...], list[int]] = {}
            for i, record in enumerate(held):
                by_group.setdefault(key(record), []).append(i)
            if len(by_group) > 256:
                raise DatasetError(
                    "fairness_group_budget",
                    "Audit supports up to 256 validation groups per intersection.",
                )
            train_counts = Counter(key(i) for i in train)
            train_positive = Counter(
                key(i) for i in train if dataset.rows[i - 1][label] == positive
            )
            eligible: list[dict[str, Any]] = []
            suppressed = 0
            for group, ids in sorted(by_group.items()):
                true = [actual[i] for i in ids]
                if (
                    len(ids) < config.min_support
                    or sum(true) < config.min_class_count
                    or len(ids) - sum(true) < config.min_class_count
                    or any(not value.strip() for value in group)
                ):
                    suppressed += 1
                    continue
                report = {
                    "group": group,
                    "support": len(ids),
                    "training_support": train_counts[group],
                    "training_share": train_counts[group] / len(train),
                    "validation_share": len(ids) / len(held),
                    "validation_positive": sum(true),
                    "metrics": binary_metrics(
                        true,
                        [predicted[i] for i in ids],
                        [probabilities[i] for i in ids],
                        interval,
                    ),
                }
                if train_counts[group] >= config.min_support:
                    report["training_positive"] = train_positive[group]
                else:
                    report["training_support"] = None
                    report["training_share"] = None
                if not config.summary_only:
                    feature_summaries = []
                    for j in features[:16]:
                        cells = [dataset.rows[held[i] - 1][j] for i in ids]
                        present = [number(cell) for cell in cells if cell.strip()]
                        feature_summaries.append(
                            {
                                "feature": dataset.columns[j],
                                "missing_rate": sum(not cell.strip() for cell in cells)
                                / len(cells),
                                "numeric_median": median(
                                    [value for value in present if value is not None]
                                )
                                if len(present) >= config.min_support
                                and all(value is not None for value in present)
                                else None,
                            }
                        )
                    report["feature_summaries"] = feature_summaries
                eligible.append(report)

            def values(metric: str) -> list[float]:
                return [
                    item["metrics"][metric]["value"]
                    for item in eligible
                    if item["metrics"][metric]["value"] is not None
                ]

            def gap(metric: str) -> float | None:
                v = values(metric)
                return max(v) - min(v) if len(v) >= 2 else None

            selection = values("selection_rate")
            tpr, fpr = gap("true_positive_rate"), gap("false_positive_rate")
            disparity = {
                "demographic_parity_difference": gap("selection_rate"),
                "demographic_parity_ratio": min(selection) / max(selection)
                if len(selection) >= 2 and max(selection) > 0
                else None,
                "equal_opportunity_difference": tpr,
                "equalized_odds_difference": max(tpr, fpr)
                if tpr is not None and fpr is not None
                else None,
                "false_positive_rate_gap": fpr,
                "false_negative_rate_gap": gap("false_negative_rate"),
                "worst_group_accuracy": min(values("accuracy"), default=None),
                "accuracy_gap": gap("accuracy"),
                "status": "evaluated"
                if len(eligible) >= 2
                else "insufficient_evidence",
            }
            entry = {
                "intersection_width": size,
                "eligible_groups": len(eligible),
                "suppressed_groups": suppressed,
                "disparities": disparity,
            }
            if not config.summary_only:
                entry["attributes"] = [dataset.columns[j] for j in fields]
                entry["groups"] = eligible
            reports.append(entry)
    overall = binary_metrics(actual, predicted, probabilities, interval)
    output = {
        "status": "evaluated",
        "partition": "validation",
        "comparisons": reports,
        "overall": overall
        if not config.summary_only
        else {
            "accuracy": overall["accuracy"],
            "balanced_accuracy": overall["balanced_accuracy"],
        },
        "intervals": "wilson_iid" if interval else "not_computed",
        "limitations": [
            "Descriptive disparities can differ by metric. They do not establish unfair treatment.",
            "Max–min comparison uses eligible groups without a fixed reference.",
            "Uncertainty is omitted unless independent rows are explicitly asserted.",
        ],
    }
    unequal = [
        i
        for i, item in enumerate(reports)
        if (gap := item["disparities"]["equal_opportunity_difference"]) is not None
        and gap >= 0.1
    ]
    output["recommendations"] = (
        [
            {
                "evidence": {"comparison_indices": unequal, "minimum_recall_gap": 0.1},
                "action": "Review label quality, representation, and error cases in the eligible groups.",
                "potential_benefit": "Identify a testable explanation for disparate recall.",
                "risk": "Group differences can reflect sampling, measurement, or model error.",
                "validation": "Prespecify a follow-up and evaluate on independent records.",
                "contraindications": [
                    "Small or dependent groups require separate uncertainty methods."
                ],
                "limitations": [
                    "This screen does not establish unfair treatment or justify demographic exclusion."
                ],
            }
        ]
        if unequal
        else []
    )
    if not config.summary_only:
        output["positive_label"] = positive
        output["audit_features_excluded"] = sorted(
            name for name in excluded_names if name and name != target
        )
    return output


def compare_fairness(
    dataset: Dataset,
    target: str,
    manifest: Manifest,
    config: FairnessConfig,
    model: ModelConfig,
    excluded_records: tuple[int, ...],
) -> dict[str, Any]:
    from dataclasses import replace

    if not excluded_records or len(set(excluded_records)) != len(excluded_records):
        raise DatasetError(
            "fairness_intervention", "Supply unique training record IDs."
        )
    detailed = replace(config, summary_only=False)
    baseline = audit_fairness(dataset, target, manifest, detailed, model)
    candidate = audit_fairness(
        dataset, target, manifest, detailed, model, excluded_records=excluded_records
    )
    delta = (
        candidate["overall"]["accuracy"]["value"]
        - baseline["overall"]["accuracy"]["value"]
    )
    changes = []
    for left, right in zip(
        baseline["comparisons"], candidate["comparisons"], strict=True
    ):
        recalls = [
            {
                "group": b["group"],
                "recall_change": b["metrics"]["recall"]["value"]
                - a["metrics"]["recall"]["value"],
                "training_support_change": b["training_support"] - a["training_support"]
                if a["training_support"] is not None
                and b["training_support"] is not None
                else None,
            }
            for a, b in zip(left["groups"], right["groups"], strict=True)
        ]
        disparities = {
            key: right["disparities"][key] - value
            if value is not None and right["disparities"][key] is not None
            else None
            for key, value in left["disparities"].items()
            if key != "status"
        }
        item = {
            "intersection_width": left["intersection_width"],
            "disparity_changes": disparities,
            "groups_with_recall_degradation": sum(
                row["recall_change"] < 0 for row in recalls
            ),
        }
        if not config.summary_only:
            item["groups"] = recalls
            item["attributes"] = left["attributes"]
        changes.append(item)
    return {
        "status": "exploratory",
        "accuracy_change": delta,
        "removed_count": len(excluded_records),
        "subgroup_changes": changes,
        "held_out_evaluated": False,
        "limitations": [
            "Subgroup changes are descriptive; aggregate gains can conceal subgroup deterioration.",
            "No intervention is automatically recommended or applied.",
        ],
    }
