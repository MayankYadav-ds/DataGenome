from dataclasses import dataclass
from random import Random
from statistics import mean
from typing import Any

from .ingestion import DatasetError


@dataclass(frozen=True)
class ResamplingConfig:
    mode: str = "group"
    samples: int = 199
    seed: int = 42
    block_length: int = 5
    minimum_units: int = 8


def paired_interval(
    before: list[float],
    after: list[float],
    units: list[str],
    config: ResamplingConfig = ResamplingConfig(),
) -> dict[str, Any]:
    from math import isfinite

    if (
        len(before) != len(after)
        or len(units) != len(before)
        or not before
        or len(before) > 5000
        or any(not isfinite(v) or not 0 <= v <= 1 for v in before + after)
        or config.mode not in {"independent", "group", "temporal"}
        or not 39 <= config.samples <= 999
        or not 0 <= config.seed < 2**32
        or not 2 <= config.block_length <= 1000
        or not 8 <= config.minimum_units <= 100
    ):
        raise DatasetError(
            "resampling_config",
            "Invalid paired outcomes, unit IDs or resampling budget.",
        )
    if any(not value.strip() for value in units):
        raise DatasetError(
            "resampling_units", "Dependence-unit identifiers must be present."
        )
    rng = Random(config.seed)
    differences = [b - a for a, b in zip(before, after, strict=True)]
    blocks: list[list[int]] = []
    if config.mode in {"independent", "group"}:
        by_group: dict[str, list[int]] = {}
        for i, key in enumerate(
            units if config.mode == "group" else [str(i) for i in range(len(units))]
        ):
            by_group.setdefault(key, []).append(i)
        blocks = list(by_group.values())
    else:
        # Caller must provide outcomes ordered by time. Preserve ties within a timestamp.
        runs = [key for i, key in enumerate(units) if i == 0 or key != units[i - 1]]
        if len(set(runs)) != len(runs):
            raise DatasetError(
                "resampling_order", "Temporal units must form contiguous time blocks."
            )
        times = list(dict.fromkeys(units))
        positions: dict[str, list[int]] = {key: [] for key in times}
        for i, key in enumerate(units):
            positions[key].append(i)
        for start in range(0, len(times) - config.block_length + 1):
            blocks.append(
                [
                    i
                    for key in times[start : start + config.block_length]
                    for i in positions[key]
                ]
            )
    effective = (
        len(blocks)
        if config.mode in {"independent", "group"}
        else len(set(units)) // config.block_length
    )
    if effective < config.minimum_units:
        return {
            "status": "insufficient_evidence",
            "effective_units": effective,
            "interval": None,
        }
    estimates = []
    for _ in range(config.samples):
        chosen: list[int] = []
        draws = (
            len(blocks)
            if config.mode in {"independent", "group"}
            else (len(set(units)) + config.block_length - 1) // config.block_length
        )
        for _ in range(draws):
            chosen.extend(rng.choice(blocks))
        estimates.append(mean(differences[i] for i in chosen))
    estimates.sort()
    return {
        "status": "estimated",
        "paired_mean_change": mean(differences),
        "percentile_95": [
            estimates[int(0.025 * (len(estimates) - 1))],
            estimates[int(0.975 * (len(estimates) - 1))],
        ],
        "effective_units": effective,
        "resampling": config.mode,
        "bootstrap_samples": config.samples,
        "limitations": [
            "Percentile intervals are approximate and require representative resampling units.",
            "Temporal inputs must be supplied in chronological order.",
            "Group bootstrap weights observations within sampled clusters.",
            "Zero-width intervals with identical paired outcomes contain no evidence of equivalence.",
        ],
    }


def metric_intervals(
    actual: list[str],
    before: list[str],
    after: list[str],
    units: list[str],
    config: ResamplingConfig,
) -> dict[str, Any]:
    """Paired validation-only classification bootstrap; fixed class vocabulary."""
    from collections import Counter

    if not (len(actual) == len(before) == len(after) == len(units)) or not actual:
        raise DatasetError(
            "resampling_config", "Aligned nonempty predictions are required."
        )
    # Reuse the reviewed dependence-unit validation and effective sample gate.
    probe = paired_interval(
        [float(a == b) for a, b in zip(actual, before, strict=True)],
        [float(a == b) for a, b in zip(actual, after, strict=True)],
        units,
        config,
    )
    if probe["status"] != "estimated":
        return {name: probe for name in ("accuracy", "balanced_accuracy", "macro_f1")}
    classes = sorted(set(actual) | set(before) | set(after))
    if set(classes) != set(actual):
        return {
            name: {"status": "insufficient_class_support", "percentile_95": None}
            for name in ("accuracy", "balanced_accuracy", "macro_f1")
        }

    def scores(predicted: list[str], selected: list[int]) -> dict[str, float] | None:
        counts = Counter(actual[i] for i in selected)
        if any(not counts[label] for label in classes):
            return None
        recalls, f1s = [], []
        for label in classes:
            tp = sum(actual[i] == label and predicted[i] == label for i in selected)
            fp = sum(actual[i] != label and predicted[i] == label for i in selected)
            fn = counts[label] - tp
            recalls.append(tp / counts[label])
            f1s.append(2 * tp / (2 * tp + fp + fn))
        return {
            "accuracy": sum(actual[i] == predicted[i] for i in selected)
            / len(selected),
            "balanced_accuracy": mean(recalls),
            "macro_f1": mean(f1s),
        }

    groups: dict[str, list[int]] = {}
    for i, key in enumerate(units):
        groups.setdefault(key, []).append(i)
    if config.mode == "independent":
        groups = {str(i): [i] for i in range(len(actual))}
    keys = list(groups)
    blocks = (
        list(groups.values())
        if config.mode in {"independent", "group"}
        else [
            [
                i
                for key in keys[start : start + config.block_length]
                for i in groups[key]
            ]
            for start in range(len(keys) - config.block_length + 1)
        ]
    )
    draws = (
        len(blocks)
        if config.mode in {"independent", "group"}
        else (len(keys) + config.block_length - 1) // config.block_length
    )
    rng = Random(config.seed)
    estimates: dict[str, list[float]] = {
        name: [] for name in ("accuracy", "balanced_accuracy", "macro_f1")
    }
    all_ids = list(range(len(actual)))
    left, right = scores(before, all_ids), scores(after, all_ids)
    assert left is not None and right is not None
    for _ in range(config.samples):
        ids = [i for _ in range(draws) for i in rng.choice(blocks)]
        a, b = scores(before, ids), scores(after, ids)
        if a is not None and b is not None:
            for name in estimates:
                estimates[name].append(b[name] - a[name])
    result: dict[str, Any] = {}
    for name, values in estimates.items():
        values.sort()
        enough = len(values) >= max(39, int(0.9 * config.samples))
        result[name] = {
            "status": "estimated" if enough else "insufficient_class_support",
            "observed_change": right[name] - left[name],
            "percentile_95": [
                values[int(0.025 * (len(values) - 1))],
                values[int(0.975 * (len(values) - 1))],
            ]
            if enough
            else None,
            "valid_replicates": len(values),
            "configuration": __import__("dataclasses").asdict(config),
            "effective_units": probe["effective_units"],
        }
    return result
