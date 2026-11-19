from typing import Any

import numpy as np
from scipy.stats import kendalltau, spearmanr
from sklearn.metrics import average_precision_score


def detection(
    ids: list[int],
    scores: list[float],
    truth: frozenset[int],
    flagged: set[int],
    labels: list[str],
) -> dict[str, Any]:
    actual = np.array([i in truth for i in ids])
    predicted = np.array([i in flagged for i in ids])
    tp = int((actual & predicted).sum())
    fp = int((~actual & predicted).sum())
    fn = int((actual & ~predicted).sum())
    k = len(truth.intersection(ids))
    top = sorted(zip(ids, scores, strict=True), key=lambda v: (-v[1], v[0]))[:k]
    hit = sum(i in truth for i, _ in top)
    return {
        "records": len(ids),
        "corrupted": k,
        "flagged": int(predicted.sum()),
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        "false_positive_rate": fp / int((~actual).sum()) if (~actual).any() else None,
        "precision_at_k": hit / k if k else None,
        "recall_at_k": hit / k if k else None,
        "average_precision": float(average_precision_score(actual, scores))
        if actual.any()
        else None,
        "per_class_false_positive_rate": {
            c: sum(
                i in flagged and i not in truth
                for i, y in zip(ids, labels, strict=True)
                if y == c
            )
            / n
            if (
                n := sum(
                    i not in truth for i, y in zip(ids, labels, strict=True) if y == c
                )
            )
            else None
            for c in sorted(set(labels))
        },
        "undefined": "Precision needs alerts; recall/AP/top-K need injected positives; FPR needs clean records.",
    }


def agreement(a: list[float], b: list[float], k: int = 2) -> dict[str, Any]:
    variable = len(set(a)) > 1 and len(set(b)) > 1
    left = sorted(range(len(a)), key=lambda i: (-a[i], i))
    right = sorted(range(len(b)), key=lambda i: (-b[i], i))
    return {
        "spearman": float(spearmanr(a, b).statistic) if variable else None,
        "kendall": float(kendalltau(a, b).statistic) if variable else None,
        "top_k_agreement": len(set(left[:k]) & set(right[:k])) / k,
        "bottom_k_agreement": len(set(left[-k:]) & set(right[-k:])) / k,
        "mean_absolute_error": float(np.mean(np.abs(np.array(a) - b))),
        "undefined_reason": None if variable else "constant_ranking",
        "ties": "Correlations use average ranks; top/bottom ties break by fixed record position.",
    }
