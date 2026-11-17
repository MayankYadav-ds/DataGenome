from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.spatial.distance import cdist, jensenshannon
from scipy.stats import chi2_contingency, ks_2samp, wasserstein_distance

from .identity import canonical
from .ingestion import Dataset, DatasetError
from .numeric import number


@dataclass(frozen=True)
class DriftConfig:
    iid: bool = False
    seed: int = 42
    minimum_samples: int = 20
    permutations: int = 39
    maximum_mmd_sample: int = 128
    summary_only: bool = True


def holm(values: list[float]) -> list[float]:
    adjusted = [0.0] * len(values)
    largest = 0.0
    for rank, index in enumerate(sorted(range(len(values)), key=values.__getitem__)):
        largest = max(largest, min(1.0, (len(values) - rank) * values[index]))
        adjusted[index] = largest
    return adjusted


def numeric_result(a: list[float], b: list[float], iid: bool) -> dict[str, Any]:
    # Scale both vectors by the same constant to avoid overflow in distance calculations.
    scale = max(max(map(abs, a)), max(map(abs, b))) or 1.0
    x, y = np.asarray(a) / scale, np.asarray(b) / scale
    statistic = ks_2samp(x, y, method="asymp")
    edges = np.unique(np.quantile(x, np.arange(1, 10) / 10))
    edges = edges[(edges > min(x)) & (edges < max(x))]
    if min(x) == max(x):
        # Point masses need an explicit point bin.
        same = x[0]

        def counts(values: NDArray[np.float64]) -> NDArray[np.int64]:
            return np.array(
                [(values < same).sum(), (values == same).sum(), (values > same).sum()]
            )

        left, right = counts(x), counts(y)
    else:
        bounds = np.r_[-np.inf, edges, np.inf]
        left, right = np.histogram(x, bounds)[0], np.histogram(y, bounds)[0]
    left_p = (left + 0.5) / (left.sum() + 0.5 * len(left))
    right_p = (right + 0.5) / (right.sum() + 0.5 * len(right))
    return {
        "method": "numeric_ks",
        "effect": float(statistic.statistic),
        "p_value": float(statistic.pvalue) if iid else None,
        "wasserstein_scaled": float(wasserstein_distance(x, y)),
        "numeric_scale": scale,
        "psi": float(np.sum((right_p - left_p) * np.log(right_p / left_p))),
        "jensen_shannon": float(jensenshannon(left_p, right_p, base=2) ** 2),
        "reference_quantiles_scaled": np.quantile(x, [0.25, 0.5, 0.75]).tolist(),
        "comparison_quantiles_scaled": np.quantile(y, [0.25, 0.5, 0.75]).tolist(),
        "threshold": 0.20,
    }


def categorical_result(left: list[str], right: list[str], iid: bool) -> dict[str, Any]:
    a, b = Counter(left), Counter(right)
    universe = sorted(a.keys() | b.keys())
    table = np.asarray(
        [[a[k] for k in universe], [b[k] for k in universe]], dtype=float
    )
    statistic = float(jensenshannon(table[0], table[1], base=2) ** 2)
    p = None
    if iid and len(universe) > 1:
        result = chi2_contingency(table, correction=False)
        if np.min(result.expected_freq) >= 5:
            p = float(result.pvalue)
    changes = sorted(
        universe, key=lambda key: (-abs(b[key] / len(right) - a[key] / len(left)), key)
    )
    return {
        "method": "categorical_jsd",
        "effect": statistic,
        "p_value": p,
        "threshold": 0.10,
        "previously_unseen": len(b.keys() - a.keys()),
        "disappearing": len(a.keys() - b.keys()),
        "largest_category_changes": [
            {
                "value": key,
                "reference": a[key] / len(left),
                "comparison": b[key] / len(right),
            }
            for key in changes[:20]
        ],
        "test_status": "evaluated" if p is not None else "unavailable_or_sparse",
    }


def multivariate(
    reference: Dataset,
    comparison: Dataset,
    columns: list[tuple[int, int]],
    config: DriftConfig,
) -> dict[str, Any]:
    if len(columns) < 2:
        return {
            "status": "unsupported",
            "reason": "Requires two common numeric features.",
        }
    rng = Random(config.seed)

    def draw(data: Dataset, indices: list[int]) -> list[list[float]]:
        # Use complete cases for the multivariate result, independent of univariate counts.
        rows = [[number(row[i]) for i in indices] for row in data.rows]
        complete = [
            [v for v in row if v is not None]
            for row in rows
            if all(v is not None for v in row)
        ]
        return rng.sample(complete, min(config.maximum_mmd_sample, len(complete)))

    a, b = (
        draw(reference, [i for i, _ in columns]),
        draw(comparison, [j for _, j in columns]),
    )
    if min(len(a), len(b)) < config.minimum_samples:
        return {
            "status": "insufficient_evidence",
            "reason": "Too few complete sampled rows.",
        }
    n = len(a)
    x = np.asarray(a + b)
    scale = np.max(np.abs(x), axis=0)
    x = x / np.where(scale > 0, scale, 1)
    s = x.std(axis=0)
    x = (x - x.mean(axis=0)) / np.where(s > 0, s, 1)
    sq = cdist(x, x, "sqeuclidean")
    positive = sq[sq > 0]
    bandwidth = float(np.median(positive)) if positive.size else 1.0
    kernel = np.exp(-sq / (2 * bandwidth))

    def effect(ids: list[int]) -> float:
        ii, jj = ids[:n], ids[n:]
        return max(
            0.0,
            float(
                kernel[np.ix_(ii, ii)].mean()
                + kernel[np.ix_(jj, jj)].mean()
                - 2 * kernel[np.ix_(ii, jj)].mean()
            ),
        )

    order = list(range(len(x)))
    observed = effect(order)
    extreme = 0
    if config.iid:
        for _ in range(config.permutations):
            rng.shuffle(order)
            extreme += effect(order) >= observed - 1e-12
    return {
        "status": "evaluated",
        "method": "rbf_mmd_biased",
        "effect": observed,
        "p_value": (extreme + 1) / (config.permutations + 1) if config.iid else None,
        "reference_sample": len(a),
        "comparison_sample": len(b),
        "features": len(columns),
        "permutations": config.permutations if config.iid else 0,
        "limitations": "Permutation inference requires exchangeable observations. Complete cases only.",
    }


def detect_drift(
    reference: Dataset,
    comparison: Dataset,
    config: DriftConfig = DriftConfig(),
    *,
    target: str | None = None,
) -> dict[str, Any]:
    if (
        not 5 <= config.minimum_samples <= 500
        or not 0 <= config.seed < 2**32
        or not 9 <= config.permutations <= 199
        or not 16 <= config.maximum_mmd_sample <= 256
        or max(len(reference.rows), len(comparison.rows)) > 10000
        or max(len(reference.columns), len(comparison.columns)) > 64
    ):
        raise DatasetError("drift_budget", "Invalid drift limits or dataset size.")
    if target is not None and target not in reference.columns:
        raise DatasetError(
            "drift_target", "Target must exist in the reference dataset."
        )
    findings: list[dict[str, Any]] = []
    numeric_columns = []
    for i, name in enumerate(reference.columns):
        if name not in comparison.columns:
            continue
        j = comparison.columns.index(name)
        left = [row[i] for row in reference.rows]
        right = [row[j] for row in comparison.rows]
        a, b = [v for v in left if v.strip()], [v for v in right if v.strip()]
        missing_a, missing_b = 1 - len(a) / len(left), 1 - len(b) / len(right)
        findings.append(
            {
                "feature": name,
                "kind": "missingness",
                "method": "absolute_rate_gap",
                "effect": abs(missing_b - missing_a),
                "threshold": 0.10,
                "p_value": None,
                "reference": missing_a,
                "comparison": missing_b,
                "reference_samples": len(left),
                "comparison_samples": len(right),
            }
        )
        if min(len(a), len(b)) < config.minimum_samples:
            findings.append(
                {
                    "feature": name,
                    "kind": "value",
                    "status": "insufficient_evidence",
                    "reference_samples": len(a),
                    "comparison_samples": len(b),
                }
            )
            continue
        x, y = [number(v) for v in a], [number(v) for v in b]
        if name != target and None not in x and None not in y:
            result = numeric_result(
                [v for v in x if v is not None],
                [v for v in y if v is not None],
                config.iid,
            )
            numeric_columns.append((i, j))
        else:
            result = categorical_result(a, b, config.iid)
        findings.append(
            {
                "feature": name,
                "kind": "label_distribution" if name == target else "value",
                "status": "evaluated",
                "reference_samples": len(a),
                "comparison_samples": len(b),
                **result,
            }
        )
    joint = multivariate(reference, comparison, numeric_columns[:16], config)
    tested = [item for item in [*findings, joint] if item.get("p_value") is not None]
    for item, p in zip(tested, holm([item["p_value"] for item in tested]), strict=True):
        item["adjusted_p_value"] = p
    for item in findings:
        if "effect" in item:
            item["severity"] = (
                "review"
                if item["effect"] >= item["threshold"]
                else "below_effect_threshold"
            )
    result = {
        "status": "evaluated",
        "multivariate": joint,
        "feature_findings": len(findings),
        "review_count": sum(item.get("severity") == "review" for item in findings),
        "comparison_labels_available": bool(target and target in comparison.columns),
        "reference_only_columns": len(set(reference.columns) - set(comparison.columns)),
        "comparison_only_columns": len(
            set(comparison.columns) - set(reference.columns)
        ),
        "limitations": [
            "Effect thresholds are screening rules rather than universal cutoffs.",
            "Holm adjusts reported tests jointly when IID is explicitly asserted.",
            "Observed distribution changes do not establish concept drift.",
        ],
    }
    count = result["review_count"]
    result["recommendations"] = (
        [
            {
                "evidence": {"review_count": count},
                "action": "Review changed inputs and check measurement or collection changes.",
                "potential_benefit": "Distinguish pipeline changes from shifts in the sampled population.",
                "risk": "Automatically adapting could amplify transient changes.",
                "validation": "Evaluate the same frozen model on labeled later observations.",
                "contraindications": [
                    "Do not interpret dependent observations with IID tests."
                ],
                "limitations": [
                    "Distribution changes do not establish a causal mechanism."
                ],
            }
        ]
        if count
        else []
    )
    if not config.summary_only:
        result.update(
            reference_sha256=canonical(reference),
            comparison_sha256=canonical(comparison),
            findings=findings,
        )
    return result


def main() -> None:
    import argparse
    import json

    from .ingestion import DEFAULT_MAX_BYTES, load_csv

    parser = argparse.ArgumentParser(description="Compare two bounded CSV datasets.")
    parser.add_argument("reference", type=Path)
    parser.add_argument("comparison", type=Path)
    parser.add_argument("--target")
    parser.add_argument("--iid", action="store_true")
    parser.add_argument("--detailed", action="store_true")
    args = parser.parse_args()
    try:
        with args.reference.open("rb") as left, args.comparison.open("rb") as right:
            result = detect_drift(
                load_csv(left, args.reference.name, DEFAULT_MAX_BYTES),
                load_csv(right, args.comparison.name, DEFAULT_MAX_BYTES),
                DriftConfig(iid=args.iid, summary_only=not args.detailed),
                target=args.target,
            )
    except DatasetError as error:
        parser.exit(2, json.dumps({"code": error.code, "message": str(error)}) + "\n")
    except OSError:
        parser.exit(2, '{"code":"drift_io_error"}\n')
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
