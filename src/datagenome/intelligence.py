from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from statistics import correlation, median, quantiles
from typing import Any

from .duplicates import groups, near_pairs
from .ingestion import Dataset, DatasetError
from .leakage import feature_rows
from .numeric import number
from .splits import column


@dataclass(frozen=True)
class IntelligenceConfig:
    missing_warning: float = 0.05
    missing_high: float = 0.3
    candidate_limit: int = 10000
    ranges: dict[str, tuple[float, float]] = field(default_factory=dict)


def analyze(
    dataset: Dataset,
    target: str | None = None,
    config: IntelligenceConfig = IntelligenceConfig(),
) -> dict[str, Any]:
    from math import isfinite

    if not 0 <= config.missing_warning <= config.missing_high <= 1:
        raise DatasetError(
            "invalid_missing_threshold",
            "Missingness thresholds must be ordered fractions.",
        )
    for name, (low, high) in config.ranges.items():
        column(dataset, name)
        if not isfinite(low) or not isfinite(high) or low > high:
            raise DatasetError(
                "invalid_numeric_range", "Numeric bounds must be finite and ordered."
            )
    target_index = column(dataset, target) if target is not None else None
    n = len(dataset.rows)
    row_counts: dict[int, int] = {}
    patterns: Counter[tuple[str, ...]] = Counter()
    co_occurrence: Counter[tuple[str, str]] = Counter()
    conditioned: dict[str, Counter[str]] = {}
    for record, row in enumerate(dataset.rows, 1):
        missing = tuple(
            name
            for name, value in zip(dataset.columns, row, strict=True)
            if not value.strip()
        )
        row_counts[record] = len(missing)
        patterns[missing] += 1
        if target_index is not None and row[target_index].strip():
            counts = conditioned.setdefault(row[target_index], Counter())
            counts.update(missing)
    for pattern, count in patterns.most_common(100):
        co_occurrence.update(dict.fromkeys(combinations(pattern, 2), count))

    findings: list[dict[str, object]] = []
    summaries = {}
    numeric_columns: dict[str, list[float | None]] = {}

    def emit(
        method: str,
        columns: tuple[str, ...],
        evidence: dict[str, object],
        thresholds: dict[str, object],
        remediation: str,
        limitations: str,
        records: list[int] | None = None,
        severity: str = "warning",
    ) -> None:
        from .identity import fingerprint

        findings.append(
            {
                "id": method + ":" + fingerprint(columns),
                "method": method,
                "severity": severity,
                "columns": columns,
                "records": (records or [])[:100],
                "evidence": evidence,
                "thresholds": thresholds,
                "remediation": remediation,
                "limitations": limitations,
            }
        )

    for i, name in enumerate(dataset.columns):
        cells = [row[i] for row in dataset.rows]
        missing_ids = [j for j, value in enumerate(cells, 1) if not value.strip()]
        share = len(missing_ids) / n
        counts = Counter(value for value in cells if value.strip())
        summary: dict[str, object] = {"missing_fraction": share, "unique": len(counts)}
        summaries[name] = summary
        if missing_ids:
            emit(
                "column_missingness",
                (name,),
                {"count": len(missing_ids), "fraction": share},
                {"warning": config.missing_warning, "high": config.missing_high},
                "Review how blanks were produced.",
                "Blank and whitespace-only cells.",
                missing_ids,
                "high"
                if share >= config.missing_high
                else "warning"
                if share >= config.missing_warning
                else "info",
            )
        if not counts:
            continue
        observed = counts.total()
        top_share = counts.most_common(1)[0][1] / observed
        numeric_values = [number(value) for value in cells]
        finite = [value for value in numeric_values if value is not None]
        if len(counts) > 1 and top_share >= 0.95:
            emit(
                "near_constant",
                (name,),
                {"mode_share": top_share},
                {"minimum": 0.95},
                "Check whether rare values are relevant.",
                "Uses nonblank parsed text.",
            )
        infinite = [
            k
            for k, value in enumerate(cells, 1)
            if value.strip().lower()
            in {"inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}
        ]
        if infinite:
            emit(
                "infinite_values",
                (name,),
                {"count": len(infinite)},
                {},
                "Review the encoding of nonfinite values.",
                "Recognizes literal infinity tokens.",
                infinite,
            )
        if finite and len(finite) != observed:
            emit(
                "mixed_numeric",
                (name,),
                {"numeric": len(finite), "observed": observed},
                {},
                "Validate expected feature types.",
                "Uses finite numeric parsing.",
            )
        if name in config.ranges:
            low, high = config.ranges[name]
            bad = [
                k
                for k, value in enumerate(numeric_values, 1)
                if value is not None and not low <= value <= high
            ]
            if bad:
                emit(
                    "range_violation",
                    (name,),
                    {"count": len(bad)},
                    {"min": low, "max": high},
                    "Verify values against the declared range.",
                    "Only finite values are evaluated.",
                    bad,
                )
        if not finite or len(finite) != observed:
            summary["category_frequencies"] = counts.most_common(100)
            summary["rare_categories"] = [
                value
                for value, count in counts.most_common()
                if count / observed <= 0.01
            ][:100]
            if len(counts) >= 20 and len(counts) / observed >= 0.5:
                emit(
                    "high_cardinality",
                    (name,),
                    {"unique": len(counts)},
                    {"minimum_unique": 20, "minimum_share": 0.5},
                    "Review categorical encoding.",
                    "Threshold is heuristic.",
                )
        elif name != target:
            numeric_columns[name] = numeric_values
            scale = max(abs(value) for value in finite) or 1.0
            scaled = [value / scale for value in finite]
            q1, q2, q3 = (
                quantiles(scaled, n=4, method="inclusive")
                if len(scaled) > 1
                else scaled * 3
            )
            center = sum(scaled) / len(scaled)
            variance = sum((value - center) ** 2 for value in scaled) / len(scaled)
            standardized = (
                [(value - center) / variance**0.5 for value in scaled]
                if variance
                else []
            )
            summary.update(
                quantiles=[q1 * scale, q2 * scale, q3 * scale],
                median=q2 * scale,
                mad_scaled=median(abs(value - q2) for value in scaled),
                iqr_scaled=q3 - q1,
                scale=scale,
                skewness=sum(value**3 for value in standardized) / len(scaled)
                if variance
                else None,
                excess_kurtosis=sum(value**4 for value in standardized) / len(scaled)
                - 3
                if variance
                else None,
            )
        if name != target and observed >= 20 and len(counts) == observed:
            emit(
                "potential_identifier",
                (name,),
                {"unique": observed},
                {"minimum": 20},
                "Confirm whether this feature identifies records.",
                "Uniqueness is a heuristic.",
            )

    for left, right in combinations(list(numeric_columns)[:32], 2):
        pairs = [
            (a, b)
            for a, b in zip(numeric_columns[left], numeric_columns[right], strict=True)
            if a is not None and b is not None
        ]
        if len(pairs) < 4:
            continue
        x, y = zip(*pairs)
        x_scale = max(x, key=abs) or 1
        y_scale = max(y, key=abs) or 1
        try:
            strength = correlation(
                [a / x_scale for a in x],
                [b / y_scale for b in y],
            )
        except (ArithmeticError, ValueError):
            continue
        if abs(strength) >= 0.98:
            emit(
                "correlated_features",
                (left, right),
                {"pearson": strength, "paired": len(pairs)},
                {"absolute_minimum": 0.98},
                "Review feature redundancy.",
                "Complete-case association.",
            )

    columns = [
        tuple(row[i] for row in dataset.rows) for i in range(len(dataset.columns))
    ]
    for group in groups(columns):
        names = tuple(
            dataset.columns[i - 1] for i in group if dataset.columns[i - 1] != target
        )
        if len(names) > 1:
            emit(
                "redundant_features",
                names,
                {"identical_columns": len(names)},
                {},
                "Review retaining one representative feature.",
                "Exact parsed-cell equality.",
            )

    feature_keys = feature_rows(dataset, target)
    feature_groups = groups(feature_keys)
    conflicts = [
        group
        for group in feature_groups
        if target_index is not None
        and len(
            {
                dataset.rows[i - 1][target_index]
                for i in group
                if dataset.rows[i - 1][target_index].strip()
            }
        )
        > 1
    ]
    return {
        "columns": summaries,
        "row_missing_counts": row_counts,
        "missing_patterns": patterns.most_common(100),
        "co_occurring_missing": co_occurrence.most_common(100),
        "target_conditioned_missing": conditioned,
        "findings": findings,
        "duplicates": {
            "exact_groups": groups(dataset.rows),
            "feature_groups": feature_groups,
            "conflicting_labels": conflicts,
            "near_pairs": list(near_pairs(feature_keys, config.candidate_limit)),
            "method": "exact cells and sorted-neighbor Hamming distance",
            "thresholds": {
                "near_distance": 1,
                "candidate_limit": config.candidate_limit,
            },
            "severity": "warning",
            "remediation": "Inspect repeats and reconcile conflicting labels.",
            "limitations": "Near matches consider sorted neighbors and can miss other pairs.",
        },
        "limitations": [
            "Co-occurrence uses the 100 most frequent missingness patterns.",
            "Correlation covers the first 32 numeric features.",
            "Category and rare-value lists are capped at 100.",
        ],
    }
