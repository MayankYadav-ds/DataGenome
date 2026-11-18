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
        or config.mode not in {"group", "temporal"}
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
    if config.mode == "group":
        by_group: dict[str, list[int]] = {}
        for i, key in enumerate(units):
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
        if config.mode == "group"
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
            if config.mode == "group"
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
