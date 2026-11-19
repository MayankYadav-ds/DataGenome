"""Prespecified small scientific studies; only aggregate evidence is returned."""

from dataclasses import replace
from itertools import permutations
from math import factorial
from random import Random
from typing import Any

import numpy as np

from .benchmark_data import corrupt, synthetic
from .benchmark_metrics import agreement, detection
from .fairness import FairnessConfig, audit_fairness, binary_metrics
from .identity import canonical
from .influence import LogisticObjective, estimate
from .ingestion import Dataset
from .label_audit import LabelAuditConfig, audit_labels
from .leakage import LeakageConfig, inspect_leakage
from .modeling import ModelConfig, classification_pipeline
from .splits import Manifest, SplitConfig, split
from .univariate import UnivariateConfig
from .valuation import ValuationConfig, value_data
from .valuation_math import exact_values, sampled_values


def leakage(seed: int, kind: str) -> dict[str, Any]:
    clean = synthetic(seed)
    manifest = split(clean, SplitConfig("stratified", seed=seed), "label")
    data = clean
    cfg = LeakageConfig(univariate=UnivariateConfig(max_features=8))
    if kind in {"target_copy", "target_encoding", "group_overlap", "time_overlap"}:
        data = corrupt(clean, manifest.partitions["train"], kind, 0.1, seed).data
        if kind == "group_overlap":
            cfg = replace(cfg, group="injected")
        if kind == "time_overlap":
            cfg = replace(cfg, time="injected")
    elif kind == "cross_split":
        rows = list(clean.rows)
        rows[manifest.partitions["validation"][0] - 1] = rows[
            manifest.partitions["train"][0] - 1
        ]
        data = Dataset(clean.columns, tuple(rows))
    elif kind == "strong_predictor":
        # Genuine generative predictor with class overlap, not target-derived.
        data = Dataset(
            ("x", "label"), tuple((str(i / 100), str(int(i > 119))) for i in range(240))
        )
        manifest = split(data, SplitConfig("stratified", seed=seed), "label")
    elif kind == "cardinality":
        data = Dataset(
            ("identifier", "label"),
            tuple((f"id-{i}", row[-1]) for i, row in enumerate(clean.rows)),
        )
    manifest = replace(manifest, dataset_sha256=canonical(data))
    signals = inspect_leakage(data, "label", manifest, cfg)
    expected = {
        "target_copy": "target_copy",
        "target_encoding": "target_bijection",
        "group_overlap": "group_overlap",
        "time_overlap": "temporal_overlap",
        "cross_split": "cross_split_rows",
    }.get(kind)
    positive = expected is not None
    detected = any(s.method == expected for s in signals) if positive else None
    return {
        "dataset_sha256": canonical(data),
        "split_sha256": manifest.fingerprint,
        "scenario": kind,
        "injected_violation_or_agreement": positive,
        "expected_method_detected": detected,
        "confirmed_alerts": sum(
            s.classification == "confirmed_violation" for s in signals
        ),
        "heuristic_alerts": sum(
            s.classification == "suspicious_heuristic" for s in signals
        ),
        "strong_agreement_alerts": sum(
            s.classification == "strong_statistical_evidence" for s in signals
        ),
        "unsupported": sum(
            s.classification in {"unsupported_analysis", "insufficient_evidence"}
            for s in signals
        ),
        "univariate_scores": [
            dict(
                feature=s.columns[0] if s.columns else None,
                score=s.evidence.get("score"),
                records=s.evidence.get("evaluated_records"),
                classification=s.classification,
            )
            for s in signals
            if s.method == "univariate_predictive"
        ],
        "interpretation": "Exact agreement is statistical evidence; legitimate predictors may trigger heuristics. Counts are not pooled precision estimates.",
    }


def label_study(
    data: Dataset, seed: int, kind: str, intensity: float
) -> dict[str, Any]:
    from sklearn.model_selection import StratifiedGroupKFold

    from .folds import connected_groups

    manifest = split(data, SplitConfig("stratified", seed=seed), "label")
    corruption = corrupt(data, manifest.partitions["train"], kind, intensity, seed)
    data = corruption.data
    manifest = replace(manifest, dataset_sha256=canonical(data))
    audit = audit_labels(data, "label", manifest, LabelAuditConfig(folds=3))
    ids = manifest.partitions["train"]
    labels = [data.rows[i - 1][-1] for i in ids]
    candidates = {r["record_id"]: r["probability_gap"] for r in audit["candidates"]}
    outputs = {
        "datagenome": detection(
            ids,
            [candidates.get(i, 0.0) for i in ids],
            corruption.changed,
            set(candidates),
            labels,
        )
    }
    groups = connected_groups([(data.rows[i - 1][:-1],) for i in ids])
    low = [0.0] * len(ids)
    disagreement = [0.0] * len(ids)
    for fit, score in StratifiedGroupKFold(
        n_splits=3, shuffle=True, random_state=seed
    ).split(ids, labels, groups):
        train = [ids[i] for i in fit]
        pipeline, _, design, _, _ = classification_pipeline(
            data, list(range(len(data.columns) - 1)), train, ModelConfig(seed=seed)
        )
        pipeline.fit(design(train), [labels[i] for i in fit])
        probs = pipeline.predict_proba(design([ids[i] for i in score]))
        classes = pipeline.classes_.tolist()
        for i, p in zip(score, probs, strict=True):
            low[i] = 1 - float(p[classes.index(labels[i])])
            disagreement[i] = float(classes[int(np.argmax(p))] != labels[i])
    rng = Random(seed)
    random_scores = [rng.random() for _ in ids]
    for name, scores, threshold in (
        ("low_observed_probability", low, 0.5),
        ("oof_disagreement", disagreement, 0.5),
        ("random", random_scores, 0.9),
    ):
        outputs[name] = detection(
            ids,
            scores,
            corruption.changed,
            {i for i, s in zip(ids, scores, strict=True) if s >= threshold},
            labels,
        )
    # Numeric neighborhood consistency is deliberately model-independent and train-only.
    x = np.array([[float(v) for v in data.rows[i - 1][:-1]] for i in ids])
    x = (x - x.mean(axis=0)) / np.where(x.std(axis=0) > 0, x.std(axis=0), 1)
    dist = ((x[:, None, :] - x[None, :, :]) ** 2).sum(axis=2)
    np.fill_diagonal(dist, np.inf)
    neighbor = [
        float(
            np.mean(
                [labels[j] != labels[i] for j in np.argsort(dist[i], kind="stable")[:5]]
            )
        )
        for i in range(len(ids))
    ]
    outputs["neighborhood"] = detection(
        ids,
        neighbor,
        corruption.changed,
        {i for i, s in zip(ids, neighbor, strict=True) if s >= 0.6},
        labels,
    )
    return {
        "dataset_sha256": canonical(data),
        "split_sha256": manifest.fingerprint,
        "corruption": {
            "kind": kind,
            "intensity": intensity,
            "changed_records": len(corruption.changed),
        },
        "methods": outputs,
        "status": audit["status"],
        "ranking_comparison": agreement([candidates.get(i, 0.0) for i in ids], low),
        "warning": "Injected corruption is not verified natural label error; probabilities are uncalibrated; ranking comparison is between methods, not cross-seed stability.",
    }


def valuation_study(seed: int, model_name: str, utility: str) -> dict[str, Any]:
    data = synthetic(seed, 24, 2)
    manifest = Manifest(
        canonical(data),
        SplitConfig(seed=seed),
        {
            "train": list(range(1, 7)),
            "validation": list(range(7, 19)),
            "test": list(range(19, 25)),
        },
    )
    results: dict[str, Any] = {}
    for method, budget in [
        ("loo", 16),
        ("shapley", 128),
        ("banzhaf", 128),
        ("knn-shapley", 128),
        ("mc-shapley", 8),
        ("mc-shapley", 32),
        ("mc-shapley", 128),
    ]:
        if method == "knn-shapley" and utility != "accuracy":
            continue
        cfg = ValuationConfig(
            method=method,
            metric=utility,
            seed=seed,
            max_evaluations=256,
            permutations=max(2, budget),
            seconds=120,
        )
        out = value_data(
            data, "label", manifest, cfg, model=ModelConfig(model=model_name, seed=seed)
        )
        results[f"{method}-{budget}" if method == "mc-shapley" else method] = {
            "scores": [
                next(r["score"] for r in out["records"] if r["record_id"] == i)
                for i in range(1, 7)
            ],
            "computation": {
                k: out[k]
                for k in ("utility_evaluations", "model_fits", "elapsed_seconds")
            },
        }
    exact = results["shapley"]["scores"]
    comparisons = {
        name: agreement(exact, r["scores"])
        for name, r in results.items()
        if name != "shapley"
    }
    return {
        "dataset_sha256": canonical(data),
        "split_sha256": manifest.fingerprint,
        "model": model_name,
        "utility": utility,
        "methods": results,
        "comparisons_to_shapley": comparisons,
        "warning": "LOO/Banzhaf/KNN estimate different games; MAE across different games is descriptive, not approximation error. Only MC approximates exact model Shapley.",
    }


def mathematical_reference(seed: int) -> dict[str, Any]:
    n = 5
    rng = Random(seed)
    table = [rng.uniform(-1, 1) for _ in range(1 << n)]
    # Independent permutation definition, not the subset-weight implementation.
    reference = [0.0] * n
    for order in permutations(range(n)):
        mask = 0
        for i in order:
            reference[i] += (table[mask | (1 << i)] - table[mask]) / factorial(n)
            mask |= 1 << i
    actual = exact_values(n, table.__getitem__)
    banzhaf = [
        sum(table[m | (1 << i)] - table[m] for m in range(1 << n) if not m & (1 << i))
        / 2 ** (n - 1)
        for i in range(n)
    ]
    sampled, _, _ = sampled_values(n, table.__getitem__, seed, 128)
    return {
        "shapley_max_error": max(
            abs(a - b) for a, b in zip(actual, reference, strict=True)
        ),
        "banzhaf_max_error": max(
            abs(a - b)
            for a, b in zip(
                exact_values(n, table.__getitem__, banzhaf=True), banzhaf, strict=True
            )
        ),
        "mc": agreement(reference, sampled),
        "efficiency_residual": abs(sum(actual) - (table[-1] - table[0])),
    }


def influence_study(
    seed: int, scenario: str, regularization: float, damping: float
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    raw = rng.normal(size=(40, 3))
    if scenario == "correlated":
        raw[:, 1] = raw[:, 0] + rng.normal(0, 1e-5, 40)
    if scenario == "duplicates":
        raw[1:5] = raw[0]
    if scenario == "influential":
        raw[0] *= 10
    x = np.column_stack((np.ones(40), raw))
    y = (
        raw[:, 0] + (0 if scenario == "separable" else rng.normal(size=40)) > 0
    ).astype(float)
    obj = LogisticObjective(x, y, regularization)
    beta = obj.fit()
    v = np.array([[1.0, 0.1, -0.3, 0.2]])
    vy = np.array([1.0])
    h = 1e-5
    identity = np.eye(len(beta))
    gradient = np.array(
        [(obj.loss(beta + h * e) - obj.loss(beta - h * e)) / (2 * h) for e in identity]
    )
    hessian = np.column_stack(
        [
            (obj.gradient(beta + h * e) - obj.gradient(beta - h * e)) / (2 * h)
            for e in identity
        ]
    )
    predicted = estimate(obj, beta, v, vy, damping)
    from scipy.special import expit

    before = float(np.logaddexp(0, v @ beta)[0] - vy[0] * (v @ beta)[0])
    actual = []
    for i in range(len(x)):
        after = LogisticObjective(
            np.delete(x, i, axis=0), np.delete(y, i), regularization
        ).fit()
        actual.append(
            float(np.logaddexp(0, v @ after)[0] - vy[0] * (v @ after)[0]) - before
        )
    approximate = predicted["removal_loss_change"].tolist()
    # Probability-specific derivative uses the very same fixed Hessian objective.
    p = float(expit(v @ beta)[0])
    return {
        "scenario": scenario,
        "regularization": regularization,
        "damping": damping,
        "gradient_max_error": float(np.max(np.abs(gradient - obj.gradient(beta)))),
        "hessian_max_error": float(np.max(np.abs(hessian - obj.hessian(beta)))),
        "hessian_condition": predicted["hessian_condition"],
        "solver_residual": predicted["relative_solver_residual"],
        "fit_gradient_inf": predicted["fit_gradient_inf"],
        "comparison": agreement(actual, approximate, 5),
        "sign_agreement": float(np.mean(np.sign(actual) == np.sign(approximate))),
        "selected_prediction_probability": p,
        "warning": "Fixed-preprocessing binary regularized objective, including penalized intercept. Retraining approximation, not causal attribution.",
    }


def fairness_study(seed: int) -> dict[str, Any]:
    from .proxies import detect_proxies

    clean = synthetic(seed, 500, 3)
    rows = tuple((*r[:-1], str(i % 2), r[-1]) for i, r in enumerate(clean.rows))
    data = Dataset((*clean.columns[:-1], "audit", "label"), rows)
    manifest = split(data, SplitConfig("stratified", seed=seed), "label")
    result = audit_fairness(
        data,
        "label",
        manifest,
        FairnessConfig(
            ("audit",), min_support=5, min_class_count=1, summary_only=False
        ),
        ModelConfig(seed=seed),
    )
    fixtures = []
    for truth, pred in [
        ([False, False, True, True], [False, True, False, True]),
        ([True] * 8, [False] * 8),
    ]:
        m = binary_metrics(truth, pred, [float(p) for p in pred], False)
        tp = sum(a and b for a, b in zip(truth, pred, strict=True))
        fp = sum(not a and b for a, b in zip(truth, pred, strict=True))
        fixtures.append(
            {
                "selection": m["selection_rate"]["value"],
                "reference_selection": sum(pred) / len(pred),
                "tpr": m["recall"]["value"],
                "reference_tpr": tp / sum(truth) if sum(truth) else None,
                "fpr": m["false_positive_rate"]["value"],
                "reference_fpr": fp / (len(truth) - sum(truth))
                if not all(truth)
                else None,
            }
        )
    proxy_data = Dataset(
        data.columns[:-1] + ("planted_proxy", "label"),
        tuple((*r[:-1], r[-2], r[-1]) for r in data.rows),
    )
    proxy_manifest = replace(manifest, dataset_sha256=canonical(proxy_data))
    proxies = detect_proxies(
        proxy_data, proxy_manifest, "audit", "label", min_support=10, summary_only=False
    )
    return {
        "dataset_sha256": canonical(data),
        "split_sha256": manifest.fingerprint,
        "reference_fixtures": fixtures,
        "disparities": [r["disparities"] for r in result["comparisons"]],
        "suppressed_groups": [
            r.get("suppressed_groups") for r in result["comparisons"]
        ],
        "proxy_findings": proxies.get("findings", []),
        "warning": "Synthetic audit attributes only; no demographic meaning. Proxy association is descriptive, predictive proxy verification and dependence-aware subgroup intervals are NOT RUN.",
    }
