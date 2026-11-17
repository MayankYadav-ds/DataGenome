from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from math import sqrt
from statistics import correlation

from .duplicates import near_pairs
from .identity import fingerprint
from .ingestion import Dataset, DatasetError
from .numeric import number
from .splits import PARTITIONS, Manifest, column, timestamp, validate


@dataclass(frozen=True)
class Signal:
    id: str
    classification: str
    method: str
    severity: str
    columns: tuple[str, ...]
    records: tuple[int, ...]
    evidence: dict[str, object]
    thresholds: dict[str, object]
    remediation: str
    limitations: str


@dataclass(frozen=True)
class LeakageConfig:
    group: str | None = None
    time: str | None = None
    cutoff: str | None = None
    unavailable: tuple[str, ...] = ()
    candidate_limit: int = 10000
    association_threshold: float = 0.9


def feature_rows(dataset: Dataset, target: str | None) -> list[tuple[str, ...]]:
    return [
        tuple(
            value
            for name, value in zip(dataset.columns, row, strict=True)
            if name != target
        )
        for row in dataset.rows
    ]


def inspect_leakage(
    dataset: Dataset,
    target: str,
    manifest: Manifest,
    config: LeakageConfig = LeakageConfig(),
) -> list[Signal]:
    if not 0 < config.association_threshold <= 1:
        raise DatasetError(
            "invalid_association_threshold", "Use a threshold in (0, 1]."
        )
    validate(dataset, manifest)
    target_index = column(dataset, target)
    output: list[Signal] = []

    def emit(
        method: str,
        classification: str,
        columns: tuple[str, ...],
        evidence: dict[str, object],
        remediation: str,
        limitations: str,
        records: tuple[int, ...] = (),
        thresholds: dict[str, object] | None = None,
        scope: str = "",
    ) -> None:
        output.append(
            Signal(
                method + ":" + fingerprint([columns, scope]),
                classification,
                method,
                {
                    "confirmed_violation": "high",
                    "insufficient_evidence": "info",
                    "unsupported_analysis": "info",
                }.get(classification, "warning"),
                columns,
                records[:100],
                evidence,
                thresholds or {},
                remediation,
                limitations,
            )
        )

    train = manifest.partitions["train"]
    for index, name in enumerate(dataset.columns):
        if index == target_index:
            continue
        pairs = [
            (dataset.rows[i - 1][index], dataset.rows[i - 1][target_index])
            for i in train
        ]
        pairs = [
            (value, label) for value, label in pairs if value.strip() and label.strip()
        ]
        labels = {label for _, label in pairs}
        values = {value for value, _ in pairs}
        if len(pairs) < 6 or len(labels) < 2:
            emit(
                "target_association_insufficient",
                "insufficient_evidence",
                (name,),
                {"paired": len(pairs), "classes": len(labels)},
                "Collect more labeled training records.",
                "Requires paired training evidence.",
                thresholds={"minimum_pairs": 6, "minimum_classes": 2},
            )
        elif len(values) >= 2:
            if all(value == label for value, label in pairs):
                method = "target_copy"
            elif len(values) == len(labels) == len(set(pairs)) and len(
                pairs
            ) >= 3 * len(labels):
                method = "target_bijection"
            else:
                method = ""
            if method:
                emit(
                    method,
                    "strong_statistical_evidence",
                    (name,),
                    {"paired": len(pairs)},
                    "Audit feature provenance and availability.",
                    "Training-only value agreement can occur in valid predictors.",
                    thresholds={"minimum_pairs": 6, "minimum_pairs_per_class_ratio": 3},
                )
            elif len(labels) == 2:
                numeric = [
                    (number(value), float(label == min(labels)))
                    for value, label in pairs
                ]
                x = [value for value, _ in numeric if value is not None]
                if len(x) == len(pairs) and len(set(x)) > 1:
                    scale = max(abs(value) for value in x) or 1
                    try:
                        strength = abs(
                            correlation(
                                [value / scale for value in x],
                                [label for _, label in numeric],
                            )
                        )
                    except (ValueError, ArithmeticError):
                        continue
                    if strength >= config.association_threshold:
                        emit(
                            "predictive_association",
                            "suspicious_heuristic",
                            (name,),
                            {"absolute_point_biserial": strength, "paired": len(pairs)},
                            "Verify how and when the feature is obtained.",
                            "In-sample binary association is neither causal nor proof of leakage.",
                            thresholds={
                                "minimum_absolute_correlation": config.association_threshold
                            },
                        )

            if not method and 2 <= len(values) <= 20 and len(labels) <= 20:
                counts = Counter(pairs)
                feature_counts = Counter(value for value, _ in pairs)
                label_counts = Counter(label for _, label in pairs)
                chi_squared = 0.0
                adequate = True
                for value, count in feature_counts.items():
                    for label, total in label_counts.items():
                        expected = count * total / len(pairs)
                        adequate &= expected >= 5
                        chi_squared += (counts[value, label] - expected) ** 2 / expected
                strength = sqrt(
                    chi_squared / (len(pairs) * min(len(values) - 1, len(labels) - 1))
                )
                if adequate and strength >= config.association_threshold:
                    emit(
                        "categorical_association",
                        "suspicious_heuristic",
                        (name,),
                        {"cramers_v": min(strength, 1.0), "paired": len(pairs)},
                        "Audit the provenance of the associated feature.",
                        "Training-only categorical association does not establish leakage.",
                        thresholds={
                            "minimum_cramers_v": config.association_threshold,
                            "minimum_expected_count": 5,
                        },
                    )

    features = feature_rows(dataset, target)
    group = config.group or manifest.config.group
    time = config.time or manifest.config.time
    group_index = column(dataset, group) if group else None
    time_index = column(dataset, time) if time else None
    cutoff = timestamp(config.cutoff) if config.cutoff else None
    if cutoff is not None and time_index is None:
        raise DatasetError(
            "missing_timestamp_column", "A cutoff requires a timestamp column."
        )
    if time_index is not None:
        dates = [timestamp(row[time_index]) for row in dataset.rows]
        if cutoff is not None:
            bad = tuple(i for i in train if dates[i - 1] > cutoff)
            if bad:
                emit(
                    "training_after_cutoff",
                    "confirmed_violation",
                    (time or "",),
                    {"affected": len(bad)},
                    "Train on data available by the cutoff.",
                    "Uses the declared cutoff and timestamp.",
                    bad,
                )
    else:
        dates = []
    for left, right in combinations(PARTITIONS, 2):
        a, b = manifest.partitions[left], manifest.partitions[right]
        scope = f"{left}:{right}"
        for method, keys in (
            ("cross_split_rows", dataset.rows),
            ("cross_split_features", features),
        ):
            lookup = {keys[i - 1] for i in a}
            hits = tuple(i for i in b if keys[i - 1] in lookup)
            if hits:
                emit(
                    method,
                    "confirmed_violation",
                    dataset.columns
                    if method.endswith("rows")
                    else tuple(name for name in dataset.columns if name != target),
                    {"affected": len(hits), "partitions": [left, right]},
                    "Create an explicit split that keeps repeats together.",
                    "Exact parsed-cell matches can also occur naturally.",
                    hits,
                    scope=scope,
                )
        if group_index is not None:
            seen = {dataset.rows[i - 1][group_index] for i in a} - {""}
            hits = tuple(
                i
                for i in b
                if dataset.rows[i - 1][group_index] in seen
                and dataset.rows[i - 1][group_index].strip()
            )
            if hits:
                emit(
                    "group_overlap",
                    "confirmed_violation",
                    (group or "",),
                    {"affected": len(hits), "partitions": [left, right]},
                    "Keep each group in one partition.",
                    "Blank groups are excluded.",
                    hits,
                    scope=scope,
                )
        if dates:
            latest = max(dates[i - 1] for i in a)
            hits = tuple(i for i in b if dates[i - 1] <= latest)
            if hits:
                emit(
                    "temporal_overlap",
                    "confirmed_violation",
                    (time or "",),
                    {"affected": len(hits), "partitions": [left, right]},
                    "Split into successive time windows.",
                    "Uses the configured timestamps.",
                    hits,
                    scope=scope,
                )
    partition_for = {
        record: key
        for key, records in manifest.partitions.items()
        for record in records
    }
    close = [
        (a, b)
        for a, b in near_pairs(features, config.candidate_limit)
        if partition_for[a] != partition_for[b]
    ]
    if close:
        emit(
            "cross_split_near_matches",
            "suspicious_heuristic",
            tuple(name for name in dataset.columns if name != target),
            {"candidate_matches": len(close), "pairs": close[:100]},
            "Review close records before selecting a split.",
            "Sorted-neighbor search can miss pairs. One differing field may be legitimate.",
            tuple(sorted({record for pair in close for record in pair})),
            thresholds={
                "candidate_limit": config.candidate_limit,
                "hamming_distance": 1,
            },
        )
    for name in sorted(set(config.unavailable)):
        column(dataset, name)
        emit(
            "unavailable_feature",
            "confirmed_violation",
            (name,),
            {},
            "Exclude this feature before fitting.",
            "Uses supplied availability metadata.",
        )
    return output
