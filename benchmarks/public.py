import argparse
import json
from importlib.metadata import version
from pathlib import Path
from random import Random
from statistics import mean
from time import perf_counter

from sklearn.datasets import load_breast_cancer, load_wine

from datagenome.identity import canonical
from datagenome.ingestion import Dataset
from datagenome.leakage import LeakageConfig, inspect_leakage
from datagenome.modeling import ModelConfig, fit_baseline
from datagenome.splits import SplitConfig, split

SEEDS = (11, 23, 37, 53, 71)
THRESHOLDS = (0.70, 0.80, 0.90, 0.95)
TARGET = "label"


def evaluate(dataset, target, seeds=SEEDS):
    rng = Random(2026)
    masked = Dataset(
        dataset.columns,
        tuple(
            tuple(
                "" if i < 3 and rng.random() < 0.25 else value
                for i, value in enumerate(row)
            )
            for row in dataset.rows
        ),
    )
    injected = Dataset(
        (*dataset.columns, "synthetic_copy", "synthetic_encoding"),
        tuple((*row, row[-1], "encoded_" + row[-1]) for row in dataset.rows),
    )
    expected = {"synthetic_copy", "synthetic_encoding"}
    audits, trials, skipped = [], [], []
    for seed in seeds:
        config = SplitConfig("stratified", seed=seed)
        original_split = split(dataset, config, target)
        injection_split = split(injected, config, target)
        for threshold in THRESHOLDS:
            audit = LeakageConfig(association_threshold=threshold)
            original = inspect_leakage(dataset, target, original_split, audit)
            signals = inspect_leakage(injected, target, injection_split, audit)
            strong = {
                item.columns[0]
                for item in signals
                if item.method in {"target_copy", "target_bijection"}
            }
            audits.append(
                {
                    "seed": seed,
                    "threshold": threshold,
                    "original_heuristics": sorted(
                        {
                            item.columns[0]
                            for item in original
                            if item.method
                            in {"predictive_association", "categorical_association"}
                        }
                    ),
                    "original_confirmed_violations": sum(
                        item.classification == "confirmed_violation"
                        for item in original
                    ),
                    "injection_true_positives": len(expected & strong),
                    "injection_false_negatives": len(expected - strong),
                    "strong_flags_on_original_features": sorted(strong - expected),
                }
            )
        manifest = split(masked, config, target)
        violations = [
            item.id
            for item in inspect_leakage(masked, target, manifest)
            if item.classification == "confirmed_violation"
        ]
        if violations:
            skipped.append({"seed": seed, "violations": violations})
            continue
        arms = {
            method: fit_baseline(
                masked,
                target,
                manifest,
                ModelConfig(seed=seed, imputation=method),
                include_test=True,
            )["metrics"]
            for method in ("median", "mean")
        }
        metrics = {}
        for partition in ("validation", "test"):
            metrics[partition] = {}
            for metric in ("accuracy", "balanced_accuracy", "macro_f1"):
                before, after = (
                    arms[method][partition][metric] for method in ("median", "mean")
                )
                metrics[partition][metric] = {
                    "median": before,
                    "mean": after,
                    "delta": after - before,
                }
        trials.append(
            {"seed": seed, "split_sha256": manifest.fingerprint, "metrics": metrics}
        )
    summary = {}
    for partition in ("validation", "test"):
        summary[partition] = {}
        for metric in ("accuracy", "balanced_accuracy", "macro_f1"):
            deltas = [trial["metrics"][partition][metric]["delta"] for trial in trials]
            summary[partition][metric] = (
                {
                    "mean_delta": mean(deltas),
                    "min_delta": min(deltas),
                    "max_delta": max(deltas),
                }
                if deltas
                else None
            )
    return {
        "dataset_sha256": canonical(dataset),
        "masked_sha256": canonical(masked),
        "rows": len(dataset.rows),
        "features": len(dataset.columns) - 1,
        "masked_cells": sum(
            a != b
            for left, right in zip(dataset.rows, masked.rows, strict=True)
            for a, b in zip(left, right, strict=True)
        ),
        "detector_trials": audits,
        "intervention_trials": trials,
        "skipped": skipped,
        "intervention_summary": summary,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark on bundled UCI classification datasets."
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    start = perf_counter()
    results = {}
    for name, loader in (
        ("breast-cancer-wisconsin", load_breast_cancer),
        ("wine", load_wine),
    ):
        bundle = loader()
        data = Dataset(
            (*bundle.feature_names, TARGET),
            tuple(
                (*map(str, row), str(label))
                for row, label in zip(bundle.data, bundle.target, strict=True)
            ),
        )
        results[name] = evaluate(data, TARGET)
    report = json.dumps(
        {
            "schema_version": "1.0",
            "scikit_learn": version("scikit-learn"),
            "seeds": SEEDS,
            "mask_seed": 2026,
            "datasets": results,
            "elapsed_seconds": perf_counter() - start,
        },
        indent=2,
        allow_nan=False,
    )
    if args.output:
        args.output.write_text(report + "\n", encoding="utf-8")
    else:
        print(report)


if __name__ == "__main__":
    main()
