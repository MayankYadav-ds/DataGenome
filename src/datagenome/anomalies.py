from dataclasses import dataclass
from statistics import median, quantiles
from typing import Any

import numpy as np

from .ingestion import Dataset, DatasetError
from .numeric import number


@dataclass(frozen=True)
class AnomalyConfig:
    seed: int = 42
    iqr_multiplier: float = 1.5
    modified_z_threshold: float = 3.5
    contamination: float = 0.05
    max_multivariate_rows: int = 2000


def detect_anomalies(
    dataset: Dataset, target: str | None = None, config: AnomalyConfig = AnomalyConfig()
) -> dict[str, Any]:
    if (
        not 0 <= config.seed < 2**32
        or not 0 < config.iqr_multiplier <= 100
        or not 0 < config.modified_z_threshold <= 100
        or not 0 < config.contamination <= 0.5
        or not 5 <= config.max_multivariate_rows <= 5000
    ):
        raise DatasetError(
            "invalid_anomaly_config", "Invalid anomaly thresholds or limits."
        )
    names = ("iqr", "modified_z", "isolation_forest", "local_outlier_factor")
    scores: dict[str, dict[int, float]] = {name: {} for name in names}
    feature_evidence: dict[int, list[dict[str, object]]] = {}
    unsupported: list[str] = []
    vectors: list[list[float]] = []
    for index, name in enumerate(dataset.columns):
        if name == target:
            continue
        tokens = [row[index] for row in dataset.rows]
        observed = [number(token) for token in tokens]
        if any(
            value is None and token.strip()
            for value, token in zip(observed, tokens, strict=True)
        ):
            unsupported.append(f"{name}: nonnumeric or mixed observations.")
            continue
        finite = [value for value in observed if value is not None]
        if len(finite) < 4 or min(finite) == max(finite):
            unsupported.append(
                f"{name}: fewer than four finite observations or constant."
            )
            continue
        scale = max(abs(value) for value in finite)
        values = [value / scale for value in finite]
        center = median(values)
        q1, _, q3 = quantiles(values, n=4, method="inclusive")
        spread = q3 - q1
        mad = median(abs(value - center) for value in values)
        if spread == 0:
            unsupported.append(f"{name}: IQR is zero.")
        if mad == 0:
            unsupported.append(f"{name}: median absolute deviation is zero.")
        vector: list[float] = []
        for record, value in enumerate(observed, 1):
            if value is None:
                vector.append(center)
                continue
            scaled = value / scale
            vector.append(scaled)
            methods = []
            if spread:
                score = min(1e100, max(q1 - scaled, scaled - q3, 0) / spread)
                scores["iqr"][record] = max(score, scores["iqr"].get(record, 0))
                if score > config.iqr_multiplier:
                    methods.append("iqr")
            if mad:
                score = min(1e100, 0.67448975 * abs(scaled - center) / mad)
                scores["modified_z"][record] = max(
                    score, scores["modified_z"].get(record, 0)
                )
                if score > config.modified_z_threshold:
                    methods.append("modified_z")
            if methods:
                feature_evidence.setdefault(record, []).append(
                    {"feature": name, "methods": methods}
                )
        vectors.append(vector)
    thresholds = {
        "iqr": config.iqr_multiplier,
        "modified_z": config.modified_z_threshold,
    }
    multivariate = (
        bool(vectors) and 5 <= len(dataset.rows) <= config.max_multivariate_rows
    )
    if not multivariate:
        unsupported.append(
            "Isolation Forest and LOF require usable numeric features and a bounded sample."
        )
    else:
        try:
            from sklearn.ensemble import IsolationForest
            from sklearn.neighbors import LocalOutlierFactor
        except ImportError:
            multivariate = False
            unsupported.append(
                "Isolation Forest and LOF native dependencies could not load."
            )
    if multivariate:
        matrix = np.asarray(vectors, dtype=float).T
        estimators = {
            "isolation_forest": IsolationForest(
                n_estimators=64,
                max_samples=256 if len(matrix) >= 256 else len(matrix),
                random_state=config.seed,
                contamination=config.contamination,
                n_jobs=1,
            ),
            "local_outlier_factor": LocalOutlierFactor(
                n_neighbors=min(20, len(matrix) - 1),
                contamination=config.contamination,
                n_jobs=1,
            ),
        }
        isolation: Any = estimators["isolation_forest"]
        isolation.fit(matrix)
        lof: Any = estimators["local_outlier_factor"]
        lof.fit_predict(matrix)
        for method, readings in (
            ("isolation_forest", -isolation.decision_function(matrix)),
            ("local_outlier_factor", lof.offset_ - lof.negative_outlier_factor_),
        ):
            scores[method] = {
                index: float(score) for index, score in enumerate(readings, 1)
            }
            thresholds[method] = 0.0
    agreement: dict[int, list[str]] = {}
    for method, readings_by_record in scores.items():
        if readings_by_record:
            for record_id, score in readings_by_record.items():
                if score > thresholds[method]:
                    agreement.setdefault(record_id, []).append(method)
    ranked = sorted(agreement, key=lambda i: (-len(agreement[i]), i))
    return {
        "detectors": {
            method: {
                "scores": results,
                "threshold": thresholds.get(method),
                "status": "evaluated" if results else "unsupported",
            }
            for method, results in scores.items()
        },
        "ranked": [
            {
                "record": i,
                "methods": agreement[i],
                "features": feature_evidence.get(i, []),
            }
            for i in ranked
        ],
        "seed": config.seed,
        "contamination": config.contamination,
        "unsupported": unsupported,
        "severity": "warning",
        "remediation": "Review flagged rows against domain evidence.",
        "limitations": [
            "Scores are detector-specific and ranked by agreement.",
            "Numeric missing values use medians for multivariate detection.",
            "Anomaly flags are suspicious observations.",
        ],
    }
