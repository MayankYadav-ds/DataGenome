from collections import Counter
from typing import Any

import numpy as np
from sklearn.metrics import mutual_info_score

from .ingestion import Dataset, DatasetError
from .numeric import number
from .splits import Manifest, column, validate


def detect_proxies(
    dataset: Dataset,
    manifest: Manifest,
    sensitive: str,
    target: str | None = None,
    *,
    min_support: int = 20,
    summary_only: bool = True,
) -> dict[str, Any]:
    validate(dataset, manifest)
    if (
        not 5 <= min_support <= 1000
        or len(dataset.columns) > 65
        or len(manifest.partitions["train"]) > 5000
        or sensitive == target
    ):
        raise DatasetError(
            "proxy_budget", "Invalid proxy support, column count, or training size."
        )
    index = column(dataset, sensitive)
    ids = manifest.partitions["train"]
    findings: list[dict[str, Any]] = []
    excluded = {target, sensitive, manifest.config.group, manifest.config.time}
    for j, name in enumerate(dataset.columns):
        if name in excluded:
            continue
        pairs = [
            (dataset.rows[i - 1][j], dataset.rows[i - 1][index])
            for i in ids
            if dataset.rows[i - 1][j].strip() and dataset.rows[i - 1][index].strip()
        ]
        strata = Counter(group for _, group in pairs)
        if (
            len(pairs) < min_support
            or not 2 <= len(strata) <= 20
            or min(strata.values()) < min_support
        ):
            continue
        values, groups = zip(*pairs, strict=True)
        numerics = [number(value) for value in values]
        if None not in numerics:
            x = np.asarray([v for v in numerics if v is not None])
            scale = max(map(abs, x)) or 1.0
            x = x / scale
            cutoffs = np.unique(np.quantile(x, np.arange(1, 5) / 5))
            categories = [str(i) for i in np.searchsorted(cutoffs, x, side="right")]
            method = "training_quantile_binned_mutual_information"
        else:
            counts = Counter(values)
            common = {value for value, _ in counts.most_common(31)}
            categories = [
                "value:" + value if value in common else "other:" for value in values
            ]
            method = "pooled_categorical_mutual_information"
        if len(set(categories)) < 2:
            continue
        info = float(mutual_info_score(groups, categories))
        entropy = float(mutual_info_score(groups, groups))
        fraction = min(1.0, max(0.0, info / entropy))
        findings.append(
            {
                "feature": name,
                "method": method,
                "support": len(pairs),
                "normalized_sensitive_entropy_reduction": fraction,
                "potential_proxy": fraction >= 0.30,
                "threshold": 0.30,
            }
        )
    findings.sort(
        key=lambda item: (
            -item["normalized_sensitive_entropy_reduction"],
            item["feature"],
        )
    )
    result: dict[str, Any] = {
        "status": "evaluated" if findings else "insufficient_evidence",
        "evaluated_features": len(findings),
        "potential_proxy_count": sum(item["potential_proxy"] for item in findings),
        "limitations": [
            "Training-only descriptive association is not evidence of discriminatory use.",
            "Finite-sample bias and discretization affect the scores.",
            "Investigate provenance and run a controlled feature comparison before acting.",
        ],
    }
    if not summary_only:
        result["findings"] = findings
    return result
