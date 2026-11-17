import argparse
import csv
import io
import json
import os
import random
import tracemalloc
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter

from datagenome.anomalies import detect_anomalies
from datagenome.experiments import Intervention, compare
from datagenome.identity import canonical
from datagenome.ingestion import Dataset
from datagenome.intelligence import analyze
from datagenome.leakage import LeakageConfig, inspect_leakage
from datagenome.modeling import MODELS, ModelConfig, fit_baseline
from datagenome.profiling import profile
from datagenome.splits import Manifest, SplitConfig

SCENARIOS = (
    "clean",
    "target-copy",
    "target-transform",
    "legitimate-predictor",
    "cross-split",
    "conflicting-labels",
    "group",
    "temporal",
    "anomalies",
    "missing",
    "imbalance",
    "redundant",
    "constant",
    "identifier",
    "mixed",
)


def fixture(
    scenario: str, seed: int, n: int
) -> tuple[Dataset, Manifest, LeakageConfig, set[int]]:
    rng = random.Random(seed)
    columns = ("x", "y", "aux", "label")
    rows = []
    start = date(2024, 1, 1)
    injected: set[int] = set()
    for i in range(n):
        label = i % 2
        x, y = rng.gauss(0, 1), rng.gauss(0, 1)
        observed = f"{rng.random():.10f}"
        if scenario in {"target-copy", "target-transform"}:
            observed = (
                str(label)
                if scenario == "target-copy"
                else ("one" if label else "zero")
            )
            injected.add(i + 1)
        elif scenario == "legitimate-predictor":
            observed = str(label * 10 + rng.gauss(0, 0.25))
        elif scenario == "group":
            observed = str(i % 12)
        elif scenario == "temporal":
            observed = str(start + timedelta(days=i if i != n - 1 else 0))
            if i == n - 1:
                injected.add(i + 1)
        elif scenario == "constant":
            observed = "constant"
        elif scenario == "identifier":
            observed = f"key{i}"
        elif scenario == "redundant":
            observed = str(x)
        elif scenario == "imbalance":
            label = int(i % 25 == 0)
        if scenario in {"anomalies", "mixed"} and i % 47 == 0:
            x, y = 14 + x, -14 + y
            injected.add(i + 1)
        row = [str(x), str(y), observed, str(label)]
        if scenario in {"missing", "mixed"} and i % 19 == 0:
            row[0] = row[2] = ""
            injected.add(i + 1)
        rows.append(tuple(row))
    if scenario in {"cross-split", "conflicting-labels"}:
        rows[-1] = rows[0] if scenario == "cross-split" else (*rows[0][:-1], "1")
        injected.add(n)
    if scenario == "group":
        injected.update(range(n * 3 // 5 + 1, n + 1))
    dataset = Dataset(columns, tuple(rows))
    config = SplitConfig(seed=seed)
    manifest = Manifest(
        canonical(dataset),
        config,
        {
            "train": list(range(1, n * 3 // 5 + 1)),
            "validation": list(range(n * 3 // 5 + 1, n * 4 // 5 + 1)),
            "test": list(range(n * 4 // 5 + 1, n + 1)),
        },
    )
    return (
        dataset,
        manifest,
        LeakageConfig(
            group="aux" if scenario == "group" else None,
            time="aux" if scenario == "temporal" else None,
        ),
        injected,
    )


def quality(found: set[int], expected: set[int]) -> dict[str, float | int | None]:
    true = len(found & expected)
    return {
        "true_positives": true,
        "false_positives": len(found - expected),
        "false_negatives": len(expected - found),
        "precision": true / len(found) if found else None,
        "recall": true / len(expected) if expected else None,
    }


def run(seeds: list[int], n: int) -> dict[str, object]:
    output = {}
    for seed in seeds:
        results = {}
        for scenario in SCENARIOS:
            dataset, manifest, config, mask = fixture(scenario, seed, n)
            leak = inspect_leakage(dataset, "label", manifest, config)
            intel = analyze(dataset, "label")
            anomalies = detect_anomalies(dataset, "label")
            methods = sorted({signal.method for signal in leak})
            item = {
                "leakage_methods": methods,
                "confirmed": sum(
                    signal.classification == "confirmed_violation" for signal in leak
                ),
                "feature_findings": sorted({f["method"] for f in intel["findings"]}),
                "conflict_groups": len(intel["duplicates"]["conflicting_labels"]),
                "profile_findings": sorted(
                    {finding.category for finding in profile(dataset, "label").findings}
                ),
            }
            if scenario in {"clean", "anomalies"}:
                scores = {
                    name: quality(
                        {
                            record
                            for record, score in detector["scores"].items()
                            if score > detector["threshold"]
                        },
                        mask,
                    )
                    for name, detector in anomalies["detectors"].items()
                    if detector["status"] == "evaluated"
                }
                item["detector_quality"] = scores
            if scenario == "cross-split":
                item["exact_rows"] = quality(
                    {
                        record
                        for signal in leak
                        if signal.method == "cross_split_rows"
                        for record in signal.records
                    },
                    mask,
                )
            if scenario == "missing":
                item["missing_rows"] = quality(
                    {
                        record
                        for record, count in intel["row_missing_counts"].items()
                        if count
                    },
                    mask,
                )
            if scenario in {
                "clean",
                "legitimate-predictor",
                "target-copy",
                "target-transform",
            }:
                expected = (
                    {0} if scenario in {"target-copy", "target-transform"} else set()
                )
                found = (
                    {0} if {"target_copy", "target_bijection"} & set(methods) else set()
                )
                item["target_agreement_quality"] = quality(found, expected)
            if scenario == "legitimate-predictor":
                item["models"] = {
                    name: {
                        "validation_accuracy": result["metrics"]["validation"][
                            "accuracy"
                        ],
                        "validation_macro_f1": result["metrics"]["validation"][
                            "macro_f1"
                        ],
                    }
                    for name in MODELS
                    if (
                        result := fit_baseline(
                            dataset, "label", manifest, ModelConfig(name, seed)
                        )
                    )
                }
            if scenario == "constant":
                comparison = compare(
                    dataset, "label", manifest, Intervention(constant_features=("aux",))
                )
                item["intervention"] = {
                    key: comparison[key]
                    for key in (
                        "status",
                        "affected_features",
                        "validation_differences",
                        "held_out_evaluated",
                    )
                }
            results[scenario] = item
        output[str(seed)] = results
    return output


def resources(sizes: list[int], seed: int) -> list[dict[str, object]]:
    results = []
    for size in sizes:
        dataset, manifest, config, _ = fixture("clean", seed, size)
        tracemalloc.start()
        start = perf_counter()
        analyze(dataset, "label")
        inspect_leakage(dataset, "label", manifest, config)
        elapsed = perf_counter() - start
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        results.append(
            {"rows": size, "features": 3, "seconds": elapsed, "python_peak_bytes": peak}
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=240)
    parser.add_argument("--seeds", nargs="+", type=int, default=[104, 221])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--datasets", type=Path)
    args = parser.parse_args()
    if not 100 <= args.rows <= 1000 or any(
        not 0 <= seed < 2**32 for seed in args.seeds
    ):
        parser.error("Use 100 to 1,000 rows and uint32 seeds.")
    if args.datasets:
        args.datasets.mkdir(parents=True, exist_ok=True)
        for seed in args.seeds:
            for scenario in SCENARIOS:
                dataset, manifest, config, injected = fixture(scenario, seed, args.rows)
                prefix = f"{seed}-{scenario}"
                stream = io.StringIO(newline="")
                writer = csv.writer(stream)
                writer.writerow(dataset.columns)
                writer.writerows(dataset.rows)
                for suffix, value in (
                    (".csv", stream.getvalue()),
                    (
                        ".json",
                        json.dumps(
                            {
                                "injected_records": sorted(injected),
                                "split": asdict(manifest),
                                "leakage": asdict(config),
                            },
                            indent=2,
                        ),
                    ),
                ):
                    with (args.datasets / (prefix + suffix)).open(
                        "x", encoding="utf-8", newline=""
                    ) as output:
                        output.write(value)
    payload = json.dumps(
        {
            "scenarios": run(args.seeds, args.rows),
            "resources": resources([240, 1000, 4000], args.seeds[0]),
            "platform": os.name,
        },
        indent=2,
        allow_nan=False,
    )
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
