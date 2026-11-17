from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from random import Random
from typing import Any

from .identity import canonical, fingerprint
from .ingestion import Dataset, DatasetError

PARTITIONS = ("train", "validation", "test")


def column(dataset: Dataset, name: str | None) -> int:
    if name not in dataset.columns:
        raise DatasetError(
            "unknown_column", "Configured column must match a CSV header."
        )
    return dataset.columns.index(name)


def timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
        return (
            parsed.replace(tzinfo=UTC)
            if parsed.tzinfo is None
            else parsed.astimezone(UTC)
        )
    except (ValueError, OverflowError):
        raise DatasetError(
            "invalid_timestamp", "Expected ISO 8601 timestamps."
        ) from None


@dataclass(frozen=True)
class SplitConfig:
    strategy: str = "random"
    ratios: tuple[float, float, float] = (0.6, 0.2, 0.2)
    seed: int = 42
    group: str | None = None
    time: str | None = None


@dataclass(frozen=True)
class Manifest:
    dataset_sha256: str
    config: SplitConfig
    partitions: dict[str, list[int]]

    @property
    def fingerprint(self) -> str:
        return fingerprint(asdict(self))


def restore(report: Any) -> Manifest:
    try:
        value = report["split"]
        cfg = value["config"]
        config = SplitConfig(
            cfg["strategy"],
            tuple(cfg["ratios"]),
            cfg["seed"],
            cfg["group"],
            cfg["time"],
        )
        partitions = value["partitions"]
        if not isinstance(partitions, dict) or not all(
            isinstance(ids, list) and all(type(i) is int for i in ids)
            for ids in partitions.values()
        ):
            raise ValueError
        manifest = Manifest(value["dataset_sha256"], config, partitions)
        if manifest.fingerprint != value["fingerprint"]:
            raise ValueError
        return manifest
    except (TypeError, KeyError, ValueError, OverflowError):
        raise DatasetError(
            "invalid_manifest", "Expected a valid DataGenome split report."
        ) from None


def validate(dataset: Dataset, manifest: Manifest) -> None:
    groups = manifest.partitions
    if manifest.dataset_sha256 != canonical(dataset) or set(groups) != set(PARTITIONS):
        raise DatasetError("invalid_manifest", "Manifest does not match the dataset.")
    ids = [index for name in PARTITIONS for index in groups[name]]
    if any(not groups[name] for name in PARTITIONS) or sorted(ids) != list(
        range(1, len(dataset.rows) + 1)
    ):
        raise DatasetError(
            "invalid_manifest", "Partitions must cover every record exactly once."
        )
    config = manifest.config
    if config.strategy == "group":
        feature = column(dataset, config.group)
        keys = [
            {dataset.rows[index - 1][feature] for index in groups[name]}
            for name in PARTITIONS
        ]
        if any(not key.strip() for part in keys for key in part) or sum(
            map(len, keys)
        ) != len(set.union(*keys)):
            raise DatasetError(
                "invalid_manifest", "Group identifiers must be present and disjoint."
            )
    if config.strategy == "chronological":
        feature = column(dataset, config.time)
        dates = [
            [timestamp(dataset.rows[i - 1][feature]) for i in groups[name]]
            for name in PARTITIONS
        ]
        if any(max(left) >= min(right) for left, right in zip(dates, dates[1:])):
            raise DatasetError(
                "invalid_manifest",
                "Chronological partitions overlap or are out of order.",
            )


def split(dataset: Dataset, config: SplitConfig, target: str | None = None) -> Manifest:
    n = len(dataset.rows)
    strategy = config.strategy
    ratios = config.ratios
    if (
        strategy not in {"random", "stratified", "group", "chronological"}
        or len(ratios) != 3
        or not all(0 < ratio < 1 for ratio in ratios)
        or abs(sum(ratios) - 1) > 1e-9
        or not 0 <= config.seed < 2**32
        or bool(config.group) != (strategy == "group")
        or bool(config.time) != (strategy == "chronological")
        or (target is not None and target in (config.group, config.time))
    ):
        raise DatasetError(
            "invalid_split", "Incompatible split options or invalid ratios/seed."
        )
    rng = Random(config.seed)
    ids = list(range(1, n + 1))
    partitions: dict[str, list[int]] = {name: [] for name in PARTITIONS}

    def assign(units: list[list[int]]) -> None:
        if len(units) < 3:
            raise DatasetError(
                "insufficient_split_samples",
                "Each splitting stratum needs three units.",
            )
        size = len(units)
        train = min(size - 2, max(1, round(size * ratios[0])))
        validation = min(size - 1, max(train + 1, round(size * sum(ratios[:2]))))
        for name, batch in zip(
            PARTITIONS,
            (units[:train], units[train:validation], units[validation:]),
            strict=True,
        ):
            partitions[name].extend(index for unit in batch for index in unit)

    if strategy == "random":
        rng.shuffle(ids)
        assign([[index] for index in ids])
    else:
        feature = column(
            dataset,
            {"stratified": target, "group": config.group, "chronological": config.time}[
                strategy
            ],
        )
        buckets: dict[str | datetime, list[int]] = defaultdict(list)
        for index, row in enumerate(dataset.rows, 1):
            value = row[feature]
            if not value.strip():
                raise DatasetError("missing_split_key", "Split keys must be present.")
            key = timestamp(value) if strategy == "chronological" else value
            buckets[key].append(index)
        if strategy == "stratified":
            for records in buckets.values():
                rng.shuffle(records)
                assign([[index] for index in records])
        else:
            units = list(buckets.values())
            if strategy == "group":
                rng.shuffle(units)
            else:
                units = [buckets[key] for key in sorted(buckets)]
            assign(units)
    result = Manifest(
        canonical(dataset),
        config,
        {key: sorted(ids) for key, ids in partitions.items()},
    )
    validate(dataset, result)
    return result
