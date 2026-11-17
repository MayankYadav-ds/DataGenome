import argparse
import json
import tempfile
import tracemalloc
from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random
from time import perf_counter

from datagenome.confirmation import confirm_slices, freeze_slices
from datagenome.drift import DriftConfig, detect_drift
from datagenome.fairness import FairnessConfig, audit_fairness, compare_fairness
from datagenome.independent import freeze_removal, score_frozen
from datagenome.ingestion import Dataset, DatasetError
from datagenome.label_audit import audit_labels
from datagenome.leakage import LeakageConfig, inspect_leakage
from datagenome.modeling import ModelConfig
from datagenome.performance_drift import performance_drift
from datagenome.proxies import detect_proxies
from datagenome.splits import SplitConfig, split
from datagenome.valuation import ValuationConfig

SCENARIOS = (
    "no-shift",
    "mean-small",
    "mean-large",
    "variance",
    "category-frequency",
    "new-category",
    "missingness",
    "dependence",
    "label-frequency",
    "conditional-outcome",
    "temporary-recovery",
    "low-support",
)


def population(rng, kind, size):
    rows = []
    for i in range(size):
        x, z = rng.gauss(0, 1), rng.gauss(0, 1)
        category = "a" if rng.random() < 0.5 else "b"
        extra = rng.random()
        label = int(x + 0.3 * z > 0)
        if kind == "mean-small":
            x += 0.25
        if kind == "mean-large":
            x += 1.2
        if kind == "variance":
            x *= 2.8
        if kind == "category-frequency":
            category = "a" if extra < 0.93 else "b"
        if kind == "new-category" and extra < 0.35:
            category = "new"
        if kind == "dependence":
            z = 0.99 * x + 0.10 * z
        if kind == "label-frequency":
            label = int(extra < 0.9)
        if kind == "conditional-outcome":
            label = 1 - label
        rows.append(
            (
                "" if kind == "missingness" and i % 3 == 0 else str(x),
                str(z),
                category,
                str(label),
            )
        )
    return Dataset(("x", "z", "category", "label"), tuple(rows))


def drift_trials(seed):
    ref = population(Random(seed), "no-shift", 300)
    cfg = DriftConfig(iid=True, seed=seed, permutations=99, summary_only=False)
    results = []
    for name in SCENARIOS:
        other = population(
            Random(seed + 400), name, 10 if name == "low-support" else 300
        )
        value = detect_drift(ref, other, cfg, target="label")
        joint = value["multivariate"]
        signals = [
            {
                "feature": row["feature"],
                "kind": row["kind"],
                "effect": row["effect"],
                "adjusted_p_value": row.get("adjusted_p_value"),
            }
            for row in value["findings"]
            if row.get("severity") == "review"
        ]
        result = {
            "scenario": name,
            "seed": seed,
            "review": signals,
            "multivariate": joint,
            "unsupported_univariate": sum(
                row.get("status") == "insufficient_evidence"
                for row in value["findings"]
            ),
        }
        if name == "conditional-outcome":
            manifest = split(ref, SplitConfig("stratified", seed=seed), "label")
            result["fixed_model"] = performance_drift(ref, other, "label", manifest)[
                "changes"
            ]
        results.append(result)
    return results


def group_trials(seed, folder):
    rng = Random(seed)
    rows = []
    for i in range(360):
        group = int((i % 6 == 0) if i < 216 else (i % 3 == 0))
        y = (i + i // 6) % 2
        observed = 1 - y if i < 216 and group and i % 18 == 0 else y
        feature = 1 - y if i >= 216 and group else y
        x = 4 * feature + rng.gauss(0, 0.4)
        rows.append(
            (
                str(x),
                str(group),
                f"proxy-{group}",
                str(group + rng.gauss(0, 0.18)),
                str(i % 2),
                f"entity-{i // 6}",
                (datetime(2023, 1, 1, tzinfo=UTC) + timedelta(days=i)).isoformat(),
                str(observed),
            )
        )
    data = Dataset(
        (
            "signal",
            "sensitive",
            "planted_proxy",
            "legitimate_association",
            "intersection",
            "entity",
            "time",
            "label",
        ),
        tuple(rows),
    )
    chrono = split(data, SplitConfig("chronological", seed=seed, time="time"), "label")
    grouped = split(data, SplitConfig("group", seed=seed, group="entity"), "label")
    outcome = {
        "seed": seed,
        "fairness": audit_fairness(
            data,
            "label",
            chrono,
            FairnessConfig(
                ("sensitive", "intersection"), min_support=8, min_class_count=3
            ),
        ),
        "proxies": detect_proxies(
            data, chrono, "sensitive", "label", min_support=10, summary_only=False
        ),
        "chronological_label_audit": {
            key: audit_labels(data, "label", chrono)[key]
            for key in ("status", "evaluated_records", "unscored_labeled_records")
        },
        "group_split_sizes": {
            name: len(ids) for name, ids in grouped.partitions.items()
        },
    }
    outcome["random_split_contamination"] = sorted(
        {
            item.method
            for item in inspect_leakage(
                data,
                "label",
                split(data, SplitConfig(seed=seed), "label"),
                LeakageConfig(group="entity", time="time"),
            )
            if item.classification == "confirmed_violation"
        }
    )
    train = chrono.partitions["train"]
    outcome["fairness_intervention"] = compare_fairness(
        data,
        "label",
        chrono,
        FairnessConfig(("sensitive", "intersection"), min_support=8, min_class_count=3),
        ModelConfig(seed=seed),
        tuple(train[i] for i in (0, 18, 36)),
    )
    slice_data = Dataset(
        ("signal", "sensitive", "label"), tuple((r[0], r[1], r[-1]) for r in rows)
    )
    from dataclasses import replace

    from datagenome.identity import canonical

    # Retain timestamps for manifest validation, and keep them out of predictors.
    temporal_data = Dataset(
        (*slice_data.columns, "time"),
        tuple((*r, rows[i][-2]) for i, r in enumerate(slice_data.rows)),
    )
    temporal_manifest = replace(chrono, dataset_sha256=canonical(temporal_data))
    path = folder / f"slices-{seed}.protocol.json"
    freeze_slices(
        temporal_data,
        "label",
        temporal_manifest,
        ModelConfig(seed=seed),
        path,
        min_support=8,
    )
    outcome["confirmation"] = confirm_slices(
        temporal_data, path, folder / f"slice-ledger-{seed}"
    )
    from datagenome.splits import Manifest

    outcome["independent_removal"] = {}
    for name, manifest in (("group", grouped), ("chronological", chrono)):
        axis = "entity" if name == "group" else "time"
        index = data.columns.index(axis)
        numeric = Dataset(
            ("signal", axis, "label"), tuple((r[0], r[index], r[-1]) for r in rows)
        )
        held = Manifest(canonical(numeric), manifest.config, manifest.partitions)
        plan = folder / f"removal-{seed}-{name}.protocol.json"
        try:
            freeze_removal(
                numeric,
                "label",
                held,
                ValuationConfig(method="knn-shapley", k=3, seed=seed),
                ModelConfig(seed=seed),
                0.1,
                plan,
            )
            result = score_frozen(
                numeric, plan, folder / f"removal-ledger-{seed}-{name}"
            )
            outcome["independent_removal"][name] = {
                key: arm["delta"]["accuracy"] for key, arm in result["arms"].items()
            }
        except DatasetError as error:
            outcome["independent_removal"][name] = {"unscored_reason": error.code}
    return outcome


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        tracemalloc.start()
        start = perf_counter()
        seeds = (19, 47)
        report = {
            "seeds": seeds,
            "drift": [row for seed in seeds for row in drift_trials(seed)],
            "subgroups": [group_trials(seed, Path(temporary)) for seed in seeds],
            "runtime_seconds": perf_counter() - start,
            "peak_python_bytes": tracemalloc.get_traced_memory()[1],
        }
        tracemalloc.stop()
    args.output.write_text(
        json.dumps(report, allow_nan=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
