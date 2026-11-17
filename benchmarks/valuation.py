import argparse
import json
import math
import tracemalloc
from pathlib import Path
from random import Random
from statistics import mean
from time import perf_counter

from scipy.stats import kendalltau, spearmanr

from datagenome.identity import canonical
from datagenome.ingestion import Dataset
from datagenome.modeling import ModelConfig
from datagenome.removal import compare_removal
from datagenome.splits import Manifest, SplitConfig
from datagenome.valuation import ValuationConfig, value_data

SCENARIOS = (
    "clean",
    "uniform-noise",
    "class-noise",
    "feature-noise",
    "redundant",
    "duplicates",
    "conflicts",
    "minority",
    "rare",
    "mismatch",
    "irrelevant",
    "difficult",
)


def fixture(scenario, seed, n):
    rng = Random(seed)
    rows = []
    for i in range(n + 14):
        train = i < n
        label = int(i % (5 if scenario == "minority" else 2) == 0)
        center = 2.5 * (2 * label - 1)
        if train and scenario == "mismatch":
            center += 4
        if train and scenario == "irrelevant":
            center = 0
        if train and scenario in {"rare", "difficult"} and i % 7 == 0:
            center /= 8
        rows.append(
            (str(center + rng.gauss(0, 0.85)), str(rng.gauss(0, 1)), str(label))
        )
    mask = set()
    noise_candidates = {
        "uniform-noise": list(range(n)),
        "class-noise": [i for i in range(n) if rows[i][-1] == "1"],
        "feature-noise": sorted(range(n), key=lambda i: abs(float(rows[i][0])))[
            : n // 2
        ],
    }
    if scenario in noise_candidates:
        selection = Random(seed + 101).sample(
            noise_candidates[scenario], min(n // 5, len(noise_candidates[scenario]))
        )
        for i in selection:
            x, z, label = rows[i]
            rows[i] = (x, z, str(1 - int(label)))
            mask.add(i + 1)
    if scenario in {"duplicates", "conflicts"}:
        x, z, label = rows[0]
        rows[1] = (x, z, str(1 - int(label)) if scenario == "conflicts" else label)
        if scenario == "conflicts":
            mask.add(2)
    if scenario == "redundant":
        rows[1] = (str(float(rows[0][0]) + 0.0001), rows[0][1], rows[0][2])
    data = Dataset(("x", "z", "label"), tuple(rows))
    parts = {
        "train": list(range(1, n + 1)),
        "validation": list(range(n + 1, n + 11)),
        "test": list(range(n + 11, n + 15)),
    }
    return data, Manifest(canonical(data), SplitConfig(seed=seed), parts), mask


def ranking(left, right, k):
    def key(row):
        return row["record_id"]

    a, b = sorted(left, key=key), sorted(right, key=key)
    x, y = [r["score"] for r in a], [r["score"] for r in b]

    def finite(value):
        return float(value) if math.isfinite(value) else None

    spearman = (
        finite(spearmanr(x, y).statistic)
        if len(set(x)) > 1 and len(set(y)) > 1
        else None
    )
    kendall = finite(kendalltau(x, y).statistic)
    return {
        "spearman": spearman,
        "kendall": kendall,
        "mae": mean(abs(p - q) for p, q in zip(x, y, strict=True)),
        "top_k_overlap": len(
            {row["record_id"] for row in left[:k]}
            & {row["record_id"] for row in right[:k]}
        )
        / k,
    }


def run():
    start = perf_counter()
    scenarios = []
    for seed in (19, 47):
        for scenario in SCENARIOS:
            data, manifest, mask = fixture(scenario, seed, 25)
            config = ValuationConfig(method="knn-shapley", seed=seed)
            valued = value_data(data, "label", manifest, config)
            k = max(1, len(mask))
            low = {
                row["record_id"]
                for row in sorted(
                    valued["records"], key=lambda row: (row["score"], row["record_id"])
                )[:k]
            }
            random = set(Random(seed + 10).sample(manifest.partitions["train"], k))
            comparison = compare_removal(
                data, "label", manifest, config, ModelConfig(seed=seed), 0.2
            )
            arms = {
                name: {
                    key: arm[key]
                    for key in (
                        "status",
                        "accuracy_change",
                        "class_recall_change",
                        "minority_recall_degraded",
                    )
                    if key in arm
                }
                for name, arm in comparison["arms"].items()
            }
            scenarios.append(
                {
                    "seed": seed,
                    "scenario": scenario,
                    "k": k,
                    "precision_at_k": len(low & mask) / k if mask else None,
                    "recall_at_k": len(low & mask) / len(mask) if mask else None,
                    "random_precision_at_k": len(random & mask) / k if mask else None,
                    "knn_runtime": valued["elapsed_seconds"],
                    "removal": arms,
                    "matched_removal_count": comparison["matched_removal_count"],
                }
            )
    references = []
    for seed in (19, 47):
        data, manifest, _ = fixture("clean", seed, 6)
        results = {
            method: value_data(
                data, "label", manifest, ValuationConfig(method=method, seed=seed)
            )
            for method in ("loo", "shapley", "mc-shapley", "banzhaf", "knn-shapley")
        }
        alternate = value_data(
            data, "label", manifest, ValuationConfig(method="mc-shapley", seed=seed + 1)
        )
        tree = value_data(
            data,
            "label",
            manifest,
            ValuationConfig(method="loo", seed=seed),
            model=ModelConfig(model="decision-tree", seed=seed),
        )
        references.append(
            {
                "seed": seed,
                "mc_vs_exact": ranking(
                    results["mc-shapley"]["records"], results["shapley"]["records"], 3
                ),
                "cross_seed": ranking(
                    results["mc-shapley"]["records"], alternate["records"], 3
                ),
                "cross_model": ranking(results["loo"]["records"], tree["records"], 3),
                "loo_vs_shapley": ranking(
                    results["loo"]["records"], results["shapley"]["records"], 3
                ),
                "runs": {
                    method: {
                        key: r[key]
                        for key in (
                            "elapsed_seconds",
                            "utility_evaluations",
                            "model_fits",
                        )
                    }
                    for method, r in results.items()
                },
            }
        )
    return {
        "schema_version": "1.0",
        "references": references,
        "scenarios": scenarios,
        "seconds": perf_counter() - start,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    tracemalloc.start()
    report = run()
    report["python_peak_bytes"] = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    result = json.dumps(report, allow_nan=False, indent=2)
    if args.output:
        args.output.write_text(result + "\n", encoding="utf-8")
    else:
        print(result)


if __name__ == "__main__":
    main()
