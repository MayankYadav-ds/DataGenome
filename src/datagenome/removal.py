from random import Random
from time import perf_counter
from typing import Any

from .ingestion import Dataset, DatasetError
from .label_audit import audit_labels
from .modeling import ModelConfig, fit_baseline
from .splits import Manifest, column
from .valuation import ValuationConfig, value_data


def compare_removal(
    dataset: Dataset,
    target: str,
    manifest: Manifest,
    config: ValuationConfig,
    model: ModelConfig,
    fraction: float,
) -> dict[str, Any]:
    if not 0 < fraction <= 0.20:
        raise DatasetError(
            "invalid_removal_fraction", "Use a removal fraction in (0, 0.20]."
        )
    if len(dataset.rows) > 2500 or len(dataset.columns) > 33:
        raise DatasetError(
            "removal_size_limit", "Removal supports 2,500 rows and 32 features.", 413
        )
    start = perf_counter()
    valuation = value_data(dataset, target, manifest, config, model=model)
    train = manifest.partitions["train"]
    count = int(len(train) * fraction)
    if count < 1:
        raise DatasetError(
            "insufficient_removal_count", "The fraction must select at least one row."
        )
    index = column(dataset, target)
    groups: dict[str, list[int]] = {}
    for i in train:
        groups.setdefault(dataset.rows[i - 1][index], []).append(i)
    label_min = min(map(len, groups.values()))
    minority = sorted(label for label, ids in groups.items() if len(ids) == label_min)
    # Per-class caps prevent a ranking from concentrating all removals in one class.
    limits = {
        label: min(len(ids) - 1, int(len(ids) * fraction))
        for label, ids in groups.items()
    }
    count = min(count, sum(limits.values()))
    if not count:
        raise DatasetError(
            "minority_removal_guard",
            "Per-class removal caps leave no eligible removals.",
        )

    low = sorted(valuation["records"], key=lambda row: (row["score"], row["record_id"]))
    high = valuation["records"]
    randomized = sorted(train)
    Random(config.seed).shuffle(randomized)
    audit = audit_labels(dataset, target, manifest)
    candidates = {
        "lowest": [row["record_id"] for row in low],
        "highest": [row["record_id"] for row in high],
        "random": randomized,
        "label_audit": [row["record_id"] for row in audit["candidates"]],
    }
    baseline = fit_baseline(dataset, target, manifest, model)["metrics"]["validation"]
    arms: dict[str, Any] = {}
    for name, ordering in candidates.items():
        remaining = limits.copy()
        removed = []
        for i in ordering:
            label = dataset.rows[i - 1][index]
            if remaining[label] > 0:
                removed.append(i)
                remaining[label] -= 1
                if len(removed) == count:
                    break
        if len(removed) != count:
            arms[name] = {
                "status": "insufficient_candidates",
                "eligible_count": len(removed),
            }
            continue
        excluded = set(removed)
        fit = fit_baseline(
            dataset,
            target,
            manifest,
            model,
            train_ids=[i for i in train if i not in excluded],
        )
        metrics = fit["metrics"]["validation"]
        recalls = {}
        for label, row in baseline["per_class"].items():
            before, after = row["recall"], metrics["per_class"][label]["recall"]
            recalls[label] = (
                after - before if before is not None and after is not None else None
            )
        arms[name] = {
            "status": "evaluated",
            "removed_ids": removed,
            "metrics": metrics,
            "accuracy_change": metrics["accuracy"] - baseline["accuracy"],
            "class_recall_change": recalls,
            "minority_recall_degraded": any(
                (change := recalls.get(label)) is not None and change < 0
                for label in minority
            ),
            "elapsed_seconds": fit["train_seconds"] + fit["evaluate_seconds"],
        }
    return {
        "status": "evaluated",
        "held_out_evaluated": False,
        "baseline": baseline,
        "arms": arms,
        "minority_classes": minority,
        "matched_removal_count": count,
        "fraction": fraction,
        "class_caps": limits,
        "elapsed_seconds": perf_counter() - start,
        "valuation_method": config.method,
        "split_sha256": manifest.fingerprint,
        "limitations": [
            "Scores describe one validation partition used for ranking and comparison.",
            "Class caps protect representation, not subgroup fairness or recall.",
            "Source records are never modified.",
        ],
    }
